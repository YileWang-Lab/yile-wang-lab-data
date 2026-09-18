"""Equation-level tests for observable-shop conditioned town absorption."""
import unittest
from types import SimpleNamespace

from whitebox import market_model as model


def snap(step, shops, config=None):
    return SimpleNamespace(step=step, shops=tuple(shops), config=config or {})


class ShopConditioningTests(unittest.TestCase):
    def test_count_multiples_in_half_open_interval(self):
        self.assertEqual(model._count_multiples(4, 0, 13), 4)
        self.assertEqual(model._count_multiples(4, 1, 12), 2)

    def test_closed_form_matches_stepwise_expectation(self):
        for now in (0, 71, 72, 289, 576, 718):
            n_shops = min(8, now // 72)
            live = snap(now, ["YARN_STORE"] * n_shops)
            for item in ("WOOL", "MILK", "FERTILIZER"):
                expected = 0.0
                known = model._shop_tick_units(item, live.shops)
                for step in range(now, 719):
                    if item != "FERTILIZER" and step % 24 == 0:
                        expected += 1.0
                    if step % 4 == 0:
                        future = min(8 - n_shops,
                                     max(0, step // 72 - now // 72))
                        expected += (known + future
                                     * model.EXPECTED_FUTURE_SHOP_TICK[item])
                self.assertEqual(model.expected_town_take(live, item), expected)

    def test_observed_duplicate_shops_count_independently(self):
        self.assertEqual(
            model._shop_tick_units("WOOL", ["YARN_STORE", "YARN_STORE"]),
            4,
        )

    def test_future_draw_expectation_is_closed_form(self):
        # Only YARN_STORE of the eight equally likely shop names stocks WOOL,
        # and its single-product multiplier is two: E[take] = 2/8.
        self.assertEqual(model.EXPECTED_FUTURE_SHOP_TICK["WOOL"], 0.25)
        # Three multi-product shops stock MILK: E[take] = 3/8.
        self.assertEqual(model.EXPECTED_FUTURE_SHOP_TICK["MILK"], 0.375)

    def test_current_shops_are_exact_and_not_averaged(self):
        # At step 576 both the centre and all eight observed YARN_STORE copies
        # consume. There is no remaining future-shop uncertainty.
        observed = snap(576, ["YARN_STORE"] * 8)
        self.assertEqual(model.expected_town_take(observed, "WOOL", end_step=577), 17.0)
        self.assertEqual(model.expected_town_take(observed, "FERTILIZER", end_step=577), 0.0)

    def test_future_unlock_enters_on_its_first_usable_step(self):
        # In [0,73), centre ticks occur at 0/24/48/72. The first unknown shop
        # unlocks for day 3 and contributes on step 72: 4 + E[WOOL] = 4.25.
        empty_town = snap(0, [])
        self.assertEqual(model.expected_town_take(empty_town, "WOOL", end_step=72), 3.0)
        self.assertEqual(model.expected_town_take(empty_town, "WOOL", end_step=73), 4.25)

    def test_observed_unlock_replaces_its_expectation(self):
        # At the first step of day 3 the actual YARN_STORE is public: centre 1
        # plus the shop's exact two, rather than 1 + the prior expectation .25.
        yarn = snap(72, ["YARN_STORE"])
        self.assertEqual(model.expected_town_take(yarn, "WOOL", end_step=73), 3.0)

    def test_future_shop_uncertainty_is_an_analytic_interval(self):
        # Four deterministic town-centre WOOL units leave in [0, 73).  The
        # first hidden shop appears at step 72 and can remove either zero WOOL
        # or two if it is YARN_STORE; no sampling or seed enters this bound.
        self.assertEqual(
            model.town_take_bounds(snap(0, []), "WOOL", end_step=73),
            (4, 6),
        )

    def test_observed_shop_contribution_is_exact_in_both_bounds(self):
        # Once the day-3 shop is observed as YARN_STORE, its two-unit tick and
        # the one-unit town-centre tick are no longer uncertain.
        self.assertEqual(
            model.town_take_bounds(
                snap(72, ["YARN_STORE"]), "WOOL", end_step=73,
            ),
            (3, 3),
        )

    def test_conditioned_crop_mix_responds_to_observed_market(self):
        # Four FARMERS_MARKET instances observed by day 12 create materially
        # more remaining STRAWBERRY absorption than four YARN_STORE instances.
        # The response is to public state, not a seed or opponent identity.
        produce = model.crop_mix(snap=snap(288, ["FARMERS_MARKET"] * 4))
        yarn = model.crop_mix(snap=snap(288, ["YARN_STORE"] * 4))
        self.assertGreater(produce.get("STRAWBERRY", 0.0),
                           yarn.get("STRAWBERRY", 0.0))


if __name__ == "__main__":
    unittest.main()
