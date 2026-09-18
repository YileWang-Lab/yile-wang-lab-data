"""Equation tests for the bounded multi-day portfolio certificate."""
import unittest
from types import SimpleNamespace
from unittest import mock

from whitebox import cashflow, econ, market_model, strategy


def _snap(day=0, money=3000, shed=None, market=None, empty=20):
    tiles = [["LOCKED" for _x in range(10)] for _y in range(10)]
    open_positions = [(x, y) for y in range(5) for x in range(5)
                      if (x, y) not in {(4, 4)}][:empty]
    for x, y in open_positions:
        tiles[y][x] = None
    me = SimpleNamespace(
        money=float(money), unlocked=["NW"], tiles=tiles,
        empty=list(open_positions),
        animals={}, crops={}, hands=[], farmer=(4, 4), hires_today=0,
        animal_counts=lambda: {kind: 0 for kind in econ.ANIMALS},
    )
    opp = SimpleNamespace(animals={}, crops={})
    snap = SimpleNamespace(
        day=day, step=day * 24, days_left=max(0, 29 - day),
        me=me, opp=opp, shed=dict(shed or {}), seeds={},
        market_inv=dict(market or {item: econ.MARKET_I0
                                   for item in econ.SELLABLE}),
        board=10,
        shed_used=sum((shed or {}).values()),
        shops=(), config={},
    )
    snap.carried = lambda: {}
    return snap


