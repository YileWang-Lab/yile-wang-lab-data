"""Rule tests for public opponent timing, holdings and cash signals."""
import unittest

from whitebox import horizon


class _Farm:
    money = 399.0


class _Snap:
    seat = 0
    step = 100
    day = 4
    opp = _Farm()


class HorizonTests(unittest.TestCase):
    def test_public_cash_is_a_hard_affordability_bound(self):
        hz = horizon.Horizon(_Snap(), None)
        self.assertEqual(hz.cash, 399.0)
        self.assertTrue(hz.can_afford(399))
        self.assertFalse(hz.can_afford(400))
        self.assertEqual(hz.affordability_gap(400), 1.0)


if __name__ == "__main__":
    unittest.main()
