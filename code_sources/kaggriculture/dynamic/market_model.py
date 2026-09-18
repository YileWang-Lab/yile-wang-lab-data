"""Exact market arithmetic, and the marginal value of one more sale.

Everything here is derived from the engine's own pricing block
(`kaggriculture.py` lines 27-80), not fitted. `price()` reproduces
`market_price()` bit for bit, including the int rounding and the $1 floor, so
any quantity built on it is exact rather than approximate.

WHY THE MARGINAL VALUE OF A SALE IS NOT ITS PRICE
-------------------------------------------------
Market inventory is a pure accumulator: `_town_consume` subtracts the same
amount whatever we do, and `_commit_unit` adds one per sale above the floor.
So an extra unit sold at step s raises inventory by 1 for the REST OF THE
SEASON, and every later sale by EITHER player clears one slope lower.

Write P for the price curve, |P'| for its local slope, and let N_us and N_them
be the units each player still has to sell after step s. Margin is our revenue
minus theirs, so differentiating:

    MV(sale at s) = P(inv) - |P'|*N_us + |P'|*N_them
                  = P(inv) + |P'| * (N_them - N_us)

The face price is only the first term. The second is the suppression term the
strategy notes have been reaching for, and it is SIGNED: pushing volume into a
book we ourselves still have to sell into is self-harm, and that is why
`planner`'s wheat-flooding and capped-book-flooding experiments both came back
negative while costing the opponent nothing. Suppression pays only where the
opponent's remaining supply of that product exceeds our own.

WHICH BOOKS CAN ACTUALLY BE SUPPRESSED
--------------------------------------
The excess is permanent only until the floor clips it or the town drains it
away. Town demand is what decides that, and it is wildly uneven, because a
product's demand comes only from the shops that happen to unlock:

    item         units to $1     season town drain     drain/depth
    MELON              158              30                 0.19
    FERTILIZER         493               0                 0.00
    WOOL                59             246                 4.2
    MILK                76             331                 4.4
    STRAWBERRY          62             422                 6.8
    EGG              (log)             225                  -
    WHEAT            (log)             523                  -

MELON is in NO shop's product list -- only the town centre's 1-per-24-steps
touches it -- so a melon sold is a melon the book carries to the end of the
season. FERTILIZER has no buyer at all. Those two are the books where being
first is worth something, and they are exactly the two the front-run audit
measured a POSITIVE realised-price edge on (+24.3 and +1.1). The three the
audit measured NEGATIVE (MILK -2.8, STRAWBERRY -2.1, WOOL -2.2) are exactly
the three whose town drain exceeds their depth several times over: dumping
into them buys a price cut the town undoes within days, while our own later
units pay for it. The audit read that ordering as market DEPTH; it is
non-recovery, and depth is only correlated with it.
"""
import math

MARKET_I0 = 10000
PRICE_FLOOR = 1
HINGE_GAIN = 8.0
SEASON_STEPS = 720
TURNS_PER_DAY = 24

PRODUCTS = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK",
            "WOOL", "FERTILIZER"]

MARKET_PARAMS = {
    "WHEAT":      {"base":  25, "T": 400, "below_func": "sqrt",  "below_target": 0.80, "above_func": "log",    "above_target": 0.20},
    "CARROT":     {"base":  35, "T": 450, "below_func": "hinge", "below_target": 1.00, "above_func": "sqrt",   "above_target": 0.70},
    "TOMATO":     {"base":  60, "T": 200, "below_func": "hinge", "below_target": 0.40, "above_func": "sqrt",   "above_target": 0.60},
    "STRAWBERRY": {"base": 120, "T": 100, "below_func": "sqrt",  "below_target": 0.70, "above_func": "linear", "above_target": 1.60},
    "MELON":      {"base": 250, "T": 300, "below_func": "log",   "below_target": 0.20, "above_func": "sq",     "above_target": 3.60},
    "EGG":        {"base":  50, "T": 332, "below_func": "hinge", "below_target": 0.40, "above_func": "log",    "above_target": 0.20},
    "MILK":       {"base": 160, "T": 122, "below_func": "sqrt",  "below_target": 0.60, "above_func": "linear", "above_target": 1.60},
    "WOOL":       {"base": 200, "T": 105, "below_func": "log",   "below_target": 0.20, "above_func": "sq",     "above_target": 3.20},
    "FERTILIZER": {"base": 100, "T": 200, "below_func": "linear", "below_target": 0.40, "above_func": "linear", "above_target": 0.40},
}

