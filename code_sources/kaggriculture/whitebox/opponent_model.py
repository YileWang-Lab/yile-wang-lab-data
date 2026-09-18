"""Module 1b -- OPPONENT MODEL. Minimal by directive (2026-08-24).

No style classification, no supply/demand pressure ratio, no "animal-heavy /
crop-heavy" labels. Their farming and animal-care choices have NO effect on us
except through one number: price is set only by what BOTH sides actually put
on the market, and what they can put on the market is fully determined by what
they have visibly planted or placed, plus the engine's own growth rules.

    对手种了什么 -> 最早什么时候能收获 -> 最早什么时候会卖

`earliest_available` is that one number, computed from public tiles alone --
their shed is not observable, but what is GROWING is, exactly.
"""
from whitebox import econ, paths


def earliest_available(farm, item, day):
    """Earliest AGENT DAY `farm` could plausibly have `item` on the market.

    PUBLIC TILES ONLY -- what is already planted or placed, never what their
    private seed stock might let them plant next; we cannot see that, so it is
    not modelled. A tile already holding `yield_units > 0` is available NOW,
    which is the correct worst-case assumption for our own timing: assume a
    rational opponent already has what they could already have collected.
    Returns None if nothing visible produces this item at all.
    """
    best = None
    for t in farm.animals.values():
        spec = econ.ANIMALS.get(t.get("animal"))
        if not spec or spec["product"] != item:
            continue
        if int(t.get("yield_units", 0) or 0) > 0:
            return day
        placed = int(t.get("placed_day", day) or day)
        avail = placed + spec["first_yield_day"]
        if best is None or avail < best:
            best = avail
    for t in farm.crops.values():
        cd = econ.CROPS.get(t.get("crop"))
        if not cd or t.get("crop") != item:
            continue
        if int(t.get("yield_units", 0) or 0) > 0:
            return day
        planted = int(t.get("planted_day", day) or day)
        avail = planted + cd["first_yield_day"]
        if best is None or avail < best:
            best = avail
    return best


def earliest_sellable(farm, item, day, min_units=1):
    """Earliest STEP `farm` could have `min_units` of `item` BANKED and
    sellable -- not just ripe.

    Two corrections `earliest_available` does not make, both requested
    directly (2026-08-24) after `earliest_available` was found to answer a
    narrower question than the one that actually matters for timing a sale:

      VOLUME. A single tile ripening early is not a threat worth reacting to
      -- a BATCH is. This walks their producing tiles in ripening order and
      finds the step by which at least `min_units` are available, not the
      first unit off the first tile. `min_units` is left to the caller: it is
      a STRATEGIC choice (how big a dump is worth front-running), not a
      mechanical one, and belongs where `FRONTRUN_LEAD_DAYS` already lives.

      TRAVEL. Ripe is not sellable. `SELL` draws from `private["shed"]` only;
      `HARVEST`/`PICKUP` land in a worker's own pocket, and only a `DROP` on a
      shed-access tile banks it (HANDOFF rule 5 -- the same rule that once
      cost OUR OWN agent every unit of milk it ever picked up). We cannot see
      where their workers will actually be on a future turn, only where the
      tile is, so this charges the triggering tile's round trip to the
      nearest shed tile -- the same shed-anchored assumption `opp_clear_round`
      below and DUSK's collector already use for timing ourselves.

    Returns an AGENT STEP (comparable to `snap.step`), not a day.
    """
    candidates = []
    for pos, t in farm.animals.items():
        spec = econ.ANIMALS.get(t.get("animal"))
        if not spec or spec["product"] != item:
            continue
        held = int(t.get("yield_units", 0) or 0)
        placed = int(t.get("placed_day", day) or day)
        avail = day if held > 0 else placed + spec["first_yield_day"]
        candidates.append((avail, max(held, 1), pos))
    for pos, t in farm.crops.items():
        cd = econ.CROPS.get(t.get("crop"))
        if not cd or t.get("crop") != item:
            continue
        held = int(t.get("yield_units", 0) or 0)
        planted = int(t.get("planted_day", day) or day)
        avail = day if held > 0 else planted + cd["first_yield_day"]
        candidates.append((avail, max(held, 1), pos))
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0])
    cum = 0
    for avail, units, pos in candidates:
        cum += units
        if cum >= min_units:
            home = min(paths.dist(pos, s) for s in paths.SHED_TILES)
            return max(day, avail) * 24 + 2 * home + 2   # there, harvest+drop
    return None


def opp_clear_round(farm):
    """719 - (ceil(A / W) + 1) -- their forced liquidation turn.

    Unchanged from DUSK (HANDOFF section 38): a physical bound from public
    animal count and crew size, not a behavioural guess. Kept here because it
    answers the same class of question as `earliest_available` -- a date, from
    public state, nothing else.
    """
    animals = len(farm.animals)
    if animals <= 0:
        return None
    workers = max(1, farm.workers)
    return 719 - ((animals + workers - 1) // workers + 1)
