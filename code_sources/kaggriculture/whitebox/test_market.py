import unittest
from types import SimpleNamespace
from unittest import mock

from whitebox import market, market_model, state


class SameTurnBankTests(unittest.TestCase):
    def test_paid_fertilizer_precedes_capital_and_sales(self):
        snap = SimpleNamespace(
            step=240, day=10, hour=0, shops=(), config=None,
            market_inv={item: market.econ.MARKET_I0
                        for item in market.econ.SELLABLE},
            shed={}, shed_used=0, shed_room=100, inventories=[{}],
            seeds={}, days_left=20,
            me=SimpleNamespace(
                money=10000.0, empty=[], crops={}, animals={},
                unlocked=["NW"], animal_counts=lambda: {},
            ),
            opp=SimpleNamespace(animals={}, crops={}, workers=1),
            carried=lambda: {},
        )
        plan = SimpleNamespace(
            phase="mid", wheat_needed=0, cash_floor=0.0,
            service_cash_floor=0.0, fertilizer_target=2,
            target_animals={}, target_quadrants=1, crop_mix={},
            crop_targets={}, animal_budget=0.0,
        )
        got = market.orders(
            snap, plan, sale_variant="observation_only_timing",
        )
        self.assertEqual(got[0], ["BUY_PRODUCT", "FERTILIZER", 2])

    def test_drop_inventory_is_merged_and_front_loaded(self):
        snap = SimpleNamespace(
            inventories=[{"MILK": 3}, {"WOOL": 2}],
            market_inv={"MILK": 10000, "WOOL": 10000},
            step=400,
        )
        got = market.same_turn_bank_orders(
            snap,
            [["BUY_SEED", "MELON", 1], ["SELL", "MILK", 4]],
            [["DROP"], ["PASS"]],
        )
        self.assertEqual(got[0], ["SELL", "MILK", 7])
        self.assertEqual(got[1], ["BUY_SEED", "MELON", 1])

    def test_no_drop_is_identity(self):
        snap = SimpleNamespace(inventories=[{"MILK": 3}], market_inv={}, step=0)
        orders = [["BUY_SEED", "MELON", 1]]
        self.assertEqual(
            market.same_turn_bank_orders(snap, orders, [["PASS"]]), orders
        )


