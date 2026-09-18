"""Daily route solver.

The measured gap to the reference agents is throughput, not strategy: they land
52% useful actions to our 25% because their route was solved offline instead of
re-derived greedily every turn. This module solves that routing problem.

Each day is an open prize-collecting multi-worker routing problem: select task
bundles by terminal-dollar value, assign them under worker budgets and shared
input stock, then order the selected stops. Small paths are exact Held-Karp;
larger ones use deterministic nearest-neighbour + 2-opt. Crew-change replans
preserve one committed prefix per incumbent so hiring cannot cause route thrash.

Movement is unrestricted -- LOCKED tiles are passable -- so travel cost is plain
Manhattan distance and no path search is needed.
"""
import heapq
import math
import time
from functools import lru_cache

from route.geom import SHED_SET, SHED_TILES, dist, steps_between

TURNS_PER_DAY = 24

# Opt-in research seam.  The default preserves historical behaviour; a
# survival-focused candidate can request a second solve over only its missing
# FEED cores, keeping unrelated mandatory crop work out of that hard-cover
# witness.  It is reset by version wrappers and never reads external data.
SURVIVAL_FEED_ONLY_FALLBACK = False


class Task:
    """One tile's work for one day. `ops` are engine action lists, already in
    the order they must run on the tile (FERTILIZE -> WATER -> HARVEST, since
    WATER checks the fertilizer flag and HARVEST clears the yield)."""

    __slots__ = ("pos", "ops", "carry", "value", "mandatory", "kind",
                 "cash_cost", "order_key", "activations", "exclusive_key")

    def __init__(self, pos, ops, carry=None, value=1.0, mandatory=False,
                 kind=None, cash_cost=0.0, order_key=None, activations=None,
                 exclusive_key=None):
        self.pos = pos
        self.ops = ops
        # {item: n} that must be in hand before the ops run (feed wheat,
        # fertilizer, an animal to PLACE). Collected in one PICKUP per item.
        self.carry = carry or {}
        self.value = value
        self.mandatory = bool(mandatory)
        self.kind = kind or (ops[0][0] if ops else "TASK")
        # Optional capital-column metadata. ``cash_cost`` is paid once per
        # selected task unit; ``order_key`` consumes one market slot no matter
        # how many units share it; ``activations`` are fixed-charge prerequisites
        # such as BUY_LAND, counted once across every dependent task.
        self.cash_cost = max(0.0, float(cash_cost))
        self.order_key = order_key
        self.activations = dict(activations or {})
        # Alternative capital columns may name the same physical tile (for
        # example COW vs SHEEP vs STRAWBERRY). At most one can be selected;
        # grouping their operations into one route stop would otherwise emit
        # several individually legal but jointly impossible mutations there.
        self.exclusive_key = exclusive_key

    @property
    def n_ops(self):
        return len(self.ops)

    def __repr__(self):
        mark = "!" if self.mandatory else ""
        return f"Task({self.pos}, {[o[0] for o in self.ops]}, v={self.value:.0f}{mark})"


class Unit:
    """A farmer/hand slot for one day. `start_hour` is when the unit first gets
    to act -- hands hired at hour h are appended by the market phase of that
    turn and so are first controllable at h+1."""

    __slots__ = ("idx", "start", "start_hour")

    def __init__(self, idx, start, start_hour=0):
        self.idx = idx
        self.start = start
        self.start_hour = start_hour

    @property
    def budget(self):
        return max(0, TURNS_PER_DAY - self.start_hour)


# ---------------------------------------------------------------- tour solving

def tour_length(start, order):
    if not order:
        return 0
    total = dist(start, order[0])
    for a, b in zip(order, order[1:]):
        total += dist(a, b)
    return total


def nearest_neighbour(start, tiles):
    remaining = list(tiles)
    order = []
    cur = start
    while remaining:
        nxt = min(remaining, key=lambda t: (dist(cur, t), t))
        remaining.remove(nxt)
        order.append(nxt)
        cur = nxt
    return order


def two_opt(start, order, max_passes=6):
    """2-opt on an open path with a fixed start. Reversing order[i:j+1] only
    changes the two edges entering and leaving that span, so each candidate is
    an O(1) delta; the tail edge is free because the path may end anywhere."""
    if len(order) < 3:
        return order
    order = list(order)
    n = len(order)
    for _ in range(max_passes):
        improved = False
        for i in range(n - 1):
            prev = order[i - 1] if i > 0 else start
            for j in range(i + 1, n):
                a, b = order[i], order[j]
                before = dist(prev, a)
                after = dist(prev, b)
                if j + 1 < n:
                    nxt = order[j + 1]
                    before += dist(b, nxt)
                    after += dist(a, nxt)
                if after < before:
                    order[i:j + 1] = reversed(order[i:j + 1])
                    improved = True
        if not improved:
            break
    return order


def _heuristic_tour(start, tiles):
    return two_opt(start, nearest_neighbour(start, tiles))


@lru_cache(maxsize=4096)
def _exact_open_cached(start, tiles):
    """Held-Karp shortest open path through all unique ``tiles``."""
    n = len(tiles)
    if n <= 1:
        return tiles
    inf = 10 ** 9
    size = 1 << n
    dp = [[inf] * n for _ in range(size)]
    parent = [[-1] * n for _ in range(size)]
    for j, tile in enumerate(tiles):
        dp[1 << j][j] = dist(start, tile)
    for mask in range(size):
        for last in range(n):
            cur = dp[mask][last]
            if cur >= inf:
                continue
            for nxt in range(n):
                bit = 1 << nxt
                if mask & bit:
                    continue
                nm = mask | bit
                cand = cur + dist(tiles[last], tiles[nxt])
                if cand < dp[nm][nxt]:
                    dp[nm][nxt] = cand
                    parent[nm][nxt] = last
    mask = size - 1
    last = min(range(n), key=lambda j: (dp[mask][j], tiles[j]))
    rev = []
    while last >= 0:
        rev.append(tiles[last])
        prev = parent[mask][last]
        mask ^= 1 << last
        last = prev
    return tuple(reversed(rev))


