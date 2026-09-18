"""Per-product market capacity: how much money can each product EVER yield in one season?

The environment is market-limited, not production-limited, for most products. This
computes the efficient frontier revenue(units_sold) for each product under an optimal
reserve-price selling policy, given exogenous town drain.

Key mechanics mirrored from kaggriculture.py:
  - price(inv) = base +/- amp * f(|inv - I0|), amp = target*base/f(T), floored at 1
  - SELL quotes at PRE-sell inventory; a sale at price 1 does NOT add to inventory
  - town center drains 1 of every product except FERTILIZER, once per day
  - each unlocked shop instance drains 1 per demanded product every 4 turns (6x/day),
    doubled for single-product shops
  - shops unlock every 3 days, drawn uniformly WITH REPLACEMENT, capped at 8 instances
"""
import math

MARKET_I0 = 10000
PRICE_FLOOR = 1
HINGE_GAIN = 8.0

MARKET_PARAMS = {
    "WHEAT":      {"base":  25, "T": 400, "below_func": "sqrt",  "below_target": 0.80, "above_func": "log",    "above_target": 0.20},
    "CARROT":     {"base":  35, "T": 450, "below_func": "hinge", "below_target": 1.00, "above_func": "sqrt",   "above_target": 0.70},
    "TOMATO":     {"base":  60, "T": 200, "below_func": "hinge", "below_target": 0.40, "above_func": "sqrt",   "above_target": 0.60},
    "STRAWBERRY": {"base": 120, "T": 100, "below_func": "sqrt",  "below_target": 0.70, "above_func": "linear", "above_target": 1.60},
    "MELON":      {"base": 250, "T": 300, "below_func": "log",   "below_target": 0.20, "above_func": "sq",     "above_target": 3.60},
    "EGG":        {"base":  50, "T": 332, "below_func": "hinge", "below_target": 0.40, "above_func": "log",    "above_target": 0.20},
    "MILK":       {"base": 160, "T": 122, "below_func": "sqrt",  "below_target": 0.60, "above_func": "linear", "above_target": 1.60},
    "WOOL":       {"base": 200, "T": 105, "below_func": "log",   "below_target": 0.20, "above_func": "sq",     "above_target": 3.20},
    "FERTILIZER": {"base": 100, "T": 200, "below_func": "linear","below_target": 0.40, "above_func": "linear", "above_target": 0.40},
}

SHOPS = {
    "BAKERY":         ["EGG", "WHEAT"],
    "PIZZA_SHOP":     ["MILK", "TOMATO", "WHEAT"],
    "BRUNCH_SPOT":    ["EGG", "WHEAT", "STRAWBERRY"],
    "YARN_STORE":     ["WOOL"],
    "ICE_CREAM_SHOP": ["STRAWBERRY", "MILK", "WHEAT"],
    "PET_CAFE":       ["CARROT"],
    "SMOOTHIE_SHOP":  ["STRAWBERRY", "MILK"],
    "FARMERS_MARKET": ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY"],
}
PRODUCTS = list(MARKET_PARAMS)
MAX_SHOP_INSTANCES = 8
SHOP_UNLOCK_INTERVAL = 3
SHOP_TICKS_PER_DAY = 6   # townShopSellInterval=4 -> 24/4
DAYS = 30


def shape(func, x, T):
    x = max(0.0, x)
    if func == "linear": return x
    if func == "sq":     return x * x
    if func == "sqrt":   return math.sqrt(x)
    if func == "log":    return math.log(1.0 + x)
    if func == "hinge":
        u = x / T
        return u + HINGE_GAIN * max(0.0, u - 1.0) ** 2
    return x


def price(item, inv):
    p = MARKET_PARAMS[item]
    base, T = p["base"], p["T"]
    if inv < MARKET_I0:
        amp = p["below_target"] * base / shape(p["below_func"], T, T)
        v = base + amp * shape(p["below_func"], MARKET_I0 - inv, T)
    else:
        amp = p["above_target"] * base / shape(p["above_func"], T, T)
        v = base - amp * shape(p["above_func"], inv - MARKET_I0, T)
    return max(PRICE_FLOOR, int(round(v)))


def expected_shop_drain_per_day(item, n_instances):
    """Expected units/day drained by `n_instances` shops drawn uniformly with replacement."""
    per_draw = 0.0
    for products in SHOPS.values():
        if item in products:
            per_draw += (2 if len(products) == 1 else 1) / len(SHOPS)
    return per_draw * n_instances * SHOP_TICKS_PER_DAY


def drain_schedule(item):
    """Expected units drained on each day 0..29."""
    out = []
    for day in range(DAYS):
        n_shops = min(MAX_SHOP_INSTANCES, day // SHOP_UNLOCK_INTERVAL)
        d = expected_shop_drain_per_day(item, n_shops)
        if item != "FERTILIZER":
            d += 1.0                       # town center, once per day
        out.append(d)
    return out


def frontier(item, reserve, first_sell_day=0):
    """Sell a unit whenever price >= reserve. Returns (units, revenue)."""
    inv = float(MARKET_I0)
    drains = drain_schedule(item)
    units = revenue = 0
    for day in range(DAYS):
        inv -= drains[day]
        if day < first_sell_day:
            continue
        # Last day: no future to protect, dump down to the floor.
        r = 1 if day == DAYS - 1 else reserve
        while True:
            p = price(item, int(round(inv)))
            if p < r:
                break
            revenue += p
            units += 1
            if p > PRICE_FLOOR:
                inv += 1
            else:
                break        # floor sales don't move inventory: infinite loop guard
            if units > 20000:
                return units, revenue
    return units, revenue


def best_capacity(item):
    """Sweep the reserve price for the revenue-maximising schedule."""
    best = (0, 0, 0)
    for r in range(1, MARKET_PARAMS[item]["base"] * 3 + 2):
        u, rev = frontier(item, r)
        if rev > best[1]:
            best = (u, rev, r)
    return best


if __name__ == "__main__":
    print(f"{'PRODUCT':<12} {'base':>5} {'drain/day':>10} {'max$':>9} {'units':>7} {'$/unit':>7} {'reserve':>8}")
    print("-" * 66)
    rows = []
    for item in PRODUCTS:
        u, rev, r = best_capacity(item)
        d = drain_schedule(item)
        rows.append((item, rev, u))
        print(f"{item:<12} {MARKET_PARAMS[item]['base']:>5} {sum(d)/DAYS:>10.1f} "
              f"{rev:>9,.0f} {u:>7} {rev/max(1,u):>7.1f} {r:>8}")
    print("-" * 66)
    print(f"{'TOTAL':<12} {'':>5} {'':>10} {sum(r[1] for r in rows):>9,.0f}")

    print("\n--- REALISTIC: sell N units evenly over days 10-29 (shed cap forces this) ---")
    print("    total $ (avg $/unit)")
    NS = (50, 100, 200, 400, 800, 1600)
    print(f"{'PRODUCT':<12}" + "".join(f"{n:>13}" for n in NS))
    for item in PRODUCTS:
        line = f"{item:<12}"
        for n in NS:
            inv = float(MARKET_I0)
            drains = drain_schedule(item)
            sell_days = list(range(10, DAYS))
            per_day = n / len(sell_days)
            revenue = acc = 0.0
            for day in range(DAYS):
                inv -= drains[day]
                if day < 10:
                    continue
                acc += per_day
                while acc >= 1:
                    p = price(item, int(round(inv)))
                    revenue += p
                    acc -= 1
                    if p > PRICE_FLOOR:
                        inv += 1
            line += f"{revenue:>8,.0f}({revenue / n:>3.0f})"
        print(line)
