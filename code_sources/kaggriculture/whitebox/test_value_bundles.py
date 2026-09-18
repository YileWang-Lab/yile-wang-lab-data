"""Equation tests for nonlinear ordinary-task market clearing."""
import unittest
from collections import Counter
from types import SimpleNamespace

from route import router
from route.router import Task, Unit
from whitebox import cashflow, econ, value


def _animal(kind, **changes):
    tile = {
        "kind": econ.ANIMALS[kind]["structure"], "animal": kind,
        "placed_day": 0, "yield_units": 0, "consecutive_unfed": 0,
        "fed_today": False, "cared_today": False,
        "fertilizer_available": False, "pending_care_bonus": 0,
    }
    tile.update(changes)
    return tile


def _snap(day=10):
    tiles = [[None for _x in range(10)] for _y in range(10)]
    me = SimpleNamespace(tiles=tiles, animals={}, crops={})
    opp = SimpleNamespace(animals={}, crops={})
    return SimpleNamespace(
        day=day, step=day * 24, me=me, opp=opp,
        market_inv={item: econ.MARKET_I0 for item in econ.SELLABLE},
    )


class OrdinaryTaskBundleTests(unittest.TestCase):
    def test_paid_fertilizer_target_is_exact_public_positive_surplus(self):
        snap = _snap(day=9)
        crop = {
            "crop": "STRAWBERRY", "planted_day": 0,
            "watered_today": False, "fertilized_until_day": -1,
            "yield_units": 0,
        }
        snap.me.crops[(0, 0)] = crop
        snap.me.tiles[0][0] = crop
        snap.me.money = 1000.0
        snap.shed = {}
        snap.shed_room = econ.SHED_CAPACITY
        snap.inventories = [{}]
        snap.carried = lambda: {}
        plan = SimpleNamespace(
            phase="mid", wheat_needed=0, cash_floor=0.0,
            service_cash_floor=0.0,
        )
        self.assertEqual(value.paid_fertilizer_target(snap, plan), 1)
        plan.cash_floor = snap.me.money
        self.assertEqual(value.paid_fertilizer_target(snap, plan), 0)

    def test_temporal_sale_transition_matches_engine_equation(self):
        for item in econ.SELLABLE:
            for inventory in (econ.MARKET_I0 - 11,
                              econ.MARKET_I0,
                              econ.MARKET_I0 + 37):
                for qty in (0, 1, 7, econ.SHED_CAPACITY):
                    self.assertEqual(
                        value._temporal_sale_result(item, qty, inventory),
                        cashflow._sale_result(item, qty, inventory),
                    )

    def test_dated_capital_schedules_conserve_rule_quantities(self):
        snap = _snap(day=4)
        strawberry = Task(
            (0, 0), [["PLANT", "STRAWBERRY"], ["WATER"]],
            value=value.plant_value(snap, "STRAWBERRY"),
            kind="CAPITAL_CROP",
        )
        cow = Task(
            (1, 0), [["BUILD_PASTURE"], ["PLACE", "COW"]],
            value=value.animal_placement_value(snap, "COW"),
            kind="CAPITAL_ANIMAL",
        )
        for task in (strawberry, cow):
            total = value.task_sale_outputs(snap, task)
            dated = value.task_sale_schedule(snap, task)
            collapsed = {}
            for (item, _day), qty in dated.items():
                collapsed[item] = collapsed.get(item, 0) + qty
            self.assertEqual(dict(total), collapsed)
            self.assertGreater(len(dated), 1)

    def test_temporal_bundle_carries_our_book_between_output_days(self):
        snap = _snap(day=4)
        task = Task((0, 0), [["PASS"]], value=1, kind="TEST")
        model = value.TemporalPairedTaskBundleObjective(snap, [task])
        schedule = Counter({("MILK", 8): 4, ("MILK", 10): 4})
        model.terms[id(task)] = (schedule, -137.0, frozenset(("MILK",)))
        model.initial_opponent["MILK"] = 0
        model.drain = {}
        first, after = cashflow._sale_result(
            "MILK", 4, snap.market_inv["MILK"],
        )
        second, _after = cashflow._sale_result("MILK", 4, after)
        self.assertEqual(model.score([task]), first + second - 137)

    def test_temporal_opponent_stock_is_conserved_across_phases(self):
        snap = _snap(day=4)
        task = Task((0, 0), [["PASS"]], value=0, kind="TEST")
        model = value.TemporalPairedTaskBundleObjective(snap, [task])
        model.initial_opponent["MILK"] = 3
        model.drain = {}
        schedule = ((8, 2), (10, 2))
        expected = float("inf")
        initial = snap.market_inv["MILK"]
        for first_opp in range(4):
            first = cashflow._paired_sale_exact(
                "MILK", 2, initial, first_opp,
            )
            _joint, after = cashflow._sale_result(
                "MILK", 2 + first_opp, initial,
            )
            for second_opp in range(3 - first_opp + 1):
                second = cashflow._paired_sale_exact(
                    "MILK", 2, after, second_opp,
                )
                expected = min(expected, first + second)
        self.assertEqual(model._item_value("MILK", schedule), expected)

    def test_temporal_selected_set_marginals_telescope(self):
        snap = _snap(day=4)
        tasks = [
            Task((x, 0), [["PLANT", "STRAWBERRY"], ["WATER"]],
                 value=value.plant_value(snap, "STRAWBERRY"),
                 kind="PLANT_CROP")
            for x in range(2)
        ]
        model = value.TemporalPairedTaskBundleObjective(snap, tasks)
        counts = model.counts()
        first = model.add_gain(tasks[0], counts)
        model.update_counts(counts, tasks[0])
        second = model.add_gain(tasks[1], counts)
        self.assertAlmostEqual(first + second, model.score(tasks))

    def test_paired_phase_value_is_worst_exact_simultaneous_quantity(self):
        snap = _snap()
        item, ours = "MILK", 17
        snap.opp.animals[(9, 9)] = _animal(
            "COW", yield_units=econ.SHED_CAPACITY,
        )
        inventory = snap.market_inv[item]
        exact = [cashflow._paired_sale_exact(
            item, ours, inventory, theirs,
        ) for theirs in range(econ.SHED_CAPACITY + 1)]
        self.assertAlmostEqual(
            value.paired_phase_sale_value(snap, item, ours), min(exact),
        )
        self.assertLess(min(exact), cashflow._sale_result(
            item, ours, inventory,
        )[0])

    def test_paired_phase_bundle_replaces_only_output_revenue(self):
        snap = _snap()
        snap.opp.animals[(9, 9)] = _animal("COW", yield_units=40)
        qty = 12
        old_revenue = value.sale_value(snap, "MILK", qty)
        task = Task(
            (0, 0), [["HARVEST"]], value=old_revenue - 137,
            kind="TEST",
        )
        model = value.TaskBundleObjective(
            snap, [task], paired_phase=True,
        )
        model.terms[id(task)] = ({"MILK": qty}, -137.0)
        expected = value.paired_phase_sale_value(snap, "MILK", qty) - 137
        self.assertEqual(model.score([task]), expected)
        self.assertEqual(model.residual(task), -137)
        self.assertGreater(expected, old_revenue - 137)

    def test_selected_quantity_marginal_changes_route_subset(self):
        snap = _snap()
        repeated_a = Task((0, 0), [["HARVEST"]], value=1.0, kind="TEST")
        repeated_b = Task((1, 0), [["HARVEST"]], value=1.0, kind="TEST")
        diverse = Task((0, 1), [["HARVEST"]], value=1.0, kind="TEST")
        tasks = [repeated_a, repeated_b, diverse]
        model = value.TaskBundleObjective(snap, tasks)
        milk_qty, wool_qty = 30, 15
        milk_value = model.revenue("MILK", milk_qty)
        wool_value = model.revenue("WOOL", wool_qty)
        repeated_a.value = repeated_b.value = milk_value
        diverse.value = wool_value
        model.terms[id(repeated_a)] = ({"MILK": milk_qty}, 0.0)
        model.terms[id(repeated_b)] = ({"MILK": milk_qty}, 0.0)
        model.terms[id(diverse)] = ({"WOOL": wool_qty}, 0.0)

        additive, _ = router.joint_assign(
            tasks, [Unit(0, (0, 0), 21)], refine=False,
        )
        bundled, _ = router.joint_assign(
            tasks, [Unit(0, (0, 0), 21)], refine=False,
            bundle_model=model,
        )
        self.assertEqual(additive[0], [repeated_a, repeated_b])
        self.assertEqual(bundled[0], [repeated_a, diverse])
        self.assertGreater(
            model.score(bundled[0]), model.score(additive[0]),
        )

    def test_swap_gain_equals_exact_selected_score_difference(self):
        snap = _snap()
        tasks = [Task((x, 0), [["PASS"]], value=1.0, kind="TEST")
                 for x in range(3)]
        model = value.TaskBundleObjective(snap, tasks)
        model.terms[id(tasks[0])] = ({"MILK": 20}, 3.0)
        model.terms[id(tasks[1])] = ({"MILK": 20}, -5.0)
        model.terms[id(tasks[2])] = ({"WOOL": 10}, 7.0)
        selected = tasks[:2]
        counts = model.counts(selected)
        self.assertAlmostEqual(
            model.swap_gain(tasks[2], tasks[1], counts),
            model.score([tasks[0], tasks[2]]) - model.score(selected),
        )

    def test_capital_and_ordinary_output_share_one_book(self):
        snap = _snap(day=4)
        cow = _animal("COW", yield_units=4)
        snap.me.tiles[0][0] = cow
        ordinary = Task(
            (0, 0), [["HARVEST"]],
            value=value.sale_value(snap, "MILK", 4),
            kind="ANIMAL_SERVICE",
        )
        capital = Task(
            (1, 0), [["BUILD_PASTURE"], ["PLACE", "COW"]],
            value=value.animal_placement_value(snap, "COW")
                  - econ.ANIMALS["COW"]["cost"],
            kind="CAPITAL_ANIMAL",
        )
        model = value.TaskBundleObjective(snap, [ordinary, capital])
        outputs = model.outputs(ordinary)["MILK"] + model.outputs(capital)["MILK"]
        expected = (model.residual(ordinary) + model.residual(capital)
                    + value.sale_value(snap, "MILK", outputs))
        self.assertAlmostEqual(model.score([ordinary, capital]), expected)

    def test_repeated_milk_wool_and_strawberry_clear_once_per_item(self):
        snap = _snap()
        tasks = []
        groups = (("COW", "MILK", 6), ("SHEEP", "WOOL", 5))
        x = 0
        expected_quantities = {"MILK": 0, "WOOL": 0, "STRAWBERRY": 0}
        for animal, product, held in groups:
            for _ in range(2):
                tile = _animal(animal, yield_units=held)
                snap.me.tiles[0][x] = tile
                task = Task(
                    (x, 0), [["HARVEST"]], value=value.sale_value(
                        snap, product, held,
                    ), kind="ANIMAL_SERVICE",
                )
                tasks.append(task)
                expected_quantities[product] += held
                x += 1
        for _ in range(2):
            qty = 4
            snap.me.tiles[0][x] = {
                "kind": "PLANT", "crop": "STRAWBERRY",
                "planted_day": 0, "yield_units": qty,
                "watered_today": True, "consecutive_unwatered": 0,
                "max_lifespan_step": -1, "fertilized_until_day": -1,
            }
            tasks.append(Task(
                (x, 0), [["HARVEST"]],
                value=value.sale_value(snap, "STRAWBERRY", qty),
                kind="CROP_SERVICE",
            ))
            expected_quantities["STRAWBERRY"] += qty
            x += 1

        value.reprice_task_sale_bundles(snap, tasks)
        self.assertAlmostEqual(
            sum(task.value for task in tasks),
            sum(value.sale_value(snap, item, qty)
                for item, qty in expected_quantities.items()),
        )
        for task in tasks:
            self.assertLess(task.value, max(
                value.sale_value(snap, item, qty)
                for item, qty in value.task_sale_outputs(snap, task).items()
            ) + 1e-9)

    def test_plant_proposal_uses_joint_strawberry_quantity(self):
        snap = _snap(day=4)
        qty = value.plant_output_units(snap, "STRAWBERRY")
        tasks = [
            Task((0, 0), [["PLANT", "STRAWBERRY"], ["WATER"]],
                 value=value.plant_value(snap, "STRAWBERRY"),
                 kind="PLANT_CROP"),
            Task((1, 0), [["PLANT", "STRAWBERRY"], ["WATER"]],
                 value=value.plant_value(snap, "STRAWBERRY"),
                 kind="PLANT_CROP"),
        ]
        value.reprice_task_sale_bundles(snap, tasks)
        self.assertEqual(qty, 4)
        self.assertAlmostEqual(
            sum(task.value for task in tasks),
            value.sale_value(snap, "STRAWBERRY", 2 * qty),
        )

    def test_feed_and_option_floor_remain_explicit_residuals(self):
        snap = _snap(day=9)
        tasks, residuals, total_units = [], [], 0
        for x in range(2):
            tile = _animal(
                "COW", consecutive_unfed=1, pending_care_bonus=1,
            )
            snap.me.tiles[0][x] = tile
            ops = [["FEED"], ["CARE"]]
            original, mandatory = value.animal_task_value(snap, tile, ops)
            self.assertTrue(mandatory)
            task = Task((x, 0), ops, value=original,
                        mandatory=mandatory, kind="ANIMAL_SERVICE")
            outputs = value.task_sale_outputs(snap, task)
            self.assertGreater(outputs["MILK"], 0)
            residuals.append(
                original - value.sale_value(snap, "MILK", outputs["MILK"])
            )
            total_units += outputs["MILK"]
            tasks.append(task)
        value.reprice_task_sale_bundles(snap, tasks)
        self.assertAlmostEqual(
            sum(task.value for task in tasks),
            sum(residuals) + value.sale_value(snap, "MILK", total_units),
        )
        self.assertTrue(all(task.mandatory for task in tasks))

    def test_unidentified_build_value_is_not_relabelled_as_output(self):
        snap = _snap()
        task = Task((0, 0), [["BUILD_PASTURE"]], value=123.0,
                    kind="BUILD_ANIMAL_HOME")
        self.assertEqual(value.task_sale_outputs(snap, task), {})
        value.reprice_task_sale_bundles(snap, [task])
        self.assertEqual(task.value, 123.0)


if __name__ == "__main__":
    unittest.main()
