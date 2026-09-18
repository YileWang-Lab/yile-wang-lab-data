"""Module 5b -- MARKET MODEL. What a product is worth, and how fast it crashes.

Everything here is COMPUTED from `whitebox.econ` (which is verified equal to the
engine) at import, not hardcoded. Three questions the planting and selling rules
need answered, and none of them is answerable by looking at the base price:

  HOW FAST DOES IT CRASH?   `crash_depth(item)` -- units of glut that halve the
                            price. It is governed by `T`, not by `above_target`:
                            MELON's `above_target` is 3.60, the harshest in the
                            game, yet it takes 112 units to halve because T=300,
                            while WOOL at 3.20 halves in 42 because T=105.

  HOW EXPOSED ARE WE?       `dump_loss(item, q, d)` -- what we lose selling `q`
                            after the opponent dumped `d` first. This is the
                            zero-sum term, and it is not uniform: at q=d=60 it
                            is -5% for EGG and -99% for WOOL.

  HOW FAST DOES IT RECOVER? `town_per_day(item)` -- the town's daily absorption.
                            This decides whether a crash is temporary or
                            permanent, and it REVERSES the ranking above:
                            STRAWBERRY halves in 31 units but the town eats that
                            back in 1.2 days, while MELON halves in 112 and the
                            town absorbs ONE a day, so a melon glut never lifts.

THE PRACTICAL CONSEQUENCE, and it is the opposite of "diversify":

  MELON  high value (100 units = $21,721, 2.4x the next best) AND slow to crash,
         but zero recovery. Plant it, and sell it ONCE, timed. Never trickle.
  MILK / WOOL / STRAWBERRY  crash in 31-42 units and are wiped out by a
         front-runner (-94% to -99%), but the town refills the hole in 1-3 days.
         Sell these in SMALL BATCHES SPREAD OVER DAYS. Never dump.
  EGG / WHEAT  structurally immune (log curve, above_target 0.20): they never
         halve at any volume. Low ceiling, but no opponent can take it away.

So the defence against a front-running opponent is not spreading the portfolio
evenly. It is picking MELON for value, EGG/CARROT as the un-takeable floor, and
above all SPACING the sales of the fragile products across the town's clock.
"""
from whitebox import econ
from whitebox.state import town_take, _SHOPS

I0 = econ.MARKET_I0
SHOP_NAMES = tuple(_SHOPS)


def _shop_tick_units(item, shops):
    """Exact units removed on one shop tick by an observed shop multiset."""
    total = 0
    for shop in shops or ():
        products = _SHOPS.get(shop, ())
        if item in products:
            total += 2 if len(products) == 1 else 1
    return total


# A future shop is drawn uniformly from ``sorted(SHOPS)`` with replacement.
# Linearity of expectation makes its expected contribution on a shop tick this
# finite sum; no Monte Carlo sample or fitted coefficient is involved.
EXPECTED_FUTURE_SHOP_TICK = {
    item: sum(_shop_tick_units(item, (shop,)) for shop in SHOP_NAMES)
          / float(len(SHOP_NAMES))
    for item in econ.SELLABLE
}
MIN_FUTURE_SHOP_TICK = {
    item: min(_shop_tick_units(item, (shop,)) for shop in SHOP_NAMES)
    for item in econ.SELLABLE
}
MAX_FUTURE_SHOP_TICK = {
    item: max(_shop_tick_units(item, (shop,)) for shop in SHOP_NAMES)
    for item in econ.SELLABLE
}


def _config_int(snap, key, default):
    config = getattr(snap, "config", None)
    try:
        value = config.get(key, default) if isinstance(config, dict) else getattr(config, key, default)
        return max(1, int(value))
    except (AttributeError, TypeError, ValueError):
        return int(default)


def _count_multiples(interval, start, end):
    """Count integer multiples of ``interval`` in ``[start, end)``."""
    if start >= end:
        return 0
    return (end - 1) // interval - (start - 1) // interval


