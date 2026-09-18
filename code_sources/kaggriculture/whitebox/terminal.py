"""State-derived terminal collection and liquidation certificate.

This module is opt-in.  Historical versions keep their measured fixed-window
collector.  The certificate below uses only the current observation and engine
rules: it becomes eligible after the last possible daily refresh, constructs a
complete closed trip schedule for every currently harvestable tile, proves the
schedule fits the remaining unit actions and current shed capacity, and emits
only the first action of that certified schedule.
"""
from collections import Counter

from whitebox import econ, paths, state


class TerminalCertificate:
    __slots__ = ("feasible", "reason", "routes", "actions", "outputs",
                 "opponent_upper", "paired_value", "remaining_actions",
                 "max_route_actions")

    def __init__(self, remaining_actions):
        self.feasible = False
        self.reason = "not_certified"
        self.routes = {}
        self.actions = []
        self.outputs = {}
        self.opponent_upper = {}
        self.paired_value = 0.0
        self.remaining_actions = int(remaining_actions)
        self.max_route_actions = 0


def production_closed(snap):
    """Whether no engine end-of-day production refresh can still execute."""
    # An action at the last hour of a day refreshes production after unit and
    # market commits.  The next such action is `(day + 1) * turns - 1`; if it is
    # beyond the engine's last action, WATER/FEED/CARE cannot create another
    # terminal unit.  This is a transition equation, not a takeover window.
    next_refresh_action = ((int(snap.day) + 1) * econ.TURNS_PER_DAY) - 1
    return next_refresh_action > state.LAST_STEP


def _units(snap):
    positions = [tuple(snap.me.farmer)]
    positions.extend(tuple(pos) for pos in snap.me.hands)
    inventories = list(snap.inventories)
    inventories.extend({} for _ in range(max(0, len(positions) - len(inventories))))
    return positions, inventories[:len(positions)]


def _crop_harvestable(snap, tile):
    crop = tile.get("crop")
    spec = econ.CROPS.get(crop)
    if spec is None:
        return False
    return int(snap.day) - int(tile.get("planted_day", snap.day)) >= int(
        spec["first_yield_day"]
    )


def _targets(snap):
    out = []
    for pos, tile in sorted(snap.me.animals.items()):
        units = max(0, int(tile.get("yield_units", 0) or 0))
        kind = tile.get("animal")
        product = (econ.ANIMALS.get(kind) or {}).get("product")
        if units and product in econ.SELLABLE:
            out.append((tuple(pos), product, units, -1))
    for pos, tile in sorted(snap.me.crops.items()):
        units = max(0, int(tile.get("yield_units", 0) or 0))
        product = tile.get("crop")
        if units and product in econ.SELLABLE and _crop_harvestable(snap, tile):
            out.append((tuple(pos), product, units,
                        int(tile.get("max_lifespan_step", -1) or -1)))
    return out


def _immediate_production_pending(snap):
    """Whether a legal WATER can still create harvestable crop units now."""
    for tile in snap.me.crops.values():
        crop = tile.get("crop")
        spec = econ.CROPS.get(crop)
        if spec is None or spec["ongoing"] or tile.get("watered_today"):
            continue
        age = int(snap.day) - int(tile.get("planted_day", snap.day))
        window_start = (int(spec["max_yield_day"]) + 1) // 2
        held = max(0, int(tile.get("yield_units", 0) or 0))
        if (age >= int(spec["first_yield_day"])
                and window_start <= age <= int(spec["max_yield_day"])
                and held < int(spec["max_yield"])):
            return True
    return False


def _decays_before(step, harvest_offset, lifespan_step):
    """Exact plant decay count before a future HARVEST action commits."""
    if lifespan_step < 0 or harvest_offset <= 0:
        return 0
    end = int(step) + int(harvest_offset) - 1
    first = max(int(step), int(lifespan_step))
    if (first - int(lifespan_step)) % 2:
        first += 1
    if first > end:
        return 0
    return 1 + (end - first) // 2


def _visible_opponent_upper(snap, remaining):
    """Public ripe output with an individually feasible route to their shed.

    Summing individually reachable targets is a relaxation of shared worker
    time, hence an upper bound.  It deliberately does not invent a per-product
    hidden-shed quantity; hidden stock has one aggregate capacity and remains a
    separate unresolved uncertainty set.
    """
    starts = [tuple(snap.opp.farmer)]
    starts.extend(tuple(pos) for pos in snap.opp.hands)
    upper = Counter()
    standing = list(snap.opp.animals.items()) + list(snap.opp.crops.items())
    for pos, tile in standing:
        units = max(0, int(tile.get("yield_units", 0) or 0))
        if units <= 0:
            continue
        if "animal" in tile:
            item = (econ.ANIMALS.get(tile.get("animal")) or {}).get("product")
        else:
            item = tile.get("crop")
            if not _crop_harvestable(snap, tile):
                continue
        if item not in econ.SELLABLE:
            continue
        route = min(paths.dist(start, pos) for start in starts)
        route += 1 + paths.dist_to_shed(pos) + 1  # HARVEST + DROP
        if route <= remaining:
            upper[item] += units
    return upper


def _paired_visible_value(snap, outputs, opponent_upper, hidden_capacity=0):
    """Exact lockstep margin against the public visible quantity interval."""
    from whitebox.cashflow import _paired_bundle_value, _paired_sale_value

    if int(hidden_capacity) > 0:
        return _paired_bundle_value(
            outputs, snap.market_inv, opponent_upper, int(hidden_capacity),
        )

    total = 0.0
    for item in sorted(outputs):
        qty = max(0, int(outputs[item]))
        if qty <= 0:
            continue
        inv = int(snap.market_inv.get(item, econ.MARKET_I0) or econ.MARKET_I0)
        total += _paired_sale_value(
            item, qty, inv, max(0, int(opponent_upper.get(item, 0))),
        )
    return float(total)


