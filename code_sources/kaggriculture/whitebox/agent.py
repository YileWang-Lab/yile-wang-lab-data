"""The driver: composes the six modules into one engine action per turn.

    state.extract -> strategy.decide -> tasks.enumerate/assign
                                     -> market acquisition proposals
                                     -> capital task/route/hire master
                                     -> paths (inside tasks.next_op)

WHITE-BOX CONTRACT. The production entry has no tape loader, replayed opening,
learned action table, or seam that can borrow another agent's decisions. Every
action is recomputed from the live state. Constants used by the production path
come from the engine and are reproduced in `whitebox/econ.py`; replay-mining
modules retained elsewhere in the directory are historical diagnostics only.
"""
import os
import sys
import time

_HERE = globals().get("__file__")
if _HERE:
    _ROOT = os.path.dirname(os.path.dirname(os.path.abspath(_HERE)))
else:
    # kaggle_environments executes a raw .py agent without defining __file__.
    # Local real-engine gates run from the repository root, where the modular
    # whitebox package is importable. A final upload will still be bundled into
    # one file; this branch is for faithful pre-bundle validation.
    _ROOT = os.getcwd()
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from whitebox import state, strategy, tasks, hiring, market, capital, econ  # noqa: E402
from whitebox import value as _value  # noqa: E402
from whitebox import horizon as _horizon   # noqa: E402

# One tracker per seat, fed every turn. The inventory arithmetic behind it is a
# running delta, so a skipped turn breaks it permanently (HANDOFF section 6).
_TRACKER = {}
_ASSET_TOTALS = {}


def _tracker(seat, step):
    t = _TRACKER.get(seat)
    if t is None or step == 0:
        t = state.OpponentTracker()
        _TRACKER[seat] = t
    return t


def _observable_asset_totals(snap):
    """Conserved owned-capital counts used only to detect new acquisitions."""
    totals = {}
    for crop in strategy.econ.CROPS:
        totals[crop] = max(0, int(snap.seeds.get(crop, 0) or 0))
    for tile in snap.me.crops.values():
        crop = tile.get("crop")
        if crop in totals:
            totals[crop] += 1
    carried = snap.carried()
    standing = snap.me.animal_counts()
    for kind in strategy.econ.ANIMALS:
        totals[kind] = (max(0, int(standing.get(kind, 0) or 0))
                        + max(0, int(snap.shed.get(kind, 0) or 0))
                        + max(0, int(carried.get(kind, 0) or 0)))
    return tuple((item, totals[item]) for item in sorted(totals))


def _reset_for_new_assets(snap):
    """Invalidate today's route only when observable owned capital increases.

    PLANT and PLACE conserve these totals, so ordinary execution cannot cause
    per-turn re-planning.  A market acquisition becomes visible on the next
    observation and receives an executable same-day route even when no hand was
    hired to trigger the historical crew-count invalidation.
    """
    if snap.step == 0:
        _ASSET_TOTALS.pop(snap.seat, None)
    current = _observable_asset_totals(snap)
    previous = _ASSET_TOTALS.get(snap.seat)
    if previous is not None and previous[0] == snap.day:
        before = dict(previous[1])
        if any(qty > int(before.get(item, 0)) for item, qty in current):
            if not tasks.paid_turnover_arrival_is_preplanned(
                    snap, before, current):
                tasks.reset(snap.seat)
    _ASSET_TOTALS[snap.seat] = (snap.day, current)

# The production path is white-box only. Historical seam substitution was
# useful for attribution, but made it possible to depend on a tape accidentally.
MODES = {"units": "computed", "market": "computed"}
PORTFOLIO = strategy.DEFAULT_PORTFOLIO
# Section 48 is a promising experiment, not yet margin-qualified for default:
# 18 paired cells are below the >=288 promotion gate. Explicit opt-in only.
CAPITAL_MASTER = os.environ.get("WB_CAPITAL_MASTER", "0") != "0"
ACT_BUDGET_MS = max(20.0, float(os.environ.get("WB_ACT_BUDGET_MS", "180")))


def _act_deadline(obs, config):
    """Soft optimisation deadline, shared by every expensive solver layer.

    Kaggle grants 1 s per action plus only 60 s total overage. A 180 ms local
    budget leaves headroom for slower judging hardware, Python/file wrapper
    overhead and the cheap action-emission tail. The hard clamp prevents an
    experimental environment value from silently spending most of actTimeout.
    """
    try:
        act_timeout = float(state._get(config, "actTimeout", 1.0) or 1.0)
    except Exception:
        act_timeout = 1.0
    try:
        overage = float(state._get(obs, "remainingOverageTime", 60.0) or 0.0)
    except Exception:
        overage = 60.0
    seconds = min(ACT_BUDGET_MS / 1000.0, max(0.020, act_timeout * 0.35))
    if overage < 15.0:
        seconds = min(seconds, 0.120)
    if overage < 5.0:
        seconds = min(seconds, 0.080)
    return time.perf_counter() + seconds


