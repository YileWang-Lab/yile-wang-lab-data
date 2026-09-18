"""Opportunity cost of a tile, and the crop that beats it.

    V_task = V_self + V_suppress - V_opportunity
    V_opportunity(tile, t) = max over feasible c of E[Profit(c, tile, t)]

The late-wheat result was a hand-found instance of the degenerate case: after
day 19 nothing but WHEAT can still be planted, so the feasible set collapses to
one element, V_opportunity is 0, and any positive-profit crop should be planted
automatically. Finding that by hand is not a strategy. This module computes the
feasible set and the profit of each member, so every such window -- including
the ones nobody has looked for -- falls out of the arithmetic.

E[Profit] IS EXACT, not fitted. The two yield rules are different and both were
misread earlier in this project, so they are spelled out:

NON-ONGOING (WHEAT, CARROT, MELON). `_new_plant` seeds `yield_units = 1`.
Nothing accrues at the nightly refresh -- `_daily_refresh_plants` returns early
for them. Yield comes from WATER, and only inside a window
(engine line 438-443):

    window_start = (max_yield_day + 1) // 2
    watering at window_start <= age <= max_yield_day adds 1 (2 if fertilized)

so WHEAT (max_yield_day 4, window 2..4) reaches 1 + 3 = 4 units, and MELON
(window 6..12, cap 6) reaches 6 by age 10. HARVEST then DELETES the plant, which
is what makes a non-ongoing crop able to cycle a tile.

ONGOING (STRAWBERRY, TOMATO). Yield accrues at the nightly refresh, one per
`interval` days from `first_yield_day`, and `production_count > max_yield` stops
it permanently (engine line 796) -- `max_yield` is a LIFETIME cap, not just a
holding cap. STRAWBERRY therefore produces exactly 4 units, at ages 10, 12, 14
and 16, and a tile planted after day 13 cannot collect all four before the
season ends. That is the arithmetic behind deferral measuring -10,029 to
-32,276: every day held back is a yield never taken.

LABOUR is counted in unit-turns and priced at the margin. A crop needs PLANT and
WATER on its planting turn, a WATER often enough to never miss two nights in a
row (the engine kills on the second consecutive miss, so alternate days suffice
for survival, but the yield window wants every day), and one HARVEST per
collection.
"""
import math

SEASON_DAYS = 30

CROPS = {
    "WHEAT":      {"seed": 10, "first": 2, "maxday": 4, "interval": 0, "maxy": 6, "ongoing": False},
    "CARROT":     {"seed": 20, "first": 2, "maxday": 3, "interval": 0, "maxy": 4, "ongoing": False},
    "TOMATO":     {"seed": 50, "first": 8, "maxday": 8, "interval": 1, "maxy": 4, "ongoing": True},
    "STRAWBERRY": {"seed": 100, "first": 10, "maxday": 10, "interval": 2, "maxy": 4, "ongoing": True},
    "MELON":      {"seed": 80, "first": 10, "maxday": 12, "interval": 0, "maxy": 6, "ongoing": False},
}


def last_plant_day(crop):
    """Latest day a fresh planting still returns ANYTHING before the buzzer.

    The binding constraint is `first_yield_day` -- the age at which HARVEST is
    first permitted -- not `max_yield_day`, which only bounds how much accrues.
    `dynamic/agent2.py::_last_plant_day` uses max_yield_day and is therefore
    conservative by exactly the gap between the two:

        MELON   17 -> 19   (planted day 19 it still reaches its full 6 units,
                            because the accrual window closes at age 10 anyway)
        WHEAT   25 -> 27   (2 units instead of 4, but 2 units of wheat is $100
                            against a $10 seed and four unit-turns)
        CARROT  26 -> 27   TOMATO 21 -> 21   STRAWBERRY 19 -> 19

    Those two are windows of the same kind the late-wheat refill exploits, found
    by arithmetic rather than by hand -- which is the point of this module.

    BOTH WERE THEN REFUTED BY EXPERIMENT (-1,546, t=-7.0, n=288), and that is
    the loop working rather than a defect: the formula proposes candidates, the
    engine decides. `expected_profit` prices labour at a flat $/unit-turn, which
    understates a LATE planting -- it waters every day until harvest against a
    crew that is winding down, and it finishes inside the terminal liquidation
    window where the turns are wanted for selling. `agent2.TRUE_LAST_PLANT_DAY`
    keeps them reachable and defaults off.
    """
    return SEASON_DAYS - 1 - CROPS[crop]["first"]


def yield_plan(crop, day, fertilized=False):
    """(units, unit_turns, day_done) for planting `crop` on `day`.

    Exact against the engine's two accrual rules. Truncated by the season end
    rather than assumed to complete, which is the whole point at the margins.
    """
    cd = CROPS[crop]
    horizon = SEASON_DAYS - 1 - day          # ages still reachable
    if horizon < cd["first"]:
        return 0.0, 0, day
    step = 2 if fertilized else 1
    if not cd["ongoing"]:
        start = (cd["maxday"] + 1) // 2
        last = min(cd["maxday"], horizon)
        waters_in_window = max(0, last - start + 1) if last >= start else 0
        units = min(cd["maxy"], 1 + step * waters_in_window)
        age_done = max(cd["first"], last)
        # PLANT+WATER, then a WATER on each day up to the harvest, then HARVEST.
        turns = 2 + max(0, age_done - 1) + 1
        return float(units), turns, day + age_done
    n = 0
    age = cd["first"]
    while n < cd["maxy"] and age <= horizon:
        n += 1
        age += cd["interval"]
    units = min(cd["maxy"], n * step)
    age_done = cd["first"] + max(0, n - 1) * cd["interval"]
    turns = 2 + max(0, age_done - 1) + n
    return float(units), turns, day + age_done