def certify(snap):
    """Construct a complete executable residual sweep or reject it.

    Every trip ends at a concrete shed tile and includes HARVEST and DROP.
    Trips are assigned by deterministic earliest completion.  This is a
    constructive feasibility certificate, not a claim that the assignment is
    the shortest possible multi-worker tour.
    """
    remaining = max(0, state.LAST_STEP - int(snap.step) + 1)
    cert = TerminalCertificate(remaining)
    if not production_closed(snap):
        cert.reason = "future_refresh"
        return cert
    if _immediate_production_pending(snap):
        cert.reason = "immediate_crop_output"
        return cert

    positions, inventories = _units(snap)
    if not positions or remaining <= 0:
        cert.reason = "no_actions"
        return cert

    carrying = []
    carried_outputs = Counter()
    for inv in inventories:
        n = sum(max(0, int(qty or 0)) for item, qty in inv.items()
                if item in econ.SELLABLE)
        carrying.append(n)
        for item, qty in inv.items():
            if item in econ.SELLABLE:
                carried_outputs[item] += max(0, int(qty or 0))
    if int(snap.shed_used) + sum(carrying) > econ.SHED_CAPACITY:
        cert.reason = "current_drop_capacity"
        return cert

    finish = [0] * len(positions)
    endpoint = list(positions)
    routes = [[] for _ in positions]
    for idx, amount in enumerate(carrying):
        if amount <= 0:
            continue
        home = paths.nearest_shed_tile(endpoint[idx])
        finish[idx] = paths.dist(endpoint[idx], home) + 1
        endpoint[idx] = home
        if finish[idx] > remaining:
            cert.reason = "carried_delivery"
            return cert

    targets = _targets(snap)
    # Harder/farther trips enter first; ties are entirely public geometry.
    targets.sort(key=lambda t: (-paths.dist_to_shed(t[0]), t[0], t[1]))
    assigned_outputs = Counter()
    for target in targets:
        pos, item, units, lifespan = target
        best = None
        for idx in range(len(positions)):
            travel = paths.dist(endpoint[idx], pos)
            harvest_offset = finish[idx] + travel
            if _decays_before(snap.step, harvest_offset, lifespan):
                continue
            home = paths.nearest_shed_tile(pos)
            added = travel + 1 + paths.dist(pos, home) + 1
            new_finish = finish[idx] + added
            if new_finish > remaining:
                continue
            key = (new_finish, added, idx)
            if best is None or key < best[0]:
                best = (key, idx, home)
        if best is None:
            cert.reason = "residual_sweep"
            return cert
        _key, idx, home = best
        routes[idx].append(target)
        finish[idx] = best[0][0]
        endpoint[idx] = home
        assigned_outputs[item] += units

    actions = []
    for idx, pos in enumerate(positions):
        if carrying[idx] > 0:
            if pos in paths.SHED_SET:
                actions.append(["DROP"])
            else:
                actions.append([paths.step_toward(pos, paths.nearest_shed_tile(pos))])
            continue
        if routes[idx]:
            target = routes[idx][0][0]
            if pos == target:
                actions.append(["HARVEST"])
            else:
                actions.append([paths.step_toward(pos, target)])
        else:
            actions.append(["PASS"])

    outputs = Counter(snap.shed)
    outputs.update(carried_outputs)
    outputs.update(assigned_outputs)
    opponent_upper = _visible_opponent_upper(snap, remaining)
    cert.feasible = True
    cert.reason = "ok"
    cert.routes = {idx: route for idx, route in enumerate(routes) if route}
    cert.actions = actions
    cert.outputs = dict(outputs)
    cert.opponent_upper = dict(opponent_upper)
    cert.paired_value = _paired_visible_value(snap, outputs, opponent_upper)
    cert.max_route_actions = max(finish) if finish else 0
    return cert


def certify_partial(snap):
    """Construct a positive-value feasible subset of the residual sweep.

    Hour 0 remains with the ordinary capital/hire master because new hands are
    bought in that market phase and begin acting at hour 1.  Afterwards this
    primal repeatedly chooses the feasible target with the greatest exact
    aggregate paired-sale gain.  Repeated output of one product is therefore
    repriced as a single nonlinear quantity; there is no value/distance weight.
    """
    remaining = max(0, state.LAST_STEP - int(snap.step) + 1)
    cert = TerminalCertificate(remaining)
    if not production_closed(snap):
        cert.reason = "future_refresh"
        return cert
    if _immediate_production_pending(snap):
        cert.reason = "immediate_crop_output"
        return cert
    if int(snap.hour) == 0:
        cert.reason = "hire_market_phase"
        return cert

    positions, inventories = _units(snap)
    if not positions or remaining <= 0:
        cert.reason = "no_actions"
        return cert

    carrying = []
    carried_outputs = Counter()
    for inv in inventories:
        n = sum(max(0, int(qty or 0)) for item, qty in inv.items()
                if item in econ.SELLABLE)
        carrying.append(n)
        for item, qty in inv.items():
            if item in econ.SELLABLE:
                carried_outputs[item] += max(0, int(qty or 0))
    if int(snap.shed_used) + sum(carrying) > econ.SHED_CAPACITY:
        cert.reason = "current_drop_capacity"
        return cert

    finish = [0] * len(positions)
    endpoint = list(positions)
    routes = [[] for _ in positions]
    for idx, amount in enumerate(carrying):
        if amount <= 0:
            continue
        home = paths.nearest_shed_tile(endpoint[idx])
        finish[idx] = paths.dist(endpoint[idx], home) + 1
        endpoint[idx] = home
        if finish[idx] > remaining:
            cert.reason = "carried_delivery"
            return cert

    opponent_upper = _visible_opponent_upper(snap, remaining)
    outputs = Counter({item: max(0, int(qty or 0))
                       for item, qty in snap.shed.items()
                       if item in econ.SELLABLE})
    outputs.update(carried_outputs)
    current_value = _paired_visible_value(snap, outputs, opponent_upper)
    left = _targets(snap)

    while left:
        best = None
        for target_idx, target in enumerate(left):
            pos, item, units, lifespan = target
            trial_outputs = outputs.copy()
            trial_outputs[item] += units
            trial_value = _paired_visible_value(
                snap, trial_outputs, opponent_upper,
            )
            gain = trial_value - current_value
            if gain <= 1e-9:
                continue
            for unit_idx in range(len(positions)):
                travel = paths.dist(endpoint[unit_idx], pos)
                harvest_offset = finish[unit_idx] + travel
                if _decays_before(snap.step, harvest_offset, lifespan):
                    continue
                home = paths.nearest_shed_tile(pos)
                added = travel + 1 + paths.dist(pos, home) + 1
                new_finish = finish[unit_idx] + added
                if new_finish > remaining:
                    continue
                # Economic priority is exact aggregate paired gain.  Route
                # completion and public geometry break only equal-gain ties.
                key = (gain, -new_finish, -added,
                       tuple(pos), item, -unit_idx)
                if best is None or key > best[0]:
                    best = (key, target_idx, unit_idx, home,
                            new_finish, trial_outputs, trial_value)
        if best is None:
            break
        (_key, target_idx, unit_idx, home, new_finish,
         outputs, current_value) = best
        target = left.pop(target_idx)
        routes[unit_idx].append(target)
        finish[unit_idx] = new_finish
        endpoint[unit_idx] = home

    actions = []
    for idx, pos in enumerate(positions):
        if carrying[idx] > 0:
            if pos in paths.SHED_SET:
                actions.append(["DROP"])
            else:
                actions.append([paths.step_toward(pos, paths.nearest_shed_tile(pos))])
            continue
        if routes[idx]:
            target = routes[idx][0][0]
            if pos == target:
                actions.append(["HARVEST"])
            else:
                actions.append([paths.step_toward(pos, target)])
        else:
            actions.append(["PASS"])

    cert.feasible = True
    cert.reason = "ok_partial"
    cert.routes = {idx: route for idx, route in enumerate(routes) if route}
    cert.actions = actions
    cert.outputs = dict(outputs)
    cert.opponent_upper = dict(opponent_upper)
    cert.paired_value = float(current_value)
    cert.max_route_actions = max(finish) if finish else 0
    return cert


