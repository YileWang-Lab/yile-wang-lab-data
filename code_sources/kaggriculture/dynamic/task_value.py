"""Economic task valuation for the day scheduler.

The scheduler currently ranks a day's work by OP NAME -- `OP_VALUE` scores
FEED 1000, HARVEST 900, WATER 800 and so on. That makes a melon harvest and a
wheat harvest worth exactly the same 900, when one is six units at $250 and the
other six at $25, and it makes watering a strawberry two days from its first
yield worth the same as watering one that will never yield again.

This prices each task instead:

    V_task = V_self + V_suppress - V_opportunity

`V_self` is the revenue the task actually protects or creates, quoted through
`market_model` at the CURRENT book rather than at a base-price constant. That
matters more than it sounds: measured mid-season, WHEAT trades at $53 against a
base of 25 because both players buy it for feed, and EGG at $89 against a base
of 50 because nothing in our portfolio produces it. Constants get both backwards.

`V_suppress` is not a separate term here. `market_model.sale_value` already
returns `P + alpha*|P'|*(N_them - N_us)`, so pricing a unit through it carries
the suppression adjustment with the correct sign, and a task that produces into
a book the opponent must also sell into is scored up automatically.

`V_opportunity` is left to the scheduler: `route/router.py` drops the
lowest-value tasks when a day is over-subscribed, which is a comparison against
the best alternative by construction. Encoding it in the value as well would
double-count it.

SURVIVAL DOMINATES REVENUE, and the engine says so absolutely: two consecutive
unwatered nights turn a plant into a weed, two unfed nights and the animal
escapes. A task standing between an asset and that threshold is worth the whole
remaining asset, not one op's list price. Those are ranked above everything.
"""
from dynamic import market_model as MM

SEASON_DAYS = 30
TURNS_PER_DAY = 24

CROPS = {
    "WHEAT":      {"seed": 10, "first": 2, "maxday": 4, "interval": 0, "maxy": 6, "ongoing": False},
    "CARROT":     {"seed": 20, "first": 2, "maxday": 3, "interval": 0, "maxy": 4, "ongoing": False},
    "TOMATO":     {"seed": 50, "first": 8, "maxday": 8, "interval": 1, "maxy": 4, "ongoing": True},
    "STRAWBERRY": {"seed": 100, "first": 10, "maxday": 10, "interval": 2, "maxy": 4, "ongoing": True},
    "MELON":      {"seed": 80, "first": 10, "maxday": 12, "interval": 0, "maxy": 6, "ongoing": False},
}
ANIMALS = {
    "GOOSE": {"cost": 300, "first": 4, "interval": 1, "maxheld": 4, "product": "EGG"},
    "COW":   {"cost": 400, "first": 8, "interval": 2, "maxheld": 6, "product": "MILK"},
    "SHEEP": {"cost": 500, "first": 6, "interval": 3, "maxheld": 6, "product": "WOOL"},
}

# An asset that dies tonight if this task is skipped. Ranked above every
# revenue comparison so triage can never trade a living tile for convenience.
CRITICAL = 1_000_000.0


class Ctx:
    """Everything a task needs to be priced, gathered once per day.

    `unit_price(item)` is the marginal value of one more unit of `item` reaching
    the market, suppression term included.
    """

    __slots__ = ("inv", "shops", "day", "n_us", "n_them", "alpha", "_cache")

    def __init__(self, market_inv, shops, day, n_us=None, n_them=None, alpha=1.0):
        self.inv = dict(market_inv or {})
        self.shops = tuple(shops or ())
        self.day = int(day)
        self.n_us = dict(n_us or {})
        self.n_them = dict(n_them or {})
        self.alpha = float(alpha)
        self._cache = {}

    def slope_of(self, item):
        """|dP/dq| at the book's current level -- the sensitivity that turns an
        error in the opponent-supply estimate into an error in our revenue."""
        return MM.slope(item, int(self.inv.get(item, MM.MARKET_I0)))

    def market_price(self, item):
        """The book's current quote, with no marginal or suppression term."""
        return float(MM.price(item, int(self.inv.get(item, MM.MARKET_I0))))

    def realized(self, item, units, days, prior=0.0):
        """Average $/unit for selling `units` of `item` over `days`, against
        the town's drain, the opponent's expected supply, and `prior` -- what
        we are ALREADY committed to selling into the same book.

        `prior` is what makes a marginal asset cheaper than the first one: it
        shifts the starting inventory to where our existing production will
        already have pushed it.
        """
        inv = int(self.inv.get(item, MM.MARKET_I0))
        opp = self.n_them.get(item, 0.0)
        return MM.realized_price(item, inv + max(0.0, prior), units,
                                 self.shops, days, opp_units=opp)

    def unit_price(self, item):
        v = self._cache.get(item)
        if v is None:
            inv = int(self.inv.get(item, MM.MARKET_I0))
            v = MM.sale_value(item, inv, self.n_us.get(item, 0.0),
                              self.n_them.get(item, 0.0), discount=self.alpha)
            self._cache[item] = v
        return v


