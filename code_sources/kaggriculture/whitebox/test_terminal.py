"""Equation tests for the state-derived terminal certificate."""
import unittest
from types import SimpleNamespace

from whitebox import econ, state, terminal


def _snap(step=696, farmer=(4, 4), hands=(), animals=None, crops=None,
          shed=None, inventories=None):
    me = SimpleNamespace(
        farmer=tuple(farmer), hands=[tuple(p) for p in hands],
        animals=dict(animals or {}), crops=dict(crops or {}),
    )
    opp = SimpleNamespace(
        farmer=(4, 4), hands=[], animals={}, crops={},
    )
    shed = dict(shed or {})
    inv = list(inventories or [{} for _ in range(1 + len(hands))])
    return SimpleNamespace(
        step=int(step), day=int(step) // econ.TURNS_PER_DAY,
        hour=int(step) % econ.TURNS_PER_DAY,
        me=me, opp=opp, shed=shed, inventories=inv,
        shed_used=sum(shed.values()),
        market_inv={item: econ.MARKET_I0 for item in econ.SELLABLE},
        shops=(), config={"episodeSteps": 720, "shedCapacity": 100},
    )


def _cow(units=1):
    return {"kind": "PASTURE", "animal": "COW", "yield_units": units}


def _animal(kind, units=1):
    structure = econ.ANIMALS[kind]["structure"]
    return {"kind": structure, "animal": kind, "yield_units": units}


