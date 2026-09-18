# Kaggriculture public expansion baseline
#
# Strategy
# - Buy useful land early and run a mixed crop plan instead of a single-crop opening.
# - Build a mixed cow/sheep herd and reserve wheat for daily feed.
# - Hire up to twelve hands early in the day so expansion tiles can be worked in parallel.
#
# Known limitations
# - Hiring is deliberately simple and can overpay when the marginal hand has little work.
# - Crop and herd targets are fixed; the policy does not condition on the opponent.
# - Late-horizon adaptation and inventory routing are intentionally simple.
#
# This is a reproducible public baseline, not the current private competition agent.

from collections import deque

CROP_RULES = {
    "WHEAT": (10, 2, 4, 24, False),
    "CARROT": (20, 2, 3, 25, False),
    "TOMATO": (50, 8, 0, 19, True),
    "STRAWBERRY": (100, 10, 0, 16, True),
    "MELON": (80, 10, 12, 16, False),
}

COW_COST = 400
TARGET_HANDS_CORE = 10
TARGET_HANDS_EXPANDED = 10
LAND_DAY = 4
EXPANSION_DEADLINE = 16
EXPANSION_BUFFER = 500
SELL_ORDER = (
    "MILK", "FERTILIZER", "MELON", "STRAWBERRY",
    "TOMATO", "CARROT", "WHEAT", "EGG", "WOOL",
)


def _animal_slots(board_size, unlocked_quadrants):
    h = board_size // 2
    quadrants = set(unlocked_quadrants or ["NW"])
    # The four core slots reproduce the public top-agent opening: 2 cows + 2 sheep.
    slots = [(h - 1, h - 1), (h - 2, h - 1), (h - 1, h - 2), (h - 1, h - 3)]
    if "NE" in quadrants:
        slots.extend([(h, h - 1), (h, h - 2), (h + 1, h - 3), (h + 2, h - 2), (h + 2, h - 1)])
    if "SW" in quadrants:
        slots.extend([(h - 2, h), (h - 1, h), (h - 1, h + 1)])
    return [p for p in slots if 0 <= p[0] < board_size and 0 <= p[1] < board_size]


def _shed_tiles(board_size, tiles):
    h = board_size // 2
    out = []
    for p in ((h - 1, h - 1), (h, h - 1), (h - 1, h), (h, h)):
        if 0 <= p[0] < board_size and 0 <= p[1] < board_size and tiles[p[1]][p[0]] != "LOCKED":
            out.append(p)
    return out


