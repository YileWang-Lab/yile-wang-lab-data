"""Auto-generated self-contained submission artifact. Do not edit by hand — edit task_teacher_v12/main.py and/or src/kaggriculture_lib, then rerun scripts/package_agent.py to regenerate."""

from __future__ import annotations

import sys as _sys
import types as _types


def _register_shared_module(name, source, path):
    module = _types.ModuleType(name)
    module.__file__ = path
    _sys.modules[name] = module
    exec(compile(source, path, "exec"), module.__dict__)
    return module


_kaggriculture_lib = _types.ModuleType("kaggriculture_lib")
_kaggriculture_lib.__path__ = []
_sys.modules["kaggriculture_lib"] = _kaggriculture_lib

_economy_source = '"""Kaggriculture game economy: prices, yields, and derived ROI estimates.\n\nEvery formula here mirrors the environment\'s own implementation exactly\n(installed at `kaggle_environments/envs/kaggriculture/kaggriculture.py`, see\n`docs/2_environment_notes.md` for the version pin and line-range citations\nper formula). This module exists so every agent version (heuristic, BC,\nPPO) shares one tested source of truth instead of re-deriving the game math\nindependently — see `docs/0_coding_standards.md` §2.\n"""\n\nfrom __future__ import annotations\n\nimport math\nfrom typing import Literal\n\nShapeFn = Literal["linear", "sq", "sqrt", "log", "log10"]\n\nMARKET_I0 = 10_000\nPRICE_FLOOR = 1\n\n# Mirrors kaggle-environments==1.29.3\'s kaggriculture.py MARKET_PARAMS\n# verbatim (pinned version — see requirements.txt and docs/2_environment_notes.md\'s\n# version-gap comparison: newer releases like 1.32.2 have different\n# above_target glut-sensitivity constants for premium goods).\nMARKET_PARAMS: dict[str, dict] = {\n    "WHEAT":      {"base":  25, "I0": MARKET_I0, "T": 400, "below_func": "sqrt",   "below_target": 0.80, "above_func": "log",  "above_target": 0.20},\n    "CARROT":     {"base":  35, "I0": MARKET_I0, "T": 450, "below_func": "log",    "below_target": 0.20, "above_func": "sqrt", "above_target": 0.70},\n    "TOMATO":     {"base":  60, "I0": MARKET_I0, "T": 200, "below_func": "linear", "below_target": 0.40, "above_func": "sqrt", "above_target": 0.60},\n    "STRAWBERRY": {"base": 120, "I0": MARKET_I0, "T": 100, "below_func": "sqrt",   "below_target": 0.70, "above_func": "linear", "above_target": 0.40},\n    "MELON":      {"base": 250, "I0": MARKET_I0, "T": 300, "below_func": "log",    "below_target": 0.20, "above_func": "sq",   "above_target": 0.90},\n    "EGG":        {"base":  50, "I0": MARKET_I0, "T": 332, "below_func": "linear", "below_target": 0.40, "above_func": "log",  "above_target": 0.20},\n    "MILK":       {"base": 160, "I0": MARKET_I0, "T": 122, "below_func": "sqrt",   "below_target": 0.60, "above_func": "linear", "above_target": 0.40},\n    "WOOL":       {"base": 200, "I0": MARKET_I0, "T": 105, "below_func": "log",    "below_target": 0.20, "above_func": "sq",   "above_target": 0.80},\n    "FERTILIZER": {"base": 100, "I0": MARKET_I0, "T": 200, "below_func": "linear", "below_target": 0.40, "above_func": "linear", "above_target": 0.40},\n}\n\n# Mirrors kaggle-environments==1.29.3\'s kaggriculture.py CROPS verbatim.\nCROPS: dict[str, dict] = {\n    "WHEAT":      {"seed": 10, "first_yield_day": 2, "max_yield_day": 4, "interval": 0, "max_yield": 6, "ongoing": False},\n    "CARROT":     {"seed": 20, "first_yield_day": 2, "max_yield_day": 3, "interval": 0, "max_yield": 4, "ongoing": False},\n    "TOMATO":     {"seed": 50, "first_yield_day": 8, "max_yield_day": 8, "interval": 1, "max_yield": 4, "ongoing": True},\n    "STRAWBERRY": {"seed": 100, "first_yield_day": 10, "max_yield_day": 10, "interval": 2, "max_yield": 4, "ongoing": True},\n    "MELON":      {"seed": 80, "first_yield_day": 10, "max_yield_day": 12, "interval": 0, "max_yield": 6, "ongoing": False},\n}\n\n# Mirrors kaggle-environments==1.29.3\'s kaggriculture.py ANIMALS verbatim.\n# Note COW cost is 600 here vs. 400 in 1.32.2 — confirmed via direct diff,\n# not a transcription assumption.\nANIMALS: dict[str, dict] = {\n    "GOOSE": {"cost": 300, "structure": "COOP", "first_yield_day": 4, "interval": 1, "max_held": 4, "product": "EGG"},\n    "COW":   {"cost": 600, "structure": "PASTURE", "first_yield_day": 8, "interval": 2, "max_held": 6, "product": "MILK"},\n    "SHEEP": {"cost": 500, "structure": "PASTURE", "first_yield_day": 6, "interval": 3, "max_held": 6, "product": "WOOL"},\n}\n\n# Mirrors kaggle-environments==1.29.3\'s kaggriculture.py LAND_ORDER / LAND_PRICES verbatim.\nLAND_ORDER = ["NE", "SW", "SE"]\nLAND_PRICES = [1000, 2000, 4000]\n\n# 1.29.3\'s default; confirmed 10x more expensive than 1.32.2\'s default of 1.\nFARM_HAND_COST_MULT = 10\n\n\ndef _shape(func: ShapeFn, x: float) -> float:\n    """Mirrors kaggle-environments==1.29.3\'s kaggriculture.py:51-60 (`_shape`)."""\n    x = max(0.0, x)\n    if func == "linear":\n        return x\n    if func == "sq":\n        return x * x\n    if func == "sqrt":\n        return math.sqrt(x)\n    if func == "log":\n        return math.log(1.0 + x)\n    if func == "log10":\n        return math.log10(1.0 + x)\n    return x\n\n\ndef market_price(item: str, inventory: float, params: dict | None = None) -> int:\n    """Current sale price for `item` at the given market inventory level.\n\n    Mirrors kaggle-environments==1.29.3\'s kaggriculture.py:175-191 (`market_price`) exactly:\n    `price(inv) = base + sign*amp*f(|inv-I0|)`, floored at `PRICE_FLOOR` and\n    rounded to the nearest int. `sign` is +1 (scarcity) below I0, -1 (glut)\n    above it; `amp` is derived so that moving `T` units past `I0` shifts\n    price by `target * base`.\n    """\n    p = (params or MARKET_PARAMS)[item]\n    base, i0, t = p["base"], p["I0"], p["T"]\n    if inventory < i0:\n        f = p["below_func"]\n        amp = p["below_target"] * base / _shape(f, t)\n        price = base + amp * _shape(f, i0 - inventory)\n    else:\n        f = p["above_func"]\n        amp = p["above_target"] * base / _shape(f, t)\n        price = base - amp * _shape(f, inventory - i0)\n    return max(PRICE_FLOOR, round(price))\n\n\ndef hire_cost(n_already_today: int, mult: int = FARM_HAND_COST_MULT) -> int:\n    """Cost of the next hire today. Mirrors kaggle-environments==1.29.3\'s\n    kaggriculture.py:651-662 (`_fib`, `_hire_cost`).\n\n    `_fib(n)` is indexed so `_fib(0)=1, _fib(1)=1, _fib(2)=2, _fib(3)=3, ...`\n    and resets to 0 at the start of each day (`farm["hires_today"]`).\n    """\n    a, b = 1, 1\n    for _ in range(n_already_today):\n        a, b = b, a + b\n    return mult * a\n\n\ndef hire_cost_mult(config: dict | None = None) -> int:\n    """Hire multiplier from episode config, else `FARM_HAND_COST_MULT`.\n\n    Live ladder episodes set `farmHandCostMult=1`; bare 1.29.3 `make()`\n    defaults to 10. Agents that care about ladder-parity should pass\n    `config` through here (see `env_config.LADDER_MATCH_CONFIGURATION`).\n    """\n    if not config:\n        return FARM_HAND_COST_MULT\n    return int(config.get("farmHandCostMult", FARM_HAND_COST_MULT))\n\n\ndef land_cost(n_unlocked_extra: int) -> int | None:\n    """Cost of the next `BUY_LAND` order, or None if all land is unlocked.\n\n    Mirrors kaggle-environments==1.29.3\'s kaggriculture.py:673-688\n    (`_do_buy_land`). `n_unlocked_extra` is\n    the count of quadrants already bought beyond the always-unlocked NW.\n    """\n    if n_unlocked_extra >= len(LAND_ORDER):\n        return None\n    return LAND_PRICES[n_unlocked_extra]\n\n\ndef shed_access_tiles(board_size: int) -> list[tuple[int, int]]:\n    """Four inner-corner tiles around the shed, NWSE order.\n\n    Mirrors kaggle-environments==1.29.3\'s kaggriculture.py `_shed_access_tiles`.\n    """\n    half = board_size // 2\n    return [(half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half)]\n\n\ndef one_time_crop_watering_bonus_window(crop: str) -> tuple[int, int]:\n    """Inclusive (start, end) age-in-days window where watering adds yield.\n\n    Mirrors kaggle-environments==1.29.3\'s kaggriculture.py:368-382\n    (`WATER` handler): window starts at\n    `(max_yield_day + 1) // 2` (== ceil(max_yield_day / 2)) through\n    `max_yield_day` inclusive. Only meaningful for non-ongoing crops.\n    """\n    cd = CROPS[crop]\n    if cd["ongoing"]:\n        raise ValueError(f"{crop} is an ongoing-yield crop, not one-time")\n    start = (cd["max_yield_day"] + 1) // 2\n    return start, cd["max_yield_day"]\n\n\ndef ongoing_crop_production_days(crop: str) -> list[int]:\n    """Days-since-planting (0-indexed) on which an ongoing crop ticks yield.\n\n    Mirrors kaggle-environments==1.29.3\'s kaggriculture.py:731-766\n    (`_daily_refresh_plants`): production\n    ticks when `(day_since_planting - first_yield_day) % interval == 0`,\n    for up to `max_yield` ticks.\n    """\n    cd = CROPS[crop]\n    if not cd["ongoing"]:\n        raise ValueError(f"{crop} is a one-time-yield crop, not ongoing")\n    days = []\n    tick = 0\n    day = cd["first_yield_day"]\n    while tick < cd["max_yield"]:\n        days.append(day)\n        tick += 1\n        day += cd["interval"]\n    return days\n\n\ndef animal_production_days(animal: str) -> list[int]:\n    """Days-since-placement (0-indexed) on which an animal ticks a base yield.\n\n    Mirrors kaggle-environments==1.29.3\'s kaggriculture.py:767-797\n    (`_daily_refresh_animals`). Does not\n    include CARE-bonus timing, which depends on per-day feed/care history\n    rather than a fixed schedule.\n    """\n    a = ANIMALS[animal]\n    days = []\n    tick = 0\n    day = a["first_yield_day"]\n    while tick < a["max_held"]:\n        days.append(day)\n        tick += 1\n        day += a["interval"]\n    return days\n\n\nDEFAULT_EPISODE_STEPS = 720\nDEFAULT_TURNS_PER_DAY = 24\n\n\ndef last_day_index(config: dict | None) -> int:\n    """0-indexed final day of the season, from the real episode config.\n\n    Promoted from `agents/roi_teacher_v3/main.py`\'s `_last_day_index` (see\n    the approved `task_teacher_v1` design in\n    docs/superpowers/specs/2026-08-01-kaggriculture-competition-plan-design.md):\n    every agent version that reasons about remaining season length needs\n    the identical calculation, not a per-agent reimplementation.\n    """\n    episode_steps = config.get("episodeSteps", DEFAULT_EPISODE_STEPS) if config else DEFAULT_EPISODE_STEPS\n    turns_per_day = config.get("turnsPerDay", DEFAULT_TURNS_PER_DAY) if config else DEFAULT_TURNS_PER_DAY\n    season_days = episode_steps // turns_per_day\n    return season_days - 1\n\n\ndef can_mature_in_time(crop: str, current_day: int, last_day: int) -> bool:\n    """True iff a one-time crop planted today reaches `max_yield_day` age on\n    or before the season\'s last day, leaving turns that day to harvest.\n\n    Promoted from `agents/roi_teacher_v3/main.py`\'s `_can_mature_in_time`.\n    """\n    return current_day + CROPS[crop]["max_yield_day"] <= last_day\n\n\ndef can_ongoing_crop_reach_any_tick(crop: str, current_day: int, last_day: int) -> bool:\n    """True iff an ongoing crop planted today reaches at least one\n    production tick on or before the season\'s last day.\n\n    Generalizes `can_mature_in_time` (a single-maturity-day check) to a\n    crop whose value accrues over a multi-tick schedule instead of one\n    event -- see `ongoing_crop_production_days`.\n    """\n    if not CROPS[crop]["ongoing"]:\n        raise ValueError(f"{crop} is a one-time-yield crop, not ongoing")\n    return any(current_day + offset <= last_day for offset in ongoing_crop_production_days(crop))\n\n\ndef wheat_reserved_for_feed(geese_count: int, days_horizon: int) -> int:\n    """Wheat units to keep (not sell) so geese can be fed for `days_horizon` days."""\n    if geese_count <= 0 or days_horizon <= 0:\n        return 0\n    return geese_count * days_horizon\n\n\ndef one_time_crop_static_yield_per_tile_day(crop: str, watered_in_window: bool = True) -> float:\n    """Simple static estimate of average yield/tile/day over the crop\'s life.\n\n    Not a substitute for simulating an actual play line — ignores fertilizer,\n    weeds, and opportunity cost of the farmer\'s actions to water/harvest.\n    Intended as a first-pass ranking signal for `docs/3_agent_strategy.md`,\n    matching the design doc\'s Phase-1 "static $/tile/day tables" deliverable.\n    """\n    cd = CROPS[crop]\n    base_units = 1  # tile always yields >= 1 unit on harvest (see 1.29.3\'s kaggriculture.py:198-211, `_new_plant`)\n    if watered_in_window:\n        start, end = one_time_crop_watering_bonus_window(crop)\n        bonus_days = end - start + 1\n        base_units += bonus_days  # +1 unit per watered day in the bonus window\n    base_units = min(base_units, cd["max_yield"])\n    lifespan_days = cd["max_yield_day"] + 1  # decay begins one day after max_yield_day\n    return base_units / lifespan_days\n'
economy = _register_shared_module('kaggriculture_lib.economy', _economy_source, 'kaggriculture_lib/economy.py')
_kaggriculture_lib.economy = economy

