"""Joint white-box hiring and task-routing decision.

A hand is valuable only through the route it can still execute today.  For
each legal hire count this module therefore rebuilds the complete daily route
for all existing workers plus the newly spawned workers, and compares the
extra scheduled task value with the exact Fibonacci hire bill.

Engine facts used here:

* hire prices are private to a farm: ``fib(farm.hires_today)``;
* every HIRE consumes one of the ten market-order slots;
* unit actions resolve before market orders, so a hand hired at hour ``h`` can
  first act at ``h + 1`` and has ``23 - h`` actions left;
* a hand spawns on the least-occupied shed-access tile, with NW/NE/SW/SE as
  the deterministic tie-break order;
* all hands disappear at the day boundary.

No opponent action trace, learned policy, fixed crew trajectory, or replay
target enters this decision.  The remaining approximation is explicit: task
values and the route solver are the current white-box relaxations of terminal
money value.
"""
import os

from route import geom, router
from route.router import Unit
from whitebox import econ, value as objective


# This is only a computational/safety ceiling, not a target crew size.  The
# Fibonacci bill, available work, cash, and market slots normally bind first.
MAX_HANDS = int(os.environ.get("WB_MAX_HANDS", "20"))
SAFETY_MULT = float(os.environ.get("WB_HIRE_SAFETY", "1.0"))
_MOVE = {
    "NORTH": (0, -1),
    "SOUTH": (0, 1),
    "WEST": (-1, 0),
    "EAST": (1, 0),
}


def _after_action(pos, action, board_size):
    """Position after this turn's unit action; market HIRE resolves after it."""
    if not action or action[0] not in _MOVE:
        return tuple(pos)
    dx, dy = _MOVE[action[0]]
    x, y = int(pos[0]) + dx, int(pos[1]) + dy
    if 0 <= x < board_size and 0 <= y < board_size:
        return (x, y)
    return tuple(pos)


def spawn_positions(snap, count, unit_actions=None):
    """Predict the engine's exact spawn tile for each HIRE in this turn.

    ``unit_actions`` is farmer-first and lets the occupancy calculation use the
    positions after the already-selected unit actions, matching engine order.
    """
    tiles = geom.shed_access_tiles(snap.board)
    positions = [tuple(snap.me.farmer)] + [tuple(p) for p in snap.me.hands]
    if unit_actions:
        positions = [
            _after_action(p, unit_actions[i] if i < len(unit_actions) else None,
                          snap.board)
            for i, p in enumerate(positions)
        ]
    occupancy = {p: 0 for p in tiles}
    for p in positions:
        if p in occupancy:
            occupancy[p] += 1

    out = []
    for _ in range(max(0, int(count))):
        spawn = min(tiles, key=lambda p: (occupancy[p], tiles.index(p)))
        out.append(spawn)
        occupancy[spawn] += 1
    return out


def _scheduled_value(tours):
    """Sum each scheduled task once, even if a future solver shares bundles."""
    seen = set()
    value = 0.0
    for tour in tours.values():
        for task in (tour or {}).get("tasks", ()):
            ident = id(task)
            if ident not in seen:
                seen.add(ident)
                value += float(task.value)
    return value


def route_value(snap, tasks, new_hands=0, unit_actions=None, plan=None,
                deadline=None, bank_outputs=False):
    """Optimal value under the current transparent route relaxation.

    Existing workers may act at the current hour. New workers are appended at
    deterministic spawn tiles and start one hour later. Crucially, every
    candidate reroutes *all* workers; a hire is not priced only against the old
    planner's leftover list.
    """
    units = [Unit(0, tuple(snap.me.farmer), snap.hour)]
    units.extend(Unit(i + 1, tuple(pos), snap.hour)
                 for i, pos in enumerate(snap.me.hands))
    first_new_idx = len(units)
    for j, pos in enumerate(spawn_positions(snap, new_hands, unit_actions)):
        units.append(Unit(first_new_idx + j, pos, snap.hour + 1))
    stock = objective.planned_shed_stock(snap, plan)
    assignment, _undone = router.joint_assign(
        list(tasks), units, stock, deadline=deadline, refine=False,
        bank_outputs=bank_outputs,
    )
    # Hiring needs the labour value curve, not emitted movement instructions.
    # The same joint master is used, while exact per-worker path reconstruction
    # is deferred to the one plan that is actually selected next turn.
    seen = set()
    value = 0.0
    for worker_tasks in assignment.values():
        for task in worker_tasks:
            ident = id(task)
            if ident not in seen:
                seen.add(ident)
                value += float(task.value)
    return value