EXACT_OPEN_LIMIT = 10


def solve_tour(start, tiles):
    """Exact open tour for small routes, deterministic 2-opt above the limit."""
    unique = tuple(sorted(set(tuple(t) for t in tiles)))
    if len(unique) <= EXACT_OPEN_LIMIT:
        return list(_exact_open_cached(tuple(start), unique))
    return _heuristic_tour(start, unique)


def _route_order(anchor, tiles, exact=False, prefix=None):
    """Open route order, optionally preserving one already-committed stop."""
    unique = sorted(set(tuple(tile) for tile in tiles))
    prefix = tuple(prefix) if prefix is not None else None
    if prefix in unique:
        unique.remove(prefix)
        tail = (solve_tour(prefix, unique) if exact else
                _heuristic_tour(prefix, unique))
        return [prefix] + list(tail)
    return solve_tour(anchor, unique) if exact else _heuristic_tour(anchor, unique)


def _route_banks_output(tasks):
    return any(op and op[0] in ("HARVEST", "COLLECT_FERTILIZER")
               for task in tasks for op in task.ops)


def _bank_tail(order, tasks, bank_outputs):
    if not bank_outputs or not order or not _route_banks_output(tasks):
        return 0
    return min(dist(order[-1], shed) for shed in SHED_TILES) + 1


def route_cost(unit, tasks, exact=False, prefix=None, bank_outputs=False):
    """Complete open-route cost for a worker/task bundle."""
    tasks = list(tasks)
    if not tasks:
        return 0
    tiles = [t.pos for t in tasks]
    pickups = _carry_turns(tasks)
    anchor = (min(SHED_TILES, key=lambda p: (dist(unit.start, p), p))
              if pickups else unit.start)
    order = _route_order(anchor, tiles, exact=exact, prefix=prefix)
    return (dist(unit.start, anchor) + pickups + tour_length(anchor, order)
            + sum(t.n_ops for t in tasks)
            + _bank_tail(order, tasks, bank_outputs))


# ------------------------------------------------------------------ partition

def _sweep_key(pos, centre):
    """Angle around the shed, then distance. Sorting by this walks the board in
    a spiral, so any contiguous slice of the list is a compact wedge -- which is
    what makes the greedy packing below produce sane, non-overlapping zones."""
    ang = math.atan2(pos[1] - centre[1], pos[0] - centre[0])
    return (ang, dist(pos, (round(centre[0]), round(centre[1]))))


def partition(tasks, units, centre=(4.5, 4.5)):
    """Assign tasks to units by angular sweep, packing each unit to its turn
    budget. Returns (assignment, leftover)."""
    ordered = sorted(tasks, key=lambda t: _sweep_key(t.pos, centre))
    assignment = {u.idx: [] for u in units}
    leftover = []
    if not units:
        return assignment, ordered

    ui = 0
    cur_cost = 0
    cur_pos = None
    for task in ordered:
        while ui < len(units):
            u = units[ui]
            overhead = _carry_turns(assignment[u.idx] + [task])
            step = dist(cur_pos, task.pos) if cur_pos is not None else dist(u.start, task.pos)
            projected = cur_cost + step + task.n_ops + overhead
            # Do not force an oversized first task onto an empty worker.  The
            # old fallback made ``build_tour`` drop it later, after partitioning
            # had already denied it to a later worker (especially a newly hired
            # hand spawning next to the task).  Try the next worker instead;
            # if nobody can fit it the task correctly lands in ``leftover``.
            if projected <= u.budget:
                assignment[u.idx].append(task)
                cur_cost += step + task.n_ops
                cur_pos = task.pos
                break
            ui += 1
            cur_cost = 0
            cur_pos = None
        else:
            leftover.append(task)
    return assignment, leftover


def _carry_turns(tasks):
    """PICKUP turns needed before setting off: one per distinct carried item.
    PICKUP takes a count, so n wheat is still a single turn."""
    items = set()
    for t in tasks:
        items.update(k for k, v in t.carry.items() if v)
    return len(items)


def _carry_totals(tasks):
    totals = {}
    for t in tasks:
        for k, v in t.carry.items():
            if v:
                totals[k] = totals.get(k, 0) + v
    return totals


# -------------------------------------------------------- joint prize collect

def _capital_usage(tasks):
    cash = 0.0
    order_keys = set()
    activations = {}
    for task in tasks:
        cash += float(getattr(task, "cash_cost", 0.0) or 0.0)
        key = getattr(task, "order_key", None)
        if key is not None:
            order_keys.add(key)
        for activation, cost in getattr(task, "activations", {}).items():
            activations[activation] = max(
                float(cost), activations.get(activation, 0.0)
            )
    cash += sum(activations.values())
    order_keys.update(activations)
    return cash, order_keys


def _resources_fit(tasks, shed_stock, cash_budget=None, max_order_keys=None,
                   selection_limits=None):
    exclusive = [getattr(task, "exclusive_key", None) for task in tasks]
    exclusive = [key for key in exclusive if key is not None]
    if len(exclusive) != len(set(exclusive)):
        return False
    if selection_limits:
        selected = {}
        for task in tasks:
            key = getattr(task, "order_key", None)
            if key in selection_limits:
                selected[key] = selected.get(key, 0) + 1
        if any(n > int(selection_limits[key]) for key, n in selected.items()):
            return False
    if shed_stock is None:
        carry_ok = True
    else:
        need = _carry_totals(tasks)
        carry_ok = all(int(n) <= int(shed_stock.get(item, 0) or 0)
                       for item, n in need.items())
    if not carry_ok:
        return False
    cash, order_keys = _capital_usage(tasks)
    if cash_budget is not None and cash > float(cash_budget) + 1e-9:
        return False
    if max_order_keys is not None and len(order_keys) > int(max_order_keys):
        return False
    return True


