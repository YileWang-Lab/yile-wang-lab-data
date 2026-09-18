"""Equation and wiring tests for the finite paid-response capital value."""
import unittest
from types import SimpleNamespace
from unittest import mock

from planner.simulate import Simulator
from whitebox import capital, cashflow, econ, paths, stackelberg, state
from whitebox.test_cashflow import _snap


class StackelbergValueTests(unittest.TestCase):
    def test_standing_book_reprices_only_the_shared_product_margin(self):
        snap = _snap(day=0, money=100000)
        drains = {2: {item: 0 for item in econ.SELLABLE}}
        response = stackelberg.Response("NO_RESPONSE")
        standing = {2: {"MILK": 12}}

        baseline = stackelberg._standing_response_margin(
            snap, {}, 0.0, response, {}, drains, standing,
        )
        milk_with_standing = stackelberg._standing_response_margin(
            snap, {2: {"MILK": 1}}, 0.0, response, {}, drains, standing,
        ) - baseline
        milk_on_empty_book = stackelberg._response_margin(
            snap, {2: {"MILK": 1}}, 0.0, response, {}, drains,
        )
        wool_with_standing = stackelberg._standing_response_margin(
            snap, {2: {"WOOL": 1}}, 0.0, response, {}, drains, standing,
        ) - baseline
        wool_on_empty_book = stackelberg._response_margin(
            snap, {2: {"WOOL": 1}}, 0.0, response, {}, drains,
        )

        self.assertLess(milk_with_standing, milk_on_empty_book)
        self.assertAlmostEqual(wool_with_standing, wool_on_empty_book)

    def test_robust_standing_modes_store_separate_no_action_baselines(self):
        snap = _snap(day=0, money=100000)
        position = snap.me.empty.pop()
        snap.me.animals[position] = {"animal": "COW"}
        x, y = position
        snap.me.tiles[y][x] = {"animal": "COW"}
        context = stackelberg.make_context(
            snap, robust_own_standing_realisation=True,
        )
        response = context["responses"][0]
        incremental = stackelberg._response_margin(
            snap, {}, 0.0, response,
            context["opponent_baseline"], context["drains"],
        )
        standing = stackelberg._standing_response_margin(
            snap, {}, 0.0, response,
            context["opponent_baseline"], context["drains"],
            context["own_baseline"],
        )
        self.assertEqual(
            context["baseline_robust_modes"],
            {"incremental": incremental, "standing": standing},
        )
        self.assertNotEqual(incremental, standing)

    def test_response_cost_enters_relative_margin_with_exact_sign(self):
        snap = _snap(day=0, money=100000)
        drains = {2: {item: 0 for item in econ.SELLABLE}}
        response = stackelberg.Response(
            "MILK_ONE", "COW", 1, 400.0,
            ((2, (("MILK", 1),)),),
        )
        own = {2: {"MILK": 2}}
        got = stackelberg._response_margin(
            snap, own, 30.0, response, {}, drains,
        )
        own_revenue, opponent_revenue, _book = (
            cashflow._lockstep_sale_result(
                "MILK", 2, 1, econ.MARKET_I0,
            )
        )
        self.assertEqual(
            got, own_revenue - opponent_revenue - 30.0 + 400.0,
        )
        free = stackelberg.Response(
            "MILK_ONE_FREE", "COW", 1, 0.0,
            response.outputs,
        )
        self.assertEqual(
            got - stackelberg._response_margin(
                snap, own, 30.0, free, {}, drains,
            ),
            400.0,
        )

    def test_public_response_set_pays_and_respects_public_resources(self):
        sim = Simulator.new_episode(seed=19)
        snap = state.extract(sim.observation_for(0), sim.cfg)
        context = stackelberg.make_context(snap)
        responses = context["responses"]
        self.assertEqual(responses[0].name, "NO_RESPONSE")
        self.assertEqual(
            len({response.item for response in responses[1:]}),
            len(responses) - 1,
        )
        for response in responses[1:]:
            unit_cost = (
                econ.CROPS[response.item]["seed"]
                if response.item in econ.CROPS
                else econ.ANIMALS[response.item]["cost"]
            )
            self.assertLessEqual(
                response.quantity * unit_cost, snap.opp.money,
            )
            self.assertGreaterEqual(response.cost, response.quantity * unit_cost)
            self.assertTrue(response.outputs)
        expected = min(
            stackelberg._response_margin(
                snap, {}, 0.0, response,
                context["opponent_baseline"], context["drains"],
            )
            for response in responses
        )
        self.assertEqual(context["baseline_robust"], expected)

    def test_full_response_continuation_values_more_than_first_animal_unit(self):
        sim = Simulator.new_episode(seed=19)
        snap = state.extract(sim.observation_for(0), sim.cfg)
        short = stackelberg.make_context(snap)["responses"]
        full = stackelberg.make_context(
            snap, full_response_continuation=True,
        )["responses"]
        short_cow = next(response for response in short
                         if response.item == "COW")
        full_cow = next(response for response in full
                        if response.item == "COW")
        self.assertGreater(
            sum(sum(products.values())
                for products in full_cow.schedule().values()),
            sum(sum(products.values())
                for products in short_cow.schedule().values()),
        )
        self.assertGreater(full_cow.cost, short_cow.cost)
        self.assertTrue(full_cow.name.endswith("_FULL"))

    def test_candidate_product_keeps_every_paid_response_quantity(self):
        sim = Simulator.new_episode(seed=19)
        snap = state.extract(sim.observation_for(0), sim.cfg)
        ordinary = stackelberg.make_context(
            snap, full_response_continuation=True,
        )
        complete = stackelberg.make_context(
            snap, full_response_continuation=True,
            candidate_response_products=("MILK", "WOOL"),
        )
        ordinary_cows = [response for response in ordinary["responses"]
                         if response.item == "COW"]
        complete_cows = [response for response in complete["responses"]
                         if response.item == "COW"]
        complete_sheep = [response for response in complete["responses"]
                          if response.item == "SHEEP"]
        ordinary_goose = [response for response in ordinary["responses"]
                          if response.item == "GOOSE"]
        complete_goose = [response for response in complete["responses"]
                          if response.item == "GOOSE"]
        self.assertEqual(len(ordinary_cows), 1)
        self.assertGreater(len(complete_cows), 1)
        self.assertGreater(len(complete_sheep), 1)
        self.assertEqual(complete_goose, ordinary_goose)
        self.assertEqual(
            complete["candidate_response_products"], ("MILK", "WOOL"),
        )

    def test_reinvestment_requires_realised_cash_and_closed_route(self):
        snap = _snap(day=0, money=100000, empty=8)
        snap.hour = 0
        slot = (0, 0)
        cert = cashflow.certify_shared(
            snap, {"MELON": 1}, [slot], reserve=0.0,
            positions_by_item={"MELON": [slot]},
            exact_first_output=True,
        )
        self.assertTrue(cert.feasible, cert.reason)
        options = stackelberg.feasible_reinvestments(snap, cert, reserve=0.0)
        self.assertGreater(len(options), 1)
        for option in options[1:]:
            self.assertIn("AFTER_DAY_", option.name)
            self.assertGreater(option.cost, 0.0)
            self.assertTrue(option.outputs)
        self.assertEqual(
            stackelberg.feasible_reinvestments(
                snap, cert, reserve=10**9,
            ),
            (stackelberg.Reinvestment("NO_REINVESTMENT"),),
        )

    def test_rotation_reinvestment_reuses_harvested_public_tile(self):
        snap = _snap(day=0, money=100000, empty=1)
        snap.hour = 0
        slot = cashflow._available_slots(snap)[0]
        cert = cashflow.certify_shared(
            snap, {"WHEAT": 1}, [slot], reserve=0.0,
            positions_by_item={"WHEAT": [slot]},
            exact_first_output=True,
        )
        options = stackelberg.feasible_reinvestments(
            snap, cert, release_harvested_land=True,
        )
        rotations = [option for option in options
                     if "ROTATE_WHEAT" in option.name]
        self.assertEqual(len(rotations), 1)
        output_days = [day for day, _products in rotations[0].outputs]
        self.assertGreater(len(output_days), 1)
        self.assertEqual(output_days, sorted(output_days))

    def test_deferred_capital_prices_animal_feed_and_empty_tile_option(self):
        snap = _snap(day=12, money=5000, empty=1)
        snap.hour = 0
        baseline = cashflow.certify_shared(snap, {}, (), reserve=0.0)
        options = stackelberg.feasible_deferred_capital(
            snap, baseline, reserve=0.0,
        )
        sheep = [option for option in options
                 if option.name == "DEFER_DAY_13_BUY_SHEEP_1"]
        self.assertEqual(len(sheep), 1)
        self.assertGreater(sheep[0].cost, econ.ANIMALS["SHEEP"]["cost"])
        self.assertEqual(
            sheep[0].schedule(), {20: {"WOOL": 1}},
        )
        self.assertEqual(sheep[0].purchase_day, 13)
        self.assertEqual(sheep[0].order, ("BUY_ANIMAL", "SHEEP", 1))
        self.assertEqual(len(sheep[0].positions()["SHEEP"]), 1)
        self.assertTrue(sheep[0].routes())
        self.assertTrue(sheep[0].hire_phases())
        full_options = stackelberg.feasible_deferred_capital(
            snap, baseline, reserve=0.0, full_continuation=True,
        )
        full_sheep = [option for option in full_options
                      if option.name
                      == "DEFER_DAY_13_BUY_SHEEP_1_FULL"]
        self.assertEqual(len(full_sheep), 1)
        self.assertGreater(full_sheep[0].cost, sheep[0].cost)
        self.assertEqual(
            [day for day, _products in full_sheep[0].outputs],
            [20, 23, 26, 29],
        )

        # A current one-shot crop still occupies its tile on purchase day 13;
        # the alternative may not pretend to place an animal through it.
        slot = cashflow._available_slots(snap)[0]
        occupied = cashflow.certify_shared(
            snap, {"WHEAT": 1}, [slot], reserve=0.0,
            positions_by_item={"WHEAT": [slot]},
            exact_first_output=True,
        )
        self.assertEqual(
            stackelberg.feasible_deferred_capital(snap, occupied),
            (stackelberg.Reinvestment("NO_DEFERRED_CAPITAL"),),
        )

    def test_output_cash_can_fund_paid_animal_after_one_shot_crop(self):
        snap = _snap(day=0, money=300, empty=1)
        snap.hour = 0
        slot = cashflow._available_slots(snap)[0]
        crop = cashflow.certify_shared(
            snap, {"MELON": 1}, [slot], reserve=0.0,
            positions_by_item={"MELON": [slot]},
            exact_first_output=True,
        )
        self.assertTrue(crop.feasible, crop.reason)
        self.assertLess(snap.me.money, econ.ANIMALS["COW"]["cost"])
        options = stackelberg.feasible_output_funded_capital(
            snap, crop, target_items=("COW",),
        )
        cows = [option for option in options
                if (option.order == ("BUY_ANIMAL", "COW", 1)
                    and option.name == "REINVEST_AFTER_DAY_11_BUY_COW_1")]
        self.assertEqual(len(cows), 1)
        self.assertGreater(cows[0].purchase_day,
                           min(crop.outputs_by_day))
        self.assertGreater(cows[0].cost, econ.ANIMALS["COW"]["cost"])
        self.assertTrue(cows[0].name.startswith("REINVEST_AFTER_DAY_"))
        self.assertTrue(cows[0].routes())
        self.assertTrue(cows[0].hire_phases())

    def test_output_cash_can_pay_next_land_and_asset_with_two_order_keys(self):
        snap = _snap(day=0, money=3000, empty=1)
        snap.hour = 0
        slot = cashflow._available_slots(snap)[0]
        crop = cashflow.certify_shared(
            snap, {"MELON": 1}, [slot], reserve=0.0,
            positions_by_item={"MELON": [slot]},
            exact_first_output=True,
        )
        options = stackelberg.feasible_output_funded_capital(
            snap, crop, target_items=("COW",), include_land=True,
        )
        land_cows = [option for option in options
                     if option.activates_land]
        self.assertTrue(land_cows)
        self.assertTrue(any(option.cost > snap.me.money
                            for option in land_cows))
        for option in land_cows:
            self.assertGreaterEqual(
                option.cost,
                econ.LAND_PRICES[0] + econ.ANIMALS["COW"]["cost"],
            )
            self.assertTrue(all(
                paths.quadrant_of(pos[0], pos[1], snap.board)
                == econ.LAND_ORDER[0]
                for pos in option.positions()["COW"]
            ))
            self.assertIn("BUY_LAND_NE_THEN_BUY_COW", option.name)

    def test_output_cash_can_fund_joint_crop_and_herd_frontiers(self):
        snap = _snap(day=0, money=3000, empty=24)
        snap.hour = 0
        slots = cashflow._available_slots(snap)
        first = cashflow.certify_shared(
            snap, {"WHEAT": 24}, slots,
            positions_by_item={"WHEAT": slots},
            exact_first_output=True,
        )
        self.assertTrue(first.feasible, first.reason)
        anchor = min(
            day for day, products in first.outputs_by_day.items()
            if any(products.values())
        )
        options = stackelberg.feasible_output_funded_mixed(snap, first)
        mixed = [option for option in options if option.order]
        self.assertEqual(
            {(option.order[1], option.order[3]) for option in mixed},
            {(crop, animal) for crop in econ.CROPS
             for animal in econ.ANIMALS},
        )
        self.assertTrue(any(option.cost > snap.me.money
                            for option in mixed))
        for option in mixed:
            self.assertEqual(option.order[0], "BUY_MIX")
            self.assertEqual(option.purchase_day, anchor + 1)
            crop, crop_qty = option.order[1], option.order[2]
            animal, animal_qty = option.order[3], option.order[4]
            self.assertGreater(crop_qty, 0)
            self.assertGreater(animal_qty, 0)
            positioned = option.positions()
            occupied = (list(positioned[crop])
                        + list(positioned[animal]))
            self.assertEqual(len(occupied), len(set(occupied)))
            self.assertLessEqual(len(occupied), len(slots))
            self.assertGreaterEqual(
                option.cost,
                crop_qty * econ.CROPS[crop]["seed"]
                + animal_qty * econ.ANIMALS[animal]["cost"],
            )
            self.assertTrue(option.outputs)

    def test_response_context_names_finite_output_funded_directions(self):
        sim = Simulator.new_episode(seed=19)
        snap = state.extract(sim.observation_for(0), sim.cfg)
        ordinary = stackelberg.make_context(
            snap, full_response_continuation=True,
        )
        staged = stackelberg.make_context(
            snap, full_response_continuation=True,
            staged_response_reinvestment=True,
        )
        ordinary_names = {response.name
                          for response in ordinary["responses"]}
        staged_responses = [
            response for response in staged["responses"]
            if "_THEN_REINVEST_AFTER_DAY_" in response.name
        ]
        self.assertTrue(staged_responses)
        self.assertTrue(ordinary_names.issubset(
            {response.name for response in staged["responses"]}
        ))
        self.assertTrue(staged["staged_response_reinvestment"])
        for response in staged_responses:
            self.assertIn("->", response.item)
            self.assertGreater(response.cost, 0.0)
            self.assertGreater(len(response.schedule()), 1)

    def test_empty_current_set_still_values_named_deferred_action(self):
        snap = _snap(day=12, money=5000, empty=1)
        snap.hour = 0
        context = stackelberg.make_context(snap)
        historical = stackelberg.certify_unified(
            snap, {}, (), context=context,
            deferred_capital_reinvestment=True,
            deferred_capital_full_continuation=True,
        )
        closed = stackelberg.certify_unified(
            snap, {}, (), context=context,
            deferred_capital_reinvestment=True,
            deferred_capital_full_continuation=True,
            close_empty_deferred_baseline=True,
        )
        self.assertEqual(historical.paired_value, 0.0)
        self.assertTrue(closed.feasible, closed.reason)
        self.assertGreater(closed.paired_value, 0.0)
        self.assertTrue(closed.selected_reinvestment.startswith("DEFER_DAY_13"))
        self.assertGreater(closed.selected_own_cost, 0.0)
        self.assertEqual(closed.selected_worst_response, "NO_RESPONSE")

    def test_bounded_deferred_horizon_routes_standing_productive_work(self):
        snap = _snap(day=12, money=100000, empty=20)
        snap.hour = 0
        position = snap.me.empty.pop()
        snap.me.animals[position] = {"animal": "COW"}
        x, y = position
        snap.me.tiles[y][x] = {"animal": "COW"}
        horizon = stackelberg._deferred_first_output_horizon(snap)
        cert = stackelberg.certify_unified(
            snap, {}, (), context=stackelberg.make_context(snap),
            deferred_capital_reinvestment=True,
            close_empty_deferred_baseline=True,
            deferred_standing_service_horizon=True,
            bounded_first_output_only=True,
            two_phase_future_hires=True,
        )
        self.assertEqual(horizon, 24)
        self.assertTrue(cert.feasible, cert.reason)
        self.assertEqual(max(cert.workers_by_day), horizon)
        self.assertFalse(cert.selected_full_endpoint)
        self.assertTrue(cert.selected_reinvestment.startswith("DEFER_DAY_13"))

    def test_land_option_pays_land_seed_and_two_order_keys(self):
        snap = _snap(day=0, money=100000, empty=20)
        snap.hour = 0
        slot = cashflow._available_slots(snap)[0]
        cert = cashflow.certify_shared(
            snap, {"WHEAT": 1}, [slot], reserve=0.0,
            positions_by_item={"WHEAT": [slot]},
            exact_first_output=True,
        )
        without = stackelberg.feasible_reinvestments(
            snap, cert, include_land_option=False,
        )
        with_land = stackelberg.feasible_reinvestments(
            snap, cert, include_land_option=True,
        )
        self.assertFalse(any("BUY_LAND" in option.name for option in without))
        land_options = [option for option in with_land
                        if option.name.endswith("BUY_LAND_NE_WHEAT_1")]
        self.assertEqual(len(land_options), 1)
        self.assertGreaterEqual(
            land_options[0].cost,
            econ.LAND_PRICES[0] + econ.CROPS["WHEAT"]["seed"],
        )

    def test_activated_land_fill_requires_current_paid_quadrant(self):
        snap = _snap(day=0, money=100000, empty=20)
        snap.hour = 0
        expanded = cashflow._available_slots(
            snap, include_next_land=True, reserve_inventory=False,
        )
        ne_slot = next(
            pos for pos in expanded
            if cashflow.paths.quadrant_of(pos[0], pos[1], snap.board) == "NE"
        )
        cert = cashflow.certify_shared(
            snap, {"WHEAT": 1}, [ne_slot], reserve=0.0,
            land_cost=econ.LAND_PRICES[0],
            positions_by_item={"WHEAT": [ne_slot]},
            exact_first_output=True,
        )
        without = stackelberg.feasible_reinvestments(
            snap, cert, include_activated_land=False,
        )
        with_fill = stackelberg.feasible_reinvestments(
            snap, cert, include_activated_land=True,
        )
        self.assertFalse(any("FILL_ACTIVATED" in option.name
                             for option in without))
        fills = [option for option in with_fill
                 if "FILL_ACTIVATED_NE_WHEAT_" in option.name]
        self.assertEqual(len(fills), 1)
        self.assertGreaterEqual(fills[0].cost, econ.CROPS["WHEAT"]["seed"])
        self.assertLess(fills[0].cost, econ.LAND_PRICES[0])

    def test_unified_endpoint_packs_standing_and_new_work_together(self):
        snap = _snap(day=0, money=100000, empty=8)
        snap.hour = 0
        snap.me.crops[(0, 0)] = {"crop": "STRAWBERRY"}
        slot = (1, 0)
        cert = stackelberg.certify_unified(
            snap, {"WHEAT": 1}, [slot], reserve=0.0,
            positions_by_item={"WHEAT": [slot]},
            context=stackelberg.make_context(snap),
        )
        self.assertTrue(cert.feasible, cert.reason)
        routed = {
            pos for routes in cert.routes_by_day.values()
            for route in routes for pos, _ops in route
        }
        self.assertEqual(routed, {(0, 0), slot})
        self.assertGreater(cert.paired_value, 0.0)

    def test_full_service_background_charges_actual_public_operations(self):
        snap = _snap(day=0, money=100000, empty=8)
        snap.me.crops[(0, 0)] = {"crop": "STRAWBERRY"}
        snap.me.animals[(1, 0)] = {"animal": "COW"}
        stops, feed, pickups = cashflow._visible_full_service_profile(
            snap, 2, start_day=0,
        )
        by_day = {day: dict(day_stops) for day, day_stops in stops.items()}
        # Today's projected unit phase is excluded. On future days the crop
        # pays WATER, while the animal pays FEED+CARE+fertilizer collection.
        self.assertEqual(by_day[1][(0, 0)], 1)
        self.assertEqual(by_day[1][(1, 0)], 3)
        self.assertEqual(by_day[2][(0, 0)], 1)
        self.assertEqual(by_day[2][(1, 0)], 3)
        self.assertEqual(dict(feed), {1: 1, 2: 1})
        self.assertEqual(pickups[2][(1, 0)], {"WHEAT"})

    def test_variant_is_explicitly_isolated(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (2, [["BUY_SEED", "MELON", 3]], [])
        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = capital.decide(
                snap, plan, [], [],
                variant=(
                    "crew_conditioned_stackelberg_reinvestment_deterministic"
                ),
            )
        self.assertEqual(got, expected)
        kwargs = decide_crew.call_args.kwargs
        self.assertTrue(kwargs["memoize_proposals"])
        self.assertTrue(kwargs["stackelberg"])

    def test_land_variant_is_explicitly_isolated(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (3, [["BUY_SEED", "WHEAT", 8]], [])
        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = capital.decide(
                snap, plan, [], [],
                variant=(
                    "crew_conditioned_stackelberg_land_reinvestment_deterministic"
                ),
            )
        self.assertEqual(got, expected)
        kwargs = decide_crew.call_args.kwargs
        self.assertTrue(kwargs["stackelberg"])
        self.assertTrue(kwargs["land_reinvestment"])

    def test_activated_land_variant_is_explicitly_isolated(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (4, [["BUY_SEED", "STRAWBERRY", 9]], [])
        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = capital.decide(
                snap, plan, [], [],
                variant=(
                    "crew_conditioned_stackelberg_activated_land_deterministic"
                ),
            )
        self.assertEqual(got, expected)
        kwargs = decide_crew.call_args.kwargs
        self.assertTrue(kwargs["stackelberg"])
        self.assertFalse(kwargs["land_reinvestment"])
        self.assertTrue(kwargs["activated_land_reinvestment"])

    def test_land_arm_variant_recertifies_both_physical_arms(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (5, [["BUY_SEED", "MELON", 11]], [])
        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = capital.decide(
                snap, plan, [], [],
                variant="crew_conditioned_stackelberg_land_arm_deterministic",
            )
        self.assertEqual(got, expected)
        kwargs = decide_crew.call_args.kwargs
        self.assertTrue(kwargs["stackelberg"])
        self.assertTrue(kwargs["activated_land_reinvestment"])
        self.assertTrue(kwargs["stackelberg_arm_recertification"])

    def test_full_service_variant_is_explicitly_isolated(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (2, [["BUY_ANIMAL", "SHEEP", 3]], [])
        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = capital.decide(
                snap, plan, [], [],
                variant=(
                    "crew_conditioned_stackelberg_full_service_deterministic"
                ),
            )
        self.assertEqual(got, expected)
        kwargs = decide_crew.call_args.kwargs
        self.assertTrue(kwargs["stackelberg"])
        self.assertTrue(kwargs["stackelberg_arm_recertification"])
        self.assertTrue(kwargs["full_service_continuation"])

    def test_standing_book_exchange_variant_is_explicitly_isolated(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (4, [["BUY_ANIMAL", "SHEEP", 2]], [])
        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = capital.decide(
                snap, plan, [], [],
                variant=(
                    "crew_conditioned_positioned_standing_scenario_dominant_exchange_deterministic"
                ),
            )
        self.assertEqual(got, expected)
        kwargs = decide_crew.call_args.kwargs
        self.assertTrue(kwargs["scenario_dominant_composition_exchange"])
        self.assertTrue(kwargs["standing_book_composition_exchange"])

    def test_structure_robust_rebalance_variant_is_explicitly_isolated(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (3, [["BUY_ANIMAL", "COW", 2]], [])
        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = capital.decide(
                snap, plan, [], [],
                variant=(
                    "crew_conditioned_positioned_standing_structure_robust_deterministic"
                ),
            )
        self.assertEqual(got, expected)
        kwargs = decide_crew.call_args.kwargs
        self.assertTrue(kwargs["scenario_dominant_composition_exchange"])
        self.assertTrue(kwargs["standing_structure_robust_after_scenario"])
        self.assertFalse(kwargs["standing_book_composition_exchange"])

    def test_complete_response_rebalance_variant_is_explicitly_isolated(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (3, [["BUY_ANIMAL", "SHEEP", 2]], [])
        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = capital.decide(
                snap, plan, [], [],
                variant=(
                    "crew_conditioned_positioned_standing_structure_complete_response_deterministic"
                ),
            )
        self.assertEqual(got, expected)
        kwargs = decide_crew.call_args.kwargs
        self.assertTrue(kwargs["scenario_dominant_composition_exchange"])
        self.assertTrue(
            kwargs["standing_structure_complete_response_after_scenario"],
        )

    def test_crop_land_arm_variant_is_explicitly_isolated(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (4, [["BUY_SEED", "WHEAT", 12], ["BUY_LAND"]], [])
        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = capital.decide(
                snap, plan, [], [],
                variant=(
                    "crew_conditioned_positioned_scenario_crop_land_arm_deterministic"
                ),
            )
        self.assertEqual(got, expected)
        kwargs = decide_crew.call_args.kwargs
        self.assertTrue(kwargs["scenario_dominant_composition_exchange"])
        self.assertTrue(kwargs["positioned_capital_manifest"])
        self.assertTrue(kwargs["crop_only_land_arm"])
        self.assertFalse(kwargs["stackelberg"])

    def test_robust_crop_land_variant_prices_rows_on_the_same_game_book(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (5, [["BUY_SEED", "MELON", 18], ["BUY_LAND"]], [])
        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = capital.decide(
                snap, plan, [], [],
                variant=(
                    "crew_conditioned_positioned_scenario_robust_crop_land_deterministic"
                ),
            )
        self.assertEqual(got, expected)
        kwargs = decide_crew.call_args.kwargs
        # The wrapper leaves the historical global Stackelberg arm disabled;
        # the dedicated gate activates it from public land ownership inside
        # the curve, so day-zero V132 behaviour remains byte-for-byte intact.
        self.assertFalse(kwargs["stackelberg"])
        self.assertTrue(kwargs["activated_land_reinvestment"])
        self.assertTrue(kwargs["robust_crop_land_gate"])
        self.assertTrue(kwargs["crop_only_land_arm"])
        self.assertTrue(kwargs["scenario_dominant_composition_exchange"])

    def test_late_land_challenger_is_post_v132_and_explicitly_isolated(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (4, [["BUY_SEED", "STRAWBERRY", 18], ["BUY_LAND"]], [])
        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = capital.decide(
                snap, plan, [], [],
                variant=(
                    "crew_conditioned_positioned_scenario_late_land_challenger_deterministic"
                ),
            )
        self.assertEqual(got, expected)
        kwargs = decide_crew.call_args.kwargs
        self.assertTrue(kwargs["scenario_dominant_composition_exchange"])
        self.assertTrue(kwargs["positioned_capital_manifest"])
        self.assertTrue(kwargs["late_crop_land_challenger"])
        self.assertFalse(kwargs["crop_only_land_arm"])
        self.assertFalse(kwargs["robust_crop_land_gate"])
        self.assertFalse(kwargs["stackelberg"])

    def test_late_rotation_is_post_v149_and_has_one_hour_hire_recourse(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (4, [["BUY_SEED", "WHEAT", 12]], [])
        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = capital.decide(
                snap, plan, [], [],
                variant=(
                    "crew_conditioned_positioned_scenario_late_land_rotation_deterministic"
                ),
            )
        self.assertEqual(got, expected)
        kwargs = decide_crew.call_args.kwargs
        self.assertTrue(kwargs["scenario_dominant_composition_exchange"])
        self.assertTrue(kwargs["late_crop_land_challenger"])
        self.assertTrue(kwargs["late_empty_crop_challenger"])

        # The only intraday recourse delegates existing tasks at hour 1; later
        # hours cannot reopen either capital or another hire solve.
        snap.hour = 1
        with mock.patch.object(
                capital, "_incremental_manifest_hire_choice",
                return_value=2) as tail_hires:
            self.assertEqual(capital.decide(
                snap, plan, [], [],
                variant=(
                    "crew_conditioned_positioned_scenario_late_land_rotation_deterministic"
                ),
            ), (2, [], []))
        tail_hires.assert_called_once()
        snap.hour = 2
        self.assertEqual(capital.decide(
            snap, plan, [], [],
            variant=(
                "crew_conditioned_positioned_scenario_late_land_rotation_deterministic"
            ),
        ), (0, [], []))

    def test_deferred_rotation_executes_only_its_bound_hour_one_certificate(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=100, service_cash_floor=200)
        expected = (4, [["BUY_SEED", "WHEAT", 12]], [])
        variant = (
            "crew_conditioned_positioned_scenario_late_land_"
            "deferred_rotation_deterministic"
        )
        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = capital.decide(snap, plan, [], [], variant=variant)
        self.assertEqual(got, expected)
        kwargs = decide_crew.call_args.kwargs
        self.assertTrue(kwargs["scenario_dominant_composition_exchange"])
        self.assertTrue(kwargs["late_crop_land_challenger"])
        self.assertTrue(kwargs["late_empty_crop_challenger"])
        self.assertTrue(kwargs["deferred_crop_hires"])

        snap.hour = 1
        with mock.patch.object(
                capital, "_certified_deferred_hire_choice",
                return_value=2) as certified:
            self.assertEqual(
                capital.decide(snap, plan, [], [], variant=variant),
                (2, [], []),
            )
        certified.assert_called_once()
        snap.hour = 2
        self.assertEqual(
            capital.decide(snap, plan, [], [], variant=variant),
            (0, [], []),
        )

    def test_deferred_hire_certificate_is_single_use_and_cash_safe(self):
        snap = _snap(money=251, empty=20)
        snap.hour = 1
        snap.seat = 0
        snap.me.hires_today = 0
        plan = SimpleNamespace(cash_floor=50, service_cash_floor=250)
        capital._DEFERRED_HIRES[snap.seat] = (snap.day, 3)
        # Only one cash unit is spendable above the stricter service floor.
        # The first Fibonacci hire costs 1; the two-hire prefix costs 2.
        self.assertEqual(
            capital._certified_deferred_hire_choice(snap, plan, []), 1,
        )
        self.assertEqual(
            capital._certified_deferred_hire_choice(snap, plan, []), 0,
        )

    def test_deferred_capital_variant_adds_only_the_named_option_gate(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (4, [["BUY_SEED", "WHEAT", 12]], [])
        variant = (
            "crew_conditioned_positioned_scenario_late_land_"
            "deferred_capital_deterministic"
        )
        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = capital.decide(snap, plan, [], [], variant=variant)
        self.assertEqual(got, expected)
        kwargs = decide_crew.call_args.kwargs
        self.assertTrue(kwargs["late_empty_crop_challenger"])
        self.assertTrue(kwargs["deferred_crop_hires"])
        self.assertTrue(kwargs["deferred_capital_option"])

    def test_commitment_free_capital_variant_suppresses_fantasy_rotation(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (4, [["BUY_SEED", "WHEAT", 12]], [])
        variant = (
            "crew_conditioned_positioned_scenario_late_land_"
            "commitment_free_capital_deterministic"
        )
        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = capital.decide(snap, plan, [], [], variant=variant)
        self.assertEqual(got, expected)
        kwargs = decide_crew.call_args.kwargs
        self.assertTrue(kwargs["late_empty_crop_challenger"])
        self.assertTrue(kwargs["deferred_crop_hires"])
        self.assertTrue(kwargs["deferred_capital_option"])
        self.assertTrue(kwargs["suppress_uncommitted_rotation"])

    def test_full_deferred_capital_variant_adds_paid_durable_endpoint(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (4, [["BUY_SEED", "WHEAT", 12]], [])
        variant = (
            "crew_conditioned_positioned_scenario_late_land_"
            "commitment_free_full_capital_deterministic"
        )
        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = capital.decide(snap, plan, [], [], variant=variant)
        self.assertEqual(got, expected)
        kwargs = decide_crew.call_args.kwargs
        self.assertTrue(kwargs["late_empty_crop_challenger"])
        self.assertTrue(kwargs["deferred_crop_hires"])
        self.assertTrue(kwargs["deferred_capital_option"])
        self.assertTrue(kwargs["deferred_capital_full_continuation"])
        self.assertTrue(kwargs["suppress_uncommitted_rotation"])

    def test_commitment_closed_variant_values_empty_wait_branch(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (4, [["BUY_SEED", "WHEAT", 12]], [])
        variant = (
            "crew_conditioned_positioned_scenario_late_land_"
            "commitment_closed_capital_deterministic"
        )
        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = capital.decide(snap, plan, [], [], variant=variant)
        self.assertEqual(got, expected)
        kwargs = decide_crew.call_args.kwargs
        self.assertTrue(kwargs["deferred_capital_option"])
        self.assertTrue(kwargs["deferred_capital_full_continuation"])
        self.assertTrue(kwargs["close_empty_deferred_baseline"])
        self.assertTrue(kwargs["suppress_uncommitted_rotation"])

    def test_closed_service_variant_uses_finite_productive_horizon(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (4, [["BUY_SEED", "WHEAT", 12]], [])
        variant = (
            "crew_conditioned_positioned_scenario_late_land_"
            "commitment_closed_service_capital_deterministic"
        )
        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = capital.decide(snap, plan, [], [], variant=variant)
        self.assertEqual(got, expected)
        kwargs = decide_crew.call_args.kwargs
        self.assertTrue(kwargs["deferred_capital_option"])
        self.assertFalse(kwargs["deferred_capital_full_continuation"])
        self.assertTrue(kwargs["close_empty_deferred_baseline"])
        self.assertTrue(kwargs["deferred_standing_service_horizon"])
        self.assertTrue(kwargs["bounded_first_output_only"])
        self.assertTrue(kwargs["suppress_uncommitted_rotation"])

    def test_bounded_execution_variant_adds_only_physical_commitment(self):
        snap = _snap(money=3000, empty=20)
        snap.seat = 0
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (4, [["BUY_SEED", "WHEAT", 12]], [])
        variant = capital._BOUNDED_COMMITMENT_VARIANT
        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = capital.decide(snap, plan, [], [], variant=variant)
        self.assertEqual(got, expected)
        kwargs = decide_crew.call_args.kwargs
        self.assertTrue(kwargs["deferred_capital_option"])
        self.assertFalse(kwargs["deferred_capital_full_continuation"])
        self.assertTrue(kwargs["close_empty_deferred_baseline"])
        self.assertTrue(kwargs["deferred_standing_service_horizon"])
        self.assertTrue(kwargs["bounded_first_output_only"])
        self.assertTrue(kwargs["suppress_uncommitted_rotation"])
        self.assertTrue(kwargs["execute_bounded_commitment"])

    def test_bounded_commitment_emits_exact_live_asset_and_hire_prefix(self):
        snap = _snap(day=13, money=3000, empty=20)
        snap.seat = 0
        snap.hour = 0
        snap.step = 13 * econ.TURNS_PER_DAY
        snap.me.hires_today = 0
        position = tuple(snap.me.empty[0])
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        capital._BOUNDED_COMMITMENTS[0] = {
            "created_day": 12,
            "end_day": 14,
            "asset_day": 13,
            "asset_order": ("BUY_SEED", "WHEAT", 1),
            "asset_positions_by_item": {"WHEAT": (position,)},
            "routes_by_day": {},
            "hires_by_day": {13: (3, 0), 14: (1, 0)},
            "requested_by_day": {},
            "executed_by_day": {},
        }
        try:
            got = capital._bounded_commitment_choice(snap, plan, [])
            self.assertEqual(got, (3, [["BUY_SEED", "WHEAT", 1]], []))
            self.assertEqual(
                capital._BOUNDED_COMMITMENTS[0]["requested_by_day"][(13, 0)],
                3,
            )
        finally:
            capital._clear_bounded_commitment(0)

    def test_infeasible_capital_fails_closed_to_explicit_idle(self):
        live_package = __import__("whitebox", fromlist=[
            "capital", "stackelberg",
        ])
        live_capital = live_package.capital
        live_stackelberg = live_package.stackelberg
        snap = _snap(day=13, money=10000, empty=20)
        positions = [tuple(snap.me.empty[0]), tuple(snap.me.empty[1])]
        row = {
            "assets": [["BUY_ANIMAL", "COW", 2]],
            "positions_by_item": {"COW": tuple(positions)},
            "selected_counts": {"COW": 2},
            "fixed": [],
            "service_reserve": 0.0,
            "hire_cost": 0.0,
            "selected_ordinary_tasks": (),
            "score": 9999.0,
        }

        def reject(_snap, counts, _slots, **_kwargs):
            cert = cashflow.Certificate(counts)
            return cert.reject("market_order_slots", _snap.me.money)

        with mock.patch.object(
                live_stackelberg, "certify_unified", side_effect=reject):
            got = live_capital._robust_composition_exchange(
                snap, row, stackelberg_context={"responses": ()},
                close_infeasible_capital=True,
            )
        self.assertEqual(got["assets"], [])
        self.assertEqual(got["selected_counts"], {})
        self.assertTrue(got["capital_feasibility_closed"])
        self.assertEqual(
            got["capital_infeasible_reason"], "market_order_slots",
        )

    def test_feasibility_closed_variant_is_v149_plus_one_hard_gate(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (4, [["BUY_SEED", "MELON", 8]], [])
        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = capital.decide(
                snap, plan, [], [],
                variant=capital._FEASIBILITY_CLOSED_VARIANT,
            )
        self.assertEqual(got, expected)
        kwargs = decide_crew.call_args.kwargs
        self.assertTrue(kwargs["scenario_dominant_composition_exchange"])
        self.assertTrue(kwargs["positioned_capital_manifest"])
        self.assertTrue(kwargs["late_crop_land_challenger"])
        self.assertFalse(kwargs["late_empty_crop_challenger"])
        self.assertTrue(kwargs["close_infeasible_capital"])

    def test_saturated_gate_closes_capacity_but_not_cash_failure(self):
        live_package = __import__("whitebox", fromlist=["capital", "cashflow"])
        live_capital = live_package.capital
        live_cashflow = live_package.cashflow
        snap = _snap(day=13, money=10000, empty=20)
        position = tuple(snap.me.empty[0])
        row = {
            "assets": [["BUY_ANIMAL", "COW", 1]],
            "positions_by_item": {"COW": (position,)},
            "selected_counts": {"COW": 1},
            "fixed": [], "service_reserve": 0.0, "hire_cost": 0.0,
            "selected_ordinary_tasks": (), "score": 100.0,
        }

        def rejected(reason):
            cert = cashflow.Certificate({})
            return cert.reject(reason, snap.me.money)

        feasible = cashflow.Certificate({})
        feasible.cash_path = [snap.me.money]

        with mock.patch.object(
                live_cashflow, "certify_shared",
                side_effect=[feasible, rejected("market_order_slots")]):
            closed = live_capital._saturated_standing_book_gate(snap, row)
        self.assertEqual(closed["assets"], [])
        self.assertTrue(closed["standing_book_gate"])

        with mock.patch.object(
                live_cashflow, "certify_shared",
                side_effect=[feasible, rejected("bridge_cash")]):
            untouched = live_capital._saturated_standing_book_gate(snap, row)
        self.assertIs(untouched, row)

    def test_saturated_book_variant_is_v149_plus_narrow_gate(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (4, [["BUY_SEED", "MELON", 8]], [])
        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = capital.decide(
                snap, plan, [], [],
                variant=capital._SATURATED_BOOK_VARIANT,
            )
        self.assertEqual(got, expected)
        kwargs = decide_crew.call_args.kwargs
        self.assertTrue(kwargs["scenario_dominant_composition_exchange"])
        self.assertTrue(kwargs["positioned_capital_manifest"])
        self.assertTrue(kwargs["late_crop_land_challenger"])
        self.assertTrue(kwargs["saturated_standing_book_gate"])
        self.assertFalse(kwargs["close_infeasible_capital"])

    def test_exact_capacity_frontier_selects_best_certified_partial_book(self):
        live_package = __import__("whitebox", fromlist=[
            "capital", "cashflow", "stackelberg",
        ])
        live_capital = live_package.capital
        live_cashflow = live_package.cashflow
        live_stackelberg = live_package.stackelberg
        snap = _snap(day=13, money=10000, empty=20)
        cow_positions = tuple(tuple(pos) for pos in snap.me.empty[:2])
        sheep_position = tuple(snap.me.empty[2])
        row = {
            "assets": [
                ["BUY_ANIMAL", "COW", 2],
                ["BUY_ANIMAL", "SHEEP", 1],
            ],
            "positions_by_item": {
                "COW": cow_positions,
                "SHEEP": (sheep_position,),
            },
            "selected_counts": {"COW": 2, "SHEEP": 1},
            "fixed": [], "service_reserve": 0.0, "hire_cost": 0.0,
            "selected_ordinary_tasks": (), "score": 9999.0,
        }

        feasible = cashflow.Certificate({})
        rejected = cashflow.Certificate({}).reject(
            "market_order_slots", snap.me.money,
        )

        def certify(_snap, counts, _slots, **_kwargs):
            quantities = (int(counts.get("COW", 0)),
                          int(counts.get("SHEEP", 0)))
            value = 100.0 if quantities == (1, 1) else 10.0
            return SimpleNamespace(
                feasible=True, paired_value=value,
                final_cash=snap.me.money + value,
                upfront_spend=sum(quantities),
            )

        shared_calls = 0

        def shared(*_args, **_kwargs):
            nonlocal shared_calls
            shared_calls += 1
            return rejected if shared_calls == 2 else feasible

        with mock.patch.object(
                live_cashflow, "certify_shared", side_effect=shared), \
                mock.patch.object(
                    live_stackelberg, "make_context", return_value={}), \
                mock.patch.object(
                    live_stackelberg, "certify_unified", side_effect=certify):
            chosen = live_capital._saturated_standing_book_gate(
                snap, row, exact_two_kind_frontier=True,
            )

        self.assertEqual(chosen["selected_counts"], {"COW": 1, "SHEEP": 1})
        self.assertEqual(chosen["assets"], [
            ["BUY_ANIMAL", "COW", 1],
            ["BUY_ANIMAL", "SHEEP", 1],
        ])
        self.assertEqual(chosen["standing_book_frontier_evaluations"], 5)
        self.assertEqual(chosen["standing_book_frontier_value"], 100.0)

    def test_precertified_gate_is_identity_without_failed_v149_certificate(self):
        snap = _snap(day=13, money=10000, empty=20)
        position = tuple(snap.me.empty[0])
        row = {
            "assets": [["BUY_ANIMAL", "COW", 1]],
            "positions_by_item": {"COW": (position,)},
            "selected_counts": {"COW": 1},
        }
        with mock.patch.object(cashflow, "certify_shared") as certify:
            got = capital._saturated_standing_book_gate(
                snap, row, exact_two_kind_frontier=True,
                precertified_infeasibility_only=True,
            )
        self.assertIs(got, row)
        certify.assert_not_called()

    def test_exact_capacity_frontier_variant_is_v149_plus_exact_gate(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (4, [["BUY_SEED", "MELON", 8]], [])
        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = capital.decide(
                snap, plan, [], [],
                variant=capital._EXACT_CAPACITY_FRONTIER_VARIANT,
            )
        self.assertEqual(got, expected)
        kwargs = decide_crew.call_args.kwargs
        self.assertTrue(kwargs["scenario_dominant_composition_exchange"])
        self.assertTrue(kwargs["positioned_capital_manifest"])
        self.assertTrue(kwargs["late_crop_land_challenger"])
        self.assertTrue(kwargs["saturated_standing_book_gate"])
        self.assertTrue(kwargs["exact_capacity_frontier"])
        self.assertFalse(kwargs["close_infeasible_capital"])

    def test_precertified_frontier_dispatch_differs_from_v149_only_by_gate(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        variants = (
            "crew_conditioned_positioned_scenario_late_land_challenger_deterministic",
            capital._PRECERTIFIED_CAPACITY_FRONTIER_VARIANT,
        )
        dispatched = []
        for variant in variants:
            with mock.patch.object(
                    capital, "_decide_crew_conditioned",
                    return_value=(0, [], [])) as decide_crew:
                capital.decide(snap, plan, [], [], variant=variant)
            dispatched.append(dict(decide_crew.call_args.kwargs))
        baseline, candidate = dispatched
        differences = {
            key: (baseline.get(key), candidate.get(key))
            for key in set(baseline) | set(candidate)
            if baseline.get(key) != candidate.get(key)
        }
        self.assertEqual(differences, {
            "saturated_standing_book_gate": (False, True),
            "exact_capacity_frontier": (False, True),
            "precertified_capacity_frontier": (False, True),
        })

    def test_staged_follower_dispatch_differs_from_v149_only_by_response_set(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        variants = (
            "crew_conditioned_positioned_scenario_late_land_challenger_deterministic",
            capital._STAGED_FOLLOWER_REINVESTMENT_VARIANT,
        )
        dispatched = []
        for variant in variants:
            with mock.patch.object(
                    capital, "_decide_crew_conditioned",
                    return_value=(0, [], [])) as decide_crew:
                capital.decide(snap, plan, [], [], variant=variant)
            dispatched.append(dict(decide_crew.call_args.kwargs))
        baseline, candidate = dispatched
        differences = {
            key: (baseline.get(key), candidate.get(key))
            for key in set(baseline) | set(candidate)
            if baseline.get(key) != candidate.get(key)
        }
        self.assertEqual(differences, {
            "staged_opponent_reinvestment": (False, True),
        })

    def test_staged_standing_dispatch_adds_only_own_standing_book(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        variants = (
            capital._STAGED_FOLLOWER_REINVESTMENT_VARIANT,
            capital._STAGED_STANDING_BOOK_VARIANT,
        )
        dispatched = []
        for variant in variants:
            with mock.patch.object(
                    capital, "_decide_crew_conditioned",
                    return_value=(0, [], [])) as decide_crew:
                capital.decide(snap, plan, [], [], variant=variant)
            dispatched.append(dict(decide_crew.call_args.kwargs))
        staged, standing = dispatched
        differences = {
            key: (staged.get(key), standing.get(key))
            for key in set(staged) | set(standing)
            if staged.get(key) != standing.get(key)
        }
        self.assertEqual(differences, {
            "standing_book_composition_exchange": (False, True),
        })

    def test_complete_staged_dispatch_adds_only_candidate_response_quantities(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        variants = (
            capital._STAGED_STANDING_BOOK_VARIANT,
            capital._COMPLETE_STAGED_STANDING_VARIANT,
        )
        dispatched = []
        for variant in variants:
            with mock.patch.object(
                    capital, "_decide_crew_conditioned",
                    return_value=(0, [], [])) as decide_crew:
                capital.decide(snap, plan, [], [], variant=variant)
            dispatched.append(dict(decide_crew.call_args.kwargs))
        standing, complete = dispatched
        differences = {
            key: (standing.get(key), complete.get(key))
            for key in set(standing) | set(complete)
            if standing.get(key) != complete.get(key)
        }
        self.assertEqual(differences, {
            "complete_opponent_response_products": (False, True),
        })

    def test_robust_realisation_dispatch_differs_from_v169_only_by_mode_set(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        variants = (
            capital._STAGED_FOLLOWER_REINVESTMENT_VARIANT,
            capital._ROBUST_STAGED_REALISATION_VARIANT,
        )
        dispatched = []
        for variant in variants:
            with mock.patch.object(
                    capital, "_decide_crew_conditioned",
                    return_value=(0, [], [])) as decide_crew:
                capital.decide(snap, plan, [], [], variant=variant)
            dispatched.append(dict(decide_crew.call_args.kwargs))
        staged, robust = dispatched
        differences = {
            key: (staged.get(key), robust.get(key))
            for key in set(staged) | set(robust)
            if staged.get(key) != robust.get(key)
        }
        self.assertEqual(differences, {
            "robust_own_standing_realisation": (False, True),
        })

    def test_staged_land_dispatch_differs_from_v169_only_by_land_response(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        variants = (
            capital._STAGED_FOLLOWER_REINVESTMENT_VARIANT,
            capital._STAGED_FOLLOWER_LAND_REINVESTMENT_VARIANT,
        )
        dispatched = []
        for variant in variants:
            with mock.patch.object(
                    capital, "_decide_crew_conditioned",
                    return_value=(0, [], [])) as decide_crew:
                capital.decide(snap, plan, [], [], variant=variant)
            dispatched.append(dict(decide_crew.call_args.kwargs))
        staged, land = dispatched
        differences = {
            key: (staged.get(key), land.get(key))
            for key in set(staged) | set(land)
            if staged.get(key) != land.get(key)
        }
        self.assertEqual(differences, {
            "staged_opponent_land_reinvestment": (False, True),
        })

    def test_staged_mixed_dispatch_differs_from_v169_only_by_mixed_response(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        variants = (
            capital._STAGED_FOLLOWER_REINVESTMENT_VARIANT,
            capital._STAGED_FOLLOWER_MIXED_REINVESTMENT_VARIANT,
        )
        dispatched = []
        for variant in variants:
            with mock.patch.object(
                    capital, "_decide_crew_conditioned",
                    return_value=(0, [], [])) as decide_crew:
                capital.decide(snap, plan, [], [], variant=variant)
            dispatched.append(dict(decide_crew.call_args.kwargs))
        staged, mixed = dispatched
        differences = {
            key: (staged.get(key), mixed.get(key))
            for key in set(staged) | set(mixed)
            if staged.get(key) != mixed.get(key)
        }
        self.assertEqual(differences, {
            "staged_opponent_mixed_reinvestment": (False, True),
        })

    def test_paid_rotation_dispatch_differs_from_v149_by_one_challenger(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        variants = (
            "crew_conditioned_positioned_scenario_late_land_challenger_deterministic",
            capital._PAID_ROTATION_SUBSTITUTION_VARIANT,
        )
        dispatched = []
        for variant in variants:
            with mock.patch.object(
                    capital, "_decide_crew_conditioned",
                    return_value=(0, [], [])) as decide_crew:
                capital.decide(snap, plan, [], [], variant=variant)
            dispatched.append(dict(decide_crew.call_args.kwargs))
        baseline, candidate = dispatched
        differences = {
            key: (baseline.get(key), candidate.get(key))
            for key in set(baseline) | set(candidate)
            if baseline.get(key) != candidate.get(key)
        }
        self.assertEqual(differences, {
            "paid_rotation_substitution": (False, True),
        })

    def test_backlogged_rotation_dispatch_is_one_isolated_gate(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        variants = (
            "crew_conditioned_positioned_scenario_late_land_challenger_deterministic",
            capital._BACKLOGGED_ROTATION_SUBSTITUTION_VARIANT,
        )
        dispatched = []
        for variant in variants:
            with mock.patch.object(
                    capital, "_decide_crew_conditioned",
                    return_value=(0, [], [])) as decide_crew:
                capital.decide(snap, plan, [], [], variant=variant)
            dispatched.append(dict(decide_crew.call_args.kwargs))
        baseline, candidate = dispatched
        differences = {
            key: (baseline.get(key), candidate.get(key))
            for key in set(baseline) | set(candidate)
            if baseline.get(key) != candidate.get(key)
        }
        self.assertEqual(differences, {
            "backlogged_rotation_substitution": (False, True),
        })

    def test_weed_backlog_variant_binds_hour_one_hires_to_dig_tasks(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 1
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        with mock.patch.object(
                capital, "_incremental_manifest_hire_choice",
                return_value=2) as choose:
            got = capital.decide(
                snap, plan, [], [],
                variant=capital._WEED_BACKLOG_HIRES_VARIANT,
            )
        self.assertEqual(got, (2, [], []))
        self.assertEqual(
            choose.call_args.kwargs["allowed_kinds"], ("CLEAR_WEED",),
        )

    def test_single_backlog_rotation_dispatch_is_one_isolated_gate(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        variants = (
            "crew_conditioned_positioned_scenario_late_land_challenger_deterministic",
            capital._SINGLE_BACKLOG_ROTATION_VARIANT,
        )
        dispatched = []
        for variant in variants:
            with mock.patch.object(
                    capital, "_decide_crew_conditioned",
                    return_value=(0, [], [])) as decide_crew:
                capital.decide(snap, plan, [], [], variant=variant)
            dispatched.append(dict(decide_crew.call_args.kwargs))
        baseline, candidate = dispatched
        differences = {
            key: (baseline.get(key), candidate.get(key))
            for key in set(baseline) | set(candidate)
            if baseline.get(key) != candidate.get(key)
        }
        self.assertEqual(differences, {
            "single_backlog_rotation_substitution": (False, True),
        })





    def test_late_land_herd_repair_is_explicitly_isolated(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (4, [["BUY_ANIMAL", "SHEEP", 3], ["BUY_LAND"]], [])
        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = capital.decide(
                snap, plan, [], [],
                variant=(
                    "crew_conditioned_positioned_scenario_late_land_herd_repair_deterministic"
                ),
            )
        self.assertEqual(got, expected)
        kwargs = decide_crew.call_args.kwargs
        self.assertTrue(kwargs["scenario_dominant_composition_exchange"])
        self.assertTrue(kwargs["late_crop_land_challenger"])
        self.assertTrue(kwargs["late_land_animal_scale_repair"])
        self.assertFalse(kwargs["standing_book_composition_exchange"])

    def test_late_land_global_repair_is_explicitly_isolated(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (5, [["BUY_SEED", "STRAWBERRY", 12], ["BUY_LAND"]], [])
        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = capital.decide(
                snap, plan, [], [],
                variant=(
                    "crew_conditioned_positioned_scenario_late_land_global_repair_deterministic"
                ),
            )
        self.assertEqual(got, expected)
        kwargs = decide_crew.call_args.kwargs
        self.assertTrue(kwargs["scenario_dominant_composition_exchange"])
        self.assertTrue(kwargs["late_crop_land_challenger"])
        self.assertTrue(kwargs["late_land_global_scale_repair"])
        self.assertFalse(kwargs["late_land_animal_scale_repair"])

    def test_crop_land_covenant_is_explicitly_isolated(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (5, [["BUY_SEED", "STRAWBERRY", 12], ["BUY_LAND"]], [])
        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = capital.decide(
                snap, plan, [], [],
                variant=(
                    "crew_conditioned_positioned_scenario_crop_land_covenant_deterministic"
                ),
            )
        self.assertEqual(got, expected)
        kwargs = decide_crew.call_args.kwargs
        self.assertTrue(kwargs["scenario_dominant_composition_exchange"])
        self.assertTrue(kwargs["late_crop_land_challenger"])
        self.assertTrue(kwargs["crop_land_covenant_repair"])
        self.assertFalse(kwargs["late_land_global_scale_repair"])


if __name__ == "__main__":
    unittest.main()