_tasking_source = '"""Multi-tile task scheduling for task_teacher_v* agents.\n\nData model and scheduling logic per the approved design in\ndocs/superpowers/specs/2026-08-01-kaggriculture-competition-plan-design.md\n("task_teacher_v1: final design"). Shared across every task_teacher_v*\nversion the way economy.py is shared across ROI decisions — stable\ninterfaces, additive evolution as new task/resource types arrive (not\npromised to stay unchanged through v2-v6).\n"""\n\nfrom __future__ import annotations\n\nimport itertools\nfrom dataclasses import dataclass, field\nfrom enum import Enum, IntEnum\n\nfrom kaggriculture_lib import economy\n\n\nclass TaskKind(str, Enum):\n    PLANT = "PLANT"\n    WATER = "WATER"\n    HARVEST = "HARVEST"\n    DIG = "DIG"\n    BUILD_COOP = "BUILD_COOP"\n    BUILD_PASTURE = "BUILD_PASTURE"\n    PLACE = "PLACE"\n    FEED = "FEED"\n    CARE = "CARE"\n    PICKUP = "PICKUP"\n\n\nclass PriorityTier(IntEnum):\n    """Lexicographic safety-first ordering. Lower sorts first (higher priority)."""\n\n    EMERGENCY = 0\n    DECAYING_YIELD = 1\n    DAILY_CARE = 2\n    ECONOMIC = 3\n    OPTIONAL = 4\n\n\n@dataclass(frozen=True, order=True)\nclass TaskId:\n    """Canonical, stable identity for a task instance."""\n\n    kind: TaskKind\n    x: int\n    y: int\n    item: str | None = None\n\n\n@dataclass(frozen=True)\nclass ResourceNeed:\n    item: str\n    quantity: int\n    source: str  # "SEED" | "SHED" | "INVENTORY"\n\n\n@dataclass(frozen=True)\nclass Task:\n    """One candidate action, generated fresh from farm state every turn."""\n\n    task_id: TaskId\n    target: tuple[int, int]\n    priority_tier: PriorityTier\n    deadline_step: int | None\n    expected_value: float\n    action_cost: int\n    resource_needs: tuple[ResourceNeed, ...] = ()\n\n\n@dataclass\nclass ReservationLedger:\n    """Per-turn reservations so multiple units can\'t select conflicting tasks.\n\n    Movement cells are never reserved (this game has no movement collision —\n    see docs/2_environment_notes.md).\n    """\n\n    task_by_tile: dict[tuple[int, int], TaskId]\n    resources: dict[tuple[str, str], int]\n    budget: float\n\n\ndef _quadrant_of(x: int, y: int, board_size: int) -> str:\n    """Mirrors kaggle-environments==1.29.3\'s kaggriculture.py:110-112 (`_quadrant_of`)."""\n    half = board_size // 2\n    return ("N" if y < half else "S") + ("W" if x < half else "E")\n\n\ndef _expected_total_units(crop: str) -> int:\n    """Total harvestable units assuming watering every day in the bonus window."""\n    cd = economy.CROPS[crop]\n    start, end = economy.one_time_crop_watering_bonus_window(crop)\n    bonus_days = end - start + 1\n    return min(cd["max_yield"], 1 + bonus_days)\n\n\ndef _score_crop(crop: str, price: float) -> float:\n    """Static $/day ROI estimate, same formula as roi_teacher_v1-v3."""\n    cd = economy.CROPS[crop]\n    lifespan_days = cd["max_yield_day"] + 1\n    revenue = _expected_total_units(crop) * price\n    return (revenue - cd["seed"]) / lifespan_days\n\n\ndef _score_ongoing_crop(crop: str, price: float, current_day: int, last_day: int) -> float:\n    """Day-aware $/day ROI estimate for an ongoing crop planted *today*.\n\n    Generalizes `_score_crop` to a multi-tick lifecycle: only ticks that\n    actually land on or before `last_day` count toward revenue, and the\n    lifespan denominator is days from planting through the last reachable\n    tick (`reachable[-1] + 1`), mirroring one-time crops\' `max_yield_day + 1`.\n    Only meaningful once `economy.can_ongoing_crop_reach_any_tick` has\n    already confirmed at least one tick is reachable.\n    """\n    offsets = economy.ongoing_crop_production_days(crop)\n    reachable = [o for o in offsets if current_day + o <= last_day]\n    revenue = len(reachable) * price\n    cost = economy.CROPS[crop]["seed"]\n    lifespan_days = reachable[-1] + 1\n    return (revenue - cost) / lifespan_days\n\n\ndef _best_feasible_crop(\n    day: int, last_day: int, market_prices: dict[str, float], candidate_crops: tuple[str, ...]\n) -> str | None:\n    scored: list[tuple[float, str]] = []\n    for crop in candidate_crops:\n        cd = economy.CROPS[crop]\n        price = market_prices.get(crop, cd["seed"])\n        if cd["ongoing"]:\n            if not economy.can_ongoing_crop_reach_any_tick(crop, day, last_day):\n                continue\n            score = _score_ongoing_crop(crop, price, day, last_day)\n        else:\n            if not economy.can_mature_in_time(crop, day, last_day):\n                continue\n            score = _score_crop(crop, price)\n        scored.append((score, crop))\n    if not scored:\n        return None\n    return max(scored, key=lambda pair: pair[0])[1]\n\n\ndef _board_has_coop(tiles: list[list], unlocked: set[str], board_size: int) -> bool:\n    """Whether any COOP structure (empty or occupied) already exists on an\n    unlocked tile, so `want_coop` never queues a redundant BUILD_COOP."""\n    for y in range(board_size):\n        for x in range(board_size):\n            if _quadrant_of(x, y, board_size) not in unlocked:\n                continue\n            tile = tiles[y][x]\n            if isinstance(tile, dict) and tile.get("kind") == "COOP":\n                return True\n    return False\n\n\ndef _first_empty_unlocked_build_target(\n    tiles: list[list],\n    unlocked: set[str],\n    board_size: int,\n    exclude: set[tuple[int, int]] | None = None,\n) -> tuple[int, int] | None:\n    """Pick where a BUILD_COOP / BUILD_PASTURE should land: prefer the first\n    empty, unlocked shed-access tile (keeps the structure close to where\n    PICKUP/PLACE happen), else fall back to the first empty unlocked tile in\n    scan order. `exclude` skips tiles already claimed by another build this turn.\n    """\n    skip = exclude or set()\n    access_tiles = [\n        (ax, ay)\n        for ax, ay in economy.shed_access_tiles(board_size)\n        if _quadrant_of(ax, ay, board_size) in unlocked\n        and tiles[ay][ax] is None\n        and (ax, ay) not in skip\n    ]\n    if access_tiles:\n        return access_tiles[0]\n\n    for y in range(board_size):\n        for x in range(board_size):\n            if (x, y) in skip:\n                continue\n            if _quadrant_of(x, y, board_size) in unlocked and tiles[y][x] is None:\n                return (x, y)\n    return None\n\n\ndef _cap_feed_tasks(tasks: list[Task], max_feed_tasks: int | None) -> list[Task]:\n    """Keep at most `max_feed_tasks` FEED tasks, preferring lower (more urgent) tiers."""\n    if max_feed_tasks is None:\n        return tasks\n    feed = [t for t in tasks if t.task_id.kind == TaskKind.FEED]\n    if len(feed) <= max_feed_tasks:\n        return tasks\n    feed_sorted = sorted(feed, key=lambda t: (t.priority_tier, t.task_id.y, t.task_id.x))\n    keep = set(id(t) for t in feed_sorted[:max_feed_tasks])\n    return [t for t in tasks if t.task_id.kind != TaskKind.FEED or id(t) in keep]\n\n\ndef generate_tasks(\n    tiles: list[list],\n    unlocked_quadrants: list[str],\n    day: int,\n    last_day: int,\n    market_prices: dict[str, float],\n    candidate_crops: tuple[str, ...],\n    board_size: int = 10,\n    shed: dict | None = None,\n    want_coop: bool = False,\n    goose_in_any_inventory: bool = False,\n    wheat_needed_for_feed: bool = False,\n    want_pasture: bool = False,\n    cow_in_any_inventory: bool = False,\n    sheep_in_any_inventory: bool = False,\n    max_feed_tasks: int | None = None,\n    non_emergency_feed_tier: PriorityTier = PriorityTier.DAILY_CARE,\n    care_tier: PriorityTier = PriorityTier.DAILY_CARE,\n) -> list[Task]:\n    """Regenerate the full task list fresh from current farm state.\n\n    Tasks are derived state, never persisted themselves (see `TeacherState`,\n    which persists only the unit -> `TaskId` assignment). One-time crops\n    only, per `task_teacher_v1`\'s scope.\n\n    Pasture/cow kwargs and FEED/CARE tier overrides are additive: defaults\n    preserve the Goose path used by `task_teacher_v4`.\n    """\n    tasks: list[Task] = []\n    unlocked = set(unlocked_quadrants)\n\n    has_empty_coop = False\n    has_empty_pasture = False\n    coop_planned = False\n    pasture_planned = False\n    coop_build_target = (\n        None\n        if not want_coop or _board_has_coop(tiles, unlocked, board_size)\n        else _first_empty_unlocked_build_target(tiles, unlocked, board_size)\n    )\n    # Unlike coop (v4 only ever builds one structure while any coop exists),\n    # pastures must scale with MAX_COWS — agent sets want_pasture only when\n    # there is no empty pasture, so occupied pastures must not block builds.\n    pasture_exclude = {coop_build_target} if coop_build_target is not None else set()\n    pasture_allowed_quads = unlocked - {"NW"} if len(unlocked) > 1 else unlocked\n    pasture_build_target = (\n        None\n        if not want_pasture\n        else _first_empty_unlocked_build_target(tiles, pasture_allowed_quads, board_size, exclude=pasture_exclude)\n    )\n\n    for y in range(board_size):\n        for x in range(board_size):\n            if _quadrant_of(x, y, board_size) not in unlocked:\n                continue\n            tile = tiles[y][x]\n\n            if tile is None:\n                if want_coop and not coop_planned and (x, y) == coop_build_target:\n                    coop_planned = True\n                    tasks.append(\n                        Task(\n                            task_id=TaskId(kind=TaskKind.BUILD_COOP, x=x, y=y),\n                            target=(x, y),\n                            priority_tier=PriorityTier.ECONOMIC,\n                            deadline_step=None,\n                            expected_value=0.0,\n                            action_cost=1,\n                        )\n                    )\n                    continue\n                if want_pasture and not pasture_planned and (x, y) == pasture_build_target:\n                    pasture_planned = True\n                    # DAILY_CARE (not ECONOMIC/0-value): Melon PLANT otherwise\n                    # always outranks BUILD_PASTURE and cows rot in the shed.\n                    tasks.append(\n                        Task(\n                            task_id=TaskId(kind=TaskKind.BUILD_PASTURE, x=x, y=y),\n                            target=(x, y),\n                            priority_tier=PriorityTier.DAILY_CARE,\n                            deadline_step=None,\n                            expected_value=0.0,\n                            action_cost=1,\n                        )\n                    )\n                    continue\n                crop = _best_feasible_crop(day, last_day, market_prices, candidate_crops)\n                if crop is None:\n                    continue\n                cd = economy.CROPS[crop]\n                price = market_prices.get(crop, cd["seed"])\n                value = (\n                    _score_ongoing_crop(crop, price, day, last_day)\n                    if cd["ongoing"]\n                    else _score_crop(crop, price)\n                )\n                tasks.append(\n                    Task(\n                        task_id=TaskId(kind=TaskKind.PLANT, x=x, y=y, item=crop),\n                        target=(x, y),\n                        priority_tier=PriorityTier.ECONOMIC,\n                        deadline_step=None,\n                        expected_value=value,\n                        action_cost=1,\n                        resource_needs=(ResourceNeed(item=crop, quantity=1, source="SEED"),),\n                    )\n                )\n\n            elif isinstance(tile, dict) and tile.get("kind") == "COOP" and "animal" not in tile:\n                has_empty_coop = True\n                if goose_in_any_inventory:\n                    tasks.append(\n                        Task(\n                            task_id=TaskId(kind=TaskKind.PLACE, x=x, y=y, item="GOOSE"),\n                            target=(x, y),\n                            priority_tier=PriorityTier.EMERGENCY,\n                            deadline_step=None,\n                            expected_value=0.0,\n                            action_cost=1,\n                            resource_needs=(ResourceNeed(item="GOOSE", quantity=1, source="INVENTORY"),),\n                        )\n                    )\n\n            elif isinstance(tile, dict) and tile.get("kind") == "PASTURE" and "animal" not in tile:\n                has_empty_pasture = True\n                if cow_in_any_inventory:\n                    tasks.append(\n                        Task(\n                            task_id=TaskId(kind=TaskKind.PLACE, x=x, y=y, item="COW"),\n                            target=(x, y),\n                            priority_tier=PriorityTier.EMERGENCY,\n                            deadline_step=None,\n                            expected_value=0.0,\n                            action_cost=1,\n                            resource_needs=(ResourceNeed(item="COW", quantity=1, source="INVENTORY"),),\n                        )\n                    )\n                if sheep_in_any_inventory:\n                    tasks.append(\n                        Task(\n                            task_id=TaskId(kind=TaskKind.PLACE, x=x, y=y, item="SHEEP"),\n                            target=(x, y),\n                            priority_tier=PriorityTier.EMERGENCY,\n                            deadline_step=None,\n                            expected_value=0.0,\n                            action_cost=1,\n                            resource_needs=(ResourceNeed(item="SHEEP", quantity=1, source="INVENTORY"),),\n                        )\n                    )\n\n            elif isinstance(tile, dict) and tile.get("kind") == "PLANT":\n                cd = economy.CROPS[tile["crop"]]\n                if not tile["watered_today"]:\n                    tier = PriorityTier.EMERGENCY if tile["consecutive_unwatered"] >= 1 else PriorityTier.DAILY_CARE\n                    tasks.append(\n                        Task(\n                            task_id=TaskId(kind=TaskKind.WATER, x=x, y=y),\n                            target=(x, y),\n                            priority_tier=tier,\n                            deadline_step=None,\n                            expected_value=0.0,\n                            action_cost=1,\n                        )\n                    )\n                elif cd["ongoing"]:\n                    if tile["yield_units"] > 0:\n                        tasks.append(\n                            Task(\n                                task_id=TaskId(kind=TaskKind.HARVEST, x=x, y=y),\n                                target=(x, y),\n                                priority_tier=PriorityTier.DECAYING_YIELD,\n                                deadline_step=None,\n                                expected_value=0.0,\n                                action_cost=1,\n                            )\n                        )\n                elif day - tile["planted_day"] >= cd["max_yield_day"]:\n                    tasks.append(\n                        Task(\n                            task_id=TaskId(kind=TaskKind.HARVEST, x=x, y=y),\n                            target=(x, y),\n                            priority_tier=PriorityTier.DECAYING_YIELD,\n                            deadline_step=None,\n                            expected_value=0.0,\n                            action_cost=1,\n                        )\n                    )\n\n            elif isinstance(tile, dict) and tile.get("kind") == "WEED":\n                tasks.append(\n                    Task(\n                        task_id=TaskId(kind=TaskKind.DIG, x=x, y=y),\n                        target=(x, y),\n                        priority_tier=PriorityTier.DAILY_CARE,\n                        deadline_step=None,\n                        expected_value=0.0,\n                        action_cost=1,\n                    )\n                )\n\n            elif isinstance(tile, dict) and "animal" in tile:\n                if not tile["fed_today"]:\n                    tier = (\n                        PriorityTier.EMERGENCY\n                        if tile.get("consecutive_unfed", 0) >= 1\n                        else non_emergency_feed_tier\n                    )\n                    tasks.append(\n                        Task(\n                            task_id=TaskId(kind=TaskKind.FEED, x=x, y=y),\n                            target=(x, y),\n                            priority_tier=tier,\n                            deadline_step=None,\n                            expected_value=0.0,\n                            action_cost=1,\n                            resource_needs=(ResourceNeed(item="WHEAT", quantity=1, source="INVENTORY"),),\n                        )\n                    )\n                elif tile.get("yield_units", 0) > 0:\n                    tasks.append(\n                        Task(\n                            task_id=TaskId(kind=TaskKind.HARVEST, x=x, y=y),\n                            target=(x, y),\n                            priority_tier=PriorityTier.DECAYING_YIELD,\n                            deadline_step=None,\n                            expected_value=0.0,\n                            action_cost=1,\n                        )\n                    )\n                elif not tile["cared_today"]:\n                    tasks.append(\n                        Task(\n                            task_id=TaskId(kind=TaskKind.CARE, x=x, y=y),\n                            target=(x, y),\n                            priority_tier=care_tier,\n                            deadline_step=None,\n                            expected_value=0.0,\n                            action_cost=1,\n                        )\n                    )\n\n    if shed:\n        access_tiles = [\n            (ax, ay) for ax, ay in economy.shed_access_tiles(board_size) if _quadrant_of(ax, ay, board_size) in unlocked\n        ]\n        if access_tiles:\n            pickup_target = access_tiles[0]\n            if shed.get("GOOSE", 0) > 0 and not goose_in_any_inventory and has_empty_coop:\n                tasks.append(\n                    Task(\n                        task_id=TaskId(kind=TaskKind.PICKUP, x=pickup_target[0], y=pickup_target[1], item="GOOSE"),\n                        target=pickup_target,\n                        priority_tier=PriorityTier.ECONOMIC,\n                        deadline_step=None,\n                        expected_value=0.0,\n                        action_cost=1,\n                        resource_needs=(ResourceNeed(item="GOOSE", quantity=1, source="SHED"),),\n                    )\n                )\n            if shed.get("COW", 0) > 0 and not cow_in_any_inventory and has_empty_pasture:\n                tasks.append(\n                    Task(\n                        task_id=TaskId(kind=TaskKind.PICKUP, x=pickup_target[0], y=pickup_target[1], item="COW"),\n                        target=pickup_target,\n                        priority_tier=PriorityTier.DAILY_CARE,\n                        deadline_step=None,\n                        expected_value=0.0,\n                        action_cost=1,\n                        resource_needs=(ResourceNeed(item="COW", quantity=1, source="SHED"),),\n                    )\n                )\n            elif shed.get("COW", 0) > 0 and not cow_in_any_inventory and want_pasture:\n                tasks.append(\n                    Task(\n                        task_id=TaskId(kind=TaskKind.PICKUP, x=pickup_target[0], y=pickup_target[1], item="COW"),\n                        target=pickup_target,\n                        priority_tier=PriorityTier.DAILY_CARE,\n                        deadline_step=None,\n                        expected_value=0.0,\n                        action_cost=1,\n                        resource_needs=(ResourceNeed(item="COW", quantity=1, source="SHED"),),\n                    )\n                )\n            if shed.get("SHEEP", 0) > 0 and not sheep_in_any_inventory and has_empty_pasture:\n                tasks.append(\n                    Task(\n                        task_id=TaskId(kind=TaskKind.PICKUP, x=pickup_target[0], y=pickup_target[1], item="SHEEP"),\n                        target=pickup_target,\n                        priority_tier=PriorityTier.DAILY_CARE,\n                        deadline_step=None,\n                        expected_value=0.0,\n                        action_cost=1,\n                        resource_needs=(ResourceNeed(item="SHEEP", quantity=1, source="SHED"),),\n                    )\n                )\n            elif shed.get("SHEEP", 0) > 0 and not sheep_in_any_inventory and want_pasture:\n                tasks.append(\n                    Task(\n                        task_id=TaskId(kind=TaskKind.PICKUP, x=pickup_target[0], y=pickup_target[1], item="SHEEP"),\n                        target=pickup_target,\n                        priority_tier=PriorityTier.DAILY_CARE,\n                        deadline_step=None,\n                        expected_value=0.0,\n                        action_cost=1,\n                        resource_needs=(ResourceNeed(item="SHEEP", quantity=1, source="SHED"),),\n                    )\n                )\n            if wheat_needed_for_feed and shed.get("WHEAT", 0) > 0:\n                emergency_feed = False\n                for r in tiles:\n                    for t in r:\n                        if isinstance(t, dict) and "animal" in t and not t["fed_today"]:\n                            if t.get("consecutive_unfed", 0) >= 1:\n                                emergency_feed = True\n                                break\n                    if emergency_feed:\n                        break\n                pickup_tier = PriorityTier.EMERGENCY if emergency_feed else PriorityTier.DAILY_CARE\n                qty = min(6, shed.get("WHEAT", 0))\n                tasks.append(\n                    Task(\n                        task_id=TaskId(kind=TaskKind.PICKUP, x=pickup_target[0], y=pickup_target[1], item="WHEAT"),\n                        target=pickup_target,\n                        # Match FEED urgency so wheat isn\'t stuck behind Melon PLANT.\n                        priority_tier=pickup_tier,\n                        deadline_step=None,\n                        expected_value=0.0,\n                        action_cost=1,\n                        resource_needs=(ResourceNeed(item="WHEAT", quantity=qty, source="SHED"),),\n                    )\n                )\n\n    return _cap_feed_tasks(tasks, max_feed_tasks)\n\n\nHYSTERESIS_BONUS = 0.5  # switch-away penalty, in the same units as expected_value\n\n\ndef rank_tasks(\n    tasks: list[Task],\n    current_position: tuple[int, int],\n    current_assignment: TaskId | None = None,\n) -> list[Task]:\n    """Deterministic full ordering: safety tier first, then nearest, then\n    highest value, with hysteresis toward the current assignment on a near\n    tie, with `task_id` as the final deterministic tiebreak.\n    """\n\n    def _key(task: Task):\n        distance = abs(task.target[0] - current_position[0]) + abs(task.target[1] - current_position[1])\n        switch_penalty = 0.0 if task.task_id == current_assignment else HYSTERESIS_BONUS\n        return (\n            task.priority_tier,\n            distance,\n            -task.expected_value + switch_penalty,\n            task.task_id,\n        )\n\n    return sorted(tasks, key=_key)\n\n\nMAX_CANDIDATES_PER_UNIT = 8\n\n# Exhaustive search is (max_candidates_per_unit + 1)^n_units. Beyond this\n# many units, fall back to a fast deterministic greedy assignment instead\n# -- per the v2 design\'s explicit "if supported unit bounds are exceeded,\n# use a deterministic greedy fallback ... do not fail silently" instruction.\n# Found via a real bug: an uncapped hiring policy let unit count grow\n# large enough (7-8) that exhaustive search over 9^7+ combinations made a\n# single full 720-turn episode take ~20s. Measured directly (25 tasks,\n# this repo\'s actual joint_assign): n=4 costs ~8ms/call, n=5 ~70ms, n=6\n# ~650ms -- the jump from n=5 to n=6 is what made whole episodes slow.\n# Capped at 4, matching the v2 design\'s own "expected farmer plus 1-3\n# hands" assumption plus one unit of headroom.\nMAX_EXHAUSTIVE_UNITS = 4\n\n\ndef _task_id_sort_key(task_id: TaskId | None) -> tuple:\n    """Deterministic, always-comparable sort key -- `TaskId`\'s own field\n    order can\'t safely compare `item=None` against `item="CARROT"` across\n    different task kinds, and `None` (PASS) needs to sort against real\n    `TaskId`s too."""\n    if task_id is None:\n        return (1,)\n    return (0, task_id.kind, task_id.x, task_id.y, task_id.item or "")\n\n\ndef _greedy_assign(\n    unit_positions: list[tuple[int, int]],\n    tasks: list[Task],\n    current_assignments: dict[int, TaskId],\n    unit_inventories: list[dict] | None = None,\n) -> dict[int, TaskId | None]:\n    """Deterministic greedy fallback for when there are too many units for\n    exhaustive search: each unit, in order, claims its own top-ranked task\n    from whatever remains unclaimed. Not joint-optimal (an earlier unit can\n    still claim a task a later unit would have been better positioned\n    for), but fast and always correct (no duplicate claims)."""\n    remaining = list(tasks)\n    assignment: dict[int, TaskId | None] = {}\n    for i, pos in enumerate(unit_positions):\n        if not remaining:\n            assignment[i] = None\n            continue\n        unit_tasks = remaining\n        if unit_inventories is not None and i < len(unit_inventories):\n            inv = unit_inventories[i]\n            unit_tasks = []\n            for t in remaining:\n                if t.task_id.kind == TaskKind.PLACE:\n                    item = t.task_id.item\n                    if item and inv.get(item, 0) <= 0:\n                        continue\n                elif t.task_id.kind == TaskKind.FEED:\n                    if inv.get("WHEAT", 0) <= 0:\n                        continue\n                unit_tasks.append(t)\n        if not unit_tasks:\n            assignment[i] = None\n            continue\n        ranked = rank_tasks(unit_tasks, current_position=pos, current_assignment=current_assignments.get(i))\n        chosen = ranked[0]\n        assignment[i] = chosen.task_id\n        remaining = [t for t in remaining if t.task_id != chosen.task_id]\n    return assignment\n\n\ndef _exhaustive_assign(\n    unit_positions: list[tuple[int, int]],\n    tasks: list[Task],\n    current_assignments: dict[int, TaskId],\n    max_candidates_per_unit: int = MAX_CANDIDATES_PER_UNIT,\n    unit_inventories: list[dict] | None = None,\n) -> dict[int, TaskId | None]:\n    """Bounded exhaustive joint assignment across units (farmer + hands).\n\n    Each unit\'s candidate set is its own top `max_candidates_per_unit`\n    feasible tasks (by `rank_tasks` from that unit\'s position) plus an\n    implicit `PASS` (`None`). Every combination that doesn\'t claim the same\n    task twice is scored by, in order: how many tasks get covered per\n    priority tier (more coverage of higher tiers always wins, checked\n    tier-by-tier before anything else), total travel distance, total\n    expected value, then a deterministic tiebreak.\n\n    This is what makes it superior to a naive "each unit picks its own\n    top-ranked task first" sequential pass: that lets an earlier-decided\n    unit claim a task purely because of its own ranking (e.g. tier\n    dominates distance), even when a later unit is better positioned for\n    it — see `docs/superpowers/specs/2026-08-01-task-teacher-v2-design.md`.\n\n    Factored out of `joint_assign` (which applies the `MAX_EXHAUSTIVE_UNITS`\n    production cap) so offline measurement tooling can invoke exhaustive\n    search directly on larger unit counts to quantify the greedy fallback\'s\n    quality gap (`docs/6_next_steps.md` item 15) -- exponential cost is\n    acceptable for that one-off analysis even though it\'s too slow per-turn.\n    """\n    task_by_id = {t.task_id: t for t in tasks}\n    n_tiers = len(PriorityTier)\n\n    candidate_lists: list[list[TaskId | None]] = []\n    for i, pos in enumerate(unit_positions):\n        unit_tasks = tasks\n        if unit_inventories is not None and i < len(unit_inventories):\n            inv = unit_inventories[i]\n            unit_tasks = []\n            for t in tasks:\n                if t.task_id.kind == TaskKind.PLACE:\n                    item = t.task_id.item\n                    if item and inv.get(item, 0) <= 0:\n                        continue\n                elif t.task_id.kind == TaskKind.FEED:\n                    if inv.get("WHEAT", 0) <= 0:\n                        continue\n                unit_tasks.append(t)\n        ranked = rank_tasks(unit_tasks, current_position=pos, current_assignment=current_assignments.get(i))\n        candidate_lists.append([t.task_id for t in ranked[:max_candidates_per_unit]] + [None])\n\n    best_key = None\n    best_combo: tuple[TaskId | None, ...] = tuple(None for _ in unit_positions)\n\n    for combo in itertools.product(*candidate_lists):\n        claimed = [tid for tid in combo if tid is not None]\n        if len(claimed) != len(set(claimed)):\n            continue  # duplicate claim this combination -- invalid\n\n        tier_counts = [0] * n_tiers\n        total_distance = 0\n        total_value = 0.0\n        for i, tid in enumerate(combo):\n            if tid is None:\n                continue\n            task = task_by_id[tid]\n            tier_counts[task.priority_tier] += 1\n            total_distance += abs(task.target[0] - unit_positions[i][0]) + abs(task.target[1] - unit_positions[i][1])\n            total_value += task.expected_value\n\n        key = (\n            tuple(-c for c in tier_counts),  # more coverage per tier wins, tier order first\n            total_distance,\n            -total_value,\n            tuple(_task_id_sort_key(tid) for tid in combo),\n        )\n        if best_key is None or key < best_key:\n            best_key = key\n            best_combo = combo\n\n    return dict(enumerate(best_combo))\n\n\ndef joint_assign(\n    unit_positions: list[tuple[int, int]],\n    tasks: list[Task],\n    current_assignments: dict[int, TaskId],\n    max_candidates_per_unit: int = MAX_CANDIDATES_PER_UNIT,\n    unit_inventories: list[dict] | None = None,\n) -> dict[int, TaskId | None]:\n    """Bounded exhaustive joint assignment across units (farmer + hands),\n    falling back to `_greedy_assign` (fast, not joint-optimal) if there are\n    more than `MAX_EXHAUSTIVE_UNITS` units, since exhaustive search over\n    `(max_candidates_per_unit + 1) ** len(unit_positions)` combinations\n    becomes impractically slow well before that. See `_exhaustive_assign`\n    for the scoring objective.\n    """\n    if len(unit_positions) > MAX_EXHAUSTIVE_UNITS:\n        return _greedy_assign(unit_positions, tasks, current_assignments, unit_inventories)\n    return _exhaustive_assign(unit_positions, tasks, current_assignments, max_candidates_per_unit, unit_inventories)\n\n\n@dataclass(frozen=True)\nclass MarketIntent:\n    """A future-turn market order: buying this now doesn\'t make a task\n    executable this same turn (unit actions execute before market actions,\n    per the game\'s turn processing order)."""\n\n    item: str\n    quantity: int\n    reason: str  # e.g. "PLANT" -- why this intent was created\n\n\n# Calibrated constants for the service-capacity load check (§ below).\n# A 2026-08-02 recalibration attempt (TRAVEL_ALLOWANCE 4->8,\n# AVERAGE_VALUE_PER_RECOVERED_ACTION 15.0->65.0 below, from real\n# task_teacher_v2 telemetry) was reverted after full-gate re-evaluation\n# showed it was a net regression, not an improvement -- see\n# docs/4_agent_version_log.md and\n# docs/superpowers/specs/2026-08-01-task-teacher-v2-design.md §23 for the\n# full account of why a single-shot measurement under one hiring regime\n# didn\'t transfer once it changed that regime. Kept at the original,\n# already-evaluated values pending a non-naive recalibration approach.\nTRAVEL_ALLOWANCE = 4  # turns/day reserved for moving between tiles\nEND_OF_DAY_RESERVE = 2  # turns/day reserved for selling/end-of-day cleanup\n\n\ndef project_daily_load(\n    pending_water_tiles: int, scheduled_plant_actions: int, scheduled_harvest_actions: int\n) -> int:\n    """O(1) service-capacity estimate — a load-accounting check, not a\n    lookahead planner. Sums known daily obligations (watering every owned\n    tile) plus this turn\'s proposed new work (planting, harvesting) plus\n    two calibrated constants for travel and end-of-day selling/cleanup.\n    """\n    return pending_water_tiles + scheduled_plant_actions + scheduled_harvest_actions + TRAVEL_ALLOWANCE + END_OF_DAY_RESERVE\n\n\n# Calibration constant for the hiring decision (task_teacher_v2): estimated\n# dollar value of one recovered service-capacity turn. Measured 2026-08-02\n# at $65.26/action under the original (less-aggressive) hiring behavior --\n# but plugging that number back in drove much more aggressive hiring (flat\n# 7 hands, ~111 hire orders/episode vs. the original ~71), which measurably\n# hurt win rate against task_teacher_v1 (0.970 -> 0.750 over 50 pairs, CI\n# dropping from [0.730, 1.000] to a barely-above-0.50 [0.510, 0.990]) --\n# see docs/4_agent_version_log.md for the full account. Reverted to the\n# original estimate, which is a worse point estimate of $/action but a\n# better-performing operating point once its own feedback effect on\n# hiring behavior is accounted for.\nAVERAGE_VALUE_PER_RECOVERED_ACTION = 15.0\n\nLAND_MIN_DAYS_REMAINING = 12\nLAND_BUDGET_RESERVE = 400\nMIN_HANDS_BEFORE_LAND = 3\n# Measured 2026-08-10: Melon-heavy v4 peaks at ~16–20 concurrent plants, but\n# usually only after day ~19 when LAND_MIN_DAYS_REMAINING already fails. Floor\n# 12 fires while the season window is still open (10/10 probe seeds) without\n# dropping the hire_v==0 / hand-floor gates.\nNW_SATURATION_PLANTS = 12\n\n\ndef estimate_hire_value(projected_load: int, remaining_turns_today: int, existing_hands: int = 0) -> float:\n    """Estimated dollar value of hiring one *more* hand today.\n\n    Value only exists if the projected service load exceeds the capacity\n    already available today — every existing unit (the farmer, plus each\n    hand already hired today) already contributes `remaining_turns_today`\n    of capacity, so hiring hand N+1 is only valuable if load still exceeds\n    what N hands (plus the farmer) can already absorb. Without this, a\n    static load estimate never decreases as hands are hired and\n    `should_hire` would keep approving hire after hire in the same day —\n    a real bug found via a full simulator run, where the resulting unit\n    count made `joint_assign`\'s combinatorial search explode. The\n    recovered-turns proxy is additionally capped at how many turns are\n    left today, since a hand can\'t do more work today than today has turns\n    for.\n    """\n    existing_capacity = remaining_turns_today * (1 + existing_hands)  # farmer + hired hands\n    overload = projected_load - existing_capacity\n    if overload <= 0:\n        return 0.0\n    recovered_turns = min(overload, remaining_turns_today)\n    return recovered_turns * AVERAGE_VALUE_PER_RECOVERED_ACTION\n\n\ndef should_hire(\n    projected_load: int,\n    remaining_turns_today: int,\n    hires_today: int,\n    money: float,\n    safety_margin: float = 0.0,\n    existing_hands: int = 0,\n    hire_cost_mult: int = economy.FARM_HAND_COST_MULT,\n) -> bool:\n    """Whether hiring one more hand today clears its fibonacci-scaled cost.\n\n    Per the v2 design: hire only when the estimated recovered value\n    exceeds the next hire\'s cost plus a configurable safety margin, and\n    only if affordable at all. Not a diversity-seeking heuristic — value\n    must be real and load-driven, per the design\'s explicit "do not hire\n    merely to create training action diversity" rule.\n\n    `hire_cost_mult` defaults to the 1.29.3 library constant (10). Ladder-\n    match agents should pass `economy.hire_cost_mult(config)` (often 1).\n    """\n    cost = economy.hire_cost(hires_today, mult=hire_cost_mult)\n    if money < cost:\n        return False\n    value = estimate_hire_value(projected_load, remaining_turns_today, existing_hands)\n    return value > cost + safety_margin\n\n\n# Default cash floor for the second extra quadrant (SW @ $2000).\nSW_BUDGET_RESERVE = 3000\nSW_MIN_PLANTS = 20\n\n\ndef should_buy_land(\n    unlocked_quadrants: list[str],\n    money: float,\n    projected_load: int,\n    remaining_turns_today: int,\n    existing_hands: int,\n    day: int,\n    last_day: int,\n    reserved_for_hire: float,\n    plant_tile_count: int,\n    budget_reserve: float = LAND_BUDGET_RESERVE,\n    max_extra_quadrants: int = 1,\n    sw_budget_reserve: float = SW_BUDGET_RESERVE,\n    sw_min_plants: int = SW_MIN_PLANTS,\n) -> bool:\n    """Whether to emit BUY_LAND this turn.\n\n    Default `max_extra_quadrants=1` preserves v4/v5 NE-only behavior.\n    With `max_extra_quadrants=2`, a second buy (SW) is allowed after NE\n    when plants/cash clear the SW gates.\n    """\n    n_extra = len(unlocked_quadrants) - 1\n    if n_extra < 0 or n_extra >= max_extra_quadrants:\n        return False\n    if existing_hands < MIN_HANDS_BEFORE_LAND:\n        return False\n    if last_day - day < LAND_MIN_DAYS_REMAINING:\n        return False\n    if estimate_hire_value(projected_load, remaining_turns_today, existing_hands) > 0:\n        return False\n\n    if n_extra == 0:\n        if plant_tile_count < NW_SATURATION_PLANTS:\n            return False\n        cost = economy.land_cost(0)\n        reserve = budget_reserve\n    else:\n        # Second extra → SW at LAND_PRICES[1].\n        if plant_tile_count < sw_min_plants:\n            return False\n        cost = economy.land_cost(1)\n        reserve = sw_budget_reserve\n\n    if cost is None:\n        return False\n    if money - reserved_for_hire < cost + reserve:\n        return False\n    return True\n\n\ndef route_toward(\n    current: tuple[int, int], target: tuple[int, int], tiles: list[list], board_size: int\n) -> str:\n    """Deterministic greedy Manhattan routing: horizontal first unless that\n    move would enter a locked tile, then vertical. Confirmed no obstacles\n    exist in this game besides board bounds and locked quadrants (plants,\n    weeds, structures, and other units never block movement — see\n    docs/2_environment_notes.md) — a BFS pathfinder is unnecessary.\n    """\n    cx, cy = current\n    tx, ty = target\n    if current == target:\n        return "PASS"\n\n    candidates: list[tuple[str, int, int]] = []\n    if tx > cx:\n        candidates.append(("EAST", cx + 1, cy))\n    elif tx < cx:\n        candidates.append(("WEST", cx - 1, cy))\n    if ty > cy:\n        candidates.append(("SOUTH", cx, cy + 1))\n    elif ty < cy:\n        candidates.append(("NORTH", cx, cy - 1))\n\n    for op, nx, ny in candidates:\n        if 0 <= nx < board_size and 0 <= ny < board_size and tiles[ny][nx] != "LOCKED":\n            return op\n    return "PASS"\n\n\n@dataclass\nclass TeacherState:\n    """Explicit, caller-owned state — never read/written via module globals.\n\n    Reset on an observed game-state signal (`obs["step"] == 0` or\n    `obs["step"] < previous_step`), not on module-load lifecycle: verified\n    empirically that kaggle_environments\' file-agent loader happens to give\n    a fresh module exec per `env.run()`, but that\'s an implementation detail\n    of one calling path, not a guarantee for direct unit-test calls, BC\n    trajectory generation, or interleaved parallel rollout workers.\n    """\n\n    assignments: dict[int, TaskId] = field(default_factory=dict)\n    previous_step: int = -1\n    previous_day: int = -1\n\n    def reset(self) -> None:\n        self.assignments.clear()\n        self.previous_step = -1\n        self.previous_day = -1\n\n\ndef reset_hand_assignments_on_day_change(state: TeacherState, day: int) -> None:\n    """Clear non-farmer (unit index > 0) assignments when `day` changes.\n\n    Both the farmer\'s position and every hired hand reset unconditionally\n    at every end-of-day boundary in the real game (confirmed against\n    kaggriculture.py\'s `_end_of_day`) — a hand\'s index identity in\n    `obs["farms"][player]["hands"]` never survives a day boundary, even if\n    an identical hand is re-hired. The farmer\'s own assignment (unit 0)\n    is left untouched here; it revalidates naturally next turn, since\n    `rank_tasks`/`joint_assign` only apply hysteresis when the persisted\n    `TaskId` still matches a freshly generated task.\n    """\n    if day != state.previous_day:\n        state.assignments = {unit: task_id for unit, task_id in state.assignments.items() if unit == 0}\n        state.previous_day = day\n'
tasking = _register_shared_module('kaggriculture_lib.tasking', _tasking_source, 'kaggriculture_lib/tasking.py')
_kaggriculture_lib.tasking = tasking


