"""One-step capital/task/crew master problem.

Market acquisition used to happen before labour planning: buy assets toward a
target, then hope the route solver could service them.  Here every proposed
seed or animal unit becomes an *optional task column*.  Selecting the column
simultaneously commits its cash, its shared market-order key and its executable
PLANT or BUILD->PLACE route.  A task on the next locked quadrant also activates
the one-time BUY_LAND cost and order.

For every legal hire count the same joint route master selects existing work
and capital columns under cash, ten market slots, carried inputs and remaining
worker turns.  No replay, opponent action trace or fitted schedule enters the
decision; the proposal ceiling still comes from the current computed Plan.
"""
import copy
import itertools
from collections import Counter, defaultdict

from route import router
from route.router import Task, Unit
from whitebox import econ, hiring, paths, value as objective
try:
    from whitebox import market_model as MM
except Exception:
    MM = None


ASSET_OPS = frozenset(("BUY_SEED", "BUY_ANIMAL", "BUY_LAND"))

# Opt-in research guard.  The production baseline keeps its qualified action
# path unchanged; a candidate may require every newly selected animal row to
# have a complete public FEED/CARE continuation certificate before emission.
FAILURE_CLOSED_ANIMAL_ADMISSION = False
_DEFERRED_HIRES = {}
_BOUNDED_COMMITMENTS = {}
_LAND_USE_COVENANTS = {}
_LAND_TURNOVER_EXERCISED = set()
_LAND_TURNOVER_COMMITMENTS = {}
_LATE_LAND_DEFERRED_HIRES_VARIANT = (
    "crew_conditioned_positioned_scenario_late_land_"
    "candidate_bound_deferred_hires_deterministic"
)
_LAND_RECOVERY_COVENANT_VARIANT = (
    "crew_conditioned_positioned_scenario_late_land_"
    "candidate_bound_first_output_covenant_deterministic"
)
_BOUNDED_COMMITMENT_VARIANT = (
    "crew_conditioned_positioned_scenario_late_land_"
    "bounded_execution_capital_deterministic"
)
_FEASIBILITY_CLOSED_VARIANT = (
    "crew_conditioned_positioned_scenario_late_land_"
    "feasibility_closed_deterministic"
)
_SATURATED_BOOK_VARIANT = (
    "crew_conditioned_positioned_scenario_late_land_"
    "saturated_book_deterministic"
)
_EXACT_CAPACITY_FRONTIER_VARIANT = (
    "crew_conditioned_positioned_scenario_late_land_"
    "exact_capacity_frontier_deterministic"
)
_PRECERTIFIED_CAPACITY_FRONTIER_VARIANT = (
    "crew_conditioned_positioned_scenario_late_land_"
    "precertified_capacity_frontier_deterministic"
)
_STAGED_FOLLOWER_REINVESTMENT_VARIANT = (
    "crew_conditioned_positioned_scenario_late_land_"
    "staged_follower_reinvestment_deterministic"
)
_STAGED_STANDING_BOOK_VARIANT = (
    "crew_conditioned_positioned_standing_scenario_late_land_"
    "staged_follower_reinvestment_deterministic"
)
_COMPLETE_STAGED_STANDING_VARIANT = (
    "crew_conditioned_positioned_complete_standing_scenario_late_land_"
    "staged_follower_reinvestment_deterministic"
)
_ROBUST_STAGED_REALISATION_VARIANT = (
    "crew_conditioned_positioned_robust_realisations_scenario_late_land_"
    "staged_follower_reinvestment_deterministic"
)
_STAGED_FOLLOWER_LAND_REINVESTMENT_VARIANT = (
    "crew_conditioned_positioned_scenario_late_land_"
    "staged_follower_land_reinvestment_deterministic"
)
_STAGED_FOLLOWER_MIXED_REINVESTMENT_VARIANT = (
    "crew_conditioned_positioned_scenario_late_land_"
    "staged_follower_mixed_reinvestment_deterministic"
)
_PAID_ROTATION_SUBSTITUTION_VARIANT = (
    "crew_conditioned_positioned_scenario_late_land_"
    "paid_rotation_substitution_deterministic"
)
_BACKLOGGED_ROTATION_SUBSTITUTION_VARIANT = (
    "crew_conditioned_positioned_scenario_late_land_"
    "backlogged_rotation_substitution_deterministic"
)
_WEED_BACKLOG_HIRES_VARIANT = (
    "crew_conditioned_positioned_scenario_late_land_"
    "weed_backlog_hires_deterministic"
)
_SINGLE_BACKLOG_ROTATION_VARIANT = (
    "crew_conditioned_positioned_scenario_late_land_"
    "single_backlog_rotation_deterministic"
)


def _service_operation_load(snap, item):
    """Exact remaining operation count for one positioned asset.

    This only orders a finite layout action set. The winner is still accepted
    by the full route/cash/Stackelberg certificate below. Fertilizer collection
    is included because it is an engine-created operation, not a fitted weight.
    """
    from whitebox import cashflow as _cashflow
    stops, _feed, _outputs, error = _cashflow._profiles_positioned(
        snap, {str(item): [(0, 0)]}, start_day=int(snap.day),
        credit_fertilizer=True,
    )
    if error or stops is None:
        return 0
    return sum(int(ops) for day_stops in stops.values()
               for _pos, ops in day_stops)


def _productive_shed_layouts(snap, positions_by_item, assets, blocked=()):
    """Yield count-preserving layouts using legal zero-distance farm cells.

    Each arm replaces equally many farthest newly-selected slots with
    available shed-access cells, then assigns the largest exact service load
    to the nearest slots. Counts, hires, land, and standing assets never move.
    """
    positioned = {
        str(item): [tuple(pos) for pos in positions]
        for item, positions in (positions_by_item or {}).items() if positions
    }
    base_slots = [pos for positions in positioned.values() for pos in positions]
    if not base_slots:
        return
    has_land = any(order and order[0] == "BUY_LAND" for order in assets or ())
    allowed = set(snap.me.unlocked)
    if has_land and econ.can_buy_land(len(snap.me.unlocked)):
        allowed.add(econ.LAND_ORDER[len(snap.me.unlocked) - 1])
    occupied = set(base_slots) | {tuple(pos) for pos in blocked}
    targets = []
    for pos in paths.SHED_TILES:
        quadrant = paths.quadrant_of(*pos, snap.board)
        if quadrant not in allowed or tuple(pos) in occupied:
            continue
        raw = snap.me.tiles[pos[1]][pos[0]]
        if raw is None or (raw == "LOCKED" and quadrant not in snap.me.unlocked):
            targets.append(tuple(pos))
    if not targets:
        return

    # A pre-built structure cannot be freely reassigned like an empty tile.
    fixed = {}
    movable = []
    for item, positions in positioned.items():
        for pos in positions:
            raw = snap.me.tiles[pos[1]][pos[0]]
            if isinstance(raw, dict) and raw.get("kind") in ("PASTURE", "COOP"):
                fixed[pos] = item
            else:
                movable.append((item, pos))
    if not movable:
        return
    targets.sort(key=lambda pos: (
        econ.LAND_ORDER.index(paths.quadrant_of(*pos, snap.board))
        if paths.quadrant_of(*pos, snap.board) in econ.LAND_ORDER else -1,
        pos,
    ))
    service_load = {
        item: _service_operation_load(snap, item) for item in positioned
    }
    items = sorted(
        (item for item, _pos in movable),
        key=lambda item: (-service_load[item], item),
    )
    original_slots = [pos for _item, pos in movable]
    original = {
        item: tuple(sorted(positions))
        for item, positions in sorted(positioned.items())
    }
    for quantity in range(1, min(len(targets), len(original_slots)) + 1):
        removed = set(sorted(
            original_slots,
            key=lambda pos: (-paths.dist_to_shed(pos), pos),
        )[:quantity])
        trial_slots = [pos for pos in original_slots if pos not in removed]
        trial_slots.extend(targets[:quantity])
        trial_slots.sort(key=lambda pos: (paths.dist_to_shed(pos), pos))
        trial = defaultdict(list)
        for pos, item in fixed.items():
            trial[item].append(pos)
        for item, pos in zip(items, trial_slots):
            trial[item].append(pos)
        clean = {
            item: tuple(sorted(positions))
            for item, positions in sorted(trial.items()) if positions
        }
        if clean != original:
            yield clean


def _positioned_full_service_route_costs(snap, positioned,
                                         credit_fertilizer=True):
    """Exact future closed-route costs for standing plus positioned capital.

    Current-day BUILD/PLACE or PLANT/WATER belongs to the capital route that
    actually buys the batch. This suffix starts from the current placement
    phase, defers a new animal's first service until tomorrow, and then removes
    today's capital stops. Every future route is pickup-aware: any number of
    FEED operations share exactly one WHEAT PICKUP on that route.
    """
    from whitebox import cashflow as _cashflow

    positioned = {
        str(item): tuple(tuple(pos) for pos in positions)
        for item, positions in (positioned or {}).items() if positions
    }
    horizon = int(_cashflow.LAST_DAY)
    stops, _feed, pickups = _cashflow._visible_full_service_profile(
        snap, horizon,
    )
    stops = defaultdict(list, {
        int(day): list(day_stops) for day, day_stops in stops.items()
    })
    pickups = defaultdict(lambda: defaultdict(set), {
        int(day): defaultdict(set, {
            tuple(pos): set(items) for pos, items in by_position.items()
        })
        for day, by_position in pickups.items()
    })
    start = int(snap.day)
    if positioned:
        extra, _extra_feed, _outputs, error = _cashflow._profiles_positioned(
            snap, positioned, start_day=start,
            defer_first_animal_service=True,
            credit_fertilizer=bool(credit_fertilizer),
        )
        if error or extra is None:
            return None
        extra.pop(start, None)
        for day, day_stops in extra.items():
            stops[int(day)].extend(day_stops)

    for kind in sorted(econ.ANIMALS):
        positions = positioned.get(kind, ())
        if not positions:
            continue
        events = _cashflow._animal_event_days(kind, start)
        if not events:
            return None
        last_refresh = int(events[-1])
        for day in range(start + 1, last_refresh + 1):
            for pos in positions:
                pickups[int(day)][tuple(pos)].add("WHEAT")

    costs_by_day = {}
    for day in sorted(stops):
        routes = _cashflow._pack_shared_routes_with_pickups(
            stops[day], pickups.get(day, {}),
        )
        if routes is None:
            return None
        costs_by_day[int(day)] = tuple(
            _cashflow._shared_route_cost(route) + len({
                item
                for pos, _ops in route
                for item in pickups.get(day, {}).get(tuple(pos), ())
            })
            for route in routes
        )
    return costs_by_day


def _service_route_signature(snap, positioned_animals):
    """Pickup-aware rule-work signature used only to order layout candidates.

    It contains no learned compactness reward. Workers, route turns and the
    longest executable route come from the same public service calendar later
    used by the acceptance certificate; shed distance and coordinates are
    deterministic tie-breaks only.
    """
    proposed = {
        str(item): tuple(tuple(pos) for pos in positions)
        for item, positions in (positioned_animals or {}).items()
        if item in econ.ANIMALS and positions
    }
    costs_by_day = _positioned_full_service_route_costs(snap, proposed)
    if costs_by_day is None:
        # This function only ranks finite layout candidates; it is not the
        # acceptance certificate.  A far corner can overflow the conservative
        # hired-hand route budget solely because fertilizer collection and its
        # extra pickup coincide with a harvest.  Rank that candidate using the
        # same public service calendar with optional fertilizer collection
        # removed, while the caller's strict certificate still rejects any
        # layout that cannot execute the full workload.
        costs_by_day = _positioned_full_service_route_costs(
            snap, proposed, credit_fertilizer=False,
        )
    if costs_by_day is None:
        return None
    workers = sum(len(costs) for costs in costs_by_day.values())
    turns = sum(sum(costs) for costs in costs_by_day.values())
    largest_route = max(
        [0] + [cost for costs in costs_by_day.values() for cost in costs]
    )
    positions = tuple(sorted(
        tuple(pos) for positions in proposed.values() for pos in positions
    ))
    shed_distance = sum(paths.dist_to_shed(pos) for pos in positions)
    return (int(workers), int(turns), int(largest_route),
            int(shed_distance), positions)


def _service_cluster_layouts(snap, positions_by_item, assets, blocked=()):
    """Yield finite route-minimal layouts for newly selected assets only.

    Existing capital never moves. Pre-built structures selected by the base
    plan remain attached to their compatible animal. Every other candidate
    cell is an engine-legal empty cell in an owned quadrant, or in the single
    next quadrant already paid for by the unchanged BUY_LAND order. Starting
    from each public shed corner, a deterministic greedy construction adds the
    cell whose exact rule-service route signature is smallest. Crops then
    inherit the unused base slots; therefore item counts, market orders, land,
    and occupied-cell cardinality remain unchanged.
    """
    positioned = {
        str(item): tuple(tuple(pos) for pos in positions)
        for item, positions in (positions_by_item or {}).items() if positions
    }
    counts = {item: len(positions)
              for item, positions in positioned.items()}
    if not positioned or not any(item in econ.ANIMALS for item in counts):
        return

    has_land = any(order and order[0] == "BUY_LAND"
                   for order in assets or ())
    unlocked = set(snap.me.unlocked)
    next_quadrant = None
    if has_land and econ.can_buy_land(len(snap.me.unlocked)):
        next_quadrant = econ.LAND_ORDER[len(snap.me.unlocked) - 1]
        unlocked.add(next_quadrant)
    blocked = {tuple(pos) for pos in blocked}

    fixed_animals = defaultdict(list)
    movable_animals = []
    movable_base_slots = []
    for item, positions in sorted(positioned.items()):
        for pos in positions:
            raw = snap.me.tiles[pos[1]][pos[0]]
            if (item in econ.ANIMALS and isinstance(raw, dict)
                    and raw.get("kind") in ("PASTURE", "COOP")):
                if raw.get("kind") != econ.ANIMALS[item]["structure"]:
                    return
                # A compatible structure is already paid and physically
                # attached to this placement. Moving the animal would add an
                # unselected BUILD rather than merely change route geometry.
                fixed_animals[item].append(pos)
            elif item in econ.ANIMALS and tuple(pos) in paths.SHED_SET:
                # A preceding certified shed-access relocation has already
                # selected this zero-distance animal cell. Preserve it while
                # clustering the remaining animals; otherwise this later
                # challenger could silently undo the stronger layout.
                fixed_animals[item].append(pos)
            else:
                movable_base_slots.append(pos)
                if item in econ.ANIMALS:
                    movable_animals.append((item, pos))
    if not movable_animals:
        return

    pool = []
    for y, board_row in enumerate(snap.me.tiles):
        for x, raw in enumerate(board_row):
            pos = (x, y)
            quadrant = paths.quadrant_of(x, y, snap.board)
            if (quadrant not in unlocked or pos in blocked
                    or not paths.productive_tile_allowed(snap, pos)):
                continue
            if raw is None or (raw == "LOCKED" and quadrant == next_quadrant):
                pool.append(pos)
    pool = sorted(set(pool))
    if len(pool) < len(movable_animals):
        return

    service_load = {
        item: _service_operation_load(snap, item)
        for item in set(positioned)
    }
    movable_animals.sort(
        key=lambda row: (-service_load[row[0]], row[0], row[1]),
    )
    fixed = {
        item: list(positions)
        for item, positions in fixed_animals.items()
    }
    original = tuple(sorted(
        (item, tuple(sorted(positions)))
        for item, positions in positioned.items()
    ))
    emitted = set()

    rays = [
        ((entry,), tuple(movable_animals[:index] + movable_animals[index + 1:]))
        for index, entry in enumerate(movable_animals)
    ]
    rays.extend(
        (tuple(movable_animals[:quantity]), tuple(movable_animals[quantity:]))
        for quantity in range(2, len(movable_animals) + 1)
    )
    for relocating, retained in rays:
        retained_positions = {pos for _item, pos in retained}
        available = [pos for pos in pool if pos not in retained_positions]
        starts = [None]
        starts.extend(
            min(available, key=lambda pos: (paths.dist(shed, pos), pos))
            for shed in paths.SHED_TILES
        )
        starts = list(dict.fromkeys(starts))

        for forced in starts:
            chosen = {
                item: list(positions) for item, positions in fixed.items()
            }
            for item, pos in retained:
                chosen.setdefault(item, []).append(pos)
            remaining = list(available)
            valid = True
            for index, (item, _old_pos) in enumerate(relocating):
                candidates = (
                    [forced] if index == 0 and forced is not None
                    else remaining
                )
                arms = []
                for pos in candidates:
                    if pos not in remaining:
                        continue
                    trial = {kind: list(positions)
                             for kind, positions in chosen.items()}
                    trial.setdefault(item, []).append(pos)
                    signature = _service_route_signature(snap, trial)
                    if signature is not None:
                        arms.append((signature, pos))
                if not arms:
                    valid = False
                    break
                _signature, winner = min(arms)
                chosen.setdefault(item, []).append(winner)
                remaining.remove(winner)
            if not valid:
                continue

            animal_positions = {
                pos for item, positions in chosen.items()
                if item in econ.ANIMALS for pos in positions
            }
            crop_slots = sorted(
                (pos for pos in movable_base_slots
                 if pos not in animal_positions),
                key=lambda pos: (paths.dist_to_shed(pos), pos),
            )
            crop_items = sorted(
                (item for item, amount in counts.items()
                 if item in econ.CROPS for _ in range(amount)),
                key=lambda item: (-service_load[item], item),
            )
            if len(crop_slots) < len(crop_items):
                continue
            layout = defaultdict(list)
            for item, positions in chosen.items():
                layout[item].extend(positions)
            for item, pos in zip(crop_items, crop_slots):
                layout[item].append(pos)
            clean = {
                item: tuple(sorted(positions))
                for item, positions in sorted(layout.items()) if positions
            }
            if ({item: len(positions)
                    for item, positions in clean.items()} != counts):
                continue
            if next_quadrant is not None and not any(
                    paths.quadrant_of(*pos, snap.board) == next_quadrant

                    for positions in clean.values() for pos in positions):
                continue
            key = tuple(sorted(clean.items()))
            if key == original or key in emitted:
                continue
            emitted.add(key)
            yield clean

def split_orders(orders):
    """Return non-capital orders and the computed acquisition proposal."""
    fixed, proposed = [], []
    for order in orders or ():
        copy = list(order)
        if copy and copy[0] in ASSET_OPS:
            proposed.append(copy)
        else:
            fixed.append(copy)
    return fixed, proposed


def _fixed_spend(snap, orders):
    """Visible-book cash required before any sale can finance later work."""
    total = 0.0
    inventory = dict(snap.market_inv)
    for order in orders:
        if not order or len(order) < 3 or order[0] != "BUY_PRODUCT":
            continue
        item, qty = order[1], max(0, int(order[2]))
        if item not in econ.BUYABLE:
            continue
        inv = int(inventory.get(item, econ.MARKET_I0) or econ.MARKET_I0)
        total += econ.buy_cost(item, qty, inv)
        inventory[item] = inv - qty
    return total


def _committed_asset_cost(order):
    """Rule cost of one explicitly retained future capital order."""
    if not order or len(order) < 3:
        return 0.0
    operation, item, quantity = order[0], str(order[1]), max(0, int(order[2]))
    if operation == "BUY_SEED" and item in econ.CROPS:
        return float(econ.CROPS[item]["seed"]) * quantity
    if operation == "BUY_ANIMAL" and item in econ.ANIMALS:
        return float(econ.ANIMALS[item]["cost"]) * quantity
    return float("inf")


def _clear_bounded_commitment(seat):
    _BOUNDED_COMMITMENTS.pop(int(seat), None)
    from whitebox import tasks as _task_planner
    _task_planner.clear_service_commitment(seat)


def _clear_land_use_covenant(seat):
    _LAND_USE_COVENANTS.pop(int(seat), None)


def _clear_land_turnover_exercises(seat):
    seat = int(seat)
    _LAND_TURNOVER_EXERCISED.difference_update(
        tuple(
            key for key in _LAND_TURNOVER_EXERCISED if key[0] == seat
        )
    )
    _LAND_TURNOVER_COMMITMENTS.pop(seat, None)


def _pure_next_land_bundle(snap, row):
    """Whether every selected capital position needs the next quadrant."""
    assets = [list(order) for order in row.get("assets", ())]
    if not any(order and order[0] == "BUY_LAND" for order in assets):
        return False
    owned_extra = len(snap.me.unlocked) - 1
    if not (0 <= owned_extra < len(econ.LAND_ORDER)):
        return False
    next_quadrant = str(econ.LAND_ORDER[owned_extra])
    positions = [
        tuple(pos)
        for item_positions in row.get("positions_by_item", {}).values()
        for pos in item_positions
    ]
    return bool(positions) and all(
        paths.quadrant_of(*pos, snap.board) == next_quadrant
        for pos in positions
    )


def _without_pure_land_bundle(row, **audit):
    """Return the exact incumbent-work row underlying a pure land bundle."""
    ordinary = list(row.get("selected_ordinary_tasks", ()))
    out = dict(row)
    out.update({
        "assets": [],
        "positions_by_item": {},
        "selected_counts": {},
        "proposed_counts": {},
        "capital_cash": 0.0,
        "order_keys": 0,
        "completed_tasks": len(ordinary),
    })
    out.update(audit)
    return out


def _store_land_use_covenant(snap, row):
    """Bind crop-valued new land to crops until its first realised output.

    The challenger bought one public quadrant because a named crop ray won.
    Until that crop can first produce, allowing a later daily replan to turn
    the same capacity into animals would execute an action absent from the
    land certificate.  The restriction is generated from this own action and
    the engine crop calendar, and expires automatically at first output.
    """
    crop = row.get("late_land_crop")
    if crop not in econ.CROPS:
        return
    owned_extra = len(snap.me.unlocked) - 1
    if not (0 <= owned_extra < len(econ.LAND_ORDER)):
        return
    _LAND_USE_COVENANTS[int(snap.seat)] = {
        "created_day": int(snap.day),
        "release_day": (
            int(snap.day) + int(econ.CROPS[crop]["first_yield_day"])
        ),
        "quadrant": str(econ.LAND_ORDER[owned_extra]),
        "crop": str(crop),
    }


def _animal_position_permitted(snap, pos):
    """Whether new animal capital may occupy ``pos`` under our own covenant."""
    seat = getattr(snap, "seat", None)
    if seat is None:
        return True
    record = _LAND_USE_COVENANTS.get(int(seat))
    if not record:
        return True
    if int(snap.day) >= int(record.get("release_day", -1)):
        _clear_land_use_covenant(snap.seat)
        return True
    return paths.quadrant_of(*tuple(pos), snap.board) != record["quadrant"]


def _new_animal_capital_permitted(snap):
    """Prevent a crop-land certificate from creating indirect herd capacity.

    Moving later crop purchases onto the new quadrant can free an old tile for
    an animal, so a position-only covenant is not closed under replanning.
    Existing animals remain fully serviceable; only unmodelled later purchases
    are absent until the selected crop produces and the covenant expires.
    """
    seat = getattr(snap, "seat", None)
    if seat is None:
        return True
    record = _LAND_USE_COVENANTS.get(int(seat))
    if not record:
        return True
    if int(snap.day) >= int(record.get("release_day", -1)):
        _clear_land_use_covenant(snap.seat)
        return True
    return False


def _store_bounded_commitment(snap, row, field="late_fill"):
    """Retain one winning finite certificate as an executable covenant."""
    routes_by_day = {
        int(day): tuple(routes) for day, routes in
        row.get(field + "_execution_routes_by_day", {}).items()
    }
    hires_by_day = {
        int(day): tuple(int(qty) for qty in phases)
        for day, phases in
        row.get(field + "_execution_hire_phases_by_day", {}).items()
    }
    asset_order = tuple(row.get(field + "_reinvestment_order", ()) or ())
    asset_day = (int(snap.day) + 1 if asset_order else -1)
    asset_positions = {
        str(item): tuple(tuple(pos) for pos in positions)
        for item, positions in
        row.get(field + "_reinvestment_positions_by_item", {}).items()
    }
    positions_by_day = {
        int(day): tuple(sorted({
            tuple(pos) for route in routes for pos, _ops in route
        }))
        for day, routes in routes_by_day.items()
    }
    dated = set(routes_by_day) | set(hires_by_day)
    if asset_day >= 0:
        dated.add(asset_day)
    if not dated:
        _clear_bounded_commitment(snap.seat)
        return
    record = {
        "created_day": int(snap.day),
        "end_day": max(dated),
        "asset_day": asset_day,
        "asset_order": asset_order,
        "asset_positions_by_item": asset_positions,
        "routes_by_day": routes_by_day,
        "hires_by_day": hires_by_day,
        "requested_by_day": {},
        "executed_by_day": {},
    }
    _BOUNDED_COMMITMENTS[int(snap.seat)] = record
    from whitebox import tasks as _task_planner
    _task_planner.commit_service_schedule(
        snap.seat, snap.day, positions_by_day,
    )


def _bounded_commitment_choice(snap, plan, market_orders):
    """Execute the selected dated purchase/hire witness, or return ``None``.

    The commitment suppresses unmodelled new capital through its finite
    horizon.  Live cash, hand capacity and the ten-order queue can only reduce
    its hire prefix; a future asset is emitted atomically only when every
    named position and its full cash bill remain feasible.
    """
    record = _BOUNDED_COMMITMENTS.get(int(snap.seat))
    if not record:
        return None
    day = int(snap.day)
    if day <= int(record.get("created_day", day)):
        return None
    if day > int(record.get("end_day", -1)):
        _clear_bounded_commitment(snap.seat)
        return None

    fixed, _proposed = split_orders(market_orders)
    if int(snap.hour) > 1:
        return 0, [], fixed

    phases = tuple(record.get("hires_by_day", {}).get(day, (0, 0)))
    phase_index = 0 if int(snap.hour) == 0 else 1
    requested = max(
        0, int(phases[phase_index] if phase_index < len(phases) else 0),
    )
    assets = []
    if int(snap.hour) == 0 and day == int(record.get("asset_day", -1)):
        order = tuple(record.get("asset_order", ()))
        positions = record.get("asset_positions_by_item", {})
        if order:
            from whitebox import tasks as _task_planner
            item = str(order[1]) if len(order) >= 2 else ""
            named = tuple(positions.get(item, ()))
            valid = (len(order) >= 3 and len(named) == int(order[2])
                     and all(_task_planner._position_accepts_item(
                         snap, tuple(pos), item,
                     ) for pos in named))
            asset_cost = _committed_asset_cost(order)
            protected = max(
                0.0,
                float(getattr(plan, "cash_floor", 0.0) or 0.0),
                float(getattr(plan, "service_cash_floor", 0.0) or 0.0),
            )
            if (not valid or asset_cost == float("inf")
                    or _fixed_spend(snap, fixed) + asset_cost
                    > float(snap.me.money) - protected + 1e-9):
                # The observed state has invalidated the retained action.  A
                # stale asset must never be partially purchased or planted on
                # a different tile; release the covenant to the live planner.
                _clear_bounded_commitment(snap.seat)
                return None
            assets = [list(order)]
            _task_planner.commit_capital_positions(
                snap.seat, day, positions,
            )

    prerequisite = [
        order for order in fixed
        if order and order[0] == "BUY_PRODUCT"
    ]
    room = max(0, min(
        requested,
        hiring.MAX_HANDS - len(snap.me.hands),
        econ.MAX_ORDERS - len(prerequisite) - len(assets),
    ))
    protected = max(
        0.0,
        float(getattr(plan, "cash_floor", 0.0) or 0.0),
        float(getattr(plan, "service_cash_floor", 0.0) or 0.0),
    )
    committed_spend = (
        float(_fixed_spend(snap, fixed))
        + sum(_committed_asset_cost(order) for order in assets)
    )
    spendable = max(
        0.0, float(snap.me.money) - protected - committed_spend,
    )
    executable = 0
    for quantity in range(1, room + 1):
        if float(econ.hire_block_cost(
                snap.me.hires_today, quantity)) > spendable + 1e-9:
            break
        executable = quantity
    record["requested_by_day"][(day, int(snap.hour))] = requested
    record["executed_by_day"][(day, int(snap.hour))] = executable
    return int(executable), assets, fixed


def _proposal_counts(proposed):
    seeds, animals, buy_land = Counter(), Counter(), False
    for order in proposed:
        if not order:
            continue
        if order[0] == "BUY_LAND":
            buy_land = True
        elif len(order) >= 3 and order[0] == "BUY_SEED":
            seeds[order[1]] += max(0, int(order[2]))
        elif len(order) >= 3 and order[0] == "BUY_ANIMAL":
            animals[order[1]] += max(0, int(order[2]))
    return seeds, animals, buy_land


def _land_activation(snap, buy_land):
    owned_extra = len(snap.me.unlocked) - 1
    if not buy_land or not econ.can_buy_land(len(snap.me.unlocked)):
        return None, {}
    quadrant = econ.LAND_ORDER[owned_extra]
    key = ("BUY_LAND", quadrant)
    return quadrant, {key: float(econ.LAND_PRICES[owned_extra])}


def _opp_animal_product_units(snap, product):
    """Worst-case visible opponent output under full FEED+CARE service."""
    total = 0
    for tile in snap.opp.animals.values():
        kind = tile.get("animal")
        spec = econ.ANIMALS.get(kind)
        if spec is None or spec["product"] != product:
            continue
        events = objective._animal_event_days(
            tile, kind, snap.day, include_start=True
        )
        total += int(tile.get("yield_units", 0) or 0)
        total += len(events) + max(0, len(events) - 1)
    return total


