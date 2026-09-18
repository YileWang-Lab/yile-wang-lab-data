"""HORIZON as a per-turn SENSOR BUNDLE (2026-08-24).

HANDOFF section 45 named HORIZON and built its two corrected signals inside
`opponent_model.py`, but they are read from exactly one place -- `market.py::
_sell_batch` -- and each caller re-derives them from raw farm tiles. That is
fine for one caller and wrong for several: `earliest_sellable` walks every
producing tile on the opponent's farm, and a behaviour-group trigger that asks
"is a MILK dump coming?" every turn for every premium item would walk that farm
five times a turn, 547 turns a game, inside a search that runs tens of
thousands of games.

This wraps the same two signals -- nothing new is inferred here -- behind one
object with a per-STEP memo, so a trigger costs a dict lookup after the first
ask of the turn:

    h = horizon.sense(snap, tracker)
    h.threat_in("MILK", days=2, min_units=5)   # future ripening, vol+travel
    h.held("MILK")                             # what they are sitting on now
    h.contested(["MILK", "WOOL"])              # either channel, several items

`held` is only meaningful for `OpponentTracker.RELIABLE` items; it returns 0
for the biased half (MILK/WOOL/WHEAT/FERTILIZER) rather than a number that
looks like knowledge and is not. That asymmetry is why `contested` ORs the two
channels instead of requiring both -- for half the products one channel is
structurally absent, and an AND would silently never fire on them.
"""
from whitebox import opponent_model as OM

# Deliberately NOT the section 45 defaults. Those are the SHIPPED trigger's
# thresholds; a behaviour group names its own, because "how big a dump is worth
# reacting to" is the thing being searched, not a constant.
DEFAULT_MIN_UNITS = 6
DEFAULT_LEAD_DAYS = 3

_CACHE = {"key": None, "sell": {}, "hold": {}, "hz": None}


class Horizon:
    """Read-only view over one turn's opponent signals. Cheap to re-ask."""

    __slots__ = ("snap", "tracker")

    def __init__(self, snap, tracker):
        self.snap = snap
        self.tracker = tracker

    # ---------------------------------------------------------- future side
    def earliest_sellable(self, item, min_units=DEFAULT_MIN_UNITS):
        """Step by which they could have `min_units` of `item` BANKED, or None.

        Volume-gated and shed-travel-corrected -- section 45's two corrections
        over `earliest_available`. Memoised per (step, item, min_units).
        """
        key = (item, int(min_units))
        hit = _CACHE["sell"].get(key, 0)
        if hit != 0:
            return hit if hit != -1 else None
        try:
            got = OM.earliest_sellable(self.snap.opp, item, self.snap.day, int(min_units))
        except Exception:
            got = None
        _CACHE["sell"][key] = -1 if got is None else got
        return got

    def threat_in(self, item, days=DEFAULT_LEAD_DAYS, min_units=DEFAULT_MIN_UNITS):
        """True if `min_units` of `item` could be on their market within `days`."""
        step = self.earliest_sellable(item, min_units)
        return step is not None and (step - self.snap.step) <= days * 24

    # --------------------------------------------------------- present side
    def held(self, item):
        """Units of `item` they are inferred to be SITTING ON right now.

        Zero for the items `OpponentTracker` cannot infer without bias, by
        design -- see the module docstring.
        """
        tr = self.tracker
        if tr is None or item not in getattr(tr, "RELIABLE", ()):
            return 0
        hit = _CACHE["hold"].get(item)
        if hit is not None:
            return hit
        try:
            got = int(tr.holdings(item) or 0)
        except Exception:
            got = 0
        _CACHE["hold"][item] = got
        return got

    # --------------------------------------------------------- finance side
    @property
    def cash(self):
        """Opponent cash right now; this field is public, not inferred."""
        try:
            return max(0.0, float(self.snap.opp.money))
        except Exception:
            return 0.0

    def affordability_gap(self, cash_cost):
        """Extra cash required before an order of ``cash_cost`` is feasible.

        A zero gap is an exact necessary cash-feasibility signal. It is not a
        prediction that the opponent will buy: market slots, shed room, tile
        capacity and their objective remain separate constraints.
        """
        return max(0.0, float(cash_cost) - self.cash)

    def can_afford(self, cash_cost):
        """Whether public cash satisfies one proposed order's hard bound."""
        return self.affordability_gap(cash_cost) <= 1e-9

    # ------------------------------------------------------------- combined
    def contested(self, items, days=DEFAULT_LEAD_DAYS, min_units=DEFAULT_MIN_UNITS):
        """The subset of `items` under pressure right now. Order preserved."""
        return [i for i in items
                if self.threat_in(i, days, min_units) or self.held(i) >= min_units]


def sense(snap, tracker):
    """The turn's Horizon. Resets the memo when the step changes."""
    key = (snap.seat, snap.step)
    if _CACHE["key"] != key:
        _CACHE["key"] = key
        _CACHE["sell"] = {}
        _CACHE["hold"] = {}
        _CACHE["hz"] = None
    hz = _CACHE["hz"]
    if hz is None or (tracker is not None and hz.tracker is None):
        hz = Horizon(snap, tracker)
        _CACHE["hz"] = hz
    return hz


def current(snap):
    """This turn's Horizon without needing the tracker in hand.

    `agent.py` calls `sense` once a turn with the real tracker, so any module
    reached later in the same turn gets the fully-equipped object back. A
    module reached WITHOUT that call still gets a working Horizon -- the future
    channel needs only public tiles -- with `held` reading 0, which is the same
    answer it gives for an unreliable item and not a wrong number.
    """
    return sense(snap, None)
