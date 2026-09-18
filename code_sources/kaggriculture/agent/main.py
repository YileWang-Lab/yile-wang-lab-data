"""Kaggriculture agent.

Design summary (see STRATEGY.md for the derivation):
  - Land is assigned fixed roles from a priority queue (COW/SHEEP first -- long
    lead time, steep diminishing returns -- then STRAWBERRY/MELON/WHEAT, GOOSE
    as filler) the moment a quadrant unlocks. Roles never change once assigned.
  - Every farmer/hand gets a contiguous slice of the role-assigned tiles ("zone")
    and patrols it in a fixed snake order, running a per-tile checklist:
    build structure -> pickup/place animal -> plant seed -> water -> fertilize ->
    feed -> care -> collect fertilizer -> harvest -> move on.
  - Animals are fed and cared EVERY day without exception (verified: full feed
    strictly dominates rationing in $ terms despite double the wheat cost).
  - Each unit starts its day with a small queue of shed pickups (wheat,
    fertilizer, any animal awaiting placement in its zone) while still
    standing on its spawn (shed-adjacent) tile, then patrols.
  - Top-level (market) logic each turn: hire hands up to a target count, buy
    land when comfortably affordable, buy seeds/animals for the next unfilled
    role slots, buy wheat to cover any feed shortfall, and sell shed contents
    above a per-product reserve price (or unconditionally once the shed is
    getting full, to guarantee we never lose goods to overflow discard).

All game constants below are copied from kaggriculture.py; the agent has no
privileged access to the environment beyond its own observation.
"""

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
LAND_ORDER = ["NE", "SW", "SE"]
LAND_PRICES = [1000, 2000, 4000]

# --- Target portfolio, derived in analysis/portfolio_optimizer.py ---
TARGET_COUNTS = {"COW": 13, "SHEEP": 10, "GOOSE": 0,
                 "STRAWBERRY": 50, "MELON": 12, "WHEAT": 14}
# Every role is taken from this table; tiles past the total stay unassigned.
# GOOSE is an explicit slot, never an implicit filler (see _build_priority_queue).

# Sell only above this price, EXCEPT when the shed is nearly full (see
# SHED_PANIC_FRACTION), in which case sell everything regardless of price.
RESERVE_PRICE = {
    "WHEAT": 20, "CARROT": 15, "TOMATO": 25, "STRAWBERRY": 60, "MELON": 80,
    "EGG": 20, "MILK": 80, "WOOL": 90, "FERTILIZER": 10,
}
SHED_PANIC_FRACTION = 0.80

TARGET_HANDS = 16              # hard cap; actual target comes from workload (see _desired_hands)
TILES_PER_HAND = 7              # legacy; retained so old genomes still load
# Daily action cost per tile, by role. An animal needs feed + care + collect
# fertilizer + amortised harvest every day; a crop mostly needs one watering.
ANIMAL_WORK_PER_DAY = 4.0
CROP_WORK_PER_DAY = 1.5
# Useful actions one unit lands per day after walking overhead (~50% of a
# unit's 24 turns go to movement), so this is well below 24.
WORK_PER_HAND = 10.0
# Cap a day's total hiring spend at this fraction of current cash. Hire cost
# is fib(n) per extra hand, so a workload-derived target of ~16 hands costs
# ~2,583/day -- affordable once producing, ruinous on day 1 with $3,000.
# Without this the agent hires to target regardless of income and goes broke
# before its animals mature (measured: score 97 instead of ~50,000).
HIRE_BUDGET_FRACTION = 0.25
SPEND_RESERVE = 150             # never let any single purchase drop money below this
MAX_MARKET_ORDERS = 10
LAND_BUY_CASH_MULTIPLE = 2.2   # buy the next quadrant once money >= price * this
ANIMAL_BUY_CAP_PER_TURN = 1    # throttle so purchases spread across turns/days
SURVIVAL_RESERVE_FRACTION = 1 / 3  # feed-buying uses SPEND_RESERVE * this as its own floor
WHEAT_FEED_BUFFER_MULT = 2      # target wheat stock = placed animals * this

# Endgame reserve-price ramp: 1.0x before RAMP_START_DAY, decays linearly to
# 0 by RAMP_END_DAY. Unsold shed inventory is worth nothing at game end, so
# this converges to "sell at any price" without a separate hard cutoff rule.
RAMP_START_DAY = 24
RAMP_END_DAY = 29

# Score-relative risk: behind on money -> lower reserve (sell more/faster,
# worth the risk to catch up); ahead -> raise reserve (protect the lead).
# Correct because only win/loss is rated, not the margin.
RISK_MULT_BEHIND = 0.75
RISK_MULT_AHEAD = 1.3

# Opponent-relative supply pressure: scale RESERVE_PRICE down toward
# OPP_SCALE_MIN when the opponent has more competing production (by tile
# count) than me for an item's driver crop/animal -- their glut is coming
# regardless of what I do, so it's better to sell into the not-yet-crashed
# price now than hold out for a price that a shared market won't deliver.
# Scales up toward OPP_SCALE_MAX when the opponent has little/none.
OPP_SCALE_MAX = 1.3
OPP_SCALE_MIN = 0.6
OPPONENT_SUPPLY_DRIVER = {
    "MILK": ("animal", "COW"), "WOOL": ("animal", "SHEEP"), "EGG": ("animal", "GOOSE"),
    "STRAWBERRY": ("crop", "STRAWBERRY"), "MELON": ("crop", "MELON"),
    "WHEAT": ("crop", "WHEAT"), "CARROT": ("crop", "CARROT"), "TOMATO": ("crop", "TOMATO"),
}