def _safe(obs):
    farm = {}
    try:
        farms = state._get(obs, "farms", []) or []
        seat = state._num(state._get(obs, "player", 0))
        farm = farms[seat] if seat < len(farms) else {}
    except Exception:
        pass
    hands = state._get(farm, "hands", []) or []
    return {"farmer": ["PASS"], "hands": [["PASS"] for _ in hands], "market": []}


def _guard(fn, default, *args):
    """Run one module; on failure fall back to `default` instead of the turn.

    A module that raises used to cost the WHOLE turn: `agent()` caught it and
    returned all-PASS, so one bad tile lookup idled the farmer, every hand and
    every market order at once. Degrading one seam is strictly better than
    degrading six, and the engine treats a malformed sub-action as a silent
    no-op anyway.
    """
    try:
        return fn(*args)
    except Exception:
        return default


def _purchase_cost(snap, orders):
    """Conservative cash needed by non-hire BUY orders in one market queue."""
    total = 0.0
    books = dict(snap.market_inv)
    owned_extra = max(0, len(snap.me.unlocked) - 1)
    for order in orders:
        if not order:
            continue
        op = order[0]
        if op == "BUY_LAND":
            if owned_extra < len(strategy.econ.LAND_PRICES):
                total += float(strategy.econ.LAND_PRICES[owned_extra])
                owned_extra += 1
        elif len(order) >= 3 and op == "BUY_SEED":
            total += (float(strategy.econ.CROPS[order[1]]["seed"])
                      * max(0, int(order[2])))
        elif len(order) >= 3 and op == "BUY_ANIMAL":
            total += (float(strategy.econ.ANIMALS[order[1]]["cost"])
                      * max(0, int(order[2])))
        elif len(order) >= 3 and op == "BUY_PRODUCT":
            item, qty = order[1], max(0, int(order[2]))
            inventory = int(books.get(item, strategy.econ.MARKET_I0))
            total += float(strategy.econ.buy_cost(item, qty, inventory))
            books[item] = inventory - qty
    return total


def _certified_turnover_seed_assets(snap, plan, noncapital, assets,
                                     items_by_position):
    """Complete the seed side of an already selected DIG route column.

    The task certificate priced the named seed and the live unit phase has now
    released exactly these tiles.  Re-optimising that prerequisite as optional
    capital can reject it under a different objective, leaving a paid worker
    to DIG without PLANT.  This completion step adds only the missing named
    seed quantities, subject to the same public cash reserve and ten-order
    limit, then retains their exact positions for manifest execution.
    """
    positions = {}
    for raw_pos, raw_item in sorted((items_by_position or {}).items()):
        item = str(raw_item)
        if item not in econ.CROPS:
            return None
        positions.setdefault(item, []).append(tuple(raw_pos))
    if not positions:
        return list(assets)

    trial = [list(order) for order in (assets or ())]
    ordered = {
        str(order[1]): int(order[2])
        for order in trial
        if len(order) >= 3 and order[0] == "BUY_SEED"
    }
    for item, item_positions in sorted(positions.items()):
        required = len(item_positions)
        available = max(0, int(snap.seeds.get(item, 0) or 0))
        missing = max(0, required - available - ordered.get(item, 0))
        if missing > 0:
            trial.append(["BUY_SEED", item, missing])
    if len(noncapital) + len(trial) > econ.MAX_ORDERS:
        return None
    reserve = max(0.0, float(getattr(
        plan, "service_cash_floor", getattr(plan, "cash_floor", 0.0),
    ) or 0.0))
    if (_purchase_cost(snap, list(noncapital) + trial)
            > max(0.0, float(snap.me.money) - reserve) + 1e-9):
        return None
    tasks.commit_capital_positions(snap.seat, snap.day, positions)
    return trial


def _ordinary_capital_tasks(work):
    """V199's task universe, excluding the orthogonal turnover option."""
    return [
        task for task in (work or ())
        if not (
            str(getattr(task, "kind", "")) == "PAID_TURNOVER_SERVICE"
            or (
                str(getattr(task, "kind", "")) == "CLEAR_WEED"
                and any(op and op[0] == "PLANT"
                        for op in (getattr(task, "ops", ()) or ()))
            )
        )
    ]


