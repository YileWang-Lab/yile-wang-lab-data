"""Opponent inventory tracker: what they are holding, and what is still coming.

`route/opponent.py` already recovers the opponent's SALES exactly, from the
public market inventory (`inv[t+1] = inv[t] + mine + theirs - town_take`). What
it never had was the other half of the balance sheet: what they have harvested
but not yet sold. That is the quantity `market_model.sale_value` needs for its
suppression term, because the term is signed on `N_them - N_us` and a forecast
of future PRODUCTION alone systematically understates `N_them` -- everything
already sitting in their shed is invisible to it.

Their shed is private. Their TILES are not, and the engine leaves every field
we need on them:

    PLANT   {crop, planted_day, yield_units, consecutive_unwatered, ...}
    ANIMAL  {animal, placed_day, yield_units, fed_today, pending_care_bonus,
             fertilizer_available, consecutive_unfed}

Within a day `yield_units` can only ever go DOWN, and only one thing takes it
down: HARVEST, which zeroes it (engine lines 464-471). Yield is added once a
night by `_daily_refresh_*`, and decay removes exactly one unit a night on a
crop past `max_lifespan_step`. So sampling every turn and summing the intra-day
drops measures their harvests exactly, and

    held(item) = harvested(item) - sold(item)

closes the balance. `fertilizer_available` flipping True -> False inside a day
is the same trick for FERTILIZER, which no other signal reaches at all.

Non-ongoing crops are DELETED by the harvest that empties them, so a tile that
vanishes has to be credited with the yield it was carrying, or every melon and
wheat harvest is missed.

TWO CORRECTIONS THE RAW BALANCE NEEDS
-------------------------------------
Measured against the simulator's private state (`dynamic/opp_state_test.py`),
the harvest side is EXACT -- its residual mirrors the sales side unit for unit.
Both corrections below are therefore about the sales side, which is blind in
exactly one place: the engine does not add a $1 sale to market inventory
(line 659), so a floored book hides every sale made into it.

1. FLOOR RECONCILIATION. While a book quotes $1 their sales are invisible, so
   `sold` freezes and `held` grows without limit -- MILK drifted 267 units that
   way. It is also the one regime where the answer does not matter: `slope()`
   is zero on a floored book, so nothing can be suppressed there. Assume they
   dump, which is what the floor makes rational for both players.

2. THE SHED CAP. `_drop_inventories_to_shed` keeps 100 items TOTAL across all
   products and DISCARDS the overflow every night. So no estimate of their
   holdings above ~100 in total is even physically possible, whatever the
   ledger says. Anything over the cap is rescaled away.

What survives those two is small by construction, which is the useful finding:
the opponent can never be sitting on a hoard. `N_them` in the suppression term
is dominated by what their TILES will still produce, not by what they hold.
"""
from collections import Counter

TURNS_PER_DAY = 24
SEASON_DAYS = 30

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


def _tile_item(tile):
    """The product this tile yields, or None."""
    a = tile.get("animal")
    if a:
        spec = ANIMALS.get(a)
        return spec["product"] if spec else None
    if tile.get("kind") == "PLANT":
        return tile.get("crop")
    return None