def deadline_expired(deadline):
    """Shared anytime guard. ``None`` means offline/unbounded solving."""
    return deadline is not None and time.perf_counter() >= float(deadline)


def deadline_near(deadline, reserve=0.0):
    """Whether only ``reserve`` seconds remain before the soft deadline."""
    return (deadline is not None and
            time.perf_counter() + max(0.0, float(reserve)) >= float(deadline))


def _fast_feasible_assign(tasks, units, shed_stock=None, cash_budget=None,
                          max_order_keys=None, fixed_owner=None,
                          selection_limits=None, bank_outputs=False,
                          required_ids=None):
    """Cheap deterministic feasible incumbent when the deadline is spent.

    It keeps value/survival ordering and every global resource constraint, but
    uses insertion order rather than trying all NN+2-opt route changes. Final
    emission still applies NN+2-opt and drops anything that does not fit.
    """
    units = list(units)
    required_ids = set(required_ids or ())
    assignment = {u.idx: [] for u in units}
    selected, leftover = [], []
    approx = {u.idx: 0 for u in units}
    by_idx = {u.idx: u for u in units}

    def ordered_cost(unit, worker_tasks):
        if not worker_tasks:
            return 0
        pickups = _carry_turns(worker_tasks)
        anchor = (min(SHED_TILES, key=lambda p: (dist(unit.start, p), p))
                  if pickups else unit.start)
        total, cur = dist(unit.start, anchor) + pickups, anchor
        seen = set()
        for task in worker_tasks:
            if task.pos not in seen:
                total += dist(cur, task.pos)
                cur = task.pos
                seen.add(task.pos)
            total += task.n_ops
        if bank_outputs and seen and _route_banks_output(worker_tasks):
            total += min(dist(cur, shed) for shed in SHED_TILES) + 1
        return total

    locked = []
    by_position = {tuple(task.pos): task for task in tasks}
    for pos, owner in (fixed_owner or {}).items():
        task = by_position.get(tuple(pos))
        unit = by_idx.get(owner)
        if task is None or unit is None:
            continue
        if float(task.value) <= 0 and not task.mandatory:
            continue
        if not _resources_fit(selected + [task], shed_stock, cash_budget,
                              max_order_keys, selection_limits):
            continue
        cost = ordered_cost(unit, [task])
        if cost > unit.budget:
            continue
        assignment[unit.idx].append(task)
        approx[unit.idx] = cost
        selected.append(task)
        locked.append(task)

    locked_ids = {id(task) for task in locked}
    candidates = [t for t in tasks
                  if (t.mandatory or float(t.value) > 0)
                  and id(t) not in locked_ids]
    candidates.sort(key=lambda t: (0 if id(t) in required_ids else
                                   (1 if t.mandatory else 2),
                                   -float(t.value), tuple(t.pos), t.kind))
    rejected = [t for t in tasks
                if id(t) not in locked_ids and t not in candidates]
    for task in candidates:
        if not _resources_fit(selected + [task], shed_stock, cash_budget,
                              max_order_keys, selection_limits):
            leftover.append(task)
            continue
        best = None
        for unit in units:
            trial = assignment[unit.idx] + [task]
            cost = ordered_cost(unit, trial)
            if cost > unit.budget:
                continue
            key = (cost - approx[unit.idx], cost, unit.idx)
            if best is None or key < best[0]:
                best = (key, unit, cost)
        if best is None:
            leftover.append(task)
            continue
        _key, unit, cost = best
        assignment[unit.idx].append(task)
        approx[unit.idx] = cost
        selected.append(task)
    leftover.extend(rejected)
    return assignment, leftover


def _candidate_key(task, units, bank_outputs=False, value=None,
                   route_cost_fn=None):
    feasible = []
    for unit in units:
        cost = (route_cost(unit, [task], bank_outputs=bank_outputs)
                if route_cost_fn is None else route_cost_fn(unit, [task]))
        if cost <= unit.budget:
            feasible.append(cost)
    min_cost = min(feasible) if feasible else 10 ** 6
    value = float(task.value) if value is None else float(value)
    density = value / max(1.0, float(min_cost))
    # Mandatory tasks first; among them, route-constrained tasks with fewer
    # feasible workers are inserted first. Optional tasks use value density.
    return (0 if task.mandatory else 1,
            len(feasible) if task.mandatory else 0,
            -density, -value, tuple(task.pos), task.kind)


