"""Fully dynamic scheduler -- NO tape, no recorded actions, no JSON payload.

Every action is derived at runtime from the board. The only thing taken from
the tape is its ECONOMIC TRAJECTORY (how many hands per day, when to buy land,
when to buy animals) -- read off as targets in planner/schedule_diff.py, not as
actions. Cloning the tape's ACTIONS was measured and failed decisively
(planner/bc_play.py: $288 against the tape's $89k, with a control proving the
network was correct and the failure was covariate shift). Cloning its
TRAJECTORY is a different object: it is 30 numbers, and a dynamic scheduler is
free to reach them however the actual board allows.

WHY THIS IS NOT THE TWO EXPERIMENTS THAT ALREADY FAILED TODAY.

The farm economy is a chain: land unlocks tiles -> tiles create seed demand ->
seeds create PLANT tasks -> PLANT tasks justify a crew -> the crew does the
work that fills the shed. route/agent.py sizes its crew to TODAY's task list,
which is circular: a small crew produces a small task list which justifies a
small crew. Measured, it hires 188 times to the tape's 277 and lands 67 PLANT
and 13 PLACE ops to the tape's 186 and 53, while its realised price per unit is
BETTER than the tape's ($89.7 vs $79.6) and its useful-op rate is higher
(44.5% vs 40.1%). It is not less efficient; it runs a farm two thirds the size,
well.

  planner/scale_sweep.py  raised the portfolio without raising the crew:
                          monotonically worse, -87,245 at 74 tiles.
  planner/v2_sweep.py     raised the crew without raising the portfolio:
                          -13k to -52k, the hands stood idle on fib-priced cash.

Each moved one end of the chain. The tape moves BOTH, in a specific order --
land on days 6 and 11, all 14 animals placed by day 11, then a flat ~12 hands a
day sustained to the end. That combination is what neither experiment tested,
and it is what this module follows.
"""
"""Route-planning agent.

Architecture: the *plan* (what goes on which tile, how many hands, when to buy)
is searched offline; the *route* is solved at the start of each day by
route/router.py and then followed. This replaces the greedy per-turn patrol in
agent/main.py, which measured 25% useful / 60% movement against the strongest
reference agent's 52% / 43%.

The daily route is solved from the observed state rather than baked into a
720-step tape, because weed spawns are seeded off a stream shared between both
farms (so a tape can never be reproduced exactly -- see HANDOFF pitfall #5).
Solving it fresh each morning keeps the routing win and stays robust to weeds,
escaped animals and refused hires.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from route.geom import (SHED_SET, SHED_TILES, SPAWN, dist, dist_to_shed,  # noqa: E402
                        quadrant_of, steps_between)
from route.opponent import OpponentModel  # noqa: E402
from route.router import TURNS_PER_DAY, Task, Unit, partition, plan_day  # noqa: E402

# ------------------------------------------------------------ engine mirrors

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
TOWN_SHOP_SELL_INTERVAL = 4
TOWN_CENTER_SELL_INTERVAL = 24
LAND_ORDER = ["NE", "SW", "SE"]
LAND_PRICES = [1000, 2000, 4000]
SEASON_DAYS = 30
SHED_CAPACITY = 100
MAX_ORDERS = 10

# Roles claim tiles nearest-to-shed first, in descending ROLE_PRIORITY. Animals
# lead because they need 3-4 ops every single day plus a wheat delivery, so they
# are the tiles worth having closest to the shed (HANDOFF pitfall #10).
#
# Priority is not cosmetic. The queue is laid over tiles sorted by quadrant
# unlock order, so a role sitting behind a 50-tile portfolio is placed entirely
# in SW/SE and -- since we typically only unlock NW+NE -- never physically
# exists. WHEAT sat exactly there, which is why raising TC_WHEAT to 18 barely
# dented the ~316 wheat we were buying every season. Searchable for that reason.
ROLE_FILL_ORDER = ("COW", "SHEEP", "MELON", "STRAWBERRY", "WHEAT", "GOOSE")
ROLE_PRIORITY = {"COW": 0.95, "SHEEP": 0.90, "WHEAT": 0.80,
                 "MELON": 0.60, "STRAWBERRY": 0.50, "GOOSE": 0.10}

# ------------------------------------------------------------------- genome

TARGET_COUNTS = {"COW": 8, "SHEEP": 4, "MELON": 8, "STRAWBERRY": 16, "WHEAT": 12, "GOOSE": 0}
MAX_HANDS = 16

# The tape's economic trajectory, median over 6 seeds (planner/schedule_diff.py).
# Targets, not actions: hands wanted on each day, and the day each extra
# quadrant is bought. Followed only as far as cash actually allows.
CREW_SCHEDULE = (1, 5, 5, 6, 6, 6, 7, 9, 12, 13, 12, 13, 13, 12, 12, 9, 13, 10,
                 13, 13, 13, 13, 13, 13, 13, 12, 12, 12, 12, 11)
LAND_SCHEDULE = (6, 11, 99)     # day each extra quadrant is targeted
ANIMAL_DEADLINE = 12            # every animal placed by here, as the tape does
SCHEDULE_DRIVEN = 1             # 0 falls back to route/agent.py's demand sizing

# SEASON PLAN. A declarative target extracted from the tape by
# dynamic/seasonplan.py -- which tile holds which role, and the day it comes
# online -- NOT the tape's actions. 73 of its 75 tiles are identical across four
# seeds, so this is a plan rather than a reaction to one board.
#
# It carries the two things every scaling attempt tonight was missing. First the
# SHAPE: 27 STRAWBERRY / 20 MELON / 14 PASTURE / 12 WHEAT, against our searched
# 21/8/13/8 -- the tape runs 2.5x the melon (a deep book, and the only product
# where the front-run audit measured a positive price edge, +24.3) and gets 390
# wheat units from just 12 tiles by cycling them, where we get 116 from 8.
# Second the ORDER: cheap tiles first (day 0 is 12 melon at $80 and 7 wheat at
# $10), expensive strawberry at $100 deferred to days 11-12 once the third
# quadrant is open and cash exists. That ordering is a cash-flow sequence known
# to be feasible from $3,000, which is exactly what six refuted scaling
# experiments kept violating.
#
# SEASON_PLAN is {(x,y): (role, day)}; empty falls back to _build_layout.
SEASON_PLAN = {}
USE_PLAN = 0                    # 0 = ignore the plan entirely (formula layout)
PLAN_GATE_DAYS = 1              # honour the plan's come-online day
PLAN_SLACK = 0                  # allow planting this many days early
HIRE_BUDGET_FRACTION = 0.35
SPEND_RESERVE = 150
SURVIVAL_RESERVE_FRACTION = 1 / 3
WHEAT_FEED_BUFFER_MULT = 2.5
LAND_BUY_CASH_MULTIPLE = 1.6
ANIMAL_BUY_CAP_PER_TURN = 2
SEED_BATCH_PER_TURN = 4
BUY_ANIMALS_FIRST = 1
SHED_PANIC_FRACTION = 0.62
RAMP_START_DAY = 25
RAMP_END_DAY = 29
RESERVE_PRICE_SCALE = 1.0
COLLECT_FERT_VALUE = 200.0
# The placement errand is pure gain and always on. The top-up (sending an
# otherwise-idle unit to the nearest outstanding tile) is not: it lifted the
# vs-starter bank 37% but *cost* us head-to-head against the strongest
# reference, because the extra product lands in a market that opponent has
# already crashed. Left to the search to resolve.
IDLE_TOPUP = 1
IDLE_MAX_TRAVEL = 18
# Sale timing. Within a step the engine runs _process_market before
# _town_consume, so a sale placed on a step the town drains goes into the market
# *before* the drain lifts the price, while the same sale one step later goes in
# after it. Holding one step is worth most on the steep glut curves -- MELON and
# WOOL are quadratic above I0, MILK and STRAWBERRY linear -- which is exactly the
# set the strongest reference agent front-runs.
FRONT_RUN = 1
FRONT_RUN_ITEMS = ("MELON", "MILK", "STRAWBERRY", "WOOL")
TERMINAL_STEP = 680
# Opponent modelling. route/opponent.py recovers the opponent's per-step sales
# exactly from the public market inventory and projects their visible tiles
# forward; the ratio of that supply to the town's remaining demand scales our
# reserve price per product. A predicted glut also cancels the front-run hold --
# there is no point waiting one step for a better price if they are about to
# bury the market in the same product.
# Planting is throttled by a feedback signal rather than a tuned cap: if any
# living crop already missed a watering yesterday, the crew is already behind
# and planting more tiles just converts seed money into weeds. A plant that
# misses two consecutive waterings dies, so consecutive_unwatered >= 1 is the
# earliest honest warning. Measured: 25 of ~37 crop tiles ended the season as
# weeds before this existed.
PLANT_MISS_TOLERANCE = 0
# Whether surplus feed wheat may be sold at all while animals are alive.
# Buying feed and selling it back is pure loss on the order slots and the cash
# float even though the engine prices a round trip at par.
WHEAT_SELL_SURPLUS = 0
OPP_MODEL = 1
OPP_SCALE_LO = 0.65
OPP_SCALE_HI = 1.30
OPP_HORIZON_DAYS = 6

RESERVE_PRICE = {
    "MELON": 70, "WOOL": 60, "MILK": 55, "STRAWBERRY": 45, "TOMATO": 20,
    "CARROT": 15, "EGG": 20, "WHEAT": 12, "FERTILIZER": 25,
}
SELL_PRIORITY_ORDER = ["MELON", "WOOL", "MILK", "STRAWBERRY", "TOMATO",
                       "CARROT", "EGG", "FERTILIZER", "WHEAT"]

OP_VALUE = {
    "FEED": 1000.0, "PLACE": 950.0, "HARVEST": 900.0, "WATER": 800.0,
    "CARE": 700.0, "BUILD_PASTURE": 600.0, "BUILD_COOP": 600.0,
    "PLANT": 500.0, "DIG": 400.0, "FERTILIZE": 300.0,
    "COLLECT_FERTILIZER": 200.0,
}

_GENOME_KEYS = ("MAX_HANDS", "SCHEDULE_DRIVEN", "ANIMAL_DEADLINE",
                "USE_PLAN", "PLAN_GATE_DAYS", "PLAN_SLACK",
                "HIRE_BUDGET_FRACTION", "SPEND_RESERVE",
                "SURVIVAL_RESERVE_FRACTION", "WHEAT_FEED_BUFFER_MULT",
                "LAND_BUY_CASH_MULTIPLE", "ANIMAL_BUY_CAP_PER_TURN", "SEED_BATCH_PER_TURN", "BUY_ANIMALS_FIRST",
                "SHED_PANIC_FRACTION", "RAMP_START_DAY", "RAMP_END_DAY",
                "RESERVE_PRICE_SCALE", "COLLECT_FERT_VALUE",
                "IDLE_TOPUP", "IDLE_MAX_TRAVEL", "FRONT_RUN", "TERMINAL_STEP",
                "OPP_MODEL", "OPP_SCALE_LO", "OPP_SCALE_HI", "OPP_HORIZON_DAYS",
                "PLANT_MISS_TOLERANCE", "WHEAT_SELL_SURPLUS")


def configure(params):
    """Apply a searched genome. Mirrors agent/main.py's interface so the same
    search harness can drive this agent."""
    g = globals()
    for key in _GENOME_KEYS:
        if key in params:
            g[key] = params[key]
    for role in ROLE_FILL_ORDER:
        key = "TC_" + role
        if key in params:
            TARGET_COUNTS[role] = int(params[key])
        rp = "RP_" + role
        if rp in params:
            ROLE_PRIORITY[role] = float(params[rp])
    if "RESERVE_PRICE" in params:
        RESERVE_PRICE.update(params["RESERVE_PRICE"])
    g["OP_VALUE"] = dict(OP_VALUE, COLLECT_FERTILIZER=float(COLLECT_FERT_VALUE))
    _reset_state()


S = {}


def _reset_state():
    S.clear()
    S.update({"layout": None, "day": -1, "tours": {}, "progress": {},
              "target_units": 1, "bought": {a: 0 for a in ANIMALS},
              "pending": [], "idle_target": {},
              "opp": OpponentModel(), "last_sales": {}})


_reset_state()


def _fib(n):
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def _hire_cost(n_already_today):
    return _fib(n_already_today)


def _cum_hire_cost(n):
    return sum(_fib(i) for i in range(n))


# ------------------------------------------------------------------- layout

def _load_season_plan():
    """Read dynamic/season_plan.json into the {(x,y): (role, day)} form."""
    import json as _json
    path = os.path.join(_ROOT, "dynamic", "season_plan.json")
    if not os.path.exists(path):
        return {}
    try:
        raw = _json.load(open(path))["plan"]
    except Exception:
        return {}
    out = {}
    for k, v in raw.items():
        x, y = k.split(",")
        role = v["role"]
        # PASTURE in the plan means "an animal lives here"; the layout wants the
        # animal, and the tape's 14 pastures are its 6 cow / 8 sheep split.
        out[(int(x), int(y))] = (role, int(v["day"]))
    return out


def _plan_layout(board_size, plan):
    """Turn the extracted plan into a role map, splitting PASTURE into the
    tape's own cow/sheep mix by distance to the shed (cows first, being the
    cheaper and faster-yielding of the two)."""
    layout = {}
    pastures = []
    for pos, (role, day) in plan.items():
        if role == "PASTURE":
            pastures.append(pos)
        elif role in ("COOP",):
            layout[pos] = "GOOSE"
        else:
            layout[pos] = role
    pastures.sort(key=lambda t: (dist_to_shed(t), t[1], t[0]))
    n_cow = int(TARGET_COUNTS.get("COW", 6))
    for i, pos in enumerate(pastures):
        layout[pos] = "COW" if i < n_cow else "SHEEP"
    for y in range(board_size):
        for x in range(board_size):
            layout.setdefault((x, y), "EMPTY")
    return layout


def _build_layout(board_size):
    """Assign a role to every tile, nearest-to-shed first, quadrant by quadrant
    in the order land actually unlocks. Tiles past the end of the portfolio stay
    EMPTY -- never an animal, which is the filler bug that had the last search
    optimising around instant bankruptcy for 800+ generations (pitfall #7)."""
    quad_rank = {"NW": 0}
    for i, q in enumerate(LAND_ORDER):
        quad_rank[q] = i + 1
    tiles = [(x, y) for y in range(board_size) for x in range(board_size)]
    tiles.sort(key=lambda t: (quad_rank[quadrant_of(t[0], t[1], board_size)],
                              dist_to_shed(t), t[1], t[0]))
    tiles = [t for t in tiles if t not in SHED_SET or True]

    layout = {}
    queue = []
    for role in sorted(ROLE_FILL_ORDER, key=lambda r: (-ROLE_PRIORITY.get(r, 0.5), r)):
        queue.extend([role] * max(0, int(TARGET_COUNTS.get(role, 0))))
    for i, tile in enumerate(tiles):
        layout[tile] = queue[i] if i < len(queue) else "EMPTY"
    return layout


def _unlocked(farm, tile):
    x, y = tile
    return farm["tiles"][y][x] != "LOCKED"


# --------------------------------------------------------------- task build

def _last_plant_day(crop):
    """Latest day a fresh planting still returns something before day 29."""
    cd = CROPS[crop]
    if cd["ongoing"]:
        return SEASON_DAYS - 1 - cd["first_yield_day"]
    return SEASON_DAYS - 1 - cd["max_yield_day"]


def _in_fert_window(tile, crop, day):
    cd = CROPS[crop]
    age = day - tile["planted_day"]
    if cd["ongoing"]:
        return age >= cd["first_yield_day"] - 1
    return (cd["max_yield_day"] + 1) // 2 <= age <= cd["max_yield_day"]


def _should_harvest(tile, crop, day):
    cd = CROPS[crop]
    if tile.get("yield_units", 0) <= 0:
        return False
    age = day - tile["planted_day"]
    if age < cd["first_yield_day"]:
        return False
    if cd["ongoing"]:
        return True
    if day >= SEASON_DAYS - 2:
        return True
    return age >= cd["max_yield_day"] or tile["yield_units"] >= cd["max_yield"]


def _mk(pos, ops, carry=None):
    value = max(OP_VALUE.get(o[0], 100.0) for o in ops)
    return Task(pos, ops, carry=carry, value=value)


def _watering_debt(farm):
    """Living crop tiles that already missed a watering. Non-zero means the crew
    could not keep up yesterday."""
    debt = 0
    for row in farm["tiles"]:
        for tile in row:
            if isinstance(tile, dict) and tile.get("kind") == "PLANT" \
                    and tile.get("consecutive_unwatered", 0) >= 1:
                debt += 1
    return debt


def _build_tasks(farm, private, day, board_size):
    tiles = farm["tiles"]
    may_plant = _watering_debt(farm) <= PLANT_MISS_TOLERANCE
    seeds = dict(private.get("seeds") or {})
    shed = dict(private.get("shed") or {})
    avail_animal = {a: int(shed.get(a, 0)) for a in ANIMALS}
    tasks = []

    for pos, role in S["layout"].items():
        if role == "EMPTY":
            continue
        x, y = pos
        tile = tiles[y][x]
        if tile == "LOCKED":
            continue

        if role in ANIMALS:
            spec = ANIMALS[role]
            if tile is None:
                tasks.append(_mk(pos, [["BUILD_" + spec["structure"]]]))
            elif isinstance(tile, dict) and tile.get("animal") == role:
                core = []
                if not tile.get("fed_today"):
                    core.append(["FEED"])
                if not tile.get("cared_today"):
                    core.append(["CARE"])
                if tile.get("yield_units", 0) > 0:
                    core.append(["HARVEST"])
                if core:
                    carry = {"WHEAT": 1} if ["FEED"] in core else None
                    tasks.append(_mk(pos, core, carry=carry))
                if tile.get("fertilizer_available"):
                    tasks.append(_mk(pos, [["COLLECT_FERTILIZER"]]))
            elif isinstance(tile, dict) and tile.get("kind") == spec["structure"]:
                if avail_animal.get(role, 0) > 0:
                    avail_animal[role] -= 1
                    tasks.append(_mk(pos, [["PLACE", role]], carry={role: 1}))
            elif isinstance(tile, dict) and "animal" not in tile:
                tasks.append(_mk(pos, [["DIG"]]))
            continue

        # crop role
        cd = CROPS.get(role)
        if cd is None:
            continue
        if tile is None:
            plan_day = (S.get("plan") or {}).get(pos, (None, -1))[1]
            if PLAN_GATE_DAYS and plan_day >= 0 and day < plan_day - PLAN_SLACK:
                continue
            if may_plant and day <= _last_plant_day(role) and seeds.get(role, 0) > 0:
                seeds[role] -= 1
                # WATER must ride along in the same visit: _new_plant starts a
                # crop at consecutive_unwatered=1, so a seedling left unwatered
                # on its planting day is already a weed by the nightly refresh.
                tasks.append(_mk(pos, [["PLANT", role], ["WATER"]]))
        elif isinstance(tile, dict) and tile.get("kind") == "PLANT":
            crop = tile["crop"]
            ops = []
            harvest = _should_harvest(tile, crop, day)
            terminal = harvest and not CROPS[crop]["ongoing"]
            if not terminal:
                if (not tile.get("watered_today")) and _in_fert_window(tile, crop, day) \
                        and tile.get("fertilized_until_day", -1) < day:
                    ops.append(["FERTILIZE"])
                if not tile.get("watered_today"):
                    ops.append(["WATER"])
            if harvest:
                ops.append(["HARVEST"])
            if ops:
                carry = {"FERTILIZER": 1} if ["FERTILIZE"] in ops else None
                tasks.append(_mk(pos, ops, carry=carry))
        elif isinstance(tile, dict) and tile.get("kind") == "WEED":
            if day <= _last_plant_day(role):
                tasks.append(_mk(pos, [["DIG"]]))
    return tasks


# ------------------------------------------------------------- day planning

def _make_units(n_units, farmer_pos):
    """Hands hired at hour h are appended by that turn's market phase and first
    act at h+1. Only 10 market orders clear per turn, so hands 11+ land a turn
    later than the first ten."""
    units = [Unit(0, tuple(farmer_pos), 0)]
    for i in range(1, n_units):
        units.append(Unit(i, SPAWN, 1 if i <= 10 else 2))
    return units


def _size_crew(tasks, money, farmer_pos, day=0):
    """Crew for the day.

    With SCHEDULE_DRIVEN the size comes from CREW_SCHEDULE rather than from the
    length of today's task list, because demand-driven sizing cannot bootstrap
    (see the module docstring). Cash still caps it -- the fib ladder is real and
    a hand nobody can pay for is not hired -- but an empty task list no longer
    collapses the crew to one, which is the feedback loop that kept the farm at
    two thirds size.
    """
    cash_cap = 1
    budget = money * HIRE_BUDGET_FRACTION
    for h in range(1, int(MAX_HANDS) + 1):
        if _cum_hire_cost(h) <= budget:
            cash_cap = h + 1
        else:
            break
    if SCHEDULE_DRIVEN:
        want = CREW_SCHEDULE[min(day, len(CREW_SCHEDULE) - 1)]
        return max(1, min(want, cash_cap))
    if not tasks:
        return 1
    cash_cap = 1
    budget = money * HIRE_BUDGET_FRACTION
    for h in range(1, int(MAX_HANDS) + 1):
        if _cum_hire_cost(h) <= budget:
            cash_cap = h + 1
        else:
            break
    for n in range(1, cash_cap + 1):
        _, leftover = partition(tasks, _make_units(n, farmer_pos))
        if not leftover:
            return n
    return cash_cap


def _plan_day(farm, private, day, board_size):
    tasks = _build_tasks(farm, private, day, board_size)
    farmer_pos = tuple(farm["farmer"])
    n_units = _size_crew(tasks, farm["money"], farmer_pos, day)
    units = _make_units(n_units, farmer_pos)
    shed_stock = dict(private.get("shed") or {})
    tours, _undone = plan_day(units, tasks, shed_stock)
    for tour in tours.values():
        tour["carry_list"] = sorted(tour["carry"].items())
    S["tours"] = tours
    S["progress"] = {i: {"carry_i": 0, "stop_i": 0, "op_i": 0} for i in tours}
    S["target_units"] = n_units


# ------------------------------------------------------------- route follow

def _unit_position(farm, idx):
    if idx == 0:
        return farm["farmer"]
    hands = farm.get("hands") or []
    return hands[idx - 1] if idx - 1 < len(hands) else None


def _op_valid(op, tile, inv, seeds):
    name = op[0]
    is_dict = isinstance(tile, dict)
    if name == "FEED":
        return is_dict and "animal" in tile and not tile.get("fed_today") and inv.get("WHEAT", 0) > 0
    if name == "CARE":
        return is_dict and "animal" in tile and not tile.get("cared_today")
    if name == "COLLECT_FERTILIZER":
        return is_dict and "animal" in tile and tile.get("fertilizer_available")
    if name == "HARVEST":
        return is_dict and tile.get("yield_units", 0) > 0
    if name == "WATER":
        return is_dict and tile.get("kind") == "PLANT" and not tile.get("watered_today")
    if name == "FERTILIZE":
        return is_dict and tile.get("kind") == "PLANT" and inv.get("FERTILIZER", 0) > 0
    if name == "PLANT":
        return tile is None and seeds.get(op[1], 0) > 0
    if name in ("BUILD_COOP", "BUILD_PASTURE"):
        return tile is None
    if name == "PLACE":
        return (inv.get(op[1], 0) > 0 and is_dict
                and tile.get("kind") == ANIMALS[op[1]]["structure"] and "animal" not in tile)
    if name == "DIG":
        return tile is not None and not (is_dict and "animal" in tile)
    return True


def _unit_action(idx, farm, private, board_size, claimed):
    raw = _unit_position(farm, idx)
    if raw is None:
        return ["PASS"]
    pos = (raw[0], raw[1])
    shed = private.get("shed") or {}
    seeds = private.get("seeds") or {}
    inventories = private.get("inventories") or [{}]
    inv = inventories[idx] if idx < len(inventories) else {}

    tour = S["tours"].get(idx)
    if not tour:
        return _idle_action(idx, farm, private, S["day"], pos, inv, claimed)
    prog = S["progress"][idx]

    while prog["carry_i"] < len(tour["carry_list"]):
        item, want = tour["carry_list"][prog["carry_i"]]
        prog["carry_i"] += 1
        have = int(shed.get(item, 0))
        take = min(int(want), have)
        if take > 0 and pos in SHED_SET:
            return ["PICKUP", item, take]

    tiles = farm["tiles"]
    while prog["stop_i"] < len(tour["stops"]):
        target, ops = tour["stops"][prog["stop_i"]]
        if pos != tuple(target):
            moves = steps_between(pos, target)
            if moves:
                return [moves[0]]
        tile = tiles[target[1]][target[0]]
        while prog["op_i"] < len(ops):
            op = ops[prog["op_i"]]
            prog["op_i"] += 1
            if _op_valid(op, tile, inv, seeds):
                return list(op)
        prog["stop_i"] += 1
        prog["op_i"] = 0
    return _idle_action(idx, farm, private, S["day"], pos, inv, claimed)



# ------------------------------------------------------ opportunistic filler

def _live_ops(role, tile, day, seeds, may_plant=True):
    """Work this tile has outstanding right now, ignoring who carries what.
    Inventory is checked separately by _op_valid at the moment of issue."""
    if role in ANIMALS:
        spec = ANIMALS[role]
        if tile is None:
            return [["BUILD_" + spec["structure"]]]
        if not isinstance(tile, dict):
            return []
        if tile.get("animal") == role:
            ops = []
            if not tile.get("fed_today"):
                ops.append(["FEED"])
            if not tile.get("cared_today"):
                ops.append(["CARE"])
            if tile.get("yield_units", 0) > 0:
                ops.append(["HARVEST"])
            if tile.get("fertilizer_available"):
                ops.append(["COLLECT_FERTILIZER"])
            return ops
        if tile.get("kind") == spec["structure"] and "animal" not in tile:
            return [["PLACE", role]]
        if "animal" not in tile:
            return [["DIG"]]
        return []

    cd = CROPS.get(role)
    if cd is None:
        return []
    if tile is None:
        if may_plant and day <= _last_plant_day(role) and seeds.get(role, 0) > 0:
            return [["PLANT", role], ["WATER"]]
        return []
    if not isinstance(tile, dict):
        return []
    if tile.get("kind") == "PLANT":
        ops = []
        if not tile.get("watered_today"):
            ops.append(["WATER"])
        if _should_harvest(tile, tile["crop"], day):
            ops.append(["HARVEST"])
        return ops
    if tile.get("kind") == "WEED" and day <= _last_plant_day(role):
        return [["DIG"]]
    return []


def _pending_now(farm, private, day):
    """Every tile with outstanding work, recomputed once per turn. The engine
    applies all of a turn's unit actions after the agent returns, so farm state
    is frozen for the whole call and one scan serves every unit."""
    tiles = farm["tiles"]
    seeds = private["seeds"]
    may_plant = _watering_debt(farm) <= PLANT_MISS_TOLERANCE
    out = []
    for pos, role in S["layout"].items():
        if role == "EMPTY":
            continue
        tile = tiles[pos[1]][pos[0]]
        if tile == "LOCKED":
            continue
        ops = _live_ops(role, tile, day, seeds, may_plant)
        if ops:
            out.append((pos, ops))
    return out


def _free_structures(farm, animal, claimed):
    spec = ANIMALS[animal]
    out = []
    for pos, role in S["layout"].items():
        if role != animal or pos in claimed:
            continue
        tile = farm["tiles"][pos[1]][pos[0]]
        if isinstance(tile, dict) and tile.get("kind") == spec["structure"] and "animal" not in tile:
            out.append(pos)
    return out


def _idle_action(idx, farm, private, day, pos, inv, claimed):
    """What a unit does on a turn its routed tour has no work for.

    Pure upside: it only ever replaces a PASS. It also closes the animal
    build-out lag -- a cow bought at hour 3 lands in the shed at hour 4, long
    after the morning route was solved, so without this it sits there until
    tomorrow's plan and the herd comes online ~10 days late.
    """
    tiles = farm["tiles"]
    shed = private["shed"]
    seeds = private["seeds"]

    carried = next((a for a in ANIMALS if inv.get(a, 0) > 0), None)
    if carried:
        spots = _free_structures(farm, carried, claimed)
        if spots:
            target = min(spots, key=lambda p: (dist(pos, p), p))
            claimed.add(target)
            if pos == target:
                return ["PLACE", carried]
            return [steps_between(pos, target)[0]]
    else:
        for a in ("COW", "SHEEP", "GOOSE"):
            if int(shed.get(a, 0)) <= 0 or not _free_structures(farm, a, claimed):
                continue
            if pos in SHED_SET:
                return ["PICKUP", a, 1]
            target = min(SHED_TILES, key=lambda p: (dist(pos, p), p))
            return [steps_between(pos, target)[0]]

    if not IDLE_TOPUP:
        S["idle_target"].pop(idx, None)
        return ["PASS"]
    sticky = S["idle_target"].get(idx)
    candidates = S.get("pending") or ()
    best, best_ops, best_d = None, None, None
    for tpos, ops in candidates:
        if tpos in claimed:
            continue
        tile = tiles[tpos[1]][tpos[0]]
        usable = [o for o in ops if _op_valid(o, tile, inv, seeds)]
        if not usable:
            continue
        d = dist(pos, tpos)
        if d > IDLE_MAX_TRAVEL:
            continue
        if tpos == sticky:
            d -= 2  # mild hysteresis so a unit finishes the trip it started
        if best_d is None or d < best_d:
            best, best_ops, best_d = tpos, usable, d
    if best is None:
        S["idle_target"].pop(idx, None)
        return ["PASS"]
    claimed.add(best)
    S["idle_target"][idx] = best
    if pos == best:
        return list(best_ops[0])
    return [steps_between(pos, best)[0]]


# ----------------------------------------------------------------- market

def _placed_animals(farm):
    n = 0
    for row in farm["tiles"]:
        for tile in row:
            if isinstance(tile, dict) and "animal" in tile:
                n += 1
    return n


def _ramp(day):
    if day < RAMP_START_DAY:
        return 1.0
    if day >= RAMP_END_DAY:
        return 0.0
    span = max(1, RAMP_END_DAY - RAMP_START_DAY)
    return max(0.0, 1.0 - (day - RAMP_START_DAY) / span)


def _role_demand(farm, day):
    """Seeds and animals still wanted by the layout, on unlocked land."""
    want = {}
    for pos, role in S["layout"].items():
        if role == "EMPTY" or not _unlocked(farm, pos):
            continue
        x, y = pos
        tile = farm["tiles"][y][x]
        if role in ANIMALS:
            if not (isinstance(tile, dict) and "animal" in tile):
                want[role] = want.get(role, 0) + 1
        elif tile is None and day <= _last_plant_day(role):
            want[role] = want.get(role, 0) + 1
    return want


def _order_animals(orders, money, want, shed, seeds, shed_used):
    """Animals are the compounding asset -- an animal yields every day from
    placement to the end of the season -- but seed for a strawberry planted on
    day 1 also compounds. Which claim on early cash wins is genuinely unobvious,
    so BUY_ANIMALS_FIRST is left to the search rather than guessed here.
    Throttled per turn, and capped by shed room since a bought animal sits in
    the shed until placed."""
    for role in ("COW", "SHEEP", "GOOSE"):
        if len(orders) >= MAX_ORDERS:
            break
        need = want.get(role, 0) - int(shed.get(role, 0))
        if need <= 0:
            continue
        cost = ANIMALS[role]["cost"]
        room = max(0, SHED_CAPACITY - shed_used - 5)
        afford = int(max(0, money - SPEND_RESERVE) // cost)
        n = int(min(need, afford, room, ANIMAL_BUY_CAP_PER_TURN))
        if n > 0:
            orders.append(["BUY_ANIMAL", role, n])
            money -= n * cost
    return money


def _order_seeds(orders, money, want, shed, seeds, shed_used):
    """Seeds never enter the shed, so they cost no capacity -- only cash.
    Batched per turn rather than bought as a whole portfolio at once."""
    for crop in ("WHEAT", "STRAWBERRY", "MELON", "CARROT", "TOMATO"):
        if len(orders) >= MAX_ORDERS:
            break
        need = want.get(crop, 0) - int(seeds.get(crop, 0))
        if need <= 0:
            continue
        cost = CROPS[crop]["seed"]
        afford = int(max(0, money - SPEND_RESERVE) // cost)
        n = int(min(need, afford, SEED_BATCH_PER_TURN))
        if n > 0:
            orders.append(["BUY_SEED", crop, n])
            money -= n * cost
    return money


def _town_demand_now(item, step, shops):
    """Units of `item` the town removes from the market at this step."""
    demand = 1 if item != "FERTILIZER" and step % TOWN_CENTER_SELL_INTERVAL == 0 else 0
    if step % TOWN_SHOP_SELL_INTERVAL == 0:
        for shop in shops:
            products = SHOP_PRODUCTS.get(shop, ())
            if item in products:
                demand += 2 if len(products) == 1 else 1
    return demand


def _market_orders(farm, private, day, hour, prices, shops=(), opp_farm=None):
    orders = []
    money = farm["money"]
    shed = private.get("shed") or {}
    seeds = private.get("seeds") or {}
    shed_used = sum(shed.values())
    survival_reserve = SPEND_RESERVE * SURVIVAL_RESERVE_FRACTION

    # 1. Hire. Only worth issuing early -- a hand hired at hour 20 has no day
    #    left to work, and the crew size was already routed for at hour 0.
    if hour <= 1:
        target_hands = S["target_units"] - 1
        n_hands = len(farm.get("hands") or [])
        hires_today = farm.get("hires_today", 0)
        k = 0
        while n_hands + k < target_hands and len(orders) < MAX_ORDERS:
            cost = _hire_cost(hires_today + k)
            if money - cost < SPEND_RESERVE:
                break
            orders.append(["HIRE"])
            money -= cost
            k += 1

    # 2. Feed wheat, ahead of every discretionary purchase: a starved animal
    #    loses its banked CARE bonus, which is most of its value.
    animals = _placed_animals(farm)
    if animals > 0 and len(orders) < MAX_ORDERS:
        # Never stock more feed than the season can still consume. Without the
        # days-left cap the feed block keeps buying a full buffer through the
        # terminal-liquidation window, which then sells it straight back: 292
        # units of bought wheat round-tripped in one episode.
        days_left = max(0, SEASON_DAYS - day)
        target_stock = int(min(animals * WHEAT_FEED_BUFFER_MULT, animals * days_left))
        have = int(shed.get("WHEAT", 0))
        room = max(0, SHED_CAPACITY - shed_used)
        if have < target_stock and room > 0:
            price = max(1, prices.get("WHEAT", 25))
            afford = int(max(0, money - survival_reserve) // price)
            n = int(min(target_stock - have, afford, room, 40))
            if n > 0:
                orders.append(["BUY_PRODUCT", "WHEAT", n])
                money -= n * price

    want = _role_demand(farm, day)
    if _watering_debt(farm) > PLANT_MISS_TOLERANCE:
        for crop in CROPS:
            want.pop(crop, None)

    # 3/4. Animals and seeds, in the order the search prefers.
    if BUY_ANIMALS_FIRST:
        money = _order_animals(orders, money, want, shed, seeds, shed_used)
        money = _order_seeds(orders, money, want, shed, seeds, shed_used)
    else:
        money = _order_seeds(orders, money, want, shed, seeds, shed_used)
        money = _order_animals(orders, money, want, shed, seeds, shed_used)

    # 5. Land. On the tape's schedule when SCHEDULE_DRIVEN, otherwise only once
    #    the next quadrant already has roles waiting.
    #
    #    The old `wanted` test is a hard cap disguised as a guard: it needs a
    #    non-EMPTY role in the next quadrant, and the layout only has roles for
    #    as many tiles as TARGET_COUNTS sums to. At the searched optimum that
    #    sum is exactly 50 -- precisely NW + NE -- so SW never holds a role,
    #    `wanted` is permanently False, and the third quadrant can never be
    #    bought however much cash accumulates. Measured: the season ends with
    #    $97k unspent on 50 tiles while the tape works 75.
    if len(orders) < MAX_ORDERS:
        n_extra = len(farm.get("unlocked_quadrants", ["NW"])) - 1
        if n_extra < len(LAND_PRICES):
            price = LAND_PRICES[n_extra]
            nxt = LAND_ORDER[n_extra]
            if SCHEDULE_DRIVEN:
                due = day >= LAND_SCHEDULE[min(n_extra, len(LAND_SCHEDULE) - 1)]
                if due and money >= price * LAND_BUY_CASH_MULTIPLE:
                    orders.append(["BUY_LAND"])
                    money -= price
            else:
                wanted = any(role != "EMPTY" and quadrant_of(p[0], p[1], 10) == nxt
                             for p, role in S["layout"].items())
                if wanted and money >= price * LAND_BUY_CASH_MULTIPLE:
                    orders.append(["BUY_LAND"])
                    money -= price

    # 6. Sell. Iterate the priority list, never the raw shed -- the shed also
    #    holds live animals and a SELL of a non-product aborts the whole slot
    #    (pitfall #8).
    step = day * 24 + hour
    sold = {}
    ramp = _ramp(day)
    panic = shed_used > SHED_CAPACITY * SHED_PANIC_FRACTION
    # Reward is money on hand, so anything still in the shed at the buzzer is
    # worth exactly nothing. Liquidate unconditionally near the end.
    terminal = step >= TERMINAL_STEP
    for item in SELL_PRIORITY_ORDER:
        if len(orders) >= MAX_ORDERS:
            break
        have = int(shed.get(item, 0))
        if have <= 0:
            continue
        if terminal:
            # Wheat is the one product we are also still *buying* during the
            # liquidation window, to feed animals through their final
            # production days. Dumping it here just gets it re-bought next turn
            # -- 303 units churned that way in one episode. Hold it to the last
            # day, when the feed no longer has a production left to fund.
            if item == "WHEAT" and animals > 0 and day < SEASON_DAYS - 1:
                continue
            orders.append(["SELL", item, have])
            sold[item] = sold.get(item, 0) + have
            continue
        if item == "WHEAT" and animals > 0 and not WHEAT_SELL_SURPLUS:
            continue
        if item == "WHEAT":
            # Reserve the feed buffer against *every* sell path, panic included.
            # Panic-selling it and re-buying it next turn churned ~292 units of
            # bought wheat straight back out to the market, which is most of why
            # our spend ran 2.2x the reference's.
            have -= int(animals * WHEAT_FEED_BUFFER_MULT)
            if have <= 0:
                continue
        scale = 1.0
        glut = False
        if OPP_MODEL and opp_farm is not None:
            scale = S["opp"].reserve_scale(opp_farm, item, day, step, shops,
                                           lo=OPP_SCALE_LO, hi=OPP_SCALE_HI,
                                           horizon_days=int(OPP_HORIZON_DAYS))
            glut = scale < 1.0
        # Hold one step for the town's tick to lift the price -- unless the
        # opponent is about to flood this product anyway, in which case waiting
        # just means selling after them into a worse market.
        if (FRONT_RUN and item in FRONT_RUN_ITEMS and not panic and not glut
                and _town_demand_now(item, step, shops) > 0):
            continue
        reserve = RESERVE_PRICE.get(item, 20) * RESERVE_PRICE_SCALE * ramp * scale
        price = prices.get(item, 0)
        if price >= reserve or panic:
            orders.append(["SELL", item, int(have)])
            sold[item] = sold.get(item, 0) + int(have)
    S["last_sales"] = sold
    return orders[:MAX_ORDERS]


# ------------------------------------------------------------------- agent

def _guard_plant_atomicity(actions, seeds):
    """If total PLANT requests for one crop in a turn exceed seeds held, the
    engine drops ALL of them. Trim the excess to PASS so the rest still land."""
    counts = {}
    for a in actions:
        if len(a) >= 2 and a[0] == "PLANT":
            counts[a[1]] = counts.get(a[1], 0) + 1
    over = {c: n - int(seeds.get(c, 0)) for c, n in counts.items() if n > int(seeds.get(c, 0))}
    if not over:
        return actions
    out = []
    for a in actions:
        if len(a) >= 2 and a[0] == "PLANT" and over.get(a[1], 0) > 0:
            over[a[1]] -= 1
            out.append(["PASS"])
        else:
            out.append(a)
    return out


def agent(obs):
    obs = obs if isinstance(obs, dict) else dict(obs)
    player = obs.get("player", 0)
    farms = obs.get("farms") or []
    if not farms or player >= len(farms):
        return {"farmer": ["PASS"], "hands": [], "market": []}
    farm = farms[player]
    private = obs.get("private") or {}
    private = {
        "shed": private.get("shed") or {},
        "seeds": private.get("seeds") or {},
        "inventories": private.get("inventories") or [{}],
    }
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    board_size = len(farm["tiles"])

    if day == 0 and hour == 0:
        _reset_state()
    if S.get("layout") is None:
        # USE_PLAN is a separate switch on purpose. The first version gated this
        # on `PLAN_GATE_DAYS >= 0`, which is true for 0, so the plan loaded even
        # when it was meant to be off -- the "baseline" silently ran the tape's
        # 73-tile layout with parameters searched for 50 and scored -164,312
        # against its real -76,238, and three variants returned byte-identical
        # numbers because they were the same agent.
        plan = (SEASON_PLAN or _load_season_plan()) if USE_PLAN else {}
        S["plan"] = plan if isinstance(plan, dict) else {}
        S["layout"] = (_plan_layout(board_size, S["plan"]) if S["plan"]
                       else _build_layout(board_size))

    if S["day"] != day:
        S["day"] = day
        _plan_day(farm, private, day, board_size)

    S["pending"] = _pending_now(farm, private, day)
    claimed = set()
    n_hands = len(farm.get("hands") or [])
    farmer_action = _unit_action(0, farm, private, board_size, claimed)
    hands_actions = [_unit_action(i + 1, farm, private, board_size, claimed)
                     for i in range(n_hands)]

    guarded = _guard_plant_atomicity([farmer_action] + hands_actions, private["seeds"])
    farmer_action, hands_actions = guarded[0], guarded[1:]

    market_obj = obs.get("market") or {}
    prices = market_obj.get("prices") or {}
    town = obs.get("town") or {}
    shops = tuple(town.get("unlocked_shops") or ())
    opp_farm = farms[1 - player] if len(farms) > 1 else None
    if OPP_MODEL:
        # Our own realised sales are within a unit or two of what we requested:
        # we only ever ask for exactly what the shed holds, so the per-unit
        # commit loop fills the order.
        S["opp"].observe(market_obj.get("inventory") or {}, day * 24 + hour,
                         shops, S.get("last_sales") or {})
    orders = _market_orders(farm, private, day, hour, prices, shops, opp_farm)

    return {"farmer": farmer_action, "hands": hands_actions, "market": orders}
