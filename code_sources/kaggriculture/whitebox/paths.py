"""Module 6 of 6 -- PATH PLANNER. Pure geometry, and smaller than it looks.

TWO ENGINE FACTS COLLAPSE THIS PROBLEM, both read from `_apply_unit_action`:

  1. LOCKED TILES ARE PASSABLE. The MOVE branch checks board bounds and nothing
     else. Travel cost is therefore plain Manhattan distance across the whole
     10x10 board, and no obstacle search is ever needed.
  2. UNITS DO NOT COLLIDE. There is no occupancy check anywhere in the engine;
     any number of units may stand on one tile.

So the reservation table, the point/edge collision constraints and the windowed
A* of a WHCA* design are all solving constraints this engine does not have. The
correct planner is `step toward the target, one axis at a time`, and the only
real decision left is TOUR ORDER, which belongs to the task planner.

This module is deliberately tiny. It is a module anyway because the ordering of
the two axes is a real choice with a real cost -- a unit that runs the x axis
first passes different tiles than one that runs y first -- and because the shed
tiles are the one piece of fixed geometry everything else keys off.
"""
BOARD = 10
HALF = BOARD // 2
SHED_TILES = ((HALF - 1, HALF - 1), (HALF, HALF - 1), (HALF - 1, HALF), (HALF, HALF))
SHED_SET = frozenset(SHED_TILES)
SPAWN = (HALF - 1, HALF - 1)

MOVES = {"NORTH": (0, -1), "SOUTH": (0, 1), "EAST": (1, 0), "WEST": (-1, 0)}


def dist(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def quadrant_of(x, y, board=BOARD):
    half = board // 2
    return ("N" if y < half else "S") + ("W" if x < half else "E")


def nearest_shed_tile(pos):
    return min(SHED_TILES, key=lambda t: dist(pos, t))


def dist_to_shed(pos):
    return min(dist(pos, t) for t in SHED_TILES)


def productive_tile_allowed(snap, pos):
    """Whether the planner may use a shed-access coordinate productively.

    The engine treats the central four coordinates as ordinary farm tiles and
    independently permits PICKUP/DROP while a unit stands there. Historical
    white-box versions excluded them; the corrected action space is opt-in on
    each current snapshot so old evaluation evidence remains reproducible.
    """
    return (tuple(pos) not in SHED_SET
            or bool(getattr(snap, "allow_productive_shed_tiles", False)))


def step_toward(pos, target, x_first=True):
    """One legal move from `pos` toward `target`, or None if already there.

    `x_first` is exposed rather than hardcoded because it is the only free
    parameter in this module and it changes which tiles a unit passes over --
    which matters the moment anything opportunistic is bolted on (picking up a
    weed in passing, topping up feed). Default matches `route/router.py`.
    """
    px, py = pos[0], pos[1]
    tx, ty = target[0], target[1]
    if (px, py) == (tx, ty):
        return None
    if x_first and px != tx:
        return "EAST" if tx > px else "WEST"
    if py != ty:
        return "SOUTH" if ty > py else "NORTH"
    if px != tx:
        return "EAST" if tx > px else "WEST"
    return None


def path(pos, target, x_first=True):
    """The full move list. Used for costing, not usually for execution --
    execution re-derives each step from the unit's ACTUAL position so a wrong
    spawn guess costs one turn instead of desynchronising the day."""
    out, cur = [], (pos[0], pos[1])
    guard = 0
    while cur != (target[0], target[1]) and guard < 2 * BOARD:
        mv = step_toward(cur, target, x_first)
        if mv is None:
            break
        dx, dy = MOVES[mv]
        cur = (cur[0] + dx, cur[1] + dy)
        out.append(mv)
        guard += 1
    return out