def joint_assign(tasks, units, shed_stock=None, fixed_owner=None,
                 cash_budget=None, max_order_keys=None, deadline=None,
                 refine=True, selection_limits=None, bank_outputs=False,
                 bundle_model=None, memoize_route_cost=False,
                 completion_balance=False, required_ids=None):
    """Joint task selection and route-aware multi-worker assignment.

    Every insertion is priced by the change in that worker's complete open
    route.  This replaces angular partitioning, where a task was assigned
    spatially before its path cost or value was known.  The algorithm is a
    deterministic primal heuristic for the prize-collecting multi-vehicle
    problem:

      1. insert positive-value and survival tasks by route-aware marginal cost;
      2. relocate tasks across workers when this shortens total travel;
      3. replace lower-value optional work with higher-value leftovers;
      4. refill capacity exposed by relocation/replacement.

    Small final worker routes are ordered exactly by Held-Karp; insertion uses
    NN+2-opt costs to keep the all-task/all-worker search bounded.
    """
    units = list(units)
    required_ids = set(required_ids or ())
    if deadline_near(deadline, 0.015):
        return _fast_feasible_assign(
            tasks, units, shed_stock, cash_budget, max_order_keys, fixed_owner,
            selection_limits, bank_outputs, required_ids
        )
    assignment = {u.idx: [] for u in units}
    by_idx = {u.idx: u for u in units}

    # Lazy nonlinear repricing revisits a candidate's singleton cost against
    # every worker whenever its selected-item signature changes.  Route cost is
    # a pure, order-independent function of the worker, selected task set,
    # committed prefix and bank-output requirement, so an exact solve-local
    # memo removes those duplicate NN+2-opt evaluations without changing a
    # feasible set, score or tie-break.  ``id`` is used only as an identity key
    # during this call; it never enters ordering or emitted actions.
    route_cost_memo = {} if memoize_route_cost else None

    def selected_route_cost(unit, worker_tasks, prefix=None):
        if route_cost_memo is None:
            return route_cost(
                unit, worker_tasks, prefix=prefix,
                bank_outputs=bank_outputs,
            )
        key = (unit.idx, tuple(sorted(id(task) for task in worker_tasks)),
               tuple(prefix) if prefix is not None else None)
        if key not in route_cost_memo:
            cached = route_cost(
                unit, worker_tasks, prefix=prefix,
                bank_outputs=bank_outputs,
            )
            route_cost_memo[key] = cached
        return route_cost_memo[key]
    costs = {u.idx: 0 for u in units}
    selected = []
    bundle_counts = bundle_model.counts() if bundle_model is not None else None
    leftover = []
    fixed_owner = fixed_owner or {}
    prefixes = {}

    # A crew-size change is an event re-plan, not permission to make every
    # incumbent reverse direction. Preserve one still-live target per old
    # worker, then jointly optimise all remaining tasks and the new workers.
    by_position = {tuple(t.pos): t for t in tasks}
    locked = []
    for unit in sorted(units, key=lambda u: u.idx):
        positions = [tuple(pos) for pos, owner in fixed_owner.items()
                     if owner == unit.idx]
        if not positions:
            continue
        task = by_position.get(positions[0])
        if task is None or (float(task.value) <= 0 and not task.mandatory):
            continue
        if not _resources_fit(selected + [task], shed_stock, cash_budget,
                              max_order_keys, selection_limits):
            continue
        new_cost = selected_route_cost(unit, [task], prefix=task.pos)
        if new_cost > unit.budget:
            continue
        assignment[unit.idx].append(task)
        costs[unit.idx] = new_cost
        selected.append(task)
        if bundle_model is not None:
            bundle_model.update_counts(bundle_counts, task)
        locked.append(task)
        prefixes[unit.idx] = tuple(task.pos)

    eligible = [t for t in tasks if t.mandatory or float(t.value) > 0]
    rejected = [t for t in tasks if t not in eligible]
    locked_ids = {id(t) for t in locked}
    candidates = [t for t in eligible if id(t) not in locked_ids]
    # `_candidate_key` prices every task against every worker. Do not begin
    # that whole sort after prefix restoration consumed the solve budget.
    if deadline_near(deadline, 0.010):
        return _fast_feasible_assign(
            tasks, units, shed_stock, cash_budget, max_order_keys, fixed_owner,
            selection_limits, bank_outputs, required_ids
        )
    def marginal_value(task):
        return (float(task.value) if bundle_model is None else
                float(bundle_model.add_gain(task, bundle_counts)))

    def dynamic_order(task_list):
        """Yield tasks in exact current marginal-value order.

        A stale entry was valued at a smaller selected same-item quantity and
        is therefore optimistic because engine marginal sale prices never rise
        as inventory grows. Lazy repricing is exact for this greedy order.
        """
        heap = []
        for sequence, task in enumerate(task_list):
            value = marginal_value(task)
            signature = (() if bundle_model is None else
                         bundle_model.signature(task, bundle_counts))
            heapq.heappush(
                heap,
                ((0 if id(task) in required_ids else 1,
                  _candidate_key(task, units, bank_outputs, value,
                                 selected_route_cost)),
                 sequence, signature, task),
            )
        while heap:
            _key, sequence, signature, task = heapq.heappop(heap)
            current = (() if bundle_model is None else
                       bundle_model.signature(task, bundle_counts))
            if signature != current:
                value = marginal_value(task)
                heapq.heappush(
                    heap,
                    ((0 if id(task) in required_ids else 1,
                      _candidate_key(task, units, bank_outputs, value,
                                     selected_route_cost)),
                     sequence, current, task),
                )
                continue
            yield task, marginal_value(task)

    def insert(task):
        if not _resources_fit(selected + [task], shed_stock, cash_budget,
                              max_order_keys, selection_limits):
            return False
        best = None
        for unit in units:
            trial = assignment[unit.idx] + [task]
            new_cost = selected_route_cost(
                unit, trial, prefix=prefixes.get(unit.idx),
            )
            if new_cost > unit.budget:
                continue
            delta = new_cost - costs[unit.idx]
            # Capital deployed earlier starts its production/payback clock
            # earlier.  The normal daily solver minimises incremental travel;
            # an isolated opening mode instead minimises the resulting worker
            # completion time, spreading deployment across already-paid crew.
            key = ((new_cost, delta, unit.idx) if completion_balance else
                   (delta, new_cost, unit.idx))
            if best is None or key < best[0]:
                best = (key, unit, new_cost)
        if best is None:
            return False
        _key, unit, new_cost = best
        assignment[unit.idx].append(task)
        costs[unit.idx] = new_cost
        selected.append(task)
        return True

    ordered_candidates = dynamic_order(candidates)
    for task, value in ordered_candidates:
        if deadline_expired(deadline):
            leftover.append(task)
            leftover.extend(t for t, _value in ordered_candidates)
            break
        if (value <= 0 and not task.mandatory) or not insert(task):
            leftover.append(task)
        elif bundle_model is not None:
            bundle_model.update_counts(bundle_counts, task)

    # Hiring and capital compare several crew sizes. They need the SAME route
    # relaxation for each k, not a complete local search repeated k times.
    # Initial insertion already couples task value, full route cost, worker
    # budget and global resources. The finally selected daily plan still calls
    # the refined path below; candidate valuation may stop here deterministically.
    if not refine:
        leftover.extend(rejected)
        return assignment, leftover

    # Route-only coordinate descent: the task value is unchanged, so any move
    # which lowers total cost preserves objective value and exposes capacity.
    for _ in range(2):
        if deadline_expired(deadline):
            break
        changed = False
        for task in list(selected):
            if deadline_expired(deadline):
                break
            if id(task) in locked_ids:
                continue
            src_idx = next((idx for idx, ts in assignment.items() if task in ts), None)
            if src_idx is None:
                continue
            src_u = by_idx[src_idx]
            src_trial = [t for t in assignment[src_idx] if t is not task]
            src_cost = selected_route_cost(
                src_u, src_trial, prefix=prefixes.get(src_idx),
            )
            old_total = costs[src_idx]
            best = None
            for dst_u in units:
                if deadline_expired(deadline):
                    break
                if dst_u.idx == src_idx:
                    continue
                dst_trial = assignment[dst_u.idx] + [task]
                dst_cost = selected_route_cost(
                    dst_u, dst_trial, prefix=prefixes.get(dst_u.idx),
                )
                if dst_cost > dst_u.budget:
                    continue
                new_total = src_cost + dst_cost
                prior_total = old_total + costs[dst_u.idx]
                if new_total >= prior_total:
                    continue
                key = (new_total, dst_u.idx)
                if best is None or key < best[0]:
                    best = (key, dst_u, dst_cost)
            if best is not None:
                _key, dst_u, dst_cost = best
                assignment[src_idx] = src_trial
                assignment[dst_u.idx].append(task)
                costs[src_idx] = src_cost
                costs[dst_u.idx] = dst_cost
                changed = True
        if not changed:
            break

    # Prize exchange. A higher-value leftover may replace a lower-value task
    # when the original greedy packing used the scarce turns first.
    for _ in range(2):
        if deadline_expired(deadline):
            break
        best_swap = None
        for incoming in leftover:
            if deadline_expired(deadline):
                break
            if float(incoming.value) <= 0:
                continue
            for unit in units:
                if deadline_expired(deadline):
                    break
                for outgoing in assignment[unit.idx]:
                    if deadline_expired(deadline):
                        break
                    if id(outgoing) in locked_ids or outgoing.mandatory:
                        continue
                    trial = [t for t in assignment[unit.idx] if t is not outgoing]
                    trial.append(incoming)
                    new_selected = [t for t in selected if t is not outgoing] + [incoming]
                    if not _resources_fit(new_selected, shed_stock, cash_budget,
                                          max_order_keys, selection_limits):
                        continue
                    new_cost = selected_route_cost(
                        unit, trial, prefix=prefixes.get(unit.idx),
                    )
                    if new_cost > unit.budget:
                        continue
                    gain = (float(incoming.value) - float(outgoing.value)
                            if bundle_model is None else
                            bundle_model.swap_gain(
                                incoming, outgoing, bundle_counts,
                            ))
                    if gain <= 0:
                        continue
                    key = (-gain, new_cost - costs[unit.idx], unit.idx,
                           tuple(incoming.pos))
                    if best_swap is None or key < best_swap[0]:
                        best_swap = (key, unit, incoming, outgoing, trial,
                                     new_selected, new_cost)
        if best_swap is None:
            break
        (_key, unit, incoming, outgoing, trial,
         new_selected, new_cost) = best_swap
        assignment[unit.idx] = trial
        costs[unit.idx] = new_cost
        selected[:] = new_selected
        if bundle_model is not None:
            bundle_model.update_counts(bundle_counts, outgoing, -1)
            bundle_model.update_counts(bundle_counts, incoming, 1)
        leftover.remove(incoming)
        leftover.append(outgoing)

    # Relocations/swaps can expose useful slack. Reconsider the best leftovers
    # against the new complete routes.
    if deadline_near(deadline, 0.005):
        leftover.extend(rejected)
        return assignment, leftover
    still_left = []
    ordered_left = dynamic_order(leftover)
    for task, value in ordered_left:
        if deadline_expired(deadline):
            still_left.append(task)
            still_left.extend(t for t, _value in ordered_left)
            break
        if (value <= 0 and not task.mandatory) or not insert(task):
            still_left.append(task)
        elif bundle_model is not None:
            bundle_model.update_counts(bundle_counts, task)
    still_left.extend(rejected)
    return assignment, still_left