class CashflowCertificateTests(unittest.TestCase):
    def test_merge_positioned_work_initializes_missing_pickup_day(self):
        stops = {}
        feed = {}
        pickups = {}
        cashflow._merge_positioned_work(
            stops, feed, pickups, {}, {},
            {7: {(2, 3): {"WHEAT"}}},
        )
        self.assertEqual(
            pickups,
            {7: {(2, 3): {"WHEAT"}}},
        )

    def test_fourth_quadrant_is_absent_from_the_action_space(self):
        self.assertTrue(econ.can_buy_land(1))
        self.assertTrue(econ.can_buy_land(2))
        self.assertFalse(econ.can_buy_land(3))
        snap = _snap()
        snap.me.unlocked = ["NW", "NE", "SW"]
        for y, row in enumerate(snap.me.tiles):
            for x in range(len(row)):
                if x < 5 or y < 5:
                    row[x] = None
        current = cashflow._available_slots(snap, include_next_land=False)
        attempted = cashflow._available_slots(snap, include_next_land=True)
        self.assertEqual(attempted, current)

    def test_productive_inventory_bundle_matches_exhaustive_hidden_allocation(self):
        snap = _snap(day=0, market={item: econ.MARKET_I0
                                    for item in econ.SELLABLE})
        outputs = {2: {"MILK": 2, "WOOL": 1}}
        bundle = {"MILK": 3, "WOOL": 2}
        got = cashflow.productive_inventory_terms(
            snap, outputs, bundle, sell_now=False, opponent_capacity=2,
        )
        self.assertEqual(got["anchor_day"], 2)

        visible = cashflow._remaining_visible_units(snap, snap.me)
        visible.update(cashflow._remaining_visible_units(snap, snap.opp))
        expected = float("inf")
        for milk_hidden in range(3):
            for wool_hidden in range(3 - milk_hidden):
                total = 0.0
                for item, qty, hidden in (
                        ("MILK", 5, milk_hidden),
                        ("WOOL", 3, wool_hidden)):
                    drain = market_model.town_take_bounds(
                        snap, item, start_step=snap.step, end_step=48,
                    )[0]
                    base = max(0, econ.MARKET_I0 - drain)
                    base += visible.get(item, 0)
                    _value, after = cashflow._sale_result(item, hidden, base)
                    total += cashflow._sale_result(item, qty, after)[0]
                expected = min(expected, total)
        self.assertEqual(got["paired_revenue"], expected)
        self.assertEqual(got["future_cash"], expected)

    def test_productive_inventory_path_values_all_outputs_and_safe_prefixes(self):
        snap = _snap(day=0, market={item: econ.MARKET_I0
                                    for item in econ.SELLABLE})
        outputs = {
            2: {"MILK": 1, "WOOL": 1},
            3: {"MILK": 2, "WOOL": 2},
        }
        bundle = {"MILK": 2}
        got = cashflow.productive_inventory_path_terms(
            snap, outputs, bundle, sell_now=False, opponent_capacity=2,
        )
        scenario_prefixes = []
        for milk_hidden in range(3):
            for wool_hidden in range(3 - milk_hidden):
                cumulative = 0.0
                prefix = {}
                for item, hidden in (("MILK", milk_hidden),
                                     ("WOOL", wool_hidden)):
                    drain = market_model.town_take_bounds(
                        snap, item, start_step=0, end_step=48,
                    )[0]
                    base = max(0, econ.MARKET_I0 - drain)
                    _value, book = cashflow._sale_result(item, hidden, base)
                    item_cumulative = 0.0
                    for day, qty in ((2, outputs[2].get(item, 0)
                                      + bundle.get(item, 0)),
                                     (3, outputs[3].get(item, 0))):
                        gained, book = cashflow._sale_result(item, qty, book)
                        item_cumulative += gained
                        prefix[day] = prefix.get(day, 0.0) + item_cumulative
                scenario_prefixes.append(prefix)
        self.assertEqual(
            got["paired_revenue"],
            min(prefix[3] for prefix in scenario_prefixes),
        )
        for prefix in scenario_prefixes:
            self.assertLessEqual(got["prefix_cash"][2], prefix[2])
            self.assertLessEqual(got["prefix_cash"][3], prefix[3])

    def test_productive_feasibility_path_skips_only_unused_terminal_value(self):
        snap = _snap(day=0, market={item: econ.MARKET_I0
                                    for item in econ.SELLABLE})
        outputs = {2: {"MILK": 1, "WOOL": 1},
                   3: {"MILK": 2, "WOOL": 2}}
        bundle = {"MILK": 2}
        full = cashflow.productive_inventory_path_terms(
            snap, outputs, bundle, sell_now=False, opponent_capacity=2,
        )
        with mock.patch.object(
                cashflow, "_allocation_dp",
                side_effect=AssertionError("terminal objective must be absent")):
            proof = cashflow.productive_inventory_path_terms(
                snap, outputs, bundle, sell_now=False, opponent_capacity=2,
                include_paired_value=False,
            )
        self.assertEqual(proof["anchor_day"], full["anchor_day"])
        self.assertEqual(proof["current_cash"], full["current_cash"])
        self.assertEqual(proof["prefix_cash"], full["prefix_cash"])
        self.assertEqual(proof["future_products_by_day"],
                         full["future_products_by_day"])

    def test_post_market_sale_cash_cannot_rescue_upfront_purchase(self):
        snap = _snap(day=0, money=100, empty=4)
        slot = cashflow._available_slots(snap)[0]
        cert = cashflow.certify_shared(
            snap, {"WHEAT": 1}, [slot], reserve=95,
            positions_by_item={"WHEAT": [slot]}, post_market_cash=1000,
            credit_output_cash=False,
        )
        self.assertFalse(cert.feasible)
        self.assertEqual(cert.reason, "upfront_cash")

    def test_post_market_sale_cash_can_fund_later_certified_service(self):
        snap = _snap(day=0, money=305, empty=4)
        slot = cashflow._available_slots(snap)[0]
        kwargs = dict(
            positions_by_item={"GOOSE": [slot]},
            credit_output_cash=False,
        )
        without = cashflow.certify_shared(
            snap, {"GOOSE": 1}, [slot], **kwargs,
        )
        with_sale = cashflow.certify_shared(
            snap, {"GOOSE": 1}, [slot], post_market_cash=10000, **kwargs,
        )
        self.assertFalse(without.feasible)
        self.assertEqual(without.reason, "bridge_cash")
        self.assertTrue(with_sale.feasible, with_sale.reason)
        self.assertGreater(with_sale.operating_cost, 0)

    def test_persistent_inventory_is_in_daily_shed_peak(self):
        snap = _snap(day=0, money=100000, shed={"MILK": 99}, empty=4)
        slot = cashflow._available_slots(snap)[0]
        cert = cashflow.certify_shared(
            snap, {"WHEAT": 1}, [slot],
            positions_by_item={"WHEAT": [slot]},
            persistent_shed_by_day={day: 99 for day in range(30)},
            credit_output_cash=False,
        )
        self.assertFalse(cert.feasible)
        self.assertEqual(cert.reason, "shed_capacity")

    def test_conserved_hidden_stock_budget_is_not_duplicated_by_item(self):
        # One hidden unit can damage either item but not both. Independently
        # assigning the same unit to both would return zero instead of ten.
        costs = [[10.0, 0.0], [10.0, 0.0]]
        self.assertEqual(cashflow._allocation_dp(costs, 1), 10.0)

    def test_same_slot_sale_uses_engine_per_unit_lockstep(self):
        # STRAWBERRY prices from inventory 10000 are 120, 118, 116.  Both
        # players' first units are quoted at 120; our tail is quoted at 116.
        result = cashflow._lockstep_sale_result(
            "STRAWBERRY", 2, 1, econ.MARKET_I0,
        )
        self.assertEqual(result, (236.0, 120.0, econ.MARKET_I0 + 3))
        self.assertEqual(
            cashflow._paired_sale_exact(
                "STRAWBERRY", 2, econ.MARKET_I0, 1,
            ),
            236.0,
        )
        self.assertNotEqual(
            cashflow._paired_sale_exact(
                "STRAWBERRY", 2, econ.MARKET_I0, 1,
            ),
            cashflow._sale_result(
                "STRAWBERRY", 2, econ.MARKET_I0,
            )[0],
        )

    def test_same_slot_sale_equation_matches_engine_simulator(self):
        from planner import simulate

        sim = simulate.Simulator.new_episode(seed=17)
        item = "MILK"
        inventory = econ.MARKET_I0 + 13
        ours, theirs = 9, 6
        sim.market["inventory"][item] = inventory
        sim.privates[0]["shed"][item] = ours
        sim.privates[1]["shed"][item] = theirs
        before = [farm["money"] for farm in sim.farms]
        simulate._process_market(
            sim.farms, sim.privates, sim.market,
            [{"market": [["SELL", item, ours]]},
             {"market": [["SELL", item, theirs]]}],
            sim.board_size, int(sim.cfg["maxMarketOrdersPerTurn"]),
            int(sim.cfg["farmHandCostMult"]),
            int(sim.cfg["shedCapacity"]),
        )
        expected_ours, expected_theirs, expected_book = (
            cashflow._lockstep_sale_result(
                item, ours, theirs, inventory,
            )
        )
        self.assertEqual(sim.farms[0]["money"] - before[0], expected_ours)
        self.assertEqual(sim.farms[1]["money"] - before[1], expected_theirs)
        self.assertEqual(sim.market["inventory"][item], expected_book)

    def test_hidden_bundle_dp_matches_exhaustive_shared_allocation(self):
        outputs = {"MILK": 4, "WOOL": 3}
        inventory = {item: econ.MARKET_I0 for item in econ.SELLABLE}
        visible = {"MILK": 1, "WOOL": 2}
        capacity = 3
        expected = float("inf")
        for milk_hidden in range(capacity + 1):
            for wool_hidden in range(capacity - milk_hidden + 1):
                milk = min(
                    cashflow._paired_sale_exact(
                        "MILK", 4, inventory["MILK"], q,
                    )
                    for q in range(visible["MILK"] + milk_hidden + 1)
                )
                wool = min(
                    cashflow._paired_sale_exact(
                        "WOOL", 3, inventory["WOOL"], q,
                    )
                    for q in range(visible["WOOL"] + wool_hidden + 1)
                )
                expected = min(expected, milk + wool)
        self.assertEqual(
            cashflow._paired_bundle_value(
                outputs, inventory, visible, capacity,
            ),
            expected,
        )

    def test_paired_sale_value_is_robust_over_quantity(self):
        item, qty, inv, upper = "MILK", 7, econ.MARKET_I0, 5
        expected = [cashflow._paired_sale_exact(item, qty, inv, opp_qty)
                    for opp_qty in range(upper + 1)]
        self.assertEqual(
            cashflow._paired_sale_value(item, qty, inv, upper),
            min(expected),
        )

    def test_visible_opponent_output_schedule_is_rule_bounded(self):
        snap = _snap(day=0)
        snap.opp.crops[(0, 0)] = {
            "kind": "PLANT", "crop": "MELON", "planted_day": 0,
            "yield_units": 2,
        }
        schedule = cashflow._visible_output_schedule(snap, snap.opp)
        # Already-held public output can be sold before our first modelled
        # return; full-service remaining one-time yield totals six, not eight.
        self.assertEqual(schedule[1]["MELON"], 2)
        self.assertEqual(sum(day.get("MELON", 0) for day in schedule.values()), 6)

    def test_visible_fertilizer_reserve_is_explicit_and_rule_bounded(self):
        snap = _snap(day=4)
        snap.me.animals[(0, 0)] = {
            "kind": "PASTURE", "animal": "COW", "placed_day": 0,
            "yield_units": 0, "fertilizer_available": True,
        }
        # Historical contexts deliberately omit the by-product.
        self.assertNotIn(
            "FERTILIZER", cashflow._remaining_visible_units(snap, snap.me),
        )
        self.assertFalse(any(
            day.get("FERTILIZER", 0)
            for day in cashflow._visible_output_schedule(
                snap, snap.me,
            ).values()
        ))
        remaining = cashflow._remaining_visible_units(
            snap, snap.me, include_fertilizer=True,
        )
        schedule = cashflow._visible_output_schedule(
            snap, snap.me, include_fertilizer=True,
        )
        self.assertEqual(remaining["FERTILIZER"], 1 + 29 - snap.day)
        self.assertEqual(schedule[5]["FERTILIZER"], 2)
        self.assertEqual(schedule[29]["FERTILIZER"], 1)
        self.assertEqual(
            sum(day.get("FERTILIZER", 0) for day in schedule.values()),
            remaining["FERTILIZER"],
        )

    def test_bounded_paired_constructor_has_structural_solve_limit(self):
        snap = _snap(money=5000, empty=12)
        proposal, cert = cashflow.invent_paired_proposal(
            snap, fixed_orders=[], reserve=0, reserve_inventory=True,
        )
        self.assertTrue(cert.feasible, cert.reason)
        self.assertTrue(proposal)
        item_types = len(econ.CROPS) + len(econ.ANIMALS)
        # Initial certificate + singleton ranking + at most one accepted
        # extension per slot and one stopping rejection per item ray.
        self.assertLessEqual(
            cert.evaluations, 1 + item_types + len(snap.me.empty) + item_types,
        )
        self.assertNotEqual(cert.paired_value, cert.final_cash)

    def test_crop_land_arm_uses_only_next_quadrant_and_never_animals(self):
        snap = _snap(money=100000, empty=24)
        orders, cert = cashflow._bounded_paired_branch(
            snap, [], 0.0, True, reserve_inventory=False,
            phase_aligned=True, allowed_items=tuple(econ.CROPS),
            new_land_only=True,
        )
        self.assertTrue(cert.feasible, cert.reason)
        self.assertTrue(cert.positions_by_item)
        self.assertIn(["BUY_LAND"], orders)
        self.assertFalse(any(order[0] == "BUY_ANIMAL" for order in orders))
        self.assertTrue(all(item in econ.CROPS
                            for item in cert.positions_by_item))
        self.assertTrue(all(
            cashflow.paths.quadrant_of(pos[0], pos[1], snap.board) == "NE"
            for positions in cert.positions_by_item.values()
            for pos in positions
        ))

    def test_exchange_line_search_never_reduces_paired_value(self):
        snap = _snap(money=5000, empty=12)
        _base_orders, base = cashflow.invent_paired_proposal(
            snap, fixed_orders=[], reserve=0, reserve_inventory=True,
        )
        orders, exchanged = cashflow.invent_exchange_proposal(
            snap, fixed_orders=[], reserve=0, reserve_inventory=True,
        )
        self.assertTrue(exchanged.feasible, exchanged.reason)
        self.assertGreaterEqual(exchanged.paired_value, base.paired_value)
        self.assertTrue(orders)
        # All directional derivatives plus one exact line contain no
        # wall-clock or iteration-until-time stopping condition.
        item_types = len(econ.CROPS) + len(econ.ANIMALS)
        self.assertLessEqual(
            exchanged.exchange_evaluations,
            item_types * item_types + len(snap.me.empty),
        )

    def test_shared_sweep_counts_geometry_once_between_nearby_units(self):
        # Four adjacent NW tasks share the path from the shed.  The historical
        # bound charges four independent eight-turn round trips; the closed
        # sweep pays shed travel once and still includes every operation,
        # return move, and DROP.
        stops = [((3, 4), 1), ((2, 4), 1), ((1, 4), 1), ((0, 4), 1)]
        routes = cashflow._pack_shared_routes(stops)
        independent = cashflow._pack_workers([9, 9, 9, 9])
        self.assertIsNotNone(routes)
        self.assertEqual(len(routes), 1)
        self.assertGreater(independent, len(routes))
        self.assertLessEqual(
            cashflow._shared_route_cost(routes[0]),
            cashflow.SHARED_ROUTE_TURNS,
        )

    def test_shared_routes_are_closed_and_cover_each_operation_once(self):
        stops = [((0, 0), 3), ((1, 0), 2), ((9, 9), 4)]
        routes = cashflow._pack_shared_routes(stops)
        self.assertIsNotNone(routes)
        flattened = [stop for route in routes for stop in route]
        self.assertEqual(sorted(flattened), sorted(stops))
        self.assertTrue(all(
            cashflow._shared_route_cost(route) <= cashflow.SHARED_ROUTE_TURNS
            for route in routes
        ))

    def test_two_phase_hires_use_only_engine_market_and_action_capacity(self):
        short_route = (((4, 4), 1),)
        routes = [short_route for _ in range(12)]
        self.assertEqual(
            cashflow._two_phase_hire_schedule(routes, {}, feed_qty=12),
            (9, 2),
        )
        # With feed in the first queue the two constructive phases can employ
        # the farmer plus 9+10 hands; one more route is not certified.
        self.assertEqual(
            cashflow._two_phase_hire_schedule(
                [short_route for _ in range(20)], {}, feed_qty=20,
            ),
            (9, 10),
        )
        self.assertIsNone(cashflow._two_phase_hire_schedule(
            [short_route for _ in range(21)], {}, feed_qty=21,
        ))

    def test_first_output_profiles_charge_minimum_survival_and_pickups(self):
        snap = _snap(day=0, money=100000, empty=8)
        positions = {"MELON": [(0, 0)], "GOOSE": [(1, 0)]}
        stops, feed, outputs, pickups, error = (
            cashflow._profiles_first_output_positioned(snap, positions)
        )
        self.assertIsNone(error)
        # Placement is conservatively modelled next day. MELON is watered on
        # days 1,3,5,7,9 and harvested on 11; skipping one night is safe.
        melon_days = [day for day, day_stops in stops.items()
                      if any(pos == (0, 0) for pos, _ops in day_stops)]
        self.assertEqual(melon_days, [1, 3, 5, 7, 9, 11])
        self.assertEqual(outputs[11]["MELON"], 6)
        # GOOSE needs no CARE for its first base unit. It survives placement
        # night, then is fed on days 2 and 4 and harvested on day 5.
        goose_days = sorted(day for day, day_stops in stops.items()
                            if any(pos == (1, 0)
                                   for pos, _ops in day_stops))
        self.assertEqual(goose_days, [1, 2, 4, 5])
        self.assertEqual(dict(feed), {2: 1, 4: 1})
        self.assertEqual(outputs[5]["EGG"], 1)
        self.assertEqual(pickups[1][(1, 0)], {"GOOSE"})
        self.assertEqual(pickups[2][(1, 0)], {"WHEAT"})

    def test_first_output_route_budget_includes_distinct_pickup_actions(self):
        # Find a physical sweep exactly on the no-carry limit. One required
        # item pickup must then force a second route (or reject the singleton),
        # proving it is not silently omitted from the 23-action budget.
        found = None
        positions = [(x, y) for y in range(10) for x in range(10)]
        for left in positions:
            for right in positions:
                if left >= right:
                    continue
                stops = [(left, 1), (right, 1)]
                routes = cashflow._pack_shared_routes(stops)
                if (routes is not None and len(routes) == 1
                        and cashflow._shared_route_cost(routes[0])
                        == cashflow.SHARED_ROUTE_TURNS):
                    found = stops
                    break
            if found:
                break
        self.assertIsNotNone(found)
        pickup_routes = cashflow._pack_shared_routes_with_pickups(
            found, {pos: {"WHEAT"} for pos, _ops in found},
        )
        self.assertIsNotNone(pickup_routes)
        self.assertGreater(len(pickup_routes), 1)

    def test_first_output_certificate_stops_after_one_grouped_sale(self):
        snap = _snap(day=0, money=100000, empty=8)
        slot = cashflow._available_slots(snap)[0]
        kwargs = dict(
            positions_by_item={"GOOSE": [slot]}, paired_objective=True,
        )
        prefix = cashflow.certify_shared(
            snap, {"GOOSE": 1}, [slot], first_output_only=True, **kwargs,
        )
        full = cashflow.certify_shared(
            snap, {"GOOSE": 1}, [slot], **kwargs,
        )
        self.assertTrue(prefix.feasible, prefix.reason)
        self.assertTrue(full.feasible, full.reason)
        self.assertEqual(
            {day: output for day, output in prefix.outputs_by_day.items()
             if output},
            {5: {"EGG": 1}},
        )
        self.assertLess(prefix.operating_cost, full.operating_cost)
        self.assertLess(max(prefix.routes_by_day), max(full.routes_by_day))

    def test_first_output_inventor_is_not_fixed_portfolio_ceiling(self):
        snap = _snap(day=0, money=100000, empty=20)
        proposal, cert = cashflow.invent_first_output_proposal(snap)
        self.assertTrue(cert.feasible, cert.reason)
        self.assertTrue(proposal)
        # The old proposal ceiling was 6 COW + 4 SHEEP + three crop quadrants.
        # This bounded rule/equation construction fills any improving physical
        # ray and therefore can invent a larger exact selected quantity.
        self.assertGreater(sum(cert.counts.values()), 13)
        self.assertLessEqual(len(proposal), econ.MAX_ORDERS)

    def test_first_output_inventor_reserves_pending_private_capital(self):
        snap = _snap(day=0, money=100000, empty=20)
        # Seeds already bought but not planted are irreversible claims on
        # future empty tiles. They cannot disappear merely because the daily
        # public-state MPC is proposing a fresh purchase.
        snap.seeds = {"MELON": 100}
        proposal, cert = cashflow.invent_first_output_proposal(snap)
        self.assertTrue(cert.feasible, cert.reason)
        self.assertEqual(proposal, [])
        self.assertEqual(cert.counts, {})

    def test_exact_first_output_uses_only_earned_one_time_growth(self):
        snap = _snap(day=0, money=100000, empty=8)
        assigned = {
            "WHEAT": [(0, 0)], "CARROT": [(1, 0)],
            "MELON": [(2, 0)], "TOMATO": [(3, 0)],
            "STRAWBERRY": [(4, 0)],
        }
        stops, _feed, outputs, _pickups, error = (
            cashflow._profiles_exact_first_output_positioned(snap, assigned)
        )
        self.assertIsNone(error)
        self.assertEqual(outputs[3]["WHEAT"], 2)
        self.assertEqual(outputs[3]["CARROT"], 2)
        self.assertEqual(outputs[11]["MELON"], 4)
        self.assertEqual(outputs[9]["TOMATO"], 1)
        self.assertEqual(outputs[11]["STRAWBERRY"], 1)
        # On the earliest legal one-time harvest day WATER must execute before
        # HARVEST to earn that day's rule-window increment.
        self.assertIn(((0, 0), 2), stops[3])
        self.assertIn(((2, 0), 2), stops[11])

    def test_exact_first_output_does_not_mutate_v98_legacy_semantics(self):
        snap = _snap(day=0, money=100000, empty=4)
        slot = cashflow._available_slots(snap)[0]
        kwargs = dict(
            positions_by_item={"WHEAT": [slot]}, paired_objective=True,
        )
        legacy = cashflow.certify_shared(
            snap, {"WHEAT": 1}, [slot], first_output_only=True, **kwargs,
        )
        exact = cashflow.certify_shared(
            snap, {"WHEAT": 1}, [slot], exact_first_output=True, **kwargs,
        )
        self.assertEqual(
            sum(day.get("WHEAT", 0) for day in legacy.outputs_by_day.values()),
            6,
        )
        self.assertEqual(
            sum(day.get("WHEAT", 0) for day in exact.outputs_by_day.values()),
            2,
        )
        self.assertLess(exact.paired_value, legacy.paired_value)

    def test_exact_first_output_quantities_match_simulator_transitions(self):
        from planner import simulate

        def harvested(crop):
            farm = {
                "tiles": [[None for _x in range(10)] for _y in range(10)],
                "farmer": [0, 0], "hands": [],
            }
            private = {
                "seeds": {crop: 1}, "shed": {}, "inventories": [{}],
            }
            simulate._apply_unit_action(
                farm, private, 0, ["PLANT", crop], 10, 1, 24,
            )
            simulate._apply_unit_action(
                farm, private, 0, ["WATER"], 10, 1, 24,
            )
            ready = 1 + econ.CROPS[crop]["first_yield_day"]
            for day in range(1, ready):
                simulate._daily_refresh_plants(farm, day, 24)
                next_day = day + 1
                if next_day < ready and (next_day - 1) % 2 == 0:
                    simulate._apply_unit_action(
                        farm, private, 0, ["WATER"], 10, next_day, 24,
                    )
            simulate._apply_unit_action(
                farm, private, 0, ["WATER"], 10, ready, 24,
            )
            simulate._apply_unit_action(
                farm, private, 0, ["HARVEST"], 10, ready, 24,
            )
            return private["inventories"][0].get(crop, 0)

        self.assertEqual(harvested("WHEAT"), 2)
        self.assertEqual(harvested("CARROT"), 2)
        self.assertEqual(harvested("MELON"), 4)

    def test_visible_survival_profile_is_rule_minimum_and_explicitly_bounded(self):
        snap = _snap(day=4, money=100000, empty=8)
        snap.me.crops[(0, 0)] = {"crop": "STRAWBERRY"}
        snap.me.crops[(1, 0)] = {"crop": "WHEAT"}
        snap.me.animals[(2, 0)] = {"animal": "COW"}
        stops, feed, pickups = cashflow._visible_survival_profile(snap, 10)
        by_day = {
            day: sorted(pos for pos, _ops in day_stops)
            for day, day_stops in stops.items()
        }
        # Tomorrow and every second day is the exact no-second-miss cadence.
        # The finite one-time WHEAT alternative is immediate abandonment.
        self.assertEqual(by_day, {
            5: [(0, 0), (2, 0)],
            7: [(0, 0), (2, 0)],
            9: [(0, 0), (2, 0)],
        })
        self.assertEqual(dict(feed), {5: 1, 7: 1, 9: 1})
        self.assertEqual(pickups[7][(2, 0)], {"WHEAT"})

    def test_joint_farm_prefix_equals_combined_less_same_dated_baseline(self):
        snap = _snap(day=0, money=100000, empty=8)
        snap.me.crops[(0, 0)] = {"crop": "STRAWBERRY"}
        slot = (1, 0)
        counts = {"WHEAT": 1}
        positions = {"WHEAT": [slot]}
        joint = cashflow.certify_joint_farm_prefix(
            snap, counts, [slot], positions_by_item=positions,
        )
        combined = cashflow.certify_shared(
            snap, counts, [slot], paired_objective=True,
            positions_by_item=positions, exact_first_output=True,
            visible_survival_horizon=3,
        )
        baseline = cashflow.certify_shared(
            snap, {}, (), paired_objective=True, exact_first_output=True,
            visible_survival_horizon=3, enforce_bridge_cash=False,
        )
        self.assertTrue(joint.feasible, joint.reason)
        self.assertEqual(joint.paired_value,
                         combined.paired_value - baseline.paired_value)
        day_one_positions = {
            pos for route in joint.routes_by_day[1] for pos, _ops in route
        }
        self.assertEqual(day_one_positions, {(0, 0), slot})

    def test_joint_farm_prefix_bridge_cash_includes_visible_animal_feed(self):
        snap = _snap(day=0, money=100, empty=8)
        snap.me.animals[(0, 0)] = {"animal": "COW"}
        slot = (1, 0)
        kwargs = dict(positions_by_item={"WHEAT": [slot]})
        isolated = cashflow.certify_shared(
            snap, {"WHEAT": 1}, [slot], reserve=80,
            paired_objective=True, exact_first_output=True, **kwargs,
        )
        joint = cashflow.certify_joint_farm_prefix(
            snap, {"WHEAT": 1}, [slot], reserve=80, **kwargs,
        )
        self.assertTrue(isolated.feasible, isolated.reason)
        self.assertFalse(joint.feasible)
        self.assertEqual(joint.reason, "bridge_cash")

    def test_minimal_full_continuation_uses_base_outputs_and_survival_feed(self):
        snap = _snap(day=0, money=100000, empty=8)
        assigned = {"STRAWBERRY": [(0, 0)], "COW": [(1, 0)]}
        stops, feed, outputs, pickups, error = (
            cashflow._profiles_minimal_full_output_positioned(snap, assigned)
        )
        self.assertIsNone(error)
        strawberry_days = [
            day for day, out in outputs.items() if out.get("STRAWBERRY")
        ]
        milk_days = sorted(day for day, out in outputs.items()
                           if out.get("MILK"))
        self.assertEqual(strawberry_days, [11, 13, 15, 17])
        self.assertEqual(milk_days, list(range(9, 30, 2)))
        self.assertTrue(all(outputs[day]["MILK"] == 1 for day in milk_days))
        self.assertEqual(dict(feed), {day: 1 for day in range(2, 30, 2)})
        self.assertEqual(pickups[28][(1, 0)], {"WHEAT"})
        # CARE is omitted: animal service is one FEED action on feed days,
        # plus a separate HARVEST only on production-sale days.
        self.assertIn(((1, 0), 1), stops[28])

    def test_optional_continuation_keeps_exact_first_abandonment_endpoint(self):
        snap = _snap(day=0, money=100000, empty=8)
        slot = (0, 0)
        common = dict(
            positions_by_item={"MELON": [slot]}, paired_objective=True,
        )
        first = cashflow.certify_shared(
            snap, {"MELON": 1}, [slot], exact_first_output=True, **common,
        )
        optional = cashflow.certify_optional_continuation(
            snap, {"MELON": 1}, [slot], positions_by_item={"MELON": [slot]},
        )
        self.assertTrue(optional.feasible, optional.reason)
        self.assertEqual(optional.paired_value, first.paired_value)
        self.assertEqual(optional.outputs_by_day, first.outputs_by_day)

    def test_optional_continuation_selects_profitable_recurring_endpoint(self):
        snap = _snap(day=0, money=100000, empty=8)
        slot = (0, 0)
        first = cashflow.certify_shared(
            snap, {"COW": 1}, [slot], paired_objective=True,
            positions_by_item={"COW": [slot]}, exact_first_output=True,
        )
        optional = cashflow.certify_optional_continuation(
            snap, {"COW": 1}, [slot],
            positions_by_item={"COW": [slot]},
        )
        self.assertTrue(optional.feasible, optional.reason)
        self.assertGreater(optional.paired_value, first.paired_value)
        self.assertGreater(sum(day.get("MILK", 0)
                               for day in optional.outputs_by_day.values()), 1)

    def test_shared_certificate_uses_actual_unique_candidate_positions(self):
        snap = _snap(money=100000, empty=12)
        slots = cashflow._available_slots(
            snap, include_next_land=False, reserve_inventory=True,
        )
        cert = cashflow.certify_shared(
            snap, {"WHEAT": 4, "GOOSE": 2}, slots,
            reserve=0, land_cost=0, fixed_orders=[],
        )
        self.assertTrue(cert.feasible, cert.reason)
        used = [pos for routes in cert.routes_by_day.values()
                for route in routes for pos, _ops in route]
        self.assertTrue(used)
        self.assertTrue(set(used).issubset(set(slots)))
        # A physical unit owns one slot, reused across service days; no daily
        # profile may contain duplicate positions.
        for routes in cert.routes_by_day.values():
            daily = [pos for route in routes for pos, _ops in route]
            self.assertEqual(len(daily), len(set(daily)))

    def test_phase_aligned_crop_output_uses_purchase_day_calendar(self):
        snap = _snap(day=0, money=100000, empty=8)
        slots = cashflow._available_slots(snap)
        legacy = cashflow.certify_shared(
            snap, {"WHEAT": 1}, slots, positions_by_item={"WHEAT": [slots[0]]},
        )
        aligned = cashflow.certify_shared(
            snap, {"WHEAT": 1}, slots,
            positions_by_item={"WHEAT": [slots[0]]}, phase_aligned=True,
        )
        self.assertTrue(legacy.feasible, legacy.reason)
        self.assertTrue(aligned.feasible, aligned.reason)
        self.assertEqual(min(day for day, out in legacy.outputs_by_day.items()
                             if out.get("WHEAT", 0) > 0), 3)
        self.assertEqual(min(day for day, out in aligned.outputs_by_day.items()
                             if out.get("WHEAT", 0) > 0), 2)
        # Today's PLANT+WATER is proved by the live route master, not charged
        # again as a fictitious second certificate route.
        self.assertNotIn(0, aligned.routes_by_day)

    def test_phase_aligned_animal_defers_feed_until_after_survival_night(self):
        snap = _snap(day=0, money=100000, empty=8)
        slots = cashflow._available_slots(snap)
        aligned = cashflow.certify_shared(
            snap, {"GOOSE": 1}, slots,
            positions_by_item={"GOOSE": [slots[0]]}, phase_aligned=True,
        )
        self.assertTrue(aligned.feasible, aligned.reason)
        self.assertNotIn(0, aligned.feed_by_day)
        self.assertEqual(aligned.feed_by_day[1], 1)
        self.assertNotIn(0, aligned.routes_by_day)

    def test_fertilizer_bridge_credits_only_routed_collect_operations(self):
        snap = _snap(day=0, money=100000, empty=8)
        slots = cashflow._available_slots(snap)
        positioned = {"GOOSE": [slots[0]]}
        legacy = cashflow.certify_shared(
            snap, {"GOOSE": 1}, slots,
            positions_by_item=positioned, phase_aligned=True,
            paired_objective=True,
        )
        bridge = cashflow.certify_shared(
            snap, {"GOOSE": 1}, slots,
            positions_by_item=positioned, phase_aligned=True,
            paired_objective=True, credit_fertilizer=True,
        )
        self.assertTrue(legacy.feasible, legacy.reason)
        self.assertTrue(bridge.feasible, bridge.reason)
        self.assertNotIn("FERTILIZER", legacy.outputs_by_day[1])
        self.assertEqual(bridge.outputs_by_day[1]["FERTILIZER"], 1)
        legacy_ops = sum(ops for route in legacy.routes_by_day[1]
                         for _pos, ops in route)
        bridge_ops = sum(ops for route in bridge.routes_by_day[1]
                         for _pos, ops in route)
        self.assertEqual(bridge_ops, legacy_ops + 1)
        self.assertGreater(bridge.paired_value, legacy.paired_value)

    def test_shared_certificate_exposes_and_proves_exact_item_positions(self):
        snap = _snap(money=100000, empty=12)
        slots = cashflow._available_slots(snap)
        positioned = {"WHEAT": [slots[3], slots[0]], "GOOSE": [slots[5]]}
        cert = cashflow.certify_shared(
            snap, {"WHEAT": 2, "GOOSE": 1}, slots,
            reserve=0, fixed_orders=[], paired_objective=True,
            positions_by_item=positioned,
        )
        self.assertTrue(cert.feasible, cert.reason)
        self.assertEqual(cert.positions_by_item, {
            "WHEAT": tuple(positioned["WHEAT"]),
            "GOOSE": tuple(positioned["GOOSE"]),
        })
        used = {pos for routes in cert.routes_by_day.values()
                for route in routes for pos, _ops in route}
        self.assertEqual(used, set(positioned["WHEAT"] + positioned["GOOSE"]))

    def test_exact_position_certificate_rejects_reassigned_or_duplicate_tiles(self):
        snap = _snap(money=100000, empty=12)
        slots = cashflow._available_slots(snap)
        for positioned in (
                {"WHEAT": [slots[0]]},
                {"WHEAT": [slots[0], slots[0]]},
                {"WHEAT": [slots[0], (9, 9)]}):
            cert = cashflow.certify_shared(
                snap, {"WHEAT": 2}, slots, positions_by_item=positioned,
            )
            self.assertFalse(cert.feasible)
            self.assertEqual(cert.reason, "physical_slots")

    def test_paired_inventor_excludes_route_master_reserved_tiles(self):
        snap = _snap(money=5000, empty=12)
        blocked = set(snap.me.empty[:4])
        _proposal, cert = cashflow.invent_paired_proposal(
            snap, fixed_orders=[], reserve=0, reserve_inventory=False,
            blocked_positions=blocked,
        )
        assigned = {pos for positions in cert.positions_by_item.values()
                    for pos in positions}
        self.assertTrue(cert.feasible, cert.reason)
        self.assertTrue(assigned)
        self.assertTrue(assigned.isdisjoint(blocked))

    def test_same_day_output_clears_as_one_joint_quantity(self):
        book = {"STRAWBERRY": econ.MARKET_I0}
        revenue, after = cashflow._sell_outputs(
            book, {"STRAWBERRY": 8},
        )
        self.assertEqual(
            revenue,
            econ.sell_revenue("STRAWBERRY", 8, econ.MARKET_I0),
        )
        moved = sum(
            econ.price("STRAWBERRY", econ.MARKET_I0 + i) > econ.PRICE_FLOOR
            for i in range(8)
        )
        self.assertEqual(after["STRAWBERRY"], econ.MARKET_I0 + moved)

    def test_certificate_proves_reserve_on_every_modelled_day(self):
        snap = _snap(money=5000)
        cert = cashflow.certify(
            snap, {"WHEAT": 2}, reserve=300, max_distance=0,
        )
        self.assertTrue(cert.feasible, cert.reason)
        self.assertTrue(cert.cash_path)
        self.assertGreaterEqual(min(cert.cash_path), 300)
        self.assertEqual(cert.upfront_spend, 2 * econ.CROPS["WHEAT"]["seed"])

    def test_land_fixed_charge_is_paid_once_for_shared_bundle(self):
        snap = _snap(money=5000)
        cert = cashflow.certify(
            snap, {"WHEAT": 2}, reserve=0, max_distance=0,
            land_cost=1000,
        )
        self.assertTrue(cert.feasible, cert.reason)
        self.assertEqual(
            cert.upfront_spend,
            1000 + 2 * econ.CROPS["WHEAT"]["seed"],
        )

    def test_rollover_shed_overflow_invalidates_bundle(self):
        snap = _snap(money=100000)
        cert = cashflow.certify(
            snap, {"MELON": 26}, reserve=0, max_distance=0,
        )
        self.assertFalse(cert.feasible)
        self.assertEqual(cert.reason, "shed_capacity")

    def test_daily_hire_and_feed_orders_respect_ten_slot_limit(self):
        snap = _snap(money=100000)
        # Eleven far-away cows require more than nine hired hands alongside
        # the day's single aggregated WHEAT feed order.
        cert = cashflow.certify(
            snap, {"COW": 11}, reserve=0, max_distance=8,
        )
        self.assertFalse(cert.feasible)
        self.assertEqual(cert.reason, "market_order_slots")

    def test_invented_proposal_is_not_the_fixed_six_cow_four_sheep_ceiling(self):
        snap = _snap(money=3000, empty=15)
        proposal, cert = cashflow.invent_proposal(
            snap, fixed_orders=[], reserve=0,
        )
        self.assertTrue(cert.feasible, cert.reason)
        counts = {(order[0], order[1]): order[2]
                  for order in proposal if len(order) >= 3}
        self.assertNotEqual(counts.get(("BUY_ANIMAL", "COW"), 0), 6)
        self.assertNotEqual(counts.get(("BUY_ANIMAL", "SHEEP"), 0), 4)
        self.assertTrue(any(order[0] in ("BUY_SEED", "BUY_ANIMAL")
                            for order in proposal))

    def test_pending_private_assets_reserve_physical_slots(self):
        snap = _snap(money=100000)
        # Pending seed is already committed capital even before the task layer
        # has planted it, including across the exact next-land branch.
        snap.seeds = {"WHEAT": 100}
        proposal, cert = cashflow.invent_proposal(
            snap, fixed_orders=[], reserve=0, reserve_inventory=True,
        )
        self.assertTrue(cert.feasible, cert.reason)
        self.assertEqual(proposal, [])

    def test_inventory_execution_plan_targets_every_observed_asset(self):
        snap = _snap(money=3000)
        snap.seeds = {"WHEAT": 3, "TOMATO": 2}
        snap.shed = {"GOOSE": 2}
        plan = strategy.decide(snap, variant="inventory_execution")
        self.assertEqual(plan.crop_targets, {"WHEAT": 3, "TOMATO": 2})
        self.assertEqual(plan.target_animals, {"GOOSE": 2})
        self.assertEqual(set(plan.crop_mix), {"WHEAT", "TOMATO"})


if __name__ == "__main__":
    unittest.main()