def _output_at(snap, pos, ops, harvest_offset):
    """Rule-derived sellable output of the live operations at one stop."""
    out = Counter()
    if any(op and op[0] == "HARVEST" for op in ops):
        if pos in snap.me.animals:
            tile = snap.me.animals[pos]
            item = (econ.ANIMALS.get(tile.get("animal")) or {}).get("product")
            units = max(0, int(tile.get("yield_units", 0) or 0))
        else:
            tile = snap.me.crops.get(pos, {})
            item = tile.get("crop")
            units = max(0, int(tile.get("yield_units", 0) or 0))
            units = max(0, units - _decays_before(
                snap.step, harvest_offset,
                int(tile.get("max_lifespan_step", -1) or -1),
            ))
        if item in econ.SELLABLE and units:
            out[item] += units
    if any(op and op[0] == "COLLECT_FERTILIZER" for op in ops):
        out["FERTILIZER"] += 1
    return out


def general_route_upper(snap, routes, hidden_capacity=0):
    """Reprice an output upper bound for ordinary live-route prefixes.

    Route order is not reoptimised.  For each worker, every live prefix is
    charged for missing-input pickup, its remaining operations and the exact
    shed-return/DROP tail. Required inputs are optimistically available and
    their economic cost is omitted, so the result is an upper bound on the
    general route's terminal output value. Products are cleared once through
    the same exact lockstep-margin equation as the terminal primal. A terminal value that
    strictly exceeds this upper bound has positive opportunity cost without
    relying on a fitted tolerance.
    """
    remaining = max(0, state.LAST_STEP - int(snap.step) + 1)
    cert = TerminalCertificate(remaining)
    if not production_closed(snap):
        cert.reason = "future_refresh"
        return cert
    if _immediate_production_pending(snap):
        cert.reason = "immediate_crop_output"
        return cert

    positions, inventories = _units(snap)
    outputs = Counter({item: max(0, int(qty or 0))
                       for item, qty in snap.shed.items()
                       if item in econ.SELLABLE})
    max_actions = 0
    live_routes = {}
    from whitebox import tasks as _tasks

    for idx, start in enumerate(positions):
        inv = inventories[idx]
        carried = Counter({item: max(0, int(qty or 0))
                           for item, qty in inv.items()
                           if item in econ.SELLABLE})
        best_outputs = Counter()
        best_stops = []
        best_actions = 0
        if carried:
            direct = paths.dist_to_shed(start) + 1
            if direct <= remaining:
                best_outputs = carried.copy()
                best_actions = direct

        cur = tuple(start)
        spent = 0
        chosen = []
        pocket = Counter(inv)
        for raw_pos in (routes or {}).get(idx, ()):
            pos = tuple(raw_pos)
            ops, carry = _tasks.live_ops(snap, pos, pocket)
            if not ops:
                continue
            missing = {item: max(0, int(qty) - int(pocket.get(item, 0)))
                       for item, qty in carry.items()
                       if int(pocket.get(item, 0)) < int(qty)}
            if missing:
                shed = paths.nearest_shed_tile(cur)
                spent += paths.dist(cur, shed) + len(missing)
                cur = shed
                for item, qty in missing.items():
                    pocket[item] += qty
            spent += paths.dist(cur, pos)
            harvest_offset = spent + next(
                (op_idx for op_idx, op in enumerate(ops)
                 if op and op[0] == "HARVEST"),
                len(ops),
            )
            spent += len(ops)
            produced = _output_at(
                snap, pos, ops, harvest_offset,
            )
            for op in ops:
                if not op:
                    continue
                if op[0] == "FEED":
                    pocket["WHEAT"] = max(0, pocket["WHEAT"] - 1)
                elif op[0] == "FERTILIZE":
                    pocket["FERTILIZER"] = max(
                        0, pocket["FERTILIZER"] - 1,
                    )
                elif op[0] == "PLACE" and len(op) > 1:
                    pocket[op[1]] = max(0, pocket[op[1]] - 1)
            pocket.update(produced)
            trial_outputs = Counter({
                item: max(0, int(qty or 0))
                for item, qty in pocket.items()
                if item in econ.SELLABLE and int(qty or 0) > 0
            })
            cur = pos
            tail = (paths.dist_to_shed(cur) + 1
                    if trial_outputs else 0)
            if spent + tail > remaining:
                break
            chosen.append(pos)
            best_outputs = trial_outputs.copy()
            best_stops = list(chosen)
            best_actions = spent + tail
        outputs.update(best_outputs)
        if best_stops:
            live_routes[idx] = best_stops
        max_actions = max(max_actions, best_actions)

    opponent_upper = _visible_opponent_upper(snap, remaining)
    cert.feasible = True
    cert.reason = "ok_general_upper"
    cert.routes = live_routes
    cert.outputs = dict(outputs)
    cert.opponent_upper = dict(opponent_upper)
    cert.paired_value = _paired_visible_value(
        snap, outputs, opponent_upper, hidden_capacity,
    )
    cert.max_route_actions = max_actions
    return cert


def prefer_terminal(terminal_cert, general_cert):
    """Strict exact opportunity-cost comparison; ties preserve general work."""
    return bool(
        terminal_cert is not None and terminal_cert.feasible
        and general_cert is not None and general_cert.feasible
        and terminal_cert.paired_value > general_cert.paired_value + 1e-9
    )


def prefer_terminal_hidden(snap, terminal_cert, general_cert,
                           hidden_capacity=econ.SHED_CAPACITY):
    """Strict dominance under one conserved hidden-shed allocation set."""
    if not (terminal_cert is not None and terminal_cert.feasible
            and general_cert is not None and general_cert.feasible):
        return False
    visible = {
        item: max(
            int(terminal_cert.opponent_upper.get(item, 0) or 0),
            int(general_cert.opponent_upper.get(item, 0) or 0),
        )
        for item in econ.SELLABLE
    }
    from whitebox.cashflow import _paired_bundle_difference
    difference = _paired_bundle_difference(
        terminal_cert.outputs, general_cert.outputs,
        snap.market_inv, visible, int(hidden_capacity),
    )
    return difference > 1e-9


