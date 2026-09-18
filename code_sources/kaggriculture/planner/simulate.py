"""Fast, pure-Python forward model of the kaggriculture engine.

This is a line-for-line port of every mechanic in
`kaggle_environments/envs/kaggriculture/kaggriculture.py` (interpreter,
_process_market, _end_of_day, decay, weeds, town consumption), decoupled from
the kaggle_environments harness so it can be stepped thousands of times per
second instead of ~140 times per second through env.step().

State shape mirrors the real observation exactly (plain dicts: farms[],
private[], market, town) so code written against a live `obs` dict (task
builders, routers, opponent models) works unmodified against this simulator.

FIDELITY IS EVERYTHING. Nothing downstream (rolling horizon, MCTS, IRL reward
evaluation, BC training labels) is trustworthy until `tests/test_sim_fidelity.py`
shows zero divergence against real replays. Do not build on this file until
that test passes clean.
"""
import math
import random

# --------------------------------------------------------------- engine data
# Copied verbatim from kaggriculture.py. Do not hand-tune these -- they define
# the physics, not agent behaviour.

CROPS = {
    "WHEAT":      {"seed": 10, "first_yield_day": 2, "max_yield_day": 4, "interval": 0, "max_yield": 6, "ongoing": False},
    "CARROT":     {"seed": 20, "first_yield_day": 2, "max_yield_day": 3, "interval": 0, "max_yield": 4, "ongoing": False},
    "TOMATO":     {"seed": 50, "first_yield_day": 8, "max_yield_day": 8, "interval": 1, "max_yield": 4, "ongoing": True},
    "STRAWBERRY": {"seed": 100, "first_yield_day": 10, "max_yield_day": 10, "interval": 2, "max_yield": 4, "ongoing": True},
    "MELON":      {"seed": 80, "first_yield_day": 10, "max_yield_day": 12, "interval": 0, "max_yield": 6, "ongoing": False},
}

ANIMALS = {
    "GOOSE": {"cost": 300, "structure": "COOP",    "first_yield_day": 4, "interval": 1, "max_held": 4, "product": "EGG"},
    "COW":   {"cost": 400, "structure": "PASTURE", "first_yield_day": 8, "interval": 2, "max_held": 6, "product": "MILK"},
    "SHEEP": {"cost": 500, "structure": "PASTURE", "first_yield_day": 6, "interval": 3, "max_held": 6, "product": "WOOL"},
}

PRODUCTS = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER"]

MARKET_I0 = 10000
PRICE_FLOOR = 1

MARKET_PARAMS = {
    "WHEAT":      {"base":  25, "I0": MARKET_I0, "T": 400, "below_func": "sqrt",   "below_target": 0.80, "above_func": "log",    "above_target": 0.20},
    "CARROT":     {"base":  35, "I0": MARKET_I0, "T": 450, "below_func": "log",    "below_target": 0.20, "above_func": "sqrt",   "above_target": 0.70},
    "TOMATO":     {"base":  60, "I0": MARKET_I0, "T": 200, "below_func": "linear", "below_target": 0.40, "above_func": "sqrt",   "above_target": 0.60},
    "STRAWBERRY": {"base": 120, "I0": MARKET_I0, "T": 100, "below_func": "sqrt",   "below_target": 0.70, "above_func": "linear", "above_target": 1.60},
    "MELON":      {"base": 250, "I0": MARKET_I0, "T": 300, "below_func": "log",    "below_target": 0.20, "above_func": "sq",     "above_target": 3.60},
    "EGG":        {"base":  50, "I0": MARKET_I0, "T": 332, "below_func": "linear", "below_target": 0.40, "above_func": "log",    "above_target": 0.20},
    "MILK":       {"base": 160, "I0": MARKET_I0, "T": 122, "below_func": "sqrt",   "below_target": 0.60, "above_func": "linear", "above_target": 1.60},
    "WOOL":       {"base": 200, "I0": MARKET_I0, "T": 105, "below_func": "log",    "below_target": 0.20, "above_func": "sq",     "above_target": 3.20},
    "FERTILIZER": {"base": 100, "I0": MARKET_I0, "T": 200, "below_func": "linear", "below_target": 0.40, "above_func": "linear", "above_target": 0.40},
}

HINGE_GAIN = 8.0

FARMER_MOVES = {"NORTH": (0, -1), "SOUTH": (0, 1), "EAST": (1, 0), "WEST": (-1, 0)}