def decision_curve(snap, plan, tasks, max_orders=econ.MAX_ORDERS,
                   unit_actions=None, deadline=None, bank_outputs=False,
                   task_factory=None):
    """Return auditable rows for every economically feasible hire count.

    ``task_factory(k)`` is the joint-planning seam: a candidate crew size may
    expose capital/work columns which do not exist for a smaller crew.  The
    legacy fixed-task call remains valid, but it can only value rerouting the
    work it was given and therefore cannot claim that extra labour has no
    productive use outside that fixed set.

    The finite enumeration bound comes only from public engine constraints:
    remaining market slots, the configured persistent hand safety ceiling and
    cash for the exact Fibonacci prefix.  There is deliberately no observed
    or replay-derived crew-size cap.
    """
    current_hands = len(snap.me.hands)
    room = max(0, min(int(max_orders), MAX_HANDS - current_hands))
    task_cache = {}

    def tasks_for(k):
        k = int(k)
        if k not in task_cache:
            task_cache[k] = list(task_factory(k) if task_factory else tasks)
        return task_cache[k]

    # A market-phase hire at hour 23 is cleared before it ever gets an action.
    base_tasks = tasks_for(0)
    if snap.hour + 1 >= econ.TURNS_PER_DAY or room <= 0:
        return [{"hires": 0, "route_value": route_value(snap, base_tasks, 0,
                                                         unit_actions, plan,
                                                         deadline, bank_outputs),
                 "hire_cost": 0.0, "net_gain": 0.0}]

    # ``cash_floor`` is protected literally.  A strategy-level reserve must not
    # be silently reinterpreted as a fixed five-person crew budget here; each
    # candidate pays its own exact private-counter Fibonacci prefix below.
    protected = max(0.0, float(getattr(plan, "cash_floor", 0.0)))
    spendable = max(0.0, float(snap.me.money) - protected)

    base = route_value(snap, base_tasks, 0, unit_actions, plan, deadline,
                       bank_outputs)
    rows = [{"hires": 0, "route_value": base,
             "hire_cost": 0.0, "net_gain": 0.0}]

    # First establish the exact cash-feasible Fibonacci prefix.  For a dynamic
    # task factory we inspect every remaining candidate universe before using a
    # value bound; stopping from only F(k) would be unsafe when F(k+1) creates
    # new positive work.
    feasible = [0]
    for k in range(1, room + 1):
        cost = float(econ.hire_block_cost(snap.me.hires_today, k))
        if cost > spendable:
            break
        feasible.append(k)
    upper = max(
        sum(max(0.0, float(task.value)) for task in tasks_for(k))
        for k in feasible
    )

    for k in feasible[1:]:
        marginal_wage = float(econ.hire_cost(snap.me.hires_today + k - 1))
        # Future Fibonacci wages never fall.  Even the best remaining task
        # universe cannot repay the very next wage, so no larger prefix can
        # beat the current arm.  This is a proof bound, not a crew heuristic.
        if marginal_wage > upper - rows[-1]["route_value"] + 1e-9:
            break
        if router.deadline_expired(deadline):
            break
        cost = float(econ.hire_block_cost(snap.me.hires_today, k))
        value = route_value(snap, tasks_for(k), k, unit_actions, plan, deadline,
                            bank_outputs)
        rows.append({"hires": k, "route_value": value,
                     "hire_cost": cost,
                     "net_gain": value - base - SAFETY_MULT * cost})
    return rows


def decide(snap, plan, tasks, max_orders=econ.MAX_ORDERS, unit_actions=None,
           deadline=None, bank_outputs=False, task_factory=None):
    """Choose the hire count maximizing rerouted task value minus exact cost."""
    rows = decision_curve(
        snap, plan, tasks, max_orders, unit_actions, deadline, bank_outputs,
        task_factory,
    )
    best = max(rows, key=lambda r: (r["net_gain"], -r["hire_cost"], -r["hires"]))
    return int(best["hires"]) if best["net_gain"] > 0 else 0
