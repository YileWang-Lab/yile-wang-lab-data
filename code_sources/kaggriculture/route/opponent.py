"""Opponent modelling: infer what the opponent is doing and what they will dump.

Two independent signals, deliberately kept separate because they fail in
different ways:

1. STRUCTURAL -- the opponent's farm is fully public (`obs.farms[1-me]`), so
   their tiles can be read directly and their future output projected from the
   engine's own yield rules. Blind to anything already sitting in their shed.

2. BEHAVIOURAL -- their sales are *exactly* recoverable, not guessed. Within a
   step the engine applies both players' market orders and then the town's
   consumption, so

       inv[t+1] = inv[t] + my_sales[t] + their_sales[t] - town_take[t]

   and every term except `their_sales` is known to us: inventory is public, the
   town's take is computable from the unlocked shop list, and our own sales are
   what we issued. Rearranged, that is a direct per-step measurement of the
   opponent's selling. It is blind only to sales at the $1 floor, which the
   engine deliberately does not add to inventory.

The two are combined in `pressure()`: how much supply is coming versus how much
demand the town has left. Above 1.0 the market is heading for a glut and the
right move is to race the opponent to it; below 1.0, hold and let the price rise.
"""
from collections import Counter, deque

PRODUCTS = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK",
            "WOOL", "FERTILIZER"]
TOWN_CENTER_PRODUCTS = [p for p in PRODUCTS if p != "FERTILIZER"]

SHOP_PRODUCTS = {
    "BAKERY":         ("EGG", "WHEAT"),
    "PIZZA_SHOP":     ("MILK", "TOMATO", "WHEAT"),
    "BRUNCH_SPOT":    ("EGG", "WHEAT", "STRAWBERRY"),
    "YARN_STORE":     ("WOOL",),
    "ICE_CREAM_SHOP": ("STRAWBERRY", "MILK", "WHEAT"),
    "PET_CAFE":       ("CARROT",),
    "SMOOTHIE_SHOP":  ("STRAWBERRY", "MILK"),
    "FARMERS_MARKET": ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY"),
}
SHOP_INTERVAL = 4
CENTER_INTERVAL = 24
SEASON_STEPS = 720
TURNS_PER_DAY = 24

ANIMALS = {
    "GOOSE": {"first_yield_day": 4, "interval": 1, "max_held": 4, "product": "EGG"},
    "COW":   {"first_yield_day": 8, "interval": 2, "max_held": 6, "product": "MILK"},
    "SHEEP": {"first_yield_day": 6, "interval": 3, "max_held": 6, "product": "WOOL"},
}
CROPS = {
    "WHEAT":      {"first_yield_day": 2, "max_yield_day": 4, "interval": 0, "max_yield": 6, "ongoing": False},
    "CARROT":     {"first_yield_day": 2, "max_yield_day": 3, "interval": 0, "max_yield": 4, "ongoing": False},
    "TOMATO":     {"first_yield_day": 8, "max_yield_day": 8, "interval": 1, "max_yield": 4, "ongoing": True},
    "STRAWBERRY": {"first_yield_day": 10, "max_yield_day": 10, "interval": 2, "max_yield": 4, "ongoing": True},
    "MELON":      {"first_yield_day": 10, "max_yield_day": 12, "interval": 0, "max_yield": 6, "ongoing": False},
}


def town_take(item, step, shops):
    """Units of `item` the town removes from the market at `step`."""
    take = 1 if item in TOWN_CENTER_PRODUCTS and step % CENTER_INTERVAL == 0 else 0
    if step % SHOP_INTERVAL == 0:
        for shop in shops:
            products = SHOP_PRODUCTS.get(shop, ())
            if item in products:
                take += 2 if len(products) == 1 else 1
    return take


def remaining_town_demand(item, step, shops, horizon=None):
    """Total units the town will still absorb between `step` and season end.

    Assumes the current shop set persists. Shops keep unlocking (every 3 days up
    to 8 instances), so this is a floor on real demand, not an estimate."""
    end = SEASON_STEPS if horizon is None else min(SEASON_STEPS, step + horizon)
    total = 0
    for s in range(max(step, 0), end):
        total += town_take(item, s, shops)
    return total


