"""Module 1 of 6 -- STATE EXTRACTOR.

One job: turn whatever `kaggle_environments` hands the agent into a plain,
immutable snapshot of the things a decision actually needs. Nothing downstream
touches `obs` again.

WHY THIS IS A MODULE AND NOT THREE LINES AT THE TOP OF THE AGENT. HANDOFF
section 5: `kaggle_environments` STRUCTIFIES the observation, so `obs["farms"]`
is sometimes a dict and sometimes an attribute-bearing Struct, and
`farm is obs["farms"][0]` is false even when it is the same farm. Every place
that reads `obs` directly is a place that can silently read the wrong seat. One
extractor, one set of `_get` calls, everything below it works on plain dicts.

WHAT IS AND IS NOT OBSERVABLE. `farms` carries BOTH players' public farms --
tiles, farmer and hand positions, money, hires_today, unlocked quadrants -- so
the opponent's animals, crops and crew are readable and their SHED IS NOT.
`private` is ours alone. This asymmetry is the whole basis of the opponent
model: their standing animals are visible, their stock is not, and section 22's
suppression math lives on exactly that boundary.
"""

import copy

PRODUCTS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
            "EGG", "MILK", "WOOL", "FERTILIZER")
ANIMAL_KINDS = ("GOOSE", "COW", "SHEEP")
CROP_KINDS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON")
TURNS_PER_DAY = 24
LAST_STEP = 718            # actions live at steps[1:], so 718 is the last one


def _get(d, key, default=None):
    if d is None:
        return default
    if isinstance(d, dict):
        return d.get(key, default)
    return getattr(d, key, default)