class CapacityReserveTests(unittest.TestCase):
    """Boundary tests for the tape-free day-close shed certificate."""

    def _snap(self, *, step=23, shed=None, inventories=None):
        return SimpleNamespace(
            step=step, hour=step % market.econ.TURNS_PER_DAY,
            shed=dict(shed or {}),
            inventories=list(inventories or [{}]),
            market_inv={item: market.econ.MARKET_I0
                        for item in market.econ.SELLABLE},
        )

    @staticmethod
    def _projected(*, shed=None, inventories=None):
        return SimpleNamespace(
            shed=dict(shed or {}),
            inventories=list(inventories or [{}]),
        )

    @staticmethod
    def _plan(**changes):
        values = {
            "wheat_needed": 0,
            "fertilizer_target": 0,
        }
        values.update(changes)
        return SimpleNamespace(**values)

    def test_under_target_is_identity(self):
        snap = self._snap(shed={"MILK": 40})
        orders = [["BUY_SEED", "WHEAT", 1]]
        self.assertEqual(
            market.capacity_reserve_orders(
                snap, self._plan(), orders, [["PASS"]],
                self._projected(shed={"MILK": 40}),
            ),
            orders,
        )

    def test_over_target_appends_only_required_sell(self):
        snap = self._snap(shed={"MILK": 95})
        orders = [["BUY_SEED", "WHEAT", 1]]
        got = market.capacity_reserve_orders(
            snap, self._plan(), orders, [["PASS"]],
            self._projected(shed={"MILK": 95, "WOOL": 10}),
        )
        self.assertEqual(got[0], orders[0])
        self.assertEqual(got[1], ["SELL", "WOOL", 6])

    def test_prefers_item_without_existing_planned_sell(self):
        snap = self._snap(shed={"MILK": 41, "WOOL": 60})
        orders = [["SELL", "MILK", 1]]
        got = market.capacity_reserve_orders(
            snap, self._plan(), orders, [["PASS"]],
            self._projected(shed={"MILK": 41, "WOOL": 60}),
        )
        # One existing MILK sale leaves 100 units; the reserve sale is taken
        # from WOOL because MILK already has a planned sale.
        self.assertEqual(got, [["SELL", "MILK", 1], ["SELL", "WOOL", 1]])

    def test_public_preference_uses_finished_product_order(self):
        snap = self._snap(shed={"MELON": 50, "WOOL": 51})
        projected = self._projected(shed={"MELON": 50, "WOOL": 51})
        got = market.capacity_reserve_orders(
            snap, self._plan(), [], [["PASS"]], projected,
            preference="public",
        )
        self.assertEqual(got, [["SELL", "WOOL", 2]])

    def test_wheat_feed_reserve_is_never_sold(self):
        snap = self._snap(shed={"WHEAT": 100, "MILK": 1})
        got = market.capacity_reserve_orders(
            snap, self._plan(wheat_needed=100), [], [["PASS"]],
            self._projected(shed={"WHEAT": 100, "MILK": 1}),
        )
        self.assertEqual(got, [["SELL", "MILK", 1]])
        self.assertTrue(all(order[1] != "WHEAT" for order in got))

    def test_fertilizer_reserve_is_never_sold(self):
        snap = self._snap(shed={"FERTILIZER": 100, "MILK": 1})
        got = market.capacity_reserve_orders(
            snap, self._plan(fertilizer_target=100), [], [["PASS"]],
            self._projected(shed={"FERTILIZER": 100, "MILK": 1}),
        )
        self.assertEqual(got, [["SELL", "MILK", 1]])
        self.assertTrue(all(order[1] != "FERTILIZER" for order in got))

    def test_sell_never_exceeds_projected_shed(self):
        snap = self._snap(shed={"MILK": 2})
        orders = [["BUY_PRODUCT", "WHEAT", 1]]
        projected = self._projected(
            shed={"MILK": 2}, inventories=[{"MILK": 99}],
        )
        got = market.capacity_reserve_orders(
            snap, self._plan(), orders, [["PASS"]], projected,
        )
        self.assertEqual(got[-1], ["SELL", "MILK", 2])

    def test_no_order_slot_preserves_parent_orders(self):
        snap = self._snap(shed={"MILK": 100, "WOOL": 10})
        orders = [["BUY_SEED", "WHEAT", 1] for _ in range(market.MAX_ORDERS)]
        self.assertEqual(
            market.capacity_reserve_orders(
                snap, self._plan(), orders, [["PASS"]],
                self._projected(shed={"MILK": 100, "WOOL": 10}),
            ),
            orders,
        )

    def test_non_boundary_and_endgame_are_identity(self):
        orders = [["BUY_SEED", "WHEAT", 1]]
        for step in (22, market.ENDGAME_START, market.ENDGAME_START + 24):
            snap = self._snap(step=step, shed={"MILK": 100})
            self.assertEqual(
                market.capacity_reserve_orders(
                    snap, self._plan(), orders, [["PASS"]],
                    self._projected(shed={"MILK": 100, "WOOL": 10}),
                ),
                orders,
            )

    def test_projection_counts_same_turn_drop_and_place(self):
        # These actions are projected before the market phase.  The helper
        # must consume the projected result rather than treating the original
        # carried inventory as sellable shed stock.
        snap = self._snap(step=23, shed={"MILK": 90},
                          inventories=[{"MILK": 5}, {"MILK": 1}])
        projected = self._projected(shed={"MILK": 95}, inventories=[{}])
        with mock.patch("whitebox.state.project_unit_phase",
                        return_value=projected) as project:
            got = market.capacity_reserve_orders(
                snap, self._plan(), [],
                [["DROP"], ["PLACE", "MILK", 1]], projected=None,
            )
        project.assert_called_once_with(
            snap, [["DROP"], ["PLACE", "MILK", 1]],
        )
        self.assertEqual(got, [])

    def test_real_projection_counts_drop_and_place_carry(self):
        tiles = [[None for _ in range(10)] for _ in range(10)]
        farm = {
            "money": 1000.0, "tiles": tiles, "farmer": [4, 4],
            "hands": [[4, 4]], "hires_today": 0,
            "unlocked_quadrants": ["NW", "NE", "SW", "SE"],
        }
        obs = {
            "step": 23, "player": 0, "farms": [farm, dict(farm)],
            "private": {
                "shed": {"MILK": 95},
                "seeds": {},
                "inventories": [{"MILK": 5}, {"MILK": 4}],
            },
            "market": {"inventory": {"MILK": market.econ.MARKET_I0}},
            "town": {"unlocked_shops": []},
        }
        snap = state.extract(obs, {"turnsPerDay": 24, "shedCapacity": 100})
        got = market.capacity_reserve_orders(
            snap, self._plan(), [],
            [["DROP"], ["PLACE", "MILK", 4]], projected=None,
        )
        # DROP fills the last five shed slots; PLACE remains carried because
        # no room is left.  The guard therefore sells only the five excess
        # shed units, never the four carried units directly.
        self.assertEqual(got, [["SELL", "MILK", 5]])

    def test_carried_inventory_is_not_current_sell_stock(self):
        snap = self._snap(shed={}, inventories=[{"MILK": 101}])
        got = market.capacity_reserve_orders(
            snap, self._plan(), [], [["PASS"]],
            self._projected(shed={}, inventories=[{"MILK": 101}]),
        )
        self.assertEqual(got, [])

    def test_malformed_projection_fails_closed(self):
        snap = self._snap(shed={"MILK": 100})
        orders = [["BUY_SEED", "WHEAT", 1]]
        malformed = SimpleNamespace(shed=None, inventories=None)
        self.assertEqual(
            market.capacity_reserve_orders(
                snap, self._plan(), orders, [["PASS"]], malformed,
            ),
            orders,
        )