"""Kaggriculture multi-tile task/route teacher agent, v11 (v10 + 4-quadrant unlocking + scaled hands floor).
"""


from kaggriculture_lib import economy
from kaggriculture_lib.tasking import (
    PriorityTier,
    TaskKind,
    TeacherState,
    generate_tasks,
    joint_assign,
    project_daily_load,
    reset_hand_assignments_on_day_change,
    route_toward,
    should_buy_land,
    should_hire,
)

CANDIDATE_CROPS = ("WHEAT", "CARROT", "MELON")
DEFAULT_TURNS_PER_DAY = 24

MAX_GEESE = 4
MAX_COWS = 8
MAX_SHEEP = 4
MAX_FEED_ACTIONS_PER_DAY = 10

COW_COST = economy.ANIMALS["COW"]["cost"]      # 600
SHEEP_COST = economy.ANIMALS["SHEEP"]["cost"]  # 500
GOOSE_COST = economy.ANIMALS["GOOSE"]["cost"]  # 300

_state = TeacherState()


def _reset_if_new_episode(state: TeacherState, step: int) -> None:
    if step == 0 or step < state.previous_step:
        state.reset()
    state.previous_step = step


def _count_immediately_completing_tasks(unit_positions, assignment, task_by_id, seeds_remaining) -> int:
    """Count assigned units already standing on crop WATER/PLANT/HARVEST tiles."""
    available_seeds = dict(seeds_remaining)
    count = 0
    for unit_idx in sorted(assignment):
        task_id = assignment[unit_idx]
        if task_id is None or task_id.kind not in (TaskKind.WATER, TaskKind.PLANT, TaskKind.HARVEST):
            continue
        task = task_by_id.get(task_id)
        if task is None or unit_positions[unit_idx] != task.target:
            continue
        if task_id.kind == TaskKind.PLANT:
            crop = task_id.item
            if available_seeds.get(crop, 0) <= 0:
                continue
            available_seeds[crop] -= 1
        count += 1
    return count