def spatial_multistart_refill(assignment, leftover, units, shed_stock=None,
                              fixed_owner=None, bank_outputs=False,
                              bundle_model=None):
    """Try a quadrant-clustered assignment, then refill released turns.

    ``joint_assign`` starts from task-level marginal insertions and can settle
    in a cross-quadrant local optimum.  This deterministic second start groups
    the *same selected tasks* by the board's public quadrant boundaries and
    assigns each next task first to a worker already serving that quadrant.
    It is accepted only when every incumbent task still fits and its exact
    aggregate route cost is strictly lower.  Positive-value leftovers may
    then use the newly exposed per-worker turns under the same stock and bundle
    objective.  Quadrant membership is only a construction order: it adds no
    bonus, penalty, target coordinate or fitted coefficient to the objective.
    """
    units = list(units)
    if len(units) < 2:
        return assignment, leftover
    by_idx = {unit.idx: unit for unit in units}
    selected = [task for unit in units for task in assignment.get(unit.idx, ())]
    if len(selected) < 2:
        return assignment, leftover

    fixed_owner = fixed_owner or {}
    prefixes = {}
    for unit in units:
        prefix = next((tuple(pos) for pos, owner in fixed_owner.items()
                       if owner == unit.idx), None)
        if prefix is not None:
            prefixes[unit.idx] = prefix

    def cost(unit, worker_tasks):
        return route_cost(
            unit, worker_tasks, prefix=prefixes.get(unit.idx),
            bank_outputs=bank_outputs,
        )

    candidate = {unit.idx: [] for unit in units}
    candidate_costs = {unit.idx: 0 for unit in units}
    worker_quadrants = {unit.idx: set() for unit in units}

    locked = []
    free = []
    for task in selected:
        owner = fixed_owner.get(tuple(task.pos))
        (locked if owner in by_idx else free).append((owner, task))
    for owner, task in sorted(
            locked, key=lambda row: (row[0], tuple(row[1].pos), row[1].kind)):
        trial = candidate[owner] + [task]
        new_cost = cost(by_idx[owner], trial)
        if new_cost > by_idx[owner].budget:
            return assignment, leftover
        candidate[owner] = trial
        candidate_costs[owner] = new_cost
        worker_quadrants[owner].add(
            (int(task.pos[0]) >= 5, int(task.pos[1]) >= 5)
        )

    free_tasks = [task for _owner, task in free]
    free_tasks.sort(key=lambda task: (
        int(task.pos[1]) >= 5, int(task.pos[0]) >= 5,
        _sweep_key(task.pos, (4.5, 4.5)), tuple(task.pos), task.kind,
    ))
    for task in free_tasks:
        quadrant = (int(task.pos[0]) >= 5, int(task.pos[1]) >= 5)
        best = None
        for unit in units:
            trial = candidate[unit.idx] + [task]
            new_cost = cost(unit, trial)
            if new_cost > unit.budget:
                continue
            spans = int(bool(worker_quadrants[unit.idx])
                        and quadrant not in worker_quadrants[unit.idx])
            key = (spans, new_cost - candidate_costs[unit.idx],
                   new_cost, unit.idx)
            if best is None or key < best[0]:
                best = (key, unit, trial, new_cost)
        if best is None:
            return assignment, leftover
        _key, unit, trial, new_cost = best
        candidate[unit.idx] = trial
        candidate_costs[unit.idx] = new_cost
        worker_quadrants[unit.idx].add(quadrant)

    incumbent_costs = {
        unit.idx: cost(unit, assignment.get(unit.idx, ())) for unit in units
    }
    if sum(candidate_costs.values()) >= sum(incumbent_costs.values()):
        return assignment, leftover

    retained_left = list(leftover)
    selected_now = list(selected)
    bundle_counts = bundle_model.counts() if bundle_model is not None else None
    if bundle_model is not None:
        for task in selected_now:
            bundle_model.update_counts(bundle_counts, task)

    def marginal(task):
        return (float(task.value) if bundle_model is None else
                float(bundle_model.add_gain(task, bundle_counts)))

    pending = sorted(retained_left, key=lambda task: (
        -marginal(task) / max(1.0, min(
            cost(unit, [task]) for unit in units
        )),
        -marginal(task), tuple(task.pos), task.kind,
    ))
    still_left = []
    for task in pending:
        value = marginal(task)
        if value <= 0 or not _resources_fit(
                selected_now + [task], shed_stock):
            still_left.append(task)
            continue
        best = None
        for unit in units:
            trial = candidate[unit.idx] + [task]
            new_cost = cost(unit, trial)
            if new_cost > unit.budget:
                continue
            key = (new_cost - candidate_costs[unit.idx], new_cost, unit.idx)
            if best is None or key < best[0]:
                best = (key, unit, trial, new_cost)
        if best is None:
            still_left.append(task)
            continue
        _key, unit, trial, new_cost = best
        candidate[unit.idx] = trial
        candidate_costs[unit.idx] = new_cost
        selected_now.append(task)
        if bundle_model is not None:
            bundle_model.update_counts(bundle_counts, task)
    return candidate, still_left