class OpponentModel:
    def __init__(self, window_steps=96):
        self.prev_inv = None
        self.prev_step = None
        self.sales = Counter()                 # cumulative inferred opponent sales
        self.recent = deque(maxlen=window_steps)   # (step, {item: units})
        self.tile_history = deque(maxlen=8)    # (day, {role: count})

    # ------------------------------------------------------------ behavioural
    def observe(self, market_inv, step, shops, my_sales=None):
        """Call once per turn with the *current* market inventory."""
        my_sales = my_sales or {}
        if self.prev_inv is not None and self.prev_step is not None and step > self.prev_step:
            per_step = {}
            for item in PRODUCTS:
                delta = int(market_inv.get(item, 0)) - int(self.prev_inv.get(item, 0))
                taken = 0
                for s in range(self.prev_step, step):
                    taken += town_take(item, s, shops)
                theirs = delta + taken - int(my_sales.get(item, 0))
                if theirs:
                    per_step[item] = theirs
                    self.sales[item] += theirs
            if per_step:
                self.recent.append((step, per_step))
        self.prev_inv = dict(market_inv)
        self.prev_step = step

    def observed_rate(self, item, lookback_steps=96):
        """Opponent's recent net sales of `item`, in units per step."""
        if not self.recent:
            return 0.0
        latest = self.recent[-1][0]
        total, span = 0, 0
        for step, per in self.recent:
            if latest - step <= lookback_steps:
                total += per.get(item, 0)
                span = max(span, latest - step + 1)
        return total / max(span, 1)

    # -------------------------------------------------------------- structural
    def forecast_supply(self, opp_farm, item, day, horizon_days=6):
        """Units of `item` the opponent's *visible* tiles will produce over the
        next `horizon_days`. Assumes they feed and care everything, i.e. the
        best case for them and the safest case for us."""
        if not opp_farm:
            return 0.0
        total = 0.0
        for row in opp_farm.get("tiles", []):
            for tile in row:
                if not isinstance(tile, dict):
                    continue
                animal = tile.get("animal")
                if animal and ANIMALS.get(animal, {}).get("product") == item:
                    spec = ANIMALS[animal]
                    # base 1 + one banked CARE bonus per production
                    per_day = 2.0 / spec["interval"]
                    start = tile.get("placed_day", day) + spec["first_yield_day"]
                    live = max(0, min(horizon_days, day + horizon_days - max(start, day)))
                    total += per_day * live
                    total += tile.get("yield_units", 0)
                elif tile.get("kind") == "PLANT" and tile.get("crop") == item:
                    cd = CROPS[tile["crop"]]
                    age = day - tile.get("planted_day", day)
                    total += tile.get("yield_units", 0)
                    if cd["ongoing"]:
                        done = max(0, (age - cd["first_yield_day"]) // max(cd["interval"], 1) + 1)
                        left = max(0, cd["max_yield"] - done)
                        total += min(left, horizon_days / max(cd["interval"], 1))
                    elif age < cd["max_yield_day"]:
                        total += min(cd["max_yield"], cd["max_yield_day"] - age)
        return total

    def classify(self, opp_farm, day):
        """Coarse read of what they are playing, from public tiles alone."""
        counts = Counter()
        for row in (opp_farm or {}).get("tiles", []):
            for tile in row:
                if not isinstance(tile, dict):
                    continue
                if tile.get("animal"):
                    counts[tile["animal"]] += 1
                elif tile.get("kind") == "PLANT":
                    counts[tile["crop"]] += 1
                elif tile.get("kind") in ("COOP", "PASTURE"):
                    counts["EMPTY_STRUCTURE"] += 1
        animals = sum(counts[a] for a in ANIMALS)
        crops = sum(counts[c] for c in CROPS)
        self.tile_history.append((day, dict(counts)))
        built = animals + crops
        if built == 0:
            style = "passive"
        elif animals >= 2 * max(crops, 1):
            style = "animal-heavy"
        elif crops >= 2 * max(animals, 1):
            style = "crop-heavy"
        else:
            style = "balanced"
        tempo = 0.0
        if len(self.tile_history) >= 2:
            d0, c0 = self.tile_history[0]
            span = max(1, day - d0)
            tempo = (built - sum(c0.get(k, 0) for k in list(ANIMALS) + list(CROPS))) / span
        return {"style": style, "counts": dict(counts), "animals": animals,
                "crops": crops, "built": built, "tempo": tempo}

    # ------------------------------------------------------------------ fusion
    def pressure(self, opp_farm, item, day, step, shops, horizon_days=6):
        """Supply heading for the market vs demand the town has left.

        >1 means glut coming -- sell into it before they do. <1 means the town
        will out-eat supply and the price will rise -- hold."""
        horizon_steps = horizon_days * TURNS_PER_DAY
        demand = remaining_town_demand(item, step, shops, horizon=horizon_steps)
        structural = self.forecast_supply(opp_farm, item, day, horizon_days)
        behavioural = self.observed_rate(item) * horizon_steps
        supply = max(structural, behavioural)
        return supply / max(demand, 1.0)

    def reserve_scale(self, opp_farm, item, day, step, shops,
                      lo=0.65, hi=1.30, horizon_days=6):
        """Multiplier for our reserve price on `item`. Glut coming -> drop the
        reserve and race them to the market; scarcity -> raise it and hold."""
        p = self.pressure(opp_farm, item, day, step, shops, horizon_days)
        if p >= 1.0:
            frac = min(1.0, (p - 1.0) / 1.5)
            return 1.0 - (1.0 - lo) * frac
        frac = min(1.0, (1.0 - p) / 0.8)
        return 1.0 + (hi - 1.0) * frac