LAND_ORDER = ["NE", "SW", "SE"]
LAND_PRICES = [1000, 2000, 4000]
FARM_HAND_COST_MULT = 1

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
TOWN_CENTER_PRODUCTS = [p for p in PRODUCTS if p != "FERTILIZER"]
MAX_SHOP_INSTANCES = 8

DEFAULT_CONFIG = {
    "boardSize": 10,
    "startingMoney": 3000,
    "maxMarketOrdersPerTurn": 10,
    "turnsPerDay": 24,
    "shedCapacity": 100,
    "weedSpawnChance": 0.005,
    "townShopUnlockInterval": 3,
    "townShopSellInterval": 4,
    "townCenterSellInterval": 24,
    "farmHandCostMult": 1,
    "episodeSteps": 720,
    "marketParams": None,
}


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


def _resolve_market_params(overrides):
    resolved = {item: dict(p) for item, p in MARKET_PARAMS.items()}
    if not overrides:
        return resolved
    for item, patch in overrides.items():
        if item in resolved and isinstance(patch, dict):
            resolved[item].update(patch)
    return resolved


def market_price(item, inventory, params=None):
    p = (params or MARKET_PARAMS)[item]
    base, I0, T = p["base"], p["I0"], p["T"]
    if inventory < I0:
        f = p["below_func"]
        amp = p["below_target"] * base / _shape(f, T, T)
        price = base + amp * _shape(f, I0 - inventory, T)
    else:
        f = p["above_func"]
        amp = p["above_target"] * base / _shape(f, T, T)
        price = base - amp * _shape(f, inventory - I0, T)
    return max(PRICE_FLOOR, int(round(price)))


def _refresh_prices(market):
    params = market.get("params")
    for item in PRODUCTS:
        market["prices"][item] = market_price(item, market["inventory"][item], params)


def _fib(n):
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def _hire_cost(n_already_today, mult=FARM_HAND_COST_MULT):
    return mult * _fib(n_already_today)


def _quadrant_of(x, y, board_size):
    half = board_size // 2
    return ("N" if y < half else "S") + ("W" if x < half else "E")


def _shed_access_tiles(board_size):
    half = board_size // 2
    return [(half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half)]


def _is_shed_adjacent(pos, board_size):
    return tuple(pos) in {(x, y) for (x, y) in _shed_access_tiles(board_size)}


def _initial_tile(x, y, board_size):
    return None if _quadrant_of(x, y, board_size) == "NW" else "LOCKED"


def _default_spawn(board_size):
    for tile in _shed_access_tiles(board_size):
        if _quadrant_of(tile[0], tile[1], board_size) == "NW":
            return tile
    return (0, 0)


def _new_farm(board_size, starting_money):
    return {
        "money": float(starting_money),
        "tiles": [[_initial_tile(x, y, board_size) for x in range(board_size)]
                  for y in range(board_size)],
        "farmer": list(_default_spawn(board_size)),
        "hands": [],
        "unlocked_quadrants": ["NW"],
        "hires_today": 0,
    }


def _new_private():
    return {
        "shed": {item: 0 for item in PRODUCTS + list(ANIMALS)},
        "seeds": {crop: 0 for crop in CROPS},
        "inventories": [{}],
    }


def _new_market(params=None):
    params = params or MARKET_PARAMS
    inv = {item: params[item]["I0"] for item in PRODUCTS}
    prices = {item: params[item]["base"] for item in PRODUCTS}
    market = {"inventory": inv, "prices": prices}
    if params is not MARKET_PARAMS:
        market["params"] = params
    return market


def _new_plant(crop, day, turns_per_day):
    cd = CROPS[crop]
    return {
        "kind": "PLANT", "crop": crop, "planted_day": day, "watered_today": False,
        "consecutive_unwatered": 1,
        "yield_units": 0 if cd["ongoing"] else 1,
        "max_lifespan_step": (-1 if cd["ongoing"] else (day + cd["max_yield_day"] + 1) * turns_per_day),
        "fertilized_until_day": -1,
    }


def _new_animal(animal, day):
    return {
        "kind": ANIMALS[animal]["structure"], "animal": animal, "placed_day": day,
        "yield_units": 0, "consecutive_unfed": 0, "fed_today": False, "cared_today": False,
        "fertilizer_available": False, "pending_care_bonus": 0,
    }


def _inv_add(inv, item, n=1):
    inv[item] = inv.get(item, 0) + n


def _inv_take(inv, item, n=1):
    if inv.get(item, 0) < n:
        return False
    inv[item] -= n
    if inv[item] == 0:
        del inv[item]
    return True