def _overnight_capacity_safe(snap, todo):
    """Whether free end-of-day banking cannot overflow our private shed.

    Count the complete current shed, every unit inventory item and every
    HARVEST/COLLECT result named by today's task set.  This is deliberately an
    upper bound: carried feed/fertilizer may be consumed and not every optional
    task will be selected.  Therefore a true result is a constructive capacity
    certificate for leaving output in workers' pockets until engine refresh.
    """
    occupied = sum(max(0, int(qty or 0))
                   for qty in snap.shed.values())
    occupied += sum(
        max(0, int(qty or 0))
        for inventory in snap.inventories
        for qty in (inventory or {}).values()
    )
    for task in todo or ():
        x, y = tuple(task.pos)
        tile = snap.me.tiles[y][x]
        names = [op[0] for op in task.ops if op]
        if "HARVEST" in names and isinstance(tile, dict):
            occupied += max(0, int(tile.get("yield_units", 0) or 0))
        if "COLLECT_FERTILIZER" in names:
            occupied += 1
    return occupied <= econ.SHED_CAPACITY


def _opening_hires(snap, selected, assets, noncapital, floor):
    """Fund the cheap opening Fibonacci block when capital needs deployment.

    The first five same-day hires cost only 1+1+2+3+5 = 12 dollars and each
    receives every remaining hour of the opening day.  A capital route which
    buys deployable assets but leaves this block unused is therefore missing
    the option value of bringing those assets online earlier.  The rule remains
    a cash- and order-slot-feasible floor, never an unconditional schedule.
    """
    floor = max(0, int(floor or 0))
    if floor <= selected or snap.step != 0 or not assets:
        return selected
    room = min(
        market.MAX_ORDERS - len(noncapital) - len(assets),
        hiring.MAX_HANDS - len(snap.me.hands),
    )
    target = min(floor, max(0, room))
    if target <= selected:
        return selected
    purchases = _purchase_cost(snap, list(noncapital) + list(assets))
    affordable = selected
    for count in range(selected + 1, target + 1):
        crew = strategy.econ.hire_block_cost(snap.me.hires_today, count)
        if purchases + crew <= float(snap.me.money) + 1e-9:
            affordable = count
        else:
            break
    return affordable


def _projected_dig_positions(snap, projected):
    """Tiles changed from a visible weed to empty by this unit phase.

    This is an exact transition certificate, not an inferred intention. It is
    empty unless a DIG emitted this turn actually succeeds in the public engine
    projection, and it names only the released tiles a same-turn seed purchase
    is allowed to exercise.
    """
    released = []
    for y, row in enumerate(snap.me.tiles):
        for x, before in enumerate(row):
            after = projected.me.tiles[y][x]
            if (isinstance(before, dict) and before.get("kind") == "WEED"
                    and after is None):
                released.append((x, y))
    return tuple(sorted(released))


