"""Shared engine constants and price maths. NOT one of the six modules.

Every number here is copied from the installed engine
(`kaggle_environments/envs/kaggriculture/kaggriculture.py`) and re-derived
nowhere else, because the two places this project got burned were a strategy
note quoting animal costs that were 5x wrong and a market model quoting a $45
wheat ceiling that is actually $125.
"""
import math
from functools import lru_cache

MARKET_I0 = 10000
PRICE_FLOOR = 1
SHED_CAPACITY = 100
MAX_ORDERS = 10
TURNS_PER_DAY = 24
STARTING_MONEY = 3000
LAND_ORDER = ("NE", "SW", "SE")
LAND_PRICES = (1000, 2000, 4000)
# The online action space owns at most three quadrants total.  The fourth is
# not an option with a large negative value; it is absent from every planner.
MAX_OWNED_QUADRANTS = 3


def can_buy_land(unlocked_count):
    """Whether exactly one next-quadrant purchase remains in the action set."""
    unlocked_count = int(unlocked_count)
    owned_extra = unlocked_count - 1
    return (1 <= unlocked_count < MAX_OWNED_QUADRANTS
            and 0 <= owned_extra < len(LAND_ORDER)
            and owned_extra < len(LAND_PRICES))

CROPS = {
    "WHEAT":      {"seed": 10, "first_yield_day": 2,  "max_yield_day": 4,  "interval": 0, "max_yield": 6, "ongoing": False},
    "CARROT":     {"seed": 20, "first_yield_day": 2,  "max_yield_day": 3,  "interval": 0, "max_yield": 4, "ongoing": False},
    "TOMATO":     {"seed": 50, "first_yield_day": 8,  "max_yield_day": 8,  "interval": 1, "max_yield": 4, "ongoing": True},
    "STRAWBERRY": {"seed": 100, "first_yield_day": 10, "max_yield_day": 10, "interval": 2, "max_yield": 4, "ongoing": True},
    "MELON":      {"seed": 80, "first_yield_day": 10, "max_yield_day": 12, "interval": 0, "max_yield": 6, "ongoing": False},
}
ANIMALS = {
    "GOOSE": {"cost": 300, "structure": "COOP",    "first_yield_day": 4, "interval": 1, "max_held": 4, "product": "EGG"},
    "COW":   {"cost": 400, "structure": "PASTURE", "first_yield_day": 8, "interval": 2, "max_held": 6, "product": "MILK"},
    "SHEEP": {"cost": 500, "structure": "PASTURE", "first_yield_day": 6, "interval": 3, "max_held": 6, "product": "WOOL"},
}
MARKET_PARAMS = {
    "WHEAT":      {"base":  25, "T": 400, "below_func": "sqrt",   "below_target": 0.80, "above_func": "log",    "above_target": 0.20},
    "CARROT":     {"base":  35, "T": 450, "below_func": "log",    "below_target": 0.20, "above_func": "sqrt",   "above_target": 0.70},
    "TOMATO":     {"base":  60, "T": 200, "below_func": "linear", "below_target": 0.40, "above_func": "sqrt",   "above_target": 0.60},
    "STRAWBERRY": {"base": 120, "T": 100, "below_func": "sqrt",   "below_target": 0.70, "above_func": "linear", "above_target": 1.60},
    "MELON":      {"base": 250, "T": 300, "below_func": "log",    "below_target": 0.20, "above_func": "sq",     "above_target": 3.60},
    "EGG":        {"base":  50, "T": 332, "below_func": "linear", "below_target": 0.40, "above_func": "log",    "above_target": 0.20},
    "MILK":       {"base": 160, "T": 122, "below_func": "sqrt",   "below_target": 0.60, "above_func": "linear", "above_target": 1.60},
    "WOOL":       {"base": 200, "T": 105, "below_func": "log",    "below_target": 0.20, "above_func": "sq",     "above_target": 3.20},
    "FERTILIZER": {"base": 100, "T": 200, "below_func": "linear", "below_target": 0.40, "above_func": "linear", "above_target": 0.40},
}
# Only these two can be BOUGHT as products (`_commit_unit`), which is why they
# are the only two with a financial arbitrage at all.
BUYABLE = ("WHEAT", "FERTILIZER")
# Animals are NOT in PRODUCTS, so `SELL` never quotes them: an animal in the
# shed is worth exactly $0. Measured 2026-08-23, HANDOFF section 38.
SELLABLE = tuple(MARKET_PARAMS)