def _farm_stats(tiles: list[list]) -> dict:
    stats = {
        "placed_cows": 0,
        "placed_sheep": 0,
        "placed_geese": 0,
        "unfed_cows": 0,
        "unfed_sheep": 0,
        "unfed_geese": 0,
        "empty_pastures": 0,
        "empty_coops": 0,
        "plant_tiles": 0,
    }
    for row in tiles:
        for tile in row:
            if not isinstance(tile, dict):
                continue
            animal = tile.get("animal")
            if animal == "COW":
                stats["placed_cows"] += 1
                if not tile["fed_today"]:
                    stats["unfed_cows"] += 1
            elif animal == "SHEEP":
                stats["placed_sheep"] += 1
                if not tile["fed_today"]:
                    stats["unfed_sheep"] += 1
            elif animal == "GOOSE":
                stats["placed_geese"] += 1
                if not tile["fed_today"]:
                    stats["unfed_geese"] += 1
            elif tile.get("kind") == "PASTURE" and tile.get("animal") is None:
                stats["empty_pastures"] += 1
            elif tile.get("kind") == "COOP" and tile.get("animal") is None:
                stats["empty_coops"] += 1
            elif tile.get("kind") == "PLANT":
                stats["plant_tiles"] += 1
    return stats


def _owned_animal_count(animal: str, placed: int, shed: dict, inventories: list[dict]) -> int:
    """Placed + shed + inventory counts for an animal type."""
    return (
        placed
        + int(shed.get(animal, 0))
        + sum(int(inv.get(animal, 0)) for inv in inventories)
    )


