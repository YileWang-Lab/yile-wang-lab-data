"""Board geometry for the route planner.

The board is 10x10 split into four 5x5 quadrants; the shed sits at the centre
and is worked from the four inner-corner tiles (4,4) (5,4) (4,5) (5,5). Only NW
is unlocked at the start, but *movement* is unrestricted -- LOCKED tiles are
passable (engine `_apply_unit_action`, MOVE branch), so travel cost is plain
Manhattan distance across the whole board and never needs a path search.
"""

BOARD = 10
HALF = BOARD // 2


def shed_access_tiles(board_size=BOARD):
    half = board_size // 2
    return [(half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half)]


SHED_TILES = shed_access_tiles()
SHED_SET = set(SHED_TILES)
# The farmer and every hand spawn here at the start of each day; three of the
# four access tiles are LOCKED until the matching quadrant is bought, and
# _default_spawn only ever returns the NW one.
SPAWN = (HALF - 1, HALF - 1)


def quadrant_of(x, y, board_size=BOARD):
    half = board_size // 2
    return ("N" if y < half else "S") + ("W" if x < half else "E")


def dist(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def dist_to_shed(t):
    return min(dist(t, s) for s in SHED_TILES)


def nearest_shed_tile(t):
    return min(SHED_TILES, key=lambda s: dist(t, s))


def steps_between(a, b):
    """Emit the move ops that walk a -> b. Vertical first, then horizontal;
    any order costs the same on an open grid."""
    ops = []
    x, y = a
    tx, ty = b
    while y < ty:
        ops.append("SOUTH"); y += 1
    while y > ty:
        ops.append("NORTH"); y -= 1
    while x < tx:
        ops.append("EAST"); x += 1
    while x > tx:
        ops.append("WEST"); x -= 1
    return ops
