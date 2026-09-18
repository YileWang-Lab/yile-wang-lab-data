"""Greedy marginal-value land/wheat allocator.

Land is the scarce, irreversible resource (100 tiles by ~day 20 if all quadrants are
bought). This finds, for each of 100 tile-slots, which activity to assign it to by
always picking the option with the highest marginal $ contribution over the remaining
season, given everything already assigned (which has already eaten into that
product's price via cumulative supply).

Simplifications (deliberately conservative, refined later by the fast simulator):
  - Every animal/crop is fully tended (fed/watered/cared every day) -- shown by
    animal_economics.py to dominate partial care for animals; crops always get the
    watering bonus window fully exploited.
  - Wheat for feed is bought at the CURRENT rising market price, not grown, per the
    finding that animal margin-per-wheat ($80-$345) dwarfs even an inflated wheat
    buy price. We still check a "grow wheat" option per tile for comparison.
  - Selling happens at a steady rate starting once the product is available, spread
    to the end of the season (mirrors the realistic sell schedule in
    market_capacity.py). This slightly understates value (optimal is more back-loaded)
    but is a safe lower bound for allocation decisions.
"""
import math
from market_capacity import (MARKET_PARAMS, MARKET_I0, PRICE_FLOOR, price,
                              drain_schedule, DAYS)

WHEAT_BUY_BASE_PATH = drain_schedule("WHEAT")  # town's organic wheat drain, for reference

CROPS = {
    "WHEAT":      {"seed": 10, "first_yield_day": 2, "max_yield_day": 4, "interval": 0, "max_yield": 6, "ongoing": False},
    "CARROT":     {"seed": 20, "first_yield_day": 2, "max_yield_day": 3, "interval": 0, "max_yield": 4, "ongoing": False},
    "TOMATO":     {"seed": 50, "first_yield_day": 8, "max_yield_day": 8, "interval": 1, "max_yield": 4, "ongoing": True},
    "STRAWBERRY": {"seed": 100, "first_yield_day": 10, "max_yield_day": 10, "interval": 2, "max_yield": 4, "ongoing": True},
    "MELON":      {"seed": 80, "first_yield_day": 10, "max_yield_day": 12, "interval": 0, "max_yield": 6, "ongoing": False},
}
ANIMALS = {
    "GOOSE": {"cost": 300, "structure": "COOP", "first_yield_day": 4, "interval": 1, "max_held": 4, "product": "EGG"},
    "COW":   {"cost": 400, "structure": "PASTURE", "first_yield_day": 8, "interval": 2, "max_held": 6, "product": "MILK"},
    "SHEEP": {"cost": 500, "structure": "PASTURE", "first_yield_day": 6, "interval": 3, "max_held": 6, "product": "WOOL"},
}


def crop_daily_yield_stream(crop, plant_day=0):
    """Units harvested on each day 0..29 from one continuously-replanted tile,
    fully watered/fertilized. One-time crops auto-replant the moment they're
    harvested (models a hand cycling the tile)."""
    cd = CROPS[crop]
    stream = [0.0] * DAYS
    if not cd["ongoing"]:
        # one-shot: yield_units lands in inventory the day the final bonus-window
        # watering happens; approximate harvest day = max_yield_day, then immediate
        # replant. Fertilized: +2/day in bonus window instead of +1.
        cycle = cd["max_yield_day"] + 1  # +1 turnaround for harvest/replant/dig
        day = plant_day
        while day + cd["max_yield_day"] <= DAYS - 1:
            harvest_day = day + cd["max_yield_day"]
            stream[harvest_day] += cd["max_yield"]  # assume fertilized -> full cap
            day += cycle
        return stream
    else:
        # ongoing: fires every `interval` days from first_yield_day, capped at
        # max_yield total productions, then decays (ignore decay window, negligible).
        n = 0
        d = plant_day + cd["first_yield_day"]
        while d < DAYS and n < cd["max_yield"]:
            stream[d] += 2  # fertilized + watered -> doubled to 2 per tick
            d += cd["interval"]
            n += 1
        return stream


def animal_daily_yield_stream(animal, place_day=0):
    a = ANIMALS[animal]
    stream = [0.0] * DAYS
    pending = 0
    held = 0
    for day in range(place_day, DAYS):
        days_since_first = day - place_day - a["first_yield_day"]
        if days_since_first >= 0 and days_since_first % a["interval"] == 0:
            bonus = pending
            pending = 0
            units = min(a["max_held"] - held, 1 + bonus)  # crude cap tracking
            units = max(0, 1 + bonus)  # yield BEFORE harvest cap; harvested same day by hand
            stream[day] += units
        pending += 1  # fed+cared every day
    return stream


def wheat_needed_for(animal, n, place_day=0):
    """Wheat/day required to keep n animals fed from place_day onward."""
    needed = [0.0] * DAYS
    for day in range(place_day, DAYS):
        needed[day] += n
    return needed