# ----------------------------------------------------------------------- emit

def build_tour(unit, tasks, shed_stock=None, prefix=None, deadline=None,
               bank_outputs=False, force_heuristic=False):
    """Turn one unit's task set into a *tour*: the pickups to make at the shed
    and the ordered (tile, ops) stops to work through.

    A tour is emitted rather than a baked move tape because a hand's real spawn
    tile is not knowable when the day is planned -- `_spawn_hand` picks the
    least-occupied shed-access tile, which depends on where the farmer happens
    to be standing. Following a tour re-derives each move from the unit's actual
    position, so a wrong guess costs a step, never a desync.

    Drops the lowest-value tasks first if the tour does not fit the budget, so
    an over-subscribed unit loses its cheapest work rather than whatever
    happened to fall at the end of the route.
    """
    tasks = list(tasks)
    budget = unit.budget
    if budget <= 0 or not tasks:
        return {
            "carry": {}, "stops": [], "tasks": [],
            "turn_cost": 0, "completion_hour": unit.start_hour,
        }

    while tasks:
        pickups = _carry_turns(tasks)
        anchor = (min(SHED_TILES, key=lambda p: (dist(unit.start, p), p))
                  if pickups else unit.start)
        # Do not start an exponential exact solve near the act deadline. The
        # deterministic NN+2-opt path is always available and engine-valid.
        exact = not force_heuristic and not deadline_near(deadline, 0.050)
        solved_order = _route_order(
            anchor, [t.pos for t in tasks], exact=exact, prefix=prefix,
        )
        # The deadline fast path certifies the task insertion order. Nearest
        # neighbour plus 2-opt is usually shorter, but is not mathematically
        # guaranteed to dominate every arbitrary feasible order. Retaining the
        # shorter of both deterministic witnesses closes the only gap through
        # which a selected mandatory survival task could be dropped here.
        insertion_order = []
        for task in tasks:
            pos = tuple(task.pos)
            if pos not in insertion_order:
                insertion_order.append(pos)
        prefix = tuple(prefix) if prefix is not None else None
        if prefix in insertion_order:
            insertion_order.remove(prefix)
            insertion_order.insert(0, prefix)

        def complete_cost(candidate_order):
            return (dist(unit.start, anchor) + pickups
                    + tour_length(anchor, candidate_order)
                    + sum(t.n_ops for t in tasks)
                    + _bank_tail(candidate_order, tasks, bank_outputs))

        order, cost = min(
            ((list(candidate), complete_cost(candidate))
             for candidate in (solved_order, insertion_order)),
            key=lambda row: (row[1], tuple(row[0])),
        )
        if cost <= budget:
            break
        optional = [task for task in tasks if not task.mandatory]
        pool = optional or tasks
        worst = min(pool, key=lambda t: (t.value, -t.n_ops))
        tasks.remove(worst)
    if not tasks:
        return {
            "carry": {}, "stops": [], "tasks": [],
            "turn_cost": 0, "completion_hour": unit.start_hour,
        }

    carry = _carry_totals(tasks)
    if shed_stock is not None:
        for item in list(carry):
            carry[item] = min(carry[item], int(shed_stock.get(item, 0)))
            if carry[item] <= 0:
                del carry[item]
            else:
                shed_stock[item] = shed_stock.get(item, 0) - carry[item]

    by_pos = {}
    for t in tasks:
        by_pos.setdefault(t.pos, []).append(t)
    stops = []
    for tile in order:
        ops = []
        for t in by_pos.get(tile, []):
            ops.extend(list(op) for op in t.ops)
        stops.append((tile, ops))
    # ``turn_cost`` is an explicit day-boundary certificate.  A task bundle is
    # admitted only when every planned pickup, move and tile operation finishes
    # by hour 24; consumers can audit this without reconstructing the route.
    # The live white-box executor normally caches only stop coordinates, but an
    # isolated manifest variant retains this complete object so its real pickup
    # and mutation sequence is the same one costed above.
    return {
        "carry": carry, "stops": stops, "tasks": tasks,
        "turn_cost": int(cost),
        "completion_hour": int(unit.start_hour + cost),
    }


