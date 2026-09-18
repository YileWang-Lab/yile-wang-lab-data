"""Day scheduler that preserves CARE DENSITY when demand exceeds capacity.

route/router.py works at 50 tiles and collapses at 73: transplanting the tape's
own 73-tile layout into our scheduler produced 150 build actions but only 811
units and $45,147, against the tape's 265/1,164/$96,293 on the identical
layout. The layout is not the tape's secret; servicing it is.

Two defects, both about what happens when the day's work does not fit.

1. STATIC TASK VALUE. route/agent.py scores a task by op type alone
   (OP_VALUE: FEED 1000, HARVEST 900, WATER 800, CARE 700...), so the same
   WATER is worth 800 whether the plant was watered yesterday or is one missed
   turn from becoming a weed. The engine's rule is absolute -- two consecutive
   unwatered nights turn a plant into a weed, two unfed nights and the animal
   escapes -- so the marginal value of that identical op differs by an entire
   asset. Value is computed from TILE STATE here, not from the op name.

2. SPREADING THE SHORTFALL. build_tour drops the lowest-value tasks
   individually, so an over-subscribed day serves many tiles partially. Partial
   service is worthless for exactly the assets that matter: a crop watered on
   70% of days still dies, because dying needs only two consecutive misses.
   Seventy-three tiles each served at 70% is seventy-three dead tiles; fifty
   served fully is fifty live ones. So the shortfall is taken by ABANDONING
   WHOLE TILES, lowest expected remaining value first, rather than by thinning
   every tile's care.

Abandoned tiles are reported back so the caller can stop buying seed for them.
"""
import math

from route.geom import SHED_SET, dist, steps_between  # noqa: F401
from route.router import (Task, Unit, TURNS_PER_DAY, solve_tour, tour_length,
                          _carry_turns, _carry_totals, build_tour)

# Engine constants needed to price a tile's remaining season.
_CROPS = {
    "WHEAT": {"first": 2, "maxday": 4, "interval": 0, "maxy": 6, "ongoing": False, "px": 25},
    "CARROT": {"first": 2, "maxday": 3, "interval": 0, "maxy": 4, "ongoing": False, "px": 35},
    "TOMATO": {"first": 8, "maxday": 8, "interval": 1, "maxy": 4, "ongoing": True, "px": 60},
    "STRAWBERRY": {"first": 10, "maxday": 10, "interval": 2, "maxy": 4, "ongoing": True, "px": 120},
    "MELON": {"first": 10, "maxday": 12, "interval": 0, "maxy": 6, "ongoing": False, "px": 250},
}
_ANIMALS = {"GOOSE": (4, 1, 50, 2.0), "COW": (8, 2, 160, 1.5), "SHEEP": (6, 3, 200, 4 / 3)}
SEASON_DAYS = 30

# A task whose omission destroys the asset outright. Ranked above everything
# else so triage can never trade a living tile for a convenience op.
CRITICAL = 1_000_000.0


def tile_value(tile, day):
    """Expected remaining revenue from this tile if it is kept alive."""
    if not isinstance(tile, dict):
        return 0.0
    days_left = max(0, SEASON_DAYS - day)
    if "animal" in tile:
        a = _ANIMALS.get(tile["animal"])
        if not a:
            return 0.0
        first, interval, px, per_day = a
        age = day - int(tile.get("placed_day", day))
        producing = max(0, days_left - max(0, first - age))
        return producing * per_day * px
    if tile.get("kind") == "PLANT":
        cd = _CROPS.get(tile.get("crop"))
        if not cd:
            return 0.0
        age = day - int(tile.get("planted_day", day))
        if cd["ongoing"]:
            done = max(0, (age - cd["first"]) // max(1, cd["interval"]) + 1) if age >= cd["first"] else 0
            remaining = max(0, cd["maxy"] - done)
            reachable = max(0, (days_left) // max(1, cd["interval"]))
            return min(remaining, reachable) * cd["px"]
        if age > cd["maxday"] + 2:
            return float(tile.get("yield_units", 0)) * cd["px"]
        return min(cd["maxy"], cd["maxy"]) * cd["px"] * (1.0 if days_left > cd["maxday"] - age else 0.3)
    return 0.0


def task_value(tile, ops, day, base_values):
    """Marginal value of DOING this task, given what the tile is about to lose.

    The engine kills a plant on its second consecutive unwatered night and lets
    an animal escape on its second unfed one, so a task standing between an
    asset and that threshold is worth the whole asset, not the op's list price.
    """
    op_names = [o[0] for o in ops]
    v = max(base_values.get(o, 100.0) for o in op_names) if op_names else 0.0
    if not isinstance(tile, dict):
        return v
    val = tile_value(tile, day)
    if "animal" in tile:
        if "FEED" in op_names and int(tile.get("consecutive_unfed", 0)) >= 1:
            return CRITICAL + val
        if "HARVEST" in op_names and tile.get("yield_units", 0) >= 4:
            v += val * 0.25          # at the holding cap, further output is lost
    elif tile.get("kind") == "PLANT":
        if "WATER" in op_names and int(tile.get("consecutive_unwatered", 0)) >= 1:
            return CRITICAL + val
        if "WATER" in op_names:
            v += val * 0.5           # keeping it alive is most of its worth
        if "HARVEST" in op_names:
            v += float(tile.get("yield_units", 0)) * 40.0
    return v


def triage(tasks, units, day, keep_ratio=1.0):
    """Fit the day's work to the crew by abandoning whole tiles, not by
    thinning every tile's care.

    Returns (kept_tasks, abandoned_positions). Critical tasks are never
    abandoned -- losing one costs an entire asset, which is strictly worse than
    losing any number of convenience ops.
    """
    capacity = sum(u.budget for u in units)
    if capacity <= 0 or not tasks:
        return list(tasks), set()

    by_pos = {}
    for t in tasks:
        by_pos.setdefault(t.pos, []).append(t)

    # cost of a tile = its ops plus a travel allowance, so the estimate is not
    # wildly optimistic about a spread-out board
    centre = (4.5, 4.5)
    def cost(pos):
        ops = sum(t.n_ops for t in by_pos[pos])
        return ops + 0.5 * dist(pos, (4, 4)) + _carry_turns(by_pos[pos])

    def worth(pos):
        return max(t.value for t in by_pos[pos])

    total = sum(cost(p) for p in by_pos)
    budget = capacity * keep_ratio
    if total <= budget:
        return list(tasks), set()

    order = sorted(by_pos, key=lambda p: (worth(p) / max(1e-6, cost(p)), worth(p)))
    dropped = set()
    for pos in order:
        if total <= budget:
            break
        if any(t.value >= CRITICAL for t in by_pos[pos]):
            continue                 # never abandon an asset about to die
        dropped.add(pos)
        total -= cost(pos)
    kept = [t for t in tasks if t.pos not in dropped]
    return kept, dropped


def plan_day(units, tasks, shed_stock=None, day=0, keep_ratio=1.0):
    """Triage first, then route what survives. Returns (tours, undone, dropped)."""
    kept, dropped = triage(tasks, units, day, keep_ratio)
    from route.router import partition
    assignment, leftover = partition(kept, units)
    tours = {}
    scheduled = set()
    for u in units:
        tour = build_tour(u, assignment[u.idx], shed_stock)
        tours[u.idx] = tour
        for t in tour["tasks"]:
            scheduled.add(id(t))
    undone = [t for t in kept if id(t) not in scheduled]
    return tours, undone, dropped