SHOP_PRODUCTS = {
    "BAKERY":         ("EGG", "WHEAT"),
    "PIZZA_SHOP":     ("MILK", "TOMATO", "WHEAT"),
    "BRUNCH_SPOT":    ("EGG", "WHEAT", "STRAWBERRY"),
    "YARN_STORE":     ("WOOL",),
    "ICE_CREAM_SHOP": ("STRAWBERRY", "MILK", "WHEAT"),
    "PET_CAFE":       ("CARROT",),
    "SMOOTHIE_SHOP":  ("STRAWBERRY", "MILK"),
    "FARMERS_MARKET": ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY"),
}
TOWN_CENTER_PRODUCTS = [p for p in PRODUCTS if p != "FERTILIZER"]
SHOP_INTERVAL = 4
CENTER_INTERVAL = 24


# ------------------------------------------------------------- price curve

def _shape(func, x, T=None):
    x = max(0.0, x)
    if func == "linear": return x
    if func == "sq":     return x * x
    if func == "sqrt":   return math.sqrt(x)
    if func == "log":    return math.log(1.0 + x)
    if func == "log10":  return math.log10(1.0 + x)
    if func == "hinge":
        if not T or T <= 0:
            return x
        u = x / T
        return u + HINGE_GAIN * max(0.0, u - 1.0) ** 2
    return x


def _dshape(func, x, T=None):
    """d/dx of _shape. Used for the slope, so the marginal terms do not need a
    finite difference (which is noisy at x=0 where sqrt and log are steep)."""
    x = max(0.0, x)
    if func == "linear": return 1.0
    if func == "sq":     return 2.0 * x
    if func == "sqrt":   return 0.5 / math.sqrt(x) if x > 0 else 1e3
    if func == "log":    return 1.0 / (1.0 + x)
    if func == "log10":  return 1.0 / ((1.0 + x) * math.log(10.0))
    if func == "hinge":
        if not T or T <= 0:
            return 1.0
        u = x / T
        return (1.0 + 2.0 * HINGE_GAIN * max(0.0, u - 1.0)) / T
    return 1.0


_AMP = {}
for _it, _p in MARKET_PARAMS.items():
    _AMP[_it] = (
        _p["below_target"] * _p["base"] / _shape(_p["below_func"], _p["T"], _p["T"]),
        _p["above_target"] * _p["base"] / _shape(_p["above_func"], _p["T"], _p["T"]),
    )


def price(item, inventory):
    """Exact mirror of the engine's `market_price` (int, floored at $1)."""
    p = MARKET_PARAMS.get(item)
    if p is None:
        return PRICE_FLOOR
    base, T = p["base"], p["T"]
    amp_lo, amp_hi = _AMP[item]
    if inventory < MARKET_I0:
        v = base + amp_lo * _shape(p["below_func"], MARKET_I0 - inventory, T)
    elif inventory > MARKET_I0:
        v = base - amp_hi * _shape(p["above_func"], inventory - MARKET_I0, T)
    else:
        v = float(base)
    return max(PRICE_FLOOR, int(round(v)))


def slope(item, inventory):
    """|dP/d(inventory)| in dollars per unit, at this inventory.

    This is the price EVERY later sale by either player loses when one more
    unit is added. Zero once the book is on the floor -- a floored book does
    not record the sale, so it cannot be pushed any lower.
    """
    p = MARKET_PARAMS.get(item)
    if p is None or price(item, inventory) <= PRICE_FLOOR:
        return 0.0
    base, T = p["base"], p["T"]
    amp_lo, amp_hi = _AMP[item]
    if inventory < MARKET_I0:
        return amp_lo * _dshape(p["below_func"], MARKET_I0 - inventory, T)
    return amp_hi * _dshape(p["above_func"], max(0.0, inventory - MARKET_I0), T)


def price_f(item, inventory):
    """`price` without the integer rounding. Used where a quantity is being
    integrated over many units and the $1 rounding steps would accumulate."""
    p = MARKET_PARAMS.get(item)
    if p is None:
        return float(PRICE_FLOOR)
    base, T = p["base"], p["T"]
    amp_lo, amp_hi = _AMP[item]
    if inventory < MARKET_I0:
        v = base + amp_lo * _shape(p["below_func"], MARKET_I0 - inventory, T)
    elif inventory > MARKET_I0:
        v = base - amp_hi * _shape(p["above_func"], inventory - MARKET_I0, T)
    else:
        v = float(base)
    return max(float(PRICE_FLOOR), v)