def npv_of_stream(item, stream, sell_from_inventory_offset=0):
    """Revenue if this stream is sold immediately as produced, against a market
    that already reflects `sell_from_inventory_offset` units/day of prior sales
    of the same item (i.e. price impact stacks across activities sharing a product,
    approximated by walking a shared inventory counter -- callers handle stacking)."""
    pass  # replaced by shared-ledger simulation below


class Ledger:
    """Tracks cumulative market inventory per product across ALL allocated activities,
    so marginal value correctly reflects earlier allocations' price impact."""
    def __init__(self):
        self.inv = {item: float(MARKET_I0) for item in MARKET_PARAMS}
        drains = {item: drain_schedule(item) for item in MARKET_PARAMS}
        self.town_drain = drains

    def clone(self):
        c = Ledger.__new__(Ledger)
        c.inv = dict(self.inv)
        c.town_drain = self.town_drain
        return c

    def apply_town_drain(self, day):
        for item in self.inv:
            self.inv[item] -= self.town_drain[item][day]

    def sell(self, item, units_stream):
        """Sell units_stream[day] units of item on each day (fractional ok, we treat
        continuously for smoothness), return total revenue. Mutates inventory."""
        revenue = 0.0
        for day in range(DAYS):
            u = units_stream[day]
            if u <= 0:
                continue
            p = price(item, int(round(self.inv[item])))
            revenue += p * u
            if p > PRICE_FLOOR:
                self.inv[item] += u
        return revenue

    def buy(self, item, units_stream):
        cost = 0.0
        for day in range(DAYS):
            u = units_stream[day]
            if u <= 0:
                continue
            p = price(item, int(round(self.inv[item] - u)))
            cost += p * u
            self.inv[item] -= u
        return cost


def run_town_drain(ledger):
    for day in range(DAYS):
        ledger.apply_town_drain(day)
    return ledger


# --- Build the full-season town-drain baseline ledger (shared across all candidate evals) ---
def base_ledger():
    L = Ledger()
    return L


