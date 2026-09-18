"""Spatial feasibility: how many tiles this crew can actually service.

The scheduler works at 50 tiles and collapses at 73 -- transplanting the tape's
own 73-tile layout produced 150 build actions but 811 units and $45,147, against
the tape's 265 / 1,164 / $96,293 on the identical layout. The layout is not the
tape's secret; servicing it is.

The cause is a missing term. `_size_crew` sizes the crew to the day's OP-TURNS,
and a tile's work is one or two ops -- but a unit spends most of its day walking:
measured, 43% of our unit-turns are movement and 33% are ops. So the crew is
sized against a third of the real cost, every tour overflows, `build_tour` drops
the tail, and tiles die unwatered. The board goes 19 tiles on day 3 to 9 on
day 6.

    L_req'(a, w) = L_req(a) + D(pos_w, loc(a))
    ENPV_adj(a, w) = ENPV(a) - D(pos_w, loc(a)) * c_step

Movement is unrestricted and LOCKED tiles are passable (`route/router.py`), so
D is plain Manhattan distance and no path search is needed:

    D(u, v) = |u_x - v_x| + |u_y - v_y|

THE HARD CONSTRAINT, which is what stops the collapse:

    sum over a in S_w of L_req(a)  +  TravelTime(S_w)  <=  L_max_per_worker

    union of S_w = A_selected,   S_i disjoint from S_j

`build_tour` already enforces this per worker AFTER the fact, by dropping the
cheapest tasks until the tour fits. What is missing is the FEEDBACK: nothing
tells the purchase side that the tiles it is buying seed for cannot be served.
`serviceable()` closes that loop, and it does so by declining -- the shape of
change that has actually held in this project.
"""
from route.geom import dist
from route.router import TURNS_PER_DAY, Task, Unit, build_tour, partition

# Ops a tile costs on a typical day. A crop wants WATER and, on a yield day,
# HARVEST; an animal wants FEED, CARE, COLLECT_FERTILIZER and often HARVEST.
OPS_PER_CROP = 1.4
OPS_PER_ANIMAL = 3.0


def distance(u, v):
    """D(u, v). Manhattan, because movement is unrestricted."""
    return dist(u, v)


def travel_time(start, positions):
    """TravelTime(S_w): the length of the solved open tour over `positions`."""
    if not positions:
        return 0
    from route.router import solve_tour, tour_length
    return tour_length(start, solve_tour(start, list(positions)))


def fits(positions, ops, start, budget=TURNS_PER_DAY):
    """The hard constraint, for one worker."""
    return sum(ops) + travel_time(start, positions) <= budget


def serviceable(positions, n_workers, ops_per_tile=OPS_PER_CROP,
                starts=None, budget=TURNS_PER_DAY):
    """How many of `positions` this crew can actually serve in one day.

    Runs the real partition and tour builder rather than a formula, so the
    answer includes the same 2-opt routing and the same drop rule the agent will
    actually experience. Returns (n_served, n_dropped).
    """
    if n_workers <= 0 or not positions:
        return 0, len(positions)
    from route.geom import SHED_TILES
    shed = list(SHED_TILES) or [(4, 4)]
    starts = starts or [shed[i % len(shed)] for i in range(n_workers)]
    units = [Unit(i, starts[i]) for i in range(n_workers)]
    n_ops = max(1, int(round(ops_per_tile)))
    tasks = [Task(p, [["WATER"]] * n_ops, value=1.0) for p in positions]
    assignment, leftover = partition(tasks, units)
    served = 0
    for u in units:
        tour = build_tour(u, assignment[u.idx])
        served += len(tour["tasks"])
    return served, len(positions) - served


def max_tiles(n_workers, board_positions, ops_per_tile=OPS_PER_CROP,
              budget=TURNS_PER_DAY):
    """Largest prefix of `board_positions` (already in claim order, so nearest
    to the shed first) that this crew serves without dropping anything.

    Binary search: `serviceable` is monotone in the number of tiles offered.
    """
    lo, hi = 0, len(board_positions)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        served, dropped = serviceable(board_positions[:mid], n_workers,
                                      ops_per_tile, budget=budget)
        if dropped == 0:
            lo = mid
        else:
            hi = mid - 1
    return lo


def crew_for(n_tiles, board_positions, ops_per_tile=OPS_PER_CROP,
             max_workers=26, budget=TURNS_PER_DAY):
    """Smallest crew that serves `n_tiles` with nothing dropped. This is the
    honest crew-sizing rule: it counts travel, which op-turn sizing does not."""
    for w in range(1, max_workers + 1):
        served, dropped = serviceable(board_positions[:n_tiles], w,
                                      ops_per_tile, budget=budget)
        if dropped == 0:
            return w
    return max_workers


def spatial_shadow_price(blocked_enpv, n_workers, wage, positions, target,
                         c_step=0.0):
    """ENPV of the hand that unblocks `target`, net of wage and of the walk.

        [ ENPV(a_blocked) - wage*N - sum_w D(pos_w, loc(a_blocked))*c_step ] / N
    """
    if n_workers <= 0:
        return 0.0
    walk = sum(distance(p, target) for p in positions[:n_workers])
    return (blocked_enpv - wage * n_workers - walk * c_step) / float(n_workers)