# When several SELL orders compete for a market-order slot, put the steepest
# glut-curve premium goods in the earliest slots: orders resolve index by
# index across both players within a turn, so an earlier slot is priced
# before an opponent's same-turn sell of the same item drags the price down.
SELL_PRIORITY_ORDER = ["MELON", "WOOL", "MILK", "STRAWBERRY", "TOMATO", "CARROT", "EGG", "WHEAT", "FERTILIZER"]

# Opponent build-trend tracking: a single snapshot of the opponent's tile
# counts says how much they're producing RIGHT NOW, but not whether that
# category is still growing (more glut still coming, discount harder) or
# has plateaued/been abandoned (no extra discount needed). Sampled once per
# day over a short rolling window.
# Build order for animal tiles. Sheep reach first yield on day 6, cows on day
# 8, so completing sheep first starts the earliest cash flow ~2 days sooner --
# and early cash compounds into the next animal purchase. Interleaving delays
# both. (Matches the 4-SHEEP-immediately / cows-ramp-after schedule visible in
# strong public routes.)
ANIMAL_BUILD_ORDER = ("SHEEP", "COW", "GOOSE")
ANIMALS_SEQUENTIAL = True        # finish one animal type before starting the next

OPENING_HANDS = 4                # bodies for the build-out before anything is live
FARM_VIEW = [None]               # our farm dict for the current turn (set in agent())
OPP_HISTORY_WINDOW = 5           # days of samples kept per driver
OPP_GROWTH_DISCOUNT_PER_TILE = 0.05  # extra reserve discount per tile/day of opponent growth
OPP_GROWTH_DISCOUNT_FLOOR = 0.7      # never discount the reserve below this multiplier from growth alone


def _fib(n):
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def _hire_cost(n_already_today):
    return _fib(n_already_today)


def _quadrant_of(x, y, board_size):
    half = board_size // 2
    return ("N" if y < half else "S") + ("W" if x < half else "E")


def _shed_access_tiles(board_size):
    half = board_size // 2
    return [(half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half)]


def _is_shed_adjacent(pos, board_size):
    return tuple(pos) in set(_shed_access_tiles(board_size))


def _snake_order(board_size):
    """Tiles ordered NEAREST-TO-SHED first, tie-broken by boustrophedon.

    Was plain snake order from (0,0), which is the single worst choice: the
    shed sits at the board centre, so (0,0) is the farthest corner, and roles
    were handed out starting there. Every animal needs a wheat round-trip to
    the shed *every day*, so that layout spent ~95% of all unit-actions
    walking (measured: 670 moves vs 35 useful actions over 12 days).

    Sorting by distance-to-shed makes the highest-priority roles (animals,
    which are assigned first) land on the tiles closest to the shed, and keeps
    each unit's contiguous zone slice as a ring near the centre. The snake
    tie-break preserves local clustering within a ring."""
    snake = []
    for y in range(board_size):
        xs = range(board_size) if y % 2 == 0 else range(board_size - 1, -1, -1)
        for x in xs:
            snake.append((x, y))
    access = _shed_access_tiles(board_size)

    def dist_to_shed(t):
        return min(abs(t[0] - a[0]) + abs(t[1] - a[1]) for a in access)

    return sorted(snake, key=lambda t: (dist_to_shed(t), snake.index(t)))


def _build_priority_queue():
    """Animals first (long lead time to first yield, so buy/place ASAP and let
    them mature while crops cycle), then crops evenly interleaved.

    Every role assigned to a tile comes from THIS queue and nowhere else. There
    is deliberately no dynamic filler: an earlier version assigned "GOOSE" to
    every tile past the end of the queue, which meant any portfolio that did
    not sum to >= the whole board silently became "...plus ~90 geese". That
    bankrupted the agent instantly (coops built everywhere, animals bought
    until cash hit zero, no money left to hire hands, one farmer unable to feed
    anything) and scored ~200 instead of ~40,000. It also poisoned the
    parameter search, which learned to always over-fill the board with crops
    purely to keep the queue from running out. Tiles past the queue now stay
    unassigned and are simply not patrolled."""
    animal_roles = [r for r in ANIMAL_BUILD_ORDER if TARGET_COUNTS.get(r, 0) > 0]
    crop_roles = [r for r in ("STRAWBERRY", "MELON", "WHEAT", "TOMATO", "CARROT")
                  if TARGET_COUNTS.get(r, 0) > 0]

    def interleave(roles):
        """Round-robin by completion fraction so types ramp together rather
        than one type monopolising the early (closest-to-shed) tiles."""
        out = []
        idx = {r: 0 for r in roles}
        total = sum(TARGET_COUNTS[r] for r in roles)
        for _ in range(total):
            best_r, best_frac = None, None
            for r in roles:
                if idx[r] >= TARGET_COUNTS[r]:
                    continue
                frac = idx[r] / TARGET_COUNTS[r]
                if best_frac is None or frac < best_frac:
                    best_r, best_frac = r, frac
            if best_r is None:
                break
            idx[best_r] += 1
            out.append(best_r)
        return out

    if ANIMALS_SEQUENTIAL:
        # Finish one animal type before starting the next, in ANIMAL_BUILD_ORDER.
        # Interleaving delays BOTH types' first yield; completing the
        # earliest-maturing type first (sheep reach first yield on day 6 vs
        # cow's day 8) starts the cash flow sooner, and early cash compounds.
        animals = []
        for r in animal_roles:
            animals += [r] * TARGET_COUNTS[r]
    else:
        animals = interleave(animal_roles)
    return animals + interleave(crop_roles)


