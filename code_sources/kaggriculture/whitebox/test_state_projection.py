"""Equation-level fidelity tests for the post-unit phase snapshot."""
import copy
import unittest

from planner.simulate import _apply_unit_action
from whitebox import econ, market, state


def _animal(kind, **changes):
    tile = {
        "kind": econ.ANIMALS[kind]["structure"], "animal": kind,
        "placed_day": 0, "yield_units": 0, "consecutive_unfed": 0,
        "fed_today": False, "cared_today": False,
        "fertilizer_available": False, "pending_care_bonus": 0,
    }
    tile.update(changes)
    return tile


def _plant(crop, day, **changes):
    rule = econ.CROPS[crop]
    tile = {
        "kind": "PLANT", "crop": crop, "planted_day": day,
        "watered_today": False, "consecutive_unwatered": 1,
        "yield_units": 0 if rule["ongoing"] else 1,
        "max_lifespan_step": -1,
        "fertilized_until_day": -1,
    }
    tile.update(changes)
    return tile


def _fixture(step=125, hands=()):
    tiles = [[None for _x in range(10)] for _y in range(10)]
    farm = {
        "money": 3000.0, "tiles": tiles, "farmer": [0, 0],
        "hands": [list(pos) for pos in hands], "hires_today": 3,
        "unlocked_quadrants": ["NW", "NE", "SW", "SE"],
    }
    other = copy.deepcopy(farm)
    other["hands"] = []
    private = {
        "shed": {item: 0 for item in (*econ.SELLABLE, *econ.ANIMALS)},
        "seeds": {crop: 0 for crop in econ.CROPS},
        "inventories": [{} for _ in range(1 + len(hands))],
    }
    obs = {
        "step": step, "day": step // 24, "hour": step % 24, "player": 0,
        "farms": [farm, other], "private": private,
        "market": {
            "inventory": {item: econ.MARKET_I0 for item in econ.SELLABLE},
            "prices": {item: econ.price(item, econ.MARKET_I0)
                       for item in econ.SELLABLE},
        },
        "town": {"unlocked_shops": []},
    }
    config = {"turnsPerDay": 24, "shedCapacity": 100}
    return obs, config


class UnitPhaseProjectionTests(unittest.TestCase):
    def test_every_unit_equation_matches_engine_transition(self):
        positions = [
            (4, 4), (5, 4), (0, 1), (4, 5), (1, 1),
            (2, 1), (3, 1), (4, 1), (5, 1), (6, 1),
            (7, 1), (8, 1), (9, 1), (0, 2), (1, 2),
        ]
        obs, config = _fixture(hands=positions)
        farm, private = obs["farms"][0], obs["private"]
        day = obs["day"]

        private["shed"]["EGG"] = 94
        private["shed"]["WHEAT"] = 5
        private["seeds"]["WHEAT"] = 1
        private["inventories"][1] = {"CARROT": 2}
        private["inventories"][3] = {"COW": 1}
        private["inventories"][4] = {"FERTILIZER": 3}
        private["inventories"][9] = {"FERTILIZER": 1}
        private["inventories"][13] = {"WHEAT": 1}

        farm["tiles"][1][0] = {"kind": "PASTURE"}
        farm["tiles"][1][2] = _plant(
            "CARROT", day - 2, yield_units=1,
            fertilized_until_day=day,
        )
        farm["tiles"][1][3] = _plant("WHEAT", day - 2, yield_units=4)
        farm["tiles"][1][4] = _animal("COW", yield_units=3)
        farm["tiles"][1][5] = _plant("TOMATO", day - 8)
        farm["tiles"][1][6] = {"kind": "WEED"}
        farm["tiles"][1][9] = _animal("COW")
        farm["tiles"][2][0] = _animal(
            "COW", fertilizer_available=True,
        )
        farm["tiles"][2][1] = _animal("COW")

        actions = [
            ["EAST"], ["DROP"], ["PICKUP", "WHEAT", 2],
            ["PLACE", "COW"], ["PLACE", "FERTILIZER", 2],
            ["PLANT", "WHEAT"], ["WATER"], ["HARVEST"],
            ["HARVEST"], ["FERTILIZE"], ["DIG"], ["BUILD_COOP"],
            ["BUILD_PASTURE"], ["FEED"], ["COLLECT_FERTILIZER"],
            ["CARE"],
        ]
        snap = state.extract(copy.deepcopy(obs), config)
        original_tiles = copy.deepcopy(snap.me.tiles)
        projected = state.project_unit_phase(snap, actions)

        expected_farm = copy.deepcopy(farm)
        expected_private = copy.deepcopy(private)
        for index, action in enumerate(actions):
            _apply_unit_action(
                expected_farm, expected_private, index, action,
                10, day, 24, 100,
            )

        self.assertEqual(projected.me.farmer, tuple(expected_farm["farmer"]))
        self.assertEqual(projected.me.hands,
                         [tuple(pos) for pos in expected_farm["hands"]])
        self.assertEqual(projected.me.tiles, expected_farm["tiles"])
        self.assertEqual(projected.shed, expected_private["shed"])
        self.assertEqual(projected.seeds, expected_private["seeds"])
        self.assertEqual(projected.inventories,
                         expected_private["inventories"])
        self.assertEqual(snap.me.tiles, original_tiles,
                         "projection must not mutate the live snapshot")

    def test_atomic_seed_block_and_sequential_same_tile_mutation(self):
        obs, config = _fixture(
            hands=((2, 2), (3, 3), (3, 3)),
        )
        obs["farms"][0]["farmer"] = [1, 1]
        obs["private"]["seeds"]["STRAWBERRY"] = 1
        obs["private"]["inventories"][3] = {"COW": 1}
        snap = state.extract(obs, config)
        projected = state.project_unit_phase(snap, [
            ["PLANT", "STRAWBERRY"], ["PLANT", "STRAWBERRY"],
            ["BUILD_PASTURE"], ["PLACE", "COW"],
        ])
        self.assertIsNone(projected.me.tiles[1][1])
        self.assertIsNone(projected.me.tiles[2][2])
        self.assertEqual(projected.seeds["STRAWBERRY"], 1)
        self.assertEqual(projected.me.tiles[3][3]["animal"], "COW")
        self.assertNotIn("COW", projected.inventories[3])

    def test_projected_drop_is_priced_once(self):
        obs, config = _fixture()
        obs["farms"][0]["farmer"] = [4, 4]
        obs["private"]["inventories"][0] = {"MILK": 3}
        snap = state.extract(obs, config)
        projected = state.project_unit_phase(snap, [["DROP"]])
        orders = market.same_turn_bank_orders(
            projected, [["SELL", "MILK", 3]], [["DROP"]],
        )
        self.assertEqual(projected.shed["MILK"], 3)
        self.assertEqual(projected.inventories[0], {})
        self.assertEqual(orders, [["SELL", "MILK", 3]])


if __name__ == "__main__":
    unittest.main()