def _num(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


class FarmView:
    """One player's public farm, as plain data."""

    __slots__ = ("money", "tiles", "farmer", "hands", "hires_today",
                 "unlocked", "animals", "crops", "weeds", "empty")

    def __init__(self, farm):
        self.money = float(_get(farm, "money", 0) or 0)
        self.tiles = _get(farm, "tiles", []) or []
        self.farmer = tuple(_get(farm, "farmer", (4, 4)) or (4, 4))
        self.hands = [tuple(h) for h in (_get(farm, "hands", []) or [])]
        self.hires_today = _num(_get(farm, "hires_today", 0))
        self.unlocked = list(_get(farm, "unlocked_quadrants", ["NW"]) or ["NW"])
        self.animals = {}      # (x, y) -> tile dict, animal standing on it
        self.crops = {}        # (x, y) -> tile dict, crop growing on it
        self.weeds = []
        self.empty = []
        for y, row in enumerate(self.tiles):
            for x, t in enumerate(row):
                if t is None:
                    self.empty.append((x, y))
                elif isinstance(t, dict):
                    if "animal" in t:
                        self.animals[(x, y)] = t
                    elif t.get("kind") == "PLANT":
                        self.crops[(x, y)] = t
                    elif t.get("kind") == "WEED":
                        self.weeds.append((x, y))

    @property
    def workers(self):
        """Farmer plus today's hands. Hands are cleared every night, so this is
        a per-day quantity and is floored at 1, never 0."""
        return 1 + len(self.hands)

    def animal_counts(self):
        out = {k: 0 for k in ANIMAL_KINDS}
        for t in self.animals.values():
            k = t.get("animal")
            if k in out:
                out[k] += 1
        return out

    def standing_yield(self):
        """Product units sitting on animals, waiting to be picked up."""
        return sum(_num(t.get("yield_units")) for t in self.animals.values())


class Snapshot:
    """Everything the five downstream modules are allowed to look at."""

    __slots__ = ("step", "day", "hour", "seat", "me", "opp", "shed", "seeds",
                 "inventories", "market_inv", "market_prices", "shops",
                 "board", "config", "allow_productive_shed_tiles")

    def __init__(self, obs, config=None):
        self.config = config
        self.allow_productive_shed_tiles = False
        self.step = _num(_get(obs, "step", 0))
        if not self.step:
            self.step = _num(_get(obs, "day", 0)) * TURNS_PER_DAY + _num(_get(obs, "hour", 0))
        self.day = self.step // TURNS_PER_DAY
        self.hour = self.step % TURNS_PER_DAY
        self.seat = _num(_get(obs, "player", 0))
        farms = _get(obs, "farms", []) or []
        self.me = FarmView(farms[self.seat] if self.seat < len(farms) else None)
        self.opp = FarmView(farms[1 - self.seat] if len(farms) > 1 else None)
        private = _get(obs, "private", {}) or {}
        self.shed = dict(_get(private, "shed", {}) or {})
        self.seeds = dict(_get(private, "seeds", {}) or {})
        # inventories[0] is the farmer; hand i is inventories[i + 1].
        self.inventories = [dict(iv or {}) for iv in
                            (_get(private, "inventories", []) or [{}])]
        market = _get(obs, "market", {}) or {}
        self.market_inv = dict(_get(market, "inventory", {}) or {})
        self.market_prices = dict(_get(market, "prices", {}) or {})
        town = _get(obs, "town", {}) or {}
        self.shops = tuple(_get(town, "unlocked_shops", ()) or ())
        self.board = len(self.me.tiles) or 10

    # -------------------------------------------------------------- derived

    @property
    def steps_left(self):
        return max(0, LAST_STEP - self.step)

    @property
    def days_left(self):
        return max(0, (LAST_STEP - self.step) // TURNS_PER_DAY)

    @property
    def shed_used(self):
        return sum(_num(v) for v in self.shed.values())

    @property
    def shed_room(self):
        return max(0, 100 - self.shed_used)

    def carried(self):
        """{item: n} held by units and NOT yet in the shed.

        The distinction is load-bearing (HANDOFF rule 5): `SELL` draws from the
        shed only, so anything in here is unsellable until a `DROP`.
        """
        out = {}
        for iv in self.inventories:
            for k, v in iv.items():
                n = _num(v)
                if n:
                    out[k] = out.get(k, 0) + n
        return out


def extract(obs, config=None):
    return Snapshot(obs, config)


# ------------------------------------------------------ exact phase projection

_MOVES = {
    "NORTH": (0, -1), "SOUTH": (0, 1),
    "WEST": (-1, 0), "EAST": (1, 0),
}


def _shed_access(board):
    half = int(board) // 2
    return {(half - 1, half - 1), (half, half - 1),
            (half - 1, half), (half, half)}


def _inv_take(inventory, item, quantity=1):
    quantity = int(quantity)
    if int(inventory.get(item, 0) or 0) < quantity:
        return False
    inventory[item] = int(inventory[item]) - quantity
    if inventory[item] == 0:
        del inventory[item]
    return True


def _new_plant(crop, day, turns_per_day, crop_rule):
    return {
        "kind": "PLANT", "crop": crop, "planted_day": int(day),
        "watered_today": False, "consecutive_unwatered": 1,
        "yield_units": 0 if crop_rule["ongoing"] else 1,
        "max_lifespan_step": (
            -1 if crop_rule["ongoing"]
            else (int(day) + crop_rule["max_yield_day"] + 1)
            * int(turns_per_day)
        ),
        "fertilized_until_day": -1,
    }


def _new_animal(animal, day, animal_rule):
    return {
        "kind": animal_rule["structure"], "animal": animal,
        "placed_day": int(day), "yield_units": 0,
        "consecutive_unfed": 0, "fed_today": False,
        "cared_today": False, "fertilizer_available": False,
        "pending_care_bonus": 0,
    }


def project_unit_phase(snap, unit_actions):
    """Return the exact own state after the already-chosen unit phase.

    Kaggriculture resolves the farmer and then each hand before processing any
    market order.  Capital bought in that market phase therefore sees these
    positions, tiles and private stocks and cannot use the action just spent.
    This deterministic transition copies the engine equations; it does not
    advance the public clock, market, town, plant decay or daily refresh.

    PLANT has one batch precondition outside the per-unit transition: if total
    same-crop demand exceeds the seed stock at phase start, every request for
    that crop is rejected.  All other operations are sequential and can see a
    previous unit's mutation of a shared tile or shed.
    """
    from whitebox import econ

    actions = [list(action) if isinstance(action, (list, tuple)) else []
               for action in (unit_actions or ())]
    farm = {
        "money": float(snap.me.money),
        "tiles": copy.deepcopy(snap.me.tiles),
        "farmer": list(snap.me.farmer),
        "hands": [list(pos) for pos in snap.me.hands],
        "hires_today": int(snap.me.hires_today),
        "unlocked_quadrants": list(snap.me.unlocked),
    }
    shed = {item: int(qty or 0) for item, qty in snap.shed.items()}
    seeds = {item: int(qty or 0) for item, qty in snap.seeds.items()}
    inventories = [dict(inventory or {}) for inventory in snap.inventories]
    workers = 1 + len(farm["hands"])
    while len(inventories) < workers:
        inventories.append({})

    demand = {}
    for action in actions[:workers]:
        if len(action) >= 2 and action[0] == "PLANT":
            demand[action[1]] = demand.get(action[1], 0) + 1
    blocked_crops = {
        crop for crop, quantity in demand.items()
        if quantity > int(seeds.get(crop, 0) or 0)
    }

    board = max(1, int(snap.board))
    access = _shed_access(board)
    turns_per_day = max(
        1, _num(_get(snap.config, "turnsPerDay", econ.TURNS_PER_DAY),
                econ.TURNS_PER_DAY),
    )
    shed_capacity = max(
        0, _num(_get(snap.config, "shedCapacity", econ.SHED_CAPACITY),
                econ.SHED_CAPACITY),
    )

    def position(index):
        return farm["farmer"] if index == 0 else farm["hands"][index - 1]

    def set_position(index, pos):
        if index == 0:
            farm["farmer"] = list(pos)
        else:
            farm["hands"][index - 1] = list(pos)

    for index in range(workers):
        action = actions[index] if index < len(actions) else []
        if not action:
            continue
        op = action[0]
        if op == "PLANT" and len(action) >= 2 and action[1] in blocked_crops:
            continue
        pos = position(index)
        x, y = int(pos[0]), int(pos[1])
        inventory = inventories[index]

        if op in _MOVES:
            dx, dy = _MOVES[op]
            nxt = (x + dx, y + dy)
            if 0 <= nxt[0] < board and 0 <= nxt[1] < board:
                set_position(index, nxt)
            continue
        if op == "PASS":
            continue

        tile = farm["tiles"][y][x]
        if op == "DROP":
            if (x, y) not in access:
                continue
            for item, raw_quantity in list(inventory.items()):
                quantity = int(raw_quantity or 0)
                if quantity > 0:
                    room = max(0, shed_capacity - sum(shed.values()))
                    take = min(quantity, room)
                    if take > 0:
                        shed[item] = int(shed.get(item, 0) or 0) + take
                del inventory[item]
            continue
        if op == "PICKUP":
            if (x, y) not in access or len(action) < 2:
                continue
            item = action[1]
            quantity = int(action[2]) if len(action) >= 3 else 1
            quantity = min(quantity, int(shed.get(item, 0) or 0))
            if quantity > 0:
                shed[item] = int(shed.get(item, 0) or 0) - quantity
                inventory[item] = int(inventory.get(item, 0) or 0) + quantity
            continue
        if op == "PLACE":
            if len(action) < 2:
                continue
            item = action[1]
            animal_rule = econ.ANIMALS.get(item)
            if (animal_rule is not None and isinstance(tile, dict)
                    and tile.get("kind") == animal_rule["structure"]
                    and "animal" not in tile):
                if _inv_take(inventory, item):
                    farm["tiles"][y][x] = _new_animal(
                        item, snap.day, animal_rule,
                    )
                continue
            if (x, y) in access:
                quantity = int(action[2]) if len(action) >= 3 else 1
                quantity = min(quantity, int(inventory.get(item, 0) or 0))
                room = max(0, shed_capacity - sum(shed.values()))
                quantity = min(quantity, room)
                if quantity > 0:
                    _inv_take(inventory, item, quantity)
                    shed[item] = int(shed.get(item, 0) or 0) + quantity
            continue
        if tile == "LOCKED":
            continue
        if op == "PLANT":
            if len(action) < 2 or tile is not None:
                continue
            crop = action[1]
            crop_rule = econ.CROPS.get(crop)
            if crop_rule is None or int(seeds.get(crop, 0) or 0) <= 0:
                continue
            seeds[crop] = int(seeds[crop]) - 1
            farm["tiles"][y][x] = _new_plant(
                crop, snap.day, turns_per_day, crop_rule,
            )
            continue
        if op == "WATER":
            if (not isinstance(tile, dict) or tile.get("kind") != "PLANT"
                    or tile.get("watered_today")):
                continue
            tile["watered_today"] = True
            crop_rule = econ.CROPS[tile["crop"]]
            if not crop_rule["ongoing"]:
                age = int(snap.day) - int(tile["planted_day"])
                start = (crop_rule["max_yield_day"] + 1) // 2
                if start <= age <= crop_rule["max_yield_day"]:
                    bonus = (2 if int(tile.get("fertilized_until_day", -1))
                              >= int(snap.day) else 1)
                    tile["yield_units"] = min(
                        crop_rule["max_yield"],
                        int(tile.get("yield_units", 0) or 0) + bonus,
                    )
            continue
        if op == "HARVEST":
            if not isinstance(tile, dict) or int(tile.get("yield_units", 0) or 0) <= 0:
                continue
            if tile.get("kind") == "PLANT":
                crop_rule = econ.CROPS[tile["crop"]]
                if int(snap.day) - int(tile["planted_day"]) < crop_rule["first_yield_day"]:
                    continue
                quantity = int(tile["yield_units"])
                inventory[tile["crop"]] = int(inventory.get(tile["crop"], 0) or 0) + quantity
                tile["yield_units"] = 0
                if not crop_rule["ongoing"]:
                    farm["tiles"][y][x] = None
            elif "animal" in tile:
                quantity = int(tile["yield_units"])
                product = econ.ANIMALS[tile["animal"]]["product"]
                inventory[product] = int(inventory.get(product, 0) or 0) + quantity
                tile["yield_units"] = 0
            continue
        if op == "FERTILIZE":
            if (isinstance(tile, dict) and tile.get("kind") == "PLANT"
                    and _inv_take(inventory, "FERTILIZER")):
                tile["fertilized_until_day"] = max(
                    int(tile.get("fertilized_until_day", -1)),
                    int(snap.day) + 2,
                )
            continue
        if op == "DIG":
            if tile is not None and not (isinstance(tile, dict) and "animal" in tile):
                farm["tiles"][y][x] = None
            continue
        if op in ("BUILD_COOP", "BUILD_PASTURE"):
            if tile is None:
                farm["tiles"][y][x] = {
                    "kind": "COOP" if op == "BUILD_COOP" else "PASTURE",
                }
            continue
        if op == "FEED":
            if (isinstance(tile, dict) and "animal" in tile
                    and not tile.get("fed_today")
                    and _inv_take(inventory, "WHEAT")):
                tile["fed_today"] = True
            continue
        if op == "COLLECT_FERTILIZER":
            if (isinstance(tile, dict) and "animal" in tile
                    and tile.get("fertilizer_available")):
                tile["fertilizer_available"] = False
                inventory["FERTILIZER"] = int(inventory.get("FERTILIZER", 0) or 0) + 1
            continue
        if op == "CARE":
            if (isinstance(tile, dict) and "animal" in tile
                    and not tile.get("cared_today")):
                tile["cared_today"] = True

    projected = copy.copy(snap)
    projected.me = FarmView(farm)
    projected.shed = shed
    projected.seeds = seeds
    projected.inventories = inventories
    return projected


# --------------------------------------------------------------- opponent model

_SHOPS = {
    "BAKERY": ("EGG", "WHEAT"), "PIZZA_SHOP": ("MILK", "TOMATO", "WHEAT"),
    "BRUNCH_SPOT": ("EGG", "WHEAT", "STRAWBERRY"), "YARN_STORE": ("WOOL",),
    "ICE_CREAM_SHOP": ("STRAWBERRY", "MILK", "WHEAT"), "PET_CAFE": ("CARROT",),
    "SMOOTHIE_SHOP": ("STRAWBERRY", "MILK"),
    "FARMERS_MARKET": ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY"),
}
_ANIMAL_PRODUCT = {"GOOSE": "EGG", "COW": "MILK", "SHEEP": "WOOL"}


def town_take(item, step, shops):
    """Units the town removes from the market at `step`. Fully determined."""
    take = 1 if item != "FERTILIZER" and step % 24 == 0 else 0
    if step % 4 == 0:
        for s in shops:
            prods = _SHOPS.get(s, ())
            if item in prods:
                take += 2 if len(prods) == 1 else 1
    return take


class OpponentTracker:
    """Running estimate of what the opponent HOLDS, from public state only.

    Their shed is not in the observation. Their holdings are still recoverable,
    because both of the flows into and out of it are:

      OUT -- sales are EXACT (HANDOFF section 6). Within a step the engine
             settles both players' orders and then the town's consumption, so
             `inv[t+1] = inv[t] + my_sales + their_sales - town_take`, and every
             term but theirs is known. This nets buys automatically: a
             BUY_PRODUCT lowers the inventory, so it shows up as a negative
             sale, which is exactly its effect on their holdings.

      IN  -- harvests are read off their tiles. `yield_units` only falls for two
             reasons: they harvested it, or `_decay_plants` took one. Decay is
             not a guess -- it fires only on PLANT tiles at `step >=
             max_lifespan_step` on every second step, `max_lifespan_step` is
             public, so the decay term is computed and subtracted exactly.

    `observe()` MUST be called every single turn. The inventory arithmetic is a
    running delta and a skipped turn breaks it permanently (HANDOFF section 6
    records the same constraint for the intervention layer).

    Blind spot, stated because it bounds every number this produces: sales at
    the $1 price floor do not enter market inventory, so they are invisible.
    Section 6 measured that as zero error on STRAWBERRY, MELON, MILK, WOOL and
    EGG across a full season, with total absolute error 9 confined to WHEAT and
    FERTILIZER -- the only two products whose price reaches the floor.
    """

    __slots__ = ("prev_inv", "prev_step", "prev_tiles", "collected", "sold",
                 "seen", "pending")

    def __init__(self):
        self.prev_inv = None
        self.prev_step = None
        self.prev_tiles = None
        self.collected = {}
        self.sold = {}
        self.seen = 0
        # Our own orders from the PREVIOUS turn. The inventory we can see at
        # step t is the state before step t's orders settle, so the delta
        # `inv[t] - inv[t-1]` is produced by the orders issued at t-1. Feeding
        # it this turn's orders instead is an off-by-one that biases every
        # single step in the same direction: measured, it drifted the holdings
        # estimate by ~5 units a step and reached an absolute error of 3,567
        # against a true holding of 22.
        self.pending = {}

    def _snapshot_tiles(self, farm):
        out = {}
        for y, row in enumerate(farm.tiles):
            for x, t in enumerate(row):
                if not isinstance(t, dict):
                    continue
                if "animal" in t:
                    out[(x, y)] = ("A", _ANIMAL_PRODUCT.get(t.get("animal")),
                                   _num(t.get("yield_units")), -1)
                elif t.get("kind") == "PLANT":
                    out[(x, y)] = ("P", t.get("crop"), _num(t.get("yield_units")),
                                   _num(t.get("max_lifespan_step"), -1))
        return out

    def record_my_orders(self, orders, shed=None):
        """Call AFTER deciding our action, with the orders we issued.

        Kept separate from `observe` because of the timing: these orders settle
        during this step and are visible in the inventory we read next turn.

        ORDERS ARE CAPPED BY WHAT WE COULD ACTUALLY SELL, and that is not a
        refinement -- it is the difference between this model working and not.
        `_commit_unit` sells a unit only while `private["shed"][item] > 0`, so an
        order for more than we hold is partly fiction, and every fictional unit
        is subtracted from the opponent's inferred sales. Measured with the
        uncapped version: `sold[FERTILIZER]` reached **-2,488**, i.e. the model
        concluded the opponent had bought two and a half thousand fertilizer,
        and total holdings error hit 3,572 against a true 22. The engine also
        drops orders past `maxMarketOrdersPerTurn`, so only the first ten count.
        """
        mine = {}
        left = dict(shed or {})
        for o in (orders or [])[:10]:
            if not o or len(o) < 3:
                continue
            if o[0] == "SELL":
                want = _num(o[2])
                if shed is not None:
                    want = min(want, max(0, _num(left.get(o[1], 0))))
                    left[o[1]] = _num(left.get(o[1], 0)) - want
                mine[o[1]] = mine.get(o[1], 0) + want
            elif o[0] == "BUY_PRODUCT":
                mine[o[1]] = mine.get(o[1], 0) - _num(o[2])
        self.pending = mine

    def observe(self, snap, my_sales=None):
        """One turn of evidence. Call every turn, before acting."""
        self.seen += 1
        my_sales = self.pending if my_sales is None else (my_sales or {})
        inv = snap.market_inv
        step = snap.step

        if self.prev_inv is not None and step > (self.prev_step or 0):
            for item in PRODUCTS:
                delta = _num(inv.get(item, 0)) - _num(self.prev_inv.get(item, 0))
                taken = 0
                for s in range(self.prev_step, step):
                    taken += town_take(item, s, snap.shops)
                theirs = delta + taken - _num(my_sales.get(item, 0))
                if theirs:
                    self.sold[item] = self.sold.get(item, 0) + theirs

        tiles = self._snapshot_tiles(snap.opp)
        if self.prev_tiles is not None:
            for pos, (kind, item, prev_units, mls) in self.prev_tiles.items():
                now = tiles.get(pos)
                units_now = now[2] if now and now[1] == item else 0
                decay = 0
                if kind == "P" and mls is not None and mls >= 0 and self.prev_step is not None:
                    for s in range(self.prev_step, step):
                        if s >= mls and (s - mls) % 2 == 0:
                            decay += 1
                got = prev_units - units_now - decay
                if got > 0 and item:
                    self.collected[item] = self.collected.get(item, 0) + got

        self.prev_inv = dict(inv)
        self.prev_tiles = tiles
        self.prev_step = step

    # ------------------------------------------------------------- estimates

    # Products whose price reaches the $1 floor carry an unbounded upward bias,
    # because a sale at the floor does not enter market inventory and so is
    # invisible to the sales term. Measured at step 710 over six games, mean
    # absolute error per item: MELON 0.0, EGG 0.0, CARROT 0.0, TOMATO 0.0,
    # FERTILIZER 0.7, STRAWBERRY 9.7 -- then MILK 104.7, WOOL 138.0, WHEAT
    # 299.7. The three big ones are exactly the products that crash to the
    # floor (WOOL is quadratic above baseline, MILK linear at 1.60, WHEAT is
    # traded both ways all game).
    RELIABLE = ("MELON", "EGG", "CARROT", "TOMATO", "STRAWBERRY")

    def holdings(self, item, shed_cap=100):
        """Units of `item` they are sitting on: harvested minus net sold.

        Clamped by `shedCapacity`, which is an EXACT constraint we were not
        using: their shed holds 100 items in total, so no single product can
        exceed that however badly the sales term has drifted.
        """
        raw = self.collected.get(item, 0) - self.sold.get(item, 0)
        return max(0, min(raw, shed_cap))

    def total_holdings(self):
        """Their whole stock, with the 100-item shed absorbed by the BIASED
        products only.

        Scaling every item to fit was the obvious clamp and it was wrong: it
        dragged MELON, EGG and STRAWBERRY -- which the sales term tracks to
        within a unit -- down along with MILK and WOOL, and turned a 0% error
        into a 100% one. The reliable products are reported as measured; the
        overflow is charged entirely to the products whose drift caused it.
        """
        raw = {i: self.holdings(i) for i in PRODUCTS}
        good = {i: v for i, v in raw.items() if i in self.RELIABLE and v}
        rest = {i: v for i, v in raw.items() if i not in self.RELIABLE and v}
        room = max(0, 100 - sum(good.values()))
        tot = sum(rest.values())
        if tot > room and tot > 0:
            scale = float(room) / tot
            rest = {i: int(v * scale) for i, v in rest.items()}
        out = dict(good)
        out.update({i: v for i, v in rest.items() if v})
        return out

    def confidence(self, item):
        """'exact' for products that never sit at the price floor, else 'biased'."""
        return "exact" if item in self.RELIABLE else "biased"

    def all_holdings(self):
        return self.total_holdings()

    def standing(self, snap):
        """Units still on their tiles, collectable before the season ends."""
        out = {}
        for t in snap.opp.animals.values():
            item = _ANIMAL_PRODUCT.get(t.get("animal"))
            n = _num(t.get("yield_units"))
            if item and n:
                out[item] = out.get(item, 0) + n
        for t in snap.opp.crops.values():
            item = t.get("crop")
            n = _num(t.get("yield_units"))
            if item and n:
                out[item] = out.get(item, 0) + n
        return out

    def clear_round(self, snap):
        """Their forced liquidation turn: 719 - (ceil(A / W) + 1).

        A physical bound, not a behavioural guess -- both inputs are public.
        """
        animals = len(snap.opp.animals)
        if animals <= 0:
            return None
        workers = max(1, snap.opp.workers)
        return 719 - ((animals + workers - 1) // workers + 1)

    def predicted_dump(self, snap):
        """{item: units} they are expected to put on the market before the end.

        Holdings they already have plus standing yield they still have time to
        collect. This is the quantity that decides what OUR stock is worth: if
        they are about to put 60 MILK into the book, MILK sold after them is
        worth the $1 floor.
        """
        out = dict(self.all_holdings())
        clear = self.clear_round(snap)
        if clear is None or snap.step <= clear:
            for item, n in self.standing(snap).items():
                out[item] = out.get(item, 0) + n
        return out