class GuaranteedDrainSaleTests(unittest.TestCase):
    def _snap(self, step=240, shops=("YARN_STORE",), shed=None,
              inventories=None):
        shed = dict(shed or {"WOOL": 20})
        return SimpleNamespace(
            step=step, day=step // 24, hour=step % 24,
            shops=tuple(shops), config=None,
            market_inv={item: 10000 for item in market.econ.SELLABLE},
            shed=shed, inventories=list(inventories or [{}]),
            shed_used=sum(shed.values()), shed_room=100 - sum(shed.values()),
        )

    def test_batch_is_exact_observed_shop_lower_drain(self):
        snap = self._snap()
        low, _high = market_model.town_take_bounds(
            snap, "WOOL", start_step=240, end_step=264,
        )
        self.assertEqual(low, 13)  # six 2-unit shop ticks + town centre
        self.assertEqual(market._guaranteed_day_batch(snap, "WOOL", 20), 13)

    def test_feed_may_consume_only_its_named_service_reserve(self):
        snap = self._snap(step=240, shops=(), shed={"WHEAT": 0})
        snap.me = SimpleNamespace(money=100.0)
        plan = SimpleNamespace(
            wheat_needed=3, cash_floor=100.0, service_cash_floor=100.0,
        )
        self.assertEqual(market.feed_orders(snap, plan), [])
        self.assertEqual(
            market.feed_orders(
                snap, plan, consume_service_reserve=True,
            ),
            [["BUY_PRODUCT", "WHEAT", 3]],
        )

    def test_batch_exists_only_at_exact_day_boundary(self):
        snap = self._snap(step=241)
        self.assertEqual(market._guaranteed_day_batch(snap, "WOOL", 20), 0)

    def test_known_overflow_is_freed_exactly_at_best_marginal_value(self):
        snap = self._snap(
            step=241, shops=(), shed={"MILK": 50, "WHEAT": 49},
            inventories=[{"WOOL": 3}],
        )
        plan = SimpleNamespace(wheat_needed=49)
        got = market.steady_orders(
            snap, plan, sale_variant="guaranteed_day_drain",
        )
        self.assertEqual(sum(order[2] for order in got), 2)
        self.assertEqual(got, [["SELL", "MILK", 2]])

    def test_variant_disables_thresholded_endgame_front_run(self):
        opp = SimpleNamespace(animals={i: {} for i in range(10)}, workers=1)
        snap = SimpleNamespace(step=707, shed={"MILK": 9}, opp=opp)
        self.assertEqual(
            market.endgame_orders(snap, [], front_run=False), []
        )
        self.assertEqual(
            market.endgame_orders(snap, [], front_run=True),
            [["SELL", "MILK", 9]],
        )

    def test_day_boundary_liquidates_all_non_feed_stock(self):
        snap = self._snap(shed={"MILK": 20, "WHEAT": 12})
        plan = SimpleNamespace(wheat_needed=7)
        got = market.steady_orders(
            snap, plan, sale_variant="day_boundary_liquidation",
        )
        self.assertEqual(got, [
            ["SELL", "MILK", 20], ["SELL", "WHEAT", 5],
        ])

    def test_day_boundary_variant_does_not_use_legacy_batch_model(self):
        snap = self._snap()
        plan = SimpleNamespace(wheat_needed=0)
        with mock.patch.object(
            market, "_sell_batch", side_effect=AssertionError("legacy batch"),
        ):
            got = market.steady_orders(
                snap, plan, sale_variant="day_boundary_liquidation",
            )
        self.assertEqual(got, [["SELL", "WOOL", 20]])

    def test_robust_sale_cash_matches_shared_capacity_exhaustive_minimum(self):
        snap = self._snap(
            shed={"MILK": 4, "WOOL": 3}, inventories=[{}],
        )
        orders = [["SELL", "MILK", 4], ["SELL", "WOOL", 3]]
        capacity = 4
        expected = float("inf")
        for milk_hidden in range(capacity + 1):
            for wool_hidden in range(capacity - milk_hidden + 1):
                milk_inv = market._inventory_after_sale(
                    "MILK", milk_hidden, snap.market_inv["MILK"],
                )
                wool_inv = market._inventory_after_sale(
                    "WOOL", wool_hidden, snap.market_inv["WOOL"],
                )
                cash = (
                    market.econ.sell_revenue("MILK", 4, milk_inv)
                    + market.econ.sell_revenue("WOOL", 3, wool_inv)
                )
                expected = min(expected, cash)
        self.assertEqual(
            market.robust_sale_cash(snap, orders, capacity), expected,
        )

    def test_robust_sale_cash_caps_fictional_quantity_at_live_shed(self):
        snap = self._snap(shed={"MILK": 2}, inventories=[{}])
        self.assertEqual(
            market.robust_sale_cash(
                snap, [["SELL", "MILK", 200]], opponent_capacity=0,
            ),
            market.econ.sell_revenue("MILK", 2, snap.market_inv["MILK"]),
        )

    def test_one_step_wait_gain_matches_shared_allocation_exhaustive_minimum(self):
        snap = self._snap(
            step=240, shops=("DAIRY_SHOP", "YARN_STORE"),
            shed={"MILK": 4, "WOOL": 3}, inventories=[{}],
        )
        orders = [["SELL", "MILK", 4], ["SELL", "WOOL", 3]]
        capacity = 4
        expected = float("inf")
        for milk_hidden in range(capacity + 1):
            for wool_hidden in range(capacity - milk_hidden + 1):
                total = 0
                for item, qty, hidden in (
                    ("MILK", 4, milk_hidden), ("WOOL", 3, wool_hidden),
                ):
                    drain, upper = market_model.town_take_bounds(
                        snap, item, start_step=snap.step,
                        end_step=snap.step + 1,
                    )
                    self.assertEqual(drain, upper)
                    now_inv = market._inventory_after_sale(
                        item, hidden, snap.market_inv[item],
                    )
                    wait_inv = market._inventory_after_sale(
                        item, hidden, snap.market_inv[item] - drain,
                    )
                    total += (
                        market.econ.sell_revenue(item, qty, wait_inv)
                        - market.econ.sell_revenue(item, qty, now_inv)
                    )
                expected = min(expected, total)
        self.assertEqual(
            market.robust_one_step_wait_gain(snap, orders, capacity), expected,
        )
        self.assertGreater(expected, 0)

    def test_one_step_option_defers_only_sale_bundle_with_strict_gain(self):
        snap = self._snap(
            step=240, shops=("DAIRY_SHOP",), shed={"MILK": 4},
            inventories=[{}],
        )
        snap.me = SimpleNamespace(money=100)
        plan = SimpleNamespace(cash_floor=100)
        orders = [["SELL", "MILK", 4]]
        self.assertEqual(
            market.defer_strictly_dominated_sales(
                snap, plan, orders, [["PASS"]],
            ),
            [],
        )

    def test_one_step_option_keeps_sale_without_drain_or_with_spend(self):
        snap = self._snap(
            step=241, shops=("DAIRY_SHOP",), shed={"MILK": 4},
            inventories=[{}],
        )
        snap.me = SimpleNamespace(money=100)
        plan = SimpleNamespace(cash_floor=100)
        sale = [["SELL", "MILK", 4]]
        self.assertEqual(
            market.defer_strictly_dominated_sales(
                snap, plan, sale, [["PASS"]],
            ),
            sale,
        )
        spend = [["BUY_SEED", "WHEAT", 1]] + sale
        snap.step = 240
        snap.hour = 0
        self.assertEqual(
            market.defer_strictly_dominated_sales(
                snap, plan, spend, [["PASS"]],
            ),
            spend,
        )

    def test_one_step_option_keeps_sale_at_rollover_drop_or_cash_shortfall(self):
        snap = self._snap(
            step=263, shops=("DAIRY_SHOP",), shed={"MILK": 4},
            inventories=[{"MILK": 1}],
        )
        snap.me = SimpleNamespace(money=99)
        plan = SimpleNamespace(cash_floor=100)
        sale = [["SELL", "MILK", 4]]
        self.assertEqual(
            market.defer_strictly_dominated_sales(
                snap, plan, sale, [["DROP"]],
            ),
            sale,
        )
        snap.step = 240
        snap.hour = 0
        self.assertEqual(
            market.defer_strictly_dominated_sales(
                snap, plan, sale, [["PASS"]],
            ),
            sale,
        )

    def test_inventory_option_keeps_v86_observation_only_switches(self):
        snap = self._snap(shed={"MILK": 4})
        snap.opp = SimpleNamespace(animals={}, crops={})
        plan = SimpleNamespace(wheat_needed=0)
        with mock.patch.object(market, "_sell_batch", return_value=2) as batch:
            self.assertEqual(
                market.steady_orders(
                    snap, plan, tracker=SimpleNamespace(),
                    sale_variant="one_step_inventory_option",
                ),
                [["SELL", "MILK", 2]],
            )
        self.assertFalse(batch.call_args.kwargs["opponent_timing"])

    def test_observation_only_variant_disables_both_timing_signals(self):
        snap = self._snap(shed={"MILK": 4})
        snap.opp = SimpleNamespace(animals={}, crops={})
        plan = SimpleNamespace(wheat_needed=0)
        tracker = SimpleNamespace()
        with mock.patch.object(market, "_sell_batch", return_value=2) as batch:
            got = market.steady_orders(
                snap, plan, tracker=tracker,
                sale_variant="observation_only_timing",
            )
        self.assertEqual(got, [["SELL", "MILK", 2]])
        self.assertIs(batch.call_args.args[3], tracker)
        self.assertFalse(batch.call_args.kwargs["opponent_timing"])

    def test_observation_only_variant_disables_terminal_front_run(self):
        snap = self._snap(step=707, shed={"MILK": 9})
        snap.opp = SimpleNamespace(
            animals={i: {} for i in range(10)}, workers=1,
        )
        snap.me = SimpleNamespace(
            money=0, unlocked=["NW"], empty=[], crops={},
            animal_counts=lambda: {},
        )
        snap.days_left = 0
        snap.seeds = {}
        plan = SimpleNamespace(
            phase="endgame", wheat_needed=0, cash_floor=0,
            target_animals={}, target_quadrants=1, crop_mix={},
            animal_budget=0,
        )
        for variant in ("observation_only_timing",
                        "one_step_inventory_option"):
            self.assertEqual(
                market.orders(snap, plan, sale_variant=variant), [],
            )

    def test_observation_only_variant_pins_animal_bridge_off(self):
        snap = self._snap(step=240, shed={})
        plan = SimpleNamespace(phase="run", wheat_needed=0)
        for variant in ("observation_only_timing",
                        "one_step_inventory_option"):
            with mock.patch.object(market, "feed_orders", return_value=[]), \
                    mock.patch.object(market, "steady_orders", return_value=[]), \
                    mock.patch.object(market, "acquisition_orders",
                                      return_value=[]) as acquire:
                self.assertEqual(
                    market.orders(snap, plan, sale_variant=variant), [],
                )
            self.assertFalse(acquire.call_args.kwargs["bridge_reserve"])


if __name__ == "__main__":
    unittest.main()
