from collections import deque
import math

CROP_RULES = {
    "WHEAT": {"seed": 10, "first": 2, "max_day": 4, "interval": 0, "max_yield": 6, "ongoing": False, "last_plant": 24, "delay": 4, "expected": 4.0},
    "CARROT": {"seed": 20, "first": 2, "max_day": 3, "interval": 0, "max_yield": 4, "ongoing": False, "last_plant": 25, "delay": 3, "expected": 3.0},
    "TOMATO": {"seed": 50, "first": 8, "max_day": 8, "interval": 1, "max_yield": 4, "ongoing": True, "last_plant": 19, "delay": 12, "expected": 4.0},
    "STRAWBERRY": {"seed": 100, "first": 10, "max_day": 10, "interval": 2, "max_yield": 4, "ongoing": True, "last_plant": 12, "delay": 16, "expected": 4.0},
    "MELON": {"seed": 80, "first": 10, "max_day": 12, "interval": 0, "max_yield": 6, "ongoing": False, "last_plant": 16, "delay": 12, "expected": 5.0},
}

ANIMAL_RULES = {
    "GOOSE": {"cost": 300, "structure": "COOP", "product": "EGG", "first": 4, "interval": 1, "max_held": 4, "harvest_at": 4},
    "COW": {"cost": 400, "structure": "PASTURE", "product": "MILK", "first": 8, "interval": 2, "max_held": 6, "harvest_at": 5},
    "SHEEP": {"cost": 500, "structure": "PASTURE", "product": "WOOL", "first": 6, "interval": 3, "max_held": 6, "harvest_at": 5},
}

PRODUCTS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER")
CROPS = tuple(CROP_RULES)
ANIMALS = tuple(ANIMAL_RULES)
LAND_PRICES = (1000, 2000, 4000)

DEFAULT_MARKET = {
    "WHEAT": {"base": 25, "I0": 10000, "T": 400, "below_func": "sqrt", "below_target": 0.80, "above_func": "log", "above_target": 0.20},
    "CARROT": {"base": 35, "I0": 10000, "T": 450, "below_func": "log", "below_target": 0.20, "above_func": "sqrt", "above_target": 0.70},
    "TOMATO": {"base": 60, "I0": 10000, "T": 200, "below_func": "linear", "below_target": 0.40, "above_func": "sqrt", "above_target": 0.60},
    "STRAWBERRY": {"base": 120, "I0": 10000, "T": 100, "below_func": "sqrt", "below_target": 0.70, "above_func": "linear", "above_target": 1.60},
    "MELON": {"base": 250, "I0": 10000, "T": 300, "below_func": "log", "below_target": 0.20, "above_func": "sq", "above_target": 3.60},
    "EGG": {"base": 50, "I0": 10000, "T": 332, "below_func": "linear", "below_target": 0.40, "above_func": "log", "above_target": 0.20},
    "MILK": {"base": 160, "I0": 10000, "T": 122, "below_func": "sqrt", "below_target": 0.60, "above_func": "linear", "above_target": 1.60},
    "WOOL": {"base": 200, "I0": 10000, "T": 105, "below_func": "log", "below_target": 0.20, "above_func": "sq", "above_target": 3.20},
    "FERTILIZER": {"base": 100, "I0": 10000, "T": 200, "below_func": "linear", "below_target": 0.40, "above_func": "linear", "above_target": 0.40},
}

SHOPS = {
    "BAKERY": ("EGG", "WHEAT"),
    "PIZZA_SHOP": ("MILK", "TOMATO", "WHEAT"),
    "BRUNCH_SPOT": ("EGG", "WHEAT", "STRAWBERRY"),
    "YARN_STORE": ("WOOL",),
    "ICE_CREAM_SHOP": ("STRAWBERRY", "MILK", "WHEAT"),
    "PET_CAFE": ("CARROT",),
    "SMOOTHIE_SHOP": ("STRAWBERRY", "MILK"),
    "FARMERS_MARKET": ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY"),
}

SELL_FLOORS = {
    "WHEAT": 14, "CARROT": 16, "TOMATO": 24, "STRAWBERRY": 42,
    "MELON": 55, "EGG": 20, "MILK": 48, "WOOL": 55,
    "FERTILIZER": 12,
}


def _shape(name, value):
    value = max(0.0, float(value))
    if name == "linear":
        return value
    if name == "sq":
        return value * value
    if name == "sqrt":
        return math.sqrt(value)
    if name == "log":
        return math.log1p(value)
    if name == "log10":
        return math.log10(1.0 + value)
    return value


def _market_params(obs, item):
    custom = (obs.get("market", {}) or {}).get("params", {}) or {}
    if item in custom:
        merged = dict(DEFAULT_MARKET[item])
        merged.update(custom[item])
        return merged
    return DEFAULT_MARKET[item]


def _price_at(obs, item, inventory):
    p = _market_params(obs, item)
    base = float(p["base"])
    i0 = float(p["I0"])
    throughput = max(1.0, float(p["T"]))
    if inventory < i0:
        fn = p["below_func"]
        amp = float(p["below_target"]) * base / max(1e-9, _shape(fn, throughput))
        price = base + amp * _shape(fn, i0 - inventory)
    else:
        fn = p["above_func"]
        amp = float(p["above_target"]) * base / max(1e-9, _shape(fn, throughput))
        price = base - amp * _shape(fn, inventory - i0)
    return max(1, int(round(price)))


def _placed_animal_counts(farm):
    counts = {animal: 0 for animal in ANIMALS}
    for row in farm.get("tiles", []) or []:
        for tile in row:
            if isinstance(tile, dict) and tile.get("animal") in counts:
                counts[tile["animal"]] += 1
    return counts