def _complete_targets(snap):
    """Terminal tile bundles with every immediately sellable engine output."""
    out = []
    for pos, tile in sorted(snap.me.animals.items()):
        ops = []
        products = Counter()
        units = max(0, int(tile.get("yield_units", 0) or 0))
        kind = tile.get("animal")
        product = (econ.ANIMALS.get(kind) or {}).get("product")
        if units and product in econ.SELLABLE:
            ops.append("HARVEST")
            products[product] += units
        if tile.get("fertilizer_available"):
            ops.append("COLLECT_FERTILIZER")
            products["FERTILIZER"] += 1
        if ops:
            out.append((tuple(pos), tuple(ops), tuple(sorted(products.items())), -1))
    for pos, tile in sorted(snap.me.crops.items()):
        units = max(0, int(tile.get("yield_units", 0) or 0))
        product = tile.get("crop")
        if units and product in econ.SELLABLE and _crop_harvestable(snap, tile):
            out.append((tuple(pos), ("HARVEST",), ((product, units),),
                        int(tile.get("max_lifespan_step", -1) or -1)))
    return out


def certify_partial_complete(snap, hidden_capacity=0):
    """V68 terminal primal with complete HARVEST+FERTILIZER tile bundles."""
    remaining = max(0, state.LAST_STEP - int(snap.step) + 1)
    cert = TerminalCertificate(remaining)
    if not production_closed(snap):
        cert.reason = "future_refresh"
        return cert
    if _immediate_production_pending(snap):
        cert.reason = "immediate_crop_output"
        return cert
    if int(snap.hour) == 0:
        cert.reason = "hire_market_phase"
        return cert

    positions, inventories = _units(snap)
    if not positions or remaining <= 0:
        cert.reason = "no_actions"
        return cert
    carrying = []
    carried_outputs = Counter()
    for inv in inventories:
        n = sum(max(0, int(qty or 0)) for item, qty in inv.items()
                if item in econ.SELLABLE)
        carrying.append(n)
        for item, qty in inv.items():
            if item in econ.SELLABLE:
                carried_outputs[item] += max(0, int(qty or 0))
    if int(snap.shed_used) + sum(carrying) > econ.SHED_CAPACITY:
        cert.reason = "current_drop_capacity"
        return cert

    finish = [0] * len(positions)
    endpoint = list(positions)
    routes = [[] for _ in positions]
    for idx, amount in enumerate(carrying):
        if amount <= 0:
            continue
        home = paths.nearest_shed_tile(endpoint[idx])
        finish[idx] = paths.dist(endpoint[idx], home) + 1
        endpoint[idx] = home
        if finish[idx] > remaining:
            cert.reason = "carried_delivery"
            return cert

    opponent_upper = _visible_opponent_upper(snap, remaining)
    outputs = Counter({item: max(0, int(qty or 0))
                       for item, qty in snap.shed.items()
                       if item in econ.SELLABLE})
    outputs.update(carried_outputs)
    current_value = _paired_visible_value(
        snap, outputs, opponent_upper, hidden_capacity,
    )
    left = _complete_targets(snap)
    left.sort(key=lambda t: (-paths.dist_to_shed(t[0]), t[0], t[1]))

    while left:
        best = None
        for target_idx, target in enumerate(left):
            pos, ops, produced_items, lifespan = target
            trial_outputs = outputs.copy()
            trial_outputs.update(dict(produced_items))
            trial_value = _paired_visible_value(
                snap, trial_outputs, opponent_upper, hidden_capacity,
            )
            gain = trial_value - current_value
            if gain <= 1e-9:
                continue
            for unit_idx in range(len(positions)):
                travel = paths.dist(endpoint[unit_idx], pos)
                harvest_idx = (ops.index("HARVEST")
                               if "HARVEST" in ops else len(ops))
                harvest_offset = finish[unit_idx] + travel + harvest_idx
                if _decays_before(snap.step, harvest_offset, lifespan):
                    continue
                home = paths.nearest_shed_tile(pos)
                added = travel + len(ops) + paths.dist(pos, home) + 1
                new_finish = finish[unit_idx] + added
                if new_finish > remaining:
                    continue
                key = (gain, -new_finish, -added,
                       tuple(pos), tuple(ops), -unit_idx)
                if best is None or key > best[0]:
                    best = (key, target_idx, unit_idx, home,
                            new_finish, trial_outputs, trial_value)
        if best is None:
            break
        (_key, target_idx, unit_idx, home, new_finish,
         outputs, current_value) = best
        target = left.pop(target_idx)
        routes[unit_idx].append(target)
        finish[unit_idx] = new_finish
        endpoint[unit_idx] = home

    actions = []
    for idx, pos in enumerate(positions):
        if carrying[idx] > 0:
            if pos in paths.SHED_SET:
                actions.append(["DROP"])
            else:
                actions.append([paths.step_toward(pos, paths.nearest_shed_tile(pos))])
            continue
        if routes[idx]:
            target_pos, ops, _produced, _lifespan = routes[idx][0]
            if pos == target_pos:
                actions.append([ops[0]])
            else:
                actions.append([paths.step_toward(pos, target_pos)])
        else:
            actions.append(["PASS"])

    cert.feasible = True
    cert.reason = "ok_partial_complete"
    cert.routes = {idx: route for idx, route in enumerate(routes) if route}
    cert.actions = actions
    cert.outputs = dict(outputs)
    cert.opponent_upper = dict(opponent_upper)
    cert.paired_value = float(current_value)
    cert.max_route_actions = max(finish) if finish else 0
    return cert


