"""Cost-optimal unit-to-task assignment, replacing the angular sweep.

WHAT route/router.py DOES NOW. `partition` sorts tasks by their angle around the
shed and packs each unit greedily until its turn budget runs out. That produces
compact, non-overlapping wedges, which is easy to reason about -- but it is not
minimising anything. A task can be handed to a unit on the far side of the board
purely because it fell next in the angular order.

WHAT THIS DOES. Build the cost matrix explicitly

    C[u][t] = manhattan(pos_u, loc_t) + work_turns(t)

and solve the assignment that minimises the total. Two solvers, both readable:

  greedy     tasks sorted by DEADLINE first (an asset that dies tonight cannot
             wait for an optimal plan), then each takes its nearest free unit.
  hungarian  the exact minimum-cost assignment, O(n^3), no heuristic at all.

WHY IT MIGHT MATTER EVEN THOUGH CAPACITY DOES NOT BIND. Section 22 measured crew
utilisation at 35% mean and 0 days over 100%, so saving turns does not directly
buy more work. But `_size_crew` sizes the crew TO the day's task list, and hire
cost is fib(n) in the number hired that day -- so a cheaper assignment needs
fewer hands for the same tasks, and the cash saved lands in the first ten days,
where section 34 measured a dollar to be worth 2.00 +- 0.19 at the buzzer.

The Hungarian implementation is the standard O(n^3) shortest-augmenting-path
form, written out rather than imported: scipy is not on the Kaggle runner and
this has to ship.
"""
import math

from route.geom import dist


def cost_matrix(units, tasks, work_of=None):
    """C[u][t] = travel + work. Rows are units, columns tasks."""
    work_of = work_of or (lambda t: t.n_ops)
    return [[dist(u.start, t.pos) + work_of(t) for t in tasks] for u in units]


def hungarian(cost):
    """Exact minimum-cost assignment. Returns row -> col (or -1).

    Jonker-Volgenant style shortest augmenting path with potentials. Handles
    rectangular input by padding, so it does not care whether there are more
    units than tasks or the other way round.
    """
    if not cost or not cost[0]:
        return []
    n, m = len(cost), len(cost[0])
    size = max(n, m)
    INF = float("inf")
    big = max(max(r) for r in cost) * size + 1.0
    C = [[(cost[i][j] if i < n and j < m else big) for j in range(size)]
         for i in range(size)]

    u = [0.0] * (size + 1)
    v = [0.0] * (size + 1)
    p = [0] * (size + 1)          # p[j] = row matched to column j
    way = [0] * (size + 1)
    for i in range(1, size + 1):
        p[0] = i
        j0 = 0
        minv = [INF] * (size + 1)
        used = [False] * (size + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = INF
            j1 = 0
            for j in range(1, size + 1):
                if used[j]:
                    continue
                cur = C[i0 - 1][j - 1] - u[i0] - v[j]
                if cur < minv[j]:
                    minv[j] = cur
                    way[j] = j0
                if minv[j] < delta:
                    delta = minv[j]
                    j1 = j
            for j in range(size + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
    out = [-1] * n
    for j in range(1, size + 1):
        i = p[j] - 1
        if 0 <= i < n and j - 1 < m:
            out[i] = j - 1
    return out


def greedy_by_deadline(units, tasks, cost, deadline_of=None):
    """Earliest deadline first, each task taking its nearest free unit.

    Deadline beats distance on purpose: the engine kills a plant on its second
    consecutive unwatered night and an animal on its second unfed one, so a task
    standing between an asset and that threshold cannot wait for a tidier plan.
    """
    deadline_of = deadline_of or (lambda t: 0 if t.value >= 1e6 else 1)
    order = sorted(range(len(tasks)), key=lambda j: (deadline_of(tasks[j]),
                                                     -tasks[j].value))
    free = set(range(len(units)))
    out = [-1] * len(units)
    for j in order:
        if not free:
            break
        i = min(free, key=lambda i: cost[i][j])
        out[i] = j
        free.discard(i)
    return out


def assign(units, tasks, mode="hungarian", work_of=None, budget_of=None):
    """{unit_idx: [tasks]} under the chosen solver.

    Assignment is one task per unit per round; the remaining tasks are dealt out
    over further rounds, each round re-costed from where the units would then
    be. That keeps every round an exact assignment problem instead of pretending
    a unit's second task costs the same as its first.
    """
    if not units or not tasks:
        return {u.idx: [] for u in units}, list(tasks)
    budget_of = budget_of or (lambda u: u.budget)
    work_of = work_of or (lambda t: t.n_ops)

    out = {u.idx: [] for u in units}
    pos = {u.idx: u.start for u in units}
    left = {u.idx: budget_of(u) for u in units}
    remaining = list(tasks)

    while remaining:
        live = [u for u in units if left[u.idx] > 0]
        if not live:
            break
        cost = [[dist(pos[u.idx], t.pos) + work_of(t) for t in remaining]
                for u in live]
        pick = (hungarian(cost) if mode == "hungarian"
                else greedy_by_deadline(live, remaining, cost))
        took = False
        for i, j in enumerate(pick):
            if j < 0 or j >= len(remaining):
                continue
            u, t = live[i], remaining[j]
            c = cost[i][j]
            if c > left[u.idx]:
                continue
            out[u.idx].append(t)
            left[u.idx] -= c
            pos[u.idx] = t.pos
            took = True
        if not took:
            break
        chosen = {id(remaining[j]) for i, j in enumerate(pick)
                  if 0 <= j < len(remaining) and remaining[j] in
                  out[live[i].idx]}
        remaining = [t for t in remaining if id(t) not in chosen]
    return out, remaining


def total_cost(assignment, units, work_of=None):
    """Sum of travel + work over an assignment. The number being minimised."""
    work_of = work_of or (lambda t: t.n_ops)
    by_idx = {u.idx: u for u in units}
    total = 0.0
    for idx, ts in assignment.items():
        cur = by_idx[idx].start
        for t in ts:
            total += dist(cur, t.pos) + work_of(t)
            cur = t.pos
    return total