def _desired_animals(obs, farm):
    day = int(obs.get("day", 0))
    unlocked = len(farm.get("unlocked_quadrants", []) or [])
    existing = _placed_animal_counts(farm)
    if day > 21:
        cow_target = existing["COW"]
        goose_target = existing["GOOSE"]
    elif unlocked >= 2:
        cow_target = 9
        goose_target = 0
    else:
        cow_target = min(9, 3)
        goose_target = min(0, 0)
    return {
        "GOOSE": max(existing["GOOSE"], goose_target),
        "COW": max(existing["COW"], cow_target),
        "SHEEP": existing["SHEEP"],
    }


def _animal_plan(obs, farm):
    desired = _desired_animals(obs, farm)
    plan = {}
    used = set()
    tiles = farm.get("tiles", []) or []
    n = len(tiles)
    h = n // 2

    for y, row in enumerate(tiles):
        for x, tile in enumerate(row):
            if isinstance(tile, dict) and tile.get("animal") in ANIMAL_RULES:
                plan[(x, y)] = tile["animal"]
                used.add((x, y))

    candidates = []
    for y, row in enumerate(tiles):
        for x, tile in enumerate(row):
            if tile == "LOCKED" or (x, y) in used:
                continue
            distance = min(
                abs(x - (h - 1)) + abs(y - (h - 1)),
                abs(x - h) + abs(y - (h - 1)),
                abs(x - (h - 1)) + abs(y - h),
                abs(x - h) + abs(y - h),
            )
            empty_bonus = 0 if tile is None else 1 if isinstance(tile, dict) and tile.get("kind") in ("PASTURE", "COOP") else 4
            ne_bonus = 0 if (x >= h and y < h) else 1
            candidates.append((empty_bonus, ne_bonus, distance, y, x))
    candidates.sort()

    current = {animal: sum(1 for a in plan.values() if a == animal) for animal in ANIMALS}
    for animal in ("COW", "GOOSE", "SHEEP"):
        need = max(0, desired.get(animal, 0) - current.get(animal, 0))
        matching = []
        other = []
        structure = ANIMAL_RULES[animal]["structure"]
        for item in candidates:
            _, _, _, y, x = item
            if (x, y) in used:
                continue
            tile = tiles[y][x]
            if isinstance(tile, dict) and tile.get("kind") == structure and "animal" not in tile:
                matching.append(item)
            else:
                other.append(item)
        ordered = matching + other
        for item in ordered[:need]:
            _, _, _, y, x = item
            plan[(x, y)] = animal
            used.add((x, y))
    return plan

def _shed_tiles(farm):
    n = len(farm["tiles"])
    h = n // 2
    cells = ((h - 1, h - 1), (h, h - 1), (h - 1, h), (h, h))
    return [p for p in cells if farm["tiles"][p[1]][p[0]] != "LOCKED"]


def _is_shed_tile(farm, pos):
    return tuple(pos) in set(_shed_tiles(farm))