def _farmer_position(farm, idx):
    if idx == 0:
        return farm["farmer"]
    return farm["hands"][idx - 1] if idx - 1 < len(farm["hands"]) else None


def _set_farmer_position(farm, idx, pos):
    if idx == 0:
        farm["farmer"] = list(pos)
    else:
        farm["hands"][idx - 1] = list(pos)


def _farmer_inventory(private, idx):
    while len(private["inventories"]) <= idx:
        private["inventories"].append({})
    return private["inventories"][idx]


def _apply_unit_action(farm, private, idx, action, board_size, day, turns_per_day, shed_capacity=100):
    if not isinstance(action, list) or not action:
        return
    op = action[0]
    pos = _farmer_position(farm, idx)
    if pos is None:
        return
    fx, fy = pos[0], pos[1]
    inv = _farmer_inventory(private, idx)

    if op in FARMER_MOVES:
        dx, dy = FARMER_MOVES[op]
        nx, ny = fx + dx, fy + dy
        if not (0 <= nx < board_size and 0 <= ny < board_size):
            return
        _set_farmer_position(farm, idx, (nx, ny))
        return

    if op == "PASS":
        return

    tile = farm["tiles"][fy][fx]

    if op == "DROP":
        if not _is_shed_adjacent((fx, fy), board_size):
            return
        shed = private["shed"]
        for item, n in list(inv.items()):
            if n <= 0:
                del inv[item]
                continue
            room = max(0, shed_capacity - sum(shed.values()))
            take = min(n, room)
            if take > 0:
                shed[item] = shed.get(item, 0) + take
            del inv[item]
        return

    if op == "PICKUP":
        if not _is_shed_adjacent((fx, fy), board_size):
            return
        if len(action) < 2:
            return
        item = action[1]
        n = int(action[2]) if len(action) >= 3 else 1
        if n <= 0:
            return
        available = private["shed"].get(item, 0)
        n = min(n, available)
        if n <= 0:
            return
        private["shed"][item] -= n
        _inv_add(inv, item, n)
        return

    if op == "PLACE":
        if len(action) < 2:
            return
        item = action[1]
        if (item in ANIMALS and isinstance(tile, dict)
                and tile.get("kind") == ANIMALS[item]["structure"] and "animal" not in tile):
            if _inv_take(inv, item, 1):
                farm["tiles"][fy][fx] = _new_animal(item, day)
            return
        if _is_shed_adjacent((fx, fy), board_size):
            n = int(action[2]) if len(action) >= 3 else 1
            if n <= 0:
                return
            n = min(n, inv.get(item, 0))
            if n <= 0:
                return
            current = sum(private["shed"].values())
            room = max(0, shed_capacity - current)
            n = min(n, room)
            if n <= 0:
                return
            inv[item] -= n
            if inv[item] == 0:
                del inv[item]
            private["shed"][item] = private["shed"].get(item, 0) + n
        return

    if tile == "LOCKED":
        return

    if op == "PLANT":
        if len(action) < 2:
            return
        crop = action[1]
        if crop not in CROPS:
            return
        if tile is not None:
            return
        if private["seeds"].get(crop, 0) <= 0:
            return
        private["seeds"][crop] -= 1
        farm["tiles"][fy][fx] = _new_plant(crop, day, turns_per_day)
        return

    if op == "WATER":
        if not (isinstance(tile, dict) and tile.get("kind") == "PLANT"):
            return
        if tile["watered_today"]:
            return
        tile["watered_today"] = True
        crop_data = CROPS[tile["crop"]]
        if not crop_data["ongoing"]:
            age_days = day - tile["planted_day"]
            window_start = (crop_data["max_yield_day"] + 1) // 2
            if window_start <= age_days <= crop_data["max_yield_day"]:
                bonus = 2 if tile["fertilized_until_day"] >= day else 1
                tile["yield_units"] = min(crop_data["max_yield"], tile["yield_units"] + bonus)
        return

    if op == "HARVEST":
        if not isinstance(tile, dict):
            return
        if tile.get("yield_units", 0) <= 0:
            return
        if tile.get("kind") == "PLANT":
            crop_data = CROPS[tile["crop"]]
            if day - tile["planted_day"] < crop_data["first_yield_day"]:
                return
            units = tile["yield_units"]
            tile["yield_units"] = 0
            _inv_add(inv, tile["crop"], units)
            if not crop_data["ongoing"]:
                farm["tiles"][fy][fx] = None
        elif "animal" in tile:
            units = tile["yield_units"]
            tile["yield_units"] = 0
            _inv_add(inv, ANIMALS[tile["animal"]]["product"], units)
        return

    if op == "FERTILIZE":
        if not (isinstance(tile, dict) and tile.get("kind") == "PLANT"):
            return
        if not _inv_take(inv, "FERTILIZER", 1):
            return
        tile["fertilized_until_day"] = max(tile.get("fertilized_until_day", -1), day + 2)
        return

    if op == "DIG":
        if tile is None:
            return
        if isinstance(tile, dict) and "animal" in tile:
            return
        farm["tiles"][fy][fx] = None
        return

    if op == "BUILD_COOP":
        if tile is not None:
            return
        farm["tiles"][fy][fx] = {"kind": "COOP"}
        return

    if op == "BUILD_PASTURE":
        if tile is not None:
            return
        farm["tiles"][fy][fx] = {"kind": "PASTURE"}
        return

    if op == "FEED":
        if not (isinstance(tile, dict) and "animal" in tile):
            return
        if tile["fed_today"]:
            return
        if not _inv_take(inv, "WHEAT", 1):
            return
        tile["fed_today"] = True
        return

    if op == "COLLECT_FERTILIZER":
        if not (isinstance(tile, dict) and "animal" in tile):
            return
        if not tile["fertilizer_available"]:
            return
        tile["fertilizer_available"] = False
        _inv_add(inv, "FERTILIZER", 1)
        return

    if op == "CARE":
        if not (isinstance(tile, dict) and "animal" in tile):
            return
        if tile["cared_today"]:
            return
        tile["cared_today"] = True
        return