def append_unbanked_suffix(unit, tour, task, bank_outputs=False):
    """Append one carry-free task without changing an incumbent tour.

    This is a stronger certificate than rebuilding the union of task sets:
    every incumbent stop and operation remains byte-for-byte ordered.  A tour
    whose existing work produces output is rejected because inserting before
    its implicit return-and-DROP tail could delay a same-day sale.  The new
    task may itself produce output; its own return tail is charged exactly.
    """
    incumbent_tasks = list((tour or {}).get("tasks", ()) or ())
    if _route_banks_output(incumbent_tasks):
        return None
    if _carry_turns([task]) or _carry_totals([task]):
        return None
    stops = [
        (tuple(pos), [list(op) for op in (ops or ())])
        for pos, ops in ((tour or {}).get("stops", ()) or ())
    ]
    current = stops[-1][0] if stops else tuple(unit.start)
    target = tuple(task.pos)
    travel = dist(current, target)
    new_tasks = incumbent_tasks + [task]
    old_cost = int((tour or {}).get("turn_cost", 0) or 0)
    order = [tuple(pos) for pos, _ops in stops]
    if stops and stops[-1][0] == target:
        stops[-1][1].extend(list(op) for op in task.ops)
    else:
        stops.append((target, [list(op) for op in task.ops]))
        order.append(target)
    new_cost = (
        old_cost + int(travel) + int(task.n_ops)
        + _bank_tail(order, new_tasks, bank_outputs)
    )
    if new_cost > int(unit.budget):
        return None
    return {
        "carry": dict((tour or {}).get("carry", {}) or {}),
        "stops": stops,
        "tasks": new_tasks,
        "turn_cost": int(new_cost),
        "completion_hour": int(unit.start_hour + new_cost),
    }