def expected_town_take(snap, item, start_step=None, end_step=719):
    """Expected future town drain conditioned on the currently visible shops.

    Current shop instances are observable and therefore enter exactly,
    including duplicates. Future instances are still hidden. The engine draws
    each independently and uniformly with replacement, so an unknown instance
    contributes ``EXPECTED_FUTURE_SHOP_TICK[item]`` on every shop tick after
    its deterministic unlock day. Summing those expectations is exact for
    absorption. It does *not* claim that nonlinear future sale revenue equals
    revenue at the expected inventory; that bundle-level uncertainty remains a
    separate robust-market problem.

    The interval is ``[start_step, end_step)`` and includes the town consumption
    which follows our action at ``start_step``. Step 719 has no agent action.
    """
    if item not in econ.SELLABLE:
        return 0.0
    now = max(0, int(getattr(snap, "step", 0) or 0))
    start = max(now, now if start_step is None else int(start_step))
    end = min(719, max(start, int(end_step)))
    if start >= end:
        return 0.0

    turns_per_day = _config_int(snap, "turnsPerDay", econ.TURNS_PER_DAY)
    shop_tick = _config_int(snap, "townShopSellInterval", 4)
    center_tick = _config_int(snap, "townCenterSellInterval", 24)
    unlock_days = _config_int(snap, "townShopUnlockInterval", 3)
    current_day = now // turns_per_day
    current_shops = tuple(getattr(snap, "shops", ()) or ())
    known_tick = _shop_tick_units(item, current_shops)
    remaining_slots = max(0, 8 - len(current_shops))
    future_tick = EXPECTED_FUTURE_SHOP_TICK[item]

    shop_ticks = _count_multiples(shop_tick, start, end)
    total = float(known_tick * shop_ticks)
    if item != "FERTILIZER":
        total += float(_count_multiples(center_tick, start, end))

    # Each unknown instance contributes on every shop tick from its first
    # usable day onward. Counting those arithmetic-progressions directly is
    # equivalent to the step loop, but bounded by the engine's eight slots.
    first_future_day = (current_day // unlock_days + 1) * unlock_days
    for offset in range(remaining_slots):
        unlock_day = first_future_day + offset * unlock_days
        unlock_step = unlock_day * turns_per_day
        if unlock_step >= end:
            break
        total += future_tick * _count_multiples(
            shop_tick, max(start, unlock_step), end
        )
    return total


def town_take_bounds(snap, item, start_step=None, end_step=719):
    """Exact integer drain interval conditioned on currently visible shops.

    Existing shop instances and the town centre are public and therefore enter
    both endpoints exactly.  Each still-hidden future shop is an independent
    draw from the finite engine shop set, so its minimum and maximum per-tick
    contribution are obtained by enumeration rather than a seeded sample.
    """
    if item not in econ.SELLABLE:
        return 0, 0
    now = max(0, int(getattr(snap, "step", 0) or 0))
    start = max(now, now if start_step is None else int(start_step))
    end = min(719, max(start, int(end_step)))
    if start >= end:
        return 0, 0

    turns_per_day = _config_int(snap, "turnsPerDay", econ.TURNS_PER_DAY)
    shop_tick = _config_int(snap, "townShopSellInterval", 4)
    center_tick = _config_int(snap, "townCenterSellInterval", 24)
    unlock_days = _config_int(snap, "townShopUnlockInterval", 3)
    current_day = now // turns_per_day
    current_shops = tuple(getattr(snap, "shops", ()) or ())
    known = _shop_tick_units(item, current_shops) * _count_multiples(
        shop_tick, start, end,
    )
    if item != "FERTILIZER":
        known += _count_multiples(center_tick, start, end)

    low = high = int(known)
    remaining_slots = max(0, 8 - len(current_shops))
    first_future_day = (current_day // unlock_days + 1) * unlock_days
    for offset in range(remaining_slots):
        unlock_step = (first_future_day + offset * unlock_days) * turns_per_day
        if unlock_step >= end:
            break
        ticks = _count_multiples(shop_tick, max(start, unlock_step), end)
        low += int(MIN_FUTURE_SHOP_TICK[item] * ticks)
        high += int(MAX_FUTURE_SHOP_TICK[item] * ticks)
    return low, high


def _crash_depth(item, frac=0.5):
    """Units of glut that take the price to `frac` of base. None if unreachable."""
    base = econ.MARKET_PARAMS[item]["base"]
    for n in range(1, 3001):
        if econ.price(item, I0 + n) <= base * frac:
            return n
    return None


def _floor_depth(item):
    for n in range(1, 3001):
        if econ.price(item, I0 + n) <= econ.PRICE_FLOOR:
            return n
    return None


def _town_per_day(item, samples=64):
    """Mean units the town removes per 24 steps, over random 8-shop draws.

    Shops are drawn WITH REPLACEMENT and a single-product shop consumes double,
    so the mix matters and is not knowable in advance; the mean over draws is
    the honest planning number. The town centre adds one of every non-fertilizer
    product per day on top.
    """
    import random
    rng = random.Random(20260824)
    tot = 0.0
    for _ in range(samples):
        shops = [rng.choice(SHOP_NAMES) for _ in range(8)]
        tot += sum(town_take(item, s, shops) for s in range(24))
    return tot / samples


CRASH_HALF = {i: _crash_depth(i) for i in econ.SELLABLE}
CRASH_FLOOR = {i: _floor_depth(i) for i in econ.SELLABLE}
TOWN_DAY = {i: _town_per_day(i) for i in econ.SELLABLE}
REV_100 = {i: econ.sell_revenue(i, 100, I0) for i in econ.SELLABLE}

# Days for the town to absorb a half-price glut. inf = it never does.
RECOVERY_DAYS = {
    i: (CRASH_HALF[i] / TOWN_DAY[i]) if (CRASH_HALF[i] and TOWN_DAY[i] > 0) else float("inf")
    for i in econ.SELLABLE
}

# How to sell each product, derived rather than declared.
#   "timed"   -- crashes permanently; one well-chosen sale, never a trickle
#   "spread"  -- crashes fast but the town refills it; small batches over days
#   "free"    -- never halves at any volume; sell whenever convenient
def _policy(item):
    if CRASH_HALF[item] is None:
        return "free"
    if RECOVERY_DAYS[item] > 8.0:
        return "timed"
    return "spread"


SELL_POLICY = {i: _policy(i) for i in econ.SELLABLE}


def dump_loss(item, qty, opp_dumped):
    """Fraction of revenue lost selling `qty` AFTER the opponent sold `opp_dumped`."""
    inv = I0
    for _ in range(int(opp_dumped)):
        if econ.price(item, inv) > econ.PRICE_FLOOR:
            inv += 1
    alone = econ.sell_revenue(item, qty, I0)
    after = econ.sell_revenue(item, qty, inv)
    return 0.0 if alone <= 0 else (after - alone) / float(alone)


def exposure(item):
    """Standing exposure: what a symmetric front-runner costs us on this item."""
    return dump_loss(item, 60, 60)


def safe_batch(item, have, inv=None, floor_price=2):
    """Largest batch whose LAST unit still clears `floor_price`.

    Sized against the curve rather than by a fixed fraction, because the curves
    differ by an order of magnitude: the same 40-unit sale is routine for EGG
    and terminal for STRAWBERRY.
    """
    inv = I0 if inv is None else int(inv)
    n = 0
    for i in range(int(have)):
        if econ.price(item, inv + i) < floor_price:
            break
        n += 1
    return n


def plant_score(item, opp_share=0.0):
    """Value of planting one more tile of `item`, discounted by dump exposure.

    `opp_share` in [0, 1] is how much of the opponent's output is this product,
    read from their public tiles. At 0 the score is raw revenue; at 1 the full
    front-run loss is charged, so a crop the opponent is loaded on is scored at
    what we would actually realise selling second.
    """
    if item not in REV_100:
        return 0.0
    raw = REV_100[item] / 100.0
    return raw * (1.0 + exposure(item) * max(0.0, min(1.0, opp_share)))


def report():
    rows = sorted(econ.SELLABLE, key=lambda i: -REV_100[i])
    out = ["%-12s %8s %7s %7s %8s %9s %8s  %s"
           % ("item", "rev/unit", "half@", "floor@", "town/day", "recover_d",
              "exposure", "policy")]
    for i in rows:
        rd = RECOVERY_DAYS[i]
        out.append("%-12s %8.1f %7s %7s %8.1f %9s %7.0f%%  %s"
                   % (i, REV_100[i] / 100.0,
                      CRASH_HALF[i] or ">3000", CRASH_FLOOR[i] or ">3000",
                      TOWN_DAY[i], ("%.1f" % rd) if rd != float("inf") else "never",
                      100 * exposure(i), SELL_POLICY[i]))
    return "\n".join(out)


if __name__ == "__main__":
    print(report())


# --------------------------------------------------------- portfolio shaping

SELLING_DAYS = 22.0        # roughly day 8 to day 30, when there is output to sell


def absorb_capacity(item, days=SELLING_DAYS, snap=None):
    """Units of `item` the town will take across the season at ~base price.

    Legacy callers use ``TOWN_DAY x days`` and retain the recorded V56
    semantics. A live ``snap`` instead uses the exact current shop multiset and
    the analytical expectation over only the still-hidden future unlocks. This
    is the ceiling on TRICKLED output. Beyond it the price is walked down
    permanently, because there is no other buyer.
    """
    if snap is not None:
        return expected_town_take(snap, item)
    return TOWN_DAY.get(item, 0.0) * days


def oneshot_capacity(item):
    """Units sellable in ONE sale before the price halves -- `crash_depth`.

    The two ceilings are different and apply to different products. MELON's
    trickle ceiling is 22 units for the WHOLE SEASON (the town takes one a day
    and no shop stocks it), but its one-shot ceiling is 112, so melon is grown
    freely and sold once. WOOL is the reverse: a 274-unit trickle ceiling but it
    halves after 42 in a single sale.
    """
    return CRASH_HALF.get(item) or 10 ** 6


def portfolio_ceiling(item, snap=None):
    """Season output above which this product stops paying, whichever way sold."""
    return max(absorb_capacity(item, snap=snap), oneshot_capacity(item))


def diversified_targets(total_units, items=None, snap=None):
    """Season output split so nothing exceeds what the market can absorb.

    DIVERSIFICATION HERE IS NOT A HEDGE, IT IS THE HIGHER-REVENUE ALLOCATION,
    and the measurement says so both ways. 60 units of production, opponent
    holding the same mix and front-running:

        concentrated MILK   alone $5,886   front-run $339   -94%
        concentrated WOOL   alone $7,929   front-run  $60   -99%
        diversified         alone $9,228   front-run $8,179  -11%

    The diversified basket wins even with NO opponent, because marginal price
    falls steeply within a product and not at all across products. Spreading
    output raises the average realised price before it does anything defensive.

    Allocation is by descending base price, each filled to its own ceiling.
    """
    items = list(items or SELL_POLICY)
    out, left = {}, float(total_units)
    for item in sorted(items, key=lambda i: -econ.MARKET_PARAMS[i]["base"]):
        if left <= 0:
            break
        take = min(left, portfolio_ceiling(item, snap=snap))
        if take > 0:
            out[item] = int(take)
            left -= take
    return out


def crop_mix(total_units=400, crops=("MELON", "STRAWBERRY", "TOMATO", "CARROT", "WHEAT"),
             snap=None):
    """Crop tile shares, normalised, from the same ceilings."""
    t = diversified_targets(total_units, crops, snap=snap)
    s = float(sum(t.values()))
    return {k: v / s for k, v in t.items()} if s else {}


def pressure_multiplier(p, lo=0.6, hi=1.8):
    """Pressure ratio -> a batch-size multiplier for `_sell_batch`.

    Same bounded-linear shape as `route/opponent.py::reserve_scale`, which was
    validated in `pbt/intervene.py` (measured +1,611 vs plain kawa): >1 pressure
    scales UP toward `hi` as the glut gets worse, <1 scales DOWN toward `lo` as
    scarcity gets worse. Clamped so a single bad reading cannot zero out or
    double a sell order outright.
    """
    if p >= 1.0:
        frac = min(1.0, (p - 1.0) / 1.5)
        return 1.0 + (hi - 1.0) * frac
    frac = min(1.0, (1.0 - p) / 0.8)
    return 1.0 - (1.0 - lo) * frac