# Last step at which a purchase can still be grown, harvested and sold.
# (30 - first_yield_day) * 24 - 1. Derived in HANDOFF section 38; the tape
# corroborates the crop line by buying WHEAT seed at 670 and 671 and no later.
SEED_DEADLINE = {c: (30 - CROPS[c]["first_yield_day"]) * TURNS_PER_DAY - 1 for c in CROPS}
ANIMAL_DEADLINE = {a: (30 - ANIMALS[a]["first_yield_day"]) * TURNS_PER_DAY - 1 for a in ANIMALS}

# THE ECONOMIC DEADLINE IS EARLIER THAN THE BIOLOGICAL ONE (2026-08-25).
#
# The line above answers "when can this still RIPEN". Selling it needs more: the
# yield has to be harvested into a hand, banked by the end-of-day auto-drop
# (`_drop_inventories_to_shed`, and only up to shedCapacity), and then sold at a
# price the book will still bear. Measured on 618 ladder seats, the last step at
# which strong players actually issue each purchase is far earlier than the
# biological bound, and the two independent replay sets agree to within a few
# steps:
#
#   item        biological   ladder last-buy   our build
#   MELON              479               155         170
#   GOOSE              623               154       never
#   COW                527               243         322
#   SHEEP              575               251         369
#   STRAWBERRY         479               265         468   <- 203 steps late
#   TOMATO             527               448       never
#   WHEAT/CARROT       671           645/644     669/643
#
# The old `WB_DEADLINE_TRIM` experiment moved these bounds earlier and measured
# -$7,409 paired margin. It is retired, not merely defaulted off: production
# always uses the engine-derived biological bound. Economic timing belongs in
# the value function, where price/cash/labour are state dependent.
DEADLINE_TRIM = 0


def _shape(func, x):
    x = max(0.0, x)
    if func == "linear": return x
    if func == "sq":     return x * x
    if func == "sqrt":   return math.sqrt(x)
    if func == "log":    return math.log(1.0 + x)
    if func == "log10":  return math.log10(1.0 + x)
    return x


@lru_cache(maxsize=32768)
def price(item, inventory):
    """Exact copy of the engine's `market_price`. Floored at $1."""
    p = MARKET_PARAMS.get(item)
    if p is None:
        return PRICE_FLOOR
    base, T = p["base"], p["T"]
    if inventory < MARKET_I0:
        amp = p["below_target"] * base / _shape(p["below_func"], T)
        v = base + amp * _shape(p["below_func"], MARKET_I0 - inventory)
    else:
        amp = p["above_target"] * base / _shape(p["above_func"], T)
        v = base - amp * _shape(p["above_func"], inventory - MARKET_I0)
    return max(PRICE_FLOOR, int(round(v)))


@lru_cache(maxsize=65536)
def sell_revenue(item, qty, inventory):
    """What selling `qty` actually banks, unit by unit at the marginal price.

    Not `qty * price`: the market clears one unit at a time and each sale that
    prices above the floor pushes the inventory up. MILK's above_target is 1.60
    over T=122, so ~100 units takes it from $160 to $1 -- the difference between
    this and the naive product is the entire reason dump sizing matters.
    """
    total, inv = 0, inventory
    for _ in range(max(0, int(qty))):
        p = price(item, inv)
        total += p
        if p > PRICE_FLOOR:
            inv += 1
    return total


@lru_cache(maxsize=65536)
def buy_cost(item, qty, inventory):
    """What buying `qty` costs. The engine quotes at post-buy inventory."""
    total, inv = 0, inventory
    for _ in range(max(0, int(qty))):
        total += price(item, inv - 1)
        inv -= 1
    return total


def hire_cost(n_already_today):
    """mult * fib(n), fib indexed so fib(0)=1: 1, 1, 2, 3, 5, 8, 13, ...

    Four hires cost $7 and the fifth costs $5 more. Cheap early and brutal
    late, which is why hiring order matters more than hiring count.
    """
    a, b = 1, 1
    for _ in range(max(0, int(n_already_today))):
        a, b = b, a + b
    return a


def hire_block_cost(n_already_today, k):
    return sum(hire_cost(n_already_today + i) for i in range(max(0, int(k))))