PRIORITY_QUEUE = _build_priority_queue()


def configure(params):
    """Override tunable constants from a flat dict (used by the search
    harness to evaluate a candidate parameter set in-process). Recomputes
    everything derived from the overridden values and clears episode state.
    Safe to call between episodes; do not call mid-episode."""
    g = globals()
    for k, v in params.items():
        if k not in g:
            raise KeyError(f"unknown tunable parameter: {k}")
        g[k] = v
    g["PRIORITY_QUEUE"] = _build_priority_queue()
    _reset_state()


# --- Global mutable state, persists across turns within one episode process ---
S = {
    "role": {},              # (x, y) -> role string ("COW"/"SHEEP"/"GOOSE"/crop name)
    "queue_ptr": 0,           # next index into PRIORITY_QUEUE for a fresh tile
    "unlocked_count": 0,      # last-seen count of unlocked quadrants, to detect new land
    "zones": {},              # unit_idx -> list[(x,y)]
    "ptr": {},                # unit_idx -> index into zones[unit_idx]
    "zone_sig": None,         # (tile count, peak unit count) zones were last built for
    "zone_units": 0,          # peak unit count the current partition was cut for
    "last_day_for_unit": {},  # unit_idx -> last day we last reset its errand state
    "errand": {},             # unit_idx -> {"target", "item", "qty", "mode"}
    "opp_history": {},        # (kind, name) driver -> list of tile-count samples, oldest first
    "opp_history_day": -1,    # last day we sampled the opponent's build
}


def _reset_state():
    S["role"] = {}
    S["queue_ptr"] = 0
    S["unlocked_count"] = 0
    S["zones"] = {}
    S["ptr"] = {}
    S["zone_sig"] = None
    S["zone_units"] = 0
    S["last_day_for_unit"] = {}
    S["errand"] = {}
    S["opp_history"] = {}
    S["opp_history_day"] = -1


def _assign_roles_for_new_land(farm, board_size):
    unlocked = farm.get("unlocked_quadrants", ["NW"])
    if len(unlocked) == S["unlocked_count"]:
        return
    S["unlocked_count"] = len(unlocked)
    order = _snake_order(board_size)
    unlocked_set = set(unlocked)
    for (x, y) in order:
        if (x, y) in S["role"]:
            continue
        if _quadrant_of(x, y, board_size) not in unlocked_set:
            continue
        if S["queue_ptr"] >= len(PRIORITY_QUEUE):
            break  # portfolio fully placed; leave the rest of the board unassigned
        S["role"][(x, y)] = PRIORITY_QUEUE[S["queue_ptr"]]
        S["queue_ptr"] += 1


def _active_tiles(board_size):
    """Role-assigned tiles in currently unlocked quadrants, snake ordered."""
    return [(x, y) for (x, y) in _snake_order(board_size) if (x, y) in S["role"]]


def _rebuild_zones(board_size, n_units):
    """Partition the role-assigned tiles into one contiguous zone per unit.

    Two things here are load-bearing:

    1. Zones are cut for the HIGH-WATER unit count of the day, not the live
       count. Hands are hired over the first turns of a day, so the live count
       climbs 1,2,3..., and re-cutting on every change reshuffles which tiles
       belong to whom several times a day.
    2. Patrol pointers survive a rebuild. Resetting them sent every unit back
       to the start of its zone whenever the hand count moved, so units
       re-walked ground they had just covered and never reached the far end.
       Together these two made hand counts of 8-11 score ~39 while 6 scored
       ~50,000 -- non-monotonic nonsense that looked like a bad parameter but
       was really zone thrashing.
    """
    tiles = _active_tiles(board_size)
    n_units = max(1, n_units)
    # Only ever grow the partition within a day; _reset_day_zoning() clears it.
    peak = max(n_units, S.get("zone_units", 0))
    sig = (len(tiles), peak)
    if S["zone_sig"] == sig:
        return
    S["zone_sig"] = sig
    S["zone_units"] = peak
    old_ptr = dict(S.get("ptr") or {})
    S["zones"] = {}
    if not tiles:
        S["ptr"] = {}
        return
    n = len(tiles)
    base = n // peak
    extra = n % peak
    i = 0
    for u in range(peak):
        take = base + (1 if u < extra else 0)
        S["zones"][u] = tiles[i:i + take]
        i += take
    # Preserve progress: clamp each unit's old pointer into its new zone.
    S["ptr"] = {u: (old_ptr.get(u, 0) % len(S["zones"][u]) if S["zones"][u] else 0)
                for u in S["zones"]}