def marginal_value(activity, ledger, plant_day):
    """Return (revenue_of_one_more_unit, wheat_cost_stream, upfront_cost, product_stream, product)
    for adding ONE more tile of `activity` on top of the current ledger state, WITHOUT
    mutating ledger (uses a clone)."""
    L = ledger.clone()
    if activity in CROPS:
        cd = CROPS[activity]
        stream = crop_daily_yield_stream(activity, plant_day)
        rev = L.sell(activity, stream)
        upfront = cd["seed"] * (DAYS // (cd["max_yield_day"] + 1) + 1 if not cd["ongoing"] else 1)
        # fertilizer needed: one per 3-day window covering the bonus window; approx 1 per cycle for one-shot,
        # 1 per production tick /2 for ongoing (fert lasts 3 days, ongoing ticks every interval<=2)
        return rev, None, upfront, stream, activity
    else:
        a = ANIMALS[activity]
        stream = animal_daily_yield_stream(activity, plant_day)
        rev = L.sell(a["product"], stream)
        wheat_stream = wheat_needed_for(activity, 1, plant_day)
        wheat_cost = L.buy("WHEAT", wheat_stream)
        upfront = a["cost"]
        return rev - wheat_cost, wheat_stream, upfront, stream, a["product"]


def greedy_allocate(total_tiles=100, plant_day=8):
    """plant_day models the fact that land/hands ramp up over the first ~week;
    we allocate as if everything starts on `plant_day` (a conservative single
    ramp-up delay), then greedily pick the best marginal tile repeatedly."""
    ledger = run_town_drain(base_ledger())  # town drain applied once as the shared background
    counts = {k: 0 for k in list(CROPS) + list(ANIMALS)}
    total_profit = 0.0
    log = []
    for i in range(total_tiles):
        best = None
        for activity in list(CROPS) + list(ANIMALS):
            net, wheat_stream, upfront, stream, product = marginal_value(activity, ledger, plant_day)
            season_days_left = DAYS - plant_day
            daily_net = net / season_days_left if season_days_left > 0 else 0
            score = net - upfront  # one-time upfront cost amortized once
            if best is None or score > best[0]:
                best = (score, activity, net, wheat_stream, upfront, stream, product)
        score, activity, net, wheat_stream, upfront, stream, product = best
        if score <= 0:
            log.append(f"tile {i}: stopping, best marginal option {activity} has score {score:.0f} <= 0")
            break
        # commit: mutate the real ledger
        ledger.sell(product, stream)
        if wheat_stream is not None:
            ledger.buy("WHEAT", wheat_stream)
        counts[activity] += 1
        total_profit += score
        log.append(f"tile {i}: -> {activity:<10} marginal net=${net:>8,.0f} upfront=${upfront:>5}  score=${score:>8,.0f}")
    return counts, total_profit, log


def two_player_allocate(tiles_per_player=100, plant_day=8):
    """Both players draw from ONE shared market ledger, picking greedily in
    strict alternation (A, B, A, B, ...) -- i.e. what happens if the opponent
    independently runs the same "best marginal $/tile" logic I do. This is
    the correction to greedy_allocate(), which implicitly assumed a single
    seller has the whole market to itself. In a 2-player match every sale
    (by either side) moves the SAME shared inventory, so a symmetric
    opponent roughly halves my reachable capacity in whichever categories we
    both want -- the interleaving below produces that split mechanically
    rather than by assumption.

    Returns (counts_a, counts_b, profit_a, profit_b, log).
    """
    ledger = run_town_drain(base_ledger())
    counts = [{k: 0 for k in list(CROPS) + list(ANIMALS)} for _ in range(2)]
    profit = [0.0, 0.0]
    picks = [0, 0]
    # "done" covers BOTH exit reasons (hit the tile cap, or best marginal
    # score turned non-positive) so the loop has one unambiguous termination
    # condition -- a done player's turns are skipped, not re-evaluated.
    done = [False, False]
    log = []
    turn = 0
    while not all(done):
        player = turn % 2
        turn += 1
        if done[player]:
            continue
        if picks[player] >= tiles_per_player:
            done[player] = True
            continue
        best = None
        for activity in list(CROPS) + list(ANIMALS):
            net, wheat_stream, upfront, stream, product = marginal_value(activity, ledger, plant_day)
            score = net - upfront
            if best is None or score > best[0]:
                best = (score, activity, net, wheat_stream, upfront, stream, product)
        score, activity, net, wheat_stream, upfront, stream, product = best
        if score <= 0:
            log.append(f"turn {turn}: player {player} stops, best marginal option {activity} score={score:.0f} <= 0")
            done[player] = True
            continue
        ledger.sell(product, stream)
        if wheat_stream is not None:
            ledger.buy("WHEAT", wheat_stream)
        counts[player][activity] += 1
        profit[player] += score
        picks[player] += 1
        log.append(f"turn {turn:>3}: player {player} -> {activity:<10} score=${score:>8,.0f}")
    return counts[0], counts[1], profit[0], profit[1], log


if __name__ == "__main__":
    counts, total_profit, log = greedy_allocate(total_tiles=100, plant_day=8)
    print("=== Greedy allocation (assumes all activity starts day 8, land already bought) ===")
    for line in log[:20]:
        print(line)
    print("...")
    for line in log[-15:]:
        print(line)
    print(f"\nFinal counts: {counts}")
    print(f"Total tiles used: {sum(counts.values())}")
    print(f"Estimated total net profit (season, from day8 onward, excl. land/hire costs): ${total_profit:,.0f}")

    print("\n=== TWO-PLAYER shared market (symmetric opponent, alternating picks) ===")
    ca, cb, pa, pb, log2 = two_player_allocate(tiles_per_player=100, plant_day=8)
    all_activities = list(CROPS) + list(ANIMALS)
    print(f"{'activity':<12} {'solo (1P)':>10} {'me (2P)':>10} {'opp (2P)':>10}")
    for a in all_activities:
        print(f"{a:<12} {counts.get(a, 0):>10} {ca.get(a, 0):>10} {cb.get(a, 0):>10}")
    print(f"{'TOTAL':<12} {sum(counts.values()):>10} {sum(ca.values()):>10} {sum(cb.values()):>10}")
    print(f"\nprofit solo(1P)=${total_profit:,.0f}   profit me(2P)=${pa:,.0f}   profit opp(2P)=${pb:,.0f}")
    print(f"2P profit as % of 1P assumption: {pa/total_profit*100:.0f}%")
    print("\nlast 10 turns of the 2P alternation:")
    for line in log2[-10:]:
        print(line)

    print("\n=== Diagnostic: isolated goose marginal value vs wheat price, at various wheat-inventory deficits ===")
    for wheat_deficit in (0, 200, 500, 1000, 1650, 2500):
        L = base_ledger()
        L.inv["WHEAT"] -= wheat_deficit
        net, wstream, upfront, stream, product = marginal_value("GOOSE", L, 8)
        wprice_now = price("WHEAT", int(L.inv["WHEAT"]))
        print(f"  wheat_deficit={wheat_deficit:>5}  wheat_price=${wprice_now:>4}  goose 1-tile net over remaining season=${net:>8,.0f}")

    print("\n=== Diagnostic: goose vs cow vs sheep marginal $/day at wheat_deficit=1650 (~55 animals x 30 days) ===")
    L = base_ledger()
    L.inv["WHEAT"] -= 1650
    for a in ("GOOSE", "COW", "SHEEP"):
        net, wstream, upfront, stream, product = marginal_value(a, L, 8)
        print(f"  {a:<6} net=${net:>8,.0f}  upfront=${upfront}")