class TerminalCertificateTests(unittest.TestCase):
    def test_production_closure_comes_from_last_refresh_equation(self):
        self.assertFalse(terminal.production_closed(_snap(step=695)))
        self.assertTrue(terminal.production_closed(_snap(step=696)))
        self.assertEqual(state.LAST_STEP, 718)

    def test_immediate_one_time_crop_output_blocks_takeover(self):
        crop = {
            "kind": "PLANT", "crop": "WHEAT", "planted_day": 27,
            "yield_units": 1, "watered_today": False,
            "max_lifespan_step": -1,
        }
        cert = terminal.certify(_snap(crops={(4, 3): crop}))
        self.assertFalse(cert.feasible)
        self.assertEqual(cert.reason, "immediate_crop_output")

    def test_joint_sweep_claims_each_target_once_and_fits_actions(self):
        snap = _snap(
            farmer=(4, 4), hands=[(5, 4)],
            animals={(3, 4): _cow(2), (6, 4): _cow(3)},
        )
        cert = terminal.certify(snap)
        self.assertTrue(cert.feasible, cert.reason)
        targets = [target[0] for route in cert.routes.values()
                   for target in route]
        self.assertEqual(sorted(targets), [(3, 4), (6, 4)])
        self.assertEqual(len(targets), len(set(targets)))
        self.assertLessEqual(cert.max_route_actions, cert.remaining_actions)
        self.assertEqual(cert.outputs["MILK"], 5)

    def test_unreachable_residual_sweep_falls_back_to_general_planner(self):
        snap = _snap(step=718, farmer=(4, 4), animals={(0, 0): _cow(2)})
        cert = terminal.certify(snap)
        self.assertFalse(cert.feasible)
        self.assertEqual(cert.reason, "residual_sweep")

    def test_carried_goods_must_reach_shed_before_last_action(self):
        snap = _snap(
            step=718, farmer=(0, 0), inventories=[{"STRAWBERRY": 4}],
        )
        cert = terminal.certify(snap)
        self.assertFalse(cert.feasible)
        self.assertEqual(cert.reason, "carried_delivery")

    def test_sale_orders_include_only_stock_available_after_current_drop(self):
        snap = _snap(
            farmer=(4, 4), shed={"EGG": 3},
            inventories=[{"MILK": 2}],
        )
        orders = terminal.sale_orders(snap, [["DROP"]])
        self.assertEqual(orders, [["SELL", "EGG", 3], ["SELL", "MILK", 2]])
        self.assertLessEqual(len(orders), econ.MAX_ORDERS)

    def test_inventory_master_derives_final_action_and_sells_current_drop(self):
        snap = _snap(
            step=98, shed={"EGG": 3}, inventories=[{"MILK": 2}],
        )
        snap.config = {"episodeSteps": 100, "shedCapacity": 100}
        orders = terminal.inventory_master_orders(
            snap, [["DROP"]], {"EGG": 3, "MILK": 2},
        )
        self.assertEqual(orders, [["SELL", "EGG", 3], ["SELL", "MILK", 2]])

    def test_inventory_master_releases_exact_required_shared_capacity(self):
        snap = _snap(
            step=696, shed={"FERTILIZER": 10, "COW": 1},
        )
        orders = terminal.inventory_master_orders(
            snap, [["PASS"]], {"FERTILIZER": 100, "COW": 1},
        )
        self.assertEqual(orders, [["SELL", "FERTILIZER", 1]])

    def test_inventory_master_retains_when_split_has_no_value_or_capacity_need(self):
        snap = _snap(step=696, shed={"FERTILIZER": 10})
        self.assertEqual(
            terminal.inventory_master_orders(
                snap, [["PASS"]], {"FERTILIZER": 10},
            ),
            [],
        )

    def test_inventory_master_matches_exhaustive_two_product_quantity_choice(self):
        snap = _snap(step=696, shed={"MILK": 3, "WOOL": 2})
        snap.config = {"episodeSteps": 720, "shedCapacity": 3}
        totals = {"MILK": 3, "WOOL": 2}
        best = None
        for milk in range(4):
            for wool in range(3):
                sold = milk + wool
                if sold < 2:
                    continue
                value = sum((
                    terminal._terminal_split_value(
                        snap, "MILK", 3, milk, 718,
                    ),
                    terminal._terminal_split_value(
                        snap, "WOOL", 2, wool, 718,
                    ),
                ))
                slots = int(milk > 0) + int(wool > 0)
                key = (value, -sold, -slots, -milk, -wool)
                if best is None or key > best[0]:
                    best = (key, milk, wool)
        orders = terminal.inventory_master_orders(
            snap, [["PASS"]], totals,
        )
        got = {order[1]: order[2] for order in orders}
        self.assertEqual(
            (got.get("MILK", 0), got.get("WOOL", 0)),
            (best[1], best[2]),
        )

    def test_current_drop_capacity_is_joint_across_units(self):
        snap = _snap(
            farmer=(4, 4), hands=[(5, 4)], shed={"EGG": 98},
            inventories=[{"MILK": 2}, {"WOOL": 1}],
        )
        cert = terminal.certify(snap)
        self.assertFalse(cert.feasible)
        self.assertEqual(cert.reason, "current_drop_capacity")

    def test_partial_certificate_leaves_hour_zero_to_hire_master(self):
        cert = terminal.certify_partial(
            _snap(step=696, animals={(3, 4): _cow(2)}),
        )
        self.assertFalse(cert.feasible)
        self.assertEqual(cert.reason, "hire_market_phase")

    def test_partial_certificate_keeps_reachable_profitable_subset(self):
        snap = _snap(
            step=715, farmer=(4, 4),
            animals={(3, 4): _cow(2), (0, 0): _cow(4)},
        )
        full = terminal.certify(snap)
        partial = terminal.certify_partial(snap)
        self.assertFalse(full.feasible)
        self.assertTrue(partial.feasible, partial.reason)
        selected = [target[0] for route in partial.routes.values()
                    for target in route]
        self.assertEqual(selected, [(3, 4)])
        self.assertEqual(partial.outputs["MILK"], 2)
        self.assertGreater(partial.paired_value, 0)

    def test_general_route_reprices_repeated_output_as_one_bundle(self):
        snap = _snap(
            step=697, farmer=(4, 4), hands=[(5, 4)],
            animals={(3, 4): _cow(2), (6, 4): _cow(3)},
        )
        cert = terminal.general_route_upper(
            snap, {0: [(3, 4)], 1: [(6, 4)]},
        )
        self.assertTrue(cert.feasible, cert.reason)
        self.assertEqual(cert.outputs["MILK"], 5)
        self.assertEqual(
            cert.paired_value,
            terminal._paired_visible_value(
                snap, {"MILK": 5}, cert.opponent_upper,
            ),
        )

    def test_opportunity_comparison_is_strict_and_preserves_ties(self):
        general = terminal.TerminalCertificate(10)
        candidate = terminal.TerminalCertificate(10)
        general.feasible = candidate.feasible = True
        general.paired_value = candidate.paired_value = 100.0
        self.assertFalse(terminal.prefer_terminal(candidate, general))
        candidate.paired_value = 101.0
        self.assertTrue(terminal.prefer_terminal(candidate, general))

    def test_hidden_opportunity_uses_one_same_scenario_difference(self):
        snap = _snap(step=697)
        general = terminal.TerminalCertificate(10)
        candidate = terminal.TerminalCertificate(10)
        general.feasible = candidate.feasible = True
        general.outputs = {"MILK": 4, "WOOL": 2}
        candidate.outputs = {"MILK": 5, "WOOL": 2}
        general.opponent_upper = {"MILK": 2, "WOOL": 3}
        candidate.opponent_upper = dict(general.opponent_upper)
        self.assertTrue(
            terminal.prefer_terminal_hidden(snap, candidate, general),
        )
        candidate.outputs = dict(general.outputs)
        self.assertFalse(
            terminal.prefer_terminal_hidden(snap, candidate, general),
        )

    def test_complete_terminal_bundle_includes_animal_fertilizer(self):
        animal = _cow(2)
        animal["fertilizer_available"] = True
        snap = _snap(step=697, animals={(3, 4): animal})
        old = terminal.certify_partial(snap)
        complete = terminal.certify_partial_complete(snap)
        self.assertTrue(complete.feasible, complete.reason)
        self.assertEqual(old.outputs["MILK"], 2)
        self.assertNotIn("FERTILIZER", old.outputs)
        self.assertEqual(complete.outputs["MILK"], 2)
        self.assertEqual(complete.outputs["FERTILIZER"], 1)
        route = next(iter(complete.routes.values()))
        self.assertEqual(route[0][1], ("HARVEST", "COLLECT_FERTILIZER"))

    def test_chained_terminal_route_pays_one_final_drop(self):
        snap = _snap(
            step=711, farmer=(4, 4),
            animals={(2, 4): _cow(2), (3, 4): _cow(2)},
        )
        separate = terminal.certify_partial_complete(snap)
        chained = terminal.certify_partial_chained(snap)
        self.assertTrue(chained.feasible, chained.reason)
        self.assertEqual(sum(len(route) for route in separate.routes.values()), 1)
        self.assertEqual(sum(len(route) for route in chained.routes.values()), 2)
        self.assertEqual(chained.outputs["MILK"], 4)
        self.assertEqual(chained.max_route_actions, 7)
        self.assertLessEqual(chained.max_route_actions, chained.remaining_actions)

    def test_chained_terminal_carry_can_visit_then_close(self):
        snap = _snap(
            step=715, farmer=(2, 4), inventories=[{"MILK": 2}],
            animals={(3, 4): _cow(2)},
        )
        chained = terminal.certify_partial_chained(snap)
        self.assertTrue(chained.feasible, chained.reason)
        self.assertEqual(chained.actions, [["EAST"]])
        self.assertEqual(chained.outputs["MILK"], 4)
        self.assertEqual(chained.max_route_actions, 4)

    def test_chained_terminal_enforces_shared_final_output_capacity(self):
        snap = _snap(
            step=697, farmer=(4, 4), hands=[(5, 4)],
            inventories=[{"MILK": 50}, {"WOOL": 49}],
            animals={(3, 4): _cow(2)},
        )
        chained = terminal.certify_partial_chained(snap)
        self.assertTrue(chained.feasible, chained.reason)
        self.assertEqual(chained.outputs.get("MILK"), 50)
        self.assertNotIn(0, chained.routes)
        self.assertNotIn(1, chained.routes)
        self.assertLessEqual(
            sum(chained.outputs.values()) - snap.shed_used,
            econ.SHED_CAPACITY,
        )

    def test_inserted_terminal_collects_target_inside_existing_chain(self):
        snap = _snap(
            step=697, farmer=(4, 4),
            animals={
                (0, 4): _animal("SHEEP", 6),
                (9, 4): _animal("COW", 6),
                (3, 4): _animal("GOOSE", 1),
            },
        )
        appended = terminal.certify_partial_chained(snap)
        inserted = terminal.certify_partial_inserted(snap)
        self.assertTrue(appended.feasible, appended.reason)
        self.assertTrue(inserted.feasible, inserted.reason)
        self.assertEqual(sum(len(r) for r in appended.routes.values()), 2)
        self.assertEqual(sum(len(r) for r in inserted.routes.values()), 3)
        self.assertNotIn("EGG", appended.outputs)
        self.assertEqual(inserted.outputs["EGG"], 1)
        self.assertEqual(inserted.max_route_actions, 21)
        route = next(iter(inserted.routes.values()))
        self.assertEqual([target[0] for target in route],
                         [(3, 4), (0, 4), (9, 4)])

    def test_inserted_route_revalidates_decay_for_every_later_crop(self):
        snap = _snap(step=715, farmer=(4, 4))
        delay = ((4, 4), ("COLLECT_FERTILIZER",),
                 (("FERTILIZER", 1),), -1)
        crop = ((5, 4), ("HARVEST",), (("MELON", 2),), 716)
        self.assertEqual(
            terminal._chained_route_finish(snap, (4, 4), [crop]),
            3,
        )
        self.assertIsNone(
            terminal._chained_route_finish(snap, (4, 4), [delay, crop]),
        )

    def test_exchange_replaces_one_long_target_with_better_joint_bundle(self):
        # Eight actions can close either the distant one-WOOL trip or the two
        # nearby one-MILK stops.  V103 greedily takes WOOL first because its
        # exact singleton revenue is larger; after that neither MILK stop
        # fits.  Removing WOOL, forcing either rejected MILK and refilling the
        # other produces a strictly more valuable exact nonlinear bundle.
        snap = _snap(
            step=711, farmer=(4, 4),
            animals={
                (1, 4): _animal("SHEEP", 1),
                (3, 4): _animal("COW", 1),
                (4, 3): _animal("COW", 1),
            },
        )
        inserted = terminal.certify_partial_inserted(snap)
        exchanged = terminal.certify_partial_exchanged(snap)
        self.assertTrue(exchanged.feasible, exchanged.reason)
        self.assertEqual(inserted.outputs.get("WOOL"), 1)
        self.assertNotIn("MILK", inserted.outputs)
        self.assertNotIn("WOOL", exchanged.outputs)
        self.assertEqual(exchanged.outputs.get("MILK"), 2)
        self.assertGreater(exchanged.paired_value, inserted.paired_value)
        self.assertEqual(exchanged.reason, "ok_partial_exchanged")
        self.assertLessEqual(
            exchanged.max_route_actions, exchanged.remaining_actions,
        )

    def test_exchange_preserves_v103_when_no_rejected_target_exists(self):
        snap = _snap(
            step=711, farmer=(4, 4), animals={(3, 4): _cow(2)},
        )
        inserted = terminal.certify_partial_inserted(snap)
        exchanged = terminal.certify_partial_exchanged(snap)
        self.assertEqual(exchanged.reason, inserted.reason)
        self.assertEqual(exchanged.routes, inserted.routes)
        self.assertEqual(exchanged.actions, inserted.actions)
        self.assertEqual(exchanged.outputs, inserted.outputs)
        self.assertEqual(exchanged.paired_value, inserted.paired_value)

    def test_rescue_replaces_only_unfinishable_general_suffix(self):
        snap = _snap(
            step=715, farmer=(2, 4), inventories=[{"STRAWBERRY": 4}],
            animals={(9, 9): _cow(2)},
        )
        actions, rescued = terminal.rescue_actions(
            snap, {0: [(9, 9)]}, [["EAST"]],
        )
        self.assertEqual(rescued, 1)
        self.assertIn(actions[0][0], ("EAST", "SOUTH"))
        self.assertNotEqual(actions[0], ["PASS"])

    def test_rescue_preserves_general_route_when_suffix_can_bank(self):
        snap = _snap(
            step=697, farmer=(4, 4), inventories=[{"MILK": 2}],
            animals={(3, 4): _cow(2)},
        )
        original = [["WEST"]]
        actions, rescued = terminal.rescue_actions(
            snap, {0: [(3, 4)]}, original,
        )
        self.assertEqual(rescued, 0)
        self.assertEqual(actions, original)


if __name__ == "__main__":
    unittest.main()