def realized_price(item, inventory, n, shops, days, opp_units=0.0):
    """Average $/unit actually obtained for selling `n` units over `days`.

        P_realized(Q) = f(Q_ours + E[Q_opponent])

    This is the endogenous half of every asset valuation. A marginal quote
    prices ONE more unit; an asset produces many, and each one it produces
    lowers the price of the next. Without this feedback a sixth cow is worth
    the same as the first, which is how a fixed-count portfolio search ends up
    buying production the book cannot absorb.

    The town drains at its own rate throughout, so the book is not a fixed
    budget -- it refills. That is why MELON (no shop demand at all) and
    STRAWBERRY (422 units of season demand against 62 to the floor) behave
    completely differently under the same nominal depth.
    """
    n = float(n)
    if n <= 0:
        return 0.0
    days = max(1, int(days))
    rate = drain_rate(item, shops)
    us_pd = n / days
    them_pd = float(opp_units) / days
    cur = float(inventory)
    total = 0.0
    for _ in range(days):
        # Quote our slice at its own midpoint: the first unit of the day clears
        # above the average and the last below it.
        total += price_f(item, cur + us_pd * 0.5) * us_pd
        cur = cur + us_pd + them_pd - rate
    return max(float(PRICE_FLOOR), total / n)


def revenue(item, inventory, n):
    """Exact proceeds of selling `n` units back-to-back from `inventory`.

    Sales at the floor do not increment inventory (engine line 659), so the
    book stops deepening there and every further unit clears at $1.
    """
    total = 0
    inv = int(inventory)
    for _ in range(max(0, int(n))):
        px = price(item, inv)
        total += px
        if px > PRICE_FLOOR:
            inv += 1
    return total


def units_above(item, inventory, floor_price):
    """How many units can be sold from `inventory` before the quote drops
    below `floor_price`. This is the 'quota' a capped book really has."""
    inv = int(inventory)
    n = 0
    while n < 5000 and price(item, inv) >= floor_price:
        if price(item, inv) <= PRICE_FLOOR:
            break
        inv += 1
        n += 1
    return n


# ------------------------------------------------------------- town demand

def town_take(item, step, shops):
    """Units of `item` the town removes at `step`. Exact."""
    take = 1 if (item in TOWN_CENTER_PRODUCTS and step % CENTER_INTERVAL == 0) else 0
    if step % SHOP_INTERVAL == 0:
        for shop in shops:
            products = SHOP_PRODUCTS.get(shop, ())
            if item in products:
                take += 2 if len(products) == 1 else 1
    return take


def drain_rate(item, shops):
    """Town absorption in units per DAY at the current shop set.

    Six shop ticks and one centre tick per day, so this is exact for a fixed
    shop set and a lower bound while shops are still unlocking (one more every
    three days, to a cap of eight).
    """
    per_tick = 0
    for shop in shops:
        products = SHOP_PRODUCTS.get(shop, ())
        if item in products:
            per_tick += 2 if len(products) == 1 else 1
    centre = 1 if item in TOWN_CENTER_PRODUCTS else 0
    return per_tick * (TURNS_PER_DAY // SHOP_INTERVAL) + centre


def remaining_demand(item, step, shops):
    """Units the town will still absorb before the season ends, at the current
    shop set. A floor on real demand: more shops keep unlocking."""
    days_left = max(0.0, (SEASON_STEPS - step) / float(TURNS_PER_DAY))
    return drain_rate(item, shops) * days_left


# --------------------------------------------------- the marginal-value rule

def sale_value(item, inventory, n_us_future, n_them_future, discount=1.0):
    """Dollar value of selling one unit NOW, counting what it does to every
    later sale by both players.

        MV = P(inv) + |P'(inv)| * (N_them - N_us)

    `n_us_future`  units of this item we ourselves still expect to sell.
    `n_them_future` units the opponent still holds or will produce -- this is
                   what `dynamic/opp_state.py` estimates.
    `discount`     shrinks the second term; it is the coefficient the strategy
                   notes call alpha, and it absorbs the fact that neither
                   player's remaining supply is known exactly and that the town
                   claws some of the excess back on the high-drain books.

    Returns a float that may exceed the face price (the opponent has more to
    sell than we do -- suppress) or fall below it (we do -- meter instead).
    """
    px = float(price(item, inventory))
    if px <= PRICE_FLOOR:
        return px
    k = slope(item, inventory)
    return px + discount * k * (float(n_them_future) - float(n_us_future))


def metered_rate(item, inventory, shops, days_left, stock, n_them_future=0.0):
    """Units per day to sell so the book is not crashed before season end.

    Selling faster than the town drains pushes the price down permanently, so
    the no-crash rate is the drain rate. But holding is only worth it if the
    opponent will not crash the book anyway: every unit THEY sell while we hold
    costs us the same slope with none of the revenue. So the opponent's
    remaining supply is added to what has to clear in the time available.
    """
    days_left = max(1.0, float(days_left))
    must_clear = max(0.0, float(stock))
    natural = drain_rate(item, shops)
    if n_them_future > natural * days_left:
        # They will floor it regardless; metering just donates the book to them.
        return must_clear
    return max(natural, must_clear / days_left)