def act(obs, config=None, capital_master=None, capital_variant=None,
        bank_sales=False, robust_banking=False, plan_variant=None,
        charge_activation_cost=True, deterministic_routes=False,
        terminal_variant=None, task_value_variant=None,
        deterministic_route_refine=False, market_variant=None,
        opening_hire_floor=0, execution_variant=None,
        productive_shed_tiles=False, productive_shed_relocation=False,
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
        spatial_route_multistart=False,
        paid_weed_turnover=False,
        survival_feed_hard_core=False):
    """Live state -> one fully computed engine action."""
    deadline = _act_deadline(obs, config)
    snap = state.extract(obs, config)
    snap.allow_productive_shed_tiles = bool(productive_shed_tiles)
    _value.set_exact_zero_day_age(
        execution_variant == "exact_zero_day_manifest"
    )
    tr = _tracker(snap.seat, snap.step)
    _guard(tr.observe, None, snap)

    # HORIZON once a turn, with the real tracker, BEFORE anything reads it.
    # Every later site asks `horizon.current(snap)` and gets this same object
    # back off the per-step memo, so `earliest_sellable` walks the opponent's
    # tiles once a turn no matter how many decisions consult it.
    _guard(_horizon.sense, None, snap, tr)

    plan = strategy.decide(snap, PORTFOLIO, plan_variant)
    plan.execution_variant = execution_variant
    plan.paid_weed_turnover = bool(paid_weed_turnover)
    plan.survival_feed_hard_core = bool(survival_feed_hard_core)
    if execution_variant in (
            "paid_production_fertilizer_manifest",
            "paid_fertilizer_productive_shed_relocation_manifest"):
        plan.fertilizer_target = _value.paid_fertilizer_target(snap, plan)

    if plan_variant in ("inventory_execution_replan",
                        "crew_conditioned_inventory_execution"):
        _reset_for_new_assets(snap)

    if snap.step == 0:
        tasks.reset()
    tasks._last_plan[0] = plan

    # V65 opt-in: replace the fixed terminal window with a live constructive
    # certificate.  Historical variants never import this module and retain
    # their recorded last-eight-step semantics.
    if terminal_variant in ("state_certificate", "state_partial"):
        from whitebox import terminal as _terminal
        terminal_solver = (_terminal.certify_partial
                           if terminal_variant == "state_partial"
                           else _terminal.certify)
        terminal_cert = _guard(terminal_solver, None, snap)
        if terminal_cert is not None and terminal_cert.feasible:
            unit_actions = list(terminal_cert.actions)
            farmer = unit_actions[0] if unit_actions else ["PASS"]
            hands = unit_actions[1:1 + len(snap.me.hands)]
            orders = _guard(_terminal.sale_orders, [], snap, unit_actions)
            hands = (hands + [["PASS"]] * len(snap.me.hands))[:len(snap.me.hands)]
            out = {"farmer": list(farmer),
                   "hands": [list(h) for h in hands],
                   "market": [list(o) for o in orders][:market.MAX_ORDERS]}
            _guard(tr.record_my_orders, None, out["market"], snap.shed)
            return out

    # ---- endgame: the validated collector owns the last few steps
    if (terminal_variant is None
            and snap.step >= 719 - tasks.ENDGAME_TAKEOVER):
        farmer = _guard(tasks.endgame_collect, ["PASS"], snap, 0)
        hands = [_guard(tasks.endgame_collect, ["PASS"], snap, i + 1)
                 for i in range(len(snap.me.hands))]
        orders = _guard(market.orders, [], snap, plan, tr, market_variant)
        if bank_sales in (
                True, "joint_routes", "certified_tail_elision",
                "certified_bank_detour"):
            orders = _guard(
                market.same_turn_bank_orders, orders, snap, orders,
                [farmer] + hands,
            )
        hands = (hands + [["PASS"]] * len(snap.me.hands))[:len(snap.me.hands)]
        out = {"farmer": list(farmer), "hands": [list(h) for h in hands],
               "market": [list(o) for o in orders][:market.MAX_ORDERS]}
        _guard(tr.record_my_orders, None, out["market"], snap.shed)
        return out

    todo = _guard(tasks.enumerate_tasks, [], snap, plan)
    if task_value_variant == "bundle_outputs":
        # Reprice the complete ordinary proposal before route selection. The
        # full-proposal average is a conservative value for any selected subset
        # under the exact non-increasing marginal sale curve.
        from whitebox import value as _objective
        todo = _objective.reprice_task_sale_bundles(snap, todo)
    overnight_auto_bank = bool(
        bank_sales in (
            "capacity_safe_overnight", "certified_tail_elision",
        )
        and _overnight_capacity_safe(snap, todo)
    )
    bank_routes = bool(
        bank_sales in (
            "joint_routes", "certified_tail_elision",
            "certified_bank_detour",
        )
        or (bank_sales == "capacity_safe_overnight"
            and not overnight_auto_bank)
    )
    bank_detour = bool(bank_sales == "certified_bank_detour")
    # ``capital_only`` is an isolation arm for one measured seam.  Capital
    # keeps V149's conservative output-banking route cost, while the live daily
    # route may use the engine's free end-of-day auto-drop and sells from the
    # next observation.  All historical booleans and ``joint_routes`` retain
    # byte-for-byte signal semantics.
    capital_bank_routes = bool(
        bank_routes or bank_sales == "capital_only"
    )
    bundle_master = task_value_variant in (
        "bundle_master", "paired_phase_bundle_master",
        "temporal_paired_bundle_master",
    )
    tours, undone = _guard(
        tasks.assign, ({}, []), snap, todo, deadline, bank_routes,
        deterministic_routes,
        bundle_master,
        deterministic_route_refine,
        task_value_variant == "paired_phase_bundle_master",
        task_value_variant == "temporal_paired_bundle_master",
        spatial_route_multistart,
    )
    if execution_variant in (
            "paid_production_fertilizer_manifest",
            "paid_fertilizer_productive_shed_relocation_manifest"):
        selected_fertilizer = _guard(
            tasks.selected_input_requirement, 0, snap, "FERTILIZER",
        )
        plan.fertilizer_target = min(
            int(plan.fertilizer_target), int(selected_fertilizer),
        )

    # ---- units (farmer + hands): task planner + path planner
    farmer = _guard(tasks.next_op, ["PASS"], snap, 0, tours.get(0),
                    robust_banking, bank_routes, overnight_auto_bank,
                    bank_detour)
    hands = [_guard(tasks.next_op, ["PASS"], snap, i + 1, tours.get(i + 1),
                    robust_banking, bank_routes, overnight_auto_bank,
                    bank_detour)
             for i in range(len(snap.me.hands))]

    # V67: compare the terminal primal with the ordinary route master's live
    # executable output on the same nonlinear lockstep-margin objective. Only a
    # strict positive opportunity-cost result may replace general work.
    if terminal_variant in ("state_opportunity", "state_opportunity_complete",
                             "state_opportunity_rescue",
                             "state_opportunity_chained_rescue",
                             "state_opportunity_inserted_rescue",
                             "state_opportunity_exchanged_rescue",
                             "state_opportunity_hidden",
                             "state_opportunity_rescue_inventory_master"):
        from whitebox import terminal as _terminal
        hidden_terminal = terminal_variant == "state_opportunity_hidden"
        if hidden_terminal:
            terminal_cert = _guard(
                _terminal.certify_partial_complete, None,
                snap, _terminal.econ.SHED_CAPACITY,
            )
            general_cert = _guard(
                _terminal.general_route_upper, None,
                snap, tours, _terminal.econ.SHED_CAPACITY,
            )
        else:
            terminal_solver = (_terminal.certify_partial_exchanged
                               if terminal_variant
                               == "state_opportunity_exchanged_rescue" else
                               _terminal.certify_partial_inserted
                               if terminal_variant
                               == "state_opportunity_inserted_rescue" else
                               _terminal.certify_partial_chained
                               if terminal_variant
                               == "state_opportunity_chained_rescue" else
                               _terminal.certify_partial_complete
                               if terminal_variant in (
                                   "state_opportunity_complete",
                                   "state_opportunity_rescue",
                                   "state_opportunity_rescue_inventory_master",
                               ) else _terminal.certify_partial)
            terminal_cert = _guard(terminal_solver, None, snap)
            general_cert = _guard(
                _terminal.general_route_upper, None, snap, tours,
            )
        terminal_preferred = (
            _terminal.prefer_terminal_hidden(snap, terminal_cert, general_cert)
            if hidden_terminal else
            _terminal.prefer_terminal(terminal_cert, general_cert)
        )
        if terminal_preferred:
            unit_actions = list(terminal_cert.actions)
            farmer = unit_actions[0] if unit_actions else ["PASS"]
            hands = unit_actions[1:1 + len(snap.me.hands)]
            orders = (_guard(
                _terminal.inventory_master_orders, [], snap, unit_actions,
                terminal_cert.outputs,
            ) if terminal_variant
                == "state_opportunity_rescue_inventory_master" else
                _guard(_terminal.sale_orders, [], snap, unit_actions))
            hands = (hands + [["PASS"]] * len(snap.me.hands))[:len(snap.me.hands)]
            out = {"farmer": list(farmer),
                   "hands": [list(h) for h in hands],
                   "market": [list(o) for o in orders][:market.MAX_ORDERS]}
            _guard(tr.record_my_orders, None, out["market"], snap.shed)
            return out
        if terminal_variant in ("state_opportunity_rescue",
                                 "state_opportunity_chained_rescue",
                                 "state_opportunity_inserted_rescue",
                                 "state_opportunity_exchanged_rescue",
                                 "state_opportunity_rescue_inventory_master",
                                 "state_opportunity_hidden"):
            rescued_actions, _rescued = _terminal.rescue_actions(
                snap, tours, [farmer] + hands,
            )
            farmer = rescued_actions[0] if rescued_actions else ["PASS"]
            hands = rescued_actions[1:1 + len(snap.me.hands)]

    # ---- market: hiring FIRST, then the order generator
    # HIRE prices use this farm's own daily counter (the opponent cannot
    # reprice them). Each hire still consumes one of the ten order slots. The
    # decider reroutes every current and candidate hand before choosing a count.
    unit_actions = [farmer] + hands
    capacity_projected = None
    decision_snap, decision_plan, decision_todo = snap, plan, todo
    phase_projected = False
    turnover_positions = ()
    turnover_items_by_position = {}
    if capital_variant in ("phase_snapshot",
                            "certified_marginal_phase_deterministic",
                            "phase_aligned_certificate_deterministic",
                            "crew_conditioned_phase_aligned_deterministic",
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
                            "crew_conditioned_positioned_scenario_late_land_candidate_bound_deferred_hires_deterministic",
                            "crew_conditioned_positioned_scenario_late_land_candidate_bound_first_output_covenant_deterministic",
                            "crew_conditioned_positioned_scenario_late_land_feasibility_closed_deterministic",
                            "crew_conditioned_positioned_scenario_late_land_saturated_book_deterministic",
                            "crew_conditioned_positioned_scenario_late_land_exact_capacity_frontier_deterministic",
                            "crew_conditioned_positioned_scenario_late_land_precertified_capacity_frontier_deterministic",
                            "crew_conditioned_positioned_scenario_late_land_staged_follower_reinvestment_deterministic",
                            "crew_conditioned_positioned_standing_scenario_late_land_staged_follower_reinvestment_deterministic",
                            "crew_conditioned_positioned_complete_standing_scenario_late_land_staged_follower_reinvestment_deterministic",
                            "crew_conditioned_positioned_robust_realisations_scenario_late_land_staged_follower_reinvestment_deterministic",
                            "crew_conditioned_positioned_scenario_late_land_staged_follower_land_reinvestment_deterministic",
                            "crew_conditioned_positioned_scenario_late_land_staged_follower_mixed_reinvestment_deterministic",
                            "crew_conditioned_positioned_scenario_late_land_paid_rotation_substitution_deterministic",
                            "crew_conditioned_positioned_scenario_late_land_backlogged_rotation_substitution_deterministic",
                            "crew_conditioned_positioned_scenario_late_land_weed_backlog_hires_deterministic",
                            "crew_conditioned_positioned_scenario_late_land_single_backlog_rotation_deterministic",
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
                            "crew_conditioned_positioned_scenario_late_land_bounded_execution_capital_deterministic",
                            "crew_conditioned_positioned_scenario_late_land_herd_repair_deterministic",
                            "crew_conditioned_positioned_scenario_late_land_global_repair_deterministic",
                            "crew_conditioned_positioned_scenario_crop_land_covenant_deterministic",
                            "crew_conditioned_robust_portfolio_descent_deterministic",
                            "crew_conditioned_cashflow_backed_portfolio_deterministic",
                            "crew_conditioned_robust_service_portfolio_deterministic",
                            "crew_conditioned_frontier_portfolio_deterministic"):
        # The market resolves after every current unit action. Regenerate every
        # market/capital input from that exact transition, then route from the
        # next action hour. The projection keeps the current public clock: no
        # market clearing, decay or daily refresh has occurred yet.
        decision_snap = state.project_unit_phase(snap, unit_actions)
        phase_projected = True
        if paid_weed_turnover:
            turnover_positions = _projected_dig_positions(
                snap, decision_snap,
            )
            turnover_items_by_position = {
                tuple(pos): item
                for pos in turnover_positions
                for item in (tasks.paid_turnover_item(snap, pos),)
                if item in econ.CROPS
            }
        decision_plan = strategy.decide(
            decision_snap, PORTFOLIO, plan_variant,
        )
        decision_plan.survival_feed_hard_core = bool(
            survival_feed_hard_core
        )
        if execution_variant in (
                "paid_production_fertilizer_manifest",
                "paid_fertilizer_productive_shed_relocation_manifest"):
            decision_plan.execution_variant = execution_variant
            decision_plan.fertilizer_target = int(plan.fertilizer_target)
        decision_plan.paid_weed_turnover = bool(plan.paid_weed_turnover)
        tasks._last_plan[0] = decision_plan
        decision_todo = tasks.enumerate_tasks(decision_snap, decision_plan)
    if market_variant in ("capacity_reserve", "capacity_reserve_public_priority"):
        # Reuse the exact post-unit snapshot already consumed by the capital
        # and task masters.  Non-capital variants construct it once here.  A
        # single shared phase prevents market and routing layers from pricing
        # the same MOVE/HARVEST/DROP twice or disagreeing on carried stock.
        capacity_projected = (
            decision_snap if phase_projected else
            _guard(state.project_unit_phase, None, snap, unit_actions)
        )
    decision_capital_todo = (
        _ordinary_capital_tasks(decision_todo)
        if paid_weed_turnover else decision_todo
    )
    fixed = _guard(
        market.orders, [], decision_snap, decision_plan, tr, market_variant,
    )
    use_capital = CAPITAL_MASTER if capital_master is None else bool(capital_master)
    if use_capital and capital_variant in (
            "phase_snapshot", "certified_marginal_phase_deterministic",
            "phase_aligned_certificate_deterministic",
            "crew_conditioned_phase_aligned_deterministic",
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
            "crew_conditioned_positioned_scenario_late_land_candidate_bound_deferred_hires_deterministic",
            "crew_conditioned_positioned_scenario_late_land_candidate_bound_first_output_covenant_deterministic",
            "crew_conditioned_positioned_scenario_late_land_feasibility_closed_deterministic",
            "crew_conditioned_positioned_scenario_late_land_saturated_book_deterministic",
            "crew_conditioned_positioned_scenario_late_land_exact_capacity_frontier_deterministic",
            "crew_conditioned_positioned_scenario_late_land_precertified_capacity_frontier_deterministic",
            "crew_conditioned_positioned_scenario_late_land_staged_follower_reinvestment_deterministic",
            "crew_conditioned_positioned_standing_scenario_late_land_staged_follower_reinvestment_deterministic",
            "crew_conditioned_positioned_complete_standing_scenario_late_land_staged_follower_reinvestment_deterministic",
            "crew_conditioned_positioned_robust_realisations_scenario_late_land_staged_follower_reinvestment_deterministic",
            "crew_conditioned_positioned_scenario_late_land_staged_follower_land_reinvestment_deterministic",
            "crew_conditioned_positioned_scenario_late_land_staged_follower_mixed_reinvestment_deterministic",
            "crew_conditioned_positioned_scenario_late_land_paid_rotation_substitution_deterministic",
            "crew_conditioned_positioned_scenario_late_land_backlogged_rotation_substitution_deterministic",
            "crew_conditioned_positioned_scenario_late_land_weed_backlog_hires_deterministic",
            "crew_conditioned_positioned_scenario_late_land_single_backlog_rotation_deterministic",
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
            "crew_conditioned_positioned_scenario_late_land_bounded_execution_capital_deterministic",
            "crew_conditioned_positioned_scenario_late_land_herd_repair_deterministic",
            "crew_conditioned_positioned_scenario_late_land_global_repair_deterministic",
            "crew_conditioned_positioned_scenario_crop_land_covenant_deterministic",
            "crew_conditioned_robust_portfolio_descent_deterministic",
            "crew_conditioned_cashflow_backed_portfolio_deterministic",
            "crew_conditioned_robust_service_portfolio_deterministic",
            "crew_conditioned_frontier_portfolio_deterministic"):
        # No state-dependent legacy fallback: this isolated arm either solves
        # the complete projected master or the outer safety guard returns the
        # engine-safe action for the whole turn.
        choice = capital.decide(
            decision_snap, decision_plan, decision_capital_todo, fixed,
            None, deadline, capital_variant, capital_bank_routes,
            charge_activation_cost,
            productive_shed_relocation=productive_shed_relocation,
            service_cluster_layout=service_cluster_layout,
            land_turnover_option=land_turnover_option,
            bounded_land_quantity_frontier=(
                bounded_land_quantity_frontier
            ),
            crop_rotation_reinvestment=crop_rotation_reinvestment,
            joint_standing_capital=joint_standing_capital,
            joint_standing_portfolio_gate=joint_standing_portfolio_gate,
            land_frontier_certificate=land_frontier_certificate,
            single_quadrant_asset_class_exchange=(
                single_quadrant_asset_class_exchange
            ),
            opening_asset_class_exchange=opening_asset_class_exchange,
            opening_animal_retention=opening_animal_retention,
            turnover_positions=turnover_positions,
            turnover_items_by_position=turnover_items_by_position,
        )
    else:
        choice = (_guard(capital.decide, None, snap, plan, todo, fixed,
                         unit_actions, deadline, capital_variant,
                         capital_bank_routes,
                         charge_activation_cost)
                  if use_capital else None)
    if choice is None:
        free_slots = max(0, market.MAX_ORDERS - len(fixed))
        n_hire = _guard(hiring.decide, 0, decision_snap, decision_plan,
                        decision_todo, free_slots,
                        unit_actions, deadline, capital_bank_routes)
        orders = ([["HIRE"] for _ in range(n_hire)] + fixed)[:market.MAX_ORDERS]
    else:
        n_hire, assets, noncapital = choice
        if paid_weed_turnover and turnover_items_by_position:
            completed_assets = _guard(
                _certified_turnover_seed_assets, None,
                decision_snap, decision_plan, noncapital, assets,
                turnover_items_by_position,
            )
            if completed_assets is not None:
                assets = completed_assets
        if (paid_weed_turnover and not turnover_positions
                and int(decision_snap.hour) > 0
                and int(n_hire) == 0 and not assets):
            available_orders = max(
                0, market.MAX_ORDERS - len(noncapital),
            )
            cash_available = max(
                0.0,
                float(decision_snap.me.money)
                - float(getattr(
                    decision_plan, "service_cash_floor", 0.0,
                ) or 0.0)
                - _purchase_cost(decision_snap, noncapital),
            )
            # DIG may be inserted only into already-unused V199 route turns.
            # A new hand bought for current clearing changes the future crew
            # state before the crop's service suffix is certified.  Incremental
            # labour is therefore confined to an already-planted live suffix.
            turnover_hire_kinds = ("PAID_TURNOVER_SERVICE",)
            n_hire = _guard(
                tasks.paid_turnover_hires, 0,
                decision_snap, decision_plan, available_orders,
                cash_available, capital_bank_routes,
                turnover_hire_kinds,
            )
            if int(n_hire) > 0:
                _guard(
                    tasks.commit_paid_turnover_incremental_hire, False,
                    decision_snap, turnover_hire_kinds,
                )
        n_hire = _opening_hires(
            decision_snap, n_hire, assets, noncapital, opening_hire_floor,
        )
        orders = capital.compose_orders(
            noncapital, n_hire, assets,
            frontload_sales=(
                capital_variant
                == "ordinary_bundle_master_cash_sales_deterministic"
            ),
        )
    # Optional public-state capacity certificate.  This is intentionally a
    # post-process after capital selection: freeing a shed slot may improve
    # physical survival, but it is not allowed to fund or select purchases in
    # the same market phase.  The isolated V214 wrapper enables it at the
    # daily boundary only.
    if market_variant in ("capacity_reserve", "capacity_reserve_public_priority"):
        if market_variant == "capacity_reserve_public_priority":
            orders = _guard(
                market.capacity_reserve_orders, orders,
                snap, plan, orders, unit_actions, capacity_projected,
                99, "public",
            )
        else:
            orders = _guard(
                market.capacity_reserve_orders, orders,
                snap, plan, orders, unit_actions, capacity_projected,
            )
    if market_variant == "one_step_inventory_option":
        orders = _guard(
            market.defer_strictly_dominated_sales, orders,
            decision_snap, decision_plan, orders, unit_actions,
        )
    if bank_sales is True or bank_routes:
        orders = _guard(
            market.same_turn_bank_orders, orders, decision_snap, orders,
            unit_actions
        )

    # Hard action-space invariant: neither a legacy proposal nor an opt-in
    # challenger may leak a fourth-quadrant order past its planning guard.
    if not econ.can_buy_land(len(decision_snap.me.unlocked)):
        orders = [order for order in orders
                  if not order or order[0] != "BUY_LAND"]

    # The engine pads or truncates nothing: `hands` must match the live count.
    hands = (hands + [["PASS"]] * len(snap.me.hands))[:len(snap.me.hands)]
    out = {"farmer": list(farmer), "hands": [list(h) for h in hands],
           "market": [list(o) for o in orders][:market.MAX_ORDERS]}
    _guard(tr.record_my_orders, None, out["market"], decision_snap.shed)
    return out