class OppState:
    """Track the opponent's harvests, sales and therefore their holdings.

    `observe(...)` must be called EVERY turn -- the intra-day yield drop is the
    measurement, and a skipped turn merges a harvest into a night refresh and
    loses it. Same requirement the sales inference already has.
    """

    SHED_CAP = 100

    __slots__ = ("harvested", "sold", "prev_tiles", "prev_day", "prev_hour",
                 "prev_money", "spent", "earned", "hist")

    def __init__(self):
        self.harvested = Counter()   # cumulative units taken off their tiles
        self.sold = Counter()        # cumulative units they put on the market
        self.prev_tiles = None       # {(x,y): (item, yield_units, fert_flag)}
        self.prev_day = -1
        self.prev_hour = -1
        self.prev_money = None
        self.spent = 0.0
        self.earned = 0.0
        self.hist = []               # (day, {item: cumulative harvested})

    # ------------------------------------------------------------- harvests
    def _snapshot(self, opp_farm):
        snap = {}
        tiles = (opp_farm or {}).get("tiles") or []
        for y, row in enumerate(tiles):
            for x, tile in enumerate(row):
                if not isinstance(tile, dict):
                    continue
                item = _tile_item(tile)
                if item is None:
                    continue
                snap[(x, y)] = (item, int(tile.get("yield_units", 0) or 0),
                                bool(tile.get("fertilizer_available", False)))
        return snap

    def observe(self, opp_farm, day, hour, market_inv=None, step=None,
                shops=(), my_sales=None):
        """One turn of observation. Market arguments are optional; pass them to
        keep the sales side of the balance up to date too."""
        snap = self._snapshot(opp_farm)
        prev = self.prev_tiles
        if prev is not None:
            same_day = (day == self.prev_day)
            for pos, (item, y_prev, f_prev) in prev.items():
                cur = snap.get(pos)
                if cur is None:
                    # Tile gone: a non-ongoing crop is deleted by the harvest
                    # that empties it, so its carried yield was taken.
                    if y_prev > 0:
                        self.harvested[item] += y_prev
                    continue
                _, y_now, f_now = cur
                drop = y_prev - y_now
                if drop > 0:
                    # Across a night boundary a single unit may be decay, not a
                    # harvest; inside a day nothing but HARVEST removes yield.
                    if not same_day and drop == 1:
                        pass
                    else:
                        self.harvested[item] += drop
                if f_prev and not f_now:
                    self.harvested["FERTILIZER"] += 1
        if day != self.prev_day:
            self.hist.append((day, dict(self.harvested)))
            if len(self.hist) > 12:
                del self.hist[0]
        self.prev_tiles = snap
        self.prev_day = day
        self.prev_hour = hour

        money = (opp_farm or {}).get("money")
        if money is not None:
            money = float(money)
            if self.prev_money is not None:
                d = money - self.prev_money
                if d > 0:
                    self.earned += d
                else:
                    self.spent += -d
            self.prev_money = money

    # ---------------------------------------------------------------- sales
    def reconcile(self, prices, n_hands=0):
        """Apply the two corrections above. Call once a turn, after
        `observe()` and `record_sales()`.

        `prices` is the public market price map; `n_hands` lets units in hand
        (not yet dropped to the shed) sit above the cap for the rest of the day.
        """
        for item, px in (prices or {}).items():
            if px is not None and float(px) <= 1.0 and self.harvested[item] > self.sold[item]:
                self.sold[item] = self.harvested[item]
        allowance = self.SHED_CAP + 4 * (1 + max(0, int(n_hands)))
        total = sum(max(0, self.harvested[k] - self.sold[k]) for k in self.harvested)
        if total > allowance and total > 0:
            excess = total - allowance
            for item in sorted(self.harvested, key=lambda k: -(self.harvested[k] - self.sold[k])):
                h = self.harvested[item] - self.sold[item]
                if h <= 0:
                    continue
                take = min(h, int(round(excess * h / float(total))))
                self.sold[item] += take

    def record_sales(self, per_step_sales):
        """Feed in the exactly-recovered per-step opponent sales from
        `route.opponent.OpponentModel.observe`."""
        for item, n in (per_step_sales or {}).items():
            self.sold[item] += n

    # ------------------------------------------------------------- holdings
    def held(self, item):
        """Units of `item` they have harvested but not yet sold.

        Clamped at zero: sales at the $1 floor are invisible to the inventory
        arithmetic, so `sold` can lag reality and drive the balance negative.
        """
        return max(0, self.harvested[item] - self.sold[item])

    def forecast_production(self, opp_farm, item, day, horizon_days=None):
        """Units of `item` their CURRENT tiles will still produce.

        Best case for them (assumes they feed, water and care everything),
        which is the conservative case for us: it never tells us the book is
        safer to sell into than it is.
        """
        if horizon_days is None:
            horizon_days = max(0, SEASON_DAYS - day)
        horizon_days = max(0, min(horizon_days, SEASON_DAYS - day))
        if horizon_days <= 0 or not opp_farm:
            return 0.0
        total = 0.0
        for row in opp_farm.get("tiles") or []:
            for tile in row:
                if not isinstance(tile, dict) or _tile_item(tile) != item:
                    continue
                a = tile.get("animal")
                if a:
                    spec = ANIMALS[a]
                    start = int(tile.get("placed_day", day)) + spec["first_yield_day"]
                    active = max(0, horizon_days - max(0, start - day))
                    # base 1 per interval, doubled by a banked CARE bonus
                    total += active * 2.0 / spec["interval"]
                    continue
                cd = CROPS.get(tile.get("crop"))
                if not cd:
                    continue
                age = day - int(tile.get("planted_day", day))
                if cd["ongoing"]:
                    done = 0
                    if age >= cd["first_yield_day"]:
                        done = (age - cd["first_yield_day"]) // max(1, cd["interval"]) + 1
                    left = max(0, cd["max_yield"] - done)
                    total += min(left, horizon_days / max(1, cd["interval"]))
                elif age < cd["max_yield_day"]:
                    total += min(cd["max_yield"], cd["max_yield_day"] - age)
        if item == "FERTILIZER":
            # Animals shed fertilizer unconditionally, one per animal per day.
            n = 0
            for row in opp_farm.get("tiles") or []:
                for tile in row:
                    if isinstance(tile, dict) and tile.get("animal"):
                        n += 1
            total += n * horizon_days
        return total

    def harvest_rate(self, item, lookback_days=6):
        """Units of `item` they have been taking off their tiles per day.

        Exact, because the harvest side of the ledger is exact. It is the only
        term that sees the two things the structural forecast structurally
        cannot: tiles they have not planted yet, and the FERTILIZE bonus, which
        doubles a night's accrual (engine line 800) and so doubles the lifetime
        output of an ongoing crop.
        """
        if len(self.hist) < 2:
            return 0.0
        d1, c1 = self.hist[-1]
        for d0, c0 in self.hist:
            if d1 - d0 <= lookback_days:
                break
        span = max(1, d1 - d0)
        return max(0.0, (c1.get(item, 0) - c0.get(item, 0)) / float(span))

    def supply(self, opp_farm, item, day, horizon_days=None, gain=1.0, blend=0.0):
        """N_them for `market_model.sale_value`: everything they can still put
        on the market.

        The structural read of their tiles UNDER-states the truth by roughly
        2.5x -- measured against their actual remaining sales it predicts 72.8
        strawberry against a true 192.7 -- because it cannot see tiles they
        have not planted yet, and because FERTILIZE doubles a night's accrual
        (engine line 800) and so doubles an ongoing crop's lifetime output.
        What it does have is RANK: correlation 0.66 to 0.82 against the truth
        on the five products that matter.

        A scalar `gain` fixes a bias; nothing fixes a lost correlation. So the
        bias is left for calibration to absorb and the forecast is kept
        structural. Extrapolating the exact observed harvest rate instead was
        tried and is worse in the way that counts: it cut the bias roughly in
        half and took strawberry's correlation from 0.66 to -0.00 and melon's
        from 0.80 to -0.04. `blend` keeps it reachable, defaulted off.
        """
        if horizon_days is None:
            horizon_days = max(0, SEASON_DAYS - day)
        horizon_days = max(0, min(horizon_days, SEASON_DAYS - day))
        structural = self.forecast_production(opp_farm, item, day, horizon_days)
        if blend:
            structural = max(structural,
                             blend * self.harvest_rate(item) * horizon_days)
        return self.held(item) + gain * structural