def certify_partial_chained(snap):
    """Complete terminal bundles with one final DROP per worker chain.

    ``certify_partial_complete`` is deliberately conservative: after every
    target it returns to a shed and pays a DROP before considering another
    target.  The ordinary-route upper bound, however, visits a sequence of
    live stops and closes that whole sequence with one DROP.  This variant
    removes that physical asymmetry.  For worker ``u`` with selected stops
    ``p[1..k]`` its certified action count is exactly

        dist(start[u], p[1]) + ops[p[1]]
        + sum(dist(p[i-1], p[i]) + ops[p[i]])
        + dist(p[k], shed) + DROP.

    Current carried output is simply the initial load of that closed chain.
    All carried plus newly selected output must fit one shared shed capacity,
    so even simultaneous final drops are constructive.  Current shed stock is
    sold by ``sale_orders`` in this action's later market phase and therefore
    is checked separately against any immediately delivered load.
    """
    remaining = max(0, state.LAST_STEP - int(snap.step) + 1)
    cert = TerminalCertificate(remaining)
    if not production_closed(snap):
        cert.reason = "future_refresh"
        return cert
    if _immediate_production_pending(snap):
        cert.reason = "immediate_crop_output"
        return cert
    if int(snap.hour) == 0:
        cert.reason = "hire_market_phase"
        return cert

    positions, inventories = _units(snap)
    if not positions or remaining <= 0:
        cert.reason = "no_actions"
        return cert

    carried = []
    carried_outputs = Counter()
    for inv in inventories:
        amount = sum(max(0, int(qty or 0)) for item, qty in inv.items()
                     if item in econ.SELLABLE)
        carried.append(amount)
        for item, qty in inv.items():
            if item in econ.SELLABLE:
                carried_outputs[item] += max(0, int(qty or 0))
    total_carried = sum(carried)
    if int(snap.shed_used) + total_carried > econ.SHED_CAPACITY:
        cert.reason = "current_drop_capacity"
        return cert
    if total_carried > econ.SHED_CAPACITY:
        cert.reason = "route_output_capacity"
        return cert

    # ``spent`` excludes the one final return/DROP tail.  ``finish`` includes
    # it, and is the exact closed-chain length used for feasibility.
    spent = [0] * len(positions)
    finish = [0] * len(positions)
    endpoint = list(positions)
    routes = [[] for _ in positions]
    for idx, amount in enumerate(carried):
        if amount <= 0:
            continue
        finish[idx] = paths.dist_to_shed(endpoint[idx]) + 1
        if finish[idx] > remaining:
            cert.reason = "carried_delivery"
            return cert

    opponent_upper = _visible_opponent_upper(snap, remaining)
    outputs = Counter({item: max(0, int(qty or 0))
                       for item, qty in snap.shed.items()
                       if item in econ.SELLABLE})
    outputs.update(carried_outputs)
    route_output = Counter(carried_outputs)
    current_value = _paired_visible_value(snap, outputs, opponent_upper)
    left = _complete_targets(snap)
    left.sort(key=lambda t: (-paths.dist_to_shed(t[0]), t[0], t[1]))

    while left:
        best = None
        for target_idx, target in enumerate(left):
            pos, ops, produced_items, lifespan = target
            produced = Counter(dict(produced_items))
            if sum(route_output.values()) + sum(produced.values()) \
                    > econ.SHED_CAPACITY:
                continue
            trial_outputs = outputs.copy()
            trial_outputs.update(produced)
            trial_value = _paired_visible_value(
                snap, trial_outputs, opponent_upper,
            )
            gain = trial_value - current_value
            if gain <= 1e-9:
                continue
            for unit_idx in range(len(positions)):
                travel = paths.dist(endpoint[unit_idx], pos)
                harvest_idx = (ops.index("HARVEST")
                               if "HARVEST" in ops else len(ops))
                harvest_offset = spent[unit_idx] + travel + harvest_idx
                if _decays_before(snap.step, harvest_offset, lifespan):
                    continue
                new_spent = spent[unit_idx] + travel + len(ops)
                new_finish = new_spent + paths.dist_to_shed(pos) + 1
                if new_finish > remaining:
                    continue
                key = (gain, -new_finish, -travel,
                       tuple(pos), tuple(ops), -unit_idx)
                if best is None or key > best[0]:
                    best = (key, target_idx, unit_idx, new_spent,
                            new_finish, trial_outputs, trial_value, produced)
        if best is None:
            break
        (_key, target_idx, unit_idx, new_spent, new_finish,
         outputs, current_value, produced) = best
        target = left.pop(target_idx)
        routes[unit_idx].append(target)
        spent[unit_idx] = new_spent
        finish[unit_idx] = new_finish
        endpoint[unit_idx] = target[0]
        route_output.update(produced)

    actions = []
    for idx, pos in enumerate(positions):
        if routes[idx]:
            target_pos, ops, _produced, _lifespan = routes[idx][0]
            if pos == target_pos:
                actions.append([ops[0]])
            else:
                actions.append([paths.step_toward(pos, target_pos)])
        elif carried[idx] > 0:
            if pos in paths.SHED_SET:
                actions.append(["DROP"])
            else:
                actions.append([
                    paths.step_toward(pos, paths.nearest_shed_tile(pos)),
                ])
        else:
            actions.append(["PASS"])

    cert.feasible = True
    cert.reason = "ok_partial_chained"
    cert.routes = {idx: route for idx, route in enumerate(routes) if route}
    cert.actions = actions
    cert.outputs = dict(outputs)
    cert.opponent_upper = dict(opponent_upper)
    cert.paired_value = float(current_value)
    cert.max_route_actions = max(finish) if finish else 0
    return cert


def _chained_route_finish(snap, start, route, has_load=False):
    """Exact closed length of one ordered terminal route, or ``None``.

    Re-evaluate every harvest offset because inserting one stop can delay crops
    already present later in the chain.  This helper is used only by the V103
    insertion primal; V102's append-only implementation remains untouched.
    """
    elapsed = 0
    cur = tuple(start)
    for target in route:
        pos, ops, _produced_items, lifespan = target
        travel = paths.dist(cur, pos)
        harvest_idx = (ops.index("HARVEST")
                       if "HARVEST" in ops else len(ops))
        harvest_offset = elapsed + travel + harvest_idx
        if _decays_before(snap.step, harvest_offset, lifespan):
            return None
        elapsed += travel + len(ops)
        cur = pos
    if route or has_load:
        elapsed += paths.dist_to_shed(cur) + 1
    return int(elapsed)


