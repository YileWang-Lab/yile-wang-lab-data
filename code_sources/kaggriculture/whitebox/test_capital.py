"""Rule tests for optional capital/task/crew columns."""
import unittest
from types import SimpleNamespace
from unittest import mock

from route import router
from route.router import Task, Unit
from whitebox import agent, capital, cashflow, econ, market, value
from whitebox.test_cashflow import _snap


class CapitalTests(unittest.TestCase):
    def test_intraday_turnover_buys_named_seed_without_hiring_or_land(self):
        live_capital = __import__("whitebox", fromlist=["capital"]).capital
        live_cashflow = __import__("whitebox", fromlist=["cashflow"]).cashflow
        snap = _snap(money=100000, empty=5)
        snap.hour = 12
        target = tuple(snap.me.empty[0])
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        proposal = live_cashflow.Certificate({})
        proposal.positions_by_item = {}

        with mock.patch.object(
                live_cashflow, "invent_paired_proposal",
                return_value=([], proposal)) as invent:
            rows = live_capital.crew_conditioned_decision_curve(
                snap, plan, [], [],
                turnover_positions=(target,),
                turnover_items_by_position={target: "MELON"},
            )

        self.assertEqual(len(rows), 1)
        call = invent.call_args
        self.assertEqual(call.kwargs["fixed_orders"], [])
        self.assertEqual(call.kwargs["allowed_items"], ("MELON",))
        self.assertFalse(call.kwargs["allow_land"])
        self.assertEqual(
            set(call.kwargs["blocked_positions"]),
            set(snap.me.empty) - {target},
        )

    def test_crew_conditioned_variant_rebuilds_every_k_and_returns_winning_assets(self):
        live_capital = __import__("whitebox", fromlist=["capital"]).capital
        live_router = live_capital.router
        snap = _snap(money=100000, shed={"MILK": 1}, empty=20)
        snap.hour = 0
        snap.me.hires_today = 2
        plan = SimpleNamespace(cash_floor=999, service_cash_floor=37)
        fixed = [["SELL", "MILK", 1],
                 ["BUY_PRODUCT", "WHEAT", 1]]
        market_orders = fixed + [["BUY_SEED", "MELON", 9]]
        proposal_calls = []
        column_calls = []
        route_calls = []
        model_calls = []
        captured_rows = []

        def invent(_snap, **kwargs):
            arm_fixed = [list(order) for order in kwargs["fixed_orders"]]
            k = sum(order == ["HIRE"] for order in arm_fixed)
            proposal_calls.append((k, arm_fixed, kwargs))
            # Quantity identifies the arm.  The legacy MELON proposal must not
            # leak into any crew-conditioned result.
            return (["BUY_SEED", "WHEAT", k + 1],), SimpleNamespace(
                positions_by_item={}, evaluations=k + 10,
            )

        def make_columns(_snap, proposed, _tasks, **kwargs):
            proposed = [list(order) for order in proposed]
            column_calls.append((proposed, kwargs))
            if not proposed:
                return [], {}
            qty = int(proposed[0][2])
            columns = [
                Task(
                    (idx, 0), [["PLANT", "WHEAT"]], value=0,
                    kind="CAPITAL_CROP",
                    order_key=("BUY_SEED", "WHEAT"),
                )
                for idx in range(qty)
            ]
            return columns, {}

        class FakePositionedObjective:
            def __init__(self, _snap, all_tasks, fixed_orders, **kwargs):
                self.all_tasks = list(all_tasks)
                model_calls.append((list(fixed_orders), kwargs))

            def score(self, chosen):
                # Proposal quantity four is the unique global winner, even
                # after paying the k=3 Fibonacci prefix.
                return 1000.0 if len(chosen) == 4 else 0.0

        def assign(tasks, _units, _stock, **kwargs):
            route_calls.append(kwargs)
            return {0: list(tasks)}, []

        original_curve = live_capital.crew_conditioned_decision_curve

        def capture_curve(*args, **kwargs):
            rows = original_curve(*args, **kwargs)
            captured_rows.extend(rows)
            return rows

        # Arena-isolation tests intentionally reload whitebox package modules;
        # resolve the package's live cashflow binding at execution time because
        # the production function performs the same local import.
        live_cashflow = __import__("whitebox", fromlist=["cashflow"]).cashflow
        with mock.patch.object(
                live_capital, "crew_conditioned_decision_curve",
                side_effect=capture_curve), \
                mock.patch.object(
                live_cashflow, "invent_paired_proposal", side_effect=invent), \
                mock.patch.object(live_capital, "capital_tasks",
                                  side_effect=make_columns), \
                mock.patch.object(live_capital, "PositionedCertificateObjective",
                                  FakePositionedObjective), \
                mock.patch.object(
                    live_router, "joint_assign", side_effect=assign):
            result = live_capital.decide(
                snap, plan, [], market_orders,
                variant="crew_conditioned_phase_aligned_deterministic",
            )

        # Two fixed orders leave exactly eight legal HIRE slots: every k=0..8
        # gets its own portfolio, certificate, route and score.
        self.assertEqual([call[0] for call in proposal_calls], list(range(9)))
        self.assertEqual(len(column_calls), 9)
        self.assertEqual(len(route_calls), 9)
        self.assertEqual(len(model_calls), 9)
        self.assertEqual([row["hires"] for row in captured_rows],
                         list(range(9)))
        for k, arm_fixed, kwargs in proposal_calls:
            self.assertEqual(arm_fixed, fixed + [["HIRE"] for _ in range(k)])
            self.assertEqual(
                kwargs["reserve"],
                37 + econ.hire_block_cost(snap.me.hires_today, k),
            )
            self.assertTrue(kwargs["reserve_inventory"])
            self.assertTrue(kwargs["phase_aligned"])
            self.assertFalse(kwargs["fertilizer_bridge"])
        for k, kwargs in enumerate(route_calls):
            self.assertEqual(kwargs["max_order_keys"],
                             econ.MAX_ORDERS - len(fixed) - k)
            self.assertEqual(
                kwargs["cash_budget"],
                (snap.me.money - 37 - live_capital._fixed_spend(snap, fixed)
                 - econ.hire_block_cost(snap.me.hires_today, k)),
            )
            self.assertIsNone(kwargs["deadline"])
            self.assertTrue(kwargs["memoize_route_cost"])
        for k, row in enumerate(captured_rows):
            self.assertEqual(row["hire_cost"],
                             econ.hire_block_cost(snap.me.hires_today, k))
            self.assertEqual(row["purchase_slots"],
                             econ.MAX_ORDERS - len(fixed) - k)
            self.assertEqual(row["assets"],
                             [["BUY_SEED", "WHEAT", k + 1]])
        for k, (model_fixed, kwargs) in enumerate(model_calls):
            self.assertEqual(model_fixed, fixed)
            self.assertEqual(
                kwargs["reserve"],
                37 + econ.hire_block_cost(snap.me.hires_today, k),
            )
            self.assertTrue(kwargs["phase_aligned"])

        # The selected assets must be reconstructed from k=3's proposal, not
        # from the legacy proposal, the first arm or the final enumerated arm.
        self.assertEqual(result, (
            3, [["BUY_SEED", "WHEAT", 4]], fixed,
        ))

    def test_fertilizer_bridge_variant_is_explicitly_isolated(self):
        live_capital = __import__("whitebox", fromlist=["capital"]).capital
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (2, [["BUY_ANIMAL", "COW", 1]], [])
        with mock.patch.object(
                live_capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = live_capital.decide(
                snap, plan, [], [],
                variant="crew_conditioned_fertilizer_bridge_deterministic",
            )
        self.assertEqual(got, expected)
        self.assertTrue(decide_crew.call_args.kwargs["fertilizer_bridge"])

    def test_visible_fertilizer_reserve_variant_is_explicitly_isolated(self):
        live_capital = __import__("whitebox", fromlist=["capital"]).capital
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (2, [["BUY_ANIMAL", "SHEEP", 1]], [])
        with mock.patch.object(
                live_capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = live_capital.decide(
                snap, plan, [], [],
                variant=(
                    "crew_conditioned_fertilizer_reserved_memoized_deterministic"
                ),
            )
        self.assertEqual(got, expected)
        kwargs = decide_crew.call_args.kwargs
        self.assertTrue(kwargs["fertilizer_bridge"])
        self.assertTrue(kwargs["memoize_proposals"])
        self.assertTrue(kwargs["reserve_visible_fertilizer"])

    def test_exchange_repair_variant_is_explicitly_isolated(self):
        live_capital = __import__("whitebox", fromlist=["capital"]).capital
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (4, [["BUY_SEED", "STRAWBERRY", 8]], [])
        with mock.patch.object(
                live_capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = live_capital.decide(
                snap, plan, [], [],
                variant="crew_conditioned_exchange_memoized_deterministic",
            )
        self.assertEqual(got, expected)
        kwargs = decide_crew.call_args.kwargs
        self.assertFalse(kwargs["fertilizer_bridge"])
        self.assertTrue(kwargs["memoize_proposals"])
        self.assertTrue(kwargs["exchange_repair"])

    def test_adaptive_marginal_variant_is_explicitly_isolated(self):
        live_capital = __import__("whitebox", fromlist=["capital"]).capital
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (3, [["BUY_ANIMAL", "SHEEP", 2]], [])
        with mock.patch.object(
                live_capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = live_capital.decide(
                snap, plan, [], [],
                variant=(
                    "crew_conditioned_adaptive_marginal_memoized_deterministic"
                ),
            )
        self.assertEqual(got, expected)
        kwargs = decide_crew.call_args.kwargs
        self.assertTrue(kwargs["memoize_proposals"])
        self.assertTrue(kwargs["adaptive_marginal"])
        self.assertFalse(kwargs["fertilizer_bridge"])

    def test_intraday_replan_variant_is_explicitly_isolated(self):
        live_capital = __import__("whitebox", fromlist=["capital"]).capital
        snap = _snap(money=3000, empty=20)
        snap.hour = 7
        snap.step = 7
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (1, [["BUY_SEED", "WHEAT", 4]], [])
        with mock.patch.object(
                live_capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = live_capital.decide(
                snap, plan, [], [],
                variant="crew_conditioned_intraday_memoized_deterministic",
            )
        self.assertEqual(got, expected)
        kwargs = decide_crew.call_args.kwargs
        self.assertTrue(kwargs["memoize_proposals"])
        self.assertTrue(kwargs["intraday_replan"])
        self.assertFalse(kwargs["fertilizer_bridge"])

    def test_late_task_hires_reopen_only_fixed_task_fallback(self):
        live_capital = __import__("whitebox", fromlist=["capital"]).capital
        snap = _snap(money=3000, empty=20)
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        snap.hour = 0
        snap.step = 0
        with mock.patch.object(
                live_capital, "_decide_crew_conditioned",
                return_value=(3, [["BUY_SEED", "WHEAT", 4]], [])) as joint:
            self.assertEqual(live_capital.decide(
                snap, plan, [], [],
                variant="crew_conditioned_late_task_hires_deterministic",
            ), (3, [["BUY_SEED", "WHEAT", 4]], []))
        joint.assert_called_once()

        snap.hour = 5
        snap.step = 5
        with mock.patch.object(
                live_capital, "_decide_crew_conditioned") as joint:
            self.assertIsNone(live_capital.decide(
                snap, plan, [], [],
                variant="crew_conditioned_late_task_hires_deterministic",
            ))
        joint.assert_not_called()

    def test_joint_visible_workload_variant_is_explicitly_isolated(self):
        live_capital = __import__("whitebox", fromlist=["capital"]).capital
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (2, [["BUY_ANIMAL", "COW", 1]], [])
        with mock.patch.object(
                live_capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = live_capital.decide(
                snap, plan, [], [],
                variant=(
                    "crew_conditioned_late_hires_joint_workload_deterministic"
                ),
            )
        self.assertEqual(got, expected)
        kwargs = decide_crew.call_args.kwargs
        self.assertTrue(kwargs["memoize_proposals"])
        self.assertTrue(kwargs["joint_visible_workload"])

    def test_positioned_manifest_variant_is_explicitly_isolated(self):
        live_capital = __import__("whitebox", fromlist=["capital"]).capital
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (3, [["BUY_SEED", "WHEAT", 20]], [])
        with mock.patch.object(
                live_capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = live_capital.decide(
                snap, plan, [], [],
                variant=(
                    "crew_conditioned_positioned_manifest_deterministic"
                ),
            )
        self.assertEqual(got, expected)
        kwargs = decide_crew.call_args.kwargs
        self.assertTrue(kwargs["positioned_capital_manifest"])
        self.assertFalse(kwargs["stackelberg"])

    def test_positioned_robust_exchange_variant_is_explicitly_isolated(self):
        live_capital = __import__("whitebox", fromlist=["capital"]).capital
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (3, [["BUY_SEED", "WHEAT", 20]], [])
        with mock.patch.object(
                live_capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = live_capital.decide(
                snap, plan, [], [],
                variant=(
                    "crew_conditioned_positioned_robust_exchange_deterministic"
                ),
            )
        self.assertEqual(got, expected)
        kwargs = decide_crew.call_args.kwargs
        self.assertTrue(kwargs["positioned_capital_manifest"])
        self.assertTrue(kwargs["robust_composition_exchange"])
        self.assertFalse(kwargs["stackelberg"])

    def test_candidate_bound_land_hires_variant_is_explicitly_isolated(self):
        live_capital = __import__("whitebox", fromlist=["capital"]).capital
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        snap.step = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (3, [["BUY_LAND"], ["BUY_SEED", "WHEAT", 20]], [])
        variant = (
            "crew_conditioned_positioned_scenario_late_land_"
            "candidate_bound_deferred_hires_deterministic"
        )
        with mock.patch.object(
                live_capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = live_capital.decide(
                snap, plan, [], [], variant=variant,
            )
        self.assertEqual(got, expected)
        kwargs = decide_crew.call_args.kwargs
        self.assertTrue(kwargs["memoize_proposals"])
        self.assertTrue(kwargs["positioned_capital_manifest"])
        self.assertTrue(kwargs["scenario_dominant_composition_exchange"])
        self.assertTrue(kwargs["late_crop_land_challenger"])
        self.assertTrue(kwargs["deferred_land_hires"])
        self.assertFalse(kwargs["deferred_crop_hires"])

    def test_candidate_bound_land_hires_execute_only_saved_hour_one_count(self):
        live_capital = __import__("whitebox", fromlist=["capital"]).capital
        snap = _snap(money=100000, empty=20)
        snap.seat = 0
        snap.day = 7
        snap.hour = 1
        snap.step = 1
        snap.me.hires_today = 0
        snap.me.hands = []
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        variant = (
            "crew_conditioned_positioned_scenario_late_land_"
            "candidate_bound_deferred_hires_deterministic"
        )
        live_capital._DEFERRED_HIRES[snap.seat] = (snap.day, 4)
        got = live_capital.decide(
            snap, plan, [], [["SELL", "MILK", 1]], variant=variant,
        )
        self.assertEqual(got, (4, [], [["SELL", "MILK", 1]]))
        # The certificate is consumed exactly once; later calls cannot repeat
        # the Fibonacci prefix or manufacture a new capital decision.
        self.assertEqual(live_capital.decide(
            snap, plan, [], [["SELL", "MILK", 1]], variant=variant,
        ), (0, [], [["SELL", "MILK", 1]]))

    def test_first_output_land_covenant_is_action_bound_and_expires(self):
        live_capital = __import__("whitebox", fromlist=["capital"]).capital
        snap = _snap(day=11, money=100000, empty=20)
        snap.seat = 0
        snap.me.unlocked = ["NW", "NE"]
        live_capital._store_land_use_covenant(
            snap, {"late_land_crop": "STRAWBERRY"},
        )
        try:
            record = live_capital._LAND_USE_COVENANTS[snap.seat]
            self.assertEqual(record["quadrant"], "SW")
            self.assertEqual(record["release_day"], 21)

            snap.day = 12
            snap.me.unlocked.append("SW")
            snap.me.tiles[5][0] = None
            snap.me.tiles[5][1] = None
            columns, _animals = live_capital.capital_tasks(
                snap,
                [["BUY_ANIMAL", "COW", 1],
                 ["BUY_SEED", "WHEAT", 1]],
                [],
                positions_by_item={
                    "COW": [(0, 5)], "WHEAT": [(1, 5)],
                },
            )
            self.assertFalse(any(
                task.order_key == ("BUY_ANIMAL", "COW")
                for task in columns
            ))
            self.assertTrue(any(
                task.order_key == ("BUY_SEED", "WHEAT")
                for task in columns
            ))

            # Moving the animal to old land is not an escape hatch: the new
            # quadrant could otherwise absorb crops and indirectly free this
            # old position, reproducing the same unpriced herd expansion.
            snap.me.tiles[0][0] = None
            columns, _animals = live_capital.capital_tasks(
                snap, [["BUY_ANIMAL", "COW", 1]], [],
                positions_by_item={"COW": [(0, 0)]},
            )
            self.assertFalse(columns)

            snap.day = record["release_day"]
            columns, _animals = live_capital.capital_tasks(
                snap, [["BUY_ANIMAL", "COW", 1]], [],
                positions_by_item={"COW": [(0, 5)]},
            )
            self.assertTrue(any(
                task.order_key == ("BUY_ANIMAL", "COW")
                for task in columns
            ))
            self.assertNotIn(snap.seat, live_capital._LAND_USE_COVENANTS)
        finally:
            live_capital._clear_land_use_covenant(snap.seat)

    def test_first_output_land_covenant_variant_is_explicitly_isolated(self):
        live_capital = __import__("whitebox", fromlist=["capital"]).capital
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        snap.step = 0
        snap.seat = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (2, [["BUY_LAND"], ["BUY_SEED", "MELON", 5]], [])
        variant = (
            "crew_conditioned_positioned_scenario_late_land_"
            "candidate_bound_first_output_covenant_deterministic"
        )
        with mock.patch.object(
                live_capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = live_capital.decide(
                snap, plan, [], [], variant=variant,
            )
        self.assertEqual(got, expected)
        kwargs = decide_crew.call_args.kwargs
        self.assertTrue(kwargs["deferred_land_hires"])
        self.assertTrue(kwargs["land_recovery_covenant"])
        self.assertTrue(kwargs["late_crop_land_challenger"])
        self.assertTrue(kwargs["scenario_dominant_composition_exchange"])

    def test_productive_shed_tile_is_an_opt_in_shared_action_space(self):
        live_capital = __import__("whitebox", fromlist=["capital"]).capital
        live_cashflow = __import__("whitebox", fromlist=["cashflow"]).cashflow
        live_tasks = __import__("whitebox", fromlist=["tasks"]).tasks
        snap = _snap(money=100000, empty=20)
        snap.me.tiles[4][4] = None
        if (4, 4) not in snap.me.empty:
            snap.me.empty.append((4, 4))

        snap.allow_productive_shed_tiles = False
        self.assertNotIn((4, 4), live_cashflow._available_slots(snap))
        columns, _animals = live_capital.capital_tasks(
            snap, [["BUY_SEED", "WHEAT", 1]], [],
            positions_by_item={"WHEAT": [(4, 4)]},
        )
        self.assertFalse(columns)
        self.assertFalse(live_tasks._position_accepts_item(
            snap, (4, 4), "WHEAT",
        ))

        snap.allow_productive_shed_tiles = True
        self.assertIn((4, 4), live_cashflow._available_slots(snap))
        columns, _animals = live_capital.capital_tasks(
            snap, [["BUY_SEED", "WHEAT", 1]], [],
            positions_by_item={"WHEAT": [(4, 4)]},
        )
        self.assertEqual(len(columns), 1)
        self.assertEqual(columns[0].pos, (4, 4))
        self.assertTrue(live_tasks._position_accepts_item(
            snap, (4, 4), "WHEAT",
        ))

    def test_shed_cluster_admission_gives_new_animals_first_access(self):
        """Central cells are offered to animals before fungible crops."""
        live_cashflow = __import__("whitebox", fromlist=["cashflow"]).cashflow
        snap = _snap(money=100000, empty=20)
        snap.me.tiles[4][4] = None
        if (4, 4) not in snap.me.empty:
            snap.me.empty.append((4, 4))
        snap.allow_productive_shed_tiles = True

        slots = live_cashflow._available_slots(snap)
        assigned = live_cashflow._assign_positions(
            {"COW": 1, "WHEAT": 1}, slots,
        )
        self.assertEqual(assigned["COW"], [(4, 4)])
        self.assertNotEqual(assigned["WHEAT"], [(4, 4)])
        self.assertEqual(
            min(capital.paths.dist_to_shed(pos) for pos in assigned["COW"]),
            0,
        )

    def test_v218_wrapper_keeps_central_cells_certificate_gated(self):
        from whitebox.versions import v218_certified_shed_cluster as v218

        with mock.patch.object(
                v218._agent, "variant_agent", return_value={}) as run:
            v218.whitebox_v218_certified_shed_cluster({})
        kwargs = run.call_args.kwargs
        self.assertTrue(kwargs["productive_shed_relocation"])
        self.assertTrue(kwargs["service_cluster_layout"])
        self.assertEqual(
            kwargs["execution_variant"],
            "paid_fertilizer_productive_shed_relocation_manifest",
        )
        # The broad action-space switch remains closed; only the challenger
        # can admit a shed-access cell after its full certificate.
        self.assertFalse(kwargs.get("productive_shed_tiles", False))

    def test_engine_allows_crop_and_animal_on_shed_access_tile(self):
        from planner.simulate import Simulator

        idle = {"farmer": ["PASS"], "hands": [], "market": []}
        sim = Simulator.new_episode(seed=23)
        sim.privates[0]["seeds"]["WHEAT"] = 1
        sim.step_actions(
            {"farmer": ["PLANT", "WHEAT"], "hands": [], "market": []},
            idle,
        )
        self.assertEqual(sim.farms[0]["tiles"][4][4]["crop"], "WHEAT")
        sim.step_actions(
            {"farmer": ["WATER"], "hands": [], "market": []}, idle,
        )
        self.assertTrue(sim.farms[0]["tiles"][4][4]["watered_today"])

        sim = Simulator.new_episode(seed=29)
        sim.privates[0]["inventories"][0]["COW"] = 1
        sim.step_actions(
            {"farmer": ["BUILD_PASTURE"], "hands": [], "market": []},
            idle,
        )
        sim.step_actions(
            {"farmer": ["PLACE", "COW"], "hands": [], "market": []},
            idle,
        )
        self.assertEqual(sim.farms[0]["tiles"][4][4]["animal"], "COW")

    def test_crew_conditioned_variant_is_hour_zero_only_and_never_falls_back(self):
        live_capital = __import__("whitebox", fromlist=["capital"]).capital
        snap = _snap(money=100000, empty=20)
        snap.hour = 1
        snap.step = 1
        snap.day = 0
        snap.seat = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        live_cashflow = __import__("whitebox", fromlist=["cashflow"]).cashflow
        with mock.patch.object(
                live_cashflow, "invent_paired_proposal") as invent:
            self.assertEqual(
                live_capital.crew_conditioned_decision_curve(
                    snap, plan, [], [["BUY_SEED", "WHEAT", 5]],
                ),
                [],
            )
            # A non-None empty choice deliberately blocks the legacy
            # fixed-task hiring fallback after the day-opening joint program.
            self.assertEqual(live_capital.decide(
                snap, plan, [], [["BUY_SEED", "WHEAT", 5]],
                variant="crew_conditioned_phase_aligned_deterministic",
            ), (0, [], []))
        invent.assert_not_called()

        live_agent = __import__("whitebox", fromlist=["agent"]).agent
        tracker = SimpleNamespace(
            observe=lambda *_args: None,
            record_my_orders=lambda *_args: None,
        )
        with mock.patch.object(live_agent.state, "extract", return_value=snap), \
                mock.patch.object(live_agent.state, "project_unit_phase",
                                  return_value=snap), \
                mock.patch.object(live_agent, "_tracker",
                                  return_value=tracker), \
                mock.patch.object(live_agent._horizon, "sense"), \
                mock.patch.object(live_agent.strategy, "decide",
                                  return_value=plan), \
                mock.patch.object(live_agent.tasks, "enumerate_tasks",
                                  return_value=[]), \
                mock.patch.object(live_agent.tasks, "assign",
                                  return_value=({}, [])), \
                mock.patch.object(live_agent.tasks, "next_op",
                                  return_value=["PASS"]), \
                mock.patch.object(live_agent.market, "orders",
                                  return_value=[["BUY_SEED", "WHEAT", 5]]), \
                mock.patch.object(live_agent.hiring, "decide",
                                  return_value=9) as fallback:
            action = live_agent.act(
                {}, capital_master=True,
                capital_variant=(
                    "crew_conditioned_phase_aligned_deterministic"
                ),
            )
        fallback.assert_not_called()
        self.assertEqual(action["market"], [])

    def test_capacity_market_reuses_capital_phase_projection(self):
        """Market and capital layers must consume one shared unit snapshot."""
        live_agent = __import__("whitebox", fromlist=["agent"]).agent
        snap = _snap(money=1000, empty=3)
        snap.step = 0
        snap.day = 0
        snap.hour = 0
        snap.seat = 0
        plan = SimpleNamespace(
            cash_floor=0.0, service_cash_floor=0.0,
            fertilizer_target=0, paid_weed_turnover=False,
        )
        tracker = SimpleNamespace(
            observe=lambda *_args: None,
            record_my_orders=lambda *_args: None,
        )
        phase = mock.Mock(return_value=snap)
        with mock.patch.object(live_agent.state, "extract", return_value=snap), \
                mock.patch.object(live_agent.state, "project_unit_phase",
                                  phase), \
                mock.patch.object(live_agent, "_tracker",
                                  return_value=tracker), \
                mock.patch.object(live_agent._horizon, "sense"), \
                mock.patch.object(live_agent.strategy, "decide",
                                  return_value=plan), \
                mock.patch.object(live_agent.tasks, "enumerate_tasks",
                                  return_value=[]), \
                mock.patch.object(live_agent.tasks, "assign",
                                  return_value=({}, [])), \
                mock.patch.object(live_agent.tasks, "next_op",
                                  return_value=["PASS"]), \
                mock.patch.object(live_agent.market, "orders",
                                  return_value=[]), \
                mock.patch.object(live_agent.market,
                                  "capacity_reserve_orders",
                                  return_value=[]) as capacity, \
                mock.patch.object(live_agent.capital, "decide",
                                  return_value=(0, [], [])):
            action = live_agent.act(
                {}, capital_master=True,
                capital_variant="crew_conditioned_phase_aligned_deterministic",
                market_variant="capacity_reserve",
            )
        self.assertEqual(action["market"], [])
        phase.assert_called_once_with(snap, [["PASS"]])
        capacity.assert_called_once()
        self.assertIs(capacity.call_args.args[4], snap)

    def test_complete_shared_slot_columns_cover_every_item_and_tile(self):
        snap = _snap(money=100000, empty=3)
        proposed = [
            ["BUY_ANIMAL", "COW", 1],
            ["BUY_SEED", "MELON", 1],
        ]
        columns, _animals = capital.capital_tasks(
            snap, proposed, [], complete_alternatives=True,
        )
        by_order = {}
        for task in columns:
            by_order.setdefault(task.order_key, set()).add(tuple(task.pos))
            self.assertEqual(
                task.exclusive_key, ("CAPITAL_TILE", tuple(task.pos)),
            )
        expected = set(sorted(
            snap.me.empty,
            key=lambda pos: (capital.paths.dist_to_shed(pos), pos),
        )[:2])
        self.assertEqual(by_order[("BUY_ANIMAL", "COW")], expected)
        self.assertEqual(by_order[("BUY_SEED", "MELON")], expected)

    def test_complete_shared_slot_bundle_master_is_clock_free_and_limited(self):
        snap = _snap(money=100000, empty=3)
        snap.hour = 5
        plan = SimpleNamespace(cash_floor=0)
        seen = []
        original = router.joint_assign

        def capture(tasks, *args, **kwargs):
            capital_tasks = [task for task in tasks
                             if task.kind.startswith("CAPITAL_")]
            positions = {}
            for task in capital_tasks:
                positions.setdefault(task.order_key, set()).add(task.pos)
            seen.append((
                kwargs.get("deadline"), kwargs.get("memoize_route_cost"),
                kwargs.get("selection_limits"), positions,
                type(kwargs.get("bundle_model")).__name__,
            ))
            return original(tasks, *args, **kwargs)

        proposed = [["BUY_ANIMAL", "COW", 1],
                    ["BUY_SEED", "MELON", 1]]
        with mock.patch.object(router, "joint_assign", capture):
            capital.decide(
                snap, plan, [], proposed, unit_actions=[["PASS"]],
                deadline=0.0,
                variant=(
                    "ordinary_complete_tiles_bundle_master_"
                    "memoized_deterministic"
                ),
            )
        self.assertTrue(seen)
        for deadline, memoized, limits, positions, model in seen:
            self.assertIsNone(deadline)
            self.assertTrue(memoized)
            self.assertEqual(limits[("BUY_ANIMAL", "COW")], 1)
            self.assertEqual(limits[("BUY_SEED", "MELON")], 1)
            self.assertEqual(
                positions[("BUY_ANIMAL", "COW")],
                positions[("BUY_SEED", "MELON")],
            )
            self.assertEqual(model, "TaskBundleObjective")

    def test_temporal_recertification_routes_with_v89_then_scores_selected(self):
        snap = _snap(money=100000, empty=8)
        snap.hour = 5
        plan = SimpleNamespace(cash_floor=0)
        route_models = []
        scored = []
        original_route = router.joint_assign
        original_temporal = value.TemporalPairedTaskBundleObjective

        def capture_route(*args, **kwargs):
            route_models.append(type(kwargs.get("bundle_model")).__name__)
            return original_route(*args, **kwargs)

        class CaptureTemporal(original_temporal):
            def score(self, selected):
                scored.append(tuple(id(task) for task in selected))
                return super().score(selected)

        with mock.patch.object(router, "joint_assign", capture_route), \
                mock.patch.object(
                    value, "TemporalPairedTaskBundleObjective", CaptureTemporal,
                ):
            capital.decide(
                snap, plan, [], [["BUY_SEED", "WHEAT", 2]],
                unit_actions=[["PASS"]], deadline=0.0,
                variant="temporal_recertified_bundle_memoized_deterministic",
            )
        self.assertTrue(route_models)
        self.assertTrue(all(name == "TaskBundleObjective"
                            for name in route_models))
        self.assertTrue(scored)
        self.assertTrue(all(len(selected) <= 2 for selected in scored))

    def test_temporal_paired_capital_master_is_clock_free_and_memoized(self):
        snap = _snap(money=100000, empty=8)
        snap.hour = 5
        plan = SimpleNamespace(cash_floor=0)
        seen = []
        original = router.joint_assign

        def capture(*args, **kwargs):
            model = kwargs.get("bundle_model")
            seen.append((kwargs.get("deadline"),
                         kwargs.get("memoize_route_cost"),
                         type(model).__name__))
            return original(*args, **kwargs)

        with mock.patch.object(router, "joint_assign", capture):
            capital.decide(
                snap, plan, [], [["BUY_SEED", "WHEAT", 2]],
                unit_actions=[["PASS"]], deadline=0.0,
                variant="temporal_paired_bundle_master_memoized_deterministic",
            )
        self.assertTrue(seen)
        self.assertTrue(all(
            deadline is None and memoized
            and model == "TemporalPairedTaskBundleObjective"
            for deadline, memoized, model in seen
        ))

    def test_paired_phase_capital_master_is_clock_free_and_memoized(self):
        snap = _snap(money=100000, empty=8)
        snap.hour = 5
        plan = SimpleNamespace(cash_floor=0)
        seen = []
        original = router.joint_assign

        def capture(*args, **kwargs):
            model = kwargs.get("bundle_model")
            seen.append((kwargs.get("deadline"),
                         kwargs.get("memoize_route_cost"),
                         getattr(model, "paired_phase", False)))
            return original(*args, **kwargs)

        with mock.patch.object(router, "joint_assign", capture):
            capital.decide(
                snap, plan, [], [["BUY_SEED", "WHEAT", 2]],
                unit_actions=[["PASS"]], deadline=0.0,
                variant="paired_phase_bundle_master_memoized_deterministic",
            )
        self.assertTrue(seen)
        self.assertTrue(all(deadline is None and memoized and paired
                            for deadline, memoized, paired in seen))

    @staticmethod
    def _deadline_snap(day, hour, **kwargs):
        snap = _snap(day=day, **kwargs)
        snap.hour = hour
        snap.step = day * econ.TURNS_PER_DAY + hour
        snap.inventories = [{}]
        return snap

    @staticmethod
    def _deadline_melon(pos=(3, 3), value_amount=9999):
        return Task(
            pos, [["PLANT", "MELON"], ["WATER"]], value=value_amount,
            kind="CAPITAL_CROP", cash_cost=econ.CROPS["MELON"]["seed"],
            order_key=("BUY_SEED", "MELON"),
        )

    def test_deadline_classifier_uses_exact_rule_day_only(self):
        task = self._deadline_melon()
        deadline = econ.SEED_DEADLINE["MELON"]
        on_day = self._deadline_snap(deadline // 24, 0)
        before = self._deadline_snap(deadline // 24 - 1, 23)
        after = self._deadline_snap(deadline // 24 + 1, 0)
        self.assertTrue(capital._deadline_capital_task(on_day, task))
        self.assertFalse(capital._deadline_capital_task(before, task))
        self.assertFalse(capital._deadline_capital_task(after, task))
        self.assertFalse(capital._deadline_capital_task(
            on_day, Task((0, 0), [["CARE"]], value=1),
        ))

    def test_deadline_asset_cannot_use_spent_hour_23_action(self):
        deadline = econ.SEED_DEADLINE["MELON"]
        snap = self._deadline_snap(deadline // 24, 23, money=100000)
        task = self._deadline_melon()
        model = value.TaskBundleObjective(snap, [task])
        kept = capital.validate_deadline_capital(
            snap, [task], 0, [["PASS"]], model,
        )
        self.assertEqual(kept, [])

    def test_deadline_asset_is_retained_when_initial_route_fits(self):
        deadline = econ.SEED_DEADLINE["MELON"]
        snap = self._deadline_snap(deadline // 24, 0, money=100000)
        task = self._deadline_melon()
        model = value.TaskBundleObjective(snap, [task])
        kept = capital.validate_deadline_capital(
            snap, [task], 0, [["PASS"]], model,
        )
        self.assertEqual(kept, [task])

    def test_current_unit_mutation_invalidates_stale_deadline_tile(self):
        deadline = econ.SEED_DEADLINE["MELON"]
        snap = self._deadline_snap(deadline // 24, 0, money=100000)
        snap.me.farmer = (3, 3)
        snap.seeds = {"MELON": 1}
        task = self._deadline_melon()
        model = value.TaskBundleObjective(snap, [task])
        kept = capital.validate_deadline_capital(
            snap, [task], 0, [["PLANT", "MELON"]], model,
        )
        self.assertEqual(kept, [])

    def test_deadline_validator_is_clock_free_memoized_v89_postfilter(self):
        deadline = econ.SEED_DEADLINE["MELON"]
        snap = self._deadline_snap(deadline // 24, 0, money=100000)
        plan = SimpleNamespace(cash_floor=0)
        seen = []
        original = router.joint_assign

        def capture(*args, **kwargs):
            seen.append((kwargs.get("deadline"),
                         kwargs.get("memoize_route_cost"),
                         type(kwargs.get("bundle_model")).__name__))
            return original(*args, **kwargs)

        with mock.patch.object(router, "joint_assign", capture), \
                mock.patch.object(
                    capital, "validate_deadline_capital",
                    wraps=capital.validate_deadline_capital,
                ) as validate:
            capital.decide(
                snap, plan, [], [["BUY_SEED", "MELON", 1]],
                unit_actions=[["PASS"]], deadline=0.0,
                variant="deadline_phase_validation_deterministic",
            )
        self.assertGreater(validate.call_count, 0)
        self.assertTrue(seen)
        self.assertTrue(all(deadline_value is None and memoized
                            for deadline_value, memoized, _model in seen))
        self.assertIn("TaskBundleObjective",
                      {model for _deadline, _memo, model in seen})
        self.assertIn("_ConditionalBundleObjective",
                      {model for _deadline, _memo, model in seen})

    def test_postselection_repair_is_identity_for_certified_quantity(self):
        snap = _snap(money=100000, empty=4)
        task = Task(
            (0, 0), [["PLANT", "WHEAT"], ["WATER"]], value=9999,
            kind="CAPITAL_CROP", cash_cost=econ.CROPS["WHEAT"]["seed"],
            order_key=("BUY_SEED", "WHEAT"),
        )
        economic = value.TaskBundleObjective(snap, [task])
        auditor = capital.ProductiveFeasibilityObjective(
            snap, [task], [], [], reserve=0, sell_now=True,
        )
        repaired = capital.repair_productive_selection(
            [task], auditor, economic,
        )
        self.assertEqual(repaired, [task])
        self.assertEqual(economic.score(repaired), economic.score([task]))

    def test_postselection_repair_removes_minimum_v89_score_loss(self):
        snap = _snap(money=15, empty=4)
        high = Task(
            (0, 0), [["PLANT", "WHEAT"], ["WATER"]], value=1000,
            kind="CAPITAL_CROP", cash_cost=econ.CROPS["WHEAT"]["seed"],
            order_key=("BUY_SEED", "WHEAT"),
        )
        low = Task(
            (1, 0), [["PLANT", "WHEAT"], ["WATER"]], value=100,
            kind="CAPITAL_CROP", cash_cost=econ.CROPS["WHEAT"]["seed"],
            order_key=("BUY_SEED", "WHEAT"),
        )
        tasks = [high, low]
        economic = value.TaskBundleObjective(snap, tasks)
        auditor = capital.ProductiveFeasibilityObjective(
            snap, tasks, [], [], reserve=0, sell_now=True,
        )
        self.assertEqual(auditor.score(tasks), float("-inf"))
        repaired = capital.repair_productive_selection(
            tasks, auditor, economic,
        )
        self.assertEqual(repaired, [high])
        self.assertGreater(auditor.score(repaired), float("-inf"))

    def test_postselection_master_keeps_v89_route_objective_and_memo(self):
        snap = _snap(money=100000, empty=8)
        snap.hour = 5
        plan = SimpleNamespace(cash_floor=0)
        seen = []
        original = router.joint_assign

        def capture(*args, **kwargs):
            seen.append((kwargs.get("deadline"),
                         kwargs.get("memoize_route_cost"),
                         type(kwargs.get("bundle_model")).__name__))
            return original(*args, **kwargs)

        with mock.patch.object(router, "joint_assign", capture), \
                mock.patch.object(
                    capital, "repair_productive_selection",
                    wraps=capital.repair_productive_selection,
                ) as repair:
            capital.decide(
                snap, plan, [], [["BUY_SEED", "WHEAT", 2]],
                unit_actions=[["PASS"]], deadline=0.0,
                variant="productive_postselection_repair_deterministic",
            )
        self.assertTrue(seen)
        self.assertTrue(all(
            deadline is None and memoized and model == "TaskBundleObjective"
            for deadline, memoized, model in seen
        ))
        self.assertGreater(repair.call_count, 0)

    def test_productive_feasibility_preserves_v89_score_and_marginals(self):
        snap = _snap(money=100000, shed={"MILK": 2}, empty=8)
        ordinary = Task((4, 4), [["CARE"]], value=75)
        capital_task = Task(
            (0, 0), [["PLANT", "WHEAT"], ["WATER"]], value=9999,
            kind="CAPITAL_CROP", cash_cost=econ.CROPS["WHEAT"]["seed"],
            order_key=("BUY_SEED", "WHEAT"),
        )
        tasks = [ordinary, capital_task]
        fixed = [["SELL", "MILK", 2]]
        model = capital.ProductiveFeasibilityObjective(
            snap, tasks, fixed, fixed, reserve=0, sell_now=True,
        )
        expected = value.TaskBundleObjective(snap, tasks)
        state = model.counts()
        first = model.add_gain(capital_task, state)
        model.update_counts(state, capital_task)
        second = model.add_gain(ordinary, state)
        model.update_counts(state, ordinary)
        self.assertEqual(model.score(tasks), expected.score(tasks))
        self.assertEqual(first + second, expected.score(tasks))
        self.assertGreater(model.certificate_evaluations, 0)

    def test_productive_feasibility_only_excludes_unproved_capital(self):
        snap = _snap(money=1, empty=4)
        capital_task = Task(
            (0, 0), [["PLANT", "WHEAT"], ["WATER"]], value=9999,
            kind="CAPITAL_CROP", cash_cost=econ.CROPS["WHEAT"]["seed"],
            order_key=("BUY_SEED", "WHEAT"),
        )
        model = capital.ProductiveFeasibilityObjective(
            snap, [capital_task], [], [], reserve=0, sell_now=True,
        )
        self.assertEqual(model.score([capital_task]), float("-inf"))
        self.assertEqual(model.add_gain(capital_task, model.counts()),
                         float("-inf"))
        self.assertEqual(model.score([]), 0.0)

    def test_productive_feasibility_shares_exact_cash_bound_across_reserves(self):
        snap = _snap(money=100000, empty=4)
        capital_task = Task(
            (0, 0), [["PLANT", "WHEAT"], ["WATER"]], value=9999,
            kind="CAPITAL_CROP", cash_cost=econ.CROPS["WHEAT"]["seed"],
            order_key=("BUY_SEED", "WHEAT"),
        )
        shared = {}
        low = capital.ProductiveFeasibilityObjective(
            snap, [capital_task], [], [], reserve=0, sell_now=True,
            certificate_cache=shared,
        )
        high = capital.ProductiveFeasibilityObjective(
            snap, [capital_task], [], [], reserve=200000, sell_now=True,
            certificate_cache=shared,
        )
        self.assertGreater(low.score([capital_task]), float("-inf"))
        self.assertEqual(low.certificate_evaluations, 1)
        self.assertEqual(high.score([capital_task]), float("-inf"))
        self.assertEqual(high.certificate_evaluations, 0)

    def test_productive_feasibility_branches_slots_and_charges_current_hire(self):
        snap = _snap(money=100000, shed={"MILK": 2}, empty=8)
        snap.hour = 5
        plan = SimpleNamespace(cash_floor=1000)
        seen = []
        original = router.joint_assign

        def capture(*args, **kwargs):
            model = kwargs.get("bundle_model")
            seen.append((kwargs.get("deadline"),
                         kwargs.get("memoize_route_cost"),
                         kwargs.get("max_order_keys"), model.sell_now,
                         model.reserve))
            return original(*args, **kwargs)

        with mock.patch.object(router, "joint_assign", capture):
            capital.decide(
                snap, plan, [], [["BUY_SEED", "WHEAT", 1],
                                 ["SELL", "MILK", 2]],
                unit_actions=[["PASS"]], deadline=0.0,
                variant="productive_feasibility_oracle_deterministic",
            )
        self.assertTrue(seen)
        self.assertTrue(all(deadline is None and memoized
                            for deadline, memoized, _slots, _sell, _reserve
                            in seen))
        self.assertEqual({sell for _d, _m, _s, sell, _r in seen},
                         {True, False})
        sold_slots = {slots for _d, _m, slots, sell, _r in seen if sell}
        retained_slots = {slots for _d, _m, slots, sell, _r in seen if not sell}
        # Retaining the sale always exposes exactly one more purchase slot for
        # the same k.  With the old fixed-six candidate cap both branches ended
        # at the same k; full legal enumeration also includes the retained-only
        # k=10 arm, where all ten slots are hires and zero remain for capital.
        self.assertEqual({slot + 1 for slot in sold_slots},
                         retained_slots - {0})
        self.assertIn(0, retained_slots)
        self.assertGreater(max(reserve for _d, _m, _s, _sell, reserve in seen),
                           min(reserve for _d, _m, _s, _sell, reserve in seen))

    def test_productive_feasibility_retention_requires_output_anchor(self):
        snap = _snap(shed={"MILK": 2})
        fixed = [["SELL", "MILK", 2]]
        retained = capital.ProductiveFeasibilityObjective(
            snap, [], fixed, [], reserve=0, sell_now=False,
        )
        self.assertEqual(retained.score([]), float("-inf"))

    def test_productive_inventory_master_is_clock_free_memoized_and_keeps_proposal(self):
        snap = _snap(shed={"MILK": 2})
        snap.hour = 5
        plan = SimpleNamespace(cash_floor=0)
        proposal = [["BUY_SEED", "WHEAT", 1], ["SELL", "MILK", 2]]
        seen = []
        original = router.joint_assign

        def capture(*args, **kwargs):
            seen.append((kwargs.get("deadline"),
                         kwargs.get("memoize_route_cost"),
                         type(kwargs.get("bundle_model")).__name__))
            return original(*args, **kwargs)

        with mock.patch.object(router, "joint_assign", capture):
            _hires, assets, _fixed = capital.decide(
                snap, plan, [], proposal, unit_actions=[["PASS"]],
                deadline=0.0,
                variant="productive_inventory_certificate_deterministic",
            )
        self.assertTrue(seen)
        self.assertTrue(all(
            deadline is None and memoized
            and model == "ProductiveInventoryCertificateObjective"
            for deadline, memoized, model in seen
        ))
        self.assertTrue(all(order[0] != "BUY_ANIMAL" for order in assets))

    def test_productive_inventory_empty_capital_preserves_v89_sales(self):
        snap = _snap(shed={"MILK": 3})
        fixed = [["SELL", "MILK", 3]]
        model = capital.ProductiveInventoryCertificateObjective(
            snap, [], fixed, reserve=0,
        )
        self.assertEqual(model.score([]), 0.0)
        self.assertEqual(model.fixed_orders_for([]), fixed)

    def test_all_output_path_master_uses_path_objective_and_exact_route_memo(self):
        snap = _snap(shed={"WOOL": 2})
        snap.hour = 5
        plan = SimpleNamespace(cash_floor=0)
        seen = []
        original = router.joint_assign

        def capture(*args, **kwargs):
            seen.append((kwargs.get("memoize_route_cost"),
                         type(kwargs.get("bundle_model")).__name__))
            return original(*args, **kwargs)

        with mock.patch.object(router, "joint_assign", capture):
            capital.decide(
                snap, plan, [], [["BUY_SEED", "WHEAT", 1],
                                 ["SELL", "WOOL", 2]],
                unit_actions=[["PASS"]], deadline=0.0,
                variant="productive_inventory_path_deterministic",
            )
        self.assertTrue(seen)
        self.assertTrue(all(
            memoized and model == "ProductiveInventoryPathObjective"
            for memoized, model in seen
        ))

    def test_memoized_bundle_capital_master_is_clock_free_and_opt_in(self):
        snap = _snap()
        snap.hour = 5
        plan = SimpleNamespace(cash_floor=0)
        seen = []
        original = router.joint_assign

        def capture(*args, **kwargs):
            seen.append((kwargs.get("deadline"),
                         kwargs.get("memoize_route_cost")))
            return original(*args, **kwargs)

        with mock.patch.object(router, "joint_assign", capture):
            capital.decide(
                snap, plan, [], [], unit_actions=[["PASS"]], deadline=0.0,
                variant="ordinary_bundle_master_memoized_deterministic",
            )
        self.assertTrue(seen)
        self.assertTrue(all(deadline is None and memoized
                            for deadline, memoized in seen))

    def test_deterministic_bundle_capital_master_ignores_expired_clock(self):
        snap = _snap()
        snap.hour = 5
        plan = SimpleNamespace(cash_floor=0)
        seen = []
        original = router.joint_assign

        def capture(*args, **kwargs):
            seen.append(kwargs.get("deadline"))
            return original(*args, **kwargs)

        with mock.patch.object(router, "joint_assign", capture):
            capital.decide(
                snap, plan, [], [], unit_actions=[["PASS"]], deadline=0.0,
                variant="ordinary_bundle_master_deterministic",
            )
        self.assertTrue(seen)
        self.assertTrue(all(deadline is None for deadline in seen))

    def test_refined_bundle_capital_master_is_clock_free_and_refines(self):
        snap = _snap()
        snap.hour = 5
        plan = SimpleNamespace(cash_floor=0)
        seen = []
        original = router.joint_assign

        def capture(*args, **kwargs):
            seen.append((kwargs.get("deadline"), kwargs.get("refine")))
            return original(*args, **kwargs)

        with mock.patch.object(router, "joint_assign", capture):
            capital.decide(
                snap, plan, [], [], unit_actions=[["PASS"]], deadline=0.0,
                variant="ordinary_bundle_master_refined_deterministic",
            )
        self.assertTrue(seen)
        self.assertTrue(all(deadline is None and refine
                            for deadline, refine in seen))

    def test_cash_sale_bundle_master_is_clock_free(self):
        snap = _snap()
        snap.hour = 5
        plan = SimpleNamespace(cash_floor=0)
        seen = []
        original = router.joint_assign

        def capture(*args, **kwargs):
            seen.append(kwargs.get("deadline"))
            return original(*args, **kwargs)

        with mock.patch.object(router, "joint_assign", capture):
            capital.decide(
                snap, plan, [], [], unit_actions=[["PASS"]], deadline=0.0,
                variant="ordinary_bundle_master_cash_sales_deterministic",
            )
        self.assertTrue(seen)
        self.assertTrue(all(deadline is None for deadline in seen))

    def test_cash_sale_bundle_master_adds_only_certified_sale_cash(self):
        snap = _snap(shed={"MILK": 1})
        snap.hour = 5
        plan = SimpleNamespace(cash_floor=0)
        budgets = []
        original = router.joint_assign

        def capture(*args, **kwargs):
            budgets.append(kwargs.get("cash_budget"))
            return original(*args, **kwargs)

        fixed = [["SELL", "MILK", 1]]
        certified = market.robust_sale_cash(snap, fixed)
        self.assertGreater(certified, 0.0)
        with mock.patch.object(router, "joint_assign", capture):
            capital.decide(
                snap, plan, [], fixed, unit_actions=[["PASS"]],
                variant="ordinary_bundle_master_cash_sales_deterministic",
            )
        self.assertTrue(budgets)
        self.assertEqual(max(budgets), snap.me.money + certified)

    def test_certified_bundle_capital_master_ignores_expired_clock(self):
        snap = _snap()
        snap.hour = 5
        plan = SimpleNamespace(cash_floor=0)
        seen = []
        original = router.joint_assign

        def capture(*args, **kwargs):
            seen.append(kwargs.get("deadline"))
            return original(*args, **kwargs)

        with mock.patch.object(router, "joint_assign", capture):
            capital.decide(
                snap, plan, [], [], unit_actions=[["PASS"]], deadline=0.0,
                variant="certified_bundle_master_deterministic",
            )
        self.assertTrue(seen)
        self.assertTrue(all(deadline is None for deadline in seen))

    def test_phase_correct_units_start_after_committed_movement(self):
        snap = _snap()
        snap.hour = 5
        snap.board = 10
        snap.me.farmer = (4, 4)
        snap.me.hands = [(5, 4)]
        units = capital._units(
            snap, 0, [["WEST"], ["NORTH"]], post_action=True,
        )
        self.assertEqual([unit.start for unit in units], [(3, 4), (5, 3)])
        self.assertEqual([unit.start_hour for unit in units], [6, 6])
        self.assertEqual([unit.budget for unit in units], [18, 18])

    def test_market_capital_cannot_use_the_already_spent_last_action(self):
        snap = _snap()
        snap.hour = 23
        snap.board = 10
        snap.me.farmer = (4, 4)
        snap.me.hands = []
        task = Task((4, 4), [["PLANT", "WHEAT"]], value=100)
        legacy = capital._units(snap, 0, [["PASS"]], post_action=False)
        corrected = capital._units(snap, 0, [["PASS"]], post_action=True)
        legacy_assignment, _ = router.joint_assign(
            [task], legacy, {}, refine=False,
        )
        corrected_assignment, _ = router.joint_assign(
            [task], corrected, {}, refine=False,
        )
        self.assertEqual(len(capital._selected(legacy_assignment)), 1)
        self.assertEqual(len(capital._selected(corrected_assignment)), 0)

    def test_projected_units_do_not_replay_movement_or_spawn_projection(self):
        snap = _snap()
        snap.hour = 5
        snap.board = 10
        # These are already the positions after WEST and NORTH respectively.
        snap.me.farmer = (3, 4)
        snap.me.hands = [(5, 3)]
        units = capital._units(
            snap, 1, [["WEST"], ["NORTH"]], post_action=True,
            already_projected=True,
        )
        self.assertEqual([unit.start for unit in units[:2]], [(3, 4), (5, 3)])
        self.assertEqual([unit.start_hour for unit in units], [6, 6, 6])
        self.assertEqual(units[2].start, (4, 4))

    def test_idle_phase_guard_requires_every_unit_to_pass(self):
        self.assertTrue(capital._idle_unit_phase([["PASS"], ["PASS"]]))
        self.assertFalse(capital._idle_unit_phase([["PASS"], ["WEST"]]))
        self.assertFalse(capital._idle_unit_phase([["PASS"], ["CARE"]]))
        self.assertFalse(capital._idle_unit_phase([]))

    def test_split_keeps_survival_and_sales_fixed(self):
        fixed, proposed = capital.split_orders([
            ["BUY_PRODUCT", "WHEAT", 3],
            ["BUY_ANIMAL", "COW", 2],
            ["SELL", "MILK", 4],
            ["BUY_LAND"],
            ["BUY_SEED", "WHEAT", 5],
        ])
        self.assertEqual(fixed, [["BUY_PRODUCT", "WHEAT", 3],
                                 ["SELL", "MILK", 4]])
        self.assertEqual(len(proposed), 3)

    def test_compose_preserves_feed_before_hire_and_assets(self):
        got = capital.compose_orders(
            [["SELL", "MILK", 4], ["BUY_PRODUCT", "WHEAT", 3]],
            2, [["BUY_SEED", "WHEAT", 5]],
        )
        self.assertEqual(got, [
            ["BUY_PRODUCT", "WHEAT", 3], ["HIRE"], ["HIRE"],
            ["BUY_SEED", "WHEAT", 5], ["SELL", "MILK", 4],
        ])

    def test_cash_certificate_frontloads_sales_before_every_spend(self):
        got = capital.compose_orders(
            [["BUY_PRODUCT", "WHEAT", 3], ["SELL", "MILK", 4]],
            1, [["BUY_ANIMAL", "COW", 1]], frontload_sales=True,
        )
        self.assertEqual(got, [
            ["SELL", "MILK", 4], ["BUY_PRODUCT", "WHEAT", 3],
            ["HIRE"], ["BUY_ANIMAL", "COW", 1],
        ])

    def test_selected_columns_recover_quantities_and_land_once(self):
        activation = {("BUY_LAND", "NE"): 1000}
        selected = [
            Task((5, 0), [["PLANT", "WHEAT"]], value=20,
                 order_key=("BUY_SEED", "WHEAT"), activations=activation),
            Task((6, 0), [["PLANT", "WHEAT"]], value=20,
                 order_key=("BUY_SEED", "WHEAT"), activations=activation),
        ]
        proposed = [["BUY_SEED", "WHEAT", 8], ["BUY_LAND"]]
        self.assertEqual(capital._asset_orders(selected, proposed), [
            ["BUY_SEED", "WHEAT", 2], ["BUY_LAND"],
        ])


    def test_shared_land_activation_is_charged_once_in_objective(self):
        activation = {("BUY_LAND", "NE"): 1000}
        selected = [
            Task((5, 0), [["PLANT", "WHEAT"]], value=600,
                 activations=activation),
            Task((6, 0), [["PLANT", "WHEAT"]], value=600,
                 activations=activation),
        ]
        self.assertEqual(capital._activation_cost(selected), 1000)

    def test_distinct_fixed_activations_are_additive(self):
        selected = [
            Task((5, 0), [["PLANT", "WHEAT"]], value=600,
                 activations={("BUY_LAND", "NE"): 1000}),
            Task((6, 0), [["PLANT", "WHEAT"]], value=600,
                 activations={("IRRIGATION", "NW"): 250}),
        ]
        self.assertEqual(capital._activation_cost(selected), 1250)

    def _best_land_branch(self, per_task_value):
        activation = {("BUY_LAND", "NE"): 1000}
        tasks = [
            Task((0, 0), [["CARE"]], value=per_task_value,
                 activations=activation),
            Task((0, 1), [["CARE"]], value=per_task_value,
                 activations=activation),
        ]
        candidates = []
        for branch in capital._activation_task_sets(tasks):
            assignment, _ = router.joint_assign(
                branch, [Unit(0, (0, 0))], {}, cash_budget=2000,
                refine=False,
            )
            chosen = capital._selected(assignment)
            candidates.append((capital._net_score(chosen), chosen))
        return max(candidates, key=lambda pair: pair[0])

    def test_negative_land_bundle_loses_to_no_land_branch(self):
        score, chosen = self._best_land_branch(400)
        self.assertEqual(score, 0)
        self.assertEqual(chosen, [])

    def test_positive_land_bundle_pays_fixed_cost_once(self):
        score, chosen = self._best_land_branch(600)
        self.assertEqual(score, 200)
        self.assertEqual(len(chosen), 2)

    def test_repeated_crop_columns_clear_as_one_nonlinear_bundle(self):
        snap = SimpleNamespace(
            day=0,
            market_inv={"STRAWBERRY": econ.MARKET_I0},
            opp=SimpleNamespace(animals={}, crops={}),
        )
        qty = value.plant_output_units(snap, "STRAWBERRY")
        standalone = value.sale_value(snap, "STRAWBERRY", qty)
        columns = [
            Task((i, 0), [["PLANT", "STRAWBERRY"], ["WATER"]],
                 value=standalone - 100, kind="CAPITAL_CROP")
            for i in range(3)
        ]
        capital._bundle_reprice_capital(snap, columns)
        gross = sum(task.value + 100 for task in columns)
        self.assertEqual(gross, value.sale_value(snap, "STRAWBERRY", 3 * qty))
        self.assertLess(gross, 3 * standalone)

    def test_bundle_repricing_keeps_non_sale_costs(self):
        snap = SimpleNamespace(
            day=20,
            market_inv={"MELON": econ.MARKET_I0},
            opp=SimpleNamespace(animals={}, crops={}),
        )
        qty = value.plant_output_units(snap, "MELON")
        standalone = value.sale_value(snap, "MELON", qty)
        task = Task((0, 0), [["PLANT", "MELON"], ["WATER"]],
                    value=standalone - 80, kind="CAPITAL_CROP")
        capital._bundle_reprice_capital(snap, [task])
        self.assertEqual(task.value, standalone - 80)

    def test_repeated_animal_columns_share_milk_curve(self):
        snap = SimpleNamespace(
            day=0,
            market_inv={"MILK": econ.MARKET_I0, "WHEAT": econ.MARKET_I0},
            opp=SimpleNamespace(animals={}, crops={}),
        )
        qty = value.animal_placement_units(snap, "COW")
        standalone = value.sale_value(snap, "MILK", qty)
        placement = value.animal_placement_value(snap, "COW")
        columns = [
            Task((i, 0), [["BUILD_PASTURE"], ["PLACE", "COW"]],
                 {"COW": 1}, value=placement - 400, kind="CAPITAL_ANIMAL")
            for i in range(2)
        ]
        non_sale = sum(task.value - standalone for task in columns)
        capital._bundle_reprice_capital(snap, columns)
        self.assertEqual(
            sum(task.value for task in columns),
            non_sale + value.sale_value(snap, "MILK", 2 * qty),
        )

    def test_selected_bundle_recertifies_actual_crop_quantity(self):
        snap = SimpleNamespace(
            day=0,
            market_inv={"STRAWBERRY": econ.MARKET_I0},
            opp=SimpleNamespace(animals={}, crops={}),
        )
        qty = value.plant_output_units(snap, "STRAWBERRY")
        standalone = value.sale_value(snap, "STRAWBERRY", qty)
        columns = [
            Task((i, 0), [["PLANT", "STRAWBERRY"], ["WATER"]],
                 value=standalone - 100, kind="CAPITAL_CROP")
            for i in range(3)
        ]
        terms = capital._capital_bundle_terms(snap, columns)
        capital._bundle_reprice_capital(snap, columns, terms=terms)

        # The route master may trim a three-tile certificate to one executable
        # tile. Its terminal sale is then the exact singleton quantity, not
        # one third of the conservative three-tile bundle.
        score = capital._recertified_net_score(
            snap, [columns[0]], terms,
        )
        self.assertEqual(score, standalone - 100)
        self.assertGreater(score, columns[0].value)

    def test_selected_bundle_recertification_keeps_all_other_terms_once(self):
        snap = SimpleNamespace(
            day=0,
            market_inv={"STRAWBERRY": econ.MARKET_I0},
            opp=SimpleNamespace(animals={}, crops={}),
        )
        qty = value.plant_output_units(snap, "STRAWBERRY")
        standalone = value.sale_value(snap, "STRAWBERRY", qty)
        activation = {("BUY_LAND", "NE"): 1000}
        columns = [
            Task((i + 5, 0), [["PLANT", "STRAWBERRY"], ["WATER"]],
                 value=standalone - 100, kind="CAPITAL_CROP",
                 activations=activation)
            for i in range(3)
        ]
        ordinary = Task((0, 0), [["CARE"]], value=75)
        terms = capital._capital_bundle_terms(snap, columns)
        capital._bundle_reprice_capital(snap, columns, terms=terms)

        selected = [ordinary, columns[0], columns[1]]
        score = capital._recertified_net_score(
            snap, selected, terms, hire_cost=10,
        )
        expected = (75 - 2 * 100
                    + value.sale_value(snap, "STRAWBERRY", 2 * qty)
                    - 10 - 1000)
        self.assertEqual(score, expected)

    def test_paired_recertificate_uses_only_actual_routed_capital(self):
        snap = _snap(money=100000, empty=8)
        ordinary = Task((4, 4), [["CARE"]], value=75)
        columns = [
            Task((i, 0), [["PLANT", "MELON"], ["WATER"]],
                 value=9999, kind="CAPITAL_CROP",
                 cash_cost=econ.CROPS["MELON"]["seed"],
                 order_key=("BUY_SEED", "MELON"))
            for i in range(2)
        ]
        selected = [ordinary, columns[0]]
        score = capital._paired_recertified_score(
            snap, selected, fixed_orders=[], reserve=0, hire_cost=10,
        )
        expected = cashflow.certify_shared(
            snap, {"MELON": 1}, [(0, 0)], reserve=0,
            fixed_orders=[], paired_objective=True,
        )
        self.assertTrue(expected.feasible, expected.reason)
        self.assertEqual(score, 75 + expected.paired_value - 10)

    def test_positioned_capital_columns_preserve_certificate_assignment(self):
        snap = _snap(money=100000, empty=8)
        proposed = [["BUY_SEED", "MELON", 2],
                    ["BUY_ANIMAL", "GOOSE", 1]]
        positions = {"MELON": [(0, 0), (1, 0)], "GOOSE": [(2, 0)]}
        columns, _animals = capital.capital_tasks(
            snap, proposed, [], positions_by_item=positions,
        )
        got = {(task.order_key[1], tuple(task.pos)) for task in columns}
        self.assertEqual(got, {
            ("MELON", (0, 0)), ("MELON", (1, 0)), ("GOOSE", (2, 0)),
        })

    def test_robust_tail_repair_enumerates_quantity_and_drops_bad_last_unit(self):
        snap = _snap(money=3000, empty=24)
        positions = {
            "COW": ((3, 4), (4, 3), (2, 4)),
            "SHEEP": ((3, 3),),
            "MELON": ((4, 2), (1, 4), (2, 3), (3, 2),
                      (4, 1), (0, 4), (1, 3)),
            "WHEAT": ((2, 2), (3, 1), (4, 0), (0, 3), (1, 2),
                      (2, 1), (3, 0), (0, 2), (1, 1), (2, 0),
                      (0, 1), (1, 0), (0, 0)),
        }
        row = {
            "assets": [
                ["BUY_ANIMAL", "COW", 3],
                ["BUY_ANIMAL", "SHEEP", 1],
                ["BUY_SEED", "MELON", 7],
                ["BUY_SEED", "WHEAT", 13],
            ],
            "positions_by_item": positions,
            "selected_counts": {item: len(pos)
                                for item, pos in positions.items()},
            "service_reserve": 0.0, "hire_cost": 7.0, "fixed": [],
        }
        repaired = capital._robust_tail_repair(snap, row)
        self.assertEqual(repaired["robust_tail_item"], "WHEAT")
        self.assertEqual(repaired["robust_tail_quantity"], 12)
        self.assertEqual(repaired["assets"][-1],
                         ["BUY_SEED", "WHEAT", 12])
        self.assertEqual(len(repaired["positions_by_item"]["WHEAT"]), 12)

    def test_robust_composition_exchange_holds_coverage_and_changes_book(self):
        snap = _snap(money=3000, empty=4)
        positions = {"COW": ((0, 0),), "WHEAT": ((1, 0),)}
        row = {
            "assets": [
                ["BUY_ANIMAL", "COW", 1],
                ["BUY_SEED", "WHEAT", 1],
            ],
            "positions_by_item": positions,
            "selected_counts": {"COW": 1, "WHEAT": 1},
            "service_reserve": 0.0, "hire_cost": 1.0, "fixed": [],
            "score": 50.0, "completed_tasks": 2,
        }

        def certificate(_snap, counts, _slots, **_kwargs):
            # Unique COW -> MELON improvement on a surface where coverage is
            # identical in every call and therefore has no objective weight.
            paired = (100.0 * int(counts.get("MELON", 0))
                      + 10.0 * int(counts.get("WHEAT", 0))
                      - 5.0 * int(counts.get("COW", 0)))
            return SimpleNamespace(
                feasible=True, paired_value=paired, final_cash=3000 + paired,
                upfront_spend=0.0,
            )

        with mock.patch(
                "whitebox.stackelberg.make_context", return_value={}), \
                mock.patch(
                    "whitebox.stackelberg.certify_unified",
                    side_effect=certificate):
            repaired = capital._robust_composition_exchange(snap, row)

        self.assertEqual(sum(repaired["selected_counts"].values()), 2)
        self.assertEqual(repaired["composition_coverage"], 2)
        self.assertEqual(repaired["composition_exchange_from"], "COW")
        self.assertEqual(repaired["composition_exchange_to"], "MELON")
        self.assertEqual(repaired["composition_exchange_quantity"], 1)
        self.assertEqual(repaired["selected_counts"],
                         {"MELON": 1, "WHEAT": 1})
        self.assertEqual(repaired["composition_books"],
                         {"MELON": "MELON", "WHEAT": "WHEAT"})
        self.assertEqual(repaired["completed_tasks"], 2)

    def test_single_quadrant_asset_class_exchange_rejects_cross_class_ray(self):
        """The lifecycle gate keeps an animal when only CROP is better."""
        snap = _snap(money=3000, empty=4)
        positions = {"COW": ((0, 0),)}
        row = {
            "assets": [["BUY_ANIMAL", "COW", 1]],
            "positions_by_item": positions,
            "selected_counts": {"COW": 1},
            "service_reserve": 0.0, "hire_cost": 1.0, "fixed": [],
        }

        def certificate(_snap, counts, _slots, **_kwargs):
            paired = (100.0 * int(counts.get("MELON", 0))
                      + 10.0 * int(counts.get("COW", 0)))
            return SimpleNamespace(
                feasible=True, paired_value=paired, final_cash=3000 + paired,
                upfront_spend=0.0,
            )

        with mock.patch(
                "whitebox.stackelberg.make_context", return_value={}), \
                mock.patch(
                    "whitebox.stackelberg.certify_unified",
                    side_effect=certificate):
            repaired = capital._robust_composition_exchange(
                snap, row, same_asset_class_only=True,
            )

        self.assertEqual(repaired["selected_counts"], {"COW": 1})
        self.assertEqual(repaired["composition_exchange_quantity"], 0)

    def test_single_quadrant_asset_class_exchange_keeps_within_class_rays(self):
        """The gate filters classes, rather than disabling all exchanges."""
        snap = _snap(money=3000, empty=4)
        positions = {"COW": ((0, 0),), "WHEAT": ((1, 0),)}
        row = {
            "assets": [
                ["BUY_ANIMAL", "COW", 1],
                ["BUY_SEED", "WHEAT", 1],
            ],
            "positions_by_item": positions,
            "selected_counts": {"COW": 1, "WHEAT": 1},
            "service_reserve": 0.0, "hire_cost": 1.0, "fixed": [],
        }

        def certificate(_snap, counts, _slots, **_kwargs):
            paired = (40.0 * int(counts.get("SHEEP", 0))
                      + 20.0 * int(counts.get("WHEAT", 0))
                      - 5.0 * int(counts.get("COW", 0)))
            return SimpleNamespace(
                feasible=True, paired_value=paired, final_cash=3000 + paired,
                upfront_spend=0.0,
            )

        with mock.patch(
                "whitebox.stackelberg.make_context", return_value={}), \
                mock.patch(
                    "whitebox.stackelberg.certify_unified",
                    side_effect=certificate):
            repaired = capital._robust_composition_exchange(
                snap, row, same_asset_class_only=True,
            )

        self.assertEqual(repaired["selected_counts"],
                         {"SHEEP": 1, "WHEAT": 1})
        self.assertEqual(repaired["composition_exchange_to"], "SHEEP")

    def test_single_quadrant_asset_class_exchange_keeps_crop_rays(self):
        snap = _snap(money=3000, empty=4)
        row = {
            "assets": [["BUY_SEED", "WHEAT", 1]],
            "positions_by_item": {"WHEAT": ((0, 0),)},
            "selected_counts": {"WHEAT": 1},
            "service_reserve": 0.0, "hire_cost": 1.0, "fixed": [],
        }

        def certificate(_snap, counts, _slots, **_kwargs):
            paired = (100.0 * int(counts.get("MELON", 0))
                      + 10.0 * int(counts.get("WHEAT", 0)))
            return SimpleNamespace(
                feasible=True, paired_value=paired, final_cash=3000 + paired,
                upfront_spend=0.0,
            )

        with mock.patch(
                "whitebox.stackelberg.make_context", return_value={}), \
                mock.patch(
                    "whitebox.stackelberg.certify_unified",
                    side_effect=certificate):
            repaired = capital._robust_composition_exchange(
                snap, row, same_asset_class_only=True,
            )

        self.assertEqual(repaired["selected_counts"], {"MELON": 1})
        self.assertEqual(repaired["composition_exchange_to"], "MELON")

    def test_opening_animal_retention_rejects_only_animal_to_crop(self):
        snap = _snap(money=3000, empty=4)
        row = {
            "assets": [["BUY_ANIMAL", "COW", 1]],
            "positions_by_item": {"COW": ((0, 0),)},
            "selected_counts": {"COW": 1},
            "service_reserve": 0.0, "hire_cost": 1.0, "fixed": [],
        }

        def certificate(_snap, counts, _slots, **_kwargs):
            paired = (100.0 * int(counts.get("MELON", 0))
                      + 10.0 * int(counts.get("COW", 0)))
            return SimpleNamespace(
                feasible=True, paired_value=paired, final_cash=3000 + paired,
                upfront_spend=0.0,
            )

        with mock.patch(
                "whitebox.stackelberg.make_context", return_value={}), \
                mock.patch(
                    "whitebox.stackelberg.certify_unified",
                    side_effect=certificate):
            repaired = capital._robust_composition_exchange(
                snap, row, disallow_animal_to_crop_exchange=True,
            )
        self.assertEqual(repaired["selected_counts"], {"COW": 1})
        self.assertEqual(repaired["composition_exchange_quantity"], 0)

    def test_composition_source_quadrant_covenant_cannot_touch_other_land(self):
        snap = _snap(money=3000, empty=4)
        snap.me.unlocked = ["NW", "NE", "SW"]
        snap.me.tiles[5][0] = None
        positions = {"COW": ((0, 0), (0, 5))}
        row = {
            "assets": [["BUY_ANIMAL", "COW", 2]],
            "positions_by_item": positions,
            "selected_counts": {"COW": 2},
            "service_reserve": 0.0, "hire_cost": 0.0, "fixed": [],
            "score": 0.0, "completed_tasks": 2,
        }

        def certificate(_snap, counts, _slots, **_kwargs):
            paired = 100.0 * int(counts.get("MELON", 0))
            return SimpleNamespace(
                feasible=True, paired_value=paired,
                final_cash=3000.0 + paired, upfront_spend=0.0,
            )

        with mock.patch(
                "whitebox.stackelberg.make_context", return_value={}), \
                mock.patch(
                    "whitebox.stackelberg.certify_unified",
                    side_effect=certificate):
            repaired = capital._robust_composition_exchange(
                snap, row, source_asset_class="ANIMAL",
                source_quadrants=("SW",), target_asset_class="CROP",
            )

        self.assertEqual(repaired["selected_counts"], {
            "COW": 1, "MELON": 1,
        })
        self.assertEqual(repaired["positions_by_item"]["COW"], ((0, 0),))
        self.assertEqual(repaired["positions_by_item"]["MELON"], ((0, 5),))

    def test_response_vector_dominance_rejects_hidden_scenario_loss(self):
        snap = _snap(money=3000, empty=2)
        response_a = SimpleNamespace(name="A")
        response_b = SimpleNamespace(name="B")
        context = {
            "responses": (response_a, response_b),
            "opponent_baseline": {}, "drains": {},
        }
        baseline = SimpleNamespace(
            upfront_spend=10.0, operating_cost=2.0,
            outputs_by_day={2: {"WHEAT": 1}},
        )
        candidate = SimpleNamespace(
            upfront_spend=9.0, operating_cost=2.0,
            outputs_by_day={2: {"MELON": 1}},
        )

        def margin(_snap, outputs, _cost, response, *_rest):
            if response.name == "A":
                return 20.0 if "MELON" in outputs[2] else 10.0
            return 9.0 if "MELON" in outputs[2] else 10.0

        with mock.patch(
                "whitebox.stackelberg._response_margin",
                side_effect=margin):
            self.assertFalse(capital._response_vector_dominates(
                snap, candidate, baseline, context,
            ))

    def test_positioned_recertificate_uses_retained_item_tile_pairs(self):
        snap = _snap(money=100000, empty=8)
        ordinary = Task((4, 4), [["CARE"]], value=75)
        melon = Task(
            (0, 0), [["PLANT", "MELON"], ["WATER"]], value=9999,
            kind="CAPITAL_CROP", cash_cost=econ.CROPS["MELON"]["seed"],
            order_key=("BUY_SEED", "MELON"),
        )
        goose = Task(
            (2, 0), [["BUILD_COOP"], ["PLACE", "GOOSE"]],
            {"GOOSE": 1}, value=9999, kind="CAPITAL_ANIMAL",
            cash_cost=econ.ANIMALS["GOOSE"]["cost"],
            order_key=("BUY_ANIMAL", "GOOSE"),
        )
        ordinary_model = value.TaskBundleObjective(snap, [ordinary])
        score = capital._positioned_paired_recertified_score(
            snap, [ordinary, melon, goose], [], 0, ordinary_model,
            hire_cost=10,
        )
        expected = cashflow.certify_shared(
            snap, {"MELON": 1, "GOOSE": 1}, [(0, 0), (2, 0)],
            reserve=0, fixed_orders=[], paired_objective=True,
            positions_by_item={"MELON": [(0, 0)], "GOOSE": [(2, 0)]},
        )
        self.assertTrue(expected.feasible, expected.reason)
        self.assertEqual(score, 75 + expected.paired_value - 10)

    def test_positioned_certificate_objective_marginals_telescope_exactly(self):
        snap = _snap(money=100000, empty=8)
        ordinary = Task((4, 4), [["CARE"]], value=75)
        columns = [
            Task(
                (i, 0), [["PLANT", "MELON"], ["WATER"]], value=9999,
                kind="CAPITAL_CROP", cash_cost=econ.CROPS["MELON"]["seed"],
                order_key=("BUY_SEED", "MELON"),
            ) for i in range(2)
        ]
        model = capital.PositionedCertificateObjective(
            snap, [ordinary] + columns, [], reserve=0,
        )
        state = model.counts()
        first = model.add_gain(columns[0], state)
        model.update_counts(state, columns[0])
        second = model.add_gain(columns[1], state)
        model.update_counts(state, columns[1])
        ordinary_gain = model.add_gain(ordinary, state)
        model.update_counts(state, ordinary)
        self.assertEqual(
            first + second + ordinary_gain,
            model.score([ordinary] + columns),
        )
        expected = cashflow.certify_shared(
            snap, {"MELON": 2}, [(0, 0), (1, 0)], reserve=0,
            fixed_orders=[], paired_objective=True,
            positions_by_item={"MELON": [(0, 0), (1, 0)]},
        )
        self.assertTrue(expected.feasible, expected.reason)
        self.assertEqual(model.score([ordinary] + columns),
                         75 + expected.paired_value)

    def test_positioned_certificate_objective_swap_is_exact_and_cached(self):
        snap = _snap(money=100000, empty=8)
        melon = Task(
            (0, 0), [["PLANT", "MELON"], ["WATER"]], value=9999,
            kind="CAPITAL_CROP", cash_cost=econ.CROPS["MELON"]["seed"],
            order_key=("BUY_SEED", "MELON"),
        )
        cow = Task(
            (2, 0), [["BUILD_PASTURE"], ["PLACE", "COW"]],
            {"COW": 1}, value=9999, kind="CAPITAL_ANIMAL",
            cash_cost=econ.ANIMALS["COW"]["cost"],
            order_key=("BUY_ANIMAL", "COW"),
        )
        model = capital.PositionedCertificateObjective(
            snap, [melon, cow], [], reserve=0,
        )
        state = model.counts([melon])
        expected = model.score([cow]) - model.score([melon])
        evaluations = model.certificate_evaluations
        self.assertEqual(model.swap_gain(cow, melon, state), expected)
        # Repeating the identical exact subset comparison is a cache hit.
        self.assertEqual(model.swap_gain(cow, melon, state), expected)
        self.assertEqual(model.certificate_evaluations, evaluations)

    def test_first_output_objective_matches_exact_prefix_certificate(self):
        snap = _snap(money=100000, empty=8)
        goose = Task(
            (0, 0), [["BUILD_COOP"], ["PLACE", "GOOSE"]],
            {"GOOSE": 1}, value=9999, kind="CAPITAL_ANIMAL",
            cash_cost=econ.ANIMALS["GOOSE"]["cost"],
            order_key=("BUY_ANIMAL", "GOOSE"),
        )
        model = capital.FirstOutputPrefixObjective(
            snap, [goose], [], reserve=0,
        )
        expected = cashflow.certify_shared(
            snap, {"GOOSE": 1}, [(0, 0)], reserve=0,
            fixed_orders=[], paired_objective=True,
            positions_by_item={"GOOSE": [(0, 0)]},
            first_output_only=True,
        )
        self.assertTrue(expected.feasible, expected.reason)
        self.assertEqual(model.score([goose]), expected.paired_value)
        self.assertEqual(model.certificate_evaluations, 1)

    def test_first_output_master_is_clock_free_memoized_and_hire_aware(self):
        snap = _snap(money=100000, empty=8)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=100)
        slot = cashflow._available_slots(snap)[0]
        proposal_cert = cashflow.Certificate({"WHEAT": 1})
        proposal_cert.positions_by_item = {"WHEAT": (slot,)}
        seen = []
        original = router.joint_assign

        def capture(*args, **kwargs):
            model = kwargs.get("bundle_model")
            seen.append((kwargs.get("deadline"),
                         kwargs.get("memoize_route_cost"),
                         type(model).__name__, model.reserve))
            return original(*args, **kwargs)

        with mock.patch.object(
                cashflow, "invent_first_output_proposal",
                return_value=([["BUY_SEED", "WHEAT", 1]], proposal_cert)), \
                mock.patch.object(router, "joint_assign", capture):
            capital.decide(
                snap, plan, [], [], unit_actions=[["PASS"]], deadline=0.0,
                variant="first_output_prefix_master_memoized_deterministic",
            )
        self.assertTrue(seen)
        self.assertTrue(all(deadline is None and memoized
                            and model == "FirstOutputPrefixObjective"
                            for deadline, memoized, model, _reserve in seen))
        reserves = [reserve for _deadline, _memo, _model, reserve in seen]
        self.assertEqual(min(reserves), 100)
        self.assertGreater(max(reserves), 100)

    def test_exact_first_output_objective_matches_corrected_certificate(self):
        snap = _snap(money=100000, empty=8)
        wheat = Task(
            (0, 0), [["PLANT", "WHEAT"], ["WATER"]], value=9999,
            kind="CAPITAL_CROP", cash_cost=econ.CROPS["WHEAT"]["seed"],
            order_key=("BUY_SEED", "WHEAT"),
        )
        model = capital.ExactFirstOutputObjective(
            snap, [wheat], [], reserve=0,
        )
        expected = cashflow.certify_shared(
            snap, {"WHEAT": 1}, [(0, 0)], reserve=0,
            fixed_orders=[], paired_objective=True,
            positions_by_item={"WHEAT": [(0, 0)]},
            exact_first_output=True,
        )
        self.assertTrue(expected.feasible, expected.reason)
        self.assertEqual(model.score([wheat]), expected.paired_value)

    def test_exact_first_output_master_is_clock_free_and_memoized(self):
        snap = _snap(money=100000, empty=8)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=100)
        slot = cashflow._available_slots(snap)[0]
        proposal_cert = cashflow.Certificate({"WHEAT": 1})
        proposal_cert.positions_by_item = {"WHEAT": (slot,)}
        seen = []
        original = router.joint_assign

        def capture(*args, **kwargs):
            model = kwargs.get("bundle_model")
            seen.append((kwargs.get("deadline"),
                         kwargs.get("memoize_route_cost"),
                         type(model).__name__))
            return original(*args, **kwargs)

        with mock.patch.object(
                cashflow, "invent_exact_first_output_proposal",
                return_value=([["BUY_SEED", "WHEAT", 1]], proposal_cert)), \
                mock.patch.object(router, "joint_assign", capture):
            capital.decide(
                snap, plan, [], [], unit_actions=[["PASS"]], deadline=0.0,
                variant="exact_first_output_master_memoized_deterministic",
            )
        self.assertTrue(seen)
        self.assertTrue(all(
            deadline is None and memoized
            and model == "ExactFirstOutputObjective"
            for deadline, memoized, model in seen
        ))

    def test_joint_farm_prefix_objective_matches_marginal_certificate(self):
        snap = _snap(money=100000, empty=8)
        snap.me.crops[(2, 0)] = {"crop": "STRAWBERRY"}
        wheat = Task(
            (0, 0), [["PLANT", "WHEAT"], ["WATER"]], value=9999,
            kind="CAPITAL_CROP", cash_cost=econ.CROPS["WHEAT"]["seed"],
            order_key=("BUY_SEED", "WHEAT"),
        )
        model = capital.JointFarmPrefixObjective(
            snap, [wheat], [], reserve=0,
        )
        expected = cashflow.certify_joint_farm_prefix(
            snap, {"WHEAT": 1}, [(0, 0)], reserve=0,
            fixed_orders=[], paired_objective=True,
            positions_by_item={"WHEAT": [(0, 0)]},
        )
        self.assertTrue(expected.feasible, expected.reason)
        self.assertEqual(model.score([wheat]), expected.paired_value)
        self.assertEqual(model.certificate_evaluations, 1)

    def test_joint_farm_prefix_master_is_clock_free_memoized_and_hire_aware(self):
        snap = _snap(money=100000, empty=8)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=100)
        slot = cashflow._available_slots(snap)[0]
        proposal_cert = cashflow.Certificate({"WHEAT": 1})
        proposal_cert.positions_by_item = {"WHEAT": (slot,)}
        seen = []
        original = router.joint_assign

        def capture(*args, **kwargs):
            model = kwargs.get("bundle_model")
            seen.append((kwargs.get("deadline"),
                         kwargs.get("memoize_route_cost"),
                         type(model).__name__, model.reserve))
            return original(*args, **kwargs)

        with mock.patch.object(
                cashflow, "invent_joint_farm_prefix_proposal",
                return_value=([["BUY_SEED", "WHEAT", 1]], proposal_cert)), \
                mock.patch.object(router, "joint_assign", capture):
            capital.decide(
                snap, plan, [], [], unit_actions=[["PASS"]], deadline=0.0,
                variant="joint_farm_prefix_master_memoized_deterministic",
            )
        self.assertTrue(seen)
        self.assertTrue(all(
            deadline is None and memoized
            and model == "JointFarmPrefixObjective"
            for deadline, memoized, model, _reserve in seen
        ))
        self.assertEqual(min(row[3] for row in seen), 100)
        self.assertGreater(max(row[3] for row in seen), 100)

    def test_optional_continuation_objective_matches_endpoint_certificate(self):
        snap = _snap(money=100000, empty=8)
        cow = Task(
            (0, 0), [["BUILD_PASTURE"], ["PLACE", "COW"]],
            {"COW": 1}, value=9999, kind="CAPITAL_ANIMAL",
            cash_cost=econ.ANIMALS["COW"]["cost"],
            order_key=("BUY_ANIMAL", "COW"),
        )
        model = capital.OptionalContinuationObjective(
            snap, [cow], [], reserve=0,
        )
        expected = cashflow.certify_optional_continuation(
            snap, {"COW": 1}, [(0, 0)], reserve=0,
            positions_by_item={"COW": [(0, 0)]},
        )
        self.assertTrue(expected.feasible, expected.reason)
        self.assertEqual(model.score([cow]), expected.paired_value)
        self.assertEqual(model.certificate_evaluations, 1)

    def test_optional_continuation_master_is_clock_free_and_memoized(self):
        snap = _snap(money=100000, empty=8)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=100)
        slot = cashflow._available_slots(snap)[0]
        proposal_cert = cashflow.Certificate({"COW": 1})
        proposal_cert.positions_by_item = {"COW": (slot,)}
        seen = []
        original = router.joint_assign

        def capture(*args, **kwargs):
            model = kwargs.get("bundle_model")
            seen.append((kwargs.get("deadline"),
                         kwargs.get("memoize_route_cost"),
                         type(model).__name__, model.reserve))
            return original(*args, **kwargs)

        with mock.patch.object(
                cashflow, "invent_optional_continuation_proposal",
                return_value=([["BUY_ANIMAL", "COW", 1]], proposal_cert)), \
                mock.patch.object(router, "joint_assign", capture):
            capital.decide(
                snap, plan, [], [], unit_actions=[["PASS"]], deadline=0.0,
                variant="optional_continuation_master_memoized_deterministic",
            )
        self.assertTrue(seen)
        self.assertTrue(all(
            deadline is None and memoized
            and model == "OptionalContinuationObjective"
            for deadline, memoized, model, _reserve in seen
        ))
        self.assertEqual(min(row[3] for row in seen), 100)
        self.assertGreater(max(row[3] for row in seen), 100)

    def test_certified_marginal_master_ignores_expired_clock(self):
        snap = _snap()
        snap.hour = 5
        plan = SimpleNamespace(cash_floor=0)
        seen = []
        original = router.joint_assign

        def capture(*args, **kwargs):
            seen.append((kwargs.get("deadline"), kwargs.get("bundle_model")))
            return original(*args, **kwargs)

        with mock.patch.object(router, "joint_assign", capture):
            capital.decide(
                snap, plan, [], [], unit_actions=[["PASS"]], deadline=0.0,
                variant="certified_marginal_master_deterministic",
            )
        self.assertTrue(seen)
        self.assertTrue(all(deadline is None for deadline, _model in seen))
        self.assertTrue(all(isinstance(model,
                                       capital.PositionedCertificateObjective)
                            for _deadline, model in seen))

    def test_phase_correct_certificate_starts_after_committed_unit_phase(self):
        snap = _snap()
        snap.hour = 5
        plan = SimpleNamespace(cash_floor=0)
        starts = []
        original = router.joint_assign

        def capture(tasks, units, *args, **kwargs):
            starts.append([(unit.start, unit.start_hour) for unit in units])
            return original(tasks, units, *args, **kwargs)

        with mock.patch.object(router, "joint_assign", capture):
            capital.decide(
                snap, plan, [], [], unit_actions=None, deadline=0.0,
                variant="certified_marginal_phase_deterministic",
            )
        self.assertTrue(starts)
        self.assertTrue(all(all(start_hour == 6 for _pos, start_hour in crew)
                            for crew in starts))

    def test_phase_aligned_master_adds_current_hire_to_cash_reserve(self):
        snap = _snap()
        snap.hour = 5
        plan = SimpleNamespace(cash_floor=100)
        reserves = []
        original = router.joint_assign

        def capture(*args, **kwargs):
            model = kwargs.get("bundle_model")
            reserves.append(model.reserve)
            return original(*args, **kwargs)

        with mock.patch.object(router, "joint_assign", capture):
            capital.decide(
                snap, plan, [], [], unit_actions=None, deadline=0.0,
                variant="phase_aligned_certificate_deterministic",
            )
        self.assertTrue(reserves)
        self.assertEqual(min(reserves), 100)
        self.assertGreater(max(reserves), 100)

    def test_crew_reserve_arms_share_physical_certificate_not_cash_verdict(self):
        snap = _snap(money=500, empty=8)
        melon = Task(
            (0, 0), [["PLANT", "MELON"], ["WATER"]], value=9999,
            kind="CAPITAL_CROP", cash_cost=econ.CROPS["MELON"]["seed"],
            order_key=("BUY_SEED", "MELON"),
        )
        shared = {}
        low = capital.PositionedCertificateObjective(
            snap, [melon], [], reserve=0, phase_aligned=True,
            certificate_cache=shared,
        )
        high = capital.PositionedCertificateObjective(
            snap, [melon], [], reserve=1000, phase_aligned=True,
            certificate_cache=shared,
        )
        self.assertGreater(low.score([melon]), float("-inf"))
        self.assertEqual(low.certificate_evaluations, 1)
        self.assertEqual(high.score([melon]), float("-inf"))
        self.assertEqual(high.certificate_evaluations, 0)

    def test_observable_asset_increase_replans_once_but_placement_does_not(self):
        snap = _snap()
        snap.seat = 0
        agent._ASSET_TOTALS.clear()
        with mock.patch.object(agent.tasks, "reset") as reset:
            agent._reset_for_new_assets(snap)
            self.assertEqual(reset.call_count, 0)
            snap.step = 1
            snap.hour = 1
            snap.seeds = {"WHEAT": 1}
            agent._reset_for_new_assets(snap)
            self.assertEqual(reset.call_count, 1)
            # PLANT conserves seed + standing crop capital and must not thrash
            # the day route a second time.
            snap.step = 2
            snap.hour = 2
            snap.seeds = {"WHEAT": 0}
            snap.me.crops[(0, 0)] = {"crop": "WHEAT"}
            agent._reset_for_new_assets(snap)
            self.assertEqual(reset.call_count, 1)

    def test_productive_shed_layout_preserves_counts_and_prioritizes_service(self):
        snap = _snap(day=0, money=100000, empty=25)
        # The generic fixture marks unlisted cells LOCKED; the real unlocked
        # NW access tile is an ordinary empty farm cell.
        snap.me.tiles[4][4] = None
        positioned = {
            "SHEEP": ((0, 0),),
            "WHEAT": ((1, 0), (2, 0)),
        }
        layouts = list(capital._productive_shed_layouts(
            snap, positioned,
            [["BUY_ANIMAL", "SHEEP", 1],
             ["BUY_SEED", "WHEAT", 2]],
        ))
        self.assertEqual(len(layouts), 1)
        self.assertEqual({item: len(positions)
                          for item, positions in layouts[0].items()},
                         {"SHEEP": 1, "WHEAT": 2})
        self.assertIn((4, 4), layouts[0]["SHEEP"])
        self.assertGreater(
            capital._service_operation_load(snap, "SHEEP"),
            capital._service_operation_load(snap, "WHEAT"),
        )

    def test_productive_shed_layout_never_enters_fourth_quadrant(self):
        snap = _snap(day=5, money=100000, empty=25)
        snap.me.unlocked = ["NW", "NE", "SW"]
        for x, y in ((4, 4), (5, 4), (4, 5)):
            snap.me.tiles[y][x] = None
        positioned = {"SHEEP": ((0, 0), (1, 0), (2, 0))}
        layouts = list(capital._productive_shed_layouts(
            snap, positioned, [["BUY_ANIMAL", "SHEEP", 3]],
        ))
        self.assertTrue(layouts)
        self.assertTrue(all(
            (5, 5) not in {pos for positions in layout.values()
                           for pos in positions}
            for layout in layouts
        ))

    def test_productive_shed_relocation_flag_is_explicit(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (2, [["BUY_ANIMAL", "SHEEP", 1]], [])
        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = capital.decide(
                snap, plan, [], [],
                variant=(
                    "crew_conditioned_positioned_scenario_late_land_"
                    "challenger_deterministic"
                ),
                productive_shed_relocation=True,
            )
        self.assertEqual(got, expected)
        self.assertTrue(
            decide_crew.call_args.kwargs["productive_shed_relocation"]
        )

    def test_service_cluster_layout_uses_only_route_equations(self):
        snap = _snap(day=0, money=100000, empty=25)
        positioned = {
            "COW": ((0, 0), (4, 0)),
            "SHEEP": ((0, 4), (3, 0)),
            "WHEAT": ((1, 0), (2, 0)),
        }
        assets = [
            ["BUY_ANIMAL", "COW", 2],
            ["BUY_ANIMAL", "SHEEP", 2],
            ["BUY_SEED", "WHEAT", 2],
        ]
        layouts = list(capital._service_cluster_layouts(
            snap, positioned, assets,
        ))
        self.assertTrue(layouts)
        layout = min(
            layouts,
            key=lambda candidate: capital._service_route_signature(
                snap, {item: positions for item, positions in candidate.items()
                       if item in econ.ANIMALS},
            ),
        )
        self.assertEqual(
            {item: len(positions) for item, positions in layout.items()},
            {item: len(positions) for item, positions in positioned.items()},
        )
        before = capital._service_route_signature(
            snap, {item: positions for item, positions in positioned.items()
                   if item in econ.ANIMALS},
        )
        after = capital._service_route_signature(
            snap, {item: positions for item, positions in layout.items()
                   if item in econ.ANIMALS},
        )
        self.assertLess(after[:4], before[:4])
        animal_positions = {
            pos for item, positions in layout.items()
            if item in econ.ANIMALS for pos in positions
        }
        reached = {min(animal_positions)}
        while True:
            expanded = reached | {
                pos for pos in animal_positions
                if any(abs(pos[0] - other[0]) + abs(pos[1] - other[1]) == 1
                       for other in reached)
            }
            if expanded == reached:
                break
            reached = expanded
        self.assertEqual(reached, animal_positions)

    def test_service_cluster_keeps_certified_shed_animal_fixed(self):
        snap = _snap(day=0, money=100000, empty=25)
        snap.me.tiles[4][4] = None
        snap.allow_productive_shed_tiles = True
        positioned = {
            "COW": ((4, 4), (0, 0)),
            "WHEAT": ((1, 0),),
        }
        layouts = list(capital._service_cluster_layouts(
            snap, positioned,
            [["BUY_ANIMAL", "COW", 2], ["BUY_SEED", "WHEAT", 1]],
        ))
        self.assertTrue(layouts)
        self.assertTrue(all((4, 4) in layout["COW"] for layout in layouts))

    def test_service_cluster_can_select_public_shed_cell_for_animal(self):
        snap = _snap(day=0, money=100000, empty=25)
        snap.me.tiles[4][4] = None
        snap.allow_productive_shed_tiles = True
        positioned = {
            "COW": ((0, 0),),
            "WHEAT": ((1, 0), (2, 0)),
        }
        layouts = list(capital._service_cluster_layouts(
            snap, positioned,
            [["BUY_ANIMAL", "COW", 1], ["BUY_SEED", "WHEAT", 2]],
        ))
        self.assertTrue(any((4, 4) in layout["COW"] for layout in layouts))

    def test_service_cluster_layout_never_uses_fourth_quadrant(self):
        snap = _snap(day=0, money=100000, empty=25)
        snap.me.unlocked = ["NW", "NE", "SW"]
        for x, y in ((5, 0), (6, 0), (0, 5), (0, 6)):
            snap.me.tiles[y][x] = None
        positioned = {
            "COW": ((0, 0), (5, 0)),
            "SHEEP": ((0, 5), (4, 0)),
        }
        layouts = list(capital._service_cluster_layouts(
            snap, positioned,
            [["BUY_ANIMAL", "COW", 2],
             ["BUY_ANIMAL", "SHEEP", 2]],
        ))
        self.assertTrue(layouts)
        self.assertTrue(all(
            all(capital.paths.quadrant_of(*pos, snap.board) != "SE"
                for positions in layout.values() for pos in positions)
            for layout in layouts
        ))

    def test_service_cluster_layout_keeps_paid_land_productive(self):
        snap = _snap(day=0, money=100000, empty=25)
        positioned = {
            "COW": ((0, 0),),
            "WHEAT": ((5, 0),),
        }
        layouts = list(capital._service_cluster_layouts(
            snap, positioned,
            [["BUY_LAND"], ["BUY_ANIMAL", "COW", 1],
             ["BUY_SEED", "WHEAT", 1]],
        ))
        self.assertTrue(layouts)
        self.assertTrue(all(
            any(capital.paths.quadrant_of(*pos, snap.board) == "NE"
                for positions in layout.values() for pos in positions)
            for layout in layouts
        ))

    def test_route_profile_requires_strict_dated_pareto_gain(self):
        baseline = {1: (2, 30), 2: (3, 50)}
        self.assertTrue(capital._route_profile_dominates(
            baseline, {1: (2, 29), 2: (3, 50)},
        ))
        self.assertFalse(capital._route_profile_dominates(
            baseline, dict(baseline),
        ))
        self.assertFalse(capital._route_profile_dominates(
            baseline, {1: (1, 20), 2: (3, 51)},
        ))

    def test_service_layout_lifecycle_accepts_paid_current_detour(self):
        baseline_current = (4, 86, 23)
        candidate_current = (4, 88, 23)
        baseline_future = {11: (4, 40), 12: (4, 40)}
        candidate_future = {11: (4, 38), 12: (4, 38)}
        self.assertTrue(capital._service_layout_lifecycle_dominates(
            baseline_current, candidate_current,
            baseline_future, candidate_future,
        ))
        self.assertFalse(capital._service_layout_lifecycle_dominates(
            baseline_current, candidate_current,
            baseline_future, {11: (4, 39), 12: (4, 40)},
        ))
        # An aggregate saving cannot hide a worse named future service day.
        self.assertFalse(capital._service_layout_lifecycle_dominates(
            baseline_current, candidate_current,
            baseline_future, {11: (4, 41), 12: (4, 35)},
        ))
        self.assertFalse(capital._service_layout_lifecycle_dominates(
            baseline_current, (4, 87, 24),
            baseline_future, candidate_future,
        ))

    def test_positioned_full_service_profile_is_phase_and_pickup_exact(self):
        """Future layout proof starts tomorrow and charges one WHEAT pickup."""
        snap = _snap(day=0, money=100000, empty=25)
        positioned = {
            "COW": ((4, 4),),
            "WHEAT": ((3, 4),),
        }

        profile = capital._positioned_full_service_route_profile(
            snap, positioned,
        )

        self.assertIsNotNone(profile)
        self.assertNotIn(snap.day, profile)
        # Day 1 is one closed shared route: nine physical route/operation
        # actions plus one aggregated PICKUP of WHEAT for the cow.
        self.assertEqual(profile[snap.day + 1], (1, 10))

    def test_pickup_aware_future_profile_rejects_old_false_pareto(self):
        """A clustered shape cannot hide a worse named future service day."""
        snap = _snap(day=0, money=100000, empty=25)
        baseline = capital._positioned_full_service_route_profile(snap, {
            "COW": ((0, 4), (4, 0)),
            "WHEAT": ((0, 0), (2, 2), (4, 3)),
        })
        candidate = capital._positioned_full_service_route_profile(snap, {
            "COW": ((4, 0), (4, 4)),
            "WHEAT": ((0, 0), (0, 4), (1, 3)),
        })

        self.assertEqual(baseline[snap.day + 1], (3, 52))
        self.assertEqual(candidate[snap.day + 1], (3, 54))
        self.assertFalse(capital._route_profile_dominates(
            baseline, candidate,
        ))
        self.assertFalse(capital._service_layout_lifecycle_dominates(
            (3, 50, 20), (3, 50, 20), baseline, candidate,
        ))

    def test_one_shot_release_anchor_comes_from_public_crop_calendar(self):
        snap = _snap(day=2, money=3000, empty=25)
        wheat = {
            "kind": "PLANT", "crop": "WHEAT", "planted_day": 0,
            "yield_units": 0,
        }
        melon = {
            "kind": "PLANT", "crop": "MELON", "planted_day": 0,
            "yield_units": 0,
        }
        for pos, tile in (((0, 0), wheat), ((1, 0), melon)):
            snap.me.tiles[pos[1]][pos[0]] = tile
            snap.me.crops[pos] = tile
            if pos in snap.me.empty:
                snap.me.empty.remove(pos)
        anchors = capital._standing_crop_release_anchors(snap)
        wheat_day = value._crop_event_days(
            wheat, "WHEAT", snap.day,
        )[0] + 1
        melon_day = value._crop_event_days(
            melon, "MELON", snap.day,
        )[0] + 1
        self.assertIn(("WHEAT", (0, 0)), anchors[wheat_day])
        self.assertIn(("MELON", (1, 0)), anchors[melon_day])
        self.assertLess(wheat_day, melon_day)

    def test_land_turnover_challenger_uses_same_robust_value_and_keeps_work(self):
        live_cashflow = __import__(
            "whitebox", fromlist=["cashflow"],
        ).cashflow
        snap = _snap(day=2, money=5000, empty=25)
        snap.seat = 0
        capital._clear_land_turnover_exercises(snap.seat)
        self.addCleanup(capital._clear_land_turnover_exercises, snap.seat)
        crop = {
            "kind": "PLANT", "crop": "WHEAT", "planted_day": 0,
            "yield_units": 0,
        }
        snap.me.tiles[0][0] = crop
        snap.me.crops[(0, 0)] = crop
        snap.me.empty.remove((0, 0))
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        row = {
            "hires": 2,
            "hire_cost": 2.0,
            "service_reserve": 0.0,
            "assets": [["BUY_LAND"], ["BUY_SEED", "MELON", 1]],
            "fixed": [],
            "positions_by_item": {"MELON": ((5, 0),)},
            "selected_counts": {"MELON": 1},
            "proposed_counts": {"MELON": 1},
            "selected_ordinary_tasks": (),
            "score": 100.0,
        }
        standing = cashflow.Certificate({})
        standing.feasible = True
        standing.operating_cost = 12.0
        standing.cash_by_day = {day: 5000.0 for day in range(3, 30)}
        first = cashflow.Certificate({"MELON": 1}, 1000)
        first.feasible = False
        first.reason = "bridge_cash"
        first.operating_cost = 14.0
        first.upfront_spend = 1080.0
        first.final_cash = 5100.0
        first.outputs_by_day = {12: {"MELON": 1}}
        full = cashflow.Certificate({"MELON": 1}, 1000)
        full.feasible = False
        full.reason = "bridge_cash"
        full.operating_cost = 15.0
        full.upfront_spend = 1080.0
        full.final_cash = 5200.0
        full.outputs_by_day = {12: {"MELON": 2}}
        release_day = value._crop_event_days(
            crop, "WHEAT", snap.day,
        )[0] + 1
        option = __import__(
            "whitebox.stackelberg", fromlist=["Reinvestment"]
        ).Reinvestment(
            name="WAIT_RELEASE_BUY_STRAWBERRY_1",
            cost=100.0,
            outputs=((release_day + 4, (("STRAWBERRY", 3),)),),
            purchase_day=release_day + 1,
            order=("BUY_SEED", "STRAWBERRY", 1),
            positions_by_item=(("STRAWBERRY", ((0, 0),)),),
        )
        context = {
            "responses": (__import__(
                "whitebox.stackelberg", fromlist=["Response"]
            ).Response("NO_RESPONSE"),),
            "baseline_robust": 0.0,
            "opponent_baseline": {},
            "own_baseline": {},
            "drains": {},
            "include_own_standing_book": False,
        }
        with mock.patch.object(
                capital, "_current_positioned_route_profile",
                return_value=(2, 20, 10)) as route, mock.patch(
                    "whitebox.stackelberg._standing_cash_terms",
                    return_value=({}, {})), mock.patch.object(
                    live_cashflow, "certify_shared",
                    side_effect=[standing, first, full]), mock.patch(
                    "whitebox.stackelberg.make_context",
                    return_value=context), mock.patch(
                    "whitebox.stackelberg.feasible_deferred_capital",
                    return_value=(__import__(
                        "whitebox.stackelberg",
                        fromlist=["Reinvestment"]
                    ).Reinvestment("NO_DEFERRED_CAPITAL"), option)), \
                mock.patch.object(
                    capital, "_robust_schedule_value",
                    return_value=20.0):
            winner = capital._land_turnover_option_challenger(
                snap, plan, [], row,
            )
        self.assertTrue(winner["land_turnover_option"])
        self.assertEqual(winner["assets"], [])
        self.assertEqual(
            winner["land_turnover_future_order"],
            ("BUY_SEED", "STRAWBERRY", 1),
        )
        self.assertEqual(winner["score"], 18.0)
        self.assertIn(
            (snap.seat, len(snap.me.unlocked)),
            capital._LAND_TURNOVER_EXERCISED,
        )
        waiting = capital._land_turnover_option_challenger(
            snap, plan, [], row,
        )
        self.assertEqual(waiting["assets"], [])
        self.assertTrue(waiting["land_turnover_commitment_wait"])
        self.assertEqual(
            capital._LAND_TURNOVER_COMMITMENTS[snap.seat][
                "eligible_day"
            ],
            winner["land_turnover_purchase_day"],
        )
        route.assert_called_once()

    def test_mature_land_turnover_commitment_reopens_live_land_challenger(self):
        snap = _snap(day=6, money=5000, empty=25)
        snap.seat = 0
        capital._clear_land_turnover_exercises(snap.seat)
        self.addCleanup(capital._clear_land_turnover_exercises, snap.seat)
        capital._LAND_TURNOVER_EXERCISED.add((snap.seat, 1))
        capital._LAND_TURNOVER_COMMITMENTS[snap.seat] = {
            "created_day": 2,
            "eligible_day": 4,
            "unlocked_count": 1,
        }
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        row = {
            "hires": 0,
            "assets": [],
            "fixed": [],
            "positions_by_item": {},
            "selected_counts": {},
            "selected_ordinary_tasks": (),
            "score": 0.0,
        }
        matured = dict(row)
        matured.update({
            "assets": [["BUY_SEED", "WHEAT", 1], ["BUY_LAND"]],
            "late_land_crop": "WHEAT",
        })
        with mock.patch.object(
                capital, "_late_crop_land_challenger",
                return_value=matured) as reopen:
            got = capital._land_turnover_option_challenger(
                snap, plan, [], row,
            )
        self.assertIs(got, matured)
        self.assertTrue(got["land_turnover_commitment_executed"])
        self.assertNotIn(
            snap.seat, capital._LAND_TURNOVER_COMMITMENTS,
        )
        self.assertTrue(reopen.call_args.kwargs["allow_initial_expansion"])

    def test_land_turnover_never_defers_a_feasible_immediate_bundle(self):
        live_cashflow = __import__(
            "whitebox", fromlist=["cashflow"],
        ).cashflow
        snap = _snap(day=2, money=5000, empty=25)
        snap.seat = 0
        capital._clear_land_turnover_exercises(snap.seat)
        self.addCleanup(capital._clear_land_turnover_exercises, snap.seat)
        crop = {
            "kind": "PLANT", "crop": "WHEAT", "planted_day": 0,
            "yield_units": 0,
        }
        snap.me.tiles[0][0] = crop
        snap.me.crops[(0, 0)] = crop
        snap.me.empty.remove((0, 0))
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        row = {
            "hires": 0,
            "hire_cost": 0.0,
            "service_reserve": 0.0,
            "assets": [["BUY_LAND"], ["BUY_SEED", "WHEAT", 1]],
            "fixed": [],
            "positions_by_item": {"WHEAT": ((5, 0),)},
            "selected_counts": {"WHEAT": 1},
            "selected_ordinary_tasks": (),
            "score": 100.0,
        }
        feasible = cashflow.Certificate({"WHEAT": 1}, 1000)
        feasible.feasible = True
        feasible.outputs_by_day = {4: {"WHEAT": 1}}
        standing = cashflow.Certificate({})
        standing.feasible = True
        standing.cash_by_day = {day: 5000.0 for day in range(3, 30)}

        with mock.patch.object(
                capital, "_current_positioned_route_profile",
                return_value=(1, 5, 5)), mock.patch(
                    "whitebox.stackelberg._standing_cash_terms",
                    return_value=({}, {})), mock.patch.object(
                    live_cashflow, "certify_shared",
                    side_effect=[standing, feasible, feasible]), mock.patch(
                    "whitebox.stackelberg.make_context",
                    return_value={"responses": ()}), mock.patch.object(
                    capital, "_robust_schedule_value", return_value=1.0):
            got = capital._land_turnover_option_challenger(
                snap, plan, [], row,
            )
        self.assertIs(got, row)
        self.assertNotIn(
            (snap.seat, len(snap.me.unlocked)),
            capital._LAND_TURNOVER_EXERCISED,
        )

    def test_land_turnover_option_flag_is_explicit(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (2, [["BUY_ANIMAL", "SHEEP", 1]], [])
        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = capital.decide(
                snap, plan, [], [],
                variant=(
                    "crew_conditioned_positioned_scenario_late_land_"
                    "challenger_deterministic"
                ),
                land_turnover_option=True,
            )
        self.assertEqual(got, expected)
        self.assertTrue(
            decide_crew.call_args.kwargs["land_turnover_option"]
        )

    def test_late_land_routes_the_selected_robust_ray_before_repricing(self):
        """A positive land bundle cannot disappear as zero new columns."""
        live_stackelberg = __import__(
            "whitebox.stackelberg", fromlist=["certify_unified"],
        )
        snap = _snap(day=11, money=100000, empty=20)
        snap.hour = 0
        snap.me.unlocked = ["NW", "NE"]
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        row = {
            "hires": 0,
            "hire_cost": 0.0,
            "service_reserve": 0.0,
            "assets": [],
            "fixed": [],
            "positions_by_item": {},
            "selected_counts": {},
            "selected_ordinary_tasks": (),
            "score": 0.0,
        }
        seen_mandatory = []

        def certificate(_snap, counts, _slots, **kwargs):
            cert = cashflow.Certificate(
                counts, kwargs.get("land_cost", 0.0),
            )
            cert.paired_value = 10.0 if counts else 0.0
            return cert

        def select_mandatory(all_tasks, _units, *_args, **_kwargs):
            selected = [task for task in all_tasks if task.mandatory]
            seen_mandatory.append(tuple(
                task.mandatory for task in all_tasks
                if task.kind == "CAPITAL_CROP"
            ))
            return {0: selected}, [
                task for task in all_tasks if task not in selected
            ]

        with mock.patch.object(
                econ, "CROPS", {"WHEAT": econ.CROPS["WHEAT"]}), \
                mock.patch.object(
                    econ, "SEED_DEADLINE",
                    {"WHEAT": econ.SEED_DEADLINE["WHEAT"]}), \
                mock.patch.object(
                    cashflow, "_available_slots", return_value=[(0, 5)]), \
                mock.patch.object(
                    live_stackelberg, "make_context",
                    return_value={"responses": ()}), \
                mock.patch.object(
                    live_stackelberg, "certify_unified",
                    side_effect=certificate), \
                mock.patch.object(
                    capital.router, "joint_assign",
                    side_effect=select_mandatory), \
                mock.patch.object(
                    value, "planned_shed_stock", return_value={}):
            winner = capital._late_crop_land_challenger(
                snap, plan, [], row,
            )

        self.assertEqual(winner["late_land_crop"], "WHEAT")
        self.assertEqual(winner["late_land_quantity"], 1)
        self.assertIn(["BUY_LAND"], winner["assets"])
        self.assertEqual(seen_mandatory, [(True,)])

    def test_service_layout_current_route_preserves_optional_priority(self):
        snap = _snap(day=14, money=100000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        pos = tuple(snap.me.empty[0])
        column = Task(
            pos, [["BUILD_PASTURE"], ["PLACE", "COW"]],
            {"COW": 1}, value=100, mandatory=False,
            kind="CAPITAL_ANIMAL",
        )
        row = {
            "hires": 0, "hire_cost": 0.0, "service_reserve": 0.0,
            "assets": [["BUY_ANIMAL", "COW", 1]], "fixed": [],
            "selected_ordinary_tasks": (),
        }
        seen = []

        def select(all_tasks, units, *_args, **_kwargs):
            seen.append(tuple(task.mandatory for task in all_tasks))
            return {
                unit.idx: (list(all_tasks) if index == 0 else [])
                for index, unit in enumerate(units)
            }, []

        with mock.patch.object(
                capital, "capital_tasks",
                return_value=([column], {"COW": 1})), mock.patch.object(
                capital.router, "joint_assign", side_effect=select), \
                mock.patch.object(
                    value, "planned_shed_stock", return_value={}):
            profile = capital._current_positioned_route_profile(
                snap, plan, [], row, {"COW": (pos,)},
            )

        self.assertIsNotNone(profile)
        self.assertEqual(seen, [(False,)])
        self.assertFalse(column.mandatory)

    def test_bounded_late_land_frontier_uses_feasible_regime_boundaries(self):
        """Online land search cannot return to per-quantity certificates."""
        live_stackelberg = __import__(
            "whitebox.stackelberg", fromlist=["certify_unified"],
        )
        snap = _snap(day=11, money=100000, empty=20)
        snap.hour = 0
        snap.me.unlocked = ["NW", "NE"]
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        row = {
            "hires": 0,
            "hire_cost": 0.0,
            "service_reserve": 0.0,
            "assets": [],
            "fixed": [],
            "positions_by_item": {},
            "selected_counts": {},
            "selected_ordinary_tasks": (),
            "score": 0.0,
        }
        calls = []

        def certificate(_snap, counts, _slots, **kwargs):
            calls.append((dict(counts), dict(kwargs)))
            cert = cashflow.Certificate(
                counts, kwargs.get("land_cost", 0.0),
            )
            cert.paired_value = 10.0 * sum(counts.values())
            return cert

        def select_all(all_tasks, _units, *_args, **_kwargs):
            return {0: list(all_tasks)}, []

        slots = [(x, y) for y in range(5, 10) for x in range(5)]
        with mock.patch.object(
                cashflow, "_available_slots", return_value=slots), \
                mock.patch.object(
                    live_stackelberg, "make_context",
                    return_value={"responses": ()}), \
                mock.patch.object(
                    live_stackelberg, "certify_unified",
                    side_effect=certificate), \
                mock.patch.object(
                    capital.router, "joint_assign",
                    side_effect=select_all), \
                mock.patch.object(
                    value, "planned_shed_stock", return_value={}):
            winner = capital._late_crop_land_challenger(
                snap, plan, [], row,
                bounded_quantity_frontier=True,
            )

        # A single feasible regime retains only its structural boundary arms;
        # it cannot return to all 25 integer quantities.
        self.assertLess(len(calls), 10 * len(econ.CROPS))
        evaluated = {
            next(iter(counts)) for counts, _kwargs in calls if counts
        }
        self.assertEqual(evaluated, set(econ.CROPS))
        self.assertTrue(all(
            kwargs.get("cash_context") is not None
            for _counts, kwargs in calls
        ))

    def test_bounded_late_land_frontier_keeps_profit_peak_predecessor(self):
        """A response discontinuity immediately before the screen peak lives."""
        live_stackelberg = __import__(
            "whitebox.stackelberg", fromlist=["certify_unified"],
        )
        snap = _snap(day=13, money=100000, empty=20)
        snap.hour = 0
        snap.me.unlocked = ["NW", "NE"]
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        row = {
            "hires": 0,
            "hire_cost": 0.0,
            "service_reserve": 0.0,
            "assets": [],
            "fixed": [],
            "positions_by_item": {},
            "selected_counts": {},
            "selected_ordinary_tasks": (),
            "score": 0.0,
        }
        unified_quantities = []

        def endpoint(_snap, counts, _slots, *_args, **_kwargs):
            quantity = sum(counts.values())
            if not 1 <= quantity <= 5:
                return None
            cert = cashflow.Certificate(counts, 2000.0)
            cert.final_cash = float(quantity)
            cert.outputs_by_day = {20: {"WHEAT": quantity}}
            return cert, 0.0

        def certificate(_snap, counts, _slots, **kwargs):
            quantity = sum(counts.values())
            if quantity:
                unified_quantities.append(quantity)
            cert = cashflow.Certificate(
                counts, kwargs.get("land_cost", 0.0),
            )
            cert.paired_value = 20.0 if quantity == 4 else (
                -10.0 if quantity else 0.0
            )
            return cert

        def select_all(all_tasks, _units, *_args, **_kwargs):
            return {0: list(all_tasks)}, []

        slots = [(x, y) for y in range(5, 10) for x in range(5)]
        with mock.patch.object(
                econ, "CROPS", {"WHEAT": econ.CROPS["WHEAT"]}), \
                mock.patch.object(
                    econ, "SEED_DEADLINE",
                    {"WHEAT": econ.SEED_DEADLINE["WHEAT"]}), \
                mock.patch.object(
                    cashflow, "_available_slots", return_value=slots), \
                mock.patch.object(
                    live_stackelberg, "_endpoint", side_effect=endpoint), \
                mock.patch.object(
                    live_stackelberg, "_standalone_schedule_revenue",
                    side_effect=lambda _snap, outputs: float(
                        outputs[20]["WHEAT"]
                    )), \
                mock.patch.object(
                    live_stackelberg, "make_context",
                    return_value={"responses": ()}), \
                mock.patch.object(
                    live_stackelberg, "certify_unified",
                    side_effect=certificate), \
                mock.patch.object(
                    capital.router, "joint_assign",
                    side_effect=select_all), \
                mock.patch.object(
                    value, "planned_shed_stock", return_value={}):
            winner = capital._late_crop_land_challenger(
                snap, plan, [], row,
                bounded_quantity_frontier=True,
            )

        self.assertEqual(unified_quantities[:3], [1, 4, 5])
        self.assertEqual(winner["late_land_quantity"], 4)
        self.assertIn(["BUY_LAND"], winner["assets"])

    def test_service_cluster_layout_flag_is_explicit(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (2, [["BUY_ANIMAL", "SHEEP", 1]], [])
        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = capital.decide(
                snap, plan, [], [],
                variant=(
                    "crew_conditioned_positioned_scenario_late_land_"
                    "challenger_deterministic"
                ),
                service_cluster_layout=True,
            )
        self.assertEqual(got, expected)
        self.assertTrue(
            decide_crew.call_args.kwargs["service_cluster_layout"]
        )

    def test_joint_standing_capital_wires_one_transparent_game(self):
        live_capital = __import__("whitebox", fromlist=["capital"]).capital
        live_cashflow = __import__("whitebox", fromlist=["cashflow"]).cashflow
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        snap.me.crops[(0, 0)] = {"crop": "STRAWBERRY"}
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        proposal = live_cashflow.Certificate({})
        proposal.positions_by_item = {}

        with mock.patch(
                "whitebox.stackelberg.make_context",
                return_value={"responses": ()}) as make_context, \
                mock.patch.object(
                    live_cashflow, "invent_paired_proposal",
                    return_value=([], proposal)) as invent:
            rows = live_capital.crew_conditioned_decision_curve(
                snap, plan, [], [], joint_standing_capital=True,
            )

        self.assertTrue(rows)
        context = make_context.call_args.kwargs
        self.assertTrue(context["full_response_continuation"])
        self.assertTrue(context["include_own_standing_book"])
        self.assertEqual(
            set(context["candidate_response_products"]),
            set(econ.CROPS) | {
                str(spec["product"]) for spec in econ.ANIMALS.values()
            },
        )
        self.assertTrue(invent.call_args_list)
        for call in invent.call_args_list:
            self.assertTrue(call.kwargs["joint_farm_prefix"])
            self.assertTrue(call.kwargs["recertify_stackelberg_arms"])
            self.assertTrue(call.kwargs["full_service_continuation"])

    def test_joint_standing_capital_leaves_empty_opening_equation_unchanged(self):
        live_capital = __import__("whitebox", fromlist=["capital"]).capital
        live_cashflow = __import__("whitebox", fromlist=["cashflow"]).cashflow
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        proposal = live_cashflow.Certificate({})
        proposal.positions_by_item = {}

        with mock.patch(
                "whitebox.stackelberg.make_context") as make_context, \
                mock.patch.object(
                    live_cashflow, "invent_paired_proposal",
                    return_value=([], proposal)) as invent:
            rows = live_capital.crew_conditioned_decision_curve(
                snap, plan, [], [], joint_standing_capital=True,
            )

        self.assertTrue(rows)
        make_context.assert_not_called()
        self.assertTrue(invent.call_args_list)
        for call in invent.call_args_list:
            self.assertFalse(call.kwargs["joint_farm_prefix"])
            self.assertFalse(call.kwargs["recertify_stackelberg_arms"])
            self.assertFalse(call.kwargs["full_service_continuation"])

    def test_joint_standing_capital_flag_is_explicit(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (0, [], [])
        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = capital.decide(
                snap, plan, [], [],
                variant=(
                    "crew_conditioned_positioned_scenario_late_land_"
                    "challenger_deterministic"
                ),
                joint_standing_capital=True,
            )
        self.assertEqual(got, expected)
        self.assertTrue(
            decide_crew.call_args.kwargs["joint_standing_capital"]
        )

    def test_land_frontier_certificate_flag_is_explicit_and_opt_in(self):
        """The repair is isolated: legacy calls keep it disabled."""
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        expected = (0, [], [])
        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = capital.decide(
                snap, plan, [], [],
                variant=(
                    "crew_conditioned_positioned_scenario_late_land_"
                    "challenger_deterministic"
                ),
            )
        self.assertEqual(got, expected)
        self.assertFalse(
            decide_crew.call_args.kwargs["land_frontier_certificate"]
        )

        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = capital.decide(
                snap, plan, [], [],
                variant=(
                    "crew_conditioned_positioned_scenario_late_land_"
                    "challenger_deterministic"
                ),
                land_frontier_certificate=True,
            )
        self.assertEqual(got, expected)
        self.assertTrue(
            decide_crew.call_args.kwargs["land_frontier_certificate"]
        )

    def test_single_quadrant_class_gate_is_explicit_and_land_scoped(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        variant = (
            "crew_conditioned_positioned_scenario_late_land_"
            "challenger_deterministic"
        )
        expected = (0, [], [])

        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = capital.decide(snap, plan, [], [], variant=variant)
        self.assertEqual(got, expected)
        self.assertFalse(decide_crew.call_args.kwargs[
            "same_asset_class_composition_exchange"
        ])

        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = capital.decide(
                snap, plan, [], [], variant=variant,
                single_quadrant_asset_class_exchange=True,
            )
        self.assertEqual(got, expected)
        self.assertTrue(decide_crew.call_args.kwargs[
            "same_asset_class_composition_exchange"
        ])

        snap.me.unlocked = ["NW", "NE"]
        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            got = capital.decide(
                snap, plan, [], [], variant=variant,
                single_quadrant_asset_class_exchange=True,
            )
        self.assertEqual(got, expected)
        self.assertFalse(decide_crew.call_args.kwargs[
            "same_asset_class_composition_exchange"
        ])

    def test_variant_agent_forwards_single_quadrant_class_gate(self):
        with mock.patch.object(agent, "act", return_value={}) as act:
            agent.variant_agent(
                {}, single_quadrant_asset_class_exchange=True,
            )
        self.assertTrue(act.call_args.kwargs[
            "single_quadrant_asset_class_exchange"
        ])

    def test_opening_asset_class_gate_is_step_scoped(self):
        snap = _snap(money=3000, empty=20)
        snap.hour = 0
        plan = SimpleNamespace(cash_floor=0, service_cash_floor=0)
        variant = (
            "crew_conditioned_positioned_scenario_late_land_"
            "challenger_deterministic"
        )
        expected = (0, [], [])
        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            capital.decide(
                snap, plan, [], [], variant=variant,
                opening_asset_class_exchange=True,
            )
        self.assertTrue(decide_crew.call_args.kwargs[
            "same_asset_class_composition_exchange"
        ])
        snap.step = 24
        with mock.patch.object(
                capital, "_decide_crew_conditioned",
                return_value=expected) as decide_crew:
            capital.decide(
                snap, plan, [], [], variant=variant,
                opening_asset_class_exchange=True,
            )
        self.assertFalse(decide_crew.call_args.kwargs[
            "same_asset_class_composition_exchange"
        ])


if __name__ == "__main__":
    unittest.main()