def _dist(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _nearest_shed(board_size, tiles, pos):
    cells = _shed_tiles(board_size, tiles)
    return min(cells, key=lambda p: (_dist(pos, p), p[1], p[0])) if cells else tuple(pos)


def _move(tiles, source, target):
    source = tuple(source)
    target = tuple(target)
    if source == target:
        return ["PASS"]
    n = len(tiles)
    q = deque([source])
    parent = {source: None}
    move_to = {}
    directions = ((1, 0, "EAST"), (-1, 0, "WEST"), (0, 1, "SOUTH"), (0, -1, "NORTH"))
    while q:
        cur = q.popleft()
        if cur == target:
            break
        ranked = sorted(
            directions,
            key=lambda d: abs(cur[0] + d[0] - target[0]) + abs(cur[1] + d[1] - target[1]),
        )
        for dx, dy, name in ranked:
            nxt = (cur[0] + dx, cur[1] + dy)
            if not (0 <= nxt[0] < n and 0 <= nxt[1] < n):
                continue
            if tiles[nxt[1]][nxt[0]] == "LOCKED" or nxt in parent:
                continue
            parent[nxt] = cur
            move_to[nxt] = name
            q.append(nxt)
    if target not in parent:
        return ["PASS"]
    cur = target
    while parent[cur] != source:
        cur = parent[cur]
        if cur is None:
            return ["PASS"]
    return [move_to[cur]]


def _inventories(private):
    return [dict(x or {}) for x in (private.get("inventories", []) or [])]


def _total(private, item):
    value = int((private.get("shed", {}) or {}).get(item, 0))
    for inv in private.get("inventories", []) or []:
        value += int((inv or {}).get(item, 0))
    return value


def _placed_cows(farm):
    return sum(
        1
        for row in farm.get("tiles", []) or []
        for tile in row
        if isinstance(tile, dict) and tile.get("animal") == "COW"
    )


def _count_public_animals(farm, animal):
    return sum(
        1
        for row in farm.get("tiles", []) or []
        for tile in row
        if isinstance(tile, dict) and tile.get("animal") == animal
    )


def _crop_plan(board_size, unlocked_quadrants, animal_slots):
    h = board_size // 2
    quadrants = set(unlocked_quadrants or ["NW"])
    shed = (h - 1, h - 1)
    mixes = {
        "NW": (("MELON", 11), ("STRAWBERRY", 5), ("CARROT", 2), ("WHEAT", 4)),
        "NE": (("STRAWBERRY", 14), ("WHEAT", 4), ("CARROT", 1)),
        "SW": (("STRAWBERRY", 20), ("WHEAT", 4), ("CARROT", 1)),
        "SE": (("STRAWBERRY", 18), ("WHEAT", 5), ("CARROT", 2)),
    }
    bounds = {
        "NW": (range(0, h), range(0, h)),
        "NE": (range(h, board_size), range(0, h)),
        "SW": (range(0, h), range(h, board_size)),
        "SE": (range(h, board_size), range(h, board_size)),
    }
    plan = {}
    for quadrant in ("NW", "NE", "SW", "SE"):
        if quadrant not in quadrants:
            continue
        xs, ys = bounds[quadrant]
        cells = [(x, y) for y in ys for x in xs if (x, y) not in animal_slots]
        cells.sort(key=lambda p: (_dist(p, shed), p[1], p[0]))
        crops = []
        for crop, count in mixes[quadrant]:
            crops.extend([crop] * count)
        while len(crops) < len(cells):
            crops.append("STRAWBERRY")
        plan.update(zip(cells, crops[:len(cells)]))
    return plan

def _add(tasks, priority, pos, action, need=None):
    tasks.append({"priority": priority, "pos": tuple(pos), "action": list(action), "need": need})


def _animal_for_slot(position, slots):
    index = slots.index(position)
    sheep_target = _TOP_ROUTE[1] if _TOP_ROUTE is not None else 2
    extra_sheep_slots = (6, 8, 10, 11, 5, 7, 9, 4)
    sheep_slots = {2, 3, *extra_sheep_slots[:max(0, sheep_target - 2)]}
    return "SHEEP" if index in sheep_slots else "COW"


def _animal_tasks(obs, farm, private, slots):
    day = int(obs.get("day", 0))
    prices = ((obs.get("market", {}) or {}).get("prices", {}) or {})
    tasks = []
    tiles = farm["tiles"]
    for pos in slots:
        x, y = pos
        tile = tiles[y][x]
        planned = _animal_for_slot(pos, slots)
        if tile == "LOCKED":
            continue
        if isinstance(tile, dict) and tile.get("animal") in ("COW", "SHEEP"):
            animal = tile["animal"]
            product = "MILK" if animal == "COW" else "WOOL"
            if not tile.get("fed_today", False):
                _add(tasks, 0, pos, ["FEED"], "WHEAT")
            if tile.get("fertilizer_available", False):
                _add(tasks, 1, pos, ["COLLECT_FERTILIZER"])
            if day <= 27 and int(prices.get(product, 100)) >= 20 and not tile.get("cared_today", False):
                _add(tasks, 2, pos, ["CARE"])
            held = int(tile.get("yield_units", 0))
            if held >= 3 or (day >= 27 and held > 0):
                _add(tasks, 1, pos, ["HARVEST"])
        elif tile is None:
            _add(tasks, 0, pos, ["BUILD_PASTURE"])
        elif isinstance(tile, dict) and tile.get("kind") == "WEED":
            _add(tasks, 0, pos, ["DIG"])
        elif isinstance(tile, dict) and tile.get("kind") == "PASTURE" and not tile.get("animal"):
            _add(tasks, 0, pos, ["PLACE", planned], planned)
        elif isinstance(tile, dict) and tile.get("kind") == "PLANT":
            _add(tasks, 0, pos, ["DIG"])
    return tasks

def _crop_tasks(obs, farm, private, plan, cow_slots):
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    seeds = private.get("seeds", {}) or {}
    tasks = []
    for pos, planned in plan.items():
        if pos in cow_slots:
            continue
        x, y = pos
        tile = farm["tiles"][y][x]
        if tile == "LOCKED":
            continue
        if tile is None:
            if day <= CROP_RULES[planned][3] and hour <= 19 and int(seeds.get(planned, 0)) > 0:
                _add(tasks, 8, pos, ["PLANT", planned])
            continue
        if not isinstance(tile, dict):
            continue
        if tile.get("kind") == "WEED":
            _add(tasks, 7, pos, ["DIG"])
            continue
        if tile.get("kind") != "PLANT":
            continue
        crop = tile.get("crop", planned)
        _, first, harvest_day, _, ongoing = CROP_RULES.get(crop, CROP_RULES[planned])
        age = day - int(tile.get("planted_day", day))
        held = int(tile.get("yield_units", 0))
        risk = int(tile.get("consecutive_unwatered", 0)) >= 1
        if not tile.get("watered_today", False):
            _add(tasks, 3 if risk or hour >= 17 else 5, pos, ["WATER"])
            continue
        if not ongoing:
            if age >= harvest_day and held > 0:
                _add(tasks, 4, pos, ["HARVEST"])
        elif age >= first and (held >= 3 or (day >= 27 and held > 0)):
            _add(tasks, 4, pos, ["HARVEST"])
    return tasks


def _task_cost(farm, pos, inv, shed, task):
    need = task["need"]
    target = task["pos"]
    if need is None or int(inv.get(need, 0)) > 0:
        return _dist(pos, target)
    if int(shed.get(need, 0)) <= 0:
        return 10000
    s = _nearest_shed(len(farm["tiles"]), farm["tiles"], pos)
    return _dist(pos, s) + 1 + _dist(s, target)


def _task_action(farm, pos, inv, shed, task):
    need = task["need"]
    if need is not None and int(inv.get(need, 0)) <= 0:
        if int(shed.get(need, 0)) <= 0:
            return ["PASS"]
        s = _nearest_shed(len(farm["tiles"]), farm["tiles"], pos)
        if tuple(pos) == tuple(s):
            return ["PICKUP", need, 1 if need in ("COW", "SHEEP") else 4]
        return _move(farm["tiles"], pos, s)
    if tuple(pos) == task["pos"]:
        return list(task["action"])
    return _move(farm["tiles"], pos, task["pos"])


def _unit_actions(obs, farm, private, cow_slots, crop_plan):
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    positions = [tuple(farm.get("farmer", [0, 0]))] + [tuple(p) for p in farm.get("hands", [])]
    invs = _inventories(private)
    while len(invs) < len(positions):
        invs.append({})
    shed = dict(private.get("shed", {}) or {})
    tasks = _animal_tasks(obs, farm, private, cow_slots) + _crop_tasks(obs, farm, private, crop_plan, set(cow_slots))
    actions = [["PASS"] for _ in positions]
    free_units = set(range(len(positions)))
    free_tasks = set(range(len(tasks)))

    if day >= 29 and hour >= 14:
        for i, pos in enumerate(positions):
            carried = sum(int(v) for v in invs[i].values())
            s = _nearest_shed(len(farm["tiles"]), farm["tiles"], pos)
            if carried:
                actions[i] = ["DROP"] if pos == s else _move(farm["tiles"], pos, s)
            elif pos != s:
                actions[i] = _move(farm["tiles"], pos, s)
        return actions

    while free_units and free_tasks:
        best = None
        for i in free_units:
            for j in free_tasks:
                task = tasks[j]
                cost = _task_cost(farm, positions[i], invs[i], shed, task)
                if cost >= 10000:
                    continue
                key = (task["priority"], cost, task["pos"][1], task["pos"][0], i, j)
                if best is None or key < best[0]:
                    best = (key, i, j)
        if best is None:
            break
        _, i, j = best
        actions[i] = _task_action(farm, positions[i], invs[i], shed, tasks[j])
        free_units.remove(i)
        free_tasks.remove(j)

    remaining = dict(private.get("seeds", {}) or {})
    for i, action in enumerate(actions):
        if len(action) >= 2 and action[0] == "PLANT":
            crop = action[1]
            if int(remaining.get(crop, 0)) <= 0:
                actions[i] = ["PASS"]
            else:
                remaining[crop] -= 1
    return actions


def _fib(n):
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a


_TOP_ROUTE = None
_TOP_PHASE = 0


def _top_target(obs, expanded):
    global _TOP_ROUTE, _TOP_PHASE
    if not expanded:
        return {"COW": 2, "SHEEP": 2}
    day = int(obs.get("day", 0))
    if day < 7:
        return {"COW": 2, "SHEEP": 2}
    prices = ((obs.get("market", {}) or {}).get("prices", {}) or {})
    milk = float(prices.get("MILK", 160))
    wool = float(prices.get("WOOL", 200))
    if _TOP_PHASE == 0:
        # The public leader buys the first extra tranche on days 7-8.  When
        # milk is nearly as valuable as wool it concentrates that tranche in
        # cows; otherwise it preserves a balanced option for the final read.
        _TOP_ROUTE = (6, 2) if milk >= 0.97 * wool else (4, 4)
        _TOP_PHASE = 1
    if day >= 11 and _TOP_PHASE == 1:
        farms = obs.get("farms", []) or []
        player = int(obs.get("player", 0))
        farm = farms[player] if player < len(farms) else {}
        private = obs.get("private", {}) or {}
        cows = _count_public_animals(farm, "COW") + _total(private, "COW")
        sheep = _count_public_animals(farm, "SHEEP") + _total(private, "SHEEP")
        remaining = max(0, 12 - cows - sheep)
        if milk > 1.03 * wool:
            cow_add, sheep_add = remaining, 0
        elif wool > 1.03 * milk:
            cow_add, sheep_add = 0, remaining
        else:
            cow_add = (remaining + 1) // 2
            sheep_add = remaining // 2
        _TOP_ROUTE = (cows + cow_add, sheep + sheep_add)
        _TOP_PHASE = 2
    return {"COW": _TOP_ROUTE[0], "SHEEP": _TOP_ROUTE[1]}


def _market_actions(obs, farm, private, animal_slots, crop_plan):
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    shed = private.get("shed", {}) or {}
    prices = ((obs.get("market", {}) or {}).get("prices", {}) or {})
    orders = []
    budget = float(farm.get("money", 0))

    placed = {
        animal: _count_public_animals(farm, animal)
        for animal in ("COW", "SHEEP")
    }
    owned = {
        animal: placed[animal] + _total(private, animal)
        for animal in ("COW", "SHEEP")
    }
    quadrants = list(farm.get("unlocked_quadrants", []) or ["NW"])
    expanded = len(quadrants) >= 2
    target = _top_target(obs, expanded)
    animal_count = placed["COW"] + placed["SHEEP"]
    wheat_reserve = max(8, animal_count * 3)

    for item in SELL_ORDER:
        if len(orders) >= 6:
            break
        amount = int(shed.get(item, 0))
        if item == "WHEAT" and day < 29:
            amount = max(0, amount - wheat_reserve)
        if amount <= 0:
            continue
        cap = amount if day >= 29 else 20 if item in ("MILK", "WOOL", "FERTILIZER") else 28
        quantity = min(amount, cap)
        orders.append(["SELL", item, quantity])
        budget += quantity * max(1, int(prices.get(item, 1)))

    if day >= 29:
        return orders

    extra_land = max(0, len(quadrants) - 1)
    land_costs = (1000, 2000, 4000)
    earliest = 5 if extra_land == 0 else 9 if extra_land == 1 else 15
    if (
        extra_land < 2
        and earliest <= day <= 18
        and len(orders) < 10
        and budget >= land_costs[extra_land] + (300 if extra_land == 0 else 500)
    ):
        orders.append(["BUY_LAND"])
        budget -= land_costs[extra_land]
        extra_land += 1
        expanded = True
        target = _top_target(obs, True)

    costs = {"COW": 400, "SHEEP": 500}
    for animal in ("COW", "SHEEP"):
        if len(orders) >= 10:
            break
        missing = max(0, target[animal] - owned[animal])
        affordable = max(0, int((budget - 220) // costs[animal]))
        quantity = min(missing, 2, affordable)
        if quantity > 0:
            orders.append(["BUY_ANIMAL", animal, quantity])
            budget -= quantity * costs[animal]
            owned[animal] += quantity

    wheat_total = _total(private, "WHEAT")
    wanted_wheat = max(0, max(8, (placed["COW"] + placed["SHEEP"]) * 3 + 3) - wheat_total)
    if wanted_wheat > 0 and len(orders) < 10:
        price = max(1, int(prices.get("WHEAT", 25)))
        quantity = min(wanted_wheat, max(0, int((budget - 100) // price)))
        if quantity > 0:
            orders.append(["BUY_PRODUCT", "WHEAT", quantity])
            budget -= quantity * price

    seeds = private.get("seeds", {}) or {}
    needs = {crop: 0 for crop in CROP_RULES}
    for (x, y), crop in crop_plan.items():
        tile = farm["tiles"][y][x]
        if tile is None and day <= CROP_RULES[crop][3]:
            needs[crop] += 1
    for crop in ("MELON", "STRAWBERRY", "CARROT", "WHEAT"):
        if len(orders) >= 10:
            break
        wanted = max(0, needs[crop] - int(seeds.get(crop, 0)))
        if wanted <= 0:
            continue
        cost = CROP_RULES[crop][0]
        quantity = min(wanted, 20, max(0, int((budget - 80) // cost)))
        if quantity > 0:
            orders.append(["BUY_SEED", crop, quantity])
            budget -= quantity * cost

    if hour <= 3:
        missing = max(0, 10 - len(farm.get("hands", []) or []))
        hire_index = int(farm.get("hires_today", 0))
        while missing > 0 and len(orders) < 10:
            cost = _fib(hire_index)
            if budget < cost + 20:
                break
            orders.append(["HIRE"])
            budget -= cost
            hire_index += 1
            missing -= 1
    return orders[:10]

def agent(obs):
    farms = obs.get("farms", []) or []
    player = int(obs.get("player", 0))
    if player < 0 or player >= len(farms):
        return {"farmer": ["PASS"], "hands": [], "market": []}
    farm = farms[player]
    private = obs.get("private", {}) or {}
    board_size = len(farm.get("tiles", [])) or 10
    quadrants = list(farm.get("unlocked_quadrants", []) or ["NW"])
    expanded = len(quadrants) >= 2
    all_animal_slots = _animal_slots(board_size, quadrants)
    animals_owned = sum(
        _count_public_animals(farm, animal) + _total(private, animal)
        for animal in ("COW", "SHEEP")
    )
    active_count = min(len(all_animal_slots), max(3, animals_owned))
    animal_slots = all_animal_slots[:active_count]
    crop_plan = _crop_plan(board_size, quadrants, set(all_animal_slots))
    actions = _unit_actions(obs, farm, private, animal_slots, crop_plan)
    return {
        "farmer": actions[0] if actions else ["PASS"],
        "hands": actions[1:] if len(actions) > 1 else [],
        "market": _market_actions(obs, farm, private, all_animal_slots, crop_plan),
    }

# ---------------------------------------------------------------------------
# Frontier Fusion upgrades
# ---------------------------------------------------------------------------

_BASE_ANIMAL_TASKS = _animal_tasks
_BASE_CROP_TASKS = _crop_tasks
_BASE_TASK_ACTION = _task_action
_BASE_MARKET_ACTIONS = _market_actions

SELL_ORDER = (
    "MILK", "WOOL", "MELON", "STRAWBERRY",
    "FERTILIZER", "TOMATO", "CARROT", "WHEAT", "EGG",
)

_LAST_STEP = -1


def _step_number(obs):
    return int(obs.get("step", int(obs.get("day", 0)) * 24 + int(obs.get("hour", 0))))


def _reset_episode_state(obs):
    global _TOP_ROUTE, _TOP_PHASE, _LAST_STEP
    step = _step_number(obs)
    if step < _LAST_STEP or (step == 0 and _LAST_STEP > 0):
        _TOP_ROUTE = None
        _TOP_PHASE = 0
    _LAST_STEP = step


def _opponent_animals(obs):
    farms = obs.get("farms", []) or []
    player = int(obs.get("player", 0))
    counts = {"GOOSE": 0, "COW": 0, "SHEEP": 0}
    if len(farms) != 2 or player not in (0, 1):
        return counts
    opponent = farms[1 - player]
    for row in opponent.get("tiles", []) or []:
        for tile in row:
            if isinstance(tile, dict):
                animal = tile.get("animal")
                if animal in counts:
                    counts[animal] += 1
    return counts


def _route_signals(obs):
    prices = ((obs.get("market", {}) or {}).get("prices", {}) or {})
    milk = float(prices.get("MILK", 160))
    wool = float(prices.get("WOOL", 200))
    opponent = _opponent_animals(obs)
    shops = set(((obs.get("town", {}) or {}).get("unlocked_shops", []) or []))

    milk_demand = len(shops.intersection({"PIZZA_SHOP", "ICE_CREAM_SHOP", "SMOOTHIE_SHOP"}))
    wool_demand = 1 if "YARN_STORE" in shops else 0

    milk_signal = milk * (1.0 + 0.055 * milk_demand) / (1.0 + 0.045 * opponent["COW"])
    wool_signal = wool * (1.0 + 0.080 * wool_demand) / (1.0 + 0.040 * opponent["SHEEP"])
    return milk_signal, wool_signal, opponent


def _top_target(obs, expanded):
    global _TOP_ROUTE, _TOP_PHASE
    if not expanded:
        _TOP_ROUTE = None
        _TOP_PHASE = 0
        return {"COW": 2, "SHEEP": 2}

    day = int(obs.get("day", 0))
    if day < 7:
        return {"COW": 2, "SHEEP": 2}

    milk_signal, wool_signal, opponent = _route_signals(obs)

    if _TOP_PHASE == 0 or _TOP_ROUTE is None:
        if opponent["COW"] >= 6 and opponent["SHEEP"] <= 2:
            _TOP_ROUTE = (4, 4)
        elif opponent["SHEEP"] >= 6 and opponent["COW"] <= 2:
            _TOP_ROUTE = (6, 2)
        else:
            _TOP_ROUTE = (6, 2) if milk_signal >= 0.97 * wool_signal else (4, 4)
        _TOP_PHASE = 1

    if day >= 11 and _TOP_PHASE == 1:
        farms = obs.get("farms", []) or []
        player = int(obs.get("player", 0))
        farm = farms[player] if player < len(farms) else {}
        private = obs.get("private", {}) or {}
        cows = _count_public_animals(farm, "COW") + _total(private, "COW")
        sheep = _count_public_animals(farm, "SHEEP") + _total(private, "SHEEP")
        remaining = max(0, 12 - cows - sheep)

        force_sheep = opponent["COW"] >= 7 and opponent["COW"] >= opponent["SHEEP"] + 4
        force_cows = opponent["SHEEP"] >= 7 and opponent["SHEEP"] >= opponent["COW"] + 4

        if force_sheep or wool_signal > 1.05 * milk_signal:
            cow_add, sheep_add = 0, remaining
        elif force_cows or milk_signal > 1.05 * wool_signal:
            cow_add, sheep_add = remaining, 0
        else:
            cow_need = max(0, 6 - cows)
            cow_add = min(remaining, cow_need)
            sheep_add = remaining - cow_add

        _TOP_ROUTE = (cows + cow_add, sheep + sheep_add)
        _TOP_PHASE = 2

    return {"COW": int(_TOP_ROUTE[0]), "SHEEP": int(_TOP_ROUTE[1])}


def _fertilizer_gain(obs, tile):
    if not isinstance(tile, dict) or tile.get("kind") != "PLANT":
        return 0.0
    day = int(obs.get("day", 0))
    if day >= 27 or int(tile.get("fertilized_until_day", -1)) >= day:
        return 0.0

    crop = tile.get("crop")
    planted = int(tile.get("planted_day", day))
    age = day - planted
    held = int(tile.get("yield_units", 0))
    prices = ((obs.get("market", {}) or {}).get("prices", {}) or {})
    crop_price = float(prices.get(crop, 0))
    fertilizer_price = float(prices.get("FERTILIZER", 100))

    bonus_units = 0
    if crop == "MELON":
        if 5 <= age <= 11 and held < 6:
            active_days = sum(1 for future_age in (age, age + 1, age + 2) if 6 <= future_age <= 12)
            bonus_units = min(max(0, 6 - held), active_days)
    elif crop == "STRAWBERRY":
        if age >= 8:
            for offset in (0, 1, 2):
                next_day = day + offset + 1
                since_first = next_day - planted - 10
                if since_first >= 0 and since_first % 2 == 0:
                    production_index = since_first // 2 + 1
                    if production_index <= 4:
                        bonus_units += 1

    gain = bonus_units * crop_price - fertilizer_price
    return gain if gain >= 35 else 0.0


def _animal_tasks(obs, farm, private, slots):
    tasks = _BASE_ANIMAL_TASKS(obs, farm, private, slots)
    prices = ((obs.get("market", {}) or {}).get("prices", {}) or {})
    fertilizer_price = int(prices.get("FERTILIZER", 100))
    fertilizer_stock = _total(private, "FERTILIZER")
    tiles = farm.get("tiles", []) or []

    filtered = []
    for task in tasks:
        action = task.get("action", ["PASS"])
        op = action[0] if action else "PASS"
        x, y = task["pos"]
        tile = tiles[y][x] if 0 <= y < len(tiles) and 0 <= x < len(tiles[y]) else None

        if op == "COLLECT_FERTILIZER":
            if fertilizer_price < 22 and fertilizer_stock >= 6:
                continue

        if op == "CARE" and isinstance(tile, dict):
            animal = tile.get("animal")
            product = "MILK" if animal == "COW" else "WOOL"
            product_floor = 42 if animal == "COW" else 52
            pending = int(tile.get("pending_care_bonus", 0))
            if pending >= 5 or int(prices.get(product, 0)) < product_floor:
                continue

        filtered.append(task)
    return filtered


def _crop_tasks(obs, farm, private, plan, animal_slots):
    tasks = _BASE_CROP_TASKS(obs, farm, private, plan, animal_slots)
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    stock = _total(private, "FERTILIZER")
    if stock <= 0 or day >= 27 or hour > 17:
        return tasks

    candidates = []
    tiles = farm.get("tiles", []) or []
    for pos in sorted(plan, key=lambda p: (p[1], p[0])):
        if pos in animal_slots:
            continue
        x, y = pos
        tile = tiles[y][x]
        if not isinstance(tile, dict) or tile.get("kind") != "PLANT":
            continue
        if int(tile.get("consecutive_unwatered", 0)) >= 1:
            continue
        crop = tile.get("crop")
        held = int(tile.get("yield_units", 0))
        if crop == "STRAWBERRY" and held >= 3:
            continue
        gain = _fertilizer_gain(obs, tile)
        if gain > 0:
            candidates.append((gain, pos))

    selected = {pos for _, pos in sorted(candidates, key=lambda z: (-z[0], z[1][1], z[1][0]))[:min(stock, 2)]}
    if not selected:
        return tasks

    tasks = [task for task in tasks if task.get("pos") not in selected]
    for pos in sorted(selected, key=lambda p: (p[1], p[0])):
        _add(tasks, 2, pos, ["FERTILIZE"], "FERTILIZER")
    return tasks


def _task_action(farm, pos, inv, shed, task):
    need = task.get("need")
    if need == "FERTILIZER" and int(inv.get("FERTILIZER", 0)) <= 0:
        if int(shed.get("FERTILIZER", 0)) <= 0:
            return ["PASS"]
        shed_pos = _nearest_shed(len(farm["tiles"]), farm["tiles"], pos)
        if tuple(pos) == tuple(shed_pos):
            return ["PICKUP", "FERTILIZER", 1]
        return _move(farm["tiles"], pos, shed_pos)
    return _BASE_TASK_ACTION(farm, pos, inv, shed, task)


def _market_actions(obs, farm, private, animal_slots, crop_plan):
    orders = _BASE_MARKET_ACTIONS(obs, farm, private, animal_slots, crop_plan)
    day = int(obs.get("day", 0))
    shed = private.get("shed", {}) or {}
    reserve = 6 if day <= 25 else 0
    output = []

    for order in orders:
        if (
            isinstance(order, list)
            and len(order) >= 3
            and order[0] == "SELL"
            and order[1] == "FERTILIZER"
        ):
            available = max(0, int(shed.get("FERTILIZER", 0)) - reserve)
            quantity = min(int(order[2]), available)
            if quantity <= 0:
                continue
            order = ["SELL", "FERTILIZER", quantity]
        output.append(order)
    return output[:10]


def agent(obs):
    _reset_episode_state(obs)
    farms = obs.get("farms", []) or []
    player = int(obs.get("player", 0))
    if player < 0 or player >= len(farms):
        return {"farmer": ["PASS"], "hands": [], "market": []}

    farm = farms[player]
    private = obs.get("private", {}) or {}
    board_size = len(farm.get("tiles", [])) or 10
    quadrants = list(farm.get("unlocked_quadrants", []) or ["NW"])
    all_animal_slots = _animal_slots(board_size, quadrants)
    animals_owned = sum(
        _count_public_animals(farm, animal) + _total(private, animal)
        for animal in ("COW", "SHEEP")
    )
    active_count = min(len(all_animal_slots), max(3, animals_owned))
    animal_slots = all_animal_slots[:active_count]
    crop_plan = _crop_plan(board_size, quadrants, set(all_animal_slots))
    actions = _unit_actions(obs, farm, private, animal_slots, crop_plan)

    return {
        "farmer": actions[0] if actions else ["PASS"],
        "hands": actions[1:] if len(actions) > 1 else [],
        "market": _market_actions(obs, farm, private, all_animal_slots, crop_plan),
    }