# SHADOW PRICE OF CAPITAL, measured rather than assumed
# (dynamic/shadow_price.py: clone the engine at day t, inject cash, play both
# branches to the buzzer with the same myopic agent, difference the banks --
# that is d NAV_T / d C_t sampled off the real engine, 1,200 paired rollouts).
#
#   early, days 0-9   lambda = 2.00 +- 0.19    t vs 1 = +5.36
#   late,  days >=10  lambda = 0.92 +- 0.08    t vs 1 = -0.95, i.e. exactly 1
#   difference        +1.07 +- 0.20            t = +5.29
#
# A dollar in the first ten days is worth TWO at the buzzer; after that it is
# worth one. The scheduler prices both at one, which is precisely the V_{t+1}
# term a per-asset ENPV cannot see (MODEL.md section 15).
#
# TWO LEVELS, NOT A CURVE. The per-day shape is real (chi2 19.6 on dof 8) but
# nine noisy points cannot resolve it -- an earlier attempt interpolated the raw
# points and encoded the noise, which made every crop unprofitable on day 6
# because that day's estimate happened to be 4.44 +- 1.19. The level is
# established at t=5.36; the shape is not, so only the level is shipped.
#
# The cash trace explains the whole thing: we hold $171-360 on days 2-8 when
# capital is worth 2x, and $56,588 on day 24 when it is worth 1x.
LAMBDA_EARLY = 2.00
LAMBDA_LATE = 1.00
LAMBDA_SWITCH_DAY = 10


def shadow_price(day, strength=1.0):
    """lambda(t): what one dollar at day t is worth at the buzzer."""
    lam = LAMBDA_EARLY if int(day) < LAMBDA_SWITCH_DAY else LAMBDA_LATE
    return 1.0 + strength * (lam - 1.0)


def expected_profit(crop, day, unit_price, c_labor=0.0, travel=0.0,
                    fertilized=False, discount=0.0):
    """E[Profit] of planting `crop` on this tile today, in dollars.

        V_self = P(Q) * Y - C_seed - C_labor * H_required

    `unit_price` is the MARGINAL value of a unit of this crop -- pass
    `market_model.sale_value`, and the suppression term rides along inside it,
    so V_self and V_suppress are quoted together.
    """
    units, turns, day_done = yield_plan(crop, day, fertilized)
    if units <= 0:
        return 0.0
    revenue = units * unit_price
    cost = CROPS[crop]["seed"] + c_labor * (turns + travel)
    if not discount:
        return revenue - cost
    # Cash flows priced at the shadow price of the day they occur. Cost is paid
    # NOW, revenue arrives at day_done, and early cash is worth multiples of
    # late cash -- so a long-payback crop planted during the snowball window is
    # charged for locking capital up, which is exactly the term a myopic ENPV
    # drops.
    return (revenue * shadow_price(day_done, discount)
            - cost * shadow_price(day, discount))


def feasible(day, allowed=None, seed_budget=None):
    """Crops that can still be planted today and paid for."""
    out = []
    for crop in CROPS:
        if allowed is not None and crop not in allowed:
            continue
        if day > last_plant_day(crop):
            continue
        if seed_budget is not None and CROPS[crop]["seed"] > seed_budget:
            continue
        out.append(crop)
    return out


def rank(day, price_of, c_labor=0.0, travel=0.0, allowed=None, seed_budget=None,
         discount=0.0):
    """Every feasible crop, best expected profit first."""
    rows = [(expected_profit(c, day, price_of(c), c_labor, travel,
                             discount=discount), c)
            for c in feasible(day, allowed, seed_budget)]
    rows.sort(key=lambda r: -r[0])
    return rows


def best(day, price_of, c_labor=0.0, travel=0.0, allowed=None, seed_budget=None,
         discount=0.0):
    """(crop, profit) of the best feasible planting, or (None, 0.0)."""
    rows = rank(day, price_of, c_labor, travel, allowed, seed_budget, discount)
    if not rows or rows[0][0] <= 0:
        return None, 0.0
    return rows[0][1], rows[0][0]


def opportunity_cost(day, price_of, exclude, c_labor=0.0, travel=0.0,
                     allowed=None, seed_budget=None):
    """V_opportunity: the best thing this tile could do INSTEAD of `exclude`.

    Zero when nothing else is feasible -- which is exactly the window the
    late-season wheat refill exploits, and the general form of it.
    """
    rows = [p for p, c in rank(day, price_of, c_labor, travel, allowed,
                               seed_budget) if c != exclude]
    return max(0.0, rows[0]) if rows else 0.0
