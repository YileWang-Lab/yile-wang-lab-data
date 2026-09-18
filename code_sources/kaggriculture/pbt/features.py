"""Six-dimensional opponent feature vector, all recoverable from public state.

Five come straight off the opponent's farm, which is fully public. The sixth,
market_tx_frequency, uses the exact sales inference in route/opponent.py: within
a step the engine settles both players' orders and then the town's consumption,
so their sales fall out of the public market inventory with zero error on every
premium product (validated in HANDOFF section 11).
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from route.opponent import OpponentModel, town_take  # noqa: E402

KEYS = ("hire_count", "animal_investment", "early_land_expansion",
        "cash_burn_rate_day5", "market_tx_frequency", "premium_crop_ratio")
PREMIUM_CROPS = ("STRAWBERRY", "MELON")
START_MONEY = 3000.0


class FeatureProbe:
    """Attach to an episode; call observe() each turn as the *other* player."""

    def __init__(self):
        self.model = OpponentModel()
        self.max_hands = {}
        self.money_at = {}
        self.quads_at = {}
        self.tiles_last = {}
        self.tx_steps = 0
        self.steps = 0

    def observe(self, obs, seat, my_sales=None):
        o = obs if isinstance(obs, dict) else dict(obs)
        step = int(o.get("step", 0) or 0)
        if not step:
            step = int(o.get("day", 0) or 0) * 24 + int(o.get("hour", 0) or 0)
        day = step // 24
        farms = o.get("farms") or []
        if len(farms) < 2:
            return
        opp = farms[1 - seat]
        shops = tuple((o.get("town") or {}).get("unlocked_shops") or ())
        inv = (o.get("market") or {}).get("inventory") or {}

        before = dict(self.model.sales)
        self.model.observe(inv, step, shops, my_sales or {})
        if any(self.model.sales.get(k, 0) != before.get(k, 0) for k in self.model.sales):
            self.tx_steps += 1
        self.steps += 1

        self.max_hands[day] = max(self.max_hands.get(day, 0), len(opp.get("hands") or []))
        self.money_at[day] = float(opp.get("money", 0) or 0)
        self.quads_at[day] = len(opp.get("unlocked_quadrants") or [])
        counts = {"animal": 0, "premium": 0, "crop": 0}
        for row in opp.get("tiles") or []:
            for t in row:
                if not isinstance(t, dict):
                    continue
                if "animal" in t:
                    counts["animal"] += 1
                elif t.get("kind") == "PLANT":
                    counts["crop"] += 1
                    if t.get("crop") in PREMIUM_CROPS:
                        counts["premium"] += 1
        self.tiles_last = counts

    def vector(self):
        days = sorted(self.max_hands) or [0]
        hire = sum(self.max_hands.values()) / max(len(self.max_hands), 1)
        d5 = min(5, max(days))
        burn = (START_MONEY - self.money_at.get(d5, START_MONEY)) / 5.0
        return {
            "hire_count": hire,
            "animal_investment": float(self.tiles_last.get("animal", 0)),
            "early_land_expansion": float(self.quads_at.get(d5, 1)),
            "cash_burn_rate_day5": burn,
            "market_tx_frequency": self.tx_steps / max(self.steps, 1),
            "premium_crop_ratio": (self.tiles_last.get("premium", 0)
                                   / max(self.tiles_last.get("crop", 0), 1)),
        }
