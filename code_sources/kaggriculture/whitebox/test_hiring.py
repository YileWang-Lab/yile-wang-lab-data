"""Rule-level tests for joint hiring and hired-worker routes."""
import unittest
from types import SimpleNamespace
from unittest import mock

from planner.simulate import Simulator
from route.router import Task
from whitebox import econ, hiring


def _snap(hour=20, farmer=(0, 0), hands=(), money=100, hires_today=0):
    me = SimpleNamespace(farmer=farmer, hands=list(hands), money=money,
                         hires_today=hires_today, unlocked=["NW"])
    return SimpleNamespace(hour=hour, board=10, me=me, shed={}, market_inv={})


class HiringTests(unittest.TestCase):
    def test_engine_hire_is_created_after_unit_phase_and_acts_at_h_plus_one(self):
        sim = Simulator.new_episode(
            {"startingMoney": 100, "weedSpawnChance": 0}, seed=17,
        )
        # The farmer vacates (4, 4) during the unit phase.  The phantom hand
        # action in this same request cannot affect a worker that does not yet
        # exist; HIRE then chooses the newly empty first tie-break spawn tile.
        sim.step_actions(
            {"farmer": ["WEST"], "hands": [["EAST"]],
             "market": [["HIRE"]]},
            {"farmer": ["PASS"], "hands": [], "market": []},
        )
        self.assertEqual(sim.farms[0]["farmer"], [3, 4])
        self.assertEqual(sim.farms[0]["hands"], [[4, 4]])

        # The new hand becomes controllable on the following engine step.
        sim.step_actions(
            {"farmer": ["PASS"], "hands": [["EAST"]], "market": []},
            {"farmer": ["PASS"], "hands": [], "market": []},
        )
        self.assertEqual(sim.farms[0]["hands"], [[5, 4]])

    def test_engine_fibonacci_prices_and_has_no_five_or_six_hire_cap(self):
        expected = [1, 1, 2, 3, 5, 8, 13, 21]
        self.assertEqual([econ.hire_cost(i) for i in range(8)], expected)
        self.assertEqual(econ.hire_block_cost(0, 8), sum(expected))

        sim = Simulator.new_episode(
            {"startingMoney": 1000, "maxMarketOrdersPerTurn": 10,
             "weedSpawnChance": 0},
            seed=19,
        )
        sim.step_actions(
            {"farmer": ["PASS"], "hands": [],
             "market": [["HIRE"] for _ in range(8)]},
            {"farmer": ["PASS"], "hands": [], "market": []},
        )
        self.assertEqual(len(sim.farms[0]["hands"]), 8)
        self.assertEqual(sim.farms[0]["hires_today"], 8)
        self.assertEqual(sim.farms[0]["money"], 1000 - sum(expected))

    def test_spawn_uses_post_unit_action_occupancy(self):
        snap = _snap(hour=0, farmer=(4, 4))
        self.assertEqual(hiring.spawn_positions(snap, 2), [(5, 4), (4, 5)])
        self.assertEqual(hiring.spawn_positions(snap, 2, [["WEST"]]),
                         [(4, 4), (5, 4)])

    def test_new_hand_route_is_in_decision(self):
        # The farmer cannot reach the shed task in four turns. A hand hired at
        # hour 20 spawns on it, starts at hour 21, and can execute the task.
        snap = _snap(hour=20)
        plan = SimpleNamespace(cash_floor=0)
        work = [Task((4, 4), [["CARE"]], value=100)]
        self.assertEqual(hiring.route_value(snap, work, 0), 0)
        self.assertEqual(hiring.route_value(snap, work, 1), 100)
        self.assertEqual(hiring.decide(snap, plan, work, max_orders=1), 1)

    def test_hire_price_uses_own_daily_counter(self):
        snap = _snap(hour=20, hires_today=5)
        plan = SimpleNamespace(cash_floor=0)
        cheap_work = [Task((4, 4), [["CARE"]], value=7)]
        valuable_work = [Task((4, 4), [["CARE"]], value=9)]
        # fib(5)=8: seven dollars of work is rejected, nine is accepted.
        self.assertEqual(hiring.decide(snap, plan, cheap_work, 1), 0)
        self.assertEqual(hiring.decide(snap, plan, valuable_work, 1), 1)

    def test_hour_23_hire_has_no_action_and_is_rejected(self):
        snap = _snap(hour=23)
        plan = SimpleNamespace(cash_floor=0)
        work = [Task((4, 4), [["CARE"]], value=1000)]
        self.assertEqual(hiring.decide(snap, plan, work, 1), 0)

    def test_early_hire_strictly_dominates_after_day_boundary_is_crossed(self):
        # A new hand at hour 0 starts at hour 1 with exactly 23 actions.  The
        # same purchase one hour later has only 22, so this indivisible route
        # slips a complete production day.  This is the transparent economic
        # reason to value early labour, rather than a hard-coded opening crew.
        work = [Task((4, 4), [["CARE"] for _ in range(23)], value=100)]
        early = _snap(hour=0, farmer=(0, 0))
        late = _snap(hour=1, farmer=(0, 0))
        self.assertEqual(hiring.route_value(early, work, 1), 100)
        self.assertEqual(hiring.route_value(late, work, 1), 0)
        plan = SimpleNamespace(cash_floor=0)
        self.assertEqual(hiring.decide(early, plan, work, max_orders=1), 1)
        self.assertEqual(hiring.decide(late, plan, work, max_orders=1), 0)

    def test_task_factory_expands_the_task_set_for_each_candidate_k(self):
        snap = _snap(hour=0, farmer=(0, 0), money=1000)
        plan = SimpleNamespace(cash_floor=0)
        seen = []

        def task_factory(k):
            seen.append(k)
            # Each candidate hand creates one deployable 23-turn route at its
            # exact spawn.  No incumbent can reach it and no worker can execute
            # two, so F(k)-F(k-1) is one real completed task, not idle capacity.
            return [
                Task(pos, [["CARE"] for _ in range(23)], value=100)
                for pos in hiring.spawn_positions(snap, k)
            ]

        rows = hiring.decision_curve(
            snap, plan, [], max_orders=3, task_factory=task_factory,
        )
        self.assertEqual([row["hires"] for row in rows], [0, 1, 2, 3])
        self.assertEqual([row["route_value"] for row in rows],
                         [0, 100, 200, 300])
        self.assertEqual([row["hire_cost"] for row in rows], [0, 1, 2, 4])
        self.assertEqual(set(seen), {0, 1, 2, 3})
        self.assertEqual(
            hiring.decide(
                snap, plan, [], max_orders=3, task_factory=task_factory,
            ),
            3,
        )

    def test_candidate_bound_is_slots_and_max_hands_not_fixed_six(self):
        plan = SimpleNamespace(cash_floor=0)

        def task_factory(k):
            return [Task((4, 4), [["CARE"]], value=100) for _ in range(k)]

        def relaxed_value(_snap, tasks, _new_hands=0, *_args, **_kwargs):
            return sum(float(task.value) for task in tasks)

        with mock.patch.object(hiring, "MAX_HANDS", 20), \
                mock.patch.object(hiring, "route_value", relaxed_value):
            rows = hiring.decision_curve(
                _snap(hour=0, money=10000), SimpleNamespace(cash_floor=0), [],
                max_orders=8, task_factory=task_factory,
            )
            self.assertEqual(rows[-1]["hires"], 8)

            # Once the persistent safety ceiling is genuinely the tighter
            # bound, it still applies independently of the remaining slots.
            rows = hiring.decision_curve(
                _snap(hour=0, hands=[(0, 0)] * 18, money=10000), plan, [],
                max_orders=8, task_factory=task_factory,
            )
            self.assertEqual(rows[-1]["hires"], 2)

    def test_market_slots_and_cash_are_prefix_bounds_on_candidate_k(self):
        plan = SimpleNamespace(cash_floor=0)

        def task_factory(k):
            return [Task((4, 4), [["CARE"]], value=100) for _ in range(k)]

        def relaxed_value(_snap, tasks, _new_hands=0, *_args, **_kwargs):
            return sum(float(task.value) for task in tasks)

        with mock.patch.object(hiring, "route_value", relaxed_value):
            by_slots = hiring.decision_curve(
                _snap(hour=0, money=1000), plan, [], max_orders=2,
                task_factory=task_factory,
            )
            self.assertEqual([row["hires"] for row in by_slots], [0, 1, 2])

            # Cumulative bills are 1, 2, 4, 7.  Six dollars can fund exactly
            # the first three hires; candidate four is not a feasible prefix.
            by_cash = hiring.decision_curve(
                _snap(hour=0, money=6), plan, [], max_orders=10,
                task_factory=task_factory,
            )
            self.assertEqual([row["hires"] for row in by_cash], [0, 1, 2, 3])
            self.assertEqual([row["hire_cost"] for row in by_cash], [0, 1, 2, 4])

    def test_enumeration_stops_when_next_wage_exceeds_remaining_value(self):
        snap = _snap(hour=0, farmer=(0, 0), money=100, hires_today=5)
        plan = SimpleNamespace(cash_floor=0)
        work = [Task((4, 4), [["CARE"] for _ in range(23)], value=5)]
        # The next private-counter wage is fib(5)=$8, while at most $5 of
        # positive work remains.  No larger crew can recover that first loss.
        rows = hiring.decision_curve(snap, plan, work, max_orders=10)
        self.assertEqual([row["hires"] for row in rows], [0])

if __name__ == "__main__":
    unittest.main()