def _distance(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _next_step(farm, source, target):
    source = tuple(source)
    target = tuple(target)
    if source == target:
        return ["PASS"]
    n = len(farm["tiles"])
    preferred = []
    if target[0] > source[0]:
        preferred.append((1, 0, "EAST"))
    if target[0] < source[0]:
        preferred.append((-1, 0, "WEST"))
    if target[1] > source[1]:
        preferred.append((0, 1, "SOUTH"))
    if target[1] < source[1]:
        preferred.append((0, -1, "NORTH"))
    for move in ((1, 0, "EAST"), (-1, 0, "WEST"), (0, 1, "SOUTH"), (0, -1, "NORTH")):
        if move not in preferred:
            preferred.append(move)
    queue = deque([source])
    parent = {source: None}
    parent_move = {}
    while queue:
        cur = queue.popleft()
        if cur == target:
            break
        for dx, dy, name in preferred:
            nxt = (cur[0] + dx, cur[1] + dy)
            if not (0 <= nxt[0] < n and 0 <= nxt[1] < n):
                continue
            if farm["tiles"][nxt[1]][nxt[0]] == "LOCKED" or nxt in parent:
                continue
            parent[nxt] = cur
            parent_move[nxt] = name
            queue.append(nxt)
    if target not in parent:
        return ["PASS"]
    cur = target
    while parent[cur] != source:
        cur = parent[cur]
        if cur is None:
            return ["PASS"]
    return [parent_move[cur]]


def _nearest_shed(farm, pos):
    cells = _shed_tiles(farm)
    if not cells:
        return tuple(pos)
    return min(cells, key=lambda p: (_distance(pos, p), p[1], p[0]))


def _inventories(private):
    invs = private.get("inventories", []) or []
    return [dict(inv or {}) for inv in invs]


def _stock(private, item):
    total = int((private.get("shed", {}) or {}).get(item, 0))
    for inv in private.get("inventories", []) or []:
        total += int((inv or {}).get(item, 0))
    return total


def _actual_animals(farm):
    out = []
    for row in farm["tiles"]:
        for tile in row:
            if isinstance(tile, dict) and tile.get("animal") in ANIMAL_RULES:
                out.append(tile["animal"])
    return out


def _visible_count(obs, item):
    count = 0
    product_to_animal = {"EGG": "GOOSE", "MILK": "COW", "WOOL": "SHEEP"}
    for farm in obs.get("farms", []) or []:
        for row in farm.get("tiles", []) or []:
            for tile in row:
                if not isinstance(tile, dict):
                    continue
                if item in CROP_RULES and tile.get("kind") == "PLANT" and tile.get("crop") == item:
                    count += 1
                elif item in product_to_animal and tile.get("animal") == product_to_animal[item]:
                    count += 1
    return count


def _demand_per_day(obs, item):
    day = int(obs.get("day", 0))
    demand = 2 * (4 if day >= 20 else 2 if day >= 10 else 1)
    for shop in (obs.get("town", {}) or {}).get("unlocked_shops", []) or []:
        products = SHOPS.get(shop, ())
        if item in products:
            demand += 12 if len(products) == 1 else 6
    return demand


def _future_visible_supply(obs, item, horizon):
    day = int(obs.get("day", 0))
    horizon = max(0, int(horizon))
    total = 0.0
    product_to_animal = {"EGG": "GOOSE", "MILK": "COW", "WOOL": "SHEEP"}
    for farm in obs.get("farms", []) or []:
        for row in farm.get("tiles", []) or []:
            for tile in row:
                if not isinstance(tile, dict):
                    continue
                if item in CROP_RULES and tile.get("kind") == "PLANT" and tile.get("crop") == item:
                    rule = CROP_RULES[item]
                    held = float(tile.get("yield_units", 0))
                    planted = int(tile.get("planted_day", day))
                    age = day - planted
                    if rule["ongoing"]:
                        total += held
                        for offset in range(1, horizon + 1):
                            next_day = day + offset
                            since = next_day - planted - rule["first"]
                            if since < 0 or since % rule["interval"] != 0:
                                continue
                            production_count = since // rule["interval"] + 1
                            if production_count <= rule["max_yield"]:
                                fertilized = int(tile.get("fertilized_until_day", -1)) >= next_day - 1
                                total += 1.5 if fertilized else 1.0
                    elif rule["max_day"] - age <= horizon:
                        remaining_days = max(0, rule["max_day"] - age + 1)
                        estimated = min(rule["max_yield"], held + remaining_days)
                        total += max(held, estimated)
                elif item in product_to_animal and tile.get("animal") == product_to_animal[item]:
                    animal = tile["animal"]
                    rule = ANIMAL_RULES[animal]
                    total += float(tile.get("yield_units", 0))
                    placed = int(tile.get("placed_day", day))
                    for offset in range(1, horizon + 1):
                        next_day = day + offset
                        since = next_day - placed - rule["first"]
                        if since >= 0 and since % rule["interval"] == 0:
                            total += 2.0
    return total


def _project_inventory(obs, item, horizon, extra_supply=0.0):
    market = obs.get("market", {}) or {}
    inventory = float((market.get("inventory", {}) or {}).get(item, 10000))
    demand = float(_demand_per_day(obs, item) * max(0, int(horizon)))
    supply = _future_visible_supply(obs, item, horizon)
    return inventory + supply + float(extra_supply) - demand

def _crop_score(obs, crop, animal_count):
    day = int(obs.get("day", 0))
    rule = CROP_RULES[crop]
    if day > rule["last_plant"]:
        return -1e9
    horizon = rule["delay"]
    expected_yield = float(rule["expected"])
    projected = _project_inventory(obs, crop, horizon, expected_yield)
    future_price = _price_at(obs, crop, projected)
    current_price = int((((obs.get("market", {}) or {}).get("prices", {}) or {}).get(crop, DEFAULT_MARKET[crop]["base"])))
    expected_price = 0.72 * future_price + 0.28 * current_price
    profit = expected_yield * expected_price - rule["seed"]
    score = profit / max(1.0, horizon)
    if crop == "WHEAT" and animal_count:
        score += min(24.0, animal_count * 4.5)
    if crop == "CARROT":
        score += 4.0
    return score

def _bounded_shares(raw, floors, caps):
    keys = list(raw)
    active = set(keys)
    result = {}
    remaining = 1.0
    for _ in range(len(keys) + 2):
        if not active:
            break
        denom = sum(max(1e-12, raw[k]) for k in active)
        changed = False
        proposed = {k: remaining * max(1e-12, raw[k]) / denom for k in active}
        for k in list(active):
            if proposed[k] < floors.get(k, 0.0) - 1e-12:
                result[k] = floors.get(k, 0.0)
                remaining -= result[k]
                active.remove(k)
                changed = True
            elif proposed[k] > caps.get(k, 1.0) + 1e-12:
                result[k] = caps.get(k, 1.0)
                remaining -= result[k]
                active.remove(k)
                changed = True
        if not changed:
            for k in active:
                result[k] = proposed[k]
            active.clear()
            break
    if active:
        each = max(0.0, remaining) / len(active)
        for k in active:
            result[k] = each
    total = sum(result.values())
    if total <= 0:
        return {"WHEAT": 1.0}
    return {k: max(0.0, v) / total for k, v in result.items()}


def _crop_weights(obs, animal_count):
    day = int(obs.get("day", 0))
    available = [crop for crop in CROPS if day <= CROP_RULES[crop]["last_plant"]]
    if not available:
        return {"WHEAT": 1.0}

    safe = {'WHEAT': 0.35, 'CARROT': 0.15, 'TOMATO': 0.3, 'STRAWBERRY': 0.1, 'MELON': 0.1}
    scores = {crop: max(0.0, _crop_score(obs, crop, animal_count)) for crop in available}
    score_sum = sum(scores.values()) or 1.0
    raw = {crop: 0.62 * safe[crop] + 0.38 * scores[crop] / score_sum for crop in available}

    shops = set((obs.get("town", {}) or {}).get("unlocked_shops", []) or [])
    if "PET_CAFE" in shops and "CARROT" in raw:
        raw["CARROT"] *= 1.30
    if shops.intersection({"PIZZA_SHOP", "FARMERS_MARKET"}) and "TOMATO" in raw:
        raw["TOMATO"] *= 1.22
    if shops.intersection({"BRUNCH_SPOT", "ICE_CREAM_SHOP", "SMOOTHIE_SHOP"}) and "STRAWBERRY" in raw:
        raw["STRAWBERRY"] *= 1.18

    market_prices = ((obs.get("market", {}) or {}).get("prices", {}) or {})
    visible_melon = _visible_count(obs, "MELON")
    melon_cap = 0.10 if visible_melon >= 12 else 0.14
    if int(market_prices.get("MELON", 250)) >= 300 and visible_melon <= 6:
        melon_cap = 0.18
    strawberry_cap = 0.07 if _visible_count(obs, "STRAWBERRY") >= 12 else 0.10

    floors = {crop: 0.0 for crop in available}
    caps = {crop: 1.0 for crop in available}
    if "WHEAT" in floors:
        floors["WHEAT"] = 0.3 if animal_count else 0.20
    if "CARROT" in floors:
        floors["CARROT"] = 0.12
    if "TOMATO" in floors:
        floors["TOMATO"] = 0.25
    if "MELON" in caps:
        caps["MELON"] = melon_cap
    if "STRAWBERRY" in caps:
        caps["STRAWBERRY"] = strawberry_cap
    return _bounded_shares(raw, floors, caps)

def _cell_noise(x, y, salt=0):
    value = (((x + 11 + salt) * 73856093) ^ ((y + 17 + salt) * 19349663) ^ (salt * 83492791)) % 1000003
    return value / 1000003.0


def _crop_assignment(obs, farm, animal_plan):
    animal_count = len(_actual_animals(farm))
    shares = _crop_weights(obs, animal_count)
    cells = []
    for y, row in enumerate(farm["tiles"]):
        for x, tile in enumerate(row):
            if tile == "LOCKED" or (x, y) in animal_plan:
                continue
            cells.append((x, y))
    if not cells:
        return {}

    exact = {crop: shares.get(crop, 0.0) * len(cells) for crop in CROPS if crop in shares}
    counts = {crop: int(exact[crop]) for crop in exact}
    left = len(cells) - sum(counts.values())
    tie_priority = {"TOMATO": 5, "WHEAT": 4, "MELON": 3, "STRAWBERRY": 2, "CARROT": 1}
    ranked_leftovers = sorted(
        exact,
        key=lambda c: (
            round(exact[c] - counts[c], 10),
            tie_priority.get(c, 0),
            _crop_score(obs, c, animal_count),
        ),
        reverse=True,
    )
    for crop in ranked_leftovers[:left]:
        counts[crop] += 1

    available = set(cells)
    plan = {}
    crop_order = [crop for crop in ("MELON", "STRAWBERRY", "TOMATO", "WHEAT", "CARROT") if crop in counts]
    for crop in crop_order:
        ranked = []
        for x, y in available:
            tile = farm["tiles"][y][x]
            dist = _distance((x, y), _nearest_shed(farm, (x, y)))
            existing_bonus = 1000.0 if isinstance(tile, dict) and tile.get("kind") == "PLANT" and tile.get("crop") == crop else 0.0
            if crop == "MELON":
                spatial = dist * 12.0
            elif crop == "STRAWBERRY":
                spatial = dist * 8.0
            elif crop == "TOMATO":
                spatial = -dist * 9.0
            elif crop == "WHEAT":
                spatial = -dist * 4.0
            else:
                spatial = -dist * 2.0
            ranked.append((existing_bonus + spatial + _cell_noise(x, y, len(crop)) * 5.0, x, y))
        ranked.sort(reverse=True)
        for _, x, y in ranked[:counts[crop]]:
            plan[(x, y)] = crop
            available.discard((x, y))
    fallback = "CARROT" if "CARROT" in shares else max(shares, key=shares.get)
    for pos in available:
        plan[pos] = fallback
    return plan

def _add_task(tasks, priority, pos, action, need=None):
    tasks.append({"priority": int(priority), "pos": tuple(pos), "action": list(action), "need": need})


def _ongoing_production_on(tile, rule, current_day):
    next_day = current_day + 1
    planted = int(tile.get("planted_day", current_day))
    since = next_day - planted - rule["first"]
    if since < 0 or since % rule["interval"] != 0:
        return False
    return since // rule["interval"] + 1 <= rule["max_yield"]



def _fertilizer_value(obs, tile):
    if not isinstance(tile, dict) or tile.get("kind") != "PLANT":
        return 0.0
    crop = tile.get("crop")
    rule = CROP_RULES.get(crop)
    if rule is None or not rule["ongoing"]:
        return 0.0
    day = int(obs.get("day", 0))
    if day >= 27 or int(tile.get("fertilized_until_day", -1)) >= day:
        return 0.0
    planted = int(tile.get("planted_day", day))
    ticks = 0
    for offset in (1, 2, 3):
        next_day = day + offset
        since = next_day - planted - rule["first"]
        if since < 0 or since % rule["interval"] != 0:
            continue
        production_count = since // rule["interval"] + 1
        if production_count <= rule["max_yield"]:
            ticks += 1
    if ticks <= 0:
        return 0.0
    market = obs.get("market", {}) or {}
    inv = int((market.get("inventory", {}) or {}).get(crop, 10000))
    crop_price = _price_at(obs, crop, inv + ticks)
    fert_price = int((market.get("prices", {}) or {}).get("FERTILIZER", 100))
    value = ticks * crop_price - fert_price
    return value if value >= 10 else 0.0

def _build_tasks(obs, farm, private):
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    final_day = day >= 29
    pre_final = day == 28
    tasks = []
    animal_plan = _animal_plan(obs, farm)
    crop_plan = _crop_assignment(obs, farm, animal_plan)
    fertilizer_stock = _stock(private, "FERTILIZER")
    fertilizer_price = int((((obs.get("market", {}) or {}).get("prices", {}) or {}).get("FERTILIZER", 100)))
    plant_records = []
    fertilizer_candidates = []

    for y, row in enumerate(farm["tiles"]):
        for x, tile in enumerate(row):
            if tile == "LOCKED":
                continue
            pos = (x, y)
            planned_animal = animal_plan.get(pos)

            if isinstance(tile, dict) and tile.get("animal") in ANIMAL_RULES:
                animal = tile["animal"]
                risk = int(tile.get("consecutive_unfed", 0)) >= 1
                milk_price = int((((obs.get("market", {}) or {}).get("prices", {}) or {}).get("MILK", 160)))
                milk_care_floor = 65 if _cow_competition(obs) else 35
                boost = (animal == "COW" and day <= 27 and milk_price >= milk_care_floor)
                if not final_day and not tile.get("fed_today", False) and (risk or boost):
                    _add_task(tasks, 0 if risk else 2, pos, ["FEED"], "WHEAT")
                if not final_day and boost and not tile.get("cared_today", False):
                    _add_task(tasks, 2, pos, ["CARE"])
                if tile.get("fertilizer_available", False) and (fertilizer_price >= 20 or fertilizer_stock < 6 or final_day):
                    _add_task(tasks, 1 if not final_day else 0, pos, ["COLLECT_FERTILIZER"])
                held = int(tile.get("yield_units", 0))
                threshold = 4 if animal == "COW" else 3
                if held >= threshold or ((pre_final or final_day) and held > 0):
                    _add_task(tasks, 1 if not final_day else 0, pos, ["HARVEST"])
                continue

            if planned_animal is not None and not final_day:
                structure = ANIMAL_RULES[planned_animal]["structure"]
                if tile is None:
                    _add_task(tasks, 2, pos, ["BUILD_" + structure])
                    continue
                if isinstance(tile, dict) and tile.get("kind") == "WEED":
                    _add_task(tasks, 7, pos, ["DIG"])
                    continue
                if isinstance(tile, dict) and tile.get("kind") == structure and "animal" not in tile:
                    if _stock(private, planned_animal) > 0:
                        _add_task(tasks, 1, pos, ["PLACE", planned_animal], planned_animal)
                    continue

            if isinstance(tile, dict) and tile.get("kind") == "PLANT":
                plant_records.append((pos, tile))
                risk = int(tile.get("consecutive_unwatered", 0)) >= 1
                gain = _fertilizer_value(obs, tile)
                if gain > 0 and not risk and hour <= 17 and not pre_final and not final_day:
                    fertilizer_candidates.append((gain, pos))
                continue

            if isinstance(tile, dict) and tile.get("kind") == "WEED":
                if not final_day and hour <= 20:
                    _add_task(tasks, 8, pos, ["DIG"])
                continue

            if tile is None and planned_animal is None and not pre_final and not final_day and hour <= 16:
                crop = crop_plan.get(pos, "CARROT")
                if day <= CROP_RULES[crop]["last_plant"] and int((private.get("seeds", {}) or {}).get(crop, 0)) > 0:
                    _add_task(tasks, 11, pos, ["PLANT", crop])

    selected_fertilizer = set(pos for _, pos in sorted(fertilizer_candidates, reverse=True)[:fertilizer_stock])
    for pos, tile in plant_records:
        crop = tile.get("crop")
        rule = CROP_RULES.get(crop)
        if rule is None:
            continue
        age = day - int(tile.get("planted_day", day))
        held = int(tile.get("yield_units", 0))

        if final_day:
            if held > 0 and age >= rule["first"]:
                _add_task(tasks, 0, pos, ["HARVEST"])
            continue

        if pos in selected_fertilizer:
            _add_task(tasks, 1, pos, ["FERTILIZE"], "FERTILIZER")
            continue

        if not tile.get("watered_today", False):
            risk = int(tile.get("consecutive_unwatered", 0)) >= 1
            _add_task(tasks, 0 if risk or hour >= 18 else 5, pos, ["WATER"])
            continue

        if not rule["ongoing"]:
            if held >= rule["max_yield"] or (age >= rule["max_day"] and held > 0) or (pre_final and held > 0 and age >= rule["first"]):
                _add_task(tasks, 2 if pre_final else 4, pos, ["HARVEST"])
        else:
            threshold = 2 if pre_final else max(2, rule["max_yield"] - 1)
            if held >= threshold or (day >= 27 and held > 0):
                _add_task(tasks, 3, pos, ["HARVEST"])

    return tasks

def _resource_route_cost(farm, pos, task, inv, shed):
    need = task["need"]
    target = task["pos"]
    if need is None or int(inv.get(need, 0)) > 0:
        bonus = -50 if need is not None and int(inv.get(need, 0)) > 0 else 0
        return _distance(pos, target) + bonus
    if int(shed.get(need, 0)) <= 0:
        return 5000 + _distance(pos, target)
    shed_pos = _nearest_shed(farm, pos)
    return _distance(pos, shed_pos) + 1 + _distance(shed_pos, target)


def _task_action(farm, pos, inv, shed, task):
    need = task["need"]
    if need is not None and int(inv.get(need, 0)) <= 0:
        if int(shed.get(need, 0)) <= 0:
            return ["PASS"]
        shed_pos = _nearest_shed(farm, pos)
        if tuple(pos) == tuple(shed_pos):
            amount = 1 if need in ANIMAL_RULES else 2 if need == "FERTILIZER" else 4
            return ["PICKUP", need, min(amount, int(shed.get(need, 0)))]
        return _next_step(farm, pos, shed_pos)
    if tuple(pos) == task["pos"]:
        return list(task["action"])
    return _next_step(farm, pos, task["pos"])


def _unit_actions(obs, farm, private):
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    positions = [tuple(farm.get("farmer", [0, 0]))] + [tuple(p) for p in farm.get("hands", [])]
    invs = _inventories(private)
    while len(invs) < len(positions):
        invs.append({})
    shed = dict(private.get("shed", {}) or {})
    actions = [None] * len(positions)
    available_units = []

    carried_total = sum(sum(int(v) for v in inv.values()) for inv in invs)
    storage_pressure = sum(int(v) for v in shed.values()) + carried_total
    for idx, pos in enumerate(positions):
        carried = sum(int(v) for v in invs[idx].values())
        shed_pos = _nearest_shed(farm, pos)
        return_distance = _distance(pos, shed_pos)
        final_deadline = day >= 29 and (hour >= 14 or hour + return_distance + 1 >= 22)
        prefinal_deadline = day == 28 and hour >= 20
        should_unload = carried > 0 and (final_deadline or prefinal_deadline or storage_pressure >= 82 or carried >= 10)
        if should_unload:
            actions[idx] = ["DROP"] if tuple(pos) == tuple(shed_pos) else _next_step(farm, pos, shed_pos)
        elif day >= 29 and hour >= 20:
            actions[idx] = ["PASS"] if tuple(pos) == tuple(shed_pos) else _next_step(farm, pos, shed_pos)
        else:
            available_units.append(idx)

    tasks = _build_tasks(obs, farm, private)
    unused_tasks = set(range(len(tasks)))
    unassigned = set(available_units)

    while unassigned and unused_tasks:
        best = None
        for unit_idx in unassigned:
            pos = positions[unit_idx]
            inv = invs[unit_idx]
            for task_idx in unused_tasks:
                task = tasks[task_idx]
                if day >= 29 and task["action"][0] == "HARVEST":
                    target = task["pos"]
                    cashout_steps = _distance(pos, target) + 1 + _distance(target, _nearest_shed(farm, target)) + 1
                    if hour + cashout_steps > 22:
                        continue
                route = _resource_route_cost(farm, pos, task, inv, shed)
                key = (task["priority"] * 100000 + route * 100, route, task["pos"][1], task["pos"][0], unit_idx, task_idx)
                if best is None or key < best[0]:
                    best = (key, unit_idx, task_idx)
        if best is None:
            break
        _, unit_idx, task_idx = best
        task = tasks[task_idx]
        actions[unit_idx] = _task_action(farm, positions[unit_idx], invs[unit_idx], shed, task)
        unassigned.remove(unit_idx)
        unused_tasks.remove(task_idx)

    for idx in range(len(actions)):
        if actions[idx] is None:
            actions[idx] = ["PASS"]

    remaining = dict(private.get("seeds", {}) or {})
    for idx, action in enumerate(actions):
        if len(action) >= 2 and action[0] == "PLANT":
            crop = action[1]
            if int(remaining.get(crop, 0)) <= 0:
                actions[idx] = ["PASS"]
            else:
                remaining[crop] = int(remaining.get(crop, 0)) - 1
    return actions

def _fib(n):
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a



def _target_hands(obs, farm):
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    if day >= 29:
        return 13 if hour < 12 else len(farm.get("hands", []))
    return 11 if len(farm.get("unlocked_quadrants", []) or []) >= 2 else max(9, 11-2)


def _land_order(obs, farm, budget):
    day = int(obs.get("day", 0))
    extra = len(farm.get("unlocked_quadrants", []) or []) - 1
    if extra != 0:
        return None
    if 4 <= day <= 10 and budget >= 1850:
        return 1000
    return None

def _sell_quantity(obs, item, quantity, pressure=0, force=False):
    quantity = int(quantity)
    if quantity <= 0:
        return 0
    if force:
        return quantity
    market = obs.get("market", {}) or {}
    inventory = int((market.get("inventory", {}) or {}).get(item, 10000))
    current_price = _price_at(obs, item, inventory)
    future_inventory = _project_inventory(obs, item, 1, 0.0)
    future_price = _price_at(obs, item, future_inventory)
    if pressure < 72 and current_price + 2 < future_price:
        return 0

    floor = SELL_FLOORS[item]
    if pressure >= 88:
        floor = max(1, int(floor * 0.55))
    elif pressure >= 78:
        floor = max(1, int(floor * 0.75))
    threshold = max(floor, int(future_price * (0.78 if pressure >= 78 else 0.90)))
    batch_cap = 24 if item in ("WHEAT", "CARROT", "TOMATO", "EGG") else 10
    if pressure >= 82:
        batch_cap *= 2
    sold = 0
    for i in range(min(quantity, batch_cap)):
        if _price_at(obs, item, inventory + i) < threshold:
            break
        sold += 1
    return sold

def _seed_needs(obs, farm, private):
    day = int(obs.get("day", 0))
    animal_plan = _animal_plan(obs, farm)
    crop_plan = _crop_assignment(obs, farm, animal_plan)
    needs = {crop: 0 for crop in CROPS}
    for (x, y), crop in crop_plan.items():
        tile = farm["tiles"][y][x]
        if tile is None or (isinstance(tile, dict) and tile.get("kind") == "WEED"):
            if day <= CROP_RULES[crop]["last_plant"]:
                needs[crop] += 1
    seeds = private.get("seeds", {}) or {}
    return {crop: max(0, needs[crop] - int(seeds.get(crop, 0))) for crop in CROPS}

def _animal_missing(obs, farm, private):
    target = _desired_animals(obs, farm)
    present = {a: 0 for a in ANIMALS}
    for animal in _actual_animals(farm):
        present[animal] += 1
    shed = private.get("shed", {}) or {}
    for animal in ANIMALS:
        present[animal] += int(shed.get(animal, 0))
    for inv in private.get("inventories", []) or []:
        for animal in ANIMALS:
            present[animal] += int((inv or {}).get(animal, 0))
    return {a: max(0, target[a] - present[a]) for a in ANIMALS}

def _market_actions(obs, farm, private):
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    final_day = day >= 29
    market = obs.get("market", {}) or {}
    prices = market.get("prices", {}) or {}
    shed = private.get("shed", {}) or {}
    orders = []
    budget = float(farm.get("money", 0))
    occupancy = sum(int(v) for v in shed.values())
    carried_by_item = {item: sum(int((inv or {}).get(item, 0)) for inv in private.get("inventories", []) or []) for item in PRODUCTS}
    pressure = occupancy + sum(carried_by_item.values())
    animal_count = len(_actual_animals(farm))
    desired = _desired_animals(obs, farm)
    wheat_reserve = sum(desired.values()) * (4 if not final_day else 0)

    sale_candidates = []
    for item in SELL_FLOORS:
        shed_qty = int(shed.get(item, 0))
        candidate_qty = shed_qty
        if final_day:
            candidate_qty += int(carried_by_item.get(item, 0))
        if item == "WHEAT" and not final_day:
            candidate_qty = max(0, candidate_qty - wheat_reserve)
        if candidate_qty <= 0:
            continue
        force = final_day or occupancy >= 94
        sell_qty = _sell_quantity(obs, item, candidate_qty, pressure=pressure, force=force)
        if sell_qty > 0:
            current_price = int(prices.get(item, DEFAULT_MARKET[item]["base"]))
            sale_candidates.append((sell_qty * current_price, item, sell_qty, shed_qty))
    sale_candidates.sort(reverse=True)
    max_sale_orders = 8 if final_day else (2 if hour <= 3 else 4)
    for _, item, qty, shed_qty in sale_candidates[:max_sale_orders]:
        orders.append(["SELL", item, 1000 if final_day else qty])
        actual_sell = min(qty, shed_qty)
        budget += actual_sell * max(1, min(int(prices.get(item, 1)), DEFAULT_MARKET[item]["base"]))
        if len(orders) >= 10:
            return orders

    if final_day:
        if hour <= 10:
            missing_hands = max(0, _target_hands(obs, farm) - len(farm.get("hands", [])))
            hire_index = int(farm.get("hires_today", 0))
            while missing_hands > 0 and len(orders) < 10:
                cost = _fib(hire_index)
                if budget < cost:
                    break
                orders.append(["HIRE"])
                budget -= cost
                hire_index += 1
                missing_hands -= 1
        return orders[:10]

    land_cost = _land_order(obs, farm, budget)
    if land_cost is not None and len(orders) < 10:
        orders.append(["BUY_LAND"])
        budget -= land_cost

    pending_animals = sum(desired.values())
    actual_animals = len(_actual_animals(farm))
    wheat_total = _stock(private, "WHEAT")
    wanted_wheat = max(0, max(4, actual_animals * 2) - wheat_total)
    if wanted_wheat > 0 and len(orders) < 10:
        buy_price = int(prices.get("WHEAT", 25))
        capacity_room = max(0, 96 - occupancy)
        qty = min(wanted_wheat, capacity_room, max(0, int((budget - 220) // max(1, buy_price))))
        if qty > 0:
            orders.append(["BUY_PRODUCT", "WHEAT", qty])
            budget -= qty * buy_price
            occupancy += qty

    if day <= 13:
        missing = _animal_missing(obs, farm, private)
        for animal in ("GOOSE", "COW", "SHEEP"):
            if len(orders) >= 10:
                break
            qty = missing[animal]
            cost = ANIMAL_RULES[animal]["cost"]
            capacity_room = max(0, 96 - occupancy)
            reserve = 850 if day <= 2 else 500
            affordable = min(qty, 4, capacity_room, max(0, int((budget - reserve) // cost)))
            if affordable > 0:
                orders.append(["BUY_ANIMAL", animal, affordable])
                budget -= affordable * cost
                occupancy += affordable

    needs = _seed_needs(obs, farm, private)
    ranked_seeds = sorted(
        (crop for crop in CROPS if needs[crop] > 0),
        key=lambda crop: (_crop_score(obs, crop, animal_count), -CROP_RULES[crop]["seed"]),
        reverse=True,
    )
    seed_order_limit = 3 if hour <= 5 else 2
    seed_orders = 0
    for crop in ranked_seeds:
        if len(orders) >= 10 or seed_orders >= seed_order_limit:
            break
        cost = CROP_RULES[crop]["seed"]
        qty = min(needs[crop], 20, max(0, int((budget - 220) // cost)))
        if qty > 0:
            orders.append(["BUY_SEED", crop, qty])
            budget -= qty * cost
            seed_orders += 1

    missing_hands = max(0, _target_hands(obs, farm) - len(farm.get("hands", [])))
    hire_index = int(farm.get("hires_today", 0))
    while missing_hands > 0 and len(orders) < 10:
        cost = _fib(hire_index)
        reserve = 80 if hour <= 3 else 40
        if budget < cost + reserve:
            break
        orders.append(["HIRE"])
        budget -= cost
        hire_index += 1
        missing_hands -= 1

    return orders[:10]

def agent(obs):
    farms = obs.get("farms", []) or []
    player = int(obs.get("player", 0))
    if player < 0 or player >= len(farms):
        return {"farmer": ["PASS"], "hands": [], "market": []}
    farm = farms[player]
    private = obs.get("private", {}) or {}
    actions = _unit_actions(obs, farm, private)
    farmer = actions[0] if actions else ["PASS"]
    hands = actions[1:] if len(actions) > 1 else []
    return {"farmer": farmer, "hands": hands, "market": _market_actions(obs, farm, private)}


# ===========================================================================
# 100K META OVERLAY: fixed livestock geometry + opponent-aware scale
# ===========================================================================
_orig_crop_assignment = _crop_assignment
_orig_market_actions = _market_actions


def _opponent_animal_counts(obs):
    farms = obs.get("farms", []) or []
    player = int(obs.get("player", 0))
    if len(farms) != 2:
        return {"GOOSE": 0, "COW": 0, "SHEEP": 0}
    return _placed_animal_counts(farms[1 - player])


_COW_COMPETITION_LATCH = {}

def _cow_competition(obs):
    player = int(obs.get("player", 0))
    step = int(obs.get("step", int(obs.get("day", 0)) * 24 + int(obs.get("hour", 0))))
    if step == 0:
        _COW_COMPETITION_LATCH[player] = False
    current = int(obs.get("day", 0)) >= 1 and _opponent_animal_counts(obs).get("COW", 0) >= 3
    if current:
        _COW_COMPETITION_LATCH[player] = True
    return bool(_COW_COMPETITION_LATCH.get(player, False))


def _anti_cow_target(obs):
    day = int(obs.get("day", 0))
    player = int(obs.get("player", 0))
    shops = set((obs.get("town", {}) or {}).get("unlocked_shops", []) or [])
    milk_support = bool(shops.intersection({"PIZZA_SHOP", "ICE_CREAM_SHOP", "SMOOTHIE_SHOP"}))
    if day >= 6 and not milk_support and player == 0:
        return 7
    return 6



def _goose_competition(obs):
    counts = _opponent_animal_counts(obs)
    return counts.get("GOOSE", 0) >= 3 and counts.get("COW", 0) < 2

def _fixed_animal_plan(obs, farm):
    n = len(farm.get("tiles", []) or [])
    h = n // 2
    unlocked = farm.get("unlocked_quadrants", []) or []
    anti = _cow_competition(obs)
    target = _anti_cow_target(obs) if anti else (12 if _goose_competition(obs) else 13)

    slots = [(h - 1, h - 1), (h - 1, h - 2), (h - 2, h - 1)]
    if "NE" in unlocked:
        slots += [
            (h, h - 1), (h + 1, h - 1), (h + 2, h - 1),
            (h + 3, h - 1), (h + 4, h - 1),
            (h, h - 2), (h + 1, h - 2), (h + 2, h - 2),
            (h + 3, h - 2),
        ]
    if "SW" in unlocked and not anti:
        slots += [(h - 1, h), (h - 1, h + 1)]
    slots = [p for p in slots if 0 <= p[0] < n and 0 <= p[1] < n]
    return {pos: "COW" for pos in slots[:target]}


def _desired_animals(obs, farm):
    existing = _placed_animal_counts(farm)
    plan = _fixed_animal_plan(obs, farm)
    target = {animal: sum(kind == animal for kind in plan.values()) for animal in ANIMALS}
    return {
        animal: max(existing[animal], target[animal])
        for animal in ANIMALS
    }


def _animal_plan(obs, farm):
    plan = {}
    for y, row in enumerate(farm.get("tiles", []) or []):
        for x, tile in enumerate(row):
            if isinstance(tile, dict) and tile.get("animal") in ANIMAL_RULES:
                plan[(x, y)] = tile["animal"]
    plan.update(_fixed_animal_plan(obs, farm))
    return plan


def _crop_assignment(obs, farm, animal_plan):
    plan = _orig_crop_assignment(obs, farm, animal_plan)
    h = len(farm.get("tiles", []) or []) // 2
    # Keep the agricultural workload on the two northern quadrants. SW is used
    # only for two high-ROI late cows in the non-competitive milk branch.
    return {pos: crop for pos, crop in plan.items() if pos[1] < h}


def _target_hands(obs, farm):
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    unlocked = farm.get("unlocked_quadrants", []) or []
    anti = _cow_competition(obs)
    if day >= 29:
        target = 14 if anti else 15
        return target if hour < 12 else len(farm.get("hands", []))
    if len(unlocked) <= 1:
        return 9
    if anti:
        return 12
    return 11 if len(unlocked) == 2 else 12


def _land_order(obs, farm, budget):
    day = int(obs.get("day", 0))
    extra = len(farm.get("unlocked_quadrants", []) or []) - 1
    if extra == 0 and 4 <= day <= 10 and budget >= 1600:
        return 1000
    if not _cow_competition(obs) and extra == 1 and 11 <= day <= 17 and budget >= 4000:
        return 2000
    return None


def _market_actions(obs, farm, private):
    return _orig_market_actions(obs, farm, private)

_base_crop_weights_v5 = _crop_weights

def _crop_weights(obs, animal_count):
    if not _cow_competition(obs): return _base_crop_weights_v5(obs, animal_count)
    day=int(obs.get("day",0)); raw={'WHEAT': 0.3, 'CARROT': 0.08, 'TOMATO': 0.28, 'STRAWBERRY': 0.12, 'MELON': 0.22}; available=[c for c in CROPS if day <= CROP_RULES[c]["last_plant"]]
    if not available:return {"WHEAT":1.0}
    vals={c:raw.get(c,0.0) for c in available};total=sum(vals.values())
    return {c:v/total for c,v in vals.items()}