def _spawn_hand(farm, board_size):
    occupants = {tile: 0 for tile in _shed_access_tiles(board_size)}
    all_pos = [tuple(farm["farmer"])] + [tuple(p) for p in farm["hands"]]
    for pos in all_pos:
        if pos in occupants:
            occupants[pos] += 1
    tiles = _shed_access_tiles(board_size)
    best = sorted(occupants.items(), key=lambda kv: (kv[1], tiles.index(kv[0])))
    return list(best[0][0])


def _parse_order(order):
    if not isinstance(order, list) or not order:
        return None
    op = order[0]
    if op == "HIRE":
        return {"type": "HIRE"}
    if op == "BUY_LAND":
        return {"type": "BUY_LAND"}
    if op in ("BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "SELL"):
        if len(order) < 3:
            return None
        try:
            n = int(order[2])
        except (TypeError, ValueError):
            return None
        if n <= 0:
            return None
        return {"type": op, "item": order[1], "remaining": n}
    return None


def _commit_unit(op, item, price, farm, private, market, shed_capacity=100):
    if op == "SELL":
        if private["shed"].get(item, 0) <= 0:
            return False
        private["shed"][item] -= 1
        farm["money"] += price
        if price > 1:
            market["inventory"][item] += 1
        return True
    if op == "BUY_PRODUCT":
        if farm["money"] < price:
            return False
        if sum(private["shed"].values()) >= shed_capacity:
            return False
        farm["money"] -= price
        private["shed"][item] = private["shed"].get(item, 0) + 1
        market["inventory"][item] -= 1
        return True
    if op == "BUY_SEED":
        if farm["money"] < price:
            return False
        farm["money"] -= price
        private["seeds"][item] = private["seeds"].get(item, 0) + 1
        return True
    if op == "BUY_ANIMAL":
        if farm["money"] < price:
            return False
        if sum(private["shed"].values()) >= shed_capacity:
            return False
        farm["money"] -= price
        private["shed"][item] = private["shed"].get(item, 0) + 1
        return True
    return False


def _do_hire(farm, private, board_size, mult=FARM_HAND_COST_MULT):
    cost = _hire_cost(farm["hires_today"], mult)
    if farm["money"] < cost:
        return
    farm["money"] -= cost
    farm["hires_today"] += 1
    farm["hands"].append(_spawn_hand(farm, board_size))
    private["inventories"].append({})


def _do_buy_land(farm, board_size):
    n_unlocked_extra = len(farm["unlocked_quadrants"]) - 1
    if n_unlocked_extra >= len(LAND_ORDER):
        return
    cost = LAND_PRICES[n_unlocked_extra]
    if farm["money"] < cost:
        return
    farm["money"] -= cost
    quadrant = LAND_ORDER[n_unlocked_extra]
    farm["unlocked_quadrants"].append(quadrant)
    for y in range(board_size):
        for x in range(board_size):
            if _quadrant_of(x, y, board_size) == quadrant and farm["tiles"][y][x] == "LOCKED":
                farm["tiles"][y][x] = None


def _process_market(farms, privates, market, actions, board_size, max_orders, hire_mult, shed_capacity, on_commit=None):
    queues = []
    for a in actions:
        m = (a or {}).get("market", []) if isinstance(a, dict) else []
        q = list(m) if isinstance(m, list) else []
        queues.append(q[:max_orders])

    max_len = max((len(q) for q in queues), default=0)
    for i in range(max_len):
        order_states = []
        for player_id, q in enumerate(queues):
            ostate = _parse_order(q[i]) if i < len(q) else None
            order_states.append(ostate)

        for player_id, ostate in enumerate(order_states):
            if ostate is None:
                continue
            op = ostate["type"]
            if op == "HIRE":
                _do_hire(farms[player_id], privates[player_id], board_size, hire_mult)
                order_states[player_id] = None
            elif op == "BUY_LAND":
                _do_buy_land(farms[player_id], board_size)
                order_states[player_id] = None

        idx_esc = 0
        while True:
            idx_esc += 1
            if idx_esc >= 100_000:
                break
            quoted = [None, None]
            for player_id, ostate in enumerate(order_states):
                if ostate is None or ostate["remaining"] <= 0:
                    continue
                op = ostate["type"]
                item = ostate["item"]
                if op == "SELL" and item in PRODUCTS:
                    quoted[player_id] = ("SELL", item, market_price(item, market["inventory"][item], market.get("params")), ostate)
                elif op == "BUY_PRODUCT" and item in ("WHEAT", "FERTILIZER"):
                    quoted[player_id] = ("BUY_PRODUCT", item, market_price(item, market["inventory"][item] - 1, market.get("params")), ostate)
                elif op == "BUY_SEED" and item in CROPS:
                    quoted[player_id] = ("BUY_SEED", item, CROPS[item]["seed"], ostate)
                elif op == "BUY_ANIMAL" and item in ANIMALS:
                    quoted[player_id] = ("BUY_ANIMAL", item, ANIMALS[item]["cost"], ostate)
                else:
                    order_states[player_id] = None

            if all(q is None for q in quoted):
                break

            committed_any = False
            for player_id, q in enumerate(quoted):
                if q is None:
                    continue
                op, item, price, ostate = q
                ok = _commit_unit(op, item, price, farms[player_id], privates[player_id], market, shed_capacity)
                if ok:
                    if on_commit is not None:
                        on_commit(player_id, op, item, price)
                    ostate["remaining"] -= 1
                    committed_any = True
                else:
                    order_states[player_id] = None

            if not committed_any:
                break

        _refresh_prices(market)


def _town_take(item, step, shops, shop_interval, center_interval):
    take = 1 if item != "FERTILIZER" and step % center_interval == 0 else 0
    if step % shop_interval == 0:
        for shop_name in shops:
            products = SHOPS.get(shop_name, ())
            multiplier = 2 if len(products) == 1 else 1
            if item in products:
                take += multiplier
    return take


def _town_consume(market, town, step, shop_interval, center_interval):
    if step % shop_interval == 0:
        for shop_name in town.get("unlocked_shops", []):
            products = SHOPS[shop_name]
            multiplier = 2 if len(products) == 1 else 1
            for item in products:
                market["inventory"][item] -= multiplier
    if step % center_interval == 0:
        for item in TOWN_CENTER_PRODUCTS:
            market["inventory"][item] -= 1
    _refresh_prices(market)


def _decay_plants(farm, step):
    board_size = len(farm["tiles"])
    for y in range(board_size):
        for x in range(board_size):
            tile = farm["tiles"][y][x]
            if not isinstance(tile, dict) or tile.get("kind") != "PLANT":
                continue
            mls = tile["max_lifespan_step"]
            if mls < 0 or step < mls:
                continue
            if (step - mls) % 2 != 0:
                continue
            tile["yield_units"] -= 1
            if tile["yield_units"] <= 0:
                farm["tiles"][y][x] = {"kind": "WEED"}


def _daily_refresh_plants(farm, current_day, turns_per_day):
    board_size = len(farm["tiles"])
    next_day = current_day + 1
    for y in range(board_size):
        for x in range(board_size):
            tile = farm["tiles"][y][x]
            if not isinstance(tile, dict) or tile.get("kind") != "PLANT":
                continue
            was_watered = tile["watered_today"]
            if was_watered:
                tile["consecutive_unwatered"] = 0
            else:
                tile["consecutive_unwatered"] += 1
            tile["watered_today"] = False
            if tile["consecutive_unwatered"] >= 2:
                farm["tiles"][y][x] = {"kind": "WEED"}
                continue
            cd = CROPS[tile["crop"]]
            if not cd["ongoing"]:
                continue
            days_since_first = next_day - tile["planted_day"] - cd["first_yield_day"]
            if days_since_first < 0:
                continue
            interval = cd["interval"]
            if days_since_first % interval != 0:
                continue
            production_count = days_since_first // interval + 1
            if production_count > cd["max_yield"]:
                continue
            fertilized = was_watered and tile.get("fertilized_until_day", -1) >= current_day
            tile["yield_units"] = min(cd["max_yield"], tile["yield_units"] + (2 if fertilized else 1))
            if production_count == cd["max_yield"]:
                tile["max_lifespan_step"] = (next_day + 1) * turns_per_day


def _daily_refresh_animals(farm, day):
    board_size = len(farm["tiles"])
    next_day = day + 1
    for y in range(board_size):
        for x in range(board_size):
            tile = farm["tiles"][y][x]
            if not (isinstance(tile, dict) and "animal" in tile):
                continue
            if tile["fed_today"]:
                tile["consecutive_unfed"] = 0
            else:
                tile["consecutive_unfed"] += 1
            if tile["consecutive_unfed"] >= 2:
                farm["tiles"][y][x] = {"kind": ANIMALS[tile["animal"]]["structure"]}
                continue
            a = ANIMALS[tile["animal"]]
            days_since_first = next_day - tile["placed_day"] - a["first_yield_day"]
            if days_since_first >= 0 and days_since_first % a["interval"] == 0:
                base = 1
                bonus = tile.pop("pending_care_bonus", 0) if tile["fed_today"] else 0
                tile["yield_units"] = min(a["max_held"], tile["yield_units"] + base + bonus)
                tile["pending_care_bonus"] = 0
            if tile["cared_today"] and tile["fed_today"]:
                tile["pending_care_bonus"] = tile.get("pending_care_bonus", 0) + 1
            tile["fertilizer_available"] = True
            tile["fed_today"] = False
            tile["cared_today"] = False


def _spawn_weeds(farm, board_size, weed_chance, rng):
    for y in range(board_size):
        for x in range(board_size):
            if farm["tiles"][y][x] is None and rng.random() < weed_chance:
                farm["tiles"][y][x] = {"kind": "WEED"}


def _drop_inventories_to_shed(private, capacity):
    shed = private["shed"]
    for inv in private["inventories"]:
        for item, n in list(inv.items()):
            if n <= 0:
                del inv[item]
                continue
            current = sum(v for k, v in shed.items())
            room = max(0, capacity - current)
            take = min(n, room)
            if take > 0:
                shed[item] = shed.get(item, 0) + take
            del inv[item]


class Simulator:
    """Steps two players' actions through the exact engine mechanics.

    Construct with `Simulator.from_observation(obs, opp_private=None, seed=...)`
    when bootstrapping mid-game from a live obs (planner rollouts -- the
    opponent's private shed/seeds are not visible in a real obs, so rollouts
    treat them as unknown/zero unless supplied), or `Simulator.new_episode(...)`
    to run a full game from day 0 (self-play data generation).
    """

    __slots__ = ("cfg", "farms", "privates", "market", "town", "step", "seed",
                 "board_size", "turns_per_day", "on_commit")

    def __init__(self, cfg, farms, privates, market, town, step, seed):
        self.cfg = cfg
        self.farms = farms
        self.privates = privates
        self.market = market
        self.town = town
        self.step = step
        self.seed = seed
        self.board_size = int(cfg.get("boardSize", 10))
        self.turns_per_day = max(1, int(cfg.get("turnsPerDay", 24)))
        # Optional (player_id, op, item, price) callback fired on every
        # SUCCESSFUL unit commit. The engine fills an order one unit at a time
        # down a moving price curve, so quantity*opening_price overstates
        # realised revenue badly on large orders -- this is the only exact way
        # to attribute money to products.
        self.on_commit = None

    # ------------------------------------------------------------- factories
    @classmethod
    def new_episode(cls, configuration=None, seed=0):
        cfg = dict(DEFAULT_CONFIG)
        cfg.update(configuration or {})
        board_size = int(cfg["boardSize"])
        starting_money = int(cfg["startingMoney"])
        market_overrides = cfg.get("marketParams")
        params = _resolve_market_params(market_overrides) if market_overrides else None
        farms = [_new_farm(board_size, starting_money) for _ in range(2)]
        privates = [_new_private() for _ in range(2)]
        market = _new_market(params)
        town = {"unlocked_shops": []}
        return cls(cfg, farms, privates, market, town, 0, seed)

    @classmethod
    def from_observation(cls, obs, opp_private=None, configuration=None, seed=0):
        """Bootstrap from a live obs dict. `obs['private']` is only the caller's
        own private state (as in a real game); pass `opp_private` if it is
        separately known (e.g. postmortem analysis with a full replay)."""
        cfg = dict(DEFAULT_CONFIG)
        cfg.update(configuration or {})
        player = int(obs.get("player", 0))
        farms = [_deepcopy_farm(f) for f in obs["farms"]]
        own_private = _deepcopy_private(obs["private"])
        other_private = _deepcopy_private(opp_private) if opp_private else _new_private()
        privates = [None, None]
        privates[player] = own_private
        privates[1 - player] = other_private
        market = _deepcopy_market(obs["market"])
        market_overrides = cfg.get("marketParams")
        if market_overrides:
            market["params"] = _resolve_market_params(market_overrides)
        town = {"unlocked_shops": list((obs.get("town") or {}).get("unlocked_shops") or [])}
        step = int(obs.get("day", 0)) * cfg["turnsPerDay"] + int(obs.get("hour", 0))
        return cls(cfg, farms, privates, market, town, step, seed)

    def clone(self):
        return Simulator(dict(self.cfg), [_deepcopy_farm(f) for f in self.farms],
                          [_deepcopy_private(p) for p in self.privates],
                          _deepcopy_market(self.market),
                          {"unlocked_shops": list(self.town["unlocked_shops"])},
                          self.step, self.seed)

    # ------------------------------------------------------------ obs export
    @property
    def day(self):
        return self.step // self.turns_per_day

    @property
    def hour(self):
        return self.step % self.turns_per_day

    def observation_for(self, player):
        return {
            "day": self.day, "hour": self.hour, "step": self.step, "player": player,
            "farms": self.farms, "market": self.market, "town": self.town,
            "private": self.privates[player],
        }

    # ------------------------------------------------------------------ step
    def step_actions(self, action0, action1):
        """Apply one turn's actions (both players) and advance by one step."""
        cur_step = self.step
        day = cur_step // self.turns_per_day
        board_size = self.board_size
        turns_per_day = self.turns_per_day
        shed_capacity = int(self.cfg["shedCapacity"])
        max_orders = max(1, int(self.cfg["maxMarketOrdersPerTurn"]))
        hire_mult = int(self.cfg["farmHandCostMult"])
        shop_interval = max(1, int(self.cfg["townShopSellInterval"]))
        center_interval = max(1, int(self.cfg["townCenterSellInterval"]))

        actions = [action0, action1]
        for i, action in enumerate(actions):
            farmer_action = (action or {}).get("farmer", ["PASS"]) if isinstance(action, dict) else ["PASS"]
            hands_actions = (action or {}).get("hands", []) if isinstance(action, dict) else []
            if not isinstance(hands_actions, list):
                hands_actions = []

            unit_actions = [farmer_action, *hands_actions]
            plant_demand = {}
            for a in unit_actions:
                if isinstance(a, list) and len(a) >= 2 and a[0] == "PLANT":
                    plant_demand[a[1]] = plant_demand.get(a[1], 0) + 1
            seeds = self.privates[i].get("seeds", {})
            blocked = {crop for crop, n in plant_demand.items() if n > seeds.get(crop, 0)}

            def _allowed(a):
                if isinstance(a, list) and len(a) >= 2 and a[0] == "PLANT" and a[1] in blocked:
                    return ["PASS"]
                return a

            _apply_unit_action(self.farms[i], self.privates[i], 0, _allowed(farmer_action),
                                board_size, day, turns_per_day, shed_capacity)
            for h_idx, hand_action in enumerate(hands_actions):
                _apply_unit_action(self.farms[i], self.privates[i], h_idx + 1,
                                    _allowed(hand_action), board_size, day, turns_per_day, shed_capacity)

        _process_market(self.farms, self.privates, self.market, actions,
                         board_size, max_orders, hire_mult, shed_capacity,
                         on_commit=self.on_commit)
        _town_consume(self.market, self.town, cur_step, shop_interval, center_interval)
        for farm in self.farms:
            _decay_plants(farm, cur_step)

        if (cur_step + 1) % turns_per_day == 0:
            self._end_of_day(day)

        self.step = cur_step + 1

    def _end_of_day(self, day):
        board_size = self.board_size
        turns_per_day = self.turns_per_day
        weed_chance = float(self.cfg["weedSpawnChance"])
        shed_cap = int(self.cfg["shedCapacity"])
        shop_unlock_interval = max(1, int(self.cfg["townShopUnlockInterval"]))

        rng = random.Random((self.seed * 1_000_003) ^ day)

        for player_id, farm in enumerate(self.farms):
            private = self.privates[player_id]
            _daily_refresh_plants(farm, day, turns_per_day)
            _daily_refresh_animals(farm, day)
            _spawn_weeds(farm, board_size, weed_chance, rng)
            _drop_inventories_to_shed(private, shed_cap)
            farm["farmer"] = list(_default_spawn(board_size))
            farm["hands"] = []
            farm["hires_today"] = 0
            private["inventories"] = [{}]

        next_day = day + 1
        if next_day > 0 and next_day % shop_unlock_interval == 0:
            if len(self.town["unlocked_shops"]) < MAX_SHOP_INSTANCES:
                self.town["unlocked_shops"].append(rng.choice(sorted(SHOPS)))

    def is_done(self):
        return self.step >= int(self.cfg["episodeSteps"]) - 1

    def run_episode(self, agent0, agent1, max_steps=None):
        """Drive both agent functions to the end of the season.
        Returns (money0, money1).

        A real episode of `episodeSteps` recorded observations applies exactly
        `episodeSteps - 1` actions (index 0 is the untouched initial state --
        see planner/tests/test_sim_fidelity.py and HANDOFF's "actions live at
        steps[1:]"). One call too many here double-fires the final day's
        end-of-day refresh and was verified to cost ~600 in a real matchup.

        Agents are invoked exactly the way kaggle_environments does it
        (agent.py:169-172): the arg list is [observation, configuration]
        truncated to the callable's own `co_argcount`. 5 of the 9 reference
        agents are declared `agent(obs, config=None)`, so calling them with
        obs alone silently ran them on their hardcoded fallback constants
        instead of the episode's real config -- htdc-v12, for instance,
        falls back to FARM_HAND_COST_MULT=10 against a real value of 1, a
        10x error in its hiring economics."""
        limit = (int(self.cfg["episodeSteps"]) - 1) if max_steps is None else max_steps
        call0 = _agent_caller(agent0)
        call1 = _agent_caller(agent1)
        while self.step < limit:
            a0 = call0(self.observation_for(0), self.cfg)
            a1 = call1(self.observation_for(1), self.cfg)
            self.step_actions(a0, a1)
        return self.farms[0]["money"], self.farms[1]["money"]


def _deepcopy_farm(f):
    return {
        "money": float(f["money"]),
        "tiles": [[(dict(t) if isinstance(t, dict) else t) for t in row] for row in f["tiles"]],
        "farmer": list(f["farmer"]),
        "hands": [list(h) for h in f["hands"]],
        "unlocked_quadrants": list(f["unlocked_quadrants"]),
        "hires_today": int(f["hires_today"]),
    }


def _deepcopy_private(p):
    return {
        "shed": dict(p.get("shed") or {}),
        "seeds": dict(p.get("seeds") or {}),
        "inventories": [dict(iv) for iv in (p.get("inventories") or [{}])],
    }


def _deepcopy_market(m):
    out = {"inventory": dict(m["inventory"]), "prices": dict(m["prices"])}
    if "params" in m:
        out["params"] = m["params"]
    return out


def _agent_caller(agent):
    """Return a (obs, config) -> action wrapper that invokes `agent` with the
    same argument count kaggle_environments would use.

    Mirrors kaggle_environments/agent.py:169-172:
        args = [observation, configuration][:agent.__code__.co_argcount]
    Callables without a __code__ (builtins, C functions, some partials) get
    obs only, which is what the harness's `callable(agent)` fallback does.
    """
    code = getattr(agent, "__code__", None)
    if code is None:
        inner = getattr(agent, "__call__", None)
        code = getattr(inner, "__code__", None)
        # bound __call__ counts `self`; drop it to match the free-function case
        argcount = (code.co_argcount - 1) if code is not None else 1
    else:
        argcount = code.co_argcount
    if argcount >= 2:
        return lambda obs, cfg: agent(obs, cfg)
    return lambda obs, cfg: agent(obs)