def agent(obs, config=None):
    try:
        return act(obs, config)
    except Exception:
        return _safe(obs)


def variant_agent(obs, capital_master=False, config=None,
                  capital_variant=None, bank_sales=False,
                  robust_banking=False, plan_variant=None,
                  charge_activation_cost=True, deterministic_routes=False,
                  terminal_variant=None, task_value_variant=None,
                  deterministic_route_refine=False, market_variant=None,
                  opening_hire_floor=0, execution_variant=None,
                  productive_shed_tiles=False,
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
                  spatial_route_multistart=False,
                  paid_weed_turnover=False,
                  survival_feed_hard_core=False):
    """Versioned evaluation entry without process-global environment flags."""
    try:
        return act(obs, config, capital_master=capital_master,
                   capital_variant=capital_variant, bank_sales=bank_sales,
                   robust_banking=robust_banking, plan_variant=plan_variant,
                   charge_activation_cost=charge_activation_cost,
                   deterministic_routes=deterministic_routes,
                   terminal_variant=terminal_variant,
                   task_value_variant=task_value_variant,
                   deterministic_route_refine=deterministic_route_refine,
                   market_variant=market_variant,
                   opening_hire_floor=opening_hire_floor,
                   execution_variant=execution_variant,
                   productive_shed_tiles=productive_shed_tiles,
                   productive_shed_relocation=productive_shed_relocation,
                   service_cluster_layout=service_cluster_layout,
                   land_turnover_option=land_turnover_option,
                   bounded_land_quantity_frontier=(
                       bounded_land_quantity_frontier
                   ),
                   crop_rotation_reinvestment=crop_rotation_reinvestment,
                   joint_standing_capital=joint_standing_capital,
                   joint_standing_portfolio_gate=(
                       joint_standing_portfolio_gate
                   ),
                   land_frontier_certificate=land_frontier_certificate,
                   single_quadrant_asset_class_exchange=(
                       single_quadrant_asset_class_exchange
                   ),
                   opening_asset_class_exchange=opening_asset_class_exchange,
                   opening_animal_retention=opening_animal_retention,
                   spatial_route_multistart=spatial_route_multistart,
                   paid_weed_turnover=paid_weed_turnover,
                   survival_feed_hard_core=survival_feed_hard_core)
    except Exception:
        return _safe(obs)
    finally:
        # ``value`` is shared by every agent imported in this interpreter.
        # An opt-in event-calendar experiment must end with the historical
        # mode restored, otherwise the next (possibly opponent) action would
        # inherit our private evaluation context and invalidate paired tests.
        _value.set_exact_zero_day_age(False)


def _whitebox_entry(obs):
    return agent(obs)