def agent(obs, config=None):
    _reset_if_new_episode(_state, obs["step"])
    reset_hand_assignments_on_day_change(_state, obs["day"])

    player = obs["player"]
    me = obs["farms"][player]
    private = obs["private"]
    prices = obs["market"]["prices"]
    shed = private["shed"]
    inventories = private["inventories"]
    day = obs["day"]
    hour = obs["hour"]
    board_size = len(me["tiles"])
    turns_per_day = config.get("turnsPerDay", DEFAULT_TURNS_PER_DAY) if config else DEFAULT_TURNS_PER_DAY

    last_day = economy.last_day_index(config)

    stats = _farm_stats(me["tiles"])
    owned_cows = _owned_animal_count("COW", stats["placed_cows"], shed, inventories)
    owned_sheep = _owned_animal_count("SHEEP", stats["placed_sheep"], shed, inventories)
    owned_geese = _owned_animal_count("GOOSE", stats["placed_geese"], shed, inventories)
    
    cow_in_any_inventory = any(inv.get("COW", 0) > 0 for inv in inventories)
    sheep_in_any_inventory = any(inv.get("SHEEP", 0) > 0 for inv in inventories)
    goose_in_any_inventory = any(inv.get("GOOSE", 0) > 0 for inv in inventories)

    animals_unlocked = len(me["unlocked_quadrants"]) >= 2 and day >= 11
    
    total_owned_animals = owned_cows + owned_sheep + owned_geese
    total_max_animals = MAX_COWS + MAX_SHEEP + MAX_GEESE
    
    cow_in_transit = int(shed.get("COW", 0)) + sum(int(inv.get("COW", 0)) for inv in inventories)
    sheep_in_transit = int(shed.get("SHEEP", 0)) + sum(int(inv.get("SHEEP", 0)) for inv in inventories)
    goose_in_transit = int(shed.get("GOOSE", 0)) + sum(int(inv.get("GOOSE", 0)) for inv in inventories)
    animals_in_transit = cow_in_transit + sheep_in_transit + goose_in_transit

    # Build pastures under animal limits
    # Build pastures under animal limits
    total_pastures = stats["placed_cows"] + stats["placed_sheep"] + stats["empty_pastures"]
    want_pasture = (
        animals_unlocked
        and (total_pastures < (owned_cows + cow_in_transit + owned_sheep + sheep_in_transit))
    )

    # Build coops under animal limits
    total_coops = stats["placed_geese"] + stats["empty_coops"]
    want_coop = total_coops < (owned_geese + goose_in_transit)

    wheat_needed_for_feed = stats["unfed_cows"] > 0 or stats["unfed_sheep"] > 0 or stats["unfed_geese"] > 0

    tasks = generate_tasks(
        tiles=me["tiles"],
        unlocked_quadrants=me["unlocked_quadrants"],
        day=day,
        last_day=last_day,
        market_prices=prices,
        candidate_crops=CANDIDATE_CROPS,
        board_size=board_size,
        shed=shed,
        want_coop=want_coop,
        goose_in_any_inventory=goose_in_any_inventory,
        wheat_needed_for_feed=wheat_needed_for_feed,
        want_pasture=want_pasture,
        cow_in_any_inventory=cow_in_any_inventory,
        sheep_in_any_inventory=sheep_in_any_inventory,
        max_feed_tasks=MAX_FEED_ACTIONS_PER_DAY,
        non_emergency_feed_tier=PriorityTier.DAILY_CARE,
        care_tier=PriorityTier.DAILY_CARE,
    )
    task_by_id = {t.task_id: t for t in tasks}

    unit_positions = [tuple(me["farmer"])] + [tuple(h) for h in me["hands"]]
    assignment = joint_assign(unit_positions, tasks, _state.assignments, unit_inventories=inventories)
    _state.assignments = {unit: tid for unit, tid in assignment.items() if tid is not None}

    market_orders: list[list] = []
    
    is_terminal_liquidation = (day == last_day and hour >= 20)
    
    if is_terminal_liquidation:
        # Sell absolutely everything sellable in the shed
        for item in ["WHEAT", "CARROT", "MELON", "STRAWBERRY", "MILK", "WOOL", "EGG", "FERTILIZER"]:
            available = shed.get(item, 0)
            if available > 0:
                market_orders.append(["SELL", item, available])
    else:
        # Normal daily selling
        for crop in ["CARROT", "MELON", "STRAWBERRY"]:
            available = shed.get(crop, 0)
            if available > 0:
                market_orders.append(["SELL", crop, available])
        
        # Sell wheat only if no animals need it for feed
        if (owned_cows == 0 and owned_sheep == 0 and owned_geese == 0):
            available = shed.get("WHEAT", 0)
            if available > 0:
                market_orders.append(["SELL", "WHEAT", available])
                
        for prod in ["MILK", "WOOL", "EGG", "FERTILIZER"]:
            available = shed.get(prod, 0)
            if available > 0:
                market_orders.append(["SELL", prod, available])

    pending_water = sum(1 for t in tasks if t.task_id.kind == TaskKind.WATER)
    pending_plant = sum(1 for t in tasks if t.task_id.kind == TaskKind.PLANT)
    pending_harvest = sum(1 for t in tasks if t.task_id.kind == TaskKind.HARVEST)
    pending_cow = sum(1 for t in tasks if t.task_id.kind in (
        TaskKind.BUILD_PASTURE, TaskKind.BUILD_COOP, TaskKind.PICKUP, TaskKind.PLACE, TaskKind.FEED, TaskKind.CARE
    ))
    load = project_daily_load(pending_water, pending_plant, pending_harvest) + pending_cow
    future_action_turns = max(0, turns_per_day - hour - 1)
    immediately_completing = _count_immediately_completing_tasks(
        unit_positions, assignment, task_by_id, private["seeds"]
    )
    future_load = max(0, load - immediately_completing)

    # Dynamic hands floor based on farm size and cash
    n_quadrants = len(me["unlocked_quadrants"])
    hands_floor = 0
    mult_val = economy.hire_cost_mult(config)
    if day < 10:
        if mult_val >= 5.0:
            hands_floor = 0
        else:
            hands_floor = 3  # Optimal Day 0-9 cheap labor scaling
    elif day == 29:
        # Last day scale up to harvest and sell everything
        if me["money"] >= 6000.0:
            hands_floor = 8
        elif me["money"] >= 2000.0:
            hands_floor = 5
        else:
            hands_floor = 2
    else:
        # Middle game (Day 10-28)
        if me["money"] >= 6000.0 and n_quadrants >= 4:
            hands_floor = 11
        elif me["money"] >= 4000.0 and n_quadrants >= 3:
            hands_floor = 8
        elif me["money"] >= 2000.0 and n_quadrants >= 2:
            hands_floor = 5
        elif me["money"] >= 1000.0:
            hands_floor = 3
        elif me["money"] >= 500.0:
            hands_floor = 2
        elif me["money"] >= 200.0:
            hands_floor = 1
        else:
            hands_floor = 0

        # Capping to save on quadratic re-hiring fees if hiring is expensive:
        if mult_val >= 5.0:
            hands_floor = min(hands_floor, 3)

    # Calculate Cash Reservation for essential expenditures (Hiring, Seed purchases, Feed)
    mult = economy.hire_cost_mult(config)
    hires_to_queue = 0
    temp_money = me["money"]
    temp_hires_today = me["hires_today"]
    temp_existing = len(me["hands"])

    # 1. Hire to meet the hands floor (no extra hiring to prevent bankruptcy)
    while temp_existing < hands_floor:
        cost = economy.hire_cost(temp_hires_today, mult=mult)
        if temp_money >= cost:
            hires_to_queue += 1
            temp_money -= cost
            temp_hires_today += 1
            temp_existing += 1
        else:
            break

    reserved_for_hire = 0.0
    temp_hires_today = me["hires_today"]
    for _ in range(hires_to_queue):
        reserved_for_hire += economy.hire_cost(temp_hires_today, mult=mult)
        temp_hires_today += 1

    # Reserve for seeds assigned to units this turn
    temp_seeds = dict(private["seeds"])
    reserved_for_seeds = 0.0
    for unit_idx, task_id in assignment.items():
        if task_id and task_id.kind == TaskKind.PLANT:
            crop = task_id.item
            if temp_seeds.get(crop, 0) > 0:
                temp_seeds[crop] -= 1
            else:
                reserved_for_seeds += economy.CROPS[crop]["seed"]

    # Reserve for wheat feed
    reserved_for_feed = 0.0
    if total_owned_animals > 0:
        total_wheat = shed.get("WHEAT", 0) + sum(inv.get("WHEAT", 0) for inv in inventories)
        target_wheat = max(2, total_owned_animals * 2)
        if total_wheat < target_wheat:
            buy_qty = target_wheat - total_wheat
            reserved_for_feed = buy_qty * prices.get("WHEAT", 25.0)

    # Dynamic minimum liquidity reserve to prevent starvation and labor shortage
    feed_reserve = total_owned_animals * 50.0
    hands_reserve = 0.0
    temp_h = 0
    for _ in range(hands_floor):
        hands_reserve += 3.0 * economy.hire_cost(temp_h, mult=mult)
        temp_h += 1
    buffer = 250.0 if total_owned_animals > 0 else 100.0
    minimum_liquidity = feed_reserve + hands_reserve + buffer

    liquidity_reserve = minimum_liquidity if (last_day - day >= 2 and day >= 2) else 0.0
    essential_reserves = reserved_for_hire + liquidity_reserve
    available_money = max(0.0, me["money"] - essential_reserves)

    # 1. HIRE hands
    for _ in range(hires_to_queue):
        market_orders.append(["HIRE"])

    # 2. BUY_LAND (up to max 1 extra quadrant, saving $6,000)
    land_cost = economy.land_cost(len(me["unlocked_quadrants"]) - 1)
    n_extra = len(me["unlocked_quadrants"]) - 1
    can_buy_land = False
    if land_cost is not None and 0 <= n_extra < 1 and last_day - day >= 12 and day >= 9:
        reserve = max(1000.0 * (n_extra + 1), minimum_liquidity)
        if me["money"] - reserved_for_hire >= land_cost + reserve:
            can_buy_land = True

    if can_buy_land:
        market_orders.append(["BUY_LAND"])
        available_money -= land_cost

    # 3. BUY_ANIMAL COW (matures in 8 days, needs at least 7 days to yield 3 milkings)
    if (
        animals_unlocked
        and day + 15 <= last_day
        and (owned_cows + cow_in_transit < MAX_COWS)
        and available_money >= COW_COST
    ):
        market_orders.append(["BUY_ANIMAL", "COW", 1])
        available_money -= COW_COST

    # 4. BUY_ANIMAL SHEEP (matures in 6 days, needs at least 9 days to yield 3 wool shearings)
    if (
        animals_unlocked
        and day + 15 <= last_day
        and (owned_sheep + sheep_in_transit < MAX_SHEEP)
        and available_money >= SHEEP_COST
    ):
        market_orders.append(["BUY_ANIMAL", "SHEEP", 1])
        available_money -= SHEEP_COST

    # 4.5. BUY_ANIMAL GOOSE (matures in 4 days, needs 6 days of eggs to break even)
    max_geese_allowed = 0 if day < 10 else MAX_GEESE
    if (
        animals_unlocked
        and day + 10 <= last_day
        and (owned_geese + goose_in_transit < max_geese_allowed)
        and available_money >= GOOSE_COST
    ):
        market_orders.append(["BUY_ANIMAL", "GOOSE", 1])
        available_money -= GOOSE_COST

    if hour == 1:
        # 5. BUY_PRODUCT WHEAT
        if total_owned_animals > 0:
            total_wheat = shed.get("WHEAT", 0) + sum(inv.get("WHEAT", 0) for inv in inventories)
            target_wheat = max(2, total_owned_animals * 2)
            if total_wheat < target_wheat:
                buy_qty = target_wheat - total_wheat
                wheat_unit_price = prices.get("WHEAT", 25.0)
                if me["money"] >= buy_qty * wheat_unit_price:
                    market_orders.append(["BUY_PRODUCT", "WHEAT", buy_qty])

        # Compute actual remaining cash for seed buying inside resolve_unit_action
        market_cash_remaining = available_money
        for order in market_orders:
            if order[0] == "BUY_LAND":
                market_cash_remaining -= economy.land_cost(len(me["unlocked_quadrants"]) - 1)
            elif order[0] == "BUY_ANIMAL":
                market_cash_remaining -= economy.ANIMALS[order[1]]["cost"]
            elif order[0] == "BUY_PRODUCT" and order[1] == "WHEAT":
                market_cash_remaining -= order[2] * prices.get("WHEAT", 25.0)

        # 6. BUY_SEED batch buying
        seeds_in_shed = private["seeds"]
        total_seeds_in_shed = sum(seeds_in_shed.get(c, 0) for c in CANDIDATE_CROPS)
        total_plant_tasks = sum(1 for t in tasks if t.task_id.kind == TaskKind.PLANT)
        if total_seeds_in_shed >= total_plant_tasks:
            seeds_needed = {c: 0 for c in CANDIDATE_CROPS}
        else:
            seeds_needed = {}
            for crop in CANDIDATE_CROPS:
                plant_tasks = sum(1 for t in tasks if t.task_id.kind == TaskKind.PLANT and t.task_id.item == crop)
                current_seeds = seeds_in_shed.get(crop, 0)
                seeds_needed[crop] = max(0, plant_tasks - current_seeds)

        for crop in CANDIDATE_CROPS:
            # Check if crop can mature if planted tomorrow (Day D+1)
            cd = economy.CROPS[crop]
            can_mature_tomorrow = False
            if cd["ongoing"]:
                can_mature_tomorrow = economy.can_ongoing_crop_reach_any_tick(crop, day + 1, last_day)
            else:
                can_mature_tomorrow = economy.can_mature_in_time(crop, day + 1, last_day)
            if not can_mature_tomorrow:
                continue

            needed = seeds_needed.get(crop, 0)
            if needed > 0:
                seed_cost = economy.CROPS[crop]["seed"]
                buy_limit = 25 if day == 0 else 12
                buy_qty = min(needed, buy_limit, int(market_cash_remaining // seed_cost))
                if buy_qty > 0:
                    market_orders.append(["BUY_SEED", crop, buy_qty])
                    market_cash_remaining -= buy_qty * seed_cost
    else:
        # Re-compute market_cash_remaining for resolve_unit_action when hour != 1
        market_cash_remaining = available_money
        for order in market_orders:
            if order[0] == "BUY_LAND":
                market_cash_remaining -= economy.land_cost(len(me["unlocked_quadrants"]) - 1)
            elif order[0] == "BUY_ANIMAL":
                market_cash_remaining -= economy.ANIMALS[order[1]]["cost"]

    seeds_remaining = dict(private["seeds"])
    seed_orders_queued = {order[1] for order in market_orders if order[0] == "BUY_SEED"}

    def resolve_unit_action(position: tuple[int, int], task_id, unit_idx: int) -> list:
        nonlocal market_cash_remaining
        if task_id is None:
            return ["PASS"]
        task = task_by_id.get(task_id)
        if task is None:
            return ["PASS"]

        tx, ty = task.target
        if position != (tx, ty):
            return [route_toward(position, (tx, ty), me["tiles"], board_size)]

        unit_inv = inventories[unit_idx] if unit_idx < len(inventories) else {}

        if task_id.kind == TaskKind.PLANT:
            crop = task_id.item
            if seeds_remaining.get(crop, 0) > 0:
                seeds_remaining[crop] -= 1
                return ["PLANT", crop]
            # Fallback: plant any seed we have in the shed/inventory
            for fallback_crop in CANDIDATE_CROPS:
                if seeds_remaining.get(fallback_crop, 0) > 0:
                    seeds_remaining[fallback_crop] -= 1
                    return ["PLANT", fallback_crop]
            return ["PASS"]
        if task_id.kind == TaskKind.WATER:
            return ["WATER"]
        if task_id.kind == TaskKind.HARVEST:
            return ["HARVEST"]
        if task_id.kind == TaskKind.DIG:
            return ["DIG"]
        if task_id.kind == TaskKind.BUILD_COOP:
            return ["BUILD_COOP"]
        if task_id.kind == TaskKind.BUILD_PASTURE:
            return ["BUILD_PASTURE"]
        if task_id.kind == TaskKind.PLACE:
            if unit_inv.get(task_id.item, 0) <= 0:
                return ["PASS"]
            return ["PLACE", task_id.item]
        if task_id.kind == TaskKind.FEED:
            if unit_inv.get("WHEAT", 0) <= 0:
                return ["PASS"]
            return ["FEED"]
        if task_id.kind == TaskKind.CARE:
            return ["CARE"]
        if task_id.kind == TaskKind.PICKUP:
            qty = 1
            if task.resource_needs:
                qty = task.resource_needs[0].quantity
            return ["PICKUP", task_id.item, qty]
        return ["PASS"]

    farmer_action = resolve_unit_action(unit_positions[0], assignment.get(0), 0)
    hands_actions = [
        resolve_unit_action(unit_positions[i + 1], assignment.get(i + 1), i + 1)
        for i in range(len(me["hands"]))
    ]

    return {"farmer": farmer_action, "hands": hands_actions, "market": market_orders}