def _upgrade_required_cores(assignment, units, hard_upgrades, shed_stock=None,
                            fixed_owner=None, bank_outputs=False,
                            bundle_model=None, deadline=None):
    """Atomically replace selected survival cores by their full tile task.

    A FEED core and its full FEED/CARE/HARVEST/COLLECT task name the same
    physical visit.  They must therefore never be exposed as independent
    columns.  This routine keeps the core's worker fixed and accepts the full
    task only when the deterministic complete-route upper bound, shared stock,
    and nonlinear bundle objective all remain feasible.  No coordinate,
    opponent identity, replay datum, or fitted coefficient enters the rule.
    """
    hard_upgrades = dict(hard_upgrades or {})
    if not hard_upgrades:
        return assignment

    units = list(units)
    fixed_owner = fixed_owner or {}
    prefixes = {
        unit.idx: next((tuple(pos) for pos, owner in fixed_owner.items()
                        if owner == unit.idx), None)
        for unit in units
    }
    selected = [
        task for unit in units for task in assignment.get(unit.idx, ())
    ]
    costs = {
        unit.idx: route_cost(
            unit, assignment.get(unit.idx, ()), exact=False,
            prefix=prefixes.get(unit.idx), bank_outputs=bank_outputs,
        )
        for unit in units
    }
    bundle_counts = bundle_model.counts() if bundle_model is not None else None
    if bundle_model is not None:
        for task in selected:
            bundle_model.update_counts(bundle_counts, task)

    while not deadline_expired(deadline):
        best = None
        for unit in units:
            if deadline_expired(deadline):
                break
            worker_tasks = assignment.get(unit.idx, ())
            for offset, core in enumerate(worker_tasks):
                if deadline_expired(deadline):
                    break
                full = hard_upgrades.get(id(core))
                if full is None:
                    continue
                # Operation-level survival splitting may already have added
                # the non-FEED suffix as a second task at this coordinate.
                # Replacing the core with the historical full bundle would
                # duplicate that suffix in the emitted manifest.
                if any(
                        task is not core
                        and tuple(getattr(task, "pos", ())) == tuple(core.pos)
                        for task in worker_tasks):
                    continue
                trial = list(worker_tasks)
                trial[offset] = full
                new_selected = [
                    full if task is core else task for task in selected
                ]
                if not _resources_fit(new_selected, shed_stock):
                    continue
                new_cost = route_cost(
                    unit, trial, exact=False,
                    prefix=prefixes.get(unit.idx),
                    bank_outputs=bank_outputs,
                )
                if new_cost > unit.budget:
                    continue
                gain = (
                    float(full.value) - float(core.value)
                    if bundle_model is None else
                    float(bundle_model.swap_gain(full, core, bundle_counts))
                )
                if gain <= 1e-9:
                    continue
                delta = new_cost - costs[unit.idx]
                density = gain / max(1.0, float(delta))
                key = (-density, -gain, delta, tuple(core.pos), unit.idx)
                if best is None or key < best[0]:
                    best = (key, unit, offset, core, full, trial,
                            new_selected, new_cost)
        if best is None:
            break
        (_key, unit, _offset, core, full, trial,
         new_selected, new_cost) = best
        assignment[unit.idx] = trial
        selected[:] = new_selected
        costs[unit.idx] = new_cost
        if bundle_model is not None:
            bundle_model.update_counts(bundle_counts, core, -1)
            bundle_model.update_counts(bundle_counts, full, 1)
    return assignment


def plan_day(units, tasks, shed_stock=None, fixed_owner=None, deadline=None,
             bank_outputs=False, deterministic_primal=False,
             bundle_model=None, deterministic_refine=False,
             completion_balance=False, spatial_multistart=False,
             hard_upgrades=None):
    """Full day plan: {unit_idx: tour}, plus the tasks nobody was given."""
    hard_upgrades = dict(hard_upgrades or {})
    required_ids = set(hard_upgrades)
    assignment, leftover = joint_assign(
        tasks, units, shed_stock, fixed_owner=fixed_owner, deadline=deadline,
        refine=(deterministic_refine or not deterministic_primal),
        bank_outputs=bank_outputs,
        bundle_model=bundle_model,
        completion_balance=completion_balance,
        required_ids=required_ids,
    )
    if spatial_multistart:
        assignment, leftover = spatial_multistart_refill(
            assignment, leftover, units, shed_stock,
            fixed_owner=fixed_owner, bank_outputs=bank_outputs,
            bundle_model=bundle_model,
        )

    # `mandatory` historically affects ordering but is not a hard constraint.
    # If route competition still left a positive-value survival FEED core out,
    # re-solve the mandatory universe without optional work.  Accept this
    # conservative fallback only when it increases hard-core coverage; an
    # actual stock/turn shortfall remains visible in `undone` instead of being
    # hidden by an infeasible manifest.
    selected_ids = {
        id(task) for worker_tasks in assignment.values()
        for task in worker_tasks
    }
    if required_ids - selected_ids:
        # An operation-level survival core is a separate proof obligation. In
        # the isolated fallback arm, solve only the missing required cores;
        # carrying unrelated mandatory crop work into this re-solve can make
        # an otherwise feasible set of FEED trips compete for the same turns
        # and stock. The historical path retains its broader mandatory set.
        hard_only = bool(globals().get("SURVIVAL_FEED_ONLY_FALLBACK", False))
        hard_tasks = ([task for task in tasks if id(task) in required_ids]
                      if hard_only else [
                          task for task in tasks
                          if task.mandatory or id(task) in required_ids
                      ])
        hard_assignment, _hard_leftover = joint_assign(
            hard_tasks, units, shed_stock, fixed_owner=fixed_owner,
            deadline=None, refine=True, bank_outputs=bank_outputs,
            bundle_model=bundle_model, required_ids=required_ids,
        )
        hard_selected = {
            id(task) for worker_tasks in hard_assignment.values()
            for task in worker_tasks
        }
        old_coverage = len(required_ids & selected_ids)
        new_coverage = len(required_ids & hard_selected)
        if new_coverage > old_coverage:
            assignment = hard_assignment
            selected_ids = hard_selected
            leftover = [task for task in tasks if id(task) not in selected_ids]

    assignment = _upgrade_required_cores(
        assignment, units, hard_upgrades, shed_stock=shed_stock,
        fixed_owner=fixed_owner, bank_outputs=bank_outputs,
        bundle_model=bundle_model, deadline=deadline,
    )
    tours = {}
    scheduled = set()
    full_to_core = {id(full): core_id
                    for core_id, full in hard_upgrades.items()}
    for u in units:
        prefix = next((pos for pos, owner in (fixed_owner or {}).items()
                       if owner == u.idx), None)
        tour = build_tour(
            u, assignment[u.idx], shed_stock, prefix=prefix,
            deadline=deadline, bank_outputs=bank_outputs,
            force_heuristic=deterministic_primal,
        )
        tours[u.idx] = tour
        for t in tour["tasks"]:
            scheduled.add(id(t))
            core_id = full_to_core.get(id(t))
            if core_id is not None:
                scheduled.add(core_id)
    undone = [t for t in tasks if id(t) not in scheduled]
    return tours, undone