def certify_partial_inserted(snap):
    """V103 terminal primal: exact-marginal greedy over all route insertions.

    V102 chooses the economically best remaining target but can place it only
    after a worker's current last stop.  Here each candidate is tested at every
    insertion index in every worker chain.  The objective remains its exact
    aggregate paired-sale increment.  Complete closed length, then incremental
    closed length and public geometry break only equal-value ties.  Every trial
    revalidates decay for the whole reordered chain.
    """
    remaining = max(0, state.LAST_STEP - int(snap.step) + 1)
    cert = TerminalCertificate(remaining)
    if not production_closed(snap):
        cert.reason = "future_refresh"
        return cert
    if _immediate_production_pending(snap):
        cert.reason = "immediate_crop_output"
        return cert
    if int(snap.hour) == 0:
        cert.reason = "hire_market_phase"
        return cert

    positions, inventories = _units(snap)
    if not positions or remaining <= 0:
        cert.reason = "no_actions"
        return cert

    carried = []
    carried_outputs = Counter()
    for inv in inventories:
        amount = sum(max(0, int(qty or 0)) for item, qty in inv.items()
                     if item in econ.SELLABLE)
        carried.append(amount)
        for item, qty in inv.items():
            if item in econ.SELLABLE:
                carried_outputs[item] += max(0, int(qty or 0))
    total_carried = sum(carried)
    if int(snap.shed_used) + total_carried > econ.SHED_CAPACITY:
        cert.reason = "current_drop_capacity"
        return cert
    if total_carried > econ.SHED_CAPACITY:
        cert.reason = "route_output_capacity"
        return cert

    routes = [[] for _ in positions]
    finish = [0] * len(positions)
    for idx, amount in enumerate(carried):
        if amount <= 0:
            continue
        closed = _chained_route_finish(
            snap, positions[idx], routes[idx], has_load=True,
        )
        if closed is None or closed > remaining:
            cert.reason = "carried_delivery"
            return cert
        finish[idx] = closed

    opponent_upper = _visible_opponent_upper(snap, remaining)
    outputs = Counter({item: max(0, int(qty or 0))
                       for item, qty in snap.shed.items()
                       if item in econ.SELLABLE})
    outputs.update(carried_outputs)
    route_output_count = sum(carried_outputs.values())
    current_value = _paired_visible_value(snap, outputs, opponent_upper)
    left = _complete_targets(snap)
    left.sort(key=lambda t: (-paths.dist_to_shed(t[0]), t[0], t[1]))

    while left:
        best = None
        for target_idx, target in enumerate(left):
            pos, ops, produced_items, _lifespan = target
            produced = Counter(dict(produced_items))
            produced_count = sum(produced.values())
            if route_output_count + produced_count > econ.SHED_CAPACITY:
                continue
            trial_outputs = outputs.copy()
            trial_outputs.update(produced)
            trial_value = _paired_visible_value(
                snap, trial_outputs, opponent_upper,
            )
            gain = trial_value - current_value
            if gain <= 1e-9:
                continue
            for unit_idx in range(len(positions)):
                old_finish = finish[unit_idx]
                for insert_idx in range(len(routes[unit_idx]) + 1):
                    trial_route = list(routes[unit_idx])
                    trial_route.insert(insert_idx, target)
                    new_finish = _chained_route_finish(
                        snap, positions[unit_idx], trial_route,
                        has_load=carried[unit_idx] > 0,
                    )
                    if new_finish is None or new_finish > remaining:
                        continue
                    added = new_finish - old_finish
                    key = (gain, -new_finish, -added,
                           tuple(pos), tuple(ops), -unit_idx, -insert_idx)
                    if best is None or key > best[0]:
                        best = (key, target_idx, unit_idx, insert_idx,
                                trial_route, new_finish, trial_outputs,
                                trial_value, produced_count)
        if best is None:
            break
        (_key, target_idx, unit_idx, _insert_idx, trial_route, new_finish,
         outputs, current_value, produced_count) = best
        left.pop(target_idx)
        routes[unit_idx] = trial_route
        finish[unit_idx] = new_finish
        route_output_count += produced_count

    actions = []
    for idx, pos in enumerate(positions):
        if routes[idx]:
            target_pos, ops, _produced, _lifespan = routes[idx][0]
            if pos == target_pos:
                actions.append([ops[0]])
            else:
                actions.append([paths.step_toward(pos, target_pos)])
        elif carried[idx] > 0:
            if pos in paths.SHED_SET:
                actions.append(["DROP"])
            else:
                actions.append([
                    paths.step_toward(pos, paths.nearest_shed_tile(pos)),
                ])
        else:
            actions.append(["PASS"])

    cert.feasible = True
    cert.reason = "ok_partial_inserted"
    cert.routes = {idx: route for idx, route in enumerate(routes) if route}
    cert.actions = actions
    cert.outputs = dict(outputs)
    cert.opponent_upper = dict(opponent_upper)
    cert.paired_value = float(current_value)
    cert.max_route_actions = max(finish) if finish else 0
    return cert


def _refill_inserted_routes(snap, positions, carried, carried_outputs,
                            opponent_upper, routes, left, remaining):
    """Run V103's exact-marginal insertion primal from a certified seed set.

    This helper belongs to the V104 exchange experiment.  It does not alter
    V103: seeded routes are fully revalidated, their complete output is priced
    once, and every remaining target is inserted by the same economic and
    geometric ordering used by ``certify_partial_inserted``.
    """
    routes = [list(route) for route in routes]
    finish = []
    route_outputs = Counter(carried_outputs)
    for unit_idx, route in enumerate(routes):
        closed = _chained_route_finish(
            snap, positions[unit_idx], route,
            has_load=carried[unit_idx] > 0,
        )
        if closed is None or closed > remaining:
            return None
        finish.append(closed)
        for target in route:
            route_outputs.update(dict(target[2]))
    if sum(route_outputs.values()) > econ.SHED_CAPACITY:
        return None

    outputs = Counter({item: max(0, int(qty or 0))
                       for item, qty in snap.shed.items()
                       if item in econ.SELLABLE})
    outputs.update(route_outputs)
    route_output_count = sum(route_outputs.values())
    current_value = _paired_visible_value(snap, outputs, opponent_upper)
    left = list(left)
    left.sort(key=lambda t: (-paths.dist_to_shed(t[0]), t[0], t[1]))

    while left:
        best = None
        for target_idx, target in enumerate(left):
            pos, ops, produced_items, _lifespan = target
            produced = Counter(dict(produced_items))
            produced_count = sum(produced.values())
            if route_output_count + produced_count > econ.SHED_CAPACITY:
                continue
            trial_outputs = outputs.copy()
            trial_outputs.update(produced)
            trial_value = _paired_visible_value(
                snap, trial_outputs, opponent_upper,
            )
            gain = trial_value - current_value
            if gain <= 1e-9:
                continue
            for unit_idx in range(len(positions)):
                old_finish = finish[unit_idx]
                for insert_idx in range(len(routes[unit_idx]) + 1):
                    trial_route = list(routes[unit_idx])
                    trial_route.insert(insert_idx, target)
                    new_finish = _chained_route_finish(
                        snap, positions[unit_idx], trial_route,
                        has_load=carried[unit_idx] > 0,
                    )
                    if new_finish is None or new_finish > remaining:
                        continue
                    added = new_finish - old_finish
                    key = (gain, -new_finish, -added,
                           tuple(pos), tuple(ops), -unit_idx, -insert_idx)
                    if best is None or key > best[0]:
                        best = (key, target_idx, unit_idx, trial_route,
                                new_finish, trial_outputs, trial_value,
                                produced_count)
        if best is None:
            break
        (_key, target_idx, unit_idx, trial_route, new_finish,
         outputs, current_value, produced_count) = best
        left.pop(target_idx)
        routes[unit_idx] = trial_route
        finish[unit_idx] = new_finish
        route_output_count += produced_count

    return routes, finish, outputs, float(current_value)


def _terminal_route_signature(routes):
    """Public deterministic tie-break for economically equal route sets."""
    return tuple(
        tuple((target[0], target[1]) for target in route)
        for route in routes
    )