def _days_left(day):
    return max(0, SEASON_DAYS - day)


def crop_remaining(tile, day):
    """Units this crop tile will still yield if it is kept watered."""
    cd = CROPS.get(tile.get("crop"))
    if not cd:
        return 0.0
    held = float(tile.get("yield_units", 0) or 0)
    age = day - int(tile.get("planted_day", day))
    left = _days_left(day)
    if cd["ongoing"]:
        done = 0
        if age >= cd["first"]:
            done = (age - cd["first"]) // max(1, cd["interval"]) + 1
        remaining = max(0, cd["maxy"] - done)
        reachable = left // max(1, cd["interval"])
        return held + min(remaining, reachable)
    if age >= cd["maxday"]:
        return held
    return held + min(cd["maxy"], cd["maxday"] - age)


def animal_remaining(tile, day):
    """Units this animal will still produce if it is fed and cared for."""
    spec = ANIMALS.get(tile.get("animal"))
    if not spec:
        return 0.0
    held = float(tile.get("yield_units", 0) or 0)
    start = int(tile.get("placed_day", day)) + spec["first"]
    active = max(0, _days_left(day) - max(0, start - day))
    return held + active * 2.0 / spec["interval"]


def tile_revenue(tile, day, ctx):
    """Remaining revenue from this tile, at the market's marginal price."""
    if not isinstance(tile, dict):
        return 0.0
    if tile.get("animal"):
        spec = ANIMALS.get(tile["animal"])
        if not spec:
            return 0.0
        return animal_remaining(tile, day) * ctx.unit_price(spec["product"])
    if tile.get("kind") == "PLANT":
        crop = tile.get("crop")
        if crop not in CROPS:
            return 0.0
        return crop_remaining(tile, day) * ctx.unit_price(crop)
    return 0.0


def value(tile, ops, day, ctx, base_values=None):
    """V_task for one tile's work on one day, in dollars."""
    names = [o[0] for o in ops]
    if not names:
        return 0.0
    t = tile if isinstance(tile, dict) else {}
    remaining = tile_revenue(t, day, ctx)
    total = 0.0

    if t.get("animal"):
        spec = ANIMALS.get(t["animal"])
        product = spec["product"] if spec else None
        if "FEED" in names:
            # Two unfed nights and it escapes; one unfed night on a production
            # day also wipes the banked CARE bonus.
            if int(t.get("consecutive_unfed", 0)) >= 1:
                return CRITICAL + remaining
            total += remaining * 0.5
        if "CARE" in names and product:
            # The bonus is paid in full on the next scheduled production and is
            # worth one extra unit per interval.
            total += ctx.unit_price(product)
        if "HARVEST" in names and product:
            held = float(t.get("yield_units", 0) or 0)
            total += held * ctx.unit_price(product)
            if spec and held >= spec["maxheld"]:
                # At the holding cap further production is simply lost.
                total += remaining * 0.25
        if "COLLECT_FERTILIZER" in names:
            total += ctx.unit_price("FERTILIZER")
        if "PLACE" in names:
            total += remaining
    elif t.get("kind") == "PLANT":
        crop = t.get("crop")
        if "WATER" in names:
            if int(t.get("consecutive_unwatered", 0)) >= 1:
                return CRITICAL + remaining
            total += remaining * 0.5
        if "HARVEST" in names and crop in CROPS:
            total += float(t.get("yield_units", 0) or 0) * ctx.unit_price(crop)
        if "FERTILIZE" in names and crop in CROPS:
            # Fertilizer doubles a night's accrual (engine line 800), so it is
            # worth one extra unit, minus the fertilizer it consumes.
            total += ctx.unit_price(crop) - ctx.unit_price("FERTILIZER")
    else:
        if "PLANT" in names:
            crop = None
            for o in ops:
                if o[0] == "PLANT" and len(o) > 1:
                    crop = o[1]
            cd = CROPS.get(crop)
            if cd:
                left = _days_left(day)
                if cd["ongoing"]:
                    yields = min(cd["maxy"], max(0, (left - cd["first"])) // max(1, cd["interval"]))
                else:
                    yields = cd["maxy"] if left > cd["maxday"] else 0
                total += yields * ctx.unit_price(crop) - cd["seed"]
        if "BUILD_PASTURE" in names or "BUILD_COOP" in names:
            # A structure is only worth the animal it will hold; price it at a
            # cow, the cheapest thing we ever put in a pasture.
            total += _days_left(day) * ctx.unit_price("MILK")
        if "DIG" in names:
            total += 25.0

    if total <= 0.0 and base_values:
        # Nothing economic to say about this op -- fall back to the op-name
        # ordering rather than dropping it to zero and never scheduling it.
        return max(base_values.get(o, 100.0) for o in names) * 0.01
    return total