def _endogenous_proposal(snap, proposed):
    """Invent a white-box herd instead of merely trimming fixed targets.

    For each animal product, expected town absorption over its productive
    horizon is an engine-derived capacity. The adversarial supply reservation
    is the larger of (a) one symmetric player's half of that capacity and (b)
    the opponent's fully serviced output from public standing animals. Only the
    residual becomes our target. This is a simultaneous-game uncertainty bound,
    not a copied farm shape or behaviour label.
    """
    seeds, _old_animals, buy_land = _proposal_counts(proposed)
    orders = []
    if MM is not None:
        have = snap.me.animal_counts()
        carried = snap.carried()
        for kind, spec in econ.ANIMALS.items():
            if snap.step > econ.ANIMAL_DEADLINE[kind]:
                continue
            fake = {"animal": kind, "placed_day": snap.day}
            events = objective._animal_event_days(
                fake, kind, snap.day, include_start=True
            )
            units = len(events) + max(0, len(events) - 1)
            if units <= 0:
                continue
            if objective.animal_full_service_value(snap, kind) <= spec["cost"]:
                continue
            product = spec["product"]
            productive_days = max(
                0, snap.days_left - int(spec["first_yield_day"]) + 1
            )
            capacity = float(MM.TOWN_DAY.get(product, 0.0)) * productive_days
            opponent = float(_opp_animal_product_units(snap, product))
            reserved = max(0.5 * capacity, opponent)
            target = int(max(0.0, capacity - reserved) // units)
            owned = (int(have.get(kind, 0) or 0)
                     + int(snap.shed.get(kind, 0) or 0)
                     + int(carried.get(kind, 0) or 0))
            short = min(12, max(0, target - owned))
            if short:
                orders.append(["BUY_ANIMAL", kind, short])
    for crop, qty in seeds.items():
        if qty > 0:
            orders.append(["BUY_SEED", crop, int(qty)])
    if buy_land:
        orders.append(["BUY_LAND"])
    return orders


def capital_tasks(snap, proposed, current_tasks, joint_alternatives=False,
                  complete_alternatives=False, positions_by_item=None):
    """Expand proposal quantities into optional engine-valid task columns."""
    seeds, animals, buy_land = _proposal_counts(proposed)
    if animals and not _new_animal_capital_permitted(snap):
        animals = Counter()
    if not seeds and not animals:
        return [], animals

    land_quadrant, land_activation = _land_activation(snap, buy_land)
    unlocked = set(snap.me.unlocked)
    allowed = set(unlocked)
    if land_quadrant is not None:
        allowed.add(land_quadrant)

    used = {tuple(task.pos) for task in current_tasks}
    empty = []
    for y, row in enumerate(snap.me.tiles):
        for x, tile in enumerate(row):
            pos = (x, y)
            if pos in used or not paths.productive_tile_allowed(snap, pos):
                continue
            quadrant = paths.quadrant_of(x, y, snap.board)
            if quadrant not in allowed:
                continue
            if tile is None or (tile == "LOCKED" and quadrant == land_quadrant):
                empty.append(pos)
    empty.sort(key=lambda pos: (paths.dist_to_shed(pos), pos))

    structures = {"PASTURE": [], "COOP": []}
    for y, row in enumerate(snap.me.tiles):
        for x, tile in enumerate(row):
            pos = (x, y)
            if pos in used or not isinstance(tile, dict) or "animal" in tile:
                continue
            if tile.get("kind") in structures:
                structures[tile["kind"]].append(pos)
    for slots in structures.values():
        slots.sort(key=lambda pos: (paths.dist_to_shed(pos), pos))
    animal_empty = [pos for pos in empty
                    if _animal_position_permitted(snap, pos)]
    animal_structures = {
        structure: [pos for pos in slots
                    if _animal_position_permitted(snap, pos)]
        for structure, slots in structures.items()
    }

    columns = []
    if positions_by_item is not None:
        # V77 carries the certificate's exact physical assignment into the
        # route master.  These are columns, not reservations: routing may trim
        # them, after which the retained item/position pairs are recertified.
        for kind in sorted(animals):
            spec = econ.ANIMALS.get(kind)
            if spec is None:
                continue
            for pos in positions_by_item.get(kind, ()):
                pos = tuple(pos)
                if (pos in used
                        or not paths.productive_tile_allowed(snap, pos)
                        or not _animal_position_permitted(snap, pos)):
                    continue
                raw = snap.me.tiles[pos[1]][pos[0]]
                activation = {}
                if isinstance(raw, dict) and raw.get("kind") == spec["structure"]:
                    ops = [["PLACE", kind]]
                elif raw is None or raw == "LOCKED":
                    build = ("BUILD_PASTURE" if spec["structure"] == "PASTURE"
                             else "BUILD_COOP")
                    ops = [[build], ["PLACE", kind]]
                    if paths.quadrant_of(*pos, snap.board) not in unlocked:
                        activation = land_activation
                else:
                    continue
                cost = float(spec["cost"])
                columns.append(Task(
                    pos, ops, {kind: 1},
                    objective.animal_placement_value(snap, kind) - cost,
                    False, "CAPITAL_ANIMAL", cash_cost=cost,
                    order_key=("BUY_ANIMAL", kind), activations=activation,
                    exclusive_key=("CAPITAL_TILE", pos),
                ))
        for crop in sorted(seeds):
            if crop not in econ.CROPS:
                continue
            for pos in positions_by_item.get(crop, ()):
                pos = tuple(pos)
                if (pos in used
                        or not paths.productive_tile_allowed(snap, pos)):
                    continue
                raw = snap.me.tiles[pos[1]][pos[0]]
                if raw is not None and raw != "LOCKED":
                    continue
                activation = (land_activation
                              if paths.quadrant_of(*pos, snap.board) not in unlocked
                              else {})
                cost = float(econ.CROPS[crop]["seed"])
                columns.append(Task(
                    pos, [["PLANT", crop], ["WATER"]], {},
                    objective.plant_value(snap, crop) - cost,
                    False, "CAPITAL_CROP", cash_cost=cost,
                    order_key=("BUY_SEED", crop), activations=activation,
                    exclusive_key=("CAPITAL_TILE", pos),
                ))
        return columns, animals

    if complete_alternatives:
        # A complete but bounded shared-slot column set. Every asset can use
        # every one of the closest slots that the whole proposal could fill;
        # per-order selection limits in the master retain the proposed quantity.
        # This fixes the truncated-alternative defect in V50: after MELON won a
        # close tile, COW could move to the next tile instead of disappearing.
        slot_cap = min(len(empty), sum(seeds.values()) + sum(animals.values()))
        shared_empty = empty[:slot_cap]
        for kind in sorted(animals):
            spec = econ.ANIMALS.get(kind)
            if spec is None or animals[kind] <= 0:
                continue
            compatible = (list(animal_structures[spec["structure"]])
                          + [pos for pos in shared_empty
                             if _animal_position_permitted(snap, pos)])
            for pos in compatible:
                activation = {}
                raw = snap.me.tiles[pos[1]][pos[0]]
                if isinstance(raw, dict) and raw.get("kind") == spec["structure"]:
                    ops = [["PLACE", kind]]
                else:
                    build = ("BUILD_PASTURE" if spec["structure"] == "PASTURE"
                             else "BUILD_COOP")
                    ops = [[build], ["PLACE", kind]]
                    if paths.quadrant_of(*pos, snap.board) not in unlocked:
                        activation = land_activation
                gross = objective.animal_placement_value(snap, kind)
                cost = float(spec["cost"])
                columns.append(Task(
                    pos, ops, {kind: 1}, gross - cost, False,
                    "CAPITAL_ANIMAL", cash_cost=cost,
                    order_key=("BUY_ANIMAL", kind), activations=activation,
                    exclusive_key=("CAPITAL_TILE", pos),
                ))
        for crop in seeds:
            if crop not in econ.CROPS or seeds[crop] <= 0:
                continue
            for pos in shared_empty:
                activation = (land_activation
                              if paths.quadrant_of(*pos, snap.board) not in unlocked
                              else {})
                cost = float(econ.CROPS[crop]["seed"])
                gross = objective.plant_value(snap, crop)
                columns.append(Task(
                    pos, [["PLANT", crop], ["WATER"]], {}, gross - cost,
                    False, "CAPITAL_CROP", cash_cost=cost,
                    order_key=("BUY_SEED", crop), activations=activation,
                    exclusive_key=("CAPITAL_TILE", pos),
                ))
        return columns, animals

    if joint_alternatives:
        # Each type receives the same closest feasible positions as
        # alternatives. `exclusive_key` lets the route master choose at most
        # one mutation per tile, so rejected animal columns no longer reserve
        # land that a selected crop column could have used (and vice versa).
        for kind in sorted(animals):
            spec = econ.ANIMALS.get(kind)
            if spec is None:
                continue
            n = int(animals[kind])
            compatible = list(animal_structures[spec["structure"]][:n])
            compatible += animal_empty[:max(0, n - len(compatible))]
            for pos in compatible:
                activation = {}
                raw = snap.me.tiles[pos[1]][pos[0]]
                if isinstance(raw, dict) and raw.get("kind") == spec["structure"]:
                    ops = [["PLACE", kind]]
                else:
                    build = ("BUILD_PASTURE" if spec["structure"] == "PASTURE"
                             else "BUILD_COOP")
                    ops = [[build], ["PLACE", kind]]
                    if paths.quadrant_of(*pos, snap.board) not in unlocked:
                        activation = land_activation
                gross = objective.animal_full_service_value(snap, kind)
                cost = float(spec["cost"])
                columns.append(Task(
                    pos, ops, {kind: 1}, gross - cost, False,
                    "CAPITAL_ANIMAL", cash_cost=cost,
                    order_key=("BUY_ANIMAL", kind), activations=activation,
                    exclusive_key=("CAPITAL_TILE", pos),
                ))

        for crop in seeds:
            if crop not in econ.CROPS:
                continue
            for pos in empty[:int(seeds[crop])]:
                activation = (land_activation
                              if paths.quadrant_of(*pos, snap.board) not in unlocked
                              else {})
                cost = float(econ.CROPS[crop]["seed"])
                gross = objective.plant_value(snap, crop)
                columns.append(Task(
                    pos, [["PLANT", crop], ["WATER"]], {}, gross - cost,
                    False, "CAPITAL_CROP", cash_cost=cost,
                    order_key=("BUY_SEED", crop), activations=activation,
                    exclusive_key=("CAPITAL_TILE", pos),
                ))
        return columns, animals

    for kind in sorted(animals, key=lambda k: econ.ANIMALS[k]["cost"]):
        spec = econ.ANIMALS.get(kind)
        if spec is None:
            continue
        for _ in range(animals[kind]):
            activation = {}
            if animal_structures[spec["structure"]]:
                pos = animal_structures[spec["structure"]].pop(0)
                ops = [["PLACE", kind]]
            elif animal_empty:
                pos = animal_empty.pop(0)
                if pos in empty:
                    empty.remove(pos)
                build = ("BUILD_PASTURE" if spec["structure"] == "PASTURE"
                         else "BUILD_COOP")
                ops = [[build], ["PLACE", kind]]
                if paths.quadrant_of(*pos, snap.board) not in unlocked:
                    activation = land_activation
            else:
                break
            gross = objective.animal_placement_value(snap, kind)
            cost = float(spec["cost"])
            columns.append(Task(
                pos, ops, {kind: 1}, gross - cost, False,
                "CAPITAL_ANIMAL", cash_cost=cost,
                order_key=("BUY_ANIMAL", kind), activations=activation,
            ))

    for crop in seeds:
        if crop not in econ.CROPS:
            continue
        for _ in range(seeds[crop]):
            if not empty:
                break
            pos = empty.pop(0)
            activation = (land_activation
                          if paths.quadrant_of(*pos, snap.board) not in unlocked
                          else {})
            cost = float(econ.CROPS[crop]["seed"])
            gross = objective.plant_value(snap, crop)
            columns.append(Task(
                pos, [["PLANT", crop], ["WATER"]], {}, gross - cost, False,
                "CAPITAL_CROP", cash_cost=cost,
                order_key=("BUY_SEED", crop), activations=activation,
            ))
    return columns, animals


def _post_action_position(snap, position, action):
    """Exact public position after the already-committed unit phase."""
    pos = tuple(position)
    if not action or action[0] not in paths.MOVES:
        return pos
    dx, dy = paths.MOVES[action[0]]
    nxt = (pos[0] + dx, pos[1] + dy)
    board = max(1, int(getattr(snap, "board", 10) or 10))
    return nxt if 0 <= nxt[0] < board and 0 <= nxt[1] < board else pos


def _idle_unit_phase(unit_actions):
    """Whether the committed unit phase provably leaves public/private state."""
    actions = list(unit_actions or ())
    return bool(actions) and all(action and action[0] == "PASS"
                                 for action in actions)


def _units(snap, new_hands, unit_actions, post_action=False,
           already_projected=False):
    positions = [tuple(snap.me.farmer)]
    positions.extend(tuple(pos) for pos in snap.me.hands)
    actions = list(unit_actions or ())
    start_hour = int(snap.hour) + 1 if post_action else int(snap.hour)
    units = []
    for idx, pos in enumerate(positions):
        if post_action and not already_projected:
            action = actions[idx] if idx < len(actions) else ["PASS"]
            pos = _post_action_position(snap, pos, action)
        units.append(Unit(idx, pos, start_hour))
    first_new = len(units)
    spawn_actions = None if already_projected else unit_actions
    for j, pos in enumerate(hiring.spawn_positions(
            snap, new_hands, spawn_actions)):
        units.append(Unit(first_new + j, pos, snap.hour + 1))
    return units


def _selected(assignment):
    seen, out = set(), []
    for tasks in assignment.values():
        for task in tasks:
            if id(task) in seen:
                continue
            seen.add(id(task))
            out.append(task)
    return out


def _task_asset_item(task):
    for op in task.ops or ():
        if op and op[0] in ("PLANT", "PLACE") and len(op) >= 2:
            return str(op[1])
    return None


def _is_empty_capital_state(snap):
    carried = snap.carried()
    return bool(
        not snap.me.animals and not snap.me.crops
        and not any(int(snap.seeds.get(item, 0) or 0) > 0
                    for item in econ.CROPS)
        and not any(int(snap.shed.get(item, 0) or 0) > 0
                    for item in econ.ANIMALS)
        and not any(int(carried.get(item, 0) or 0) > 0
                    for item in econ.ANIMALS)
    )


def _projected_execution_counts(snap, proposed, fixed, new_hands,
                                bank_outputs=False, source_plan=None):
    """Exact next-observation task/route capacity for one purchase arm.

    The capital master historically routed positioned capital columns with a
    certificate objective, while the next observation rebuilt scan-order live
    tasks and routed them with ``TaskBundleObjective``. This projects our own
    deterministic HIRE/BUY effects, then calls that exact live task and route
    path. Returned counts are newly purchased item tasks the emitted executor
    can actually finish today; pre-existing private inventory is subtracted.
    """
    from whitebox import strategy as _strategy, tasks as _task_planner

    virtual = copy.deepcopy(snap)
    virtual.step = int(snap.step) + 1
    virtual.hour = int(snap.hour) + 1
    virtual.day = int(snap.day)
    spawns = hiring.spawn_positions(snap, int(new_hands), None)
    virtual.me.hands.extend(tuple(pos) for pos in spawns)
    virtual.inventories.extend({} for _ in spawns)

    prior_seed = {
        crop: max(0, int(snap.seeds.get(crop, 0) or 0))
        for crop in econ.CROPS
    }
    prior_animals = {
        kind: max(0, int(snap.shed.get(kind, 0) or 0))
        for kind in econ.ANIMALS
    }
    for order in list(fixed or ()) + list(proposed or ()):
        if not order:
            continue
        if len(order) >= 3 and order[0] == "BUY_PRODUCT":
            item, qty = str(order[1]), max(0, int(order[2] or 0))
            virtual.shed[item] = int(virtual.shed.get(item, 0) or 0) + qty
        elif len(order) >= 3 and order[0] == "BUY_SEED":
            item, qty = str(order[1]), max(0, int(order[2] or 0))
            virtual.seeds[item] = int(virtual.seeds.get(item, 0) or 0) + qty
        elif len(order) >= 3 and order[0] == "BUY_ANIMAL":
            item, qty = str(order[1]), max(0, int(order[2] or 0))
            virtual.shed[item] = int(virtual.shed.get(item, 0) or 0) + qty
        elif order[0] == "BUY_LAND":
            owned_extra = len(virtual.me.unlocked) - 1
            if not econ.can_buy_land(len(virtual.me.unlocked)):
                continue
            quadrant = econ.LAND_ORDER[owned_extra]
            virtual.me.unlocked.append(quadrant)
            for y, row in enumerate(virtual.me.tiles):
                for x, tile in enumerate(row):
                    if (tile == "LOCKED"
                            and paths.quadrant_of(x, y, virtual.board)
                            == quadrant):
                        row[x] = None
                        virtual.me.empty.append((x, y))

    live_plan = _strategy.decide(
        virtual, _strategy.DEFAULT_PORTFOLIO,
        "crew_conditioned_inventory_execution",
    )
    live_plan.execution_variant = "manifest_routes"
    live_plan.paid_weed_turnover = bool(getattr(
        source_plan, "paid_weed_turnover", False,
    ))
    live_plan.survival_feed_hard_core = bool(getattr(
        source_plan, "survival_feed_hard_core", False,
    ))
    previous_plan = _task_planner._last_plan[0]
    try:
        _task_planner._last_plan[0] = live_plan
        live_tasks = _task_planner.enumerate_tasks(virtual, live_plan)
    finally:
        _task_planner._last_plan[0] = previous_plan

    units = [Unit(0, tuple(virtual.me.farmer), virtual.hour)]
    units.extend(Unit(i + 1, tuple(pos), virtual.hour)
                 for i, pos in enumerate(virtual.me.hands))
    assignment, _left = router.joint_assign(
        live_tasks, units, objective.planned_shed_stock(virtual, live_plan),
        deadline=None, refine=False, bank_outputs=bank_outputs,
        bundle_model=objective.TaskBundleObjective(virtual, live_tasks),
        memoize_route_cost=True,
    )
    scheduled = Counter(
        item for item in (_task_asset_item(task)
                          for task in _selected(assignment))
        if item is not None
    )
    proposed_seeds, proposed_animals, _buy_land = _proposal_counts(proposed)
    return {
        **{
            crop: min(int(qty), max(
                0, int(scheduled.get(crop, 0)) - prior_seed[crop],
            ))
            for crop, qty in proposed_seeds.items()
        },
        **{
            kind: min(int(qty), max(
                0, int(scheduled.get(kind, 0)) - prior_animals[kind],
            ))
            for kind, qty in proposed_animals.items()
        },
    }


def _activation_cost(selected):
    """Objective cost of shared fixed-capital prerequisites.

    ``router._capital_usage`` already charges these activations to the cash
    constraint exactly once. They must also be charged exactly once to the
    objective. Otherwise a quadrant is treated as economically free whenever
    it is affordable, so positive crop columns can hide a negative land bundle.
    """
    activations = {}
    for task in selected:
        for key, cost in task.activations.items():
            activations[key] = max(float(cost), activations.get(key, 0.0))
    return sum(activations.values())


def _robust_tail_repair(snap, row):
    """Exact one-direction robust quantity repair of a winning crew row.

    The bounded portfolio constructor emits ordered item rays. After the
    execution-aligned crew solve, only the final retained direction is varied;
    all earlier composition and the chosen crew stay fixed. Every integer
    quantity is evaluated by the unified finite Stackelberg certificate. This
    catches a saturated tail unit whose own cash is positive but whose exact
    shared-market margin is negative, without reopening the rejected global
    V116 search inside every route marginal.
    """
    assets = [list(order) for order in row.get("assets", ())]
    tail_index = next((
        idx for idx in range(len(assets) - 1, -1, -1)
        if len(assets[idx]) >= 3
        and assets[idx][0] in ("BUY_SEED", "BUY_ANIMAL")
        and int(assets[idx][2] or 0) > 0
    ), None)
    if tail_index is None:
        return row
    tail_item = str(assets[tail_index][1])
    positioned = {
        str(item): [tuple(pos) for pos in positions]
        for item, positions in row.get("positions_by_item", {}).items()
    }
    tail_positions = positioned.get(tail_item, [])
    maximum = min(int(assets[tail_index][2]), len(tail_positions))
    if maximum <= 0:
        return row

    from whitebox import stackelberg as _stackelberg
    context = _stackelberg.make_context(snap)
    land_cost = 0.0
    if any(order and order[0] == "BUY_LAND" for order in assets):
        owned_extra = len(snap.me.unlocked) - 1
        if econ.can_buy_land(len(snap.me.unlocked)):
            land_cost = float(econ.LAND_PRICES[owned_extra])
    candidates = []
    for quantity in range(maximum + 1):
        trial_positions = {
            item: (positions[:quantity]
                   if item == tail_item else list(positions))
            for item, positions in positioned.items()
        }
        trial_positions = {
            item: positions for item, positions in trial_positions.items()
            if positions
        }
        counts = {item: len(positions)
                  for item, positions in trial_positions.items()}
        slots = sorted(
            {pos for positions in trial_positions.values()
             for pos in positions},
            key=lambda pos: (paths.dist_to_shed(pos), pos),
        )
        cert = _stackelberg.certify_unified(
            snap, counts, slots,
            reserve=float(row.get("service_reserve", 0.0))
                    + float(row.get("hire_cost", 0.0)),
            land_cost=land_cost,
            fixed_orders=row.get("fixed", ()),
            positions_by_item=trial_positions,
            context=context,
        )
        if cert.feasible:
            candidates.append((
                (float(cert.paired_value), float(cert.final_cash),
                 -float(cert.upfront_spend), -quantity),
                quantity, cert, trial_positions,
            ))
    if not candidates:
        return row
    _key, quantity, cert, trial_positions = max(candidates, key=lambda x: x[0])
    repaired = dict(row)
    if quantity > 0:
        assets[tail_index][2] = int(quantity)
    else:
        assets.pop(tail_index)
    repaired["assets"] = assets
    repaired["positions_by_item"] = {
        item: tuple(positions) for item, positions in trial_positions.items()
    }
    selected_counts = dict(repaired.get("selected_counts", {}))
    if quantity > 0:
        selected_counts[tail_item] = int(quantity)
    else:
        selected_counts.pop(tail_item, None)
    repaired["selected_counts"] = selected_counts
    repaired["completed_tasks"] = sum(selected_counts.values())
    repaired["score"] = (float(cert.paired_value)
                         - float(row.get("hire_cost", 0.0)))
    repaired["robust_tail_item"] = tail_item
    repaired["robust_tail_quantity"] = int(quantity)
    repaired["robust_tail_value"] = float(cert.paired_value)
    return repaired


def _asset_product(item):
    """Public sale book reached by one productive capital item."""
    if item in econ.CROPS:
        return str(item)
    spec = econ.ANIMALS.get(item)
    return None if spec is None else str(spec["product"])


def _public_opponent_product_units(snap):
    """Auditable remaining public opponent units, separated by sale book."""
    from whitebox import cashflow as _cashflow

    units = Counter()
    for products in _cashflow._visible_output_schedule(
            snap, snap.opp).values():
        for product, quantity in products.items():
            units[str(product)] += max(0, int(quantity or 0))
    return dict(units)


def _replacement_position_legal(snap, item, pos, activates_land=False):
    """Whether ``item`` can legally inherit one selected physical slot."""
    pos = tuple(pos)
    x, y = pos
    raw = snap.me.tiles[y][x]
    quadrant = paths.quadrant_of(x, y, snap.board)
    accessible = quadrant in set(snap.me.unlocked)
    if raw == "LOCKED":
        accessible = accessible or bool(activates_land)
    if not accessible:
        return False
    if item in econ.CROPS:
        return raw is None or raw == "LOCKED"
    spec = econ.ANIMALS.get(item)
    if spec is None:
        return False
    if raw is None or raw == "LOCKED":
        return True
    return (isinstance(raw, dict)
            and raw.get("kind") == spec["structure"]
            and "animal" not in raw)


def _positioned_assets(assets, positions_by_item):
    """Rebuild purchase quantities while retaining the proposal's order."""
    counts = Counter({
        str(item): len(positions)
        for item, positions in positions_by_item.items() if positions
    })
    out, emitted = [], set()
    for order in assets:
        if not order:
            continue
        if order[0] == "BUY_LAND":
            out.append(["BUY_LAND"])
            continue
        if len(order) < 2:
            continue
        item = str(order[1])
        if item in counts and item not in emitted:
            op = "BUY_SEED" if item in econ.CROPS else "BUY_ANIMAL"
            out.append([op, item, int(counts[item])])
            emitted.add(item)
    for item in sorted(set(counts) - emitted):
        op = "BUY_SEED" if item in econ.CROPS else "BUY_ANIMAL"
        out.append([op, item, int(counts[item])])
    return out


def _cash_prefix_dominates(candidate, baseline):
    """True when no dated cash opportunity feasible before is lost."""
    if float(candidate.upfront_spend) > float(baseline.upfront_spend) + 1e-9:
        return False
    days = sorted(set(candidate.cash_by_day) | set(baseline.cash_by_day))

    def at(cert, day):
        eligible = [d for d in cert.cash_by_day if int(d) <= int(day)]
        if eligible:
            return float(cert.cash_by_day[max(eligible)])
        if cert.cash_path:
            return float(cert.cash_path[0])
        return float("-inf")

    return all(at(candidate, day) + 1e-9 >= at(baseline, day)
               for day in days)


def _response_vector_dominates(snap, candidate, baseline, context):
    """Require non-worse margin in every named paid response scenario."""
    from whitebox import stackelberg as _stackelberg

    candidate_cost = (float(candidate.upfront_spend)
                      + float(candidate.operating_cost))
    baseline_cost = (float(baseline.upfront_spend)
                     + float(baseline.operating_cost))
    opponent_baseline = context.get("opponent_baseline", {})
    drains = context.get("drains")
    for response in context.get("responses", ()):
        candidate_margin = _stackelberg._context_response_margin(
            snap, candidate.outputs_by_day, candidate_cost, response,
            context,
        )
        baseline_margin = _stackelberg._context_response_margin(
            snap, baseline.outputs_by_day, baseline_cost, response,
            context,
        )
        if candidate_margin + 1e-9 < baseline_margin:
            return False
    return True


def _robust_composition_exchange(snap, row,
                                 preserve_cash_prefix=False,
                                 all_reinvestment_anchors=False,
                                 full_opponent_continuation=False,
                                 mixed_opponent_continuation=False,
                                 preserve_response_scenarios=False,
                                 allow_idle=False,
                                 own_full_service_continuation=False,
                                 rotation_reinvestment=False,
                                 own_service_fertilizer_credit=True,
                                 own_service_fertilizer_value=True,
                                 land_reinvestment_option=False,
                                 include_own_standing_book=False,
                                 same_asset_class_only=False,
                                 disallow_animal_to_crop_exchange=False,
                                 allow_animal_idle=False,
                                 source_asset_class=None,
                                 same_structure_only=False,
                                 candidate_response_products=(),
                                 source_quadrants=(),
                                 target_asset_class=None,
                                 stackelberg_context=None,
                                 close_infeasible_capital=False,
                                 expose_infeasible_certificate=False,
                                 staged_opponent_reinvestment=False,
                                 staged_response_cache=None,
                                 robust_own_standing_realisation=False,
                                 staged_opponent_land_reinvestment=False,
                                 staged_opponent_mixed_reinvestment=False,
                                 max_exchange_quantity=None):
    """Hold crew fixed and improve one transparent composition ray.

    Every legal one-unit ``source -> target`` exchange is evaluated with the
    same finite Stackelberg certificate.  The best strictly improving
    direction is then enumerated over all compatible source quantities.  When
    ``allow_idle`` is true, removing an asset and leaving its public tile idle
    is one more named target. Chosen crew, activated quadrant and fixed orders
    never change; coverage has no objective reward and may fall only when the
    resulting certificate has strictly greater robust economic value.
    seed/animal cost, positioned labour, product-specific shared books and
    paid public opponent responses are all recomputed for each candidate.

    This is intentionally a bounded coordinate solve, not a fitted portfolio:
    candidates come only from engine asset tables and biological deadlines.
    """
    assets = [list(order) for order in row.get("assets", ())]
    positioned = {
        str(item): [tuple(pos) for pos in positions]
        for item, positions in row.get("positions_by_item", {}).items()
        if positions
    }
    coverage = sum(len(positions) for positions in positioned.values())
    if coverage <= 0:
        return row

    legal_items = [
        item for item in sorted(tuple(econ.CROPS) + tuple(econ.ANIMALS))
        if int(snap.step) <= int(
            econ.SEED_DEADLINE[item] if item in econ.CROPS
            else econ.ANIMAL_DEADLINE[item]
        )
    ]
    if target_asset_class == "CROP":
        legal_items = [item for item in legal_items if item in econ.CROPS]
    elif target_asset_class == "ANIMAL":
        legal_items = [item for item in legal_items if item in econ.ANIMALS]
    if (len(legal_items) <= 1 and not allow_idle
            and not allow_animal_idle):
        return row

    from whitebox import stackelberg as _stackelberg

    context = (
        stackelberg_context if stackelberg_context is not None else
        _stackelberg.make_context(
            snap, full_response_continuation=full_opponent_continuation,
            mixed_response_continuation=mixed_opponent_continuation,
            include_own_standing_book=include_own_standing_book,
            candidate_response_products=candidate_response_products,
            staged_response_reinvestment=staged_opponent_reinvestment,
            staged_response_cache=staged_response_cache,
            robust_own_standing_realisation=(
                robust_own_standing_realisation
            ),
            staged_response_land_reinvestment=(
                staged_opponent_land_reinvestment
            ),
            staged_response_mixed_reinvestment=(
                staged_opponent_mixed_reinvestment
            ),
        )
    )
    reserve = (float(row.get("service_reserve", 0.0))
               + float(row.get("hire_cost", 0.0)))
    activates_land = any(order and order[0] == "BUY_LAND"
                         for order in assets)
    land_cost = 0.0
    if activates_land:
        owned_extra = len(snap.me.unlocked) - 1
        if econ.can_buy_land(len(snap.me.unlocked)):
            land_cost = float(econ.LAND_PRICES[owned_extra])
    slots = sorted(
        {pos for positions in positioned.values() for pos in positions},
        key=lambda pos: (paths.dist_to_shed(pos), pos),
    )

    def certify(candidate, expanded_reinvestment=False):
        counts = {item: len(positions)
                  for item, positions in candidate.items() if positions}
        return _stackelberg.certify_unified(
            snap, counts, slots, reserve=reserve, land_cost=land_cost,
            fixed_orders=row.get("fixed", ()), positions_by_item=candidate,
            context=context,
            land_reinvestment=(expanded_reinvestment
                               or land_reinvestment_option),
            all_reinvestment_anchors=expanded_reinvestment,
            full_service_continuation=own_full_service_continuation,
            rotation_reinvestment=rotation_reinvestment,
            service_fertilizer_credit=own_service_fertilizer_credit,
            service_fertilizer_value=own_service_fertilizer_value,
        )

    baseline_cash = certify(positioned)
    if not baseline_cash.feasible:
        if expose_infeasible_certificate:
            audited = dict(row)
            audited["composition_certificate_feasible"] = False
            audited["composition_certificate_reason"] = str(
                baseline_cash.reason
            )
            # The context is the exact finite paid-response set already used
            # by the failed V149 evaluation.  Reusing it changes no belief or
            # value term and avoids a second response solve/cache perturbation.
            audited["composition_certificate_context"] = context
            row = audited
        if not close_infeasible_capital:
            return row

        # A hard certificate failure cannot be treated as a neutral economic
        # comparison and then executed unchanged.  Enumerate every deterministic
        # one-product deletion ray, removing its farthest positions first
        # because that weakly reduces the public route burden.  The explicit
        # no-purchase action closes the set even when the already-standing farm
        # itself cannot be promised full survival.  This is a feasibility
        # fallback, not a target scale: only engine-valid subsets survive.
        feasible_subsets = []
        for source in sorted(positioned):
            removable = sorted(
                positioned[source],
                key=lambda pos: (paths.dist_to_shed(pos), pos),
                reverse=True,
            )
            for quantity in range(1, len(removable) + 1):
                trial = {
                    item: list(positions)
                    for item, positions in positioned.items()
                }
                for pos in removable[:quantity]:
                    trial[source].remove(pos)
                if not trial[source]:
                    del trial[source]
                trial_slots = sorted(
                    {tuple(pos) for positions in trial.values()
                     for pos in positions},
                    key=lambda pos: (paths.dist_to_shed(pos), pos),
                )
                counts = {
                    item: len(positions)
                    for item, positions in trial.items() if positions
                }
                cert = _stackelberg.certify_unified(
                    snap, counts, trial_slots, reserve=reserve,
                    land_cost=land_cost,
                    fixed_orders=row.get("fixed", ()),
                    positions_by_item=trial, context=context,
                    land_reinvestment=land_reinvestment_option,
                    full_service_continuation=(
                        own_full_service_continuation
                    ),
                    rotation_reinvestment=rotation_reinvestment,
                    service_fertilizer_credit=(
                        own_service_fertilizer_credit
                    ),
                    service_fertilizer_value=own_service_fertilizer_value,
                )
                if cert.feasible:
                    feasible_subsets.append((
                        (float(cert.paired_value), float(cert.final_cash),
                         -float(cert.upfront_spend),
                         sum(len(v) for v in trial.values()), source,
                         -quantity),
                        cert, trial,
                    ))

        audited = dict(row)
        audited["capital_feasibility_closed"] = True
        audited["capital_infeasible_reason"] = str(baseline_cash.reason)
        audited["capital_infeasible_before_counts"] = {
            item: len(positions)
            for item, positions in sorted(positioned.items())
        }
        empty_key = (0.0, float(snap.me.money), 0.0, 0, "", 0)
        if feasible_subsets:
            best_key, repaired_cert, repaired_positions = max(
                feasible_subsets, key=lambda arm: arm[0],
            )
        else:
            best_key, repaired_cert, repaired_positions = (
                empty_key, None, {},
            )
        # IDLE/no purchase is an explicit zero-increment alternative.  A
        # feasible subset with negative robust value may not defeat it merely
        # because it was certifiable.
        if best_key[0] <= empty_key[0] + 1e-9:
            repaired_cert, repaired_positions = None, {}

        repaired = dict(audited)
        repaired_assets = _positioned_assets(assets, repaired_positions)
        if any(order and order[0] == "BUY_LAND"
               for order in repaired_assets):
            current_quadrants = set(snap.me.unlocked)
            activates = any(
                paths.quadrant_of(pos[0], pos[1], snap.board)
                not in current_quadrants
                for positions in repaired_positions.values()
                for pos in positions
            )
            if not activates:
                repaired_assets = [
                    order for order in repaired_assets
                    if not order or order[0] != "BUY_LAND"
                ]
        repaired["assets"] = repaired_assets
        repaired["positions_by_item"] = {
            item: tuple(positions)
            for item, positions in sorted(repaired_positions.items())
            if positions
        }
        repaired["selected_counts"] = {
            item: len(positions)
            for item, positions in repaired["positions_by_item"].items()
        }
        repaired["capital_cash"] = sum(
            _committed_asset_cost(order)
            for order in repaired_assets
            if order and order[0] != "BUY_LAND"
        ) + sum(
            float(econ.LAND_PRICES[len(snap.me.unlocked) - 1])
            for order in repaired_assets
            if order and order[0] == "BUY_LAND"
            and 0 <= len(snap.me.unlocked) - 1 < len(econ.LAND_PRICES)
        )
        repaired["order_keys"] = len(repaired_assets)
        ordinary = list(row.get("selected_ordinary_tasks", ()))
        ordinary_value = float(
            objective.TaskBundleObjective(snap, ordinary).score(ordinary)
        )
        robust_value = (float(repaired_cert.paired_value)
                        if repaired_cert is not None else 0.0)
        repaired["score"] = (
            ordinary_value + robust_value
            - float(row.get("hire_cost", 0.0))
        )
        repaired["capital_feasibility_after_counts"] = dict(
            repaired["selected_counts"]
        )
        repaired["capital_feasibility_after_value"] = robust_value
        repaired["composition_exchange_quantity"] = 0
        return repaired

    # The certificate's item-position order is retained.  It is part of the
    # route proof, so the first compatible slot is a named, reproducible ray
    # rather than an unobserved spatial weight.
    one_unit = []
    source_quadrants = frozenset(str(q) for q in source_quadrants)
    for source in sorted(positioned):
        if (source_asset_class == "ANIMAL"
                and source not in econ.ANIMALS):
            continue
        if (source_asset_class == "CROP"
                and source not in econ.CROPS):
            continue
        source_positions = [
            tuple(pos) for pos in positioned[source]
            if (not source_quadrants
                or paths.quadrant_of(pos[0], pos[1], snap.board)
                in source_quadrants)
        ]
        if not source_positions:
            continue
        targets = [
            target for target in legal_items
            if (not same_asset_class_only
                or ((source in econ.ANIMALS)
                    == (target in econ.ANIMALS)))
            if (not same_structure_only
                or source not in econ.ANIMALS
                or target not in econ.ANIMALS
                or econ.ANIMALS[source]["structure"]
                == econ.ANIMALS[target]["structure"])
        ] + ([None] if (allow_idle
                        or (allow_animal_idle
                            and source in econ.ANIMALS)) else [])
        for target in targets:
            if target == source:
                continue
            if (disallow_animal_to_crop_exchange
                    and source in econ.ANIMALS
                    and target in econ.CROPS):
                continue
            compatible = (
                list(source_positions) if target is None else [
                    pos for pos in source_positions
                    if _replacement_position_legal(
                        snap, target, pos, activates_land=activates_land,
                    )
                ]
            )
            if not compatible:
                continue
            pos = compatible[0]
            trial = {item: list(positions)
                     for item, positions in positioned.items()}
            trial[source].remove(pos)
            if not trial[source]:
                del trial[source]
            if target is not None:
                trial.setdefault(target, []).append(pos)
            cash_cert = certify(trial)
            if not cash_cert.feasible:
                continue
            if (preserve_cash_prefix
                    and not _cash_prefix_dominates(
                        cash_cert, baseline_cash,
                    )):
                continue
            if (preserve_response_scenarios
                    and not _response_vector_dominates(
                        snap, cash_cert, baseline_cash, context,
                    )):
                continue
            target_name = "IDLE" if target is None else str(target)
            one_unit.append((source, target, target_name, compatible, trial,
                             cash_cert))

    if all_reinvestment_anchors and one_unit:
        baseline = certify(positioned, expanded_reinvestment=True)
        if not baseline.feasible:
            return row
        valued = []
        for (source, target, target_name, compatible, trial,
             _cash_cert) in one_unit:
            cert = certify(trial, expanded_reinvestment=True)
            if not cert.feasible:
                continue
            key = (
                float(cert.paired_value), float(cert.final_cash),
                -float(cert.upfront_spend), source, target_name,
            )
            valued.append((key, source, target, target_name, compatible))
        one_unit = valued
    else:
        baseline = baseline_cash
        one_unit = [
            ((float(cert.paired_value), float(cert.final_cash),
              -float(cert.upfront_spend), source, target_name),
             source, target, target_name, compatible)
            for (source, target, target_name, compatible, _trial,
                 cert) in one_unit
        ]

    audited = dict(row)
    audited["composition_coverage"] = int(coverage)
    audited["composition_before_value"] = float(baseline.paired_value)
    audited["composition_opponent_units"] = (
        _public_opponent_product_units(snap)
    )
    audited["composition_books"] = {
        item: _asset_product(item) for item in sorted(positioned)
    }
    if not one_unit:
        audited["composition_exchange_quantity"] = 0
        return audited

    best_one = max(one_unit, key=lambda candidate: candidate[0])
    if best_one[0][0] <= float(baseline.paired_value) + 1e-9:
        audited["composition_exchange_quantity"] = 0
        audited["composition_after_value"] = float(baseline.paired_value)
        return audited

    _one_key, source, target, target_name, compatible = best_one
    ray = []
    quantity_limit = len(compatible)
    if max_exchange_quantity is not None:
        quantity_limit = min(
            quantity_limit, max(0, int(max_exchange_quantity)),
        )
    for quantity in range(1, quantity_limit + 1):
        moved = compatible[:quantity]
        trial = {item: list(positions)
                 for item, positions in positioned.items()}
        for pos in moved:
            trial[source].remove(pos)
        if not trial[source]:
            del trial[source]
        if target is not None:
            trial.setdefault(target, []).extend(moved)
        cash_cert = certify(trial)
        if not cash_cert.feasible:
            continue
        if (preserve_cash_prefix
                and not _cash_prefix_dominates(
                    cash_cert, baseline_cash,
                )):
            continue
        if (preserve_response_scenarios
                and not _response_vector_dominates(
                    snap, cash_cert, baseline_cash, context,
                )):
            continue
        cert = (certify(trial, expanded_reinvestment=True)
                if all_reinvestment_anchors else cash_cert)
        if not cert.feasible:
            continue
        key = (
            float(cert.paired_value), float(cert.final_cash),
            -float(cert.upfront_spend), -quantity,
        )
        ray.append((key, quantity, cert, trial))
    if not ray:
        audited["composition_exchange_quantity"] = 0
        return audited

    _key, quantity, cert, best_positions = max(
        ray, key=lambda candidate: candidate[0]
    )
    repaired = dict(audited)
    repaired["assets"] = _positioned_assets(assets, best_positions)
    repaired["positions_by_item"] = {
        item: tuple(positions)
        for item, positions in sorted(best_positions.items()) if positions
    }
    repaired["selected_counts"] = {
        item: len(positions)
        for item, positions in repaired["positions_by_item"].items()
    }
    # Ordinary current tasks retain their original contribution.  Only the
    # robust capital component changes and coverage itself contributes zero.
    repaired["score"] = (
        float(row.get("score", 0.0))
        + float(cert.paired_value) - float(baseline.paired_value)
    )
    repaired["composition_exchange_from"] = source
    repaired["composition_exchange_to"] = target_name
    repaired["composition_exchange_quantity"] = int(quantity)
    repaired["composition_after_value"] = float(cert.paired_value)
    repaired["composition_cash_prefix_preserved"] = bool(
        preserve_cash_prefix
    )
    repaired["composition_all_reinvestment_anchors"] = bool(
        all_reinvestment_anchors
    )
    repaired["composition_books"] = {
        item: _asset_product(item)
        for item in sorted(repaired["positions_by_item"])
    }
    repaired["composition_after_coverage"] = sum(
        repaired["selected_counts"].values()
    )
    if not allow_idle:
        assert repaired["composition_after_coverage"] == coverage
    return repaired


def _saturated_standing_book_gate(
        snap, row, exact_two_kind_frontier=False,
        precertified_infeasibility_only=False):
    """Forbid new capital only when it exhausts standing queue headroom.

    A proposed portfolio's certificate can fail for many reasons, including a
    conservative cash bridge.  Those failures do not justify shutting down an
    early farm.  This gate compares two certificates on the same horizon: the
    public standing farm alone must fit, while standing plus the proposed
    capital must fail specifically on labour/order capacity.  That difference
    is the proposal's marginal queue burden.  No animal count or date enters
    the predicate.
    """
    if (precertified_infeasibility_only
            and row.get("composition_certificate_reason")
            != "no_stackelberg_endpoint"):
        return row

    positioned = {
        str(item): tuple(tuple(pos) for pos in positions)
        for item, positions in row.get("positions_by_item", {}).items()
        if positions
    }
    if not positioned or not any(item in econ.ANIMALS for item in positioned):
        return row

    from whitebox import cashflow as _cashflow
    from whitebox import stackelberg as _stackelberg

    counts = {item: len(positions)
              for item, positions in positioned.items()}
    horizon = _stackelberg._first_output_horizon(
        snap, counts, phase_aligned=True,
    )
    if horizon is None:
        return row
    fixed = row.get("fixed", ())
    cash_context = (
        *_cashflow._fixed_commitment(snap, fixed),
        _cashflow._reserved_book(snap),
    )
    standing = _cashflow.certify_shared(
        snap, {}, (), reserve=0.0, land_cost=0.0,
        fixed_orders=fixed, _context=cash_context,
        paired_objective=False, phase_aligned=True,
        exact_first_output=True,
        visible_survival_horizon=horizon,
        enforce_bridge_cash=False,
    )
    if not standing.feasible:
        return row

    proposal_slots = sorted(
        {tuple(pos) for positions in positioned.values()
         for pos in positions},
        key=lambda pos: (paths.dist_to_shed(pos), pos),
    )
    land_cost = 0.0
    if any(order and order[0] == "BUY_LAND"
           for order in row.get("assets", ())):
        owned_extra = len(snap.me.unlocked) - 1
        if econ.can_buy_land(len(snap.me.unlocked)):
            land_cost = float(econ.LAND_PRICES[owned_extra])
    combined = _cashflow.certify_shared(
        snap, counts, proposal_slots,
        reserve=(float(row.get("service_reserve", 0.0))
                 + float(row.get("hire_cost", 0.0))),
        land_cost=land_cost, fixed_orders=fixed,
        _context=cash_context, positions_by_item=positioned,
        paired_objective=False, phase_aligned=True,
        exact_first_output=True,
        visible_survival_horizon=horizon,
        enforce_bridge_cash=False,
    )
    if combined.feasible or combined.reason not in (
            "daily_labour", "market_order_slots", "staged_hire_horizon"):
        return row

    frontier = []
    evaluations = 0
    if exact_two_kind_frontier and len(positioned) <= 2:
        context = row.get("composition_certificate_context")
        if context is None:
            context = _stackelberg.make_context(
                snap, full_response_continuation=True,
            )
        items = tuple(sorted(positioned))
        ordered = {
            item: tuple(sorted(
                positioned[item],
                key=lambda pos: (paths.dist_to_shed(pos), pos),
            ))
            for item in items
        }
        for quantities in itertools.product(*(
                range(len(ordered[item]) + 1) for item in items)):
            if not any(quantities):
                continue
            trial = {
                item: list(ordered[item][:quantity])
                for item, quantity in zip(items, quantities) if quantity
            }
            trial_slots = sorted(
                {tuple(pos) for positions in trial.values()
                 for pos in positions},
                key=lambda pos: (paths.dist_to_shed(pos), pos),
            )
            trial_land_cost = 0.0
            if land_cost and any(
                    paths.quadrant_of(pos[0], pos[1], snap.board)
                    not in set(snap.me.unlocked)
                    for positions in trial.values() for pos in positions):
                trial_land_cost = land_cost
            trial_counts = {
                item: len(positions)
                for item, positions in trial.items()
            }
            trial_horizon = _stackelberg._first_output_horizon(
                snap, trial_counts, phase_aligned=True,
            )
            if trial_horizon is None:
                continue
            physical = _cashflow.certify_shared(
                snap, trial_counts, trial_slots,
                reserve=(float(row.get("service_reserve", 0.0))
                         + float(row.get("hire_cost", 0.0))),
                land_cost=trial_land_cost, fixed_orders=fixed,
                _context=cash_context, positions_by_item=trial,
                paired_objective=False, phase_aligned=True,
                exact_first_output=True,
                visible_survival_horizon=trial_horizon,
            )
            if not physical.feasible:
                continue
            cert = _stackelberg.certify_unified(
                snap, trial_counts,
                trial_slots,
                reserve=(float(row.get("service_reserve", 0.0))
                         + float(row.get("hire_cost", 0.0))),
                land_cost=trial_land_cost, fixed_orders=fixed,
                positions_by_item=trial, context=context,
            )
            evaluations += 1
            if cert.feasible:
                frontier.append((
                    (float(cert.paired_value), float(cert.final_cash),
                     -float(cert.upfront_spend), sum(quantities),
                     tuple(quantities)),
                    cert, trial,
                ))

    chosen_cert = None
    chosen_positions = {}
    if frontier:
        best_key, best_cert, best_positions = max(
            frontier, key=lambda arm: arm[0],
        )
        if best_key[0] > 0.0:
            chosen_cert = best_cert
            chosen_positions = best_positions

    # IDLE is the only action whose incremental liabilities are certainly
    # zero when the standing book itself has exhausted the shared queue.  The
    # exact two-kind arm may replace it only with a positive robust-value fully
    # certified subset.  Keep today's selected ordinary work and crew.
    closed = dict(row)
    repaired_assets = _positioned_assets(
        row.get("assets", ()), chosen_positions,
    )
    if any(order and order[0] == "BUY_LAND"
           for order in repaired_assets):
        current_quadrants = set(snap.me.unlocked)
        if not any(
                paths.quadrant_of(pos[0], pos[1], snap.board)
                not in current_quadrants
                for positions in chosen_positions.values()
                for pos in positions):
            repaired_assets = [
                order for order in repaired_assets
                if not order or order[0] != "BUY_LAND"
            ]
    closed["assets"] = repaired_assets
    closed["positions_by_item"] = {
        item: tuple(positions)
        for item, positions in sorted(chosen_positions.items())
    }
    closed["selected_counts"] = {
        item: len(positions)
        for item, positions in closed["positions_by_item"].items()
    }
    closed["capital_cash"] = (
        float(chosen_cert.upfront_spend) if chosen_cert is not None else 0.0
    )
    closed["order_keys"] = len(repaired_assets)
    ordinary = list(row.get("selected_ordinary_tasks", ()))
    robust_value = (
        float(chosen_cert.paired_value) if chosen_cert is not None else 0.0
    )
    closed["score"] = (
        float(objective.TaskBundleObjective(
            snap, ordinary,
        ).score(ordinary))
        + robust_value
        - float(row.get("hire_cost", 0.0))
    )
    closed["standing_book_gate"] = True
    closed["standing_book_gate_reason"] = str(combined.reason)
    closed["standing_book_gate_horizon"] = int(horizon)
    closed["standing_book_rejected_counts"] = counts
    closed["standing_book_frontier_exact"] = bool(
        exact_two_kind_frontier and len(positioned) <= 2
    )
    closed["standing_book_frontier_evaluations"] = evaluations
    closed["standing_book_frontier_value"] = robust_value
    closed["standing_book_frontier_counts"] = dict(
        closed["selected_counts"]
    )
    return closed


def _robust_portfolio_descent(snap, row,
                              service_fertilizer_credit=True,
                              stackelberg_context=None,
                              land_reinvestment_option=False):
    """Reach a local robust portfolio optimum by named certificate steps.

    One composition ray cannot cross from a bad capital basin to a portfolio
    requiring several simultaneous substitutions.  This finite descent
    repeatedly invokes the same exact one-ray certificate, permits an asset to
    become an idle tile, and stops on the first round with no strict robust
    improvement.  Its structural work bound is the number of public asset
    kinds: no tape statistic, target count, fitted coefficient, identity or
    wall-clock deadline controls the search.

    Early reinvestment remains inside ``certify_unified`` as an executable
    option funded by certified dated cash.  Lower intermediate cash is thus
    allowed when every reserve/bridge constraint remains feasible and the
    paid-response max-min value rises; cash itself is not treated as utility.
    """
    current = dict(row)
    trace = []
    asset_kinds = tuple(sorted(tuple(econ.CROPS) + tuple(econ.ANIMALS)))
    if stackelberg_context is None:
        from whitebox import stackelberg as _stackelberg
        stackelberg_context = _stackelberg.make_context(
            snap, full_response_continuation=True,
        )
    for round_index in range(len(asset_kinds)):
        candidate = _robust_composition_exchange(
            snap, current,
            preserve_cash_prefix=False,
            all_reinvestment_anchors=False,
            full_opponent_continuation=True,
            mixed_opponent_continuation=False,
            preserve_response_scenarios=False,
            allow_idle=True,
            own_full_service_continuation=True,
            rotation_reinvestment=True,
            own_service_fertilizer_credit=True,
            own_service_fertilizer_value=service_fertilizer_credit,
            land_reinvestment_option=land_reinvestment_option,
            stackelberg_context=stackelberg_context,
        )
        quantity = int(candidate.get("composition_exchange_quantity", 0))
        before = float(candidate.get("composition_before_value", 0.0))
        after = float(candidate.get("composition_after_value", before))
        if quantity <= 0 or after <= before + 1e-9:
            break
        trace.append({
            "round": int(round_index + 1),
            "from": str(candidate["composition_exchange_from"]),
            "to": str(candidate["composition_exchange_to"]),
            "quantity": quantity,
            "before_value": before,
            "after_value": after,
            "coverage": int(candidate.get(
                "composition_after_coverage",
                sum(candidate.get("selected_counts", {}).values()),
            )),
        })
        current = candidate

    audited = dict(current)
    audited["portfolio_descent_trace"] = tuple(trace)
    audited["portfolio_descent_rounds"] = len(trace)
    audited["portfolio_descent_bound"] = len(asset_kinds)
    audited["portfolio_descent_cash_is_constraint"] = True
    audited["portfolio_descent_cash_is_utility"] = False
    audited["portfolio_descent_tape_features"] = ()
    return audited


def _joint_standing_portfolio_gate(snap, row):
    """Revalue V191's executable candidate universe with the standing farm.

    The upstream planner still invents every crew/asset/position row, so this
    gate cannot turn robust valuation into an empty action generator.  It
    first closes an infeasible candidate by a deterministic farthest-position
    deletion ray, then repeatedly chooses the best legal item substitution or
    IDLE quantity under one shared full-service/finite-response context.

    Current ordinary work, paid crew and fixed market orders are invariant.
    Every change must strictly raise the same public max-min margin.  The work
    bound is the number of engine asset kinds; no replay statistic, opponent
    identity, target count, coordinate template or fitted coefficient enters.
    """
    if not (snap.me.animals or snap.me.crops):
        return row
    if not any(row.get("positions_by_item", {}).values()):
        return row

    from whitebox import stackelberg as _stackelberg

    products = tuple(econ.CROPS) + tuple(sorted({
        str(spec["product"]) for spec in econ.ANIMALS.values()
    }))
    context = _stackelberg.make_context(
        snap, full_response_continuation=True,
        include_own_standing_book=True,
        candidate_response_products=products,
    )
    current = dict(row)
    trace = []
    asset_kinds = tuple(sorted(tuple(econ.CROPS) + tuple(econ.ANIMALS)))
    for round_index in range(len(asset_kinds)):
        before_counts = dict(current.get("selected_counts", {}))
        candidate = _robust_composition_exchange(
            snap, current,
            preserve_cash_prefix=False,
            full_opponent_continuation=True,
            preserve_response_scenarios=False,
            allow_idle=True,
            own_full_service_continuation=True,
            include_own_standing_book=True,
            candidate_response_products=products,
            stackelberg_context=context,
            close_infeasible_capital=(round_index == 0),
        )
        after_counts = dict(candidate.get("selected_counts", {}))
        changed = after_counts != before_counts
        if not changed:
            current = candidate
            break
        trace.append({
            "round": int(round_index + 1),
            "before": before_counts,
            "after": after_counts,
            "reason": str(candidate.get(
                "capital_infeasible_reason", "strict_margin_improvement",
            )),
            "robust_value": float(candidate.get(
                "composition_after_value",
                candidate.get("capital_feasibility_after_value", 0.0),
            )),
        })
        current = candidate

    audited = dict(current)
    audited["joint_standing_portfolio_gate"] = True
    audited["joint_standing_portfolio_trace"] = tuple(trace)
    audited["joint_standing_portfolio_rounds"] = len(trace)
    audited["joint_standing_portfolio_bound"] = len(asset_kinds)
    audited["joint_standing_response_count"] = len(
        context.get("responses", ())
    )
    return audited


def _crew_frontier_portfolio_descent(snap, rows):
    """Revalue every maximum-coverage crew arm before choosing the crew.

    A post-selection portfolio repair cannot reveal that a different paid crew
    supports a different robust composition.  We therefore retain every arm
    on the maximum positioned-coverage frontier and run the identical public
    max-min descent on each. Lower-coverage rows are dominated action spaces
    here: every one of their public positions is contained in each retained
    full-coverage universe, and the retained solver may explicitly idle any
    excess position. If that set-containment proof fails, no row is pruned.
    """
    rows = list(rows)
    if not rows:
        return rows
    coverage = [sum(int(qty or 0)
                    for qty in row.get("selected_counts", {}).values())
                for row in rows]
    maximum = max(coverage)
    frontier = [index for index, qty in enumerate(coverage)
                if qty == maximum]
    frontier_sets = [
        {tuple(pos) for positions in rows[index].get(
            "positions_by_item", {}).values() for pos in positions}
        for index in frontier
    ]
    containment = all(
        all(
            {tuple(pos) for positions in row.get(
                "positions_by_item", {}).values() for pos in positions}
            <= full_positions
            for full_positions in frontier_sets
        )
        for row in rows
    )
    candidates = frontier if containment else list(range(len(rows)))
    from whitebox import stackelberg as _stackelberg
    context = _stackelberg.make_context(
        snap, full_response_continuation=True,
    )
    out = []
    for index, row in enumerate(rows):
        if index not in candidates:
            dominated = dict(row)
            dominated["score"] = float("-inf")
            dominated["portfolio_crew_frontier_dominated"] = True
            dominated["portfolio_crew_frontier_coverage"] = int(maximum)
            out.append(dominated)
            continue
        solved = _robust_portfolio_descent(
            snap, row, service_fertilizer_credit=False,
            stackelberg_context=context,
            land_reinvestment_option=True,
        )
        solved["portfolio_crew_frontier_dominated"] = False
        solved["portfolio_crew_frontier_coverage"] = int(maximum)
        solved["portfolio_crew_frontier_containment"] = bool(containment)
        out.append(solved)
    return out


def _activation_task_sets(tasks):
    """Enumerate exact fixed-charge branches for the current one-step master.

    A fixed prerequisite is not a separable per-task cost: two $600 columns
    behind one $1,000 land purchase are profitable together, while two $400
    columns are not.  The route solver therefore must see both the branch in
    which that activation is unavailable and the branch in which it is
    available.  There is currently at most one next-quadrant activation, but
    this small powerset keeps the semantics correct if another shared engine
    prerequisite is added later.
    """
    tasks = list(tasks)
    keys = sorted({key for task in tasks for key in task.activations}, key=repr)
    if not keys:
        return [tasks]
    # Online safety: the current model has one key.  Four keys are still only
    # sixteen deterministic branches; above that retain the two economically
    # meaningful safe incumbents rather than risking the action deadline.
    masks = range(1 << len(keys)) if len(keys) <= 4 else (0, (1 << len(keys)) - 1)
    out, seen = [], set()
    for mask in masks:
        enabled = {key for i, key in enumerate(keys) if mask & (1 << i)}
        branch = [task for task in tasks
                  if set(task.activations).issubset(enabled)]
        signature = tuple(id(task) for task in branch)
        if signature not in seen:
            seen.add(signature)
            out.append(branch)
    return out


def _net_score(selected, hire_cost=0.0, charge_activations=True):
    score = sum(float(task.value) for task in selected) - float(hire_cost)
    if charge_activations:
        score -= _activation_cost(selected)
    return score


def _capital_output(snap, task):
    """Return ``(product, units)`` generated by one optional capital column."""
    if task.kind == "CAPITAL_CROP":
        crop = next((op[1] for op in task.ops
                     if op and op[0] == "PLANT" and len(op) > 1), None)
        return (crop, objective.plant_output_units(snap, crop))
    if task.kind == "CAPITAL_ANIMAL":
        kind = next((op[1] for op in task.ops
                     if op and op[0] == "PLACE" and len(op) > 1), None)
        # V58 extends V56's default capital columns, whose standalone value is
        # ``animal_placement_value`` (base production under minimum survival
        # feed), not the full FEED+CARE relaxation used by the joint-tile arms.
        units = objective.animal_placement_units(snap, kind)
        spec = econ.ANIMALS.get(kind)
        return ((spec or {}).get("product"), units)
    return None, 0


def _capital_bundle_terms(snap, columns):
    """Freeze each capital column's product quantity and non-sale value.

    The terms are captured before bundle repricing so later route trimming can
    recertify the actually executable quantity without trying to reverse an
    average-price allocation.  Values come only from the live observation and
    the crop/animal production and market equations.
    """
    terms = {}
    for task in columns:
        item, qty = _capital_output(snap, task)
        if item in econ.SELLABLE and qty > 0:
            standalone = objective.sale_value(snap, item, qty)
            terms[id(task)] = (item, int(qty),
                               float(task.value) - standalone)
    return terms


def _bundle_reprice_capital(snap, columns, terms=None):
    """Price repeated capital output once as a nonlinear same-item bundle.

    A column's old value contains its standalone sale revenue plus all non-sale
    terms (seed/animal cost and feed opportunity cost). For each product we
    remove those standalone revenues, aggregate the rule-derived quantities,
    call ``econ.sell_revenue`` once through ``objective.sale_value``, and share
    that exact bundle revenue in proportion to units. Equal same-product assets
    remain spatial alternatives rather than receiving an arbitrary first/last
    price based on tile ordering. Any selected subset is conservatively priced
    at the full proposal bundle's average price; the multi-day column generator
    will later reprice its recertified selected quantity exactly.
    """
    terms = (_capital_bundle_terms(snap, columns) if terms is None else terms)
    groups = {}
    for task in columns:
        term = terms.get(id(task))
        if term is not None:
            item, qty, base = term
            groups.setdefault(item, []).append((task, qty, base))
    for item, entries in groups.items():
        total_qty = sum(qty for _task, qty, _base in entries)
        bundle = objective.sale_value(snap, item, total_qty)
        for task, qty, base in entries:
            task.value = base + bundle * qty / float(total_qty)
    return columns


def _recertified_net_score(snap, selected, bundle_terms, hire_cost=0.0,
                           charge_activations=True):
    """Exact objective for the capital quantities retained by route solving.

    The route master first trims a conservatively priced full proposal to an
    executable task set.  This certificate then groups only those retained
    capital outputs, applies the nonlinear sale equation once per item, and
    adds every frozen non-sale and ordinary task term once.  It changes branch
    comparison, not route feasibility or the certified acquisition ceiling.
    """
    score = 0.0
    grouped_qty = Counter()
    for task in selected:
        term = bundle_terms.get(id(task))
        if term is None:
            score += float(task.value)
            continue
        item, qty, base = term
        grouped_qty[item] += int(qty)
        score += float(base)
    for item, qty in grouped_qty.items():
        score += objective.sale_value(snap, item, qty)
    score -= float(hire_cost)
    if charge_activations:
        score -= _activation_cost(selected)
    return score


def _paired_recertified_score(snap, selected, fixed_orders, reserve,
                              hire_cost=0.0):
    """Recertify actual routed capital under the multi-day paired equation."""
    capital_columns = [
        task for task in selected
        if task.kind in ("CAPITAL_CROP", "CAPITAL_ANIMAL")
        and task.order_key and len(task.order_key) >= 2
    ]
    ordinary = sum(task.value for task in selected
                   if task not in capital_columns)
    if not capital_columns:
        return ordinary - float(hire_cost)
    counts = Counter(task.order_key[1] for task in capital_columns)
    slots = sorted({tuple(task.pos) for task in capital_columns},
                   key=lambda pos: (paths.dist_to_shed(pos), pos))
    from whitebox import cashflow as _cashflow
    cert = _cashflow.certify_shared(
        snap, counts, slots, reserve=max(0.0, float(reserve)),
        land_cost=_activation_cost(capital_columns),
        fixed_orders=fixed_orders, paired_objective=True,
    )
    if not cert.feasible:
        return float("-inf")
    return ordinary + cert.paired_value - float(hire_cost)


def _positioned_paired_recertified_score(snap, selected, fixed_orders,
                                         reserve, ordinary_model,
                                         hire_cost=0.0):
    """Score ordinary work plus the exact retained capital assignment."""
    capital_columns = [
        task for task in selected
        if task.kind in ("CAPITAL_CROP", "CAPITAL_ANIMAL")
        and task.order_key and len(task.order_key) >= 2
    ]
    capital_ids = {id(task) for task in capital_columns}
    ordinary = [task for task in selected if id(task) not in capital_ids]
    ordinary_value = ordinary_model.score(ordinary)
    if not capital_columns:
        return ordinary_value - float(hire_cost)
    positions = {}
    for task in capital_columns:
        positions.setdefault(task.order_key[1], []).append(tuple(task.pos))
    counts = {item: len(item_positions)
              for item, item_positions in positions.items()}
    slots = sorted(
        {pos for item_positions in positions.values() for pos in item_positions},
        key=lambda pos: (paths.dist_to_shed(pos), pos),
    )
    from whitebox import cashflow as _cashflow
    cert = _cashflow.certify_shared(
        snap, counts, slots, reserve=max(0.0, float(reserve)),
        land_cost=_activation_cost(capital_columns),
        fixed_orders=fixed_orders, paired_objective=True,
        positions_by_item=positions,
    )
    if not cert.feasible:
        return float("-inf")
    return ordinary_value + cert.paired_value - float(hire_cost)


class PositionedCertificateObjective:
    """Exact selected-set objective for ordinary work and positioned capital.

    Ordinary tasks retain V76's grouped current-horizon equation. Capital
    insertions and swaps are valued by the exact change in the same positioned
    multi-day certificate used for final branch comparison. Certificate values
    are memoized by the retained physical task set; no wall clock, fitted
    coefficient or state-dependent fallback limits the solve.
    """

    def __init__(self, snap, tasks, fixed_orders, reserve,
                 phase_aligned=False, certificate_cache=None,
                 first_output_only=False, exact_first_output=False,
                 joint_farm_prefix=False, optional_continuation=False,
                 credit_fertilizer=False, paired_context=None,
                 semantic_certificate_cache=False,
                 stackelberg=False, stackelberg_context=None):
        from whitebox import cashflow as _cashflow
        self.snap = snap
        self.fixed_orders = list(fixed_orders or ())
        self.reserve = max(0.0, float(reserve))
        self.phase_aligned = bool(phase_aligned)
        self.first_output_only = bool(first_output_only)
        self.exact_first_output = bool(exact_first_output)
        self.joint_farm_prefix = bool(joint_farm_prefix)
        self.optional_continuation = bool(optional_continuation)
        self.credit_fertilizer = bool(credit_fertilizer)
        self.stackelberg = bool(stackelberg)
        self.stackelberg_context = stackelberg_context
        self.semantic_certificate_cache = bool(semantic_certificate_cache)
        self.capital = {
            id(task): task for task in tasks
            if task.kind in ("CAPITAL_CROP", "CAPITAL_ANIMAL")
            and task.order_key and len(task.order_key) >= 2
        }
        self.ordinary = {id(task): task for task in tasks
                         if id(task) not in self.capital}
        self.ordinary_model = objective.TaskBundleObjective(
            snap, self.ordinary.values(),
        )
        fixed_spend, initial_shed = _cashflow._fixed_commitment(
            snap, self.fixed_orders,
        )
        self.cash_context = (
            fixed_spend, initial_shed, _cashflow._reserved_book(snap),
        )
        self.paired_context = (
            paired_context if paired_context is not None else (
                _cashflow._own_reserved_book(snap),
                _cashflow._visible_output_schedule(snap, snap.opp),
                _cashflow._guaranteed_town_drain_by_day(snap),
            )
        )
        self._capital_cache = {(): 0.0}
        # The physical certificate and its minimum cash path do not depend on
        # the reserve threshold. V80 shares this cache across exact crew-cost
        # arms, then applies each arm's reserve inequality without re-solving.
        self._certificate_cache = (certificate_cache
                                   if certificate_cache is not None else {})
        self.certificate_evaluations = 0

    def counts(self, selected=()):
        state = {"capital": set(), "ordinary": set(),
                 "ordinary_counts": Counter()}
        for task in selected:
            self.update_counts(state, task)
        return state

    def update_counts(self, state, task, sign=1):
        task_id = id(task)
        if task_id in self.capital:
            if sign > 0:
                state["capital"].add(task_id)
            else:
                state["capital"].discard(task_id)
            return
        if sign > 0:
            state["ordinary"].add(task_id)
        else:
            state["ordinary"].discard(task_id)
        self.ordinary_model.update_counts(
            state["ordinary_counts"], task, sign,
        )

    def signature(self, task, state):
        if id(task) in self.capital:
            # Shared daily routes, hires, feed, cash and product curves mean
            # every retained capital column can change this exact marginal.
            return tuple(sorted(state["capital"]))
        return self.ordinary_model.signature(task, state["ordinary_counts"])

    def _capital_value(self, capital_ids):
        local_key = tuple(sorted(capital_ids))
        if local_key in self._capital_cache:
            return self._capital_cache[local_key]
        selected = [self.capital[task_id] for task_id in local_key]
        positions = {}
        for task in selected:
            positions.setdefault(task.order_key[1], []).append(tuple(task.pos))
        counts = {item: len(item_positions)
                  for item, item_positions in positions.items()}
        slots = sorted(
            {pos for item_positions in positions.values()
             for pos in item_positions},
            key=lambda pos: (paths.dist_to_shed(pos), pos),
        )
        certificate_key = local_key
        if self.semantic_certificate_cache:
            certificate_key = (
                tuple((item, tuple(sorted(item_positions)))
                      for item, item_positions in sorted(positions.items())),
                float(_activation_cost(selected)),
                float(self.reserve) if self.stackelberg else None,
                "stackelberg" if self.stackelberg else "paired",
            )
        if certificate_key in self._certificate_cache:
            physically_feasible, min_cash, paired_value = (
                self._certificate_cache[certificate_key]
            )
            value = (paired_value
                     if physically_feasible and min_cash + 1e-9 >= self.reserve
                     else float("-inf"))
            self._capital_cache[local_key] = float(value)
            return float(value)
        from whitebox import cashflow as _cashflow
        if self.stackelberg:
            from whitebox import stackelberg as _stackelberg
            cert = _stackelberg.certify_unified(
                self.snap, counts, slots, reserve=self.reserve,
                land_cost=_activation_cost(selected),
                fixed_orders=self.fixed_orders,
                cash_context=self.cash_context,
                positions_by_item=positions,
                context=self.stackelberg_context,
            )
        elif self.optional_continuation:
            cert = _cashflow.certify_optional_continuation(
                self.snap, counts, slots, reserve=0.0,
                land_cost=_activation_cost(selected),
                fixed_orders=self.fixed_orders, paired_objective=True,
                _context=self.cash_context, _paired_context=self.paired_context,
                positions_by_item=positions,
            )
        elif self.joint_farm_prefix:
            cert = _cashflow.certify_joint_farm_prefix(
                self.snap, counts, slots, reserve=0.0,
                land_cost=_activation_cost(selected),
                fixed_orders=self.fixed_orders, paired_objective=True,
                _context=self.cash_context, _paired_context=self.paired_context,
                positions_by_item=positions,
            )
        else:
            cert = _cashflow.certify_shared(
                self.snap, counts, slots, reserve=0.0,
                land_cost=_activation_cost(selected),
                fixed_orders=self.fixed_orders, paired_objective=True,
                _context=self.cash_context, _paired_context=self.paired_context,
                positions_by_item=positions,
                phase_aligned=self.phase_aligned,
                first_output_only=self.first_output_only,
                exact_first_output=self.exact_first_output,
                credit_fertilizer=self.credit_fertilizer,
            )
        self.certificate_evaluations += 1
        min_cash = (
            float(cert.minimum_cash)
            if self.semantic_certificate_cache
            else (min(cert.cash_path) if cert.cash_path else float("-inf"))
        )
        self._certificate_cache[certificate_key] = (
            bool(cert.feasible), float(min_cash), float(cert.paired_value),
        )
        value = (cert.paired_value
                 if cert.feasible and min_cash + 1e-9 >= self.reserve
                 else float("-inf"))
        self._capital_cache[local_key] = float(value)
        return float(value)

    def _state_score(self, state):
        ordinary = [self.ordinary[task_id]
                    for task_id in state["ordinary"]]
        return (self.ordinary_model.score(ordinary)
                + self._capital_value(state["capital"]))

    def add_gain(self, task, state):
        task_id = id(task)
        if task_id not in self.capital:
            return self.ordinary_model.add_gain(
                task, state["ordinary_counts"],
            )
        before = self._capital_value(state["capital"])
        after_ids = set(state["capital"])
        after_ids.add(task_id)
        return self._capital_value(after_ids) - before

    def swap_gain(self, incoming, outgoing, state):
        trial = {"capital": set(state["capital"]),
                 "ordinary": set(state["ordinary"]),
                 "ordinary_counts": Counter(state["ordinary_counts"])}
        before = self._state_score(trial)
        self.update_counts(trial, outgoing, -1)
        self.update_counts(trial, incoming, 1)
        return self._state_score(trial) - before

    def score(self, selected):
        return self._state_score(self.counts(selected))


class FirstOutputPrefixObjective(PositionedCertificateObjective):
    """Exact selected-set value for the constructive first-output prefix.

    Ordinary work keeps V89's grouped current-route objective. Capital is
    valued by purchase cost, only the minimum rule-feasible service through
    each first harvest, and that grouped first sale. No later output or service
    is credited or charged; those decisions belong to later public replans.
    """

    def __init__(self, snap, tasks, fixed_orders, reserve,
                 certificate_cache=None):
        super().__init__(
            snap, tasks, fixed_orders, reserve,
            certificate_cache=certificate_cache,
            first_output_only=True,
        )


class ExactFirstOutputObjective(PositionedCertificateObjective):
    """V99 selected-set value using exact earliest harvestable quantities."""

    def __init__(self, snap, tasks, fixed_orders, reserve,
                 certificate_cache=None):
        super().__init__(
            snap, tasks, fixed_orders, reserve,
            certificate_cache=certificate_cache,
            exact_first_output=True,
        )


class JointFarmPrefixObjective(PositionedCertificateObjective):
    """V100 exact prefix marginal over identical visible-farm service."""

    def __init__(self, snap, tasks, fixed_orders, reserve,
                 certificate_cache=None):
        super().__init__(
            snap, tasks, fixed_orders, reserve,
            certificate_cache=certificate_cache,
            joint_farm_prefix=True,
        )


class OptionalContinuationObjective(PositionedCertificateObjective):
    """V101 selected-set value under optional exact continuation."""

    def __init__(self, snap, tasks, fixed_orders, reserve,
                 certificate_cache=None):
        super().__init__(
            snap, tasks, fixed_orders, reserve,
            certificate_cache=certificate_cache,
            optional_continuation=True,
        )


class ProductiveInventoryCertificateObjective(PositionedCertificateObjective):
    """V90 robust sale/retention state inside the productive marginal.

    Capital columns remain exactly V89's observation-derived proposal. For
    every retained physical capital set, compare executing V89's complete live
    sale bundle with retaining that same bundle until the first certified new
    output day. Both alternatives prove the identical positioned service
    routes, pre-sale purchase cash, daily bridge cash, persistent shed path and
    market slots. No independently invented portfolio or quantity coefficient
    enters this objective.
    """

    def __init__(self, snap, tasks, fixed_orders, reserve):
        from whitebox import cashflow as _cashflow
        super().__init__(snap, tasks, fixed_orders, reserve)
        stock = {item: max(0, int(qty or 0))
                 for item, qty in snap.shed.items()}
        self.sale_bundle = Counter()
        for order in self.fixed_orders[:econ.MAX_ORDERS]:
            if (not order or len(order) < 3 or order[0] != "SELL"
                    or order[1] not in econ.SELLABLE):
                continue
            item = str(order[1])
            qty = min(max(0, int(order[2] or 0)), stock.get(item, 0))
            if qty <= 0:
                continue
            stock[item] -= qty
            self.sale_bundle[item] += qty
        self.retained_fixed_orders = [
            list(order) for order in self.fixed_orders
            if not order or order[0] != "SELL"
        ]
        self.baseline_sale_value = sum(
            _cashflow._sale_result(
                item, qty,
                int(snap.market_inv.get(item, econ.MARKET_I0)
                    or econ.MARKET_I0),
            )[0]
            for item, qty in self.sale_bundle.items()
        )
        self._capital_cache = {(): 0.0}
        self._sale_choice = {(): list(self.fixed_orders)}

    def _capital_value(self, capital_ids):
        key = tuple(sorted(capital_ids))
        if key in self._capital_cache:
            return self._capital_cache[key]
        selected = [self.capital[task_id] for task_id in key]
        positions = {}
        for task in selected:
            positions.setdefault(task.order_key[1], []).append(tuple(task.pos))
        counts = {item: len(item_positions)
                  for item, item_positions in positions.items()}
        slots = sorted(
            {pos for item_positions in positions.values()
             for pos in item_positions},
            key=lambda pos: (paths.dist_to_shed(pos), pos),
        )
        from whitebox import cashflow as _cashflow
        stops, feed, outputs, error = _cashflow._profiles_positioned(
            self.snap, positions,
        )
        if error:
            self._capital_cache[key] = float("-inf")
            self._sale_choice[key] = list(self.fixed_orders)
            return float("-inf")
        days = sorted(set(stops) | set(feed) | set(outputs))
        initial_shed = int(self.cash_context[1])
        sold_units = sum(self.sale_bundle.values())
        alternatives = []
        # A strict tie executes V89's current sale and preserves the immutable
        # baseline. Retention is admissible only when a certified output day
        # exists, as enforced by `productive_inventory_terms`.
        for sell_now in (True, False):
            terms = _cashflow.productive_inventory_terms(
                self.snap, outputs, self.sale_bundle, sell_now,
            )
            if terms is None:
                continue
            anchor = terms["anchor_day"]
            persistent = {}
            for day in days:
                sale_has_executed = sell_now or (
                    anchor is not None and int(day) > int(anchor)
                )
                persistent[day] = max(
                    0, initial_shed - (sold_units if sale_has_executed else 0),
                )
            credits = ({int(anchor): float(terms["future_cash"])}
                       if anchor is not None and terms["future_cash"] > 0
                       else {})
            sale_products = ({int(anchor): set(terms["future_products"])}
                             if anchor is not None else {})
            cert = _cashflow.certify_shared(
                self.snap, counts, slots, reserve=self.reserve,
                land_cost=_activation_cost(selected),
                fixed_orders=self.fixed_orders, _context=self.cash_context,
                positions_by_item=positions,
                post_market_cash=float(terms["current_cash"]),
                cash_credit_by_day=credits,
                persistent_shed_by_day=persistent,
                sale_products_by_day=sale_products,
                credit_output_cash=False,
            )
            self.certificate_evaluations += 1
            if not cert.feasible:
                continue
            value = (float(terms["paired_revenue"])
                     - float(self.baseline_sale_value)
                     - float(cert.upfront_spend)
                     - float(cert.operating_cost))
            orders = (list(self.fixed_orders) if sell_now
                      else list(self.retained_fixed_orders))
            alternatives.append((value, 0 if sell_now else 1, orders))
        if not alternatives:
            value, orders = float("-inf"), list(self.fixed_orders)
        else:
            value, _tie, orders = max(
                alternatives, key=lambda arm: (arm[0], -arm[1]),
            )
        self._capital_cache[key] = float(value)
        self._sale_choice[key] = orders
        return float(value)

    def fixed_orders_for(self, selected):
        state = self.counts(selected)
        key = tuple(sorted(state["capital"]))
        self._capital_value(key)
        return [list(order) for order in self._sale_choice.get(
            key, self.fixed_orders,
        )]


class ProductiveInventoryPathObjective(ProductiveInventoryCertificateObjective):
    """V91 all-output robust path value with daily cash-prefix proofs."""

    def _capital_value(self, capital_ids):
        key = tuple(sorted(capital_ids))
        if key in self._capital_cache:
            return self._capital_cache[key]
        selected = [self.capital[task_id] for task_id in key]
        positions = {}
        for task in selected:
            positions.setdefault(task.order_key[1], []).append(tuple(task.pos))
        counts = {item: len(item_positions)
                  for item, item_positions in positions.items()}
        slots = sorted(
            {pos for item_positions in positions.values()
             for pos in item_positions},
            key=lambda pos: (paths.dist_to_shed(pos), pos),
        )
        from whitebox import cashflow as _cashflow
        stops, feed, outputs, error = _cashflow._profiles_positioned(
            self.snap, positions,
        )
        if error:
            self._capital_cache[key] = float("-inf")
            self._sale_choice[key] = list(self.fixed_orders)
            return float("-inf")
        days = sorted(set(stops) | set(feed) | set(outputs))
        initial_shed = int(self.cash_context[1])
        sold_units = sum(self.sale_bundle.values())
        alternatives = []
        for sell_now in (True, False):
            terms = _cashflow.productive_inventory_path_terms(
                self.snap, outputs, self.sale_bundle, sell_now,
            )
            if terms is None:
                continue
            anchor = terms["anchor_day"]
            persistent = {}
            for day in days:
                sale_has_executed = sell_now or (
                    anchor is not None and int(day) > int(anchor)
                )
                persistent[day] = max(
                    0, initial_shed - (sold_units if sale_has_executed else 0),
                )
            cert = _cashflow.certify_shared(
                self.snap, counts, slots, reserve=self.reserve,
                land_cost=_activation_cost(selected),
                fixed_orders=self.fixed_orders, _context=self.cash_context,
                positions_by_item=positions,
                persistent_shed_by_day=persistent,
                sale_products_by_day=terms["future_products_by_day"],
                credit_output_cash=False, enforce_bridge_cash=False,
            )
            self.certificate_evaluations += 1
            if not cert.feasible:
                continue
            upfront_cash = (float(self.snap.me.money)
                            - float(self.cash_context[0])
                            - float(cert.upfront_spend))
            cumulative_cost = 0.0
            earned = 0.0
            cash_ok = True
            for day in sorted(cert.operating_cost_by_day):
                cumulative_cost += cert.operating_cost_by_day[day]
                if day in terms["prefix_cash"]:
                    earned = float(terms["prefix_cash"][day])
                cash = (upfront_cash + float(terms["current_cash"])
                        + earned - cumulative_cost)
                if cash < self.reserve - 1e-9:
                    cash_ok = False
                    break
            if not cash_ok:
                continue
            value = (float(terms["paired_revenue"])
                     - float(self.baseline_sale_value)
                     - float(cert.upfront_spend)
                     - float(cert.operating_cost))
            orders = (list(self.fixed_orders) if sell_now
                      else list(self.retained_fixed_orders))
            alternatives.append((value, 0 if sell_now else 1, orders))
        if not alternatives:
            value, orders = float("-inf"), list(self.fixed_orders)
        else:
            value, _tie, orders = max(
                alternatives, key=lambda arm: (arm[0], -arm[1]),
            )
        self._capital_cache[key] = float(value)
        self._sale_choice[key] = orders
        return float(value)


class ProductiveFeasibilityObjective:
    """V92 physical/cash oracle around V89's unchanged economic score.

    ``TaskBundleObjective`` remains the sole selected-set value equation.  The
    multi-day model may only exclude a capital subset that lacks a positioned
    service, shed, slot or daily cash proof.  Current sale versus retention is
    an outer executable branch; it never adds future revenue to the objective.
    Future revenue appears only as a conservative cash credit proving that the
    exact service bill can be paid when due.
    """

    def __init__(self, snap, tasks, source_fixed_orders, current_fixed_orders,
                 reserve, sell_now, certificate_cache=None):
        from whitebox import cashflow as _cashflow
        self.snap = snap
        self.tasks = {id(task): task for task in tasks}
        self.capital = {
            id(task): task for task in tasks
            if task.kind in ("CAPITAL_CROP", "CAPITAL_ANIMAL")
            and task.order_key and len(task.order_key) >= 2
        }
        self.bundle_model = objective.TaskBundleObjective(snap, tasks)
        self.source_fixed_orders = [list(order)
                                    for order in source_fixed_orders or ()]
        self.current_fixed_orders = [list(order)
                                     for order in current_fixed_orders or ()]
        self.reserve = max(0.0, float(reserve))
        self.sell_now = bool(sell_now)
        stock = {item: max(0, int(qty or 0))
                 for item, qty in snap.shed.items()}
        self.sale_bundle = Counter()
        for order in self.source_fixed_orders[:econ.MAX_ORDERS]:
            if (not order or len(order) < 3 or order[0] != "SELL"
                    or order[1] not in econ.SELLABLE):
                continue
            item = str(order[1])
            qty = min(max(0, int(order[2] or 0)), stock.get(item, 0))
            if qty <= 0:
                continue
            stock[item] -= qty
            self.sale_bundle[item] += qty
        fixed_spend, initial_shed = _cashflow._fixed_commitment(
            snap, self.current_fixed_orders,
        )
        self.cash_context = (
            fixed_spend, initial_shed, _cashflow._reserved_book(snap),
        )
        # The physical proof and the minimum cash checkpoint do not depend on
        # the reserve threshold. Exact crew arms therefore share this cache
        # and compare their own Fibonacci hire cost after one proof.
        self._proof_cache = (certificate_cache
                             if certificate_cache is not None else {})
        self._proof_cache.setdefault(
            (), float("inf") if self.sell_now else float("-inf"),
        )
        self.certificate_evaluations = 0

    def counts(self, selected=()):
        state = {"selected": set(), "capital": set(),
                 "bundle_counts": Counter()}
        for task in selected:
            self.update_counts(state, task)
        return state

    def update_counts(self, state, task, sign=1):
        task_id = id(task)
        if sign > 0:
            state["selected"].add(task_id)
            if task_id in self.capital:
                state["capital"].add(task_id)
        else:
            state["selected"].discard(task_id)
            state["capital"].discard(task_id)
        self.bundle_model.update_counts(state["bundle_counts"], task, sign)

    def signature(self, task, state):
        economic = self.bundle_model.signature(task, state["bundle_counts"])
        if id(task) not in self.capital:
            return economic
        # Every capital insertion can change shared daily labour, feed, cash,
        # shed and sale-slot feasibility, so the complete physical subset is
        # part of the exact lazy-repricing signature.
        return tuple(sorted(state["capital"])), economic

    def _capital_feasible(self, capital_ids):
        key = tuple(sorted(capital_ids))
        if key in self._proof_cache:
            return self._proof_cache[key] + 1e-9 >= self.reserve
        selected = [self.capital[task_id] for task_id in key]
        positions = {}
        for task in selected:
            positions.setdefault(task.order_key[1], []).append(tuple(task.pos))
        counts = {item: len(item_positions)
                  for item, item_positions in positions.items()}
        slots = sorted(
            {pos for item_positions in positions.values()
             for pos in item_positions},
            key=lambda pos: (paths.dist_to_shed(pos), pos),
        )
        from whitebox import cashflow as _cashflow
        stops, feed, outputs, error = _cashflow._profiles_positioned(
            self.snap, positions,
        )
        if error:
            self._proof_cache[key] = float("-inf")
            return False
        terms = _cashflow.productive_inventory_path_terms(
            self.snap, outputs, self.sale_bundle, self.sell_now,
            include_paired_value=False,
        )
        if terms is None:
            self._proof_cache[key] = float("-inf")
            return False
        days = sorted(set(stops) | set(feed) | set(outputs))
        initial_shed = int(self.cash_context[1])
        sold_units = sum(self.sale_bundle.values())
        anchor = terms["anchor_day"]
        persistent = {}
        for day in days:
            sale_has_executed = self.sell_now or (
                anchor is not None and int(day) > int(anchor)
            )
            persistent[day] = max(
                0, initial_shed - (sold_units if sale_has_executed else 0),
            )
        cert = _cashflow.certify_shared(
            self.snap, counts, slots, reserve=0.0,
            land_cost=_activation_cost(selected),
            fixed_orders=self.current_fixed_orders,
            _context=self.cash_context, positions_by_item=positions,
            post_market_cash=float(terms["current_cash"]),
            persistent_shed_by_day=persistent,
            sale_products_by_day=terms["future_products_by_day"],
            credit_output_cash=False, enforce_bridge_cash=False,
        )
        self.certificate_evaluations += 1
        max_reserve = float("-inf")
        if cert.feasible:
            upfront_cash = (float(self.snap.me.money)
                            - float(self.cash_context[0])
                            - float(cert.upfront_spend))
            # This checkpoint precedes current sales, so sale cash can never
            # rescue the asset purchase or current hire.
            max_reserve = upfront_cash
            cumulative_cost = 0.0
            earned = 0.0
            for day in sorted(cert.operating_cost_by_day):
                cumulative_cost += cert.operating_cost_by_day[day]
                if day in terms["prefix_cash"]:
                    earned = float(terms["prefix_cash"][day])
                cash = (upfront_cash + float(terms["current_cash"])
                        + earned - cumulative_cost)
                max_reserve = min(max_reserve, cash)
        self._proof_cache[key] = float(max_reserve)
        return max_reserve + 1e-9 >= self.reserve

    def _state_score(self, state):
        if not self._capital_feasible(state["capital"]):
            return float("-inf")
        selected = [self.tasks[task_id]
                    for task_id in state["selected"]]
        return float(self.bundle_model.score(selected))

    def add_gain(self, task, state):
        after_capital = set(state["capital"])
        if id(task) in self.capital:
            after_capital.add(id(task))
        if not self._capital_feasible(after_capital):
            return float("-inf")
        return float(self.bundle_model.add_gain(
            task, state["bundle_counts"],
        ))

    def swap_gain(self, incoming, outgoing, state):
        before = self._state_score(state)
        trial = {"selected": set(state["selected"]),
                 "capital": set(state["capital"]),
                 "bundle_counts": Counter(state["bundle_counts"])}
        self.update_counts(trial, outgoing, -1)
        self.update_counts(trial, incoming, 1)
        after = self._state_score(trial)
        return after - before

    def score(self, selected):
        return self._state_score(self.counts(selected))

    def fixed_orders_for(self, _selected):
        return [list(order) for order in self.current_fixed_orders]


def _repair_task_key(task):
    """State-local deterministic tie-break for equal economic repair loss."""
    return (repr(task.order_key), tuple(task.pos), str(task.kind),
            tuple(tuple(op) for op in task.ops))


def repair_productive_selection(selected, auditor, economic_model,
                                charge_activations=True):
    """Trim only routed capital until the actual selected set is certified.

    V89's route master and nonlinear score run first. If its actual capital
    quantity lacks a full physical/cash proof, remove one capital column at a
    time. At each step keep the trial with the largest unchanged V89 score;
    exact fixed activation is included once. Ordinary work is never removed.
    The finite loop is bounded by the selected capital count and every trial
    strictly reduces it, so no clock or fallback can affect the result.
    """
    working = list(selected)
    while auditor.score(working) == float("-inf"):
        capital_tasks = [task for task in working if id(task) in auditor.capital]
        if not capital_tasks:
            break
        best = None
        for task in capital_tasks:
            trial = [kept for kept in working if kept is not task]
            score = float(economic_model.score(trial))
            if charge_activations:
                score -= _activation_cost(trial)
            key = (-score, _repair_task_key(task))
            if best is None or key < best[0]:
                best = (key, trial)
        working = best[1]
    return working


class _ConditionalBundleObjective:
    """Exact V89 marginal with a fixed already-selected task prefix."""

    def __init__(self, model, fixed):
        self.model = model
        self.fixed = list(fixed)

    def counts(self, selected=()):
        return self.model.counts(self.fixed + list(selected))

    def update_counts(self, counts, task, sign=1):
        self.model.update_counts(counts, task, sign)

    def signature(self, task, counts):
        return self.model.signature(task, counts)

    def add_gain(self, task, counts):
        return self.model.add_gain(task, counts)

    def swap_gain(self, incoming, outgoing, counts):
        return self.model.swap_gain(incoming, outgoing, counts)

    def score(self, selected):
        return self.model.score(self.fixed + list(selected))


def _deadline_capital_task(snap, task):
    """Whether this asset must be placed today to retain any modelled output."""
    if not task.order_key or len(task.order_key) < 2:
        return False
    op, item = task.order_key[:2]
    if op == "BUY_SEED" and item in econ.SEED_DEADLINE:
        deadline = int(econ.SEED_DEADLINE[item])
    elif op == "BUY_ANIMAL" and item in econ.ANIMAL_DEADLINE:
        deadline = int(econ.ANIMAL_DEADLINE[item])
    else:
        return False
    return (int(snap.step) <= deadline
            and int(snap.day) == deadline // econ.TURNS_PER_DAY)


def _capital_task_legal_after_unit_phase(projected, task):
    """Exact tile precondition for a previously selected capital column."""
    x, y = tuple(task.pos)
    tile = projected.me.tiles[y][x]
    names = [op[0] for op in task.ops if op]
    locked_with_land = tile == "LOCKED" and bool(task.activations)
    if "PLANT" in names:
        return tile is None or locked_with_land
    if any(name.startswith("BUILD_") for name in names):
        return tile is None or locked_with_land
    if "PLACE" in names:
        kind = task.order_key[1]
        spec = econ.ANIMALS.get(kind)
        return (spec is not None and isinstance(tile, dict)
                and tile.get("kind") == spec["structure"]
                and "animal" not in tile)
    return False


def validate_deadline_capital(snap, selected, hires, unit_actions,
                              economic_model, bank_outputs=False):
    """Retain deadline-day capital executable after this turn's unit phase.

    Capital is purchased in the market phase, after every current unit action.
    On the final productive placement day, any column that cannot complete its
    initial operations in the remaining actions cannot produce the units V89
    assigned to it. Non-deadline columns are unchanged. The validator is a
    necessary relaxation: it ignores all competing future ordinary work.
    """
    selected = list(selected)
    deadline_tasks = [task for task in selected
                      if _deadline_capital_task(snap, task)]
    if not deadline_tasks:
        return selected
    from whitebox import state as _state
    projected = _state.project_unit_phase(snap, unit_actions)
    legal = [task for task in deadline_tasks
             if _capital_task_legal_after_unit_phase(projected, task)]
    fixed = [task for task in selected if task not in deadline_tasks]
    if not legal:
        return fixed
    stock = Counter()
    for task in legal:
        if task.order_key[0] == "BUY_ANIMAL":
            stock[task.order_key[1]] += 1
    assignment, _left = router.joint_assign(
        legal,
        _units(projected, hires, None, post_action=True,
               already_projected=True),
        dict(stock), deadline=None, refine=False,
        bank_outputs=bank_outputs,
        bundle_model=_ConditionalBundleObjective(economic_model, fixed),
        memoize_route_cost=True,
    )
    retained = {id(task) for task in _selected(assignment)}
    return [task for task in selected
            if task not in deadline_tasks or id(task) in retained]


def _asset_orders(selected, proposed):
    quantities = Counter()
    activations = set()
    for task in selected:
        if task.order_key is not None:
            quantities[task.order_key] += 1
        activations.update(task.activations)

    out = []
    # Preserve the computed strategy's product ordering; only quantities are
    # replaced by what the joint task/route solve can actually service.
    emitted = set()
    for order in proposed:
        if not order:
            continue
        if order[0] == "BUY_LAND":
            keys = [key for key in activations if key[0] == "BUY_LAND"]
            if keys and "BUY_LAND" not in emitted:
                out.append(["BUY_LAND"])
                emitted.add("BUY_LAND")
            continue
        if len(order) < 2:
            continue
        key = (order[0], order[1])
        n = quantities.get(key, 0)
        if n > 0 and key not in emitted:
            out.append([order[0], order[1], n])
            emitted.add(key)
    return out


def compose_orders(fixed, hires, assets, frontload_sales=False):
    """Prerequisite feed, then crew/assets, then price-sensitive sales."""
    buys = [o for o in fixed if o and o[0] == "BUY_PRODUCT"]
    sales = [o for o in fixed if o and o[0] == "SELL"]
    rest = [o for o in fixed
            if not (o and o[0] in ("BUY_PRODUCT", "SELL"))]
    if frontload_sales:
        return (sales + buys + [["HIRE"] for _ in range(hires)]
                + list(assets) + rest)[:econ.MAX_ORDERS]
    return (buys + [["HIRE"] for _ in range(hires)] + list(assets)
            + sales + rest)[:econ.MAX_ORDERS]


def _incremental_manifest_hire_choice(snap, plan, fixed, bank_outputs=False,
                                      allowed_kinds=()):
    """Price new hands only against the opening manifest's explicit tail."""
    from whitebox import tasks as _task_planner

    cache = _task_planner._PLAN.get(snap.seat)
    if cache is None or cache.get("day") != snap.day:
        return 0
    pending = list(cache.get("undone") or ())
    if allowed_kinds:
        allowed = frozenset(str(kind) for kind in allowed_kinds)
        pending = [task for task in pending
                   if str(getattr(task, "kind", "")) in allowed]
    if not pending:
        return 0
    room = max(0, min(
        econ.MAX_ORDERS - len(fixed),
        hiring.MAX_HANDS - len(snap.me.hands),
    ))
    reserve = max(0.0, float(getattr(
        plan, "service_cash_floor", getattr(plan, "cash_floor", 0.0),
    ) or 0.0))
    spendable = max(
        0.0, float(snap.me.money) - reserve - float(_fixed_spend(snap, fixed)),
    )
    best = (0.0, 0.0, 0)
    for k in range(1, room + 1):
        hire_cost = float(econ.hire_block_cost(snap.me.hires_today, k))
        if hire_cost > spendable + 1e-9:
            break
        spawns = hiring.spawn_positions(snap, k, None)
        first_idx = 1 + len(snap.me.hands)
        units = [Unit(first_idx + j, pos, snap.hour + 1)
                 for j, pos in enumerate(spawns)]
        model = objective.TaskBundleObjective(snap, pending)
        assignment, _left = router.joint_assign(
            pending, units, objective.planned_shed_stock(snap, plan),
            deadline=None, refine=False, bank_outputs=bank_outputs,
            bundle_model=model, memoize_route_cost=True,
        )
        selected = _selected(assignment)
        value = float(model.score(selected))
        net = value - hire_cost
        key = (net, -hire_cost, -k)
        if key > (best[0], best[1], -best[2]):
            best = (net, -hire_cost, k)
    return int(best[2]) if best[0] > 0.0 else 0


def _certified_deferred_hire_choice(snap, plan, fixed):
    """Execute only this day's crop-challenger hour-1 hire certificate."""
    record = _DEFERRED_HIRES.pop(snap.seat, None)
    if not record or int(record[0]) != int(snap.day):
        return 0
    requested = max(0, int(record[1]))
    room = max(0, min(
        requested,
        econ.MAX_ORDERS - len(fixed),
        hiring.MAX_HANDS - len(snap.me.hands),
    ))
    protected = max(
        0.0,
        float(getattr(plan, "cash_floor", 0.0) or 0.0),
        float(getattr(plan, "service_cash_floor", 0.0) or 0.0),
    )
    spendable = max(
        0.0, float(snap.me.money) - protected
        - float(_fixed_spend(snap, fixed)),
    )
    affordable = 0
    for quantity in range(1, room + 1):
        if float(econ.hire_block_cost(
                snap.me.hires_today, quantity)) > spendable + 1e-9:
            break
        affordable = quantity
    return int(affordable)


def crew_conditioned_decision_curve(snap, plan, tasks, market_orders,
                                    bank_outputs=False,
                                    fertilizer_bridge=False,
                                    memoize_proposals=False,
                                    reserve_visible_fertilizer=False,
                                    exchange_repair=False,
                                    adaptive_marginal=False,
                                    intraday_replan=False,
                                    joint_visible_workload=False,
                                    stackelberg=False,
                                    land_reinvestment=False,
                                    activated_land_reinvestment=False,
                                    stackelberg_arm_recertification=False,
                                    full_service_continuation=False,
                                    execution_aligned_crew=False,
                                    execution_aligned_empty_farm=False,
                                    cashflow_backed_service_hiring=False,
                                    crop_only_land_arm=False,
                                    robust_crop_land_gate=False,
                                    joint_standing_capital=False,
                                    land_frontier_certificate=False,
                                    turnover_positions=(),
                                    turnover_items_by_position=None):
    """Jointly rebuild capital columns for every legal current crew size.

    This is the strict hiring/task-planning seam.  In the older master the
    asset proposal was constructed once and every ``k`` arm merely rerouted
    that fixed set; extra workers could never make an additional purchase task
    exist.  Here each arm gives the portfolio inventor its exact Fibonacci
    bill and remaining market slots, obtains that arm's positioned asset set,
    and then proves the selected subset against the same post-unit route.

    All bounds are public engine bounds (cash, ten orders, persistent hand
    safety and physical positions).  No observed crew count, action trace or
    fixed opening target enters the enumeration.
    """
    fixed, _legacy_proposal = split_orders(market_orders)
    turnover_positions = frozenset(
        tuple(pos) for pos in (turnover_positions or ())
    )
    turnover_items_by_position = {
        tuple(pos): str(item)
        for pos, item in (turnover_items_by_position or {}).items()
        if str(item) in econ.CROPS
    }
    if turnover_items_by_position:
        turnover_positions = frozenset(
            pos for pos in turnover_positions
            if pos in turnover_items_by_position
        )
    intraday_turnover = bool(turnover_positions and int(snap.hour) != 0)
    if int(snap.hour) != 0 and not intraday_replan and not intraday_turnover:
        return []

    from whitebox import cashflow as _cashflow

    service_reserve = max(
        0.0, float(getattr(plan, "service_cash_floor",
                           getattr(plan, "cash_floor", 0.0)) or 0.0),
    )
    fixed_spend = float(_fixed_spend(snap, fixed))
    spendable = max(
        0.0, float(snap.me.money) - service_reserve - fixed_spend,
    )

    def same_day_output_cash_floor(selected):
        """Cash lower bound from outputs this closed route banks today.

        One adversarial opponent shed plus every remaining visible opponent
        unit is placed ahead of our sale independently in each product book.
        This relaxation is stricter than the physical shared-capacity set, so
        the resulting proceeds are a valid lower bound. Future task value,
        uncollected output and private inventory receive no credit.
        """
        if not bank_outputs:
            return 0.0
        from whitebox import cashflow as _cashflow_local
        outputs = Counter()
        for task in selected:
            for (item, day), qty in objective.task_sale_schedule(
                    snap, task).items():
                if int(day) == int(snap.day) and int(qty or 0) > 0:
                    outputs[str(item)] += int(qty)
        opponent_units = _cashflow_local._remaining_visible_units(
            snap, snap.opp, include_fertilizer=True,
        )
        cash = 0.0
        for item, qty in outputs.items():
            adverse_book = (
                int(snap.market_inv.get(item, econ.MARKET_I0)
                    or econ.MARKET_I0)
                + int(econ.SHED_CAPACITY)
                + max(0, int(opponent_units.get(item, 0) or 0))
            )
            cash += float(econ.sell_revenue(item, int(qty), adverse_book))
        return float(cash)

    # Existing public tasks provide only an enumeration bound. Each retained
    # row is proved again below from the tasks its actual closed routes bank.
    enumerated_service_credit = (
        same_day_output_cash_floor(tasks)
        if cashflow_backed_service_hiring else 0.0
    )
    hire_spendable = max(
        0.0,
        float(snap.me.money) - fixed_spend
        - max(0.0, service_reserve - enumerated_service_credit),
    )
    room = max(0, min(
        econ.MAX_ORDERS - len(fixed),
        hiring.MAX_HANDS - len(snap.me.hands),
    ))
    if intraday_turnover:
        # A same-day HIRE changes the live unit count and therefore invalidates
        # the incumbent daily manifest.  The turnover column was already
        # budgeted as DIG+PLANT+WATER in that manifest; it needs only its seed,
        # never a global crew re-plan.
        room = 0
    blocked = {tuple(task.pos) for task in tasks}
    if intraday_turnover:
        # This finite option may buy crops only for tiles DIG released in the
        # immediately preceding projected unit phase. Pre-existing empty land,
        # another land purchase and livestock remain V199 decisions rather than
        # leaking into an unrelated intraday re-optimisation.
        blocked.update(
            tuple(pos) for pos in snap.me.empty
            if tuple(pos) not in turnover_positions
        )
    rows = []
    proposal_certificate_cache = {} if memoize_proposals else None
    positioned_certificate_cache = {} if memoize_proposals else None
    paired_context = None
    stackelberg_context = None
    if memoize_proposals:
        paired_context = (
            _cashflow._own_reserved_book(
                snap, include_fertilizer=reserve_visible_fertilizer,
            ),
            _cashflow._visible_output_schedule(
                snap, snap.opp,
                include_fertilizer=reserve_visible_fertilizer,
            ),
            _cashflow._guaranteed_town_drain_by_day(snap),
        )
    late_crop_gate_active = bool(
        robust_crop_land_gate and len(snap.me.unlocked) >= 2
    )
    # The opening farm is deliberately left unchanged. Once productive
    # capital is public, however, every proposed purchase shares its dated
    # feed, service, route and wage path with that standing farm. The same
    # candidate is then measured on one nonlinear market book against every
    # finite paid public response. This is an equation switch, not a date,
    # herd-size or replay-conditioned target.
    joint_standing_active = bool(
        (joint_standing_capital or intraday_turnover)
        and (snap.me.animals or snap.me.crops)
    )
    if stackelberg or late_crop_gate_active or joint_standing_active:
        from whitebox import stackelberg as _stackelberg
        all_response_products = tuple(econ.CROPS) + tuple(sorted({
            str(spec["product"]) for spec in econ.ANIMALS.values()
        }))
        stackelberg_context = _stackelberg.make_context(
            snap,
            full_response_continuation=joint_standing_active,
            include_own_standing_book=(
                late_crop_gate_active or joint_standing_active
            ),
            candidate_response_products=(
                all_response_products if joint_standing_active
                else tuple(econ.CROPS) if late_crop_gate_active else ()
            ),
        )
    prior_universe_signature = None
    prior_all_selected = False
    prior_complete_assignment = ()
    empty_farm_alignment = bool(
        execution_aligned_empty_farm and _is_empty_capital_state(snap)
    )

    for k in range(room + 1):
        hire_cost = float(econ.hire_block_cost(snap.me.hires_today, k))
        if hire_cost > hire_spendable + 1e-9:
            break
        purchase_slots = econ.MAX_ORDERS - len(fixed) - k
        arm_fixed = list(fixed) + [["HIRE"] for _ in range(k)]
        proposed, proposal_certificate = _cashflow.invent_paired_proposal(
            snap,
            fixed_orders=arm_fixed,
            reserve=service_reserve + hire_cost,
            reserve_inventory=True,
            blocked_positions=blocked,
            phase_aligned=True,
            fertilizer_bridge=fertilizer_bridge,
            exchange_repair=exchange_repair,
            adaptive_marginal=adaptive_marginal,
            joint_farm_prefix=(
                (joint_visible_workload or joint_standing_active)
                and bool(snap.me.animals or snap.me.crops)
            ),
            # The bounded V107 ray is the finite leader action set.  Its
            # complete selected rows are recertified below by the unified
            # Stackelberg value; putting the expensive max-min inside every
            # route marginal would solve the same semantic capital set hundreds
            # of times and violate the engine deadline.
            stackelberg=False,
            recertify_stackelberg_arms=(
                stackelberg_arm_recertification or joint_standing_active
            ),
            activated_land_reinvestment=activated_land_reinvestment,
            full_service_continuation=(
                full_service_continuation or joint_standing_active
            ),
            crop_only_land_arm=crop_only_land_arm,
            robust_crop_land_gate=robust_crop_land_gate,
            certificate_cache=proposal_certificate_cache,
            paired_context=paired_context,
            stackelberg_context=stackelberg_context,
            allowed_items=(
                tuple(sorted(set(turnover_items_by_position.values())))
                if intraday_turnover and turnover_items_by_position
                else tuple(econ.CROPS) if intraday_turnover else None
            ),
            allow_land=not intraday_turnover,
        )
        columns, proposed_animals = capital_tasks(
            snap, proposed, tasks,
            positions_by_item=proposal_certificate.positions_by_item,
        )
        proposed_seeds, proposed_animals_limit, _buy_land = (
            _proposal_counts(proposed)
        )
        selection_limits = {
            **{("BUY_SEED", crop): int(qty)
               for crop, qty in proposed_seeds.items()},
            **{("BUY_ANIMAL", kind): int(qty)
               for kind, qty in proposed_animals_limit.items()},
        }
        all_tasks = list(tasks) + columns
        model = PositionedCertificateObjective(
            snap, all_tasks, fixed,
            reserve=service_reserve + hire_cost,
            phase_aligned=True,
            credit_fertilizer=fertilizer_bridge,
            paired_context=paired_context,
            certificate_cache=positioned_certificate_cache,
            semantic_certificate_cache=memoize_proposals,
            stackelberg=False,
            stackelberg_context=None,
        )
        stock = objective.planned_shed_stock(snap, plan)
        for kind, qty in proposed_animals.items():
            stock[kind] = int(stock.get(kind, 0) or 0) + int(qty)
        universe_signature = (
            tuple(tuple(order) for order in proposed),
            tuple((item, tuple(tuple(pos) for pos in positions))
                  for item, positions in sorted(
                      proposal_certificate.positions_by_item.items()
                  )),
        )
        dominated_route_reuse = bool(
            memoize_proposals and prior_all_selected
            and universe_signature == prior_universe_signature
            and router._resources_fit(
                all_tasks, stock,
                cash_budget=max(0.0, spendable - hire_cost),
                max_order_keys=purchase_slots,
                selection_limits=selection_limits,
            )
        )
        assignment = None
        if dominated_route_reuse:
            # The prior arm assigned this identical complete task universe to
            # a strict subset of the current workers.  Adding a worker cannot
            # invalidate that route.  Current cash/order limits are checked
            # above and the current reserve is still repriced by ``model``;
            # rerunning the route search could not select more than every task.
            chosen = list(all_tasks)
            # The identical prior universe already has a complete executable
            # assignment on a strict subset of these workers. Retain that
            # concrete witness instead of only retaining the selected set.
            assignment = {
                int(idx): list(worker_tasks)
                for idx, worker_tasks in prior_complete_assignment
            }
        else:
            assignment, _left = router.joint_assign(
                all_tasks,
                _units(snap, k, None, post_action=True,
                       already_projected=True),
                stock,
                cash_budget=max(0.0, spendable - hire_cost),
                max_order_keys=purchase_slots,
                deadline=None,
                refine=False,
                selection_limits=selection_limits,
                bank_outputs=bank_outputs,
                bundle_model=model,
                memoize_route_cost=True,
            )
            chosen = _selected(assignment)
        execution_counts = None
        if execution_aligned_crew or empty_farm_alignment:
            execution_counts = _projected_execution_counts(
                snap, proposed, fixed, k, bank_outputs=bank_outputs,
                source_plan=plan,
            )
            retained = []
            retained_capital = Counter()
            for task in chosen:
                if id(task) not in model.capital:
                    retained.append(task)
                    continue
                item = str(task.order_key[1])
                if retained_capital[item] < int(
                        execution_counts.get(item, 0) or 0):
                    retained.append(task)
                    retained_capital[item] += 1
            chosen = retained

        # A proposal may contain a legal BUY_LAND plus positioned assets while
        # the ordinary prize-collecting route chooses no capital column.  Keep
        # one engine-derived frontier column as a mandatory anchor, preserve
        # the incumbent ordinary work, and rerun the same route/resource solve.
        # This is opt-in because the candidate solve is intentionally stricter
        # than the historical greedy arm; it never invents an asset or a
        # position outside the current proposal certificate.
        land_frontier_repaired = False
        if (land_frontier_certificate
                and any(order and order[0] == "BUY_LAND"
                        for order in proposed)
                and not any(
                    task.kind in ("CAPITAL_CROP", "CAPITAL_ANIMAL")
                    and task.activations for task in chosen
                )
                and not (stackelberg or late_crop_gate_active
                         or joint_standing_active)):
            candidate_columns = [copy.copy(task) for task in columns]
            land_columns = [
                task for task in candidate_columns
                if any(key[0] == "BUY_LAND" for key in task.activations)
            ]
            if land_columns:
                # The closest/highest-value legal land column is a finite
                # witness. Other proposal columns remain optional and may be
                # added by the same route master if they fit.
                anchor = min(
                    land_columns,
                    key=lambda task: (
                        -float(task.value),
                        paths.dist_to_shed(tuple(task.pos)),
                        tuple(task.pos),
                        str(task.order_key),
                    ),
                )
                anchor.mandatory = True
                candidate_ordinary = []
                for task in chosen:
                    if id(task) in getattr(model, "capital", {}):
                        continue
                    retained = copy.copy(task)
                    retained.mandatory = True
                    candidate_ordinary.append(retained)
                candidate_tasks = candidate_ordinary + candidate_columns
                candidate_model = PositionedCertificateObjective(
                    snap, candidate_tasks, fixed,
                    reserve=service_reserve + hire_cost,
                    phase_aligned=True,
                    credit_fertilizer=fertilizer_bridge,
                    paired_context=paired_context,
                    certificate_cache=positioned_certificate_cache,
                    semantic_certificate_cache=memoize_proposals,
                    stackelberg=False,
                    stackelberg_context=None,
                )
                candidate_assignment, _candidate_left = router.joint_assign(
                    candidate_tasks,
                    _units(snap, k, None, post_action=True,
                           already_projected=True),
                    stock,
                    cash_budget=max(0.0, spendable - hire_cost),
                    max_order_keys=purchase_slots,
                    deadline=None,
                    refine=False,
                    selection_limits=selection_limits,
                    bank_outputs=bank_outputs,
                    bundle_model=candidate_model,
                    memoize_route_cost=True,
                )
                candidate_chosen = _selected(candidate_assignment)
                candidate_ids = {id(task) for task in candidate_chosen}
                preserves_ordinary = all(
                    id(task) in candidate_ids for task in candidate_ordinary
                )
                has_land_anchor = id(anchor) in candidate_ids
                # The public replay audit shows expansion bundled with a
                # productive animal/service column.  Keep that as a mechanism
                # check, not a date rule: a land-only crop ray can consume the
                # shared crew and cash budget without opening a near-term
                # service stream, while an animal column is independently
                # priced by the same positioned certificate below.
                has_animal_capital = any(
                    task.kind == "CAPITAL_ANIMAL"
                    and id(task) in candidate_ids
                    for task in candidate_tasks
                )
                incumbent_score = float(model.score(chosen)) - hire_cost
                candidate_score = (
                    float(candidate_model.score(candidate_chosen))
                    - hire_cost
                    if (preserves_ordinary and has_land_anchor
                        and has_animal_capital) else
                    float("-inf")
                )
                if candidate_score > incumbent_score + 1e-9:
                    chosen = candidate_chosen
                    assignment = candidate_assignment
                    model = candidate_model
                    columns = candidate_columns
                    all_tasks = candidate_tasks
                    land_frontier_repaired = True
        chosen_ids = {id(task) for task in chosen}
        if dominated_route_reuse:
            selected_current_assignment = prior_complete_assignment
        else:
            selected_current_assignment = tuple(
                (int(idx), tuple(
                    task for task in worker_tasks if id(task) in chosen_ids
                ))
                for idx, worker_tasks in sorted((assignment or {}).items())
                if any(id(task) in chosen_ids for task in worker_tasks)
            )
        if stackelberg or late_crop_gate_active or joint_standing_active:
            from whitebox import stackelberg as _stackelberg
            capital_chosen = [
                task for task in chosen if id(task) in model.capital
            ]
            positions = defaultdict(list)
            for task in capital_chosen:
                positions[task.order_key[1]].append(tuple(task.pos))
            counts = {item: len(item_positions)
                      for item, item_positions in positions.items()}
            capital_slots = sorted(
                {pos for item_positions in positions.values()
                 for pos in item_positions},
                key=lambda pos: (paths.dist_to_shed(pos), pos),
            )
            robust_cert = _stackelberg.certify_unified(
                snap, counts, capital_slots,
                reserve=service_reserve + hire_cost,
                land_cost=_activation_cost(capital_chosen),
                fixed_orders=fixed, cash_context=model.cash_context,
                positions_by_item=dict(positions),
                context=stackelberg_context,
                land_reinvestment=land_reinvestment,
                activated_land_reinvestment=activated_land_reinvestment,
                full_service_continuation=(
                    full_service_continuation or joint_standing_active
                ),
            )
            ordinary = [task for task in chosen
                        if id(task) not in model.capital]
            score = (float(model.ordinary_model.score(ordinary))
                     + (float(robust_cert.paired_value)
                        if robust_cert.feasible else float("-inf"))
                     - hire_cost)
        else:
            score = float(model.score(chosen)) - hire_cost
        capital_cash, order_keys = router._capital_usage(chosen)
        service_credit = (
            same_day_output_cash_floor(chosen)
            if cashflow_backed_service_hiring else 0.0
        )
        if cashflow_backed_service_hiring:
            # Capital remains cash-before-output: the proposal certificate
            # above retained the full service reserve plus this exact wage.
            # Only the wage may bridge against outputs banked by the selected
            # current-day routes.
            wage_cash = max(
                0.0,
                float(snap.me.money) - fixed_spend
                - max(0.0, service_reserve - service_credit),
            )
            if hire_cost > wage_cash + 1e-9:
                score = float("-inf")
        assets = _asset_orders(chosen, proposed)
        proposed_counts = {
            **{crop: int(qty) for crop, qty in proposed_seeds.items()},
            **{kind: int(qty) for kind, qty in proposed_animals_limit.items()},
        }
        selected_counts = Counter(
            task.order_key[1] for task in chosen
            if task.order_key is not None and len(task.order_key) >= 2
        )
        selected_positions = defaultdict(list)
        for task in chosen:
            if (task.order_key is not None and len(task.order_key) >= 2
                    and task.kind in ("CAPITAL_CROP", "CAPITAL_ANIMAL")):
                selected_positions[str(task.order_key[1])].append(
                    tuple(task.pos)
                )
        rows.append({
            "hires": int(k),
            "hire_cost": hire_cost,
            "service_reserve": service_reserve,
            "service_output_cash_floor": float(service_credit),
            "purchase_slots": int(purchase_slots),
            "proposed_counts": proposed_counts,
            "selected_counts": dict(selected_counts),
            "positions_by_item": {
                item: tuple(positions)
                for item, positions in sorted(selected_positions.items())
            },
            "completed_tasks": len(chosen),
            "capital_cash": float(capital_cash),
            "order_keys": len(order_keys),
            "score": score,
            "assets": assets,
            "fixed": [list(order) for order in fixed],
            "proposal_evaluations": int(getattr(
                proposal_certificate, "evaluations", 0,
            ) or 0),
            "route_reused": dominated_route_reuse,
            "land_frontier_repaired": land_frontier_repaired,
            "execution_counts": execution_counts,
            # Internal execution witness for optional strict challengers.
            # It never crosses the agent boundary; object identity lets a
            # challenger prove that none of the incumbent's selected current
            # work disappeared when extra capital was added.
            "selected_ordinary_tasks": tuple(
                task for task in chosen
                if id(task) not in getattr(model, "capital", {})
            ),
            # Full current-route witness selected by the upstream joint
            # capital/crew master. A count-preserving layout challenger may
            # move its capital columns, but it must not ask a second
            # prize-collecting solve whether those already-selected columns
            # were optional after all.
            "selected_current_assignment": selected_current_assignment,
        })
        prior_universe_signature = universe_signature
        prior_all_selected = len(chosen) == len(all_tasks)
        prior_complete_assignment = (
            selected_current_assignment if prior_all_selected else ()
        )

    prior = None
    for row in rows:
        row["marginal_vs_previous"] = (
            None if prior is None else float(row["score"] - prior)
        )
        prior = float(row["score"])
    return rows


def _late_crop_land_challenger(snap, plan, tasks, row, bank_outputs=False,
                               activate_next_land=True,
                               allow_initial_expansion=False,
                               bounded_quantity_frontier=False,
                               allow_deferred_hires=False,
                               deferred_capital_option=False,
                               deferred_capital_full_continuation=False,
                               close_empty_deferred_baseline=False,
                               deferred_standing_service_horizon=False,
                               bounded_first_output_only=False,
                               suppress_uncommitted_rotation=False,
                               deferred_execution_witness=False,
                               staged_opponent_reinvestment=False,
                               staged_response_cache=None,
                               complete_opponent_response_products=False,
                               robust_own_standing_realisation=False,
                               staged_opponent_land_reinvestment=False,
                               staged_opponent_mixed_reinvestment=False):
    """Add one incremental crop ray only when it strictly beats ``row``.

    The default arm pays for and uses only the next public quadrant.  The
    current-land arm instead uses only already-unlocked empty positions, so a
    harvested one-shot crop can be rotated without pretending to buy land.
    Both preserve every positioned incumbent purchase, explicitly price any
    current work displaced by the route, use the largest crew compatible with
    the ten-order queue, and compare baseline/challenger on one standing-output
    book and one candidate-complete paid response set.  The opt-in deferred
    current-land arm is stricter: its extra hand must preserve every incumbent
    ordinary task. Losing arms return ``row`` exactly.
    """
    if (activate_next_land and len(snap.me.unlocked) < 2
            and not allow_initial_expansion):
        return row
    if (activate_next_land
            and not econ.can_buy_land(len(snap.me.unlocked))):
        return row
    assets = [list(order) for order in row.get("assets", ())]
    if (activate_next_land
            and any(order and order[0] == "BUY_LAND" for order in assets)):
        return row
    owned_extra = len(snap.me.unlocked) - 1
    if (activate_next_land
            and not econ.can_buy_land(len(snap.me.unlocked))):
        return row

    from whitebox import cashflow as _cashflow
    from whitebox import stackelberg as _stackelberg

    fixed = [list(order) for order in row.get("fixed", ())]
    service_reserve = max(0.0, float(row.get("service_reserve", 0.0)))
    fixed_spend = float(_fixed_spend(snap, fixed))
    base_positions = {
        str(item): [tuple(pos) for pos in positions]
        for item, positions in row.get("positions_by_item", {}).items()
        if positions
    }
    base_counts = {item: len(positions)
                   for item, positions in base_positions.items()}
    base_order_items = set(base_counts)
    incumbent_ordinary_tasks = list(
        row.get("selected_ordinary_tasks", ())
    )
    incumbent_ordinary_value = float(
        objective.TaskBundleObjective(
            snap, incumbent_ordinary_tasks,
        ).score(incumbent_ordinary_tasks)
    )
    blocked = {tuple(task.pos) for task in tasks}
    deferred_blocked = tuple(blocked) if deferred_execution_witness else ()
    expanded = _cashflow._available_slots(
        snap, include_next_land=activate_next_land, reserve_inventory=True,
        blocked_positions=blocked,
    )
    unlocked = set(snap.me.unlocked)
    target_slots = [
        tuple(pos) for pos in expanded
        if ((paths.quadrant_of(pos[0], pos[1], snap.board) not in unlocked)
            == bool(activate_next_land))
    ]
    if not target_slots:
        return row
    field = "late_land" if activate_next_land else "late_fill"

    candidates = []
    audit = []

    # The historical online arm solved every integer quantity under a complete
    # same-product follower response book.  That is an exact offline audit, but
    # it is not a bounded action-time algorithm: one live day generated 141
    # unified certificates and exhausted Kaggle's cumulative overage.  The
    # opt-in online frontier below is wholly rule-derived.  For every legal
    # crop it first partitions quantities into contiguous cash/service-feasible
    # regimes.  From each regime it retains the two boundaries, its exact
    # standalone-profit maximizer, and that maximizer's predecessor.  Every
    # public crop direction remains in the action set, while dominated interior
    # quantities do not receive an expensive adversarial certificate.  The
    # screen can omit a better quantity, but can never validate an action:
    # every emitted purchase still passes the unchanged unified cash/route/
    # response certificate and the routed recertification below.
    cash_context = None
    if bounded_quantity_frontier:
        cash_context = (
            *_cashflow._fixed_commitment(snap, fixed),
            _cashflow._reserved_book(snap),
        )
    screened = {}
    if bounded_quantity_frontier:
        for crop in sorted(econ.CROPS):
            if int(snap.step) > int(econ.SEED_DEADLINE[crop]):
                continue
            nonhire_orders = (len(fixed) + len(base_order_items)
                              + int(bool(activate_next_land))
                              + int(crop not in base_order_items))
            crew_room = min(
                max(0, hiring.MAX_HANDS - len(snap.me.hands)),
                max(0, econ.MAX_ORDERS - nonhire_orders),
            )
            k = min(int(row.get("hires", 0)), int(crew_room))
            hire_cost = float(econ.hire_block_cost(
                snap.me.hires_today, k,
            ))
            land_cost = (float(econ.LAND_PRICES[owned_extra])
                         if activate_next_land else 0.0)
            base_asset_cost = sum(
                (float(econ.CROPS[item]["seed"])
                 if item in econ.CROPS
                 else float(econ.ANIMALS[item]["cost"])) * int(quantity)
                for item, quantity in base_counts.items()
            )
            affordable = max(
                0.0, float(snap.me.money) - fixed_spend - service_reserve
                - hire_cost - land_cost - base_asset_cost,
            )
            quantity_cap = min(
                len(target_slots),
                int(affordable // float(econ.CROPS[crop]["seed"])),
            )
            if quantity_cap <= 0:
                continue
            reserve = service_reserve + hire_cost
            crop_arms = []
            for quantity in range(1, quantity_cap + 1):
                trial_positions = {
                    item: list(positions)
                    for item, positions in base_positions.items()
                }
                trial_positions.setdefault(crop, []).extend(
                    target_slots[:quantity]
                )
                trial_counts = {
                    item: len(positions)
                    for item, positions in trial_positions.items()
                    if positions
                }
                trial_slots = sorted(
                    {tuple(pos) for positions in trial_positions.values()
                     for pos in positions},
                    key=lambda pos: (paths.dist_to_shed(pos), pos),
                )
                endpoints = []
                for full in ((False,) if bounded_first_output_only
                             else (False, True)):
                    endpoint = _stackelberg._endpoint(
                        snap, trial_counts, trial_slots, reserve,
                        land_cost, fixed, cash_context, trial_positions,
                        full,
                        standing_service_horizon=(
                            _stackelberg._deferred_first_output_horizon(snap)
                            if deferred_standing_service_horizon else None
                        ),
                        two_phase_future_hires=not activate_next_land,
                    )
                    if endpoint is None:
                        continue
                    cert, own_cost = endpoint
                    surplus = (
                        float(_stackelberg._standalone_schedule_revenue(
                            snap, cert.outputs_by_day,
                        )) - float(own_cost)
                    )
                    endpoints.append((
                        surplus, float(cert.final_cash),
                        -float(own_cost), -int(full),
                    ))
                if not endpoints:
                    # Fibonacci future-hire blocks make feasibility genuinely
                    # non-monotone in quantity, so later integers remain live.
                    continue
                endpoint_key = max(endpoints)
                crop_arms.append((
                    int(quantity), float(endpoint_key[0]),
                ))
            if not crop_arms:
                audit.append((
                    crop, "screen_no_feasible_endpoint", int(k),
                    int(quantity_cap), 0.0, 0.0,
                ))
                continue
            regimes = []
            current_regime = []
            for arm in crop_arms:
                if (current_regime
                        and int(arm[0]) != int(current_regime[-1][0]) + 1):
                    regimes.append(tuple(current_regime))
                    current_regime = []
                current_regime.append(arm)
            if current_regime:
                regimes.append(tuple(current_regime))
            quantities = set()
            for regime in regimes:
                quantities.add(int(regime[0][0]))
                quantities.add(int(regime[-1][0]))
                best_arm = max(
                    regime, key=lambda arm: (arm[1], -arm[0]),
                )
                quantities.add(int(best_arm[0]))
                if int(best_arm[0]) > int(regime[0][0]):
                    quantities.add(int(best_arm[0]) - 1)
            quantity, surplus = max(
                crop_arms, key=lambda arm: (arm[1], -arm[0]),
            )
            first_output_days = max(
                1, int(econ.CROPS[crop]["first_yield_day"]),
            )
            screened[crop] = {
                "quantity": int(quantity),
                "quantities": tuple(sorted(quantities)),
                "quantity_cap": int(quantity_cap),
                "surplus": float(surplus),
                "velocity": float(surplus) / float(first_output_days),
            }
        crops = tuple(sorted(screened))
    else:
        crops = tuple(sorted(econ.CROPS))

    for crop in crops:
        if int(snap.step) > int(econ.SEED_DEADLINE[crop]):
            continue
        # Keep the incumbent asset-order universe, then reserve one key for
        # BUY_LAND and one only if this crop is not already an incumbent key.
        nonhire_orders = (len(fixed) + len(base_order_items)
                          + int(bool(activate_next_land))
                          + int(crop not in base_order_items))
        crew_room = min(
            max(0, hiring.MAX_HANDS - len(snap.me.hands)),
            max(0, econ.MAX_ORDERS - nonhire_orders),
        )
        k = min(int(row.get("hires", 0)), int(crew_room))
        hire_cost = float(econ.hire_block_cost(snap.me.hires_today, k))
        if (fixed_spend + service_reserve + hire_cost
                > float(snap.me.money) + 1e-9):
            continue

        all_response_products = (
            tuple(econ.CROPS) + tuple(sorted({
                str(spec["product"])
                for spec in econ.ANIMALS.values()
            }))
        )
        response_products = (
            all_response_products
            if (deferred_capital_option
                or complete_opponent_response_products)
            else (crop,)
        )
        context = _stackelberg.make_context(
            snap, full_response_continuation=True,
            include_own_standing_book=True,
            candidate_response_products=response_products,
            staged_response_reinvestment=staged_opponent_reinvestment,
            staged_response_cache=staged_response_cache,
            robust_own_standing_realisation=(
                robust_own_standing_realisation
            ),
            staged_response_land_reinvestment=(
                staged_opponent_land_reinvestment
            ),
            staged_response_mixed_reinvestment=(
                staged_opponent_mixed_reinvestment
            ),
        )
        reserve = service_reserve + hire_cost
        baseline = _stackelberg.certify_unified(
            snap, base_counts,
            sorted({pos for positions in base_positions.values()
                    for pos in positions},
                   key=lambda pos: (paths.dist_to_shed(pos), pos)),
            reserve=service_reserve + float(row.get("hire_cost", 0.0)),
            land_cost=0.0, fixed_orders=fixed,
            positions_by_item=base_positions, context=context,
            two_phase_future_hires=not activate_next_land,
            rotation_reinvestment=(not activate_next_land
                                   and not suppress_uncommitted_rotation),
            deferred_capital_reinvestment=deferred_capital_option,
            deferred_capital_full_continuation=(
                deferred_capital_full_continuation
            ),
            close_empty_deferred_baseline=close_empty_deferred_baseline,
            deferred_standing_service_horizon=(
                deferred_standing_service_horizon
            ),
            bounded_first_output_only=bounded_first_output_only,
            deferred_blocked_positions=deferred_blocked,
            cash_context=cash_context,
        )
        if not baseline.feasible:
            audit.append((crop, "baseline_" + str(baseline.reason),
                          int(k), 0,
                          float(getattr(baseline, "paired_value", 0.0)),
                          0.0))
            continue
        baseline_game = (float(baseline.paired_value)
                         - float(row.get("hire_cost", 0.0)))
        land_cost = (float(econ.LAND_PRICES[owned_extra])
                     if activate_next_land else 0.0)
        base_asset_cost = sum(
            (float(econ.CROPS[item]["seed"])
             if item in econ.CROPS else float(econ.ANIMALS[item]["cost"]))
            * int(quantity)
            for item, quantity in base_counts.items()
        )
        affordable = max(
            0.0, float(snap.me.money) - fixed_spend - service_reserve
            - hire_cost - land_cost - base_asset_cost,
        )
        quantity_cap = min(
            len(target_slots),
            int(affordable // float(econ.CROPS[crop]["seed"])),
        )
        quantity_arms = []
        failure_reasons = []
        quantities = (
            tuple(screened[crop]["quantities"])
            if bounded_quantity_frontier else range(1, quantity_cap + 1)
        )
        for quantity in quantities:
            trial_positions = {
                item: list(positions)
                for item, positions in base_positions.items()
            }
            trial_positions.setdefault(crop, []).extend(
                target_slots[:quantity]
            )
            trial_counts = {
                item: len(positions)
                for item, positions in trial_positions.items() if positions
            }
            trial_slots = sorted(
                {tuple(pos) for positions in trial_positions.values()
                 for pos in positions},
                key=lambda pos: (paths.dist_to_shed(pos), pos),
            )
            trial = _stackelberg.certify_unified(
                snap, trial_counts, trial_slots, reserve=reserve,
                land_cost=land_cost, fixed_orders=fixed,
                positions_by_item=trial_positions, context=context,
                activated_land_reinvestment=activate_next_land,
                two_phase_future_hires=not activate_next_land,
                rotation_reinvestment=(not activate_next_land
                                       and not suppress_uncommitted_rotation),
                deferred_capital_reinvestment=deferred_capital_option,
                deferred_capital_full_continuation=(
                    deferred_capital_full_continuation
                ),
                close_empty_deferred_baseline=close_empty_deferred_baseline,
                deferred_standing_service_horizon=(
                    deferred_standing_service_horizon
                ),
                bounded_first_output_only=bounded_first_output_only,
                deferred_blocked_positions=deferred_blocked,
                cash_context=cash_context,
            )
            if not trial.feasible:
                failure_reasons.append(str(trial.reason))
                continue
            trial_game = float(trial.paired_value) - hire_cost
            quantity_arms.append((
                trial_game, -float(trial.upfront_spend), -quantity,
                trial, trial_positions, trial_counts,
            ))
        if not quantity_arms:
            reason = (failure_reasons[0] if failure_reasons
                      and len(set(failure_reasons)) == 1
                      else "no_feasible_quantity")
            audit.append((crop, "challenger_" + reason, int(k),
                          int(quantity_cap), baseline_game, 0.0))
            continue
        (challenger_game, _spend_key, _quantity_key, challenger,
         combined_positions, combined_counts) = max(quantity_arms)
        target_slot_set = set(target_slots)
        crop_positions = [tuple(pos)
                          for pos in combined_positions.get(crop, ())
                          if tuple(pos) in target_slot_set]
        if challenger_game <= baseline_game + 1e-9:
            audit.append((crop, "robust_value", int(k),
                          len(crop_positions), baseline_game,
                          challenger_game))
            continue

        proposed = _positioned_assets(assets, combined_positions)
        if activate_next_land:
            proposed.append(["BUY_LAND"])
        columns, proposed_animals = capital_tasks(
            snap, proposed, tasks, positions_by_item=combined_positions,
        )
        if len(columns) != sum(combined_counts.values()):
            audit.append((crop, "positioned_columns", int(k),
                          len(crop_positions), baseline_game,
                          challenger_game))
            continue
        incumbent_tasks = []
        for task in row.get("selected_ordinary_tasks", ()):
            retained = copy.copy(task)
            retained.mandatory = True
            incumbent_tasks.append(retained)
        routed_columns = []
        for task in columns:
            routed = copy.copy(task)
            # ``combined_positions`` is the finite crop ray that already won
            # the same-scenario robust comparison above.  Re-ranking those
            # columns by their old standalone task values can select zero new
            # positions, making an economically positive BUY_LAND action
            # unreachable (a public-state audit exposed exactly ``n0`` here).
            # Route the selected action as an indivisible
            # candidate, then price any displaced ordinary work and recertify
            # the actually executable bundle below.  A route failure still
            # rejects the challenger; no value is awarded for coverage.
            routed.mandatory = True
            routed_columns.append(routed)
        all_tasks = incumbent_tasks + routed_columns
        stock = objective.planned_shed_stock(snap, plan)
        for kind, qty in proposed_animals.items():
            stock[kind] = int(stock.get(kind, 0) or 0) + int(qty)
        limits = {
            (("BUY_SEED", item) if item in econ.CROPS
             else ("BUY_ANIMAL", item)): int(qty)
            for item, qty in combined_counts.items()
        }
        base_position_pairs = {
            (item, tuple(pos))
            for item, positions in base_positions.items()
            for pos in positions
        }
        baseline_total = baseline_game + incumbent_ordinary_value
        deferred_cap = (econ.MAX_ORDERS if allow_deferred_hires else 0)
        route_arms = []
        route_failures = []
        for deferred in range(deferred_cap + 1):
            deferred_cost = float(econ.hire_block_cost(
                snap.me.hires_today + k, deferred,
            ))
            if (fixed_spend + service_reserve + hire_cost + deferred_cost
                    > float(snap.me.money) + 1e-9):
                break
            units = _units(
                snap, k, None, post_action=True, already_projected=True,
            )
            if deferred:
                all_spawns = hiring.spawn_positions(snap, k + deferred, None)
                first_new = len(units)
                units.extend(
                    Unit(first_new + index, tuple(pos), snap.hour + 2)
                    for index, pos in enumerate(all_spawns[k:])
                )
            assignment, _left = router.joint_assign(
                all_tasks, units, stock,
                cash_budget=max(
                    0.0, float(snap.me.money) - fixed_spend
                    - service_reserve - hire_cost - deferred_cost,
                ),
                max_order_keys=econ.MAX_ORDERS - len(fixed) - k,
                deadline=None, refine=False, selection_limits=limits,
                bank_outputs=bank_outputs, bundle_model=None,
                memoize_route_cost=True,
            )
            chosen = _selected(assignment)
            chosen_ids = {id(task) for task in chosen}
            routed_positions = defaultdict(list)
            for task in chosen:
                if (task.kind in ("CAPITAL_CROP", "CAPITAL_ANIMAL")
                        and task.order_key is not None
                        and len(task.order_key) >= 2):
                    routed_positions[str(task.order_key[1])].append(
                        tuple(task.pos)
                    )
            routed_position_pairs = {
                (item, tuple(pos))
                for item, positions in routed_positions.items()
                for pos in positions
            }
            routed_new_positions = [
                tuple(pos) for pos in routed_positions.get(crop, ())
                if tuple(pos) in target_slot_set
            ]
            missing_ordinary = sum(
                id(task) not in chosen_ids for task in incumbent_tasks
            )
            missing_base = len(base_position_pairs - routed_position_pairs)
            if ((allow_deferred_hires and missing_ordinary) or missing_base
                    or not routed_new_positions):
                route_failures.append(
                    f"d{deferred}_o{missing_ordinary}_"
                    f"b{missing_base}_n{len(routed_new_positions)}"
                )
                continue
            routed_positions = {
                item: list(positions)
                for item, positions in routed_positions.items() if positions
            }
            routed_counts = {
                item: len(positions)
                for item, positions in routed_positions.items()
            }
            routed_slots = sorted(
                {tuple(pos) for positions in routed_positions.values()
                 for pos in positions},
                key=lambda pos: (paths.dist_to_shed(pos), pos),
            )
            routed_ordinary = [
                task for task in chosen
                if task.kind not in ("CAPITAL_CROP", "CAPITAL_ANIMAL")
            ]
            routed_cert = _stackelberg.certify_unified(
                snap, routed_counts, routed_slots,
                reserve=service_reserve + hire_cost + deferred_cost,
                land_cost=land_cost, fixed_orders=fixed,
                positions_by_item=routed_positions, context=context,
                activated_land_reinvestment=activate_next_land,
                two_phase_future_hires=not activate_next_land,
                rotation_reinvestment=(not activate_next_land
                                       and not suppress_uncommitted_rotation),
                deferred_capital_reinvestment=deferred_capital_option,
                deferred_capital_full_continuation=(
                    deferred_capital_full_continuation
                ),
                close_empty_deferred_baseline=close_empty_deferred_baseline,
                deferred_standing_service_horizon=(
                    deferred_standing_service_horizon
                ),
                bounded_first_output_only=bounded_first_output_only,
                deferred_blocked_positions=(
                    tuple(tuple(task.pos) for task in routed_ordinary)
                    if deferred_execution_witness else ()
                ),
                cash_context=cash_context,
            )
            if not routed_cert.feasible:
                route_failures.append(
                    f"d{deferred}_{routed_cert.reason}"
                )
                continue
            routed_game = (float(routed_cert.paired_value)
                           - hire_cost - deferred_cost)
            routed_ordinary_value = float(
                objective.TaskBundleObjective(
                    snap, routed_ordinary,
                ).score(routed_ordinary)
            )
            routed_total = routed_game + routed_ordinary_value
            route_arms.append((
                routed_total, -deferred_cost, -deferred,
                deferred, deferred_cost, chosen, routed_positions,
                routed_counts, routed_new_positions, routed_ordinary,
                routed_ordinary_value, routed_cert,
            ))
        if not route_arms:
            reason = ("route_preservation_" + route_failures[0]
                      if route_failures else "route_preservation")
            audit.append((crop, reason, int(k), len(crop_positions),
                          baseline_game, challenger_game))
            continue
        (routed_total, _deferred_cost_key, _deferred_key, deferred,
         deferred_cost, chosen, routed_positions, routed_counts,
         routed_new_positions, routed_ordinary,
         routed_ordinary_value, routed_cert) = max(route_arms)
        if routed_total <= baseline_total + 1e-9:
            audit.append((crop, f"routed_robust_value_d{deferred}", int(k),
                          len(routed_new_positions), baseline_total,
                          routed_total))
            continue
        candidate = dict(row)
        candidate.update({
            "hires": int(k),
            "hire_cost": hire_cost,
            field + "_deferred_hires": int(deferred),
            field + "_deferred_hire_cost": float(deferred_cost),
            "positions_by_item": {
                item: tuple(positions)
                for item, positions in sorted(routed_positions.items())
            },
            "selected_counts": dict(routed_counts),
            "assets": _asset_orders(chosen, proposed),
            "score": (float(row.get("score", 0.0))
                      + routed_total - baseline_total),
            field + "_crop": crop,
            field + "_quantity": len(routed_new_positions),
            field + "_before_value": baseline_total,
            field + "_after_value": routed_total,
            field + "_response_count": len(context.get("responses", ())),
            field + "_preserved_ordinary_tasks": len(routed_ordinary),
            field + "_workers_by_day": {
                int(day): int(workers) for day, workers
                in sorted(routed_cert.workers_by_day.items())
            },
            field + "_hire_phases_by_day": {
                int(day): tuple(int(qty) for qty in phases)
                for day, phases
                in sorted(routed_cert.hire_phases_by_day.items())
            },
            field + "_execution_routes_by_day": {
                int(day): tuple(routes) for day, routes in sorted(
                    routed_cert.selected_execution_routes_by_day.items()
                )
            },
            field + "_execution_hire_phases_by_day": {
                int(day): tuple(int(qty) for qty in phases)
                for day, phases in sorted(
                    routed_cert.selected_execution_hire_phases_by_day.items()
                )
            },
            field + "_reinvestment_order": tuple(
                routed_cert.selected_reinvestment_order
            ),
            field + "_reinvestment_positions_by_item": {
                str(item): tuple(tuple(pos) for pos in positions)
                for item, positions in sorted(
                    routed_cert.selected_reinvestment_positions_by_item.items()
                )
            },
            field + "_selected_reinvestment": str(
                routed_cert.selected_reinvestment
            ),
            field + "_worst_response": str(
                routed_cert.selected_worst_response
            ),
            field + "_dropped_ordinary_value": (
                incumbent_ordinary_value - routed_ordinary_value
            ),
            "selected_ordinary_tasks": tuple(
                task for task in routed_ordinary
            ),
        })
        candidates.append(candidate)
        audit.append((crop, "accepted", int(k),
                      len(routed_new_positions), baseline_total,
                      routed_total))

    if not candidates:
        audited = dict(row)
        audited[field + "_audit"] = tuple(audit)
        return audited
    winner = max(candidates, key=lambda candidate: (
        float(candidate[field + "_after_value"]),
        -float(candidate["hire_cost"]),
        -int(candidate[field + "_quantity"]),
        str(candidate[field + "_crop"]),
    ))
    winner[field + "_audit"] = tuple(audit)
    return winner


def _productive_shed_relocation_challenger(snap, plan, tasks, row,
                                            bank_outputs=False):
    """Relocate selected new assets only when unified game value rises.

    The incumbent asset multiset, crew, land, market orders and ordinary work
    are immutable. Candidate layouts come from public service frequency and
    Manhattan geometry; today's route and the finite paid-response value must
    both certify. Losing arms return the incumbent object unchanged.
    """
    base_positions = {
        str(item): tuple(tuple(pos) for pos in positions)
        for item, positions in row.get("positions_by_item", {}).items()
        if positions
    }
    if not base_positions:
        return row
    assets = [list(order) for order in row.get("assets", ())]
    fixed = [list(order) for order in row.get("fixed", ())]
    hires = int(row.get("hires", 0) or 0)
    hire_cost = float(row.get("hire_cost", 0.0) or 0.0)
    service_reserve = max(0.0, float(row.get("service_reserve", 0.0) or 0.0))
    layouts = list(_productive_shed_layouts(
        snap, base_positions, assets,
        blocked={tuple(task.pos) for task in tasks},
    ))
    if not layouts:
        return row

    from whitebox import stackelberg as _stackelberg
    response_products = tuple(econ.CROPS) + tuple(sorted({
        str(spec["product"]) for spec in econ.ANIMALS.values()
    }))
    context = _stackelberg.make_context(
        snap, full_response_continuation=True,
        include_own_standing_book=True,
        candidate_response_products=response_products,
    )
    counts = {item: len(positions)
              for item, positions in base_positions.items()}
    base_slots = sorted(
        {pos for positions in base_positions.values() for pos in positions},
        key=lambda pos: (paths.dist_to_shed(pos), pos),
    )
    has_land = any(order and order[0] == "BUY_LAND" for order in assets)
    land_cost = (
        float(econ.LAND_PRICES[len(snap.me.unlocked) - 1])
        if has_land and 0 <= len(snap.me.unlocked) - 1 < len(econ.LAND_PRICES)
        else 0.0
    )
    reserve = service_reserve + hire_cost
    baseline = _stackelberg.certify_unified(
        snap, counts, base_slots, reserve=reserve, land_cost=land_cost,
        fixed_orders=fixed, positions_by_item=base_positions,
        context=context, activated_land_reinvestment=has_land,
    )
    if not baseline.feasible:
        return row
    baseline_game = float(baseline.paired_value) - hire_cost
    incumbent_ordinary = list(row.get("selected_ordinary_tasks", ()))
    relocation_snap = copy.copy(snap)
    relocation_snap.allow_productive_shed_tiles = True
    fixed_spend = float(_fixed_spend(snap, fixed))
    candidates = []
    audit = []

    for layout in layouts:
        if {item: len(positions) for item, positions in layout.items()} != counts:
            audit.append(("counts", baseline_game, float("-inf")))
            continue
        proposed = _positioned_assets(assets, layout)
        columns, proposed_animals = capital_tasks(
            relocation_snap, proposed, tasks, positions_by_item=layout,
        )
        if len(columns) != sum(counts.values()):
            audit.append(("positioned_columns", baseline_game, float("-inf")))
            continue
        routed_tasks = []
        for task in incumbent_ordinary + columns:
            routed = copy.copy(task)
            routed.mandatory = True
            routed_tasks.append(routed)
        stock = objective.planned_shed_stock(snap, plan)
        for kind, quantity in proposed_animals.items():
            stock[kind] = int(stock.get(kind, 0) or 0) + int(quantity)
        limits = {
            (("BUY_SEED", item) if item in econ.CROPS
             else ("BUY_ANIMAL", item)): int(quantity)
            for item, quantity in counts.items()
        }
        assignment, _left = router.joint_assign(
            routed_tasks,
            _units(snap, hires, None, post_action=True,
                   already_projected=True),
            stock,
            cash_budget=max(
                0.0, float(snap.me.money) - fixed_spend - reserve,
            ),
            max_order_keys=max(0, econ.MAX_ORDERS - len(fixed) - hires),
            deadline=None, refine=False, selection_limits=limits,
            bank_outputs=bank_outputs, bundle_model=None,
            memoize_route_cost=True,
        )
        chosen = _selected(assignment)
        if len({id(task) for task in chosen}) != len(routed_tasks):
            audit.append(("current_route", baseline_game, float("-inf")))
            continue
        slots = sorted(
            {pos for positions in layout.values() for pos in positions},
            key=lambda pos: (paths.dist_to_shed(pos), pos),
        )
        cert = _stackelberg.certify_unified(
            snap, counts, slots, reserve=reserve, land_cost=land_cost,
            fixed_orders=fixed, positions_by_item=layout,
            context=context, activated_land_reinvestment=has_land,
        )
        if not cert.feasible:
            audit.append((str(cert.reason), baseline_game, float("-inf")))
            continue
        game = float(cert.paired_value) - hire_cost
        central = sum(tuple(pos) in paths.SHED_SET
                      for positions in layout.values() for pos in positions)
        audit.append((f"central_{central}", baseline_game, game))
        if game > baseline_game + 1e-9:
            candidates.append((
                game, float(cert.final_cash), central, layout, cert,
            ))
    if not candidates:
        return row
    game, _cash, central, layout, cert = max(
        candidates,
        key=lambda arm: (arm[0], arm[1], arm[2],
                         tuple(sorted(arm[3].items()))),
    )
    winner = dict(row)
    winner.update({
        "positions_by_item": {
            item: tuple(positions) for item, positions in sorted(layout.items())
        },
        "assets": _positioned_assets(assets, layout),
        "score": float(row.get("score", 0.0)) + game - baseline_game,
        "spatial_relocation_before_value": baseline_game,
        "spatial_relocation_after_value": game,
        "spatial_relocation_central_tiles": int(central),
        "spatial_relocation_response_count": len(context.get("responses", ())),
        "spatial_relocation_workers_by_day": {
            int(day): int(workers)
            for day, workers in sorted(cert.workers_by_day.items())
        },
        "spatial_relocation_audit": tuple(audit),
    })
    return winner


def _certificate_route_profile(cert):
    """Per-day (workers, physical turns) of the selected executable witness."""
    from whitebox import cashflow as _cashflow

    routes_by_day = (cert.selected_execution_routes_by_day
                     or cert.routes_by_day)
    return {
        int(day): (
            len(routes),
            sum(_cashflow._shared_route_cost(route) for route in routes),
        )
        for day, routes in sorted(routes_by_day.items())
    }


def _positioned_full_service_route_profile(snap, positioned):
    """Exact dated route profile for standing plus one positioned batch.

    Unlike the service-route ordering signature, this proof includes every
    crop and animal in the proposed batch. It is used only as a relative
    physical fallback when the absolute Stackelberg endpoint is undefined for
    both layouts. Counts, outputs and feed quantities are coordinate-
    independent; only the public Manhattan route geometry changes.
    """
    costs_by_day = _positioned_full_service_route_costs(snap, positioned)
    if costs_by_day is None:
        return None
    return {
        int(day): (len(costs), sum(costs))
        for day, costs in sorted(costs_by_day.items())
    }


def _route_profile_dominates(baseline, candidate):
    """Pareto test with no trade-off coefficient between labour and travel."""
    strict = False
    for day in sorted(set(baseline) | set(candidate)):
        before_workers, before_turns = baseline.get(day, (0, 0))
        after_workers, after_turns = candidate.get(day, (0, 0))
        if (after_workers > before_workers
                or after_turns > before_turns):
            return False
        strict = strict or (after_workers < before_workers
                            or after_turns < before_turns)
    return strict


def _service_layout_lifecycle_dominates(base_current, current,
                                        baseline_future, future):
    """Pareto test over one executable current route plus future service.

    Placement is a durable decision. A two-turn build detour today may remove
    two travel turns on every remaining service day, so requiring today's
    *aggregate* turns to weakly improve deletes physically superior layouts.
    No conversion weight is needed: every entry is an engine action. Current
    worker count and longest route may not increase, every future day's worker
    and turn requirements must weakly improve, and aggregate lifecycle workers
    and turns must weakly improve with at least one strict physical inequality.
    """
    if (int(current[0]) > int(base_current[0])
            or int(current[2]) > int(base_current[2])):
        return False
    days = set(baseline_future) | set(future)
    if any(
            int(future.get(day, (0, 0))[0])
            > int(baseline_future.get(day, (0, 0))[0])
            or int(future.get(day, (0, 0))[1])
            > int(baseline_future.get(day, (0, 0))[1])
            for day in days):
        return False
    before_workers = int(base_current[0]) + sum(
        int(baseline_future.get(day, (0, 0))[0]) for day in days
    )
    after_workers = int(current[0]) + sum(
        int(future.get(day, (0, 0))[0]) for day in days
    )
    before_turns = int(base_current[1]) + sum(
        int(baseline_future.get(day, (0, 0))[1]) for day in days
    )
    after_turns = int(current[1]) + sum(
        int(future.get(day, (0, 0))[1]) for day in days
    )
    if after_workers > before_workers or after_turns > before_turns:
        return False
    return bool(
        after_workers < before_workers
        or after_turns < before_turns
        or int(current[2]) < int(base_current[2])
    )


def _current_positioned_route_profile(snap, plan, tasks, row, layout,
                                      bank_outputs=False):
    """Re-route the unchanged mandatory current-day work on one layout."""
    assets = [list(order) for order in row.get("assets", ())]
    fixed = [list(order) for order in row.get("fixed", ())]
    hires = int(row.get("hires", 0) or 0)
    hire_cost = float(row.get("hire_cost", 0.0) or 0.0)
    service_reserve = max(
        0.0, float(row.get("service_reserve", 0.0) or 0.0),
    )
    counts = {
        str(item): len(positions)
        for item, positions in layout.items() if positions
    }
    proposed = _positioned_assets(assets, layout)
    columns, proposed_animals = capital_tasks(
        snap, proposed, tasks, positions_by_item=layout,
    )
    if len(columns) != sum(counts.values()):
        return None

    # Preserve the priority flags used by the executable daily router. The
    # former proof changed every optional task to mandatory before the greedy
    # packing pass. That changed its deterministic order and could make a
    # genuinely complete 46/46 route appear infeasible at 44/46. The identity
    # check below already makes full retention a hard condition.
    routed_tasks = [
        copy.copy(task)
        for task in list(row.get("selected_ordinary_tasks", ())) + columns
    ]
    stock = objective.planned_shed_stock(snap, plan)
    for kind, quantity in proposed_animals.items():
        stock[kind] = int(stock.get(kind, 0) or 0) + int(quantity)
    limits = {
        (("BUY_SEED", item) if item in econ.CROPS
         else ("BUY_ANIMAL", item)): int(quantity)
        for item, quantity in counts.items()
    }
    units = _units(
        snap, hires, None, post_action=True, already_projected=True,
    )
    assignment, _left = router.joint_assign(
        routed_tasks, units, stock,
        cash_budget=max(
            0.0, float(snap.me.money) - _fixed_spend(snap, fixed)
            - service_reserve - hire_cost,
        ),
        max_order_keys=max(0, econ.MAX_ORDERS - len(fixed) - hires),
        deadline=None, refine=False, selection_limits=limits,
        bank_outputs=bank_outputs, bundle_model=None,
        memoize_route_cost=True,
    )
    chosen = _selected(assignment)
    if len({id(task) for task in chosen}) != len(routed_tasks):
        return None
    by_idx = {unit.idx: unit for unit in units}
    costs = [
        router.route_cost(
            by_idx[idx], worker_tasks, exact=True,
            bank_outputs=bank_outputs,
        )
        for idx, worker_tasks in assignment.items() if worker_tasks
    ]
    return (len(costs), sum(costs), max(costs) if costs else 0)


def _robust_schedule_value(snap, context, outputs_by_day, cost):
    """Relative max-min margin of one named, paid output schedule."""
    from whitebox import stackelberg as _stackelberg

    responses = tuple(
        context.get("responses") or (_stackelberg.Response("NO_RESPONSE"),)
    )
    worst = min(
        _stackelberg._context_response_margin(
            snap, outputs_by_day, float(cost), response, context,
        )
        for response in responses
    )
    return float(worst) - float(context.get("baseline_robust", 0.0))


def _standing_crop_release_anchors(snap):
    from whitebox import cashflow as _cashflow
    """Public one-shot crop tiles grouped by their rule-derived release day."""
    anchors = defaultdict(list)
    for pos, tile in sorted(snap.me.crops.items()):
        crop = str(tile.get("crop", ""))
        spec = econ.CROPS.get(crop)
        if spec is None or bool(spec["ongoing"]):
            continue
        held = max(0, int(tile.get("yield_units", 0) or 0))
        events = objective._crop_event_days(tile, crop, int(snap.day))
        if held:
            release_day = int(snap.day) + 1
        elif events:
            release_day = int(events[0]) + 1
        else:
            continue
        if int(snap.day) < release_day <= int(_cashflow.LAST_DAY):
            anchors[int(release_day)].append((str(crop), tuple(pos)))
    return {
        int(day): tuple(entries)
        for day, entries in sorted(anchors.items())
    }


def _land_turnover_option_challenger(snap, plan, tasks, row,
                                     bank_outputs=False,
                                     bounded_quantity_frontier=False):
    """Compare immediate land with waiting for certified standing-crop release.

    This is a two-stage public-rule Stackelberg action, not a date heuristic.
    It applies only when every newly selected asset needs the newly activated
    quadrant, so removing BUY_LAND removes no currently usable investment.
    Today's crew and ordinary work are held fixed.  The wait arm may reinvest
    only after a named one-shot crop has produced cash and released its exact
    tile; every future purchase, feed bill, market key and route is certified.
    Immediate and delayed schedules face the same finite paid response set.
    """

    seat = getattr(snap, "seat", None)
    exercise_key = (
        (int(seat), len(snap.me.unlocked)) if seat is not None else None
    )
    commitment = (
        _LAND_TURNOVER_COMMITMENTS.get(int(seat))
        if seat is not None else None
    )
    if (commitment is not None
            and int(commitment.get("unlocked_count", -1))
            != len(snap.me.unlocked)):
        # A successful purchase (or any other public ownership change) ends
        # the retained option.  It must never migrate to a different land
        # price or quadrant.
        _LAND_TURNOVER_COMMITMENTS.pop(int(seat), None)
        commitment = None
    if commitment is not None:
        eligible_day = int(commitment["eligible_day"])
        has_land = any(
            order and order[0] == "BUY_LAND"
            for order in row.get("assets", ())
        )
        if int(snap.day) < eligible_day:
            # Preserve only the exact waiting decision already certified.  A
            # newly generated mixed capital bundle remains a distinct live
            # action, but the same pure land ray cannot leak back one day
            # early through the ordinary proposal layer.
            if has_land and _pure_next_land_bundle(snap, row):
                return _without_pure_land_bundle(
                    row, land_turnover_commitment_wait=True,
                    land_turnover_eligible_day=eligible_day,
                )
            return row
        if has_land:
            # The ordinary master has reconstructed a live certified action.
            _LAND_TURNOVER_COMMITMENTS.pop(int(seat), None)
            return row
        matured = _late_crop_land_challenger(
            snap, plan, tasks, row, bank_outputs=bank_outputs,
            activate_next_land=True, allow_initial_expansion=True,
            bounded_quantity_frontier=bounded_quantity_frontier,
        )
        if any(order and order[0] == "BUY_LAND"
               for order in matured.get("assets", ())):
            _LAND_TURNOVER_COMMITMENTS.pop(int(seat), None)
            matured["land_turnover_commitment_executed"] = True
            matured["land_turnover_eligible_day"] = eligible_day
            return matured
        # Keep the finite obligation reachable and retry only through the same
        # full live certificate.  Failure creates neither a purchase nor a
        # heuristic fallback.
        return row
    if (exercise_key is not None
            and exercise_key in _LAND_TURNOVER_EXERCISED):
        # The finite option below contains one released-tile continuation, not
        # recursive rights to replace every later land decision by another
        # wait.  After exercising it once for this ownership state, subsequent
        # actions return to the ordinary cash/route-certified capital master.
        return row

    assets = [list(order) for order in row.get("assets", ())]
    if not any(order and order[0] == "BUY_LAND" for order in assets):
        return row
    owned_extra = len(snap.me.unlocked) - 1
    if not (0 <= owned_extra < len(econ.LAND_ORDER)):
        return row
    next_quadrant = str(econ.LAND_ORDER[owned_extra])
    positioned = {
        str(item): tuple(tuple(pos) for pos in positions)
        for item, positions in row.get("positions_by_item", {}).items()
        if positions
    }
    selected_positions = [
        tuple(pos) for positions in positioned.values() for pos in positions
    ]
    if (not selected_positions
            or any(paths.quadrant_of(*pos, snap.board) != next_quadrant
                   for pos in selected_positions)):
        return row
    anchors = _standing_crop_release_anchors(snap)
    if not anchors:
        return row

    # The wait action cannot manufacture current capacity by dropping work.
    # Re-route the exact incumbent ordinary task set with the same paid crew.
    wait_row = dict(row)
    wait_row.update({
        "assets": [],
        "positions_by_item": {},
        "selected_counts": {},
    })
    if _current_positioned_route_profile(
            snap, plan, tasks, wait_row, {},
            bank_outputs=bank_outputs) is None:
        return row

    from whitebox import cashflow as _cashflow
    from whitebox import stackelberg as _stackelberg

    fixed = [list(order) for order in row.get("fixed", ())]
    hire_cost = float(row.get("hire_cost", 0.0) or 0.0)
    reserve = (
        max(0.0, float(row.get("service_reserve", 0.0) or 0.0))
        + hire_cost
    )
    horizon = int(_cashflow.LAST_DAY)
    cash_credit, sale_products = _stackelberg._standing_cash_terms(
        snap, horizon,
    )
    common = dict(
        reserve=reserve,
        fixed_orders=fixed,
        paired_objective=False,
        phase_aligned=True,
        visible_full_service_horizon=horizon,
        cash_credit_by_day=cash_credit,
        sale_products_by_day=sale_products,
    )
    standing = _cashflow.certify_shared(snap, {}, (), **common)
    if not standing.feasible:
        return row
    standing_outputs = {
        int(day): dict(products)
        for day, products in _cashflow._visible_output_schedule(
            snap, snap.me, include_fertilizer=True,
        ).items()
        if int(day) <= horizon
    }
    standing.outputs_by_day = standing_outputs

    response_products = tuple(econ.CROPS) + tuple(sorted({
        str(spec["product"]) for spec in econ.ANIMALS.values()
    }))
    context = _stackelberg.make_context(
        snap,
        full_response_continuation=True,
        include_own_standing_book=True,
        candidate_response_products=response_products,
    )

    # Immediate land has the same two admissible endpoints as deferred
    # capital: abandon after exact first output, or fund full continuation.
    counts = {item: len(positions)
              for item, positions in positioned.items()}
    slots = sorted(
        selected_positions,
        key=lambda pos: (paths.dist_to_shed(pos), pos),
    )
    land_cost = float(econ.LAND_PRICES[owned_extra])
    immediate = []
    immediate_audit = []
    for first_only in (True, False):
        cert = _cashflow.certify_shared(
            snap, counts, slots,
            land_cost=land_cost,
            positions_by_item=positioned,
            exact_first_output=bool(first_only),
            **common,
        )
        immediate_audit.append((
            bool(first_only), bool(cert.feasible), str(cert.reason),
            float(cert.minimum_cash), float(cert.final_cash),
        ))
        if not cert.feasible:
            continue
        incremental_operating = (
            float(cert.operating_cost) - float(standing.operating_cost)
        )
        own_cost = float(cert.upfront_spend) + incremental_operating
        game = _robust_schedule_value(
            snap, context, cert.outputs_by_day, own_cost,
        )
        immediate.append((
            float(game), float(cert.final_cash), -float(own_cost),
            bool(first_only), cert,
        ))
    if not immediate:
        immediate_game = float("-inf")
        immediate_endpoint = None
    else:
        (immediate_game, _immediate_cash, _immediate_cost,
         _immediate_first, immediate_endpoint) = max(immediate)

    # This repair is a feasibility covenant, not a timing forecast.  If any
    # immediate endpoint pays for land, the named assets, current crew and the
    # standing farm's service bridge, the live base action remains available.
    # Waiting is admissible only when immediate expansion fails that explicit
    # proof and a concrete released-tile alternative is constructed below.
    if immediate_endpoint is not None:
        return row

    options = []
    anchor_audit = []
    released = []
    for anchor, entries in anchors.items():
        released.extend(entries)
        released_positions = {tuple(pos) for _crop, pos in released}
        future = copy.deepcopy(snap)
        # Existing empty cells may be committed to private inventory.  The
        # delayed arm is credited only the named released crop cells.
        for y, tile_row in enumerate(future.me.tiles):
            for x, tile in enumerate(tile_row):
                if tile is None:
                    tile_row[x] = "LOCKED"
        for pos in released_positions:
            x, y = pos
            future.me.tiles[y][x] = None
            future.me.crops.pop(pos, None)
        future.me.empty = sorted(released_positions)

        base = copy.deepcopy(standing)
        by_item = defaultdict(list)
        for crop, pos in released:
            by_item[str(crop)].append(tuple(pos))
        base.positions_by_item = {
            item: tuple(positions)
            for item, positions in sorted(by_item.items())
        }
        generated = _stackelberg.feasible_deferred_capital(
            future, base, reserve=reserve,
            full_continuation=True,
            purchase_day=int(anchor) + 1,
            release_harvested_land=True,
            target_items=tuple(econ.CROPS) + tuple(econ.ANIMALS),
            name_stem=f"WAIT_RELEASE_{anchor}",
        )
        feasible = 0
        best_anchor = None
        for option in generated:
            if not option.order:
                continue
            feasible += 1
            game = _robust_schedule_value(
                snap, context, option.schedule(), float(option.cost),
            )
            arm = (
                float(game), -float(option.cost),
                -int(option.purchase_day), option.name, option,
                tuple(sorted(released_positions)), int(anchor),
            )
            if best_anchor is None or arm[:4] > best_anchor[:4]:
                best_anchor = arm
            options.append(arm)
        anchor_audit.append((
            int(anchor), len(released_positions), int(feasible),
            None if best_anchor is None else float(best_anchor[0]),
        ))

    if not options:
        return row
    (wait_game, _wait_cost, _wait_day, _wait_name, option,
     release_positions, release_day) = max(options)
    if wait_game <= immediate_game + 1e-9:
        return row

    ordinary = list(row.get("selected_ordinary_tasks", ()))
    ordinary_value = float(
        objective.TaskBundleObjective(snap, ordinary).score(ordinary)
    )
    winner = _without_pure_land_bundle(row)
    winner.update({
        # The immediate row is infeasible, so it cannot define a finite score
        # delta.  Value the executable wait action directly: retained ordinary
        # work plus its same-scenario future option, less today's crew bill.
        "score": ordinary_value + float(wait_game) - hire_cost,
        "land_turnover_option": True,
        "land_turnover_quadrant": next_quadrant,
        "land_turnover_immediate_value": float(immediate_game),
        "land_turnover_immediate_audit": tuple(immediate_audit),
        "land_turnover_wait_value": float(wait_game),
        "land_turnover_ordinary_value": ordinary_value,
        "land_turnover_release_positions": tuple(release_positions),
        "land_turnover_release_day": int(release_day),
        "land_turnover_purchase_day": int(option.purchase_day),
        "land_turnover_future_order": tuple(option.order),
        "land_turnover_future_cost": float(option.cost),
        "land_turnover_future_routes_by_day": option.routes(),
        "land_turnover_future_hire_phases_by_day": option.hire_phases(),
        "land_turnover_response_count": len(context.get("responses", ())),
        "land_turnover_worst_response": min(
            context.get("responses") or (_stackelberg.Response("NO_RESPONSE"),),
            key=lambda response: (
                _stackelberg._context_response_margin(
                    snap, option.schedule(), float(option.cost),
                    response, context,
                ),
                response.name,
            ),
        ).name,
        "land_turnover_anchor_audit": tuple(anchor_audit),
        "land_turnover_gate_reason": "immediate_land_infeasible",
    })
    if exercise_key is not None:
        _LAND_TURNOVER_EXERCISED.add(exercise_key)
        _LAND_TURNOVER_COMMITMENTS[int(seat)] = {
            "created_day": int(snap.day),
            "eligible_day": int(option.purchase_day),
            "unlocked_count": len(snap.me.unlocked),
        }
    return winner


def _service_cluster_layout_challenger(snap, plan, tasks, row,
                                       bank_outputs=False,
                                       include_productive_shed=False):
    """Accept a clustered new-asset layout only under strict white-box proof.

    The candidate action set is generated solely from public board geometry
    and engine service equations. The chosen capital multiset, order keys,
    crew, activated land, fixed trades, and incumbent ordinary tasks are held
    fixed. A candidate survives only if:

      * today's mandatory work remains feasible with no more workers or
        longest-route actions;
      * every future day uses no more workers and no more closed-route turns;
      * aggregate current-plus-future workers and turns weakly improve, with
        at least one physical inequality strict; and
      * the unified finite Stackelberg worst-response value does not fall.

    Thus compactness has no fitted reward. It is selected only when it produces
    an actual labour/travel Pareto improvement with non-worse economic value.
    """
    base_positions = {
        str(item): tuple(tuple(pos) for pos in positions)
        for item, positions in row.get("positions_by_item", {}).items()
        if positions
    }
    if not base_positions:
        return row
    assets = [list(order) for order in row.get("assets", ())]
    fixed = [list(order) for order in row.get("fixed", ())]
    layout_snap = snap
    if (include_productive_shed or any(
            tuple(pos) in paths.SHED_SET
            for positions in base_positions.values() for pos in positions)):
        # The earlier productive-shed challenger may have selected one of the
        # four engine-legal access cells. Reuse that exact public geometry in
        # route construction without enabling any unselected coordinate.
        layout_snap = copy.copy(snap)
        layout_snap.allow_productive_shed_tiles = True
    layouts = list(_service_cluster_layouts(
        layout_snap, base_positions, assets,
        blocked={tuple(task.pos) for task in tasks},
    ))
    if not layouts:
        return row

    counts = {item: len(positions)
              for item, positions in base_positions.items()}
    base_current = _current_positioned_route_profile(
        layout_snap, plan, tasks, row, base_positions,
        bank_outputs=bank_outputs,
    )
    if base_current is None:
        return row

    from whitebox import stackelberg as _stackelberg
    products = tuple(econ.CROPS) + tuple(sorted({
        str(spec["product"]) for spec in econ.ANIMALS.values()
    }))
    context = _stackelberg.make_context(
        snap, full_response_continuation=True,
        include_own_standing_book=True,
        candidate_response_products=products,
    )
    hires = int(row.get("hires", 0) or 0)
    hire_cost = float(row.get("hire_cost", 0.0) or 0.0)
    reserve = (
        max(0.0, float(row.get("service_reserve", 0.0) or 0.0))
        + hire_cost
    )
    has_land = any(order and order[0] == "BUY_LAND" for order in assets)
    land_cost = (
        float(econ.LAND_PRICES[len(snap.me.unlocked) - 1])
        if has_land and econ.can_buy_land(len(snap.me.unlocked))
        else 0.0
    )

    def certify(layout):
        slots = sorted(
            {pos for positions in layout.values() for pos in positions},
            key=lambda pos: (paths.dist_to_shed(pos), pos),
        )
        return _stackelberg.certify_unified(
            snap, counts, slots, reserve=reserve, land_cost=land_cost,
            fixed_orders=fixed, positions_by_item=layout,
            context=context, activated_land_reinvestment=has_land,
            full_service_continuation=True,
            service_fertilizer_credit=True,
            service_fertilizer_value=True,
        )

    baseline = certify(base_positions)
    if not baseline.feasible:
        reason = str(baseline.reason)
        audited = dict(row)
        audited.update({
            "service_cluster_current_before": tuple(base_current),
            "service_cluster_candidate_count": len(layouts),
            "service_cluster_baseline_reason": reason,
        })
        # Layout does not change quantities, dated outputs, feed, orders,
        # land, ordinary work or asset cost. If both absolute certificates
        # fail specifically because neither has a selectable Stackelberg
        # endpoint, a strict coordinate-only route Pareto proof remains
        # meaningful. Every other failure stays closed.
        if reason != "no_stackelberg_endpoint":
            audited["service_cluster_audit"] = (("baseline_" + reason,),)
            return audited
        baseline_future = _positioned_full_service_route_profile(
            layout_snap, base_positions,
        )
        if baseline_future is None:
            audited["service_cluster_audit"] = ((
                "baseline_full_service_route",
            ),)
            return audited

        relative = []
        audit = []
        for layout in layouts:
            if {item: len(positions)
                    for item, positions in layout.items()} != counts:
                audit.append(("counts",))
                continue
            current = _current_positioned_route_profile(
                layout_snap, plan, tasks, row, layout,
                bank_outputs=bank_outputs,
            )
            if current is None:
                audit.append(("current_route",))
                continue
            if (current[0] > base_current[0]
                    or current[2] > base_current[2]):
                audit.append(("current_capacity", base_current, current))
                continue
            candidate_cert = certify(layout)
            candidate_reason = str(candidate_cert.reason)
            if candidate_cert.feasible or candidate_reason != reason:
                audit.append((
                    "absolute_reason_mismatch", reason, candidate_reason,
                ))
                continue
            future = _positioned_full_service_route_profile(
                layout_snap, layout,
            )
            if future is None:
                audit.append(("full_service_route",))
                continue
            if not _service_layout_lifecycle_dominates(
                    base_current, current, baseline_future, future):
                audit.append((
                    "route_lifecycle", base_current, current,
                    tuple(sorted(baseline_future.items())),
                    tuple(sorted(future.items())),
                ))
                continue
            days = set(baseline_future) | set(future)
            worker_saving = (
                base_current[0] - current[0]
                + sum(baseline_future.get(day, (0, 0))[0]
                      - future.get(day, (0, 0))[0] for day in days)
            )
            turn_saving = (
                base_current[1] - current[1]
                + sum(baseline_future.get(day, (0, 0))[1]
                      - future.get(day, (0, 0))[1] for day in days)
            )
            max_route_saving = base_current[2] - current[2]
            audit.append((
                "accepted_relative_route", int(worker_saving),
                int(turn_saving), int(max_route_saving),
            ))
            relative.append((
                int(worker_saving), int(turn_saving),
                int(max_route_saving), tuple(sorted(layout.items())),
                layout, current, future,
            ))
        if not relative:
            audited.update({
                "service_cluster_future_before": dict(baseline_future),
                "service_cluster_audit": tuple(audit),
            })
            return audited

        (worker_saving, turn_saving, max_route_saving, _layout_key,
         layout, current, future) = max(relative)
        winner = dict(row)
        winner.update({
            "positions_by_item": {
                item: tuple(positions)
                for item, positions in sorted(layout.items())
            },
            "assets": _positioned_assets(assets, layout),
            # Do not invent an economic delta when both absolute endpoints are
            # undefined. Preserve the score selected by the upstream master.
            "score": float(row.get("score", 0.0)),
            "service_cluster_certificate_mode": "relative_route_pareto",
            "service_cluster_baseline_reason": reason,
            "service_cluster_current_before": tuple(base_current),
            "service_cluster_current_after": tuple(current),
            "service_cluster_workers_saved": int(worker_saving),
            "service_cluster_turns_saved": int(turn_saving),
            "service_cluster_max_route_saved": int(max_route_saving),
            "service_cluster_future_before": dict(baseline_future),
            "service_cluster_future_after": dict(future),
            "service_cluster_candidate_count": len(layouts),
            "service_cluster_response_count": len(
                context.get("responses", ())
            ),
            "service_cluster_audit": tuple(audit),
        })
        return winner
    baseline_game = float(baseline.paired_value) - hire_cost
    baseline_future = _certificate_route_profile(baseline)
    candidates = []
    audit = []

    for layout in layouts:
        if {item: len(positions)
                for item, positions in layout.items()} != counts:
            audit.append(("counts",))
            continue
        current = _current_positioned_route_profile(
            layout_snap, plan, tasks, row, layout,
            bank_outputs=bank_outputs,
        )
        if current is None:
            audit.append(("current_route",))
            continue
        if (current[0] > base_current[0]
                or current[2] > base_current[2]):
            audit.append(("current_capacity", base_current, current))
            continue
        cert = certify(layout)
        if not cert.feasible:
            audit.append((str(cert.reason),))
            continue
        game = float(cert.paired_value) - hire_cost
        if game + 1e-9 < baseline_game:
            audit.append(("game_value", baseline_game, game))
            continue
        future = _certificate_route_profile(cert)
        if not _service_layout_lifecycle_dominates(
                base_current, current, baseline_future, future):
            audit.append((
                "route_lifecycle", base_current, current,
                tuple(sorted(baseline_future.items())),
                tuple(sorted(future.items())),
            ))
            continue
        worker_saving = (
            base_current[0] - current[0]
            + sum(baseline_future.get(day, (0, 0))[0]
                  - future.get(day, (0, 0))[0]
                  for day in set(baseline_future) | set(future))
        )
        turn_saving = (
            base_current[1] - current[1]
            + sum(baseline_future.get(day, (0, 0))[1]
                  - future.get(day, (0, 0))[1]
                  for day in set(baseline_future) | set(future))
        )
        max_route_saving = base_current[2] - current[2]
        audit.append(("accepted", baseline_game, game,
                      int(worker_saving), int(turn_saving),
                      int(max_route_saving)))
        candidates.append((
            game, int(worker_saving), int(turn_saving),
            int(max_route_saving), float(cert.final_cash),
            tuple(sorted(layout.items())),
            layout, cert, current, future,
        ))
    if not candidates:
        audited = dict(row)
        audited.update({
            "service_cluster_before_value": baseline_game,
            "service_cluster_current_before": tuple(base_current),
            "service_cluster_future_before": dict(baseline_future),
            "service_cluster_candidate_count": len(layouts),
            "service_cluster_audit": tuple(audit),
        })
        return audited
    (game, worker_saving, turn_saving, max_route_saving, _cash, _layout_key,
     layout, cert, current, future) = max(candidates)
    winner = dict(row)
    winner.update({
        "positions_by_item": {
            item: tuple(positions)
            for item, positions in sorted(layout.items())
        },
        "assets": _positioned_assets(assets, layout),
        "score": float(row.get("score", 0.0)) + game - baseline_game,
        "service_cluster_before_value": baseline_game,
        "service_cluster_after_value": game,
        "service_cluster_current_before": tuple(base_current),
        "service_cluster_current_after": tuple(current),
        "service_cluster_workers_saved": int(worker_saving),
        "service_cluster_turns_saved": int(turn_saving),
        "service_cluster_max_route_saved": int(max_route_saving),
        "service_cluster_future_before": dict(baseline_future),
        "service_cluster_future_after": dict(future),
        "service_cluster_worst_response": str(
            cert.selected_worst_response
        ),
        "service_cluster_response_count": len(context.get("responses", ())),
        "service_cluster_audit": tuple(audit),
    })
    return winner


def _animal_admission_certificate(snap, row, context=None):
    """Return a complete-service certificate for one selected animal row.

    This is deliberately a gate, not a value heuristic.  It reuses the
    row's own selected positions and fixed orders and asks the unified public
    state model to carry the animal through the full service horizon.  A
    missing endpoint, malformed position map or unsupported state returns
    ``None`` so callers can fail closed.  No opponent schedule or replay data
    is consulted.
    """
    selected = {
        str(item): tuple(tuple(pos) for pos in positions)
        for item, positions in row.get("positions_by_item", {}).items()
        if positions
    }
    animal_counts = {
        item: len(positions) for item, positions in selected.items()
        if item in econ.ANIMALS
    }
    if not animal_counts:
        return True
    slots = sorted(
        {tuple(pos) for positions in selected.values() for pos in positions},
        key=lambda pos: (paths.dist_to_shed(pos), pos),
    )
    if not slots:
        return None
    from whitebox import stackelberg as _stackelberg
    if context is None:
        products = tuple(econ.CROPS) + tuple(sorted({
            str(spec["product"]) for spec in econ.ANIMALS.values()
        }))
        context = _stackelberg.make_context(
            snap, full_response_continuation=True,
            include_own_standing_book=True,
            candidate_response_products=products,
        )
    land_cost = 0.0
    activates_land = any(
        order and order[0] == "BUY_LAND" for order in row.get("assets", ())
    )
    if activates_land and econ.can_buy_land(len(snap.me.unlocked)):
        owned_extra = len(snap.me.unlocked) - 1
        land_cost = float(econ.LAND_PRICES[owned_extra])
    reserve = float(row.get("service_reserve", 0.0)) + float(
        row.get("hire_cost", 0.0)
    )
    counts = {item: len(positions) for item, positions in selected.items()}
    cert = _stackelberg.certify_unified(
        snap, counts, slots, reserve=reserve, land_cost=land_cost,
        fixed_orders=row.get("fixed", ()),
        positions_by_item=selected, context=context,
        activated_land_reinvestment=activates_land,
        full_service_continuation=True,
    )
    # The full endpoint is the executable survival witness.  A first-output
    # endpoint alone can be profitable while leaving later FEED/CARE unpaid.
    return cert if cert.feasible and bool(
        getattr(cert, "selected_full_endpoint", False)
    ) else None


def _decide_crew_conditioned(snap, plan, tasks, market_orders,
                             bank_outputs=False,
                             fertilizer_bridge=False,
                             memoize_proposals=False,
                             reserve_visible_fertilizer=False,
                             exchange_repair=False,
                             adaptive_marginal=False,
                             intraday_replan=False,
                             joint_visible_workload=False,
                             stackelberg=False,
                             land_reinvestment=False,
                             activated_land_reinvestment=False,
                             stackelberg_arm_recertification=False,
                             full_service_continuation=False,
                             positioned_capital_manifest=False,
                             execution_aligned_crew=False,
                             execution_aligned_empty_farm=False,
                             robust_tail_repair=False,
                             positioned_empty_farm_manifest=False,
                             robust_composition_exchange=False,
                             cash_safe_composition_exchange=False,
                             full_response_composition_exchange=False,
                             mixed_response_composition_exchange=False,
                             scenario_dominant_composition_exchange=False,
                             robust_portfolio_descent=False,
                             cashflow_backed_service_hiring=False,
                             robust_service_without_fertilizer=False,
                             crew_frontier_portfolio_descent=False,
                             standing_book_composition_exchange=False,
                             feasible_cash_scenario_composition_exchange=False,
                             same_asset_class_composition_exchange=False,
                             allow_animal_idle_composition_exchange=False,
                             standing_animal_rebalance_after_scenario=False,
                             standing_structure_rebalance_after_scenario=False,
                             standing_structure_robust_after_scenario=False,
                             standing_structure_complete_response_after_scenario=False,
                             crop_only_land_arm=False,
                             robust_crop_land_gate=False,
                             late_crop_land_challenger=False,
                             late_land_animal_scale_repair=False,
                             late_land_global_scale_repair=False,
                             crop_land_covenant_repair=False,
                             late_land_service_burden_repair=False,
                             late_empty_crop_challenger=False,
                             deferred_crop_hires=False,
                             deferred_land_hires=False,
                             land_recovery_covenant=False,
                             deferred_capital_option=False,
                             deferred_capital_full_continuation=False,
                             close_empty_deferred_baseline=False,
                             deferred_standing_service_horizon=False,
                             bounded_first_output_only=False,
                             suppress_uncommitted_rotation=False,
                             execute_bounded_commitment=False,
                             close_infeasible_capital=False,
                             saturated_standing_book_gate=False,
                             exact_capacity_frontier=False,
                             precertified_capacity_frontier=False,
                             staged_opponent_reinvestment=False,
                             complete_opponent_response_products=False,
                             robust_own_standing_realisation=False,
                             staged_opponent_land_reinvestment=False,
                             staged_opponent_mixed_reinvestment=False,
                             paid_rotation_substitution=False,
                             backlogged_rotation_substitution=False,
                             single_backlog_rotation_substitution=False,
                             productive_shed_relocation=False,
                             service_cluster_layout=False,
                             land_turnover_option=False,
                             bounded_land_quantity_frontier=False,
                             crop_rotation_reinvestment=False,
                             joint_standing_capital=False,
                             joint_standing_portfolio_gate=False,
                             land_frontier_certificate=False,
                             opening_animal_retention=False,
                             turnover_positions=(),
                             turnover_items_by_position=None):
    rows = crew_conditioned_decision_curve(
        snap, plan, tasks, market_orders, bank_outputs,
        fertilizer_bridge=fertilizer_bridge,
        memoize_proposals=memoize_proposals,
        reserve_visible_fertilizer=reserve_visible_fertilizer,
        exchange_repair=exchange_repair,
        adaptive_marginal=adaptive_marginal,
        intraday_replan=intraday_replan,
        joint_visible_workload=joint_visible_workload,
        stackelberg=stackelberg,
        land_reinvestment=land_reinvestment,
        activated_land_reinvestment=activated_land_reinvestment,
        stackelberg_arm_recertification=stackelberg_arm_recertification,
        full_service_continuation=full_service_continuation,
        execution_aligned_crew=execution_aligned_crew,
        execution_aligned_empty_farm=execution_aligned_empty_farm,
        cashflow_backed_service_hiring=cashflow_backed_service_hiring,
        crop_only_land_arm=crop_only_land_arm,
        robust_crop_land_gate=robust_crop_land_gate,
        joint_standing_capital=joint_standing_capital,
        land_frontier_certificate=land_frontier_certificate,
        turnover_positions=turnover_positions,
        turnover_items_by_position=turnover_items_by_position,
    )
    if not rows:
        # The joint capital/crew program is a day-opening decision.  When it
        # has already bought a Fibonacci block, a later fixed-task fallback
        # would price the same workload a second time and invalidate workers'
        # carried manifests.  Earlier hiring weakly dominates that later hire
        # whenever no new market-phase capital program is being solved.
        fixed, _proposed = split_orders(market_orders)
        return 0, [], fixed
    if FAILURE_CLOSED_ANIMAL_ADMISSION:
        # Validate only rows that would actually emit a newly purchased animal.
        # Keep non-animal rows in the action set so a failed animal endpoint
        # can fall back to a certified crop/worker plan rather than forcing a
        # whole-day IDLE.  Context is shared across rows but contains only the
        # current public observation and finite response set.
        animal_products = tuple(econ.CROPS) + tuple(sorted({
            str(spec["product"]) for spec in econ.ANIMALS.values()
        }))
        admission_context = None
        admitted_rows = []
        for candidate_row in sorted(
                rows, key=lambda item: (
                    -float(item.get("score", float("-inf"))),
                    float(item.get("hire_cost", 0.0)),
                    int(item.get("hires", 0)),
                )):
            has_animal = any(
                str(item) in econ.ANIMALS and int(quantity or 0) > 0
                for item, quantity in candidate_row.get(
                    "selected_counts", {}
                ).items()
            )
            if not has_animal:
                admitted_rows.append(candidate_row)
                continue
            if admission_context is None:
                from whitebox import stackelberg as _stackelberg
                admission_context = _stackelberg.make_context(
                    snap, full_response_continuation=True,
                    include_own_standing_book=True,
                    candidate_response_products=animal_products,
                )
            cert = _animal_admission_certificate(
                snap, candidate_row, context=admission_context,
            )
            if cert is None:
                candidate_row = dict(candidate_row)
                candidate_row["animal_admission_rejected"] = True
                candidate_row["animal_admission_reason"] = (
                    "no_complete_service_endpoint"
                )
                continue
            candidate_row = dict(candidate_row)
            candidate_row["animal_admission_certificate"] = cert
            candidate_row["animal_admission_rejected"] = False
            admitted_rows.append(candidate_row)
        rows = admitted_rows
        if not rows:
            fixed, _proposed = split_orders(market_orders)
            return 0, [], fixed
    if crew_frontier_portfolio_descent:
        rows = _crew_frontier_portfolio_descent(snap, rows)
    best = max(
        rows,
        key=lambda row: (
            row["score"], -row["hire_cost"], -row["capital_cash"],
            -row["hires"], -row["order_keys"],
        ),
    )
    if robust_tail_repair and _is_empty_capital_state(snap):
        best = _robust_tail_repair(snap, best)
    staged_response_cache = (
        {} if staged_opponent_reinvestment else None
    )
    if (robust_composition_exchange or cash_safe_composition_exchange
            or full_response_composition_exchange
            or mixed_response_composition_exchange
            or scenario_dominant_composition_exchange
            or robust_portfolio_descent):
        if robust_portfolio_descent and not crew_frontier_portfolio_descent:
            best = _robust_portfolio_descent(
                snap, best,
                service_fertilizer_credit=(
                    not robust_service_without_fertilizer
                ),
            )
        else:
            best = _robust_composition_exchange(
                snap, best,
                preserve_cash_prefix=(cash_safe_composition_exchange
                                      or full_response_composition_exchange
                                      or mixed_response_composition_exchange
                                      or (scenario_dominant_composition_exchange
                                          and not feasible_cash_scenario_composition_exchange)),
                # Cash-prefix dominance is the online proof that every incumbent
                # cash-funded action date remains available. Exhaustively pricing
                # every later land date inside every coordinate takes seconds and
                # is retained as an offline certificate primitive, not an action-
                # path computation.
                all_reinvestment_anchors=False,
                full_opponent_continuation=(full_response_composition_exchange
                                            or mixed_response_composition_exchange
                                            or scenario_dominant_composition_exchange),
                mixed_opponent_continuation=mixed_response_composition_exchange,
                preserve_response_scenarios=(
                    scenario_dominant_composition_exchange
                ),
                candidate_response_products=(
                    tuple(econ.CROPS) + tuple(sorted({
                        str(spec["product"])
                        for spec in econ.ANIMALS.values()
                    }))
                    if complete_opponent_response_products else ()
                ),
                include_own_standing_book=(
                    standing_book_composition_exchange
                ),
                same_asset_class_only=(
                    same_asset_class_composition_exchange
                ),
                disallow_animal_to_crop_exchange=(
                    bool(opening_animal_retention)
                    and int(snap.step) == 0
                ),
                allow_animal_idle=(
                    allow_animal_idle_composition_exchange
                ),
                close_infeasible_capital=close_infeasible_capital,
                expose_infeasible_certificate=(
                    precertified_capacity_frontier
                ),
                staged_opponent_reinvestment=(
                    staged_opponent_reinvestment
                ),
                staged_response_cache=staged_response_cache,
                robust_own_standing_realisation=(
                    robust_own_standing_realisation
                ),
                staged_opponent_land_reinvestment=(
                    staged_opponent_land_reinvestment
                ),
                staged_opponent_mixed_reinvestment=(
                    staged_opponent_mixed_reinvestment
                ),
            )
            if (standing_animal_rebalance_after_scenario
                    or standing_structure_rebalance_after_scenario
                    or standing_structure_robust_after_scenario
                    or standing_structure_complete_response_after_scenario):
                # Preserve V132's already-gated scale/crop result, then solve
                # only the livestock type on the unified standing-output book.
                # This second pass cannot create an extra asset or touch a crop.
                best = _robust_composition_exchange(
                    snap, best,
                    preserve_cash_prefix=False,
                    all_reinvestment_anchors=False,
                    full_opponent_continuation=True,
                    mixed_opponent_continuation=False,
                    preserve_response_scenarios=(
                        not standing_structure_robust_after_scenario
                        and not standing_structure_complete_response_after_scenario
                    ),
                    include_own_standing_book=True,
                    same_asset_class_only=True,
                    source_asset_class="ANIMAL",
                    same_structure_only=(
                        standing_structure_rebalance_after_scenario
                        or standing_structure_robust_after_scenario
                        or standing_structure_complete_response_after_scenario
                    ),
                    candidate_response_products=(
                        ("MILK", "WOOL")
                        if standing_structure_complete_response_after_scenario
                        else ()
                    ),
                )
    if saturated_standing_book_gate:
        best = _saturated_standing_book_gate(
            snap, best,
            exact_two_kind_frontier=exact_capacity_frontier,
            precertified_infeasibility_only=(
                precertified_capacity_frontier
            ),
        )
    if late_crop_land_challenger:
        best = _late_crop_land_challenger(
            snap, plan, tasks, best, bank_outputs=bank_outputs,
            bounded_quantity_frontier=(
                bounded_land_quantity_frontier
            ),
            allow_deferred_hires=deferred_land_hires,
            staged_opponent_reinvestment=(
                staged_opponent_reinvestment
            ),
            staged_response_cache=staged_response_cache,
            complete_opponent_response_products=(
                complete_opponent_response_products
            ),
            robust_own_standing_realisation=(
                robust_own_standing_realisation
            ),
            staged_opponent_land_reinvestment=(
                staged_opponent_land_reinvestment
            ),
            staged_opponent_mixed_reinvestment=(
                staged_opponent_mixed_reinvestment
            ),
        )
    if (paid_rotation_substitution
            or ((backlogged_rotation_substitution
                 or single_backlog_rotation_substitution)
                and bool(snap.me.weeds))):
        # A durable animal occupies one tile through the horizon.  Compare it
        # with a crop on that same certified position plus only the repeated
        # rotations that its own realised sale cash can buy.  The animal arm
        # pays full remaining FEED/CARE/route wages; fertilizer may bridge cash
        # but carries no residual utility.  Both arms face the same standing
        # book and finite paid opponent responses.  Counts are outcomes of the
        # public action set, never target composition parameters.
        products = tuple(econ.CROPS) + tuple(sorted({
            str(spec["product"]) for spec in econ.ANIMALS.values()
        }))
        best = _robust_composition_exchange(
            snap, best,
            preserve_cash_prefix=False,
            full_opponent_continuation=True,
            preserve_response_scenarios=False,
            include_own_standing_book=True,
            own_full_service_continuation=True,
            rotation_reinvestment=True,
            own_service_fertilizer_credit=True,
            own_service_fertilizer_value=False,
            source_asset_class="ANIMAL",
            target_asset_class="CROP",
            candidate_response_products=products,
            max_exchange_quantity=(
                1 if single_backlog_rotation_substitution else None
            ),
        )
    if late_empty_crop_challenger:
        best = _late_crop_land_challenger(
            snap, plan, tasks, best, bank_outputs=bank_outputs,
            activate_next_land=False,
            allow_deferred_hires=deferred_crop_hires,
            deferred_capital_option=deferred_capital_option,
            deferred_capital_full_continuation=(
                deferred_capital_full_continuation
            ),
            close_empty_deferred_baseline=close_empty_deferred_baseline,
            deferred_standing_service_horizon=(
                deferred_standing_service_horizon
            ),
            bounded_first_output_only=bounded_first_output_only,
            suppress_uncommitted_rotation=suppress_uncommitted_rotation,
            deferred_execution_witness=execute_bounded_commitment,
        )
    if (late_land_animal_scale_repair
            and (len(snap.me.unlocked) >= 3
                 or best.get("late_land_crop") is not None)):
        # The new quadrant is a real option only if subsequent replans price
        # the standing herd before occupying its capacity.  Restrict this
        # repair to PASTURE-compatible current purchases and allow an unused
        # tile as a named action; crops, geese, crew and activated land remain
        # fixed.  The trigger is public ownership/this decision's certificate,
        # never an opponent identity or target herd.
        best = _robust_composition_exchange(
            snap, best,
            preserve_cash_prefix=False,
            full_opponent_continuation=True,
            preserve_response_scenarios=False,
            include_own_standing_book=True,
            same_asset_class_only=True,
            allow_animal_idle=True,
            source_asset_class="ANIMAL",
            same_structure_only=True,
            candidate_response_products=("MILK", "WOOL"),
        )
    if (late_land_global_scale_repair
            and (len(snap.me.unlocked) >= 3
                 or best.get("late_land_crop") is not None)):
        products = tuple(econ.CROPS) + tuple(
            sorted({str(spec["product"])
                    for spec in econ.ANIMALS.values()})
        )
        best = _robust_composition_exchange(
            snap, best,
            preserve_cash_prefix=False,
            full_opponent_continuation=True,
            preserve_response_scenarios=False,
            allow_idle=True,
            include_own_standing_book=True,
            candidate_response_products=products,
        )
    if crop_land_covenant_repair:
        crop_quadrants = list(snap.me.unlocked[2:])
        if best.get("late_land_crop") is not None:
            owned_extra = len(snap.me.unlocked) - 1
            if econ.can_buy_land(len(snap.me.unlocked)):
                crop_quadrants.append(econ.LAND_ORDER[owned_extra])
        if crop_quadrants:
            products = tuple(econ.CROPS) + tuple(
                sorted({str(spec["product"])
                        for spec in econ.ANIMALS.values()})
            )
            best = _robust_composition_exchange(
                snap, best,
                preserve_cash_prefix=False,
                full_opponent_continuation=True,
                preserve_response_scenarios=False,
                allow_animal_idle=True,
                include_own_standing_book=True,
                source_asset_class="ANIMAL",
                source_quadrants=tuple(crop_quadrants),
                target_asset_class="CROP",
                candidate_response_products=products,
            )
    if (late_land_service_burden_repair
            and (len(snap.me.unlocked) >= 3
                 or best.get("late_land_crop") is not None)):
        # Replan-node consistency: a newly selected animal must share every
        # remaining daily route, wage, feed purchase and order slot with the
        # public standing farm.  Only current animal purchase columns may be
        # changed; existing capital, crew, land and ordinary work stay fixed.
        # Crop and IDLE are engine actions in the comparison, not target
        # composition labels.
        products = tuple(econ.CROPS) + tuple(
            sorted({str(spec["product"])
                    for spec in econ.ANIMALS.values()})
        )
        best = _robust_composition_exchange(
            snap, best,
            preserve_cash_prefix=False,
            full_opponent_continuation=True,
            preserve_response_scenarios=False,
            include_own_standing_book=True,
            own_full_service_continuation=True,
            source_asset_class="ANIMAL",
            allow_animal_idle=True,
            candidate_response_products=products,
        )
    if crop_rotation_reinvestment:
        # A one-shot crop occupies a tile only until harvest. Compare every
        # legal crop substitution on the same positioned tile set, then let
        # the unified certificate buy and repeatedly work a second crop only
        # after realised sale cash and the released tile both exist. The
        # quantity is the best finite exchange ray, not a crop target.
        products = tuple(econ.CROPS) + tuple(sorted({
            str(spec["product"]) for spec in econ.ANIMALS.values()
        }))
        best = _robust_composition_exchange(
            snap, best,
            preserve_cash_prefix=False,
            full_opponent_continuation=True,
            preserve_response_scenarios=False,
            all_reinvestment_anchors=False,
            include_own_standing_book=True,
            same_asset_class_only=True,
            source_asset_class="CROP",
            target_asset_class="CROP",
            rotation_reinvestment=True,
            candidate_response_products=products,
        )
    if service_cluster_layout:
        # When both flags are enabled, shed-access cells and route clusters
        # enter one candidate set against one baseline. Sequential layout
        # challengers can each undo the other's geometry even when both local
        # certificates improve; one joint comparison closes that loophole.
        best = _service_cluster_layout_challenger(
            snap, plan, tasks, best, bank_outputs=bank_outputs,
            include_productive_shed=productive_shed_relocation,
        )
    if productive_shed_relocation and not service_cluster_layout:
        best = _productive_shed_relocation_challenger(
            snap, plan, tasks, best, bank_outputs=bank_outputs,
        )
    if land_turnover_option:
        best = _land_turnover_option_challenger(
            snap, plan, tasks, best, bank_outputs=bank_outputs,
            bounded_quantity_frontier=(
                bounded_land_quantity_frontier
            ),
        )
    if joint_standing_portfolio_gate:
        best = _joint_standing_portfolio_gate(snap, best)
    if (positioned_capital_manifest
            or robust_composition_exchange
            or cash_safe_composition_exchange
            or full_response_composition_exchange
            or mixed_response_composition_exchange
            or scenario_dominant_composition_exchange
            or robust_portfolio_descent
            or (positioned_empty_farm_manifest
                and _is_empty_capital_state(snap))):
        from whitebox import tasks as _task_planner
        _task_planner.commit_capital_positions(
            snap.seat, snap.day, best.get("positions_by_item", {}),
        )
    if deferred_crop_hires or deferred_land_hires:
        field = "late_land" if deferred_land_hires else "late_fill"
        _DEFERRED_HIRES[snap.seat] = (
            int(snap.day),
            int(best.get(field + "_deferred_hires", 0) or 0),
        )
    if land_recovery_covenant and best.get("late_land_crop") is not None:
        _store_land_use_covenant(snap, best)
    if (execute_bounded_commitment
            and best.get("late_fill_crop") is not None):
        _store_bounded_commitment(snap, best, "late_fill")
    return (int(best["hires"]), [list(order) for order in best["assets"]],
            [list(order) for order in best["fixed"]])


def decide(snap, plan, tasks, market_orders, unit_actions=None, deadline=None,
           variant=None, bank_outputs=False, charge_activation_cost=True,
           productive_shed_relocation=False,
           service_cluster_layout=False,
           land_turnover_option=False,
           bounded_land_quantity_frontier=False,
           crop_rotation_reinvestment=False,
           joint_standing_capital=False,
           joint_standing_portfolio_gate=False,
           land_frontier_certificate=False,
           single_quadrant_asset_class_exchange=False,
           opening_asset_class_exchange=False,
           opening_animal_retention=False,
           turnover_positions=(), turnover_items_by_position=None):
    """Return ``(hires, selected_asset_orders, fixed_orders)``."""
    if variant == _LAND_RECOVERY_COVENANT_VARIANT and int(snap.step) == 0:
        _clear_land_use_covenant(snap.seat)
    if (land_turnover_option and int(snap.step) == 0
            and getattr(snap, "seat", None) is not None):
        _clear_land_turnover_exercises(snap.seat)
    if variant == _BOUNDED_COMMITMENT_VARIANT:
        if int(snap.step) == 0:
            _clear_bounded_commitment(snap.seat)
        committed = _bounded_commitment_choice(
            snap, plan, market_orders,
        )
        if committed is not None:
            return committed
    if variant in ("crew_conditioned_phase_aligned_deterministic",
                   "crew_conditioned_fertilizer_bridge_deterministic",
                   "crew_conditioned_fertilizer_bridge_memoized_deterministic",
                   "crew_conditioned_fertilizer_reserved_memoized_deterministic",
                   "crew_conditioned_exchange_memoized_deterministic",
                   "crew_conditioned_adaptive_marginal_memoized_deterministic",
                   "crew_conditioned_intraday_memoized_deterministic",
                   "crew_conditioned_late_task_hires_deterministic",
                   "crew_conditioned_late_hires_joint_workload_deterministic",
                   "crew_conditioned_stackelberg_reinvestment_deterministic",
                   "crew_conditioned_stackelberg_land_reinvestment_deterministic",
                   "crew_conditioned_stackelberg_activated_land_deterministic",
                   "crew_conditioned_stackelberg_land_arm_deterministic",
                   "crew_conditioned_stackelberg_full_service_deterministic",
                   "crew_conditioned_positioned_manifest_deterministic",
                   "crew_conditioned_hour1_sunk_hires_deterministic",
                   "crew_conditioned_execution_aligned_deterministic",
                   "crew_conditioned_empty_farm_execution_deterministic",
                   "crew_conditioned_empty_farm_robust_tail_deterministic",
                   "crew_conditioned_incremental_manifest_hires_deterministic",
                   "crew_conditioned_empty_farm_positioned_deterministic",
                   "crew_conditioned_positioned_robust_exchange_deterministic",
                   "crew_conditioned_positioned_cash_safe_exchange_deterministic",
                   "crew_conditioned_positioned_full_response_exchange_deterministic",
                   "crew_conditioned_positioned_mixed_response_exchange_deterministic",
                   "crew_conditioned_positioned_scenario_dominant_exchange_deterministic",
                   "crew_conditioned_positioned_standing_scenario_dominant_exchange_deterministic",
                   "crew_conditioned_positioned_standing_feasible_scenario_exchange_deterministic",
                   "crew_conditioned_positioned_standing_animal_class_scenario_exchange_deterministic",
                   "crew_conditioned_positioned_standing_animal_scale_scenario_exchange_deterministic",
                   "crew_conditioned_positioned_standing_animal_rebalance_deterministic",
                   "crew_conditioned_positioned_standing_structure_rebalance_deterministic",
                   "crew_conditioned_positioned_standing_structure_robust_deterministic",
                   "crew_conditioned_positioned_standing_structure_complete_response_deterministic",
                   "crew_conditioned_positioned_scenario_crop_land_arm_deterministic",
                   "crew_conditioned_positioned_scenario_robust_crop_land_deterministic",
                   "crew_conditioned_positioned_scenario_late_land_challenger_deterministic",
                   _LATE_LAND_DEFERRED_HIRES_VARIANT,
                   _LAND_RECOVERY_COVENANT_VARIANT,
                   _FEASIBILITY_CLOSED_VARIANT,
                   _SATURATED_BOOK_VARIANT,
                   _EXACT_CAPACITY_FRONTIER_VARIANT,
                   _PRECERTIFIED_CAPACITY_FRONTIER_VARIANT,
                   _STAGED_FOLLOWER_REINVESTMENT_VARIANT,
                   _STAGED_STANDING_BOOK_VARIANT,
                   _COMPLETE_STAGED_STANDING_VARIANT,
                   _ROBUST_STAGED_REALISATION_VARIANT,
                   _STAGED_FOLLOWER_LAND_REINVESTMENT_VARIANT,
                   _STAGED_FOLLOWER_MIXED_REINVESTMENT_VARIANT,
                   _PAID_ROTATION_SUBSTITUTION_VARIANT,
                   _BACKLOGGED_ROTATION_SUBSTITUTION_VARIANT,
                   _WEED_BACKLOG_HIRES_VARIANT,
                   _SINGLE_BACKLOG_ROTATION_VARIANT,
                   "crew_conditioned_positioned_scenario_late_land_service_hires_deterministic",
                   "crew_conditioned_positioned_scenario_late_land_service_burden_deterministic",
                   "crew_conditioned_positioned_scenario_late_land_rotation_deterministic",
                   "crew_conditioned_positioned_scenario_late_land_tail_hires_deterministic",
                   "crew_conditioned_positioned_scenario_late_land_rotation_only_deterministic",
                   "crew_conditioned_positioned_scenario_late_land_deferred_rotation_deterministic",
                   "crew_conditioned_positioned_scenario_late_land_deferred_capital_deterministic",
                   "crew_conditioned_positioned_scenario_late_land_commitment_free_capital_deterministic",
                   "crew_conditioned_positioned_scenario_late_land_commitment_free_full_capital_deterministic",
                   "crew_conditioned_positioned_scenario_late_land_commitment_closed_capital_deterministic",
                   "crew_conditioned_positioned_scenario_late_land_commitment_closed_service_capital_deterministic",
                   _BOUNDED_COMMITMENT_VARIANT,
                   "crew_conditioned_positioned_scenario_late_land_herd_repair_deterministic",
                   "crew_conditioned_positioned_scenario_late_land_global_repair_deterministic",
                   "crew_conditioned_positioned_scenario_crop_land_covenant_deterministic",
                   "crew_conditioned_robust_portfolio_descent_deterministic",
                   "crew_conditioned_cashflow_backed_portfolio_deterministic",
                   "crew_conditioned_robust_service_portfolio_deterministic",
                   "crew_conditioned_frontier_portfolio_deterministic"):
        if (variant in (
                "crew_conditioned_late_task_hires_deterministic",
                "crew_conditioned_late_hires_joint_workload_deterministic",
                "crew_conditioned_positioned_scenario_late_land_service_hires_deterministic",
                )
                and int(snap.hour) != 0):
            # Re-open only the existing-task hiring master later in the day.
            # Returning None delegates to ``hiring.decide``; it cannot invent
            # or purchase another capital portfolio, so already-valued assets
            # are not credited repeatedly.
            return None
        if (variant in (
                "crew_conditioned_hour1_sunk_hires_deterministic",
                )
                and int(snap.hour) != 0):
            # Capital is proposed only at the day opening. Immediately after
            # that market phase, one exact existing-task hire solve may add
            # deployment/service workers from a fresh ten-slot queue. Later
            # hours cannot repeatedly buy another Fibonacci prefix.
            if int(snap.hour) == 1:
                return None
            fixed, _proposed = split_orders(market_orders)
            return 0, [], fixed
        if (variant in (
                "crew_conditioned_incremental_manifest_hires_deterministic",
                "crew_conditioned_positioned_scenario_late_land_rotation_deterministic",
                "crew_conditioned_positioned_scenario_late_land_tail_hires_deterministic",
                )
                and int(snap.hour) != 0):
            fixed, _proposed = split_orders(market_orders)
            hires = (_incremental_manifest_hire_choice(
                snap, plan, fixed, bank_outputs,
            ) if int(snap.hour) == 1 else 0)
            return int(hires), [], fixed
        if variant == _WEED_BACKLOG_HIRES_VARIANT and int(snap.hour) != 0:
            fixed, _proposed = split_orders(market_orders)
            hires = (_incremental_manifest_hire_choice(
                snap, plan, fixed, bank_outputs,
                allowed_kinds=("CLEAR_WEED",),
            ) if int(snap.hour) == 1 else 0)
            return int(hires), [], fixed
        if (variant in (
                "crew_conditioned_positioned_scenario_late_land_deferred_rotation_deterministic",
                "crew_conditioned_positioned_scenario_late_land_deferred_capital_deterministic",
                _LATE_LAND_DEFERRED_HIRES_VARIANT,
                _LAND_RECOVERY_COVENANT_VARIANT,
                "crew_conditioned_positioned_scenario_late_land_commitment_free_capital_deterministic",
                "crew_conditioned_positioned_scenario_late_land_commitment_free_full_capital_deterministic",
                "crew_conditioned_positioned_scenario_late_land_commitment_closed_capital_deterministic",
                "crew_conditioned_positioned_scenario_late_land_commitment_closed_service_capital_deterministic",
                _BOUNDED_COMMITMENT_VARIANT,
                )
                and int(snap.hour) != 0):
            fixed, _proposed = split_orders(market_orders)
            hires = (_certified_deferred_hire_choice(snap, plan, fixed)
                     if int(snap.hour) == 1 else 0)
            return int(hires), [], fixed
        return _decide_crew_conditioned(
            snap, plan, tasks, market_orders, bank_outputs,
            fertilizer_bridge=(
                variant in (
                    "crew_conditioned_fertilizer_bridge_deterministic",
                    "crew_conditioned_fertilizer_bridge_memoized_deterministic",
                    "crew_conditioned_fertilizer_reserved_memoized_deterministic",
                )
            ),
            memoize_proposals=(
                variant in (
                    "crew_conditioned_fertilizer_bridge_memoized_deterministic",
                    "crew_conditioned_fertilizer_reserved_memoized_deterministic",
                    "crew_conditioned_exchange_memoized_deterministic",
                    "crew_conditioned_adaptive_marginal_memoized_deterministic",
                    "crew_conditioned_intraday_memoized_deterministic",
                    "crew_conditioned_late_hires_joint_workload_deterministic",
                    "crew_conditioned_stackelberg_reinvestment_deterministic",
                    "crew_conditioned_stackelberg_land_reinvestment_deterministic",
                    "crew_conditioned_stackelberg_activated_land_deterministic",
                    "crew_conditioned_stackelberg_land_arm_deterministic",
                    "crew_conditioned_stackelberg_full_service_deterministic",
                    "crew_conditioned_positioned_scenario_crop_land_arm_deterministic",
                    "crew_conditioned_positioned_scenario_robust_crop_land_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_challenger_deterministic",
                    _LATE_LAND_DEFERRED_HIRES_VARIANT,
                    _LAND_RECOVERY_COVENANT_VARIANT,
                    _FEASIBILITY_CLOSED_VARIANT,
                    _SATURATED_BOOK_VARIANT,
                    _EXACT_CAPACITY_FRONTIER_VARIANT,
                    _PRECERTIFIED_CAPACITY_FRONTIER_VARIANT,
                    _STAGED_FOLLOWER_REINVESTMENT_VARIANT,
                    _STAGED_STANDING_BOOK_VARIANT,
                    _COMPLETE_STAGED_STANDING_VARIANT,
                    _ROBUST_STAGED_REALISATION_VARIANT,
                    _STAGED_FOLLOWER_LAND_REINVESTMENT_VARIANT,
                    _STAGED_FOLLOWER_MIXED_REINVESTMENT_VARIANT,
                    _PAID_ROTATION_SUBSTITUTION_VARIANT,
                    _BACKLOGGED_ROTATION_SUBSTITUTION_VARIANT,
                    _WEED_BACKLOG_HIRES_VARIANT,
                    _SINGLE_BACKLOG_ROTATION_VARIANT,
                    "crew_conditioned_positioned_scenario_late_land_service_hires_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_service_burden_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_rotation_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_tail_hires_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_rotation_only_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_deferred_rotation_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_deferred_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_free_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_free_full_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_closed_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_closed_service_capital_deterministic",
                    _BOUNDED_COMMITMENT_VARIANT,
                    "crew_conditioned_positioned_scenario_late_land_herd_repair_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_global_repair_deterministic",
                    "crew_conditioned_positioned_scenario_crop_land_covenant_deterministic",
                )
            ),
            reserve_visible_fertilizer=(
                variant
                == "crew_conditioned_fertilizer_reserved_memoized_deterministic"
            ),
            exchange_repair=(
                variant == "crew_conditioned_exchange_memoized_deterministic"
            ),
            adaptive_marginal=(
                variant
                == "crew_conditioned_adaptive_marginal_memoized_deterministic"
            ),
            intraday_replan=(
                variant == "crew_conditioned_intraday_memoized_deterministic"
            ),
            joint_visible_workload=(
                variant
                == "crew_conditioned_late_hires_joint_workload_deterministic"
            ),
            stackelberg=(
                variant in (
                    "crew_conditioned_stackelberg_reinvestment_deterministic",
                    "crew_conditioned_stackelberg_land_reinvestment_deterministic",
                    "crew_conditioned_stackelberg_activated_land_deterministic",
                    "crew_conditioned_stackelberg_land_arm_deterministic",
                    "crew_conditioned_stackelberg_full_service_deterministic",
                )
            ),
            land_reinvestment=(
                variant
                == "crew_conditioned_stackelberg_land_reinvestment_deterministic"
            ),
            activated_land_reinvestment=(
                variant in (
                    "crew_conditioned_stackelberg_activated_land_deterministic",
                    "crew_conditioned_stackelberg_land_arm_deterministic",
                    "crew_conditioned_stackelberg_full_service_deterministic",
                    "crew_conditioned_positioned_scenario_robust_crop_land_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_challenger_deterministic",
                    _LATE_LAND_DEFERRED_HIRES_VARIANT,
                    _LAND_RECOVERY_COVENANT_VARIANT,
                    _FEASIBILITY_CLOSED_VARIANT,
                    _SATURATED_BOOK_VARIANT,
                    _EXACT_CAPACITY_FRONTIER_VARIANT,
                    _PRECERTIFIED_CAPACITY_FRONTIER_VARIANT,
                    _STAGED_FOLLOWER_REINVESTMENT_VARIANT,
                    _STAGED_STANDING_BOOK_VARIANT,
                    _COMPLETE_STAGED_STANDING_VARIANT,
                    _ROBUST_STAGED_REALISATION_VARIANT,
                    _STAGED_FOLLOWER_LAND_REINVESTMENT_VARIANT,
                    _STAGED_FOLLOWER_MIXED_REINVESTMENT_VARIANT,
                    _PAID_ROTATION_SUBSTITUTION_VARIANT,
                    _BACKLOGGED_ROTATION_SUBSTITUTION_VARIANT,
                    _WEED_BACKLOG_HIRES_VARIANT,
                    _SINGLE_BACKLOG_ROTATION_VARIANT,
                    "crew_conditioned_positioned_scenario_late_land_service_hires_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_service_burden_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_rotation_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_tail_hires_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_rotation_only_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_deferred_rotation_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_deferred_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_free_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_free_full_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_closed_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_closed_service_capital_deterministic",
                    _BOUNDED_COMMITMENT_VARIANT,
                    "crew_conditioned_positioned_scenario_late_land_herd_repair_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_global_repair_deterministic",
                    "crew_conditioned_positioned_scenario_crop_land_covenant_deterministic",
                )
            ),
            stackelberg_arm_recertification=(
                variant
                in (
                    "crew_conditioned_stackelberg_land_arm_deterministic",
                    "crew_conditioned_stackelberg_full_service_deterministic",
                )
            ),
            full_service_continuation=(
                variant
                == "crew_conditioned_stackelberg_full_service_deterministic"
            ),
            positioned_capital_manifest=(
                variant in (
                    "crew_conditioned_positioned_manifest_deterministic",
                    "crew_conditioned_positioned_robust_exchange_deterministic",
                    "crew_conditioned_positioned_cash_safe_exchange_deterministic",
                    "crew_conditioned_positioned_full_response_exchange_deterministic",
                    "crew_conditioned_positioned_mixed_response_exchange_deterministic",
                    "crew_conditioned_positioned_scenario_dominant_exchange_deterministic",
                    "crew_conditioned_positioned_standing_scenario_dominant_exchange_deterministic",
                    "crew_conditioned_positioned_standing_feasible_scenario_exchange_deterministic",
                    "crew_conditioned_positioned_standing_animal_class_scenario_exchange_deterministic",
                    "crew_conditioned_positioned_standing_animal_scale_scenario_exchange_deterministic",
                    "crew_conditioned_positioned_standing_animal_rebalance_deterministic",
                    "crew_conditioned_positioned_standing_structure_rebalance_deterministic",
                    "crew_conditioned_positioned_standing_structure_robust_deterministic",
                    "crew_conditioned_positioned_standing_structure_complete_response_deterministic",
                    "crew_conditioned_positioned_scenario_crop_land_arm_deterministic",
                    "crew_conditioned_positioned_scenario_robust_crop_land_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_challenger_deterministic",
                    _LATE_LAND_DEFERRED_HIRES_VARIANT,
                    _LAND_RECOVERY_COVENANT_VARIANT,
                    _FEASIBILITY_CLOSED_VARIANT,
                    _SATURATED_BOOK_VARIANT,
                    _EXACT_CAPACITY_FRONTIER_VARIANT,
                    _PRECERTIFIED_CAPACITY_FRONTIER_VARIANT,
                    _STAGED_FOLLOWER_REINVESTMENT_VARIANT,
                    _STAGED_STANDING_BOOK_VARIANT,
                    _COMPLETE_STAGED_STANDING_VARIANT,
                    _ROBUST_STAGED_REALISATION_VARIANT,
                    _STAGED_FOLLOWER_LAND_REINVESTMENT_VARIANT,
                    _STAGED_FOLLOWER_MIXED_REINVESTMENT_VARIANT,
                    _PAID_ROTATION_SUBSTITUTION_VARIANT,
                    _BACKLOGGED_ROTATION_SUBSTITUTION_VARIANT,
                    _WEED_BACKLOG_HIRES_VARIANT,
                    _SINGLE_BACKLOG_ROTATION_VARIANT,
                    "crew_conditioned_positioned_scenario_late_land_service_hires_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_service_burden_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_rotation_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_tail_hires_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_rotation_only_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_deferred_rotation_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_deferred_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_free_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_free_full_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_closed_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_closed_service_capital_deterministic",
                    _BOUNDED_COMMITMENT_VARIANT,
                    "crew_conditioned_positioned_scenario_late_land_herd_repair_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_global_repair_deterministic",
                    "crew_conditioned_positioned_scenario_crop_land_covenant_deterministic",
                    "crew_conditioned_robust_portfolio_descent_deterministic",
                    "crew_conditioned_cashflow_backed_portfolio_deterministic",
                    "crew_conditioned_robust_service_portfolio_deterministic",
                    "crew_conditioned_frontier_portfolio_deterministic",
                )
            ),
            execution_aligned_crew=(
                variant
                == "crew_conditioned_execution_aligned_deterministic"
            ),
            execution_aligned_empty_farm=(
                variant in (
                    "crew_conditioned_empty_farm_execution_deterministic",
                    "crew_conditioned_empty_farm_robust_tail_deterministic",
                )
            ),
            robust_tail_repair=(
                variant
                == "crew_conditioned_empty_farm_robust_tail_deterministic"
            ),
            positioned_empty_farm_manifest=(
                variant
                == "crew_conditioned_empty_farm_positioned_deterministic"
            ),
            robust_composition_exchange=(
                variant
                == "crew_conditioned_positioned_robust_exchange_deterministic"
            ),
            cash_safe_composition_exchange=(
                variant
                == "crew_conditioned_positioned_cash_safe_exchange_deterministic"
            ),
            full_response_composition_exchange=(
                variant
                == "crew_conditioned_positioned_full_response_exchange_deterministic"
            ),
            mixed_response_composition_exchange=(
                variant
                == "crew_conditioned_positioned_mixed_response_exchange_deterministic"
            ),
            scenario_dominant_composition_exchange=(
                variant in (
                    "crew_conditioned_positioned_scenario_dominant_exchange_deterministic",
                    "crew_conditioned_positioned_standing_scenario_dominant_exchange_deterministic",
                    "crew_conditioned_positioned_standing_feasible_scenario_exchange_deterministic",
                    "crew_conditioned_positioned_standing_animal_class_scenario_exchange_deterministic",
                    "crew_conditioned_positioned_standing_animal_scale_scenario_exchange_deterministic",
                    "crew_conditioned_positioned_standing_animal_rebalance_deterministic",
                    "crew_conditioned_positioned_standing_structure_rebalance_deterministic",
                    "crew_conditioned_positioned_standing_structure_robust_deterministic",
                    "crew_conditioned_positioned_standing_structure_complete_response_deterministic",
                    "crew_conditioned_positioned_scenario_crop_land_arm_deterministic",
                    "crew_conditioned_positioned_scenario_robust_crop_land_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_challenger_deterministic",
                    _LATE_LAND_DEFERRED_HIRES_VARIANT,
                    _LAND_RECOVERY_COVENANT_VARIANT,
                    _FEASIBILITY_CLOSED_VARIANT,
                    _SATURATED_BOOK_VARIANT,
                    _EXACT_CAPACITY_FRONTIER_VARIANT,
                    _PRECERTIFIED_CAPACITY_FRONTIER_VARIANT,
                    _STAGED_FOLLOWER_REINVESTMENT_VARIANT,
                    _STAGED_STANDING_BOOK_VARIANT,
                    _COMPLETE_STAGED_STANDING_VARIANT,
                    _ROBUST_STAGED_REALISATION_VARIANT,
                    _STAGED_FOLLOWER_LAND_REINVESTMENT_VARIANT,
                    _STAGED_FOLLOWER_MIXED_REINVESTMENT_VARIANT,
                    _PAID_ROTATION_SUBSTITUTION_VARIANT,
                    _BACKLOGGED_ROTATION_SUBSTITUTION_VARIANT,
                    _WEED_BACKLOG_HIRES_VARIANT,
                    _SINGLE_BACKLOG_ROTATION_VARIANT,
                    "crew_conditioned_positioned_scenario_late_land_service_hires_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_service_burden_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_rotation_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_tail_hires_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_rotation_only_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_deferred_rotation_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_deferred_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_free_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_free_full_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_closed_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_closed_service_capital_deterministic",
                    _BOUNDED_COMMITMENT_VARIANT,
                    "crew_conditioned_positioned_scenario_late_land_herd_repair_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_global_repair_deterministic",
                    "crew_conditioned_positioned_scenario_crop_land_covenant_deterministic",
                )
            ),
            robust_portfolio_descent=(
                variant in (
                    "crew_conditioned_robust_portfolio_descent_deterministic",
                    "crew_conditioned_cashflow_backed_portfolio_deterministic",
                    "crew_conditioned_robust_service_portfolio_deterministic",
                    "crew_conditioned_frontier_portfolio_deterministic",
                )
            ),
            cashflow_backed_service_hiring=(
                variant
                == "crew_conditioned_cashflow_backed_portfolio_deterministic"
            ),
            robust_service_without_fertilizer=(
                variant in (
                    "crew_conditioned_robust_service_portfolio_deterministic",
                    "crew_conditioned_frontier_portfolio_deterministic",
                )
            ),
            crew_frontier_portfolio_descent=(
                variant
                == "crew_conditioned_frontier_portfolio_deterministic"
            ),
            standing_book_composition_exchange=(
                variant in (
                    "crew_conditioned_positioned_standing_scenario_dominant_exchange_deterministic",
                    "crew_conditioned_positioned_standing_feasible_scenario_exchange_deterministic",
                    "crew_conditioned_positioned_standing_animal_class_scenario_exchange_deterministic",
                    "crew_conditioned_positioned_standing_animal_scale_scenario_exchange_deterministic",
                    _STAGED_STANDING_BOOK_VARIANT,
                    _COMPLETE_STAGED_STANDING_VARIANT,
                )
            ),
            feasible_cash_scenario_composition_exchange=(
                variant
                in (
                    "crew_conditioned_positioned_standing_feasible_scenario_exchange_deterministic",
                    "crew_conditioned_positioned_standing_animal_class_scenario_exchange_deterministic",
                    "crew_conditioned_positioned_standing_animal_scale_scenario_exchange_deterministic",
                )
            ),
            same_asset_class_composition_exchange=(
                (bool(single_quadrant_asset_class_exchange)
                 and len(snap.me.unlocked) == 1)
                or (bool(opening_asset_class_exchange)
                    and int(snap.step) == 0)
                or variant in (
                    "crew_conditioned_positioned_standing_animal_class_scenario_exchange_deterministic",
                    "crew_conditioned_positioned_standing_animal_scale_scenario_exchange_deterministic",
                )
            ),
            allow_animal_idle_composition_exchange=(
                variant
                == "crew_conditioned_positioned_standing_animal_scale_scenario_exchange_deterministic"
            ),
            standing_animal_rebalance_after_scenario=(
                variant
                == "crew_conditioned_positioned_standing_animal_rebalance_deterministic"
            ),
            standing_structure_rebalance_after_scenario=(
                variant
                == "crew_conditioned_positioned_standing_structure_rebalance_deterministic"
            ),
            standing_structure_robust_after_scenario=(
                variant
                == "crew_conditioned_positioned_standing_structure_robust_deterministic"
            ),
            standing_structure_complete_response_after_scenario=(
                variant
                == "crew_conditioned_positioned_standing_structure_complete_response_deterministic"
            ),
            crop_only_land_arm=(
                variant in (
                    "crew_conditioned_positioned_scenario_crop_land_arm_deterministic",
                    "crew_conditioned_positioned_scenario_robust_crop_land_deterministic",
                )
            ),
            robust_crop_land_gate=(
                variant
                == "crew_conditioned_positioned_scenario_robust_crop_land_deterministic"
            ),
            late_crop_land_challenger=(
                variant in (
                    "crew_conditioned_positioned_scenario_late_land_challenger_deterministic",
                    _LATE_LAND_DEFERRED_HIRES_VARIANT,
                    _LAND_RECOVERY_COVENANT_VARIANT,
                    _FEASIBILITY_CLOSED_VARIANT,
                    _SATURATED_BOOK_VARIANT,
                    _EXACT_CAPACITY_FRONTIER_VARIANT,
                    _PRECERTIFIED_CAPACITY_FRONTIER_VARIANT,
                    _STAGED_FOLLOWER_REINVESTMENT_VARIANT,
                    _STAGED_STANDING_BOOK_VARIANT,
                    _COMPLETE_STAGED_STANDING_VARIANT,
                    _ROBUST_STAGED_REALISATION_VARIANT,
                    _STAGED_FOLLOWER_LAND_REINVESTMENT_VARIANT,
                    _STAGED_FOLLOWER_MIXED_REINVESTMENT_VARIANT,
                    _PAID_ROTATION_SUBSTITUTION_VARIANT,
                    _BACKLOGGED_ROTATION_SUBSTITUTION_VARIANT,
                    _WEED_BACKLOG_HIRES_VARIANT,
                    _SINGLE_BACKLOG_ROTATION_VARIANT,
                    "crew_conditioned_positioned_scenario_late_land_service_hires_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_service_burden_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_rotation_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_tail_hires_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_rotation_only_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_deferred_rotation_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_deferred_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_free_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_free_full_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_closed_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_closed_service_capital_deterministic",
                    _BOUNDED_COMMITMENT_VARIANT,
                    "crew_conditioned_positioned_scenario_late_land_herd_repair_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_global_repair_deterministic",
                    "crew_conditioned_positioned_scenario_crop_land_covenant_deterministic",
                )
            ),
            late_land_animal_scale_repair=(
                variant
                == "crew_conditioned_positioned_scenario_late_land_herd_repair_deterministic"
            ),
            late_land_global_scale_repair=(
                variant
                == "crew_conditioned_positioned_scenario_late_land_global_repair_deterministic"
            ),
            crop_land_covenant_repair=(
                variant
                == "crew_conditioned_positioned_scenario_crop_land_covenant_deterministic"
            ),
            late_land_service_burden_repair=(
                variant
                == "crew_conditioned_positioned_scenario_late_land_service_burden_deterministic"
            ),
            late_empty_crop_challenger=(
                variant in (
                    "crew_conditioned_positioned_scenario_late_land_rotation_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_rotation_only_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_deferred_rotation_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_deferred_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_free_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_free_full_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_closed_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_closed_service_capital_deterministic",
                    _BOUNDED_COMMITMENT_VARIANT,
                )
            ),
            deferred_crop_hires=(
                variant in (
                    "crew_conditioned_positioned_scenario_late_land_deferred_rotation_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_deferred_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_free_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_free_full_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_closed_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_closed_service_capital_deterministic",
                    _BOUNDED_COMMITMENT_VARIANT,
                )
            ),
            deferred_land_hires=(
                variant in (
                    _LATE_LAND_DEFERRED_HIRES_VARIANT,
                    _LAND_RECOVERY_COVENANT_VARIANT,
                )
            ),
            land_recovery_covenant=(
                variant == _LAND_RECOVERY_COVENANT_VARIANT
            ),
            deferred_capital_option=(
                variant in (
                    "crew_conditioned_positioned_scenario_late_land_deferred_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_free_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_free_full_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_closed_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_closed_service_capital_deterministic",
                    _BOUNDED_COMMITMENT_VARIANT,
                )
            ),
            deferred_capital_full_continuation=(
                variant in (
                    "crew_conditioned_positioned_scenario_late_land_commitment_free_full_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_closed_capital_deterministic",
                )
            ),
            close_empty_deferred_baseline=(
                variant in (
                    "crew_conditioned_positioned_scenario_late_land_commitment_closed_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_closed_service_capital_deterministic",
                    _BOUNDED_COMMITMENT_VARIANT,
                )
            ),
            deferred_standing_service_horizon=(
                variant in (
                    "crew_conditioned_positioned_scenario_late_land_commitment_closed_service_capital_deterministic",
                    _BOUNDED_COMMITMENT_VARIANT,
                )
            ),
            bounded_first_output_only=(
                variant in (
                    "crew_conditioned_positioned_scenario_late_land_commitment_closed_service_capital_deterministic",
                    _BOUNDED_COMMITMENT_VARIANT,
                )
            ),
            suppress_uncommitted_rotation=(
                variant in (
                    "crew_conditioned_positioned_scenario_late_land_commitment_free_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_free_full_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_closed_capital_deterministic",
                    "crew_conditioned_positioned_scenario_late_land_commitment_closed_service_capital_deterministic",
                    _BOUNDED_COMMITMENT_VARIANT,
                )
            ),
            execute_bounded_commitment=(
                variant == _BOUNDED_COMMITMENT_VARIANT
            ),
            close_infeasible_capital=(
                variant == _FEASIBILITY_CLOSED_VARIANT
            ),
            saturated_standing_book_gate=(
                variant in (
                    _SATURATED_BOOK_VARIANT,
                    _EXACT_CAPACITY_FRONTIER_VARIANT,
                    _PRECERTIFIED_CAPACITY_FRONTIER_VARIANT,
                )
            ),
            exact_capacity_frontier=(
                variant in (
                    _EXACT_CAPACITY_FRONTIER_VARIANT,
                    _PRECERTIFIED_CAPACITY_FRONTIER_VARIANT,
                )
            ),
            precertified_capacity_frontier=(
                variant == _PRECERTIFIED_CAPACITY_FRONTIER_VARIANT
            ),
            staged_opponent_reinvestment=(
                variant in (
                    _STAGED_FOLLOWER_REINVESTMENT_VARIANT,
                    _STAGED_STANDING_BOOK_VARIANT,
                    _COMPLETE_STAGED_STANDING_VARIANT,
                    _ROBUST_STAGED_REALISATION_VARIANT,
                    _STAGED_FOLLOWER_LAND_REINVESTMENT_VARIANT,
                    _STAGED_FOLLOWER_MIXED_REINVESTMENT_VARIANT,
                )
            ),
            complete_opponent_response_products=(
                variant == _COMPLETE_STAGED_STANDING_VARIANT
            ),
            robust_own_standing_realisation=(
                variant == _ROBUST_STAGED_REALISATION_VARIANT
            ),
            staged_opponent_land_reinvestment=(
                variant == _STAGED_FOLLOWER_LAND_REINVESTMENT_VARIANT
            ),
            staged_opponent_mixed_reinvestment=(
                variant == _STAGED_FOLLOWER_MIXED_REINVESTMENT_VARIANT
            ),
            paid_rotation_substitution=(
                variant == _PAID_ROTATION_SUBSTITUTION_VARIANT
            ),
            backlogged_rotation_substitution=(
                variant == _BACKLOGGED_ROTATION_SUBSTITUTION_VARIANT
            ),
            single_backlog_rotation_substitution=(
                variant == _SINGLE_BACKLOG_ROTATION_VARIANT
            ),
            productive_shed_relocation=bool(productive_shed_relocation),
            service_cluster_layout=bool(service_cluster_layout),
            land_turnover_option=bool(land_turnover_option),
            bounded_land_quantity_frontier=bool(
                bounded_land_quantity_frontier
            ),
            crop_rotation_reinvestment=bool(crop_rotation_reinvestment),
            joint_standing_capital=bool(joint_standing_capital),
            joint_standing_portfolio_gate=bool(
                joint_standing_portfolio_gate
            ),
            land_frontier_certificate=bool(land_frontier_certificate),
            opening_animal_retention=bool(opening_animal_retention),
            turnover_positions=turnover_positions,
            turnover_items_by_position=turnover_items_by_position,
        )
    fixed, proposed = split_orders(market_orders)
    # V64's exchange constructor and this hour-0 master are both structurally
    # finite. Letting wall-clock contention truncate the latter made an exact
    # exchange produce different actions in its own mirror. Non-hour-0 work and
    # every historical variant retain the shared emergency deadline.
    solve_deadline = (
        None
        if (variant in ("ordinary_bundle_master_deterministic",
                        "ordinary_bundle_master_memoized_deterministic",
                        "ordinary_complete_tiles_bundle_master_memoized_deterministic",
                        "paired_phase_bundle_master_memoized_deterministic",
                        "temporal_paired_bundle_master_memoized_deterministic",
                        "temporal_recertified_bundle_memoized_deterministic",
                        "first_output_prefix_master_memoized_deterministic",
                        "exact_first_output_master_memoized_deterministic",
                        "joint_farm_prefix_master_memoized_deterministic",
                        "optional_continuation_master_memoized_deterministic",
                        "deadline_phase_validation_deterministic",
                        "productive_inventory_certificate_deterministic",
                        "productive_inventory_path_deterministic",
                        "productive_feasibility_oracle_deterministic",
                        "productive_postselection_repair_deterministic",
                        "ordinary_bundle_master_refined_deterministic",
                        "ordinary_bundle_master_cash_sales_deterministic",
                        "certified_bundle_master_deterministic",
                        "certified_marginal_master_deterministic",
                        "certified_marginal_phase_deterministic",
                        "phase_aligned_certificate_deterministic")
            or (variant == "cashflow_exchange" and snap.hour == 0))
        else deadline
    )
    if router.deadline_expired(solve_deadline):
        return 0, [], fixed
    proposal_certificate = None
    if variant == "endogenous":
        proposed = _endogenous_proposal(snap, proposed)
    elif variant in ("cashflow_portfolio", "cashflow_execute",
                     "cashflow_shared", "cashflow_paired",
                     "cashflow_exchange",
                     "certified_bundle_master_deterministic",
                     "certified_marginal_master_deterministic",
                     "certified_marginal_phase_deterministic",
                     "phase_aligned_certificate_deterministic",
                     "first_output_prefix_master_memoized_deterministic",
                     "exact_first_output_master_memoized_deterministic",
                     "joint_farm_prefix_master_memoized_deterministic",
                     "optional_continuation_master_memoized_deterministic"):
        # Keep the complete finite deterministic masters clock-independent.
        # Economy MPC cadence is once per day. Assets bought in the market
        # phase cannot be used by the unit actions already chosen this step;
        # the certificate consequently starts service no earlier than the next
        # modelled day, and emits no opportunistic intraday capital purchase.
        if snap.hour == 0:
            from whitebox import cashflow as _cashflow
            if variant in ("certified_bundle_master_deterministic",
                            "certified_marginal_master_deterministic",
                            "certified_marginal_phase_deterministic",
                            "phase_aligned_certificate_deterministic"):
                blocked = {tuple(task.pos) for task in tasks}
                proposed, proposal_certificate = _cashflow.invent_paired_proposal(
                    snap, fixed_orders=fixed,
                    reserve=max(0.0, float(plan.cash_floor)),
                    reserve_inventory=False, blocked_positions=blocked,
                    phase_aligned=(
                        variant == "phase_aligned_certificate_deterministic"
                    ),
                )
            elif variant == "first_output_prefix_master_memoized_deterministic":
                blocked = {tuple(task.pos) for task in tasks}
                proposed, proposal_certificate = (
                    _cashflow.invent_first_output_proposal(
                        snap, fixed_orders=fixed,
                        reserve=max(0.0, float(plan.cash_floor)),
                        blocked_positions=blocked,
                    )
                )
            elif variant == "exact_first_output_master_memoized_deterministic":
                blocked = {tuple(task.pos) for task in tasks}
                proposed, proposal_certificate = (
                    _cashflow.invent_exact_first_output_proposal(
                        snap, fixed_orders=fixed,
                        reserve=max(0.0, float(plan.cash_floor)),
                        blocked_positions=blocked,
                    )
                )
            elif variant == "joint_farm_prefix_master_memoized_deterministic":
                blocked = {tuple(task.pos) for task in tasks}
                proposed, proposal_certificate = (
                    _cashflow.invent_joint_farm_prefix_proposal(
                        snap, fixed_orders=fixed,
                        reserve=max(0.0, float(plan.cash_floor)),
                        blocked_positions=blocked,
                    )
                )
            elif variant == "optional_continuation_master_memoized_deterministic":
                blocked = {tuple(task.pos) for task in tasks}
                proposed, proposal_certificate = (
                    _cashflow.invent_optional_continuation_proposal(
                        snap, fixed_orders=fixed,
                        reserve=max(0.0, float(plan.cash_floor)),
                        blocked_positions=blocked,
                    )
                )
            elif variant in ("cashflow_paired", "cashflow_exchange"):
                inventor = (_cashflow.invent_exchange_proposal
                            if variant == "cashflow_exchange"
                            else _cashflow.invent_paired_proposal)
                proposed, _certificate = inventor(
                    snap, fixed_orders=fixed,
                    reserve=max(0.0, float(plan.cash_floor)),
                    reserve_inventory=True,
                )
            else:
                proposed, _certificate = _cashflow.invent_proposal(
                    snap, fixed_orders=fixed,
                    reserve=max(0.0, float(plan.cash_floor)),
                    reserve_inventory=(variant in ("cashflow_execute",
                                                   "cashflow_shared")),
                    shared_routes=(variant == "cashflow_shared"),
                )
        else:
            proposed = []
    columns, proposed_animals = capital_tasks(
        snap, proposed, tasks,
        joint_alternatives=(variant in ("joint_tiles", "endogenous")),
        complete_alternatives=(variant in (
            "complete_tiles",
            "ordinary_complete_tiles_bundle_master_memoized_deterministic",
        )),
        positions_by_item=(proposal_certificate.positions_by_item
                           if proposal_certificate is not None else None),
    )
    bundle_terms = {}
    if variant in ("bundle_values", "bundle_recertify", "phase_correct",
                   "phase_idle", "phase_snapshot",
                   "cashflow_portfolio", "cashflow_execute",
                   "cashflow_shared", "cashflow_paired",
                   "cashflow_exchange"):
        bundle_terms = _capital_bundle_terms(snap, columns)
        _bundle_reprice_capital(snap, columns, terms=bundle_terms)
    proposed_seeds, proposed_animals_limit, _buy_land = _proposal_counts(proposed)
    selection_limits = None
    if variant in ("complete_tiles",
                   "ordinary_complete_tiles_bundle_master_memoized_deterministic",
                   "certified_bundle_master_deterministic",
                   "certified_marginal_master_deterministic",
                   "certified_marginal_phase_deterministic",
                   "phase_aligned_certificate_deterministic",
                   "first_output_prefix_master_memoized_deterministic",
                   "exact_first_output_master_memoized_deterministic",
                   "joint_farm_prefix_master_memoized_deterministic",
                   "optional_continuation_master_memoized_deterministic"):
        selection_limits = {
            **{("BUY_SEED", crop): int(qty)
               for crop, qty in proposed_seeds.items()},
            **{("BUY_ANIMAL", kind): int(qty)
               for kind, qty in proposed_animals_limit.items()},
        }

    crew_reserve = econ.hire_block_cost(0, 5)
    protected = max(0.0, float(plan.cash_floor) - crew_reserve)
    sale_cash = 0.0
    if variant == "ordinary_bundle_master_cash_sales_deterministic":
        from whitebox import market as _market
        sale_cash = _market.robust_sale_cash(snap, fixed)
    available = max(
        0.0, float(snap.me.money) + sale_cash - protected
        - _fixed_spend(snap, fixed)
    )
    retained_fixed = [list(order) for order in fixed
                      if not order or order[0] != "SELL"]
    feasibility_sale_arms = [(0, fixed, True)]
    if (variant == "productive_feasibility_oracle_deterministic"
            and len(retained_fixed) != len(fixed)):
        feasibility_sale_arms.append((1, retained_fixed, False))
    fixed_slot_floor = min(len(arm_fixed)
                           for _rank, arm_fixed, _sell in feasibility_sale_arms)
    room = max(0, min(econ.MAX_ORDERS - fixed_slot_floor,
                      hiring.MAX_HANDS - len(snap.me.hands)))
    if snap.hour + 1 >= econ.TURNS_PER_DAY:
        room = 0

    stock = objective.planned_shed_stock(snap, plan)
    for kind, qty in proposed_animals.items():
        stock[kind] = int(stock.get(kind, 0) or 0) + int(qty)

    all_tasks = list(tasks) + columns
    if variant in ("certified_marginal_master_deterministic",
                   "certified_marginal_phase_deterministic"):
        joint_bundle_model = PositionedCertificateObjective(
            snap, all_tasks, fixed,
            reserve=max(0.0, float(plan.cash_floor)),
        )
    elif variant == "first_output_prefix_master_memoized_deterministic":
        joint_bundle_model = FirstOutputPrefixObjective(
            snap, all_tasks, fixed,
            reserve=max(0.0, float(plan.cash_floor)),
        )
    elif variant == "exact_first_output_master_memoized_deterministic":
        joint_bundle_model = ExactFirstOutputObjective(
            snap, all_tasks, fixed,
            reserve=max(0.0, float(plan.cash_floor)),
        )
    elif variant == "joint_farm_prefix_master_memoized_deterministic":
        joint_bundle_model = JointFarmPrefixObjective(
            snap, all_tasks, fixed,
            reserve=max(0.0, float(plan.cash_floor)),
        )
    elif variant == "optional_continuation_master_memoized_deterministic":
        joint_bundle_model = OptionalContinuationObjective(
            snap, all_tasks, fixed,
            reserve=max(0.0, float(plan.cash_floor)),
        )
    elif variant in ("productive_inventory_certificate_deterministic",
                     "productive_inventory_path_deterministic"):
        model_class = (ProductiveInventoryPathObjective
                       if variant == "productive_inventory_path_deterministic"
                       else ProductiveInventoryCertificateObjective)
        joint_bundle_model = model_class(
            snap, all_tasks, fixed, reserve=protected,
        )
    elif variant in ("ordinary_bundle_master",
                     "ordinary_bundle_master_deterministic",
                     "ordinary_bundle_master_memoized_deterministic",
                     "ordinary_complete_tiles_bundle_master_memoized_deterministic",
                     "paired_phase_bundle_master_memoized_deterministic",
                     "temporal_paired_bundle_master_memoized_deterministic",
                     "temporal_recertified_bundle_memoized_deterministic",
                     "deadline_phase_validation_deterministic",
                     "productive_postselection_repair_deterministic",
                     "ordinary_bundle_master_refined_deterministic",
                     "ordinary_bundle_master_cash_sales_deterministic",
                     "certified_bundle_master_deterministic"):
        joint_bundle_model = (
            objective.TemporalPairedTaskBundleObjective(snap, all_tasks)
            if variant == "temporal_paired_bundle_master_memoized_deterministic"
            else objective.TaskBundleObjective(
                snap, all_tasks,
                paired_phase=(
                    variant
                    == "paired_phase_bundle_master_memoized_deterministic"
                ),
            )
        )
    else:
        joint_bundle_model = None
    ordinary_bundle_model = (
        objective.TaskBundleObjective(snap, tasks)
        if variant == "certified_bundle_master_deterministic" else None
    )
    # V97 keeps V89's fast exact nonlinear route construction, then reprices
    # only the actual executable task set selected for each hire/activation
    # branch on the dated persistent book. This is route trim followed by
    # quantity recertification: proposed or rejected columns never enter the
    # branch score, and the expensive temporal equation is not a greedy-key
    # oracle evaluated for every candidate insertion.
    temporal_recertification_model = (
        objective.TemporalPairedTaskBundleObjective(snap, all_tasks)
        if variant == "temporal_recertified_bundle_memoized_deterministic"
        else None
    )
    task_sets = (_activation_task_sets(all_tasks)
                 if charge_activation_cost else [all_tasks])
    best = None
    phase_certificate_cache = (
        {} if variant == "phase_aligned_certificate_deterministic" else None
    )
    feasibility_certificate_caches = (
        {rank: {} for rank, _fixed, _sell in feasibility_sale_arms}
        if variant == "productive_feasibility_oracle_deterministic" else None
    )
    repair_certificate_cache = (
        {} if variant == "productive_postselection_repair_deterministic"
        else None
    )
    prefix_certificate_cache = (
        {} if variant in (
            "first_output_prefix_master_memoized_deterministic",
            "exact_first_output_master_memoized_deterministic",
            "joint_farm_prefix_master_memoized_deterministic",
            "optional_continuation_master_memoized_deterministic",
        )
        else None
    )
    for k in range(room + 1):
        if k > 0 and router.deadline_expired(solve_deadline):
            break
        hire_cost = float(econ.hire_block_cost(snap.me.hires_today, k))
        if hire_cost > available:
            break
        sale_arms = (feasibility_sale_arms
                     if variant == "productive_feasibility_oracle_deterministic"
                     else [(0, fixed, True)])
        for sale_rank, arm_fixed, sell_now in sale_arms:
            if k + len(arm_fixed) > econ.MAX_ORDERS:
                continue
            purchase_slots = econ.MAX_ORDERS - len(arm_fixed) - k
            active_bundle_model = joint_bundle_model
            if variant == "phase_aligned_certificate_deterministic":
                # Requiring reserve+current hire cost in the certificate is
                # exactly equivalent to subtracting this market-phase hire
                # before every future bridge-cash check. Hire value itself is
                # still charged once outside the capital objective.
                active_bundle_model = PositionedCertificateObjective(
                    snap, all_tasks, fixed,
                    reserve=max(0.0, float(plan.cash_floor)) + hire_cost,
                    phase_aligned=True,
                    certificate_cache=phase_certificate_cache,
                )
            elif variant == "productive_feasibility_oracle_deterministic":
                # The current hire executes before every future service bill.
                # Raising the proof reserve by its exact Fibonacci block cost
                # subtracts it from every daily cash checkpoint once.
                active_bundle_model = ProductiveFeasibilityObjective(
                    snap, all_tasks, fixed, arm_fixed,
                    reserve=protected + hire_cost, sell_now=sell_now,
                    certificate_cache=feasibility_certificate_caches[sale_rank],
                )
            elif variant == "first_output_prefix_master_memoized_deterministic":
                # The current hire is paid in the same market phase as the
                # assets. Raising every prefix checkpoint by its exact block
                # cost is equivalent to subtracting that irreversible spend.
                active_bundle_model = FirstOutputPrefixObjective(
                    snap, all_tasks, fixed,
                    reserve=max(0.0, float(plan.cash_floor)) + hire_cost,
                    certificate_cache=prefix_certificate_cache,
                )
            elif variant == "exact_first_output_master_memoized_deterministic":
                active_bundle_model = ExactFirstOutputObjective(
                    snap, all_tasks, fixed,
                    reserve=max(0.0, float(plan.cash_floor)) + hire_cost,
                    certificate_cache=prefix_certificate_cache,
                )
            elif variant == "joint_farm_prefix_master_memoized_deterministic":
                active_bundle_model = JointFarmPrefixObjective(
                    snap, all_tasks, fixed,
                    reserve=max(0.0, float(plan.cash_floor)) + hire_cost,
                    certificate_cache=prefix_certificate_cache,
                )
            elif variant == "optional_continuation_master_memoized_deterministic":
                active_bundle_model = OptionalContinuationObjective(
                    snap, all_tasks, fixed,
                    reserve=max(0.0, float(plan.cash_floor)) + hire_cost,
                    certificate_cache=prefix_certificate_cache,
                )
            for branch_idx, branch_tasks in enumerate(task_sets):
                assignment, _left = router.joint_assign(
                    branch_tasks, _units(
                        snap, k, unit_actions,
                        post_action=(
                            variant in (
                                "phase_correct", "phase_snapshot",
                                "certified_marginal_phase_deterministic",
                                "phase_aligned_certificate_deterministic",
                            ) or (variant == "phase_idle"
                                  and _idle_unit_phase(unit_actions))
                        ),
                        already_projected=(variant in (
                            "phase_snapshot",
                            "certified_marginal_phase_deterministic",
                            "phase_aligned_certificate_deterministic",
                        )),
                    ), stock,
                    cash_budget=available - hire_cost,
                    max_order_keys=purchase_slots,
                    deadline=solve_deadline,
                    refine=(
                        variant == "ordinary_bundle_master_refined_deterministic"
                    ),
                    selection_limits=selection_limits,
                    bank_outputs=bank_outputs,
                    bundle_model=active_bundle_model,
                    memoize_route_cost=(
                        variant in (
                            "ordinary_bundle_master_memoized_deterministic",
                            "ordinary_complete_tiles_bundle_master_memoized_deterministic",
                            "paired_phase_bundle_master_memoized_deterministic",
                            "temporal_paired_bundle_master_memoized_deterministic",
                            "temporal_recertified_bundle_memoized_deterministic",
                            "first_output_prefix_master_memoized_deterministic",
                            "exact_first_output_master_memoized_deterministic",
                            "joint_farm_prefix_master_memoized_deterministic",
                            "optional_continuation_master_memoized_deterministic",
                            "deadline_phase_validation_deterministic",
                            "productive_inventory_certificate_deterministic",
                            "productive_inventory_path_deterministic",
                            "productive_feasibility_oracle_deterministic",
                            "productive_postselection_repair_deterministic",
                        )
                    ),
                )
                chosen = _selected(assignment)
                if variant in ("productive_inventory_certificate_deterministic",
                               "productive_inventory_path_deterministic"):
                    score = active_bundle_model.score(chosen) - hire_cost
                elif variant == "productive_feasibility_oracle_deterministic":
                    score = (active_bundle_model.score(chosen) - hire_cost
                             - (_activation_cost(chosen)
                                if charge_activation_cost else 0.0))
                elif variant == "productive_postselection_repair_deterministic":
                    auditor = ProductiveFeasibilityObjective(
                        snap, all_tasks, fixed, fixed,
                        reserve=protected + hire_cost, sell_now=True,
                        certificate_cache=repair_certificate_cache,
                    )
                    chosen = repair_productive_selection(
                        chosen, auditor, joint_bundle_model,
                        charge_activation_cost,
                    )
                    score = (joint_bundle_model.score(chosen) - hire_cost
                             - (_activation_cost(chosen)
                                if charge_activation_cost else 0.0))
                elif variant == "deadline_phase_validation_deterministic":
                    chosen = validate_deadline_capital(
                        snap, chosen, k, unit_actions, joint_bundle_model,
                        bank_outputs=bank_outputs,
                    )
                    score = (joint_bundle_model.score(chosen) - hire_cost
                             - (_activation_cost(chosen)
                                if charge_activation_cost else 0.0))
                elif variant in ("certified_marginal_master_deterministic",
                               "certified_marginal_phase_deterministic",
                               "phase_aligned_certificate_deterministic",
                               "first_output_prefix_master_memoized_deterministic",
                               "exact_first_output_master_memoized_deterministic",
                               "joint_farm_prefix_master_memoized_deterministic",
                               "optional_continuation_master_memoized_deterministic"):
                    score = active_bundle_model.score(chosen) - hire_cost
                elif variant == "temporal_recertified_bundle_memoized_deterministic":
                    score = (temporal_recertification_model.score(chosen)
                             - hire_cost
                             - (_activation_cost(chosen)
                                if charge_activation_cost else 0.0))
                elif variant == "certified_bundle_master_deterministic":
                    score = _positioned_paired_recertified_score(
                        snap, chosen, fixed,
                        reserve=max(0.0, float(plan.cash_floor)),
                        ordinary_model=ordinary_bundle_model,
                        hire_cost=hire_cost,
                    )
                elif variant in ("ordinary_bundle_master",
                               "ordinary_bundle_master_deterministic",
                               "ordinary_bundle_master_memoized_deterministic",
                               "ordinary_complete_tiles_bundle_master_memoized_deterministic",
                               "paired_phase_bundle_master_memoized_deterministic",
                               "temporal_paired_bundle_master_memoized_deterministic",
                               "deadline_phase_validation_deterministic",
                               "ordinary_bundle_master_refined_deterministic",
                               "ordinary_bundle_master_cash_sales_deterministic"):
                    score = (joint_bundle_model.score(chosen) - hire_cost
                             - (_activation_cost(chosen)
                                if charge_activation_cost else 0.0))
                elif variant in ("cashflow_paired", "cashflow_exchange"):
                    score = _paired_recertified_score(
                        snap, chosen, fixed,
                        reserve=max(0.0, float(plan.cash_floor)),
                        hire_cost=hire_cost,
                    )
                elif variant in ("bundle_recertify", "phase_correct", "phase_idle",
                                 "phase_snapshot",
                                 "cashflow_portfolio",
                                 "cashflow_execute", "cashflow_shared"):
                    score = _recertified_net_score(
                        snap, chosen, bundle_terms, hire_cost,
                        charge_activation_cost,
                    )
                else:
                    score = _net_score(chosen, hire_cost, charge_activation_cost)
                capital_cash, keys = router._capital_usage(chosen)
                if variant == "productive_feasibility_oracle_deterministic":
                    key = (-score, hire_cost + capital_cash, k, len(keys),
                           sale_rank, branch_idx)
                else:
                    key = (-score, hire_cost + capital_cash, k, len(keys),
                           branch_idx)
                if best is None or key < best[0]:
                    chosen_fixed = (
                        active_bundle_model.fixed_orders_for(chosen)
                        if variant in (
                            "productive_inventory_certificate_deterministic",
                            "productive_inventory_path_deterministic",
                            "productive_feasibility_oracle_deterministic",
                        )
                        else fixed
                    )
                    best = (key, k, chosen, chosen_fixed)
                if router.deadline_expired(solve_deadline):
                    break
            if router.deadline_expired(solve_deadline):
                break
        if router.deadline_expired(solve_deadline):
            break

    if best is None:
        return 0, [], fixed
    _key, hires, chosen, chosen_fixed = best
    return hires, _asset_orders(chosen, proposed), chosen_fixed