def certify_partial_exchanged(snap):
    """V104 one-exchange neighborhood around V103's inserted terminal set.

    For each selected target ``q`` and each rejected target ``p``, remove
    ``q``, insert ``p`` at its shortest fully certified position, then refill
    every remaining target with V103's exact aggregate-marginal primal.  The
    resulting set replaces V103 only if its complete paired bundle value is
    strictly larger.  Thus route length decides feasibility and equal-value
    placement only; it is never traded against economic value by a fitted
    coefficient.
    """
    incumbent = certify_partial_inserted(snap)
    if not incumbent.feasible:
        return incumbent

    positions, inventories = _units(snap)
    carried = []
    carried_outputs = Counter()
    for inv in inventories:
        amount = sum(max(0, int(qty or 0)) for item, qty in inv.items()
                     if item in econ.SELLABLE)
        carried.append(amount)
        for item, qty in inv.items():
            if item in econ.SELLABLE:
                carried_outputs[item] += max(0, int(qty or 0))

    routes = [list(incumbent.routes.get(idx, ()))
              for idx in range(len(positions))]
    selected = [target for route in routes for target in route]
    targets = _complete_targets(snap)
    rejected = [target for target in targets if target not in selected]
    if not selected or not rejected:
        return incumbent

    remaining = incumbent.remaining_actions
    opponent_upper = Counter(incumbent.opponent_upper)
    best = None
    best_value = float(incumbent.paired_value)

    for outgoing_unit, route in enumerate(routes):
        for outgoing_idx, _outgoing in enumerate(route):
            removed = [list(worker_route) for worker_route in routes]
            removed[outgoing_unit].pop(outgoing_idx)
            removed_finish = []
            valid_removed = True
            for unit_idx, worker_route in enumerate(removed):
                closed = _chained_route_finish(
                    snap, positions[unit_idx], worker_route,
                    has_load=carried[unit_idx] > 0,
                )
                if closed is None or closed > remaining:
                    valid_removed = False
                    break
                removed_finish.append(closed)
            if not valid_removed:
                continue

            for incoming in rejected:
                placement = None
                for unit_idx, worker_route in enumerate(removed):
                    for insert_idx in range(len(worker_route) + 1):
                        trial_route = list(worker_route)
                        trial_route.insert(insert_idx, incoming)
                        new_finish = _chained_route_finish(
                            snap, positions[unit_idx], trial_route,
                            has_load=carried[unit_idx] > 0,
                        )
                        if new_finish is None or new_finish > remaining:
                            continue
                        key = (new_finish,
                               new_finish - removed_finish[unit_idx],
                               unit_idx, insert_idx)
                        if placement is None or key < placement[0]:
                            placement = (key, unit_idx, trial_route)
                if placement is None:
                    continue

                _key, unit_idx, trial_route = placement
                seeded = [list(worker_route) for worker_route in removed]
                seeded[unit_idx] = trial_route
                seeded_targets = [target for worker_route in seeded
                                  for target in worker_route]
                left = [target for target in targets
                        if target not in seeded_targets]
                result = _refill_inserted_routes(
                    snap, positions, carried, carried_outputs,
                    opponent_upper, seeded, left, remaining,
                )
                if result is None:
                    continue
                candidate_routes, finish, outputs, candidate_value = result
                if candidate_value <= best_value + 1e-9:
                    continue
                candidate_key = (
                    max(finish) if finish else 0,
                    sum(finish),
                    _terminal_route_signature(candidate_routes),
                )
                if (best is None or candidate_value > best_value + 1e-9
                        or (abs(candidate_value - best_value) <= 1e-9
                            and candidate_key < best[0])):
                    best_value = candidate_value
                    best = (candidate_key, candidate_routes, finish, outputs)

    if best is None:
        return incumbent

    _key, routes, finish, outputs = best
    actions = []
    for idx, pos in enumerate(positions):
        if routes[idx]:
            target_pos, ops, _produced, _lifespan = routes[idx][0]
            if pos == target_pos:
                actions.append([ops[0]])
            else:
                actions.append([paths.step_toward(pos, target_pos)])
        elif carried[idx] > 0:
            if pos in paths.SHED_SET:
                actions.append(["DROP"])
            else:
                actions.append([
                    paths.step_toward(pos, paths.nearest_shed_tile(pos)),
                ])
        else:
            actions.append(["PASS"])

    cert = TerminalCertificate(remaining)
    cert.feasible = True
    cert.reason = "ok_partial_exchanged"
    cert.routes = {idx: route for idx, route in enumerate(routes) if route}
    cert.actions = actions
    cert.outputs = dict(outputs)
    cert.opponent_upper = dict(opponent_upper)
    cert.paired_value = float(best_value)
    cert.max_route_actions = max(finish) if finish else 0
    return cert


def _general_suffix_cost(snap, unit_idx, route):
    """Optimistic action cost of completing a live route and banking output."""
    positions, inventories = _units(snap)
    if unit_idx >= len(positions):
        return 0
    cur = positions[unit_idx]
    pocket = Counter(inventories[unit_idx])
    spent = 0
    has_output = any(item in econ.SELLABLE and int(qty or 0) > 0
                     for item, qty in pocket.items())
    from whitebox import tasks as _tasks
    for raw_pos in route or ():
        pos = tuple(raw_pos)
        ops, carry = _tasks.live_ops(snap, pos, pocket)
        if not ops:
            continue
        missing = {item: max(0, int(qty) - int(pocket.get(item, 0)))
                   for item, qty in carry.items()
                   if int(pocket.get(item, 0)) < int(qty)}
        if missing:
            shed = paths.nearest_shed_tile(cur)
            spent += paths.dist(cur, shed) + len(missing)
            cur = shed
            for item, qty in missing.items():
                pocket[item] += qty
        spent += paths.dist(cur, pos) + len(ops)
        cur = pos
        if any(op and op[0] in ("HARVEST", "COLLECT_FERTILIZER")
               for op in ops):
            has_output = True
        for op in ops:
            if not op:
                continue
            if op[0] == "FEED":
                pocket["WHEAT"] = max(0, pocket["WHEAT"] - 1)
            elif op[0] == "FERTILIZE":
                pocket["FERTILIZER"] = max(0, pocket["FERTILIZER"] - 1)
            elif op[0] == "PLACE" and len(op) > 1:
                pocket[op[1]] = max(0, pocket[op[1]] - 1)
    if has_output:
        spent += paths.dist_to_shed(cur) + 1
    return int(spent)