def _zone_daily_wheat(unit_idx):
    zone = S["zones"].get(unit_idx, [])
    return sum(1 for t in zone if S["role"].get(t) in ANIMALS)


def _zone_daily_fert(unit_idx):
    zone = S["zones"].get(unit_idx, [])
    return sum(1 for t in zone if S["role"].get(t) in CROPS)


def _desired_hands():
    """Hands needed for the DAILY WORKLOAD, not the tile count.

    The old version divided tile count by a constant, which badly under-hires
    for animal builds: an animal tile costs ~4 actions every single day (feed,
    care, collect fertilizer, and an amortised harvest) while a crop tile
    costs ~1.5 (water daily, plus amortised plant/fertilize/harvest). Measured
    against a strong reference agent, that formula gave us 7 hands and 1,309
    useful actions per game where the reference ran 14 hands and 3,494 -- a
    2.7x action deficit that accounted for almost all of a 4x money gap.

    Labour is also far cheaper than that deficit: the n-th hire of a day costs
    fib(n), so even 14 hands is under $1,000/day against a six-figure bank.

    WORK_PER_HAND is the useful actions a hand actually lands per day after
    walking overhead (~50% of turns go to movement), so it is well under 24.
    """
    # Count only tiles that actually need daily work RIGHT NOW. Sizing off
    # role slots instead pays for hands to tend empty pasture: our hand count
    # sat flat at 8 all season (5,2,4,4,6,14,10,9,13,11,14 for a reference
    # agent scoring 9x more) -- over-hiring while animals were still being
    # bought, then stuck too low once everything was producing.
    n_animals = _placed_animal_count(FARM_VIEW[0]) if FARM_VIEW[0] else 0
    n_crops = _planted_crop_count(FARM_VIEW[0]) if FARM_VIEW[0] else 0
    if n_animals + n_crops == 0:
        # Nothing live yet: still need bodies to build/plant the opening.
        return max(1, min(TARGET_HANDS, OPENING_HANDS))
    work = ANIMAL_WORK_PER_DAY * n_animals + CROP_WORK_PER_DAY * n_crops
    needed = int(-(-work // max(WORK_PER_HAND, 1.0)))  # ceil
    return max(1, min(TARGET_HANDS, needed))


def _placed_animal_count(farm):
    n = 0
    for row in farm["tiles"]:
        for t in row:
            if isinstance(t, dict) and "animal" in t:
                n += 1
    return n


def _planted_crop_count(farm):
    n = 0
    for row in (farm or {}).get("tiles", []) or []:
        for t in row or []:
            if isinstance(t, dict) and t.get("kind") == "PLANT":
                n += 1
    return n


def _count_tiles_by_driver(farm, kind, name):
    total = 0
    for row in farm.get("tiles", []) or []:
        for tile in row or []:
            if not isinstance(tile, dict):
                continue
            if kind == "animal" and tile.get("animal") == name:
                total += 1
            elif kind == "crop" and tile.get("kind") == "PLANT" and tile.get("crop") == name:
                total += 1
    return total


SHOP_PRODUCTS = {
    "BAKERY": ("EGG", "WHEAT"),
    "PIZZA_SHOP": ("MILK", "TOMATO", "WHEAT"),
    "BRUNCH_SPOT": ("EGG", "WHEAT", "STRAWBERRY"),
    "YARN_STORE": ("WOOL",),
    "ICE_CREAM_SHOP": ("STRAWBERRY", "MILK", "WHEAT"),
    "PET_CAFE": ("CARROT",),
    "SMOOTHIE_SHOP": ("STRAWBERRY", "MILK"),
    "FARMERS_MARKET": ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY"),
}
SEASON_DAYS = 30
# Steady-state units/day per producing tile, assuming it is tended (fed+cared /
# watered+fertilized). Animals: base 1 plus the banked CARE bonus, which in
# steady state equals the production interval, so rate = (1+interval)/interval.
# Crops: total yield over the tile's occupancy cycle.
_ANIMAL_RATE = {"GOOSE": 2.0, "COW": 1.5, "SHEEP": 4.0 / 3.0}
_CROP_RATE = {"WHEAT": 6.0 / 5, "CARROT": 4.0 / 4, "MELON": 6.0 / 11,
              "TOMATO": 8.0 / 12, "STRAWBERRY": 8.0 / 17}
_PRODUCT_OF_ANIMAL = {"GOOSE": "EGG", "COW": "MILK", "SHEEP": "WOOL"}


def _remaining_town_demand(item, day, shops):
    """Units of `item` the town will still consume between `day` and season end.

    Shops fire 6x/day (every 4 of 24 turns), single-product shops at double
    rate; the town centre takes one of every non-fertilizer product per day.
    Nobody consumes FERTILIZER at all, which is why its price only ever falls.
    """
    if item == "FERTILIZER":
        return 0.0
    per_day = 1.0  # town centre
    for shop in shops or ():
        products = SHOP_PRODUCTS.get(shop, ())
        if item in products:
            per_day += 6.0 * (2 if len(products) == 1 else 1)
    return per_day * max(0, SEASON_DAYS - day)


def _forecast_supply(farm, item, day):
    """Units of `item` this farm will still put on the market this season,
    read straight off its public tiles. This is the core of opponent
    modelling: their farm layout is fully visible, so their future sell
    pressure is predictable well before they actually sell anything."""
    if farm is None:
        return 0.0
    days_left = max(0, SEASON_DAYS - day)
    if days_left <= 0:
        return 0.0
    rate = 0.0
    fert_animals = 0
    for row in farm.get("tiles", []) or []:
        for tile in row or []:
            if not isinstance(tile, dict):
                continue
            animal = tile.get("animal")
            if animal:
                fert_animals += 1
                if _PRODUCT_OF_ANIMAL.get(animal) == item:
                    rate += _ANIMAL_RATE.get(animal, 1.0)
            elif tile.get("kind") == "PLANT" and tile.get("crop") == item:
                rate += _CROP_RATE.get(item, 0.5)
    if item == "FERTILIZER":
        rate += fert_animals  # every surviving animal yields 1/day, free
    return rate * days_left


def _market_pressure(item, my_farm, opp_farm, day, shops):
    """(my supply + their supply) / remaining demand, for one product.

    >1 means the market cannot absorb what is already coming, so the price
    can only fall and the units sold FIRST are the only ones worth much --
    race, don't hold. <1 means demand outstrips supply and holding pays.
    Returns 1.0 when demand is zero-ish so callers fall back to neutral.
    """
    demand = _remaining_town_demand(item, day, shops)
    if demand <= 1e-6:
        return 2.0  # no demand at all (fertilizer): always oversupplied
    supply = _forecast_supply(my_farm, item, day) + _forecast_supply(opp_farm, item, day)
    return supply / demand


def _update_opponent_history(opp_farm, day):
    """Sample the opponent's competing-production tile counts once per day.
    A single snapshot says how much they're producing right now; the history
    says whether that's still growing (more glut still coming -- discount
    harder) or has plateaued/been abandoned (no extra discount needed)."""
    if opp_farm is None or S["opp_history_day"] == day:
        return
    S["opp_history_day"] = day
    hist = S["opp_history"]
    for driver in set(OPPONENT_SUPPLY_DRIVER.values()):
        kind, name = driver
        count = _count_tiles_by_driver(opp_farm, kind, name)
        samples = hist.setdefault(driver, [])
        samples.append(count)
        if len(samples) > OPP_HISTORY_WINDOW:
            samples.pop(0)


def _opponent_growth_multiplier(driver):
    samples = S["opp_history"].get(driver)
    if not samples or len(samples) < 2:
        return 1.0
    growth_per_day = (samples[-1] - samples[0]) / max(1, len(samples) - 1)
    if growth_per_day <= 0:
        return 1.0
    return max(OPP_GROWTH_DISCOUNT_FLOOR, 1.0 - OPP_GROWTH_DISCOUNT_PER_TILE * growth_per_day)


def _opponent_reserve_scale(my_farm, opp_farm, item, day=0, shops=()):
    """Multiplier on this item's reserve price, from a forecast of how badly
    the market will be oversupplied.

    Replaces a cruder tile-count-share heuristic. Counting whose farm has more
    cows says who produces more, but not whether the *market* can absorb it --
    and absorption is what actually sets the price. Forecasting both farms'
    remaining output against remaining town demand answers the real question:
    hold for a better price, or race the opponent to the floor?
    """
    if opp_farm is None:
        return 1.0
    driver = OPPONENT_SUPPLY_DRIVER.get(item)
    pressure = _market_pressure(item, my_farm, opp_farm, day, shops)
    if pressure >= 1.0:
        # Oversupplied: scale down toward OPP_SCALE_MIN as the glut deepens.
        # Saturates at 3x demand so a wildly oversupplied product does not
        # produce an unboundedly small reserve.
        glut = min(1.0, (pressure - 1.0) / 2.0)
        scale = OPP_SCALE_MAX - (OPP_SCALE_MAX - OPP_SCALE_MIN) * (0.5 + 0.5 * glut)
    else:
        # Undersupplied: hold out, up to OPP_SCALE_MAX.
        scale = OPP_SCALE_MAX - (OPP_SCALE_MAX - OPP_SCALE_MIN) * 0.5 * pressure
    if driver is not None:
        scale *= _opponent_growth_multiplier(driver)
    return scale


def _ramp_fraction(day):
    if day < RAMP_START_DAY:
        return 1.0
    if day >= RAMP_END_DAY:
        return 0.0
    span = max(1, RAMP_END_DAY - RAMP_START_DAY)
    return max(0.0, (RAMP_END_DAY - day) / span)


def _risk_multiplier(my_money, opp_money):
    return RISK_MULT_BEHIND if opp_money > my_money else RISK_MULT_AHEAD


def _in_bonus_window(crop, age_days):
    cd = CROPS[crop]
    if cd["ongoing"]:
        return True  # ongoing crops just need watered+fertilized same day
    window_start = (cd["max_yield_day"] + 1) // 2
    return window_start <= age_days <= cd["max_yield_day"]


def _unit_position(farm, unit_idx):
    if unit_idx == 0:
        return farm["farmer"]
    hands = farm.get("hands", [])
    return hands[unit_idx - 1] if unit_idx - 1 < len(hands) else None


def _decide_tile_action(role, tile, inv, day, has_wheat, has_fert):
    """Return an action list for the tile the unit is standing on, or None if
    nothing to do (unit should advance to the next patrol tile)."""
    is_animal_role = role in ANIMALS
    is_crop_role = role in CROPS

    if tile is None:
        if is_animal_role:
            structure = ANIMALS[role]["structure"]
            return ["BUILD_COOP"] if structure == "COOP" else ["BUILD_PASTURE"]
        if is_crop_role:
            return ["PLANT", role]
        return None

    if not isinstance(tile, dict):
        return None  # "LOCKED" or unexpected

    kind = tile.get("kind")

    if kind in ("COOP", "PASTURE"):
        if "animal" not in tile:
            animal_needed = role if role in ANIMALS else None
            if animal_needed and inv.get(animal_needed, 0) > 0:
                return ["PLACE", animal_needed]
            return None
        if not tile.get("fed_today"):
            return ["FEED"] if has_wheat else None
        if not tile.get("cared_today"):
            return ["CARE"]
        if tile.get("fertilizer_available"):
            return ["COLLECT_FERTILIZER"]
        if tile.get("yield_units", 0) > 0:
            return ["HARVEST"]
        return None

    if kind == "WEED":
        return ["DIG"]

    if kind == "PLANT":
        crop = tile["crop"]
        cd = CROPS[crop]
        age = day - tile["planted_day"]
        if not tile.get("watered_today"):
            return ["WATER"]
        if has_fert and tile.get("fertilized_until_day", -1) < day and _in_bonus_window(crop, age):
            return ["FERTILIZE"]
        if tile.get("yield_units", 0) > 0 and age >= cd["first_yield_day"]:
            return ["HARVEST"]
        return None

    return None


def _maybe_start_errand(unit_idx, role, tile, inv, private, target, day):
    """Called when there's nothing left to do at the current tile. Returns
    True if a fetch errand was started (caller should re-decide this turn).

    Everything here is a "go get X, come back, use it" trip sized and started
    at the moment of actual need -- not guessed at dawn. A dawn-guess bulk
    pickup was tried first and failed badly: at hour 0 the farmer is
    momentarily the only unit that exists, so its zone briefly balloons to
    the whole board, it requests (and drains) the entire day's shed stock for
    a zone it won't have a minute later, and every other hand starts its own
    day locked out of wheat/fertilizer with a one-shot task that never
    retries. Sizing and firing the fetch right at the tile that needs it
    avoids that failure mode entirely and is self-correcting if the shed is
    short (each unit just requests what its own now-stable zone needs).
    """
    shed = private["shed"]
    if role in ANIMALS and isinstance(tile, dict) and tile.get("kind") in ("COOP", "PASTURE") and "animal" not in tile:
        if inv.get(role, 0) <= 0 and shed.get(role, 0) > 0:
            S["errand"][unit_idx] = {"target": target, "item": role, "qty": 1, "mode": "place_animal"}
            return True
        return False
    if role in ANIMALS and isinstance(tile, dict) and "animal" in tile and not tile.get("fed_today"):
        if inv.get("WHEAT", 0) <= 0 and shed.get("WHEAT", 0) > 0:
            qty = min(max(1, _zone_daily_wheat(unit_idx)), 20)
            S["errand"][unit_idx] = {"target": target, "item": "WHEAT", "qty": qty, "mode": "use_in_place"}
            return True
        return False
    if role in CROPS and isinstance(tile, dict) and tile.get("kind") == "PLANT":
        crop = tile["crop"]
        age = day - tile["planted_day"]
        if (inv.get("FERTILIZER", 0) <= 0 and shed.get("FERTILIZER", 0) > 0
                and tile.get("fertilized_until_day", -1) < day and _in_bonus_window(crop, age)):
            qty = min(max(1, _zone_daily_fert(unit_idx)), 20)
            S["errand"][unit_idx] = {"target": target, "item": "FERTILIZER", "qty": qty, "mode": "use_in_place"}
            return True
    return False


def _move_toward(x, y, target):
    tx, ty = target
    if x < tx:
        return ["EAST"]
    if x > tx:
        return ["WEST"]
    if y < ty:
        return ["SOUTH"]
    if y > ty:
        return ["NORTH"]
    return ["PASS"]


def _move_toward_shed(x, y, board_size):
    tiles = _shed_access_tiles(board_size)
    target = min(tiles, key=lambda t: abs(t[0] - x) + abs(t[1] - y))
    return _move_toward(x, y, target)


def _unit_turn(unit_idx, farm, private, day, board_size):
    pos = _unit_position(farm, unit_idx)
    if pos is None:
        return ["PASS"]
    x, y = pos
    inv = private["inventories"][unit_idx] if unit_idx < len(private["inventories"]) else {}

    if S["last_day_for_unit"].get(unit_idx) != day:
        S["last_day_for_unit"][unit_idx] = day
        # Everything in inventory gets wiped to the shed at end of day
        # regardless, so an in-progress errand has nothing to resume.
        S["errand"].pop(unit_idx, None)

    # An active errand (fetch something from the shed, bring it back to a
    # specific tile) takes priority over everything else -- an item picked up
    # without following through is wasted for the day.
    errand = S["errand"].get(unit_idx)
    if errand is not None:
        item, target = errand["item"], errand["target"]
        if inv.get(item, 0) <= 0:
            if _is_shed_adjacent((x, y), board_size):
                shed = private["shed"]
                avail = shed.get(item, 0)
                if avail <= 0:
                    S["errand"].pop(unit_idx, None)  # no longer available; abandon, fall through
                else:
                    return ["PICKUP", item, min(avail, errand.get("qty", 1))]
            else:
                return _move_toward_shed(x, y, board_size)
        elif (x, y) != target:
            return _move_toward(x, y, target)
        elif errand["mode"] == "place_animal":
            tx, ty = target
            tile = farm["tiles"][ty][tx]
            S["errand"].pop(unit_idx, None)
            if isinstance(tile, dict) and tile.get("kind") in ("COOP", "PASTURE") and "animal" not in tile:
                return ["PLACE", item]
            return ["PASS"]  # someone else filled it; reassess next call
        else:
            # Arrived with the item in hand (e.g. wheat/fertilizer) -- clear
            # the errand and fall through to the normal per-tile decision
            # below, which will now see it in inventory.
            S["errand"].pop(unit_idx, None)

    zone = S["zones"].get(unit_idx, [])
    if not zone:
        return ["PASS"]
    ptr = S["ptr"].get(unit_idx, 0) % len(zone)
    target = zone[ptr]

    if (x, y) != target:
        return _move_toward(x, y, target)

    role = S["role"].get(target)
    tile = farm["tiles"][y][x]
    has_wheat = inv.get("WHEAT", 0) > 0
    has_fert = inv.get("FERTILIZER", 0) > 0
    action = _decide_tile_action(role, tile, inv, day, has_wheat, has_fert)
    if action is not None:
        return action

    if _maybe_start_errand(unit_idx, role, tile, inv, private, target, day):
        return _unit_turn(unit_idx, farm, private, day, board_size)

    S["ptr"][unit_idx] = (ptr + 1) % len(zone)
    return ["PASS"]


def _plan_market_orders(farm, private, day, prices, opp_farm=None, shops=()):
    orders = []
    money = farm["money"]
    opp_money = opp_farm["money"] if opp_farm is not None else money
    _update_opponent_history(opp_farm, day)
    shed = private["shed"]
    seeds = private["seeds"]
    shed_used = sum(shed.values())

    # 1. Feed the animals we already have, FIRST, above every discretionary
    # purchase. Buying a new cow is worthless if the ones we already placed
    # starve for lack of budget left over -- survival outranks growth. Uses a
    # smaller reserve floor than discretionary spending below, since this is
    # not optional.
    survival_reserve = SPEND_RESERVE * SURVIVAL_RESERVE_FRACTION
    daily_wheat_need = _placed_animal_count(farm)
    if daily_wheat_need > 0 and len(orders) < MAX_MARKET_ORDERS:
        # int(): order quantities must be whole numbers or the engine drops them.
        target_stock = int(daily_wheat_need * WHEAT_FEED_BUFFER_MULT)  # buffer: several units draw from one shed pool
        have_wheat = int(shed.get("WHEAT", 0))
        if have_wheat < target_stock:
            shortfall = target_stock - have_wheat
            cur = prices.get("WHEAT", 25)
            max_afford = max(0, int((money - survival_reserve) // max(cur, 1)))
            buy_n = int(min(shortfall, max_afford, 50))
            if buy_n > 0:
                orders.append(["BUY_PRODUCT", "WHEAT", buy_n])
                money -= buy_n * cur  # approximation; true cost rises slightly as it fills

    # 2. Hire hands up to a workload-scaled target, never dipping below the cash buffer.
    n_hands = len(farm.get("hands", []))
    hires_today = farm.get("hires_today", 0)
    hired_this_turn = 0
    target_hands = _desired_hands()
    hire_budget = money * HIRE_BUDGET_FRACTION
    spent_hiring = 0.0
    while n_hands + hired_this_turn < target_hands and len(orders) < MAX_MARKET_ORDERS:
        cost = _hire_cost(hires_today + hired_this_turn)
        if money - cost < SPEND_RESERVE or spent_hiring + cost > hire_budget:
            break
        spent_hiring += cost
        orders.append(["HIRE"])
        money -= cost
        hired_this_turn += 1

    # 3. Buy animals for unfilled structure slots (throttled: cash reserve
    # first, a small per-turn cap second -- the reserve is what actually
    # prevents burning the whole bankroll before anything is producing).
    unfilled = {"COW": 0, "SHEEP": 0, "GOOSE": 0}
    for (x, y), role in S["role"].items():
        if role not in ANIMALS:
            continue
        tile = farm["tiles"][y][x]
        has_animal = isinstance(tile, dict) and "animal" in tile
        if not has_animal:
            unfilled[role] += 1
    for role, n in unfilled.items():
        if n <= 0 or len(orders) >= MAX_MARKET_ORDERS:
            continue
        cost = ANIMALS[role]["cost"]
        have = shed.get(role, 0)
        to_buy = max(0, min(n - have, ANIMAL_BUY_CAP_PER_TURN))
        for _ in range(to_buy):
            if money - cost < SPEND_RESERVE or shed_used >= 100 or len(orders) >= MAX_MARKET_ORDERS:
                break
            orders.append(["BUY_ANIMAL", role, 1])
            money -= cost
            shed_used += 1

    # 4. Buy seeds to keep the seed pool stocked for planned crop tiles.
    crop_role_counts = {}
    for role in S["role"].values():
        if role in CROPS:
            crop_role_counts[role] = crop_role_counts.get(role, 0) + 1
    for crop, n in crop_role_counts.items():
        target_stock = max(2, n // 6)
        have = seeds.get(crop, 0)
        if have >= target_stock or len(orders) >= MAX_MARKET_ORDERS:
            continue
        cost = CROPS[crop]["seed"]
        to_buy = target_stock - have
        buy_n = 0
        while buy_n < to_buy and money - cost >= SPEND_RESERVE:
            buy_n += 1
            money -= cost
        if buy_n > 0:
            orders.append(["BUY_SEED", crop, buy_n])

    # 5. Buy land only with a comfortable cushion left over, so it never
    # competes with funding the animals/crops that actually generate income.
    n_extra = len(farm.get("unlocked_quadrants", ["NW"])) - 1
    if n_extra < len(LAND_ORDER):
        land_price = LAND_PRICES[n_extra]
        if money >= land_price * LAND_BUY_CASH_MULTIPLE and len(orders) < MAX_MARKET_ORDERS:
            orders.append(["BUY_LAND"])
            money -= land_price

    # 6. Sell shed contents: unconditionally if shed is nearly full or the
    # season is basically over, else above a reserve price that is scaled by
    # three things layered on the base RESERVE_PRICE:
    #   - _ramp_fraction(day): decays to 0 by RAMP_END_DAY, so late-game
    #     naturally converges to "sell at any price" -- unsold shed inventory
    #     is worth nothing when the season ends.
    #   - _opponent_reserve_scale(...): sell more readily into an item the
    #     opponent is also heavily producing (their glut is coming regardless
    #     of what I do), hold out longer on items they aren't touching.
    #   - _risk_multiplier(...): behind on money -> sell more/faster (worth
    #     the risk); ahead -> hold out (protect the lead). Only the win/loss
    #     is rated, not the margin.
    # The WHEAT feed-buffer exemption also fades out with the same ramp --
    # by the literal last day there's no future production left to feed for.
    panic = shed_used >= SHED_PANIC_FRACTION * 100
    ramp = _ramp_fraction(day)
    risk_mult = _risk_multiplier(money, opp_money)
    # Only ever iterate over SELLABLE. The shed also holds live animals
    # (COW/SHEEP/GOOSE bought but not yet placed); those are NOT products.
    # Iterating the raw shed emitted ["SELL","COW",n] every turn, and the
    # engine treats a SELL of a non-product as a malformed sub-op and ABORTS
    # THE WHOLE ORDER SLOT -- which silently killed every milk/wool sale and
    # left the animal build with no income at all.
    for item in SELL_PRIORITY_ORDER:
        n = int(shed.get(item, 0))
        if n <= 0 or len(orders) >= MAX_MARKET_ORDERS:
            continue
        if item == "WHEAT" and not panic and ramp > 0:
            # int(): quantities must be whole numbers. WHEAT_FEED_BUFFER_MULT
            # is a searched float, so this subtraction produced fractional
            # quantities like 0.485, which the engine int()s to 0 and drops --
            # wasting an order slot and never actually selling the wheat.
            n -= int(daily_wheat_need * WHEAT_FEED_BUFFER_MULT)
            if n <= 0:
                continue
        reserve = (RESERVE_PRICE.get(item, 0) * ramp * risk_mult
                   * _opponent_reserve_scale(farm, opp_farm, item, day, shops))
        cur_price = prices.get(item, 0)
        if panic or cur_price >= reserve:
            orders.append(["SELL", item, n])

    return orders[:MAX_MARKET_ORDERS]


def agent(obs):
    obs = obs if isinstance(obs, dict) else dict(obs)
    player = obs.get("player", 0)
    farms = obs.get("farms", [])
    if not farms or player >= len(farms):
        return {"farmer": ["PASS"], "hands": [], "market": []}
    farm = farms[player]
    private = obs.get("private", {}) or {}
    day = obs.get("day", 0)
    hour = obs.get("hour", 0)
    board_size = len(farm["tiles"])

    if day == 0 and hour == 0:
        _reset_state()

    FARM_VIEW[0] = farm
    _assign_roles_for_new_land(farm, board_size)

    n_hands = len(farm.get("hands", []))
    n_units = 1 + n_hands
    _rebuild_zones(board_size, n_units)

    private_full = {
        "shed": private.get("shed", {}) or {},
        "seeds": private.get("seeds", {}) or {},
        "inventories": private.get("inventories", [{}]) or [{}],
    }

    farmer_action = _unit_turn(0, farm, private_full, day, board_size)
    hands_actions = [_unit_turn(i + 1, farm, private_full, day, board_size) for i in range(n_hands)]

    market_obj = obs.get("market", {}) or {}
    prices = market_obj.get("prices", {}) or {}
    opp_farm = farms[1 - player] if len(farms) > 1 else None
    town = obs.get("town", {}) or {}
    shops = tuple(town.get("unlocked_shops", []) or [])
    orders = _plan_market_orders(farm, private_full, day, prices, opp_farm, shops)

    return {"farmer": farmer_action, "hands": hands_actions, "market": orders}