def rescue_actions(snap, routes, general_actions):
    """Directly bank carried stock when the live general suffix cannot finish.

    This is recomputed from the current observation every turn.  It remembers
    no earlier terminal decision.  The ordinary action is preserved whenever
    its entire live suffix and DROP fit; only a provably terminally
    unexecutable suffix is replaced by the shortest delivery action.
    """
    actions = [list(action) for action in (general_actions or ())]
    positions, inventories = _units(snap)
    actions.extend([["PASS"] for _ in range(
        max(0, len(positions) - len(actions))
    )])
    if not production_closed(snap) or _immediate_production_pending(snap):
        return actions[:len(positions)], 0
    remaining = max(0, state.LAST_STEP - int(snap.step) + 1)
    room = max(0, econ.SHED_CAPACITY - int(snap.shed_used))
    rescued = 0
    for idx, (pos, inv) in enumerate(zip(positions, inventories)):
        amount = sum(max(0, int(qty or 0)) for item, qty in inv.items()
                     if item in econ.SELLABLE)
        if amount <= 0:
            continue
        direct = paths.dist_to_shed(pos) + 1
        if direct > remaining:
            continue
        if _general_suffix_cost(snap, idx, (routes or {}).get(idx, ())) <= remaining:
            continue
        if pos in paths.SHED_SET:
            if amount > room:
                continue
            room -= amount
            actions[idx] = ["DROP"]
        else:
            actions[idx] = [paths.step_toward(pos, paths.nearest_shed_tile(pos))]
        rescued += 1
    return actions[:len(positions)], rescued


def sale_orders(snap, actions):
    """Sell exactly current shed stock plus goods that DROP before market."""
    quantities = Counter({item: max(0, int(qty or 0))
                          for item, qty in snap.shed.items()
                          if item in econ.SELLABLE})
    for idx, action in enumerate(actions or ()):
        if (not action or action[0] != "DROP"
                or idx >= len(snap.inventories)):
            continue
        for item, qty in snap.inventories[idx].items():
            if item in econ.SELLABLE:
                quantities[item] += max(0, int(qty or 0))
    return [["SELL", item, quantities[item]] for item in sorted(quantities)
            if quantities[item] > 0][:econ.MAX_ORDERS]


def _configured_last_action(snap):
    """Last agent action derived from the public episode configuration."""
    config = getattr(snap, "config", None)
    try:
        steps = (config.get("episodeSteps", state.LAST_STEP + 2)
                 if isinstance(config, dict)
                 else getattr(config, "episodeSteps", state.LAST_STEP + 2))
        return max(0, int(steps) - 2)
    except (AttributeError, TypeError, ValueError):
        return int(state.LAST_STEP)


def _book_after_sale(item, qty, inventory):
    """Exact engine inventory transition, including the $1-floor rule."""
    inv = int(inventory)
    for _ in range(max(0, int(qty))):
        if econ.price(item, inv) > econ.PRICE_FLOOR:
            inv += 1
    return inv


def _terminal_split_value(snap, item, total_qty, sell_now, last_action):
    """Historical V88 own-cash value of a current/final sale split.

    This tombstone predates discovery of the engine's per-unit lockstep market
    transition and deliberately retains V88's standalone-revenue objective for
    reproducibility. It is not a paired robust value and is not reached by the
    selected V103 terminal policy. The guaranteed lower town drain advances
    the public book between its two own-sale phases.
    """
    from whitebox import market_model

    total = max(0, int(total_qty))
    now = min(total, max(0, int(sell_now)))
    inv = int(snap.market_inv.get(item, econ.MARKET_I0) or econ.MARKET_I0)
    current = float(econ.sell_revenue(item, now, inv))
    after = _book_after_sale(item, now, inv)
    drain, _upper = market_model.town_take_bounds(
        snap, item, start_step=int(snap.step), end_step=int(last_action),
    )
    future_inv = after - max(0, int(drain))
    return current + float(econ.sell_revenue(item, total - now, future_inv))


def inventory_master_orders(snap, actions, terminal_outputs):
    """Historical V88 own-cash sale/retention master for a closed route.

    The terminal certificate has already proved every remaining unit action
    and output.  No new capital can act before episode end, so future capital,
    feed and service costs are exactly zero in this branch.  Choose current
    sale quantities to maximize its standalone two-phase revenue, while leaving
    enough shared shed capacity for every certified output and consuming no
    more than the engine's ten product-order slots.  Re-solve from the next
    public observation; no schedule or hidden state is remembered. This V88
    tombstone is not the robust lockstep terminal objective used by V103.
    """
    available_orders = sale_orders(snap, actions)
    available = Counter({str(order[1]): max(0, int(order[2] or 0))
                         for order in available_orders if len(order) >= 3})
    if not available:
        return []

    last_action = _configured_last_action(snap)
    if int(snap.step) >= last_action:
        return available_orders

    all_outputs = Counter({str(item): max(0, int(qty or 0))
                           for item, qty in (terminal_outputs or {}).items()})
    for item, qty in available.items():
        all_outputs[item] = max(all_outputs.get(item, 0), qty)

    config = getattr(snap, "config", None)
    try:
        capacity = (config.get("shedCapacity", econ.SHED_CAPACITY)
                    if isinstance(config, dict)
                    else getattr(config, "shedCapacity", econ.SHED_CAPACITY))
        capacity = max(0, int(capacity))
    except (AttributeError, TypeError, ValueError):
        capacity = econ.SHED_CAPACITY
    release = max(0, sum(all_outputs.values()) - capacity)
    if release > sum(available.values()):
        # The two-phase certificate cannot make all future stock coexist.  V86's
        # immediate liquidation is the maximum physically useful room release.
        return available_orders

    items = sorted(item for item in all_outputs if item in econ.SELLABLE)
    # (sold units, used slots) -> (robust value, quantities in item order).
    dp = {(0, 0): (0.0, ())}
    for item in items:
        total = max(0, int(all_outputs.get(item, 0)))
        cap = min(total, max(0, int(available.get(item, 0))))
        choices = [
            _terminal_split_value(snap, item, total, qty, last_action)
            for qty in range(cap + 1)
        ]
        nxt = {}
        for (sold, slots), (prior, quantities) in dp.items():
            for qty, value in enumerate(choices):
                new_slots = slots + (1 if qty > 0 else 0)
                if new_slots > econ.MAX_ORDERS:
                    continue
                state_key = (sold + qty, new_slots)
                candidate = (prior + value, quantities + (qty,))
                previous = nxt.get(state_key)
                if (previous is None
                        or (candidate[0], tuple(-q for q in candidate[1]))
                        > (previous[0], tuple(-q for q in previous[1]))):
                    nxt[state_key] = candidate
        dp = nxt

    feasible = []
    for (sold, slots), (value, quantities) in dp.items():
        if sold < release:
            continue
        # Strict value first; on an exact tie retain more and use fewer slots.
        key = (value, -sold, -slots, tuple(-q for q in quantities))
        feasible.append((key, quantities))
    if not feasible:
        return available_orders
    _key, quantities = max(feasible)
    return [["SELL", item, qty] for item, qty in zip(items, quantities)
            if qty > 0][:econ.MAX_ORDERS]
