"""Global resource valuation: what is the best thing to do with the next dollar?

`dynamic/opportunity.py` answers that question for ONE tile among crops. The
real competition is wider -- $400 is a cow, or four strawberry tiles, or two
days of a bigger crew, or a quarter of the next quadrant -- and those are the
decisions the 1,132-against-1,704 unit gap actually lives in.

    V(C, L, P, t) = max over feasible a of  ENPV(a) + V(C-c_a, L-l_a, P-p_a, t)
    ROI(a)        = ENPV(a) / Cost_upfront(a)

Solved greedily by ROI under the cash / tile / unit-turn constraints, which is
the standard knapsack heuristic and is what the per-turn budget can afford.

THREE THINGS THIS HAS THAT A FIXED-COUNT PORTFOLIO SEARCH CANNOT
----------------------------------------------------------------
1. ENDOGENOUS PRICE. Every yield is quoted through
   `market_model.realized_price`, so the sixth cow is valued against the milk
   book the first five already filled. A genome that stores TC_COW=5 prices all
   five identically and cannot know that milk floors at 76 units plus drain.

2. THE SUB-YIELD. Animals shed one fertilizer a day unconditionally, fed or
   not, and nothing in town buys fertilizer -- so its book never recovers and
   its value is entirely a question of who sells into it first. It is a real
   term in an animal's ENPV and it is the reason an animal can be worth keeping
   after its main product has floored.

3. THE FEED DECISION. FEED costs exactly 1 WHEAT per animal per day (engine
   line 510) and buys the CARE bonus, which doubles output. An UNFED but living
   animal still produces its base unit -- only the bonus is lost -- and
   `consecutive_unfed >= 2` is what kills, so alternate-day feeding survives at
   half the wheat. Full and half rations are therefore both evaluated and the
   better one is taken, which matters most exactly when the main book has
   floored and the bonus is worth nothing.
"""
import math

from dynamic import market_model as MM
from dynamic import opportunity as OPP

SEASON_DAYS = 30
TURNS_PER_DAY = 24
LAND_PRICES = [1000, 2000, 4000]
TILES_PER_QUADRANT = 25

ANIMALS = {
    "GOOSE": {"cost": 300, "first": 4, "interval": 1, "product": "EGG",
              "structure": "COOP", "build_turns": 1},
    "COW":   {"cost": 400, "first": 8, "interval": 2, "product": "MILK",
              "structure": "PASTURE", "build_turns": 1},
    "SHEEP": {"cost": 500, "first": 6, "interval": 3, "product": "WOOL",
              "structure": "PASTURE", "build_turns": 1},
}

# Unit-turns an animal costs per day: FEED, CARE, COLLECT_FERTILIZER, and a
# HARVEST on its production days.
ANIMAL_TURNS_PER_DAY = 3.0


def _fib(n):
    a, b = 1, 1
    for _ in range(max(0, n)):
        a, b = b, a + b
    return a


def hire_cost(n_already_today):
    return _fib(n_already_today)


# ------------------------------------------------------------- feed costing

def feed_cost(n_need, own_available, market_price, own_op_cost=0.0):
    """Cost_feed = min(need, own)*C_own + max(0, need-own)*P_market

    Wheat we grew is not free -- it cost unit-turns and a tile -- but it is
    already spent, so `own_op_cost` is the marginal cost of USING it rather than
    selling it, which is what it would have fetched. Passing the market price
    there makes own and bought wheat equivalent, which is what the engine's
    round-trip pricing implies; passing 0 treats grown wheat as sunk.
    """
    n_need = max(0.0, float(n_need))
    own = max(0.0, float(own_available))
    from_own = min(n_need, own)
    from_market = max(0.0, n_need - own)
    return from_own * own_op_cost + from_market * float(market_price)


# --------------------------------------------------------------- asset ENPV

def enpv_animal(animal, day, ctx, c_labor=13.0, wheat_price=None,
                own_wheat=0.0, n_same=0, ration="auto", risk_lambda=0.0,
                death_prob=0.0):
    """ENPV of buying one more `animal` today.

        sum_i ( Y_main,i * P_realized + Y_sub,i * P_realized ) - C_buy - sum_i C_feed

    `n_same` is how many of this animal we already have, so the marginal one is
    priced against the book the existing herd is already filling.
    """
    spec = ANIMALS.get(animal)
    if spec is None:
        return 0.0, {}
    days_left = SEASON_DAYS - 1 - day
    producing = max(0, days_left - spec["first"])
    if days_left <= 0:
        return 0.0, {}
    product = spec["product"]
    if wheat_price is None:
        wheat_price = ctx.market_price("WHEAT")

    best = None
    rations = ("full", "half") if ration == "auto" else (ration,)
    for r in rations:
        per_day = (2.0 if r == "full" else 1.0) / spec["interval"]
        units = per_day * producing
        # The herd already committed to this book comes first; ours is marginal.
        prior = n_same * per_day * producing
        px = ctx.realized(product, units, days_left, prior=prior)
        fert = float(days_left)                     # unconditional, fed or not
        fert_px = ctx.realized("FERTILIZER", fert, days_left,
                               prior=n_same * days_left)
        need = days_left * (1.0 if r == "full" else 0.5)
        cost_feed = feed_cost(need, own_wheat, wheat_price, wheat_price)
        turns = ANIMAL_TURNS_PER_DAY * days_left + spec["build_turns"] + 1
        if r == "half":
            turns -= 0.5 * days_left               # CARE is pointless unfed
        v = (units * px + fert * fert_px - spec["cost"] - cost_feed
             - c_labor * turns)
        if risk_lambda:
            var = npv_variance(units, px, ctx.slope_of(product),
                               ctx.n_them.get(product, 0.0), death_prob)
            v = risk_adjust(v, var, risk_lambda)
        row = {"ration": r, "units": units, "px": px, "fert_px": fert_px,
               "feed": cost_feed, "turns": turns, "enpv": v}
        if best is None or v > best["enpv"]:
            best = row
    return best["enpv"], best


def enpv_crop(crop, day, ctx, c_labor=13.0, n_pending=0.0, risk_lambda=0.0,
              death_prob=0.0):
    """ENPV of planting one more tile of `crop` today.

        sum_k Y_k * P_realized(Y_k) - C_seed - sum_i C_ops,i

    Land is not amortised in here: the tile is already owned when this is
    asked, and `enpv_land` values the quadrant by what it lets us plant.
    """
    units, turns, day_done = OPP.yield_plan(crop, day)
    if units <= 0:
        return 0.0, {}
    days_left = max(1, SEASON_DAYS - 1 - day)
    px = ctx.realized(crop, units, days_left, prior=n_pending)
    v = units * px - OPP.CROPS[crop]["seed"] - c_labor * turns
    if risk_lambda:
        var = npv_variance(units, px, ctx.slope_of(crop),
                           ctx.n_them.get(crop, 0.0), death_prob)
        v = risk_adjust(v, var, risk_lambda)
    return v, {"units": units, "px": px, "turns": turns, "done": day_done}


def enpv_land(n_extra, day, ctx, c_labor=13.0, best_crop_enpv=0.0,
              usable_tiles=None):
    """ENPV of unlocking the next quadrant.

    Worth exactly what we can actually plant in it -- the ENPV of the best crop
    times the tiles we could still serve -- minus the price. `usable_tiles` is
    the caller's honest estimate of how many of the 25 the crew can reach; the
    six refuted scaling experiments all assumed 25.
    """
    if n_extra >= len(LAND_PRICES):
        return 0.0, {}
    cost = LAND_PRICES[n_extra]
    n = TILES_PER_QUADRANT if usable_tiles is None else max(0, usable_tiles)
    v = n * best_crop_enpv - cost
    return v, {"cost": cost, "tiles": n, "per_tile": best_crop_enpv}


def enpv_hand(day, n_hired_today, value_per_turn):
    """ENPV of one more hand today: the turns it adds, priced at what the
    marginal turn is actually earning, minus its fib-priced wage."""
    wage = hire_cost(n_hired_today)
    return TURNS_PER_DAY * float(value_per_turn) - wage, {"wage": wage}


# --------------------------------------------------------- risk adjustment

def npv_variance(units, price, slope, opp_supply, death_prob=0.0,
                 opp_rel_error=0.5):
    """Var(NPV) for an asset that will sell `units` at about `price`.

    Two independent sources, both measured rather than posited:

    PRICE. The realised price depends on the opponent's remaining supply, and
    our estimate of that is biased low by roughly 2.5x with correlation 0.66 to
    0.82 (`dynamic/opp_state_test.py`). A relative error of ~0.5 on
    `opp_supply` moves the price by the book's own slope, so

        sigma_P = |P'| * opp_rel_error * opp_supply

    YIELD. A tile can be lost -- two consecutive unwatered nights make a weed,
    two unfed nights and the animal escapes -- which costs the whole asset:

        sigma_Y = death_prob * units

    The two are independent, so their variances add.
    """
    sigma_p = abs(slope) * opp_rel_error * max(0.0, opp_supply)
    var_price = (units * sigma_p) ** 2
    var_yield = (death_prob * units * price) ** 2
    return var_price + var_yield


def risk_adjust(enpv, variance, lam):
    """ENPV_risk = E[NPV] - lambda * Var(NPV).

    Variance is in dollars SQUARED, so lambda carries units of 1/dollars and is
    small: a $1,000 asset with a $500 standard deviation has Var = 250,000, and
    a lambda of 1e-4 charges it $25. Values in the 1e-5 to 1e-3 range are the
    ones worth scanning.
    """
    return enpv - float(lam) * float(variance)


def roi(enpv, upfront):
    """ROI(a) = ENPV(a) / Cost_upfront(a). Free actions sort first."""
    if upfront <= 0:
        return float("inf") if enpv > 0 else 0.0
    return enpv / float(upfront)


# ------------------------------------------------------------------ knapsack

class Candidate:
    __slots__ = ("kind", "what", "enpv", "cash", "turns", "tiles", "detail")

    def __init__(self, kind, what, enpv, cash, turns=0.0, tiles=0, detail=None):
        self.kind = kind
        self.what = what
        self.enpv = float(enpv)
        self.cash = float(cash)
        self.turns = float(turns)
        self.tiles = int(tiles)
        self.detail = detail or {}

    @property
    def roi(self):
        return roi(self.enpv, self.cash)

    def __repr__(self):
        return (f"<{self.kind}:{self.what} enpv={self.enpv:,.0f} "
                f"${self.cash:,.0f} roi={self.roi:.2f}>")


def density(c, cash_avail, tiles_avail, turns_avail):
    """ENPV per unit of the SCARCEST resource this action consumes.

    Ranking by ROI alone is wrong here and the arithmetic says so plainly: a
    WHEAT tile returns $125 on a $10 seed (ROI 12.5) where a MELON tile returns
    $923 on $80 (ROI 11.5), so ROI prefers wheat -- but the two consume the same
    ONE tile, and we end seasons with $97k unspent on 50 tiles. Cash is not the
    binding resource; tiles and unit-turns are.

    So each action is charged for the FRACTION it consumes of every resource,
    and scored per unit of that. Whichever resource is actually scarce dominates
    the denominator on its own, and the ranking follows the bottleneck as it
    moves through the season instead of being fixed in a genome.
    """
    load = 0.0
    if cash_avail > 0:
        load += c.cash / cash_avail
    elif c.cash > 0:
        return -float("inf")
    if tiles_avail > 0:
        load += c.tiles / float(tiles_avail)
    elif c.tiles > 0:
        return -float("inf")
    if turns_avail > 0:
        load += c.turns / float(turns_avail)
    elif c.turns > 0:
        return -float("inf")
    if load <= 1e-9:
        return float("inf") if c.enpv > 0 else 0.0
    return c.enpv / load


def knapsack(candidates, cash, tiles, turns, reserve=0.0, repeat=None):
    """V_knapsack(C, L): greedy multi-dimensional knapsack.

    Returns (total_enpv, [picked]). Ranked by `density` above, re-sorted as the
    remaining resources change so the bottleneck can shift mid-solve. `repeat`
    caps how many times one candidate may be taken; without it the greedy answer
    is degenerate, because the top item absorbs the whole budget while its own
    price feedback is only recomputed by the caller between turns.
    """
    spendable = max(0.0, cash - reserve)
    c0, t0, u0 = max(1.0, spendable), max(1, tiles), max(1.0, turns)
    picks = []
    total = 0.0
    taken = {}
    pool = [c for c in candidates if c.enpv > 0]
    while True:
        best = None
        best_d = 0.0
        for c in pool:
            if repeat is not None and taken.get((c.kind, c.what), 0) >= repeat:
                continue
            if c.cash > spendable or c.tiles > tiles or c.turns > turns:
                continue
            d = density(c, c0, t0, u0)
            if d > best_d:
                best, best_d = c, d
        if best is None:
            break
        picks.append(best)
        total += best.enpv
        spendable -= best.cash
        tiles -= best.tiles
        turns -= best.turns
        taken[(best.kind, best.what)] = taken.get((best.kind, best.what), 0) + 1
    return total, picks


def labour_shadow_price(candidates, cash, tiles, turns, wage,
                        delta_turns=TURNS_PER_DAY, reserve=0.0, repeat=None):
    """ENPV_labor: the marginal knapsack value of one more hand, net of wage.

        [ V(C, L+dL) - V(C, L) - dL*wage ] / dL     per hand, here per DAY

    Positive means the crew is the binding constraint and hiring pays. This is
    the honest replacement for a fixed HIRE_BUDGET_FRACTION, and for the
    MIN_CREW floor that measured -13k to -52k by hiring against no work.
    """
    v0, _ = knapsack(candidates, cash, tiles, turns, reserve, repeat)
    v1, _ = knapsack(candidates, cash, tiles, turns + delta_turns, reserve, repeat)
    return (v1 - v0) - wage


def bundle_roi(bundle, ctx, day, c_labor=13.0):
    """ROI of a SET of actions, with their internal trades netted out.

    The one real internal transaction in this game is wheat: a wheat tile in the
    bundle feeds an animal in the same bundle at no market cost, so the pair is
    worth more than the two priced apart. Everything else nets to zero because
    the engine quotes BUY_PRODUCT post-buy.
    """
    if not bundle:
        return 0.0, 0.0
    upfront = sum(c.cash for c in bundle)
    total = sum(c.enpv for c in bundle)
    wheat_units = sum(c.detail.get("units", 0.0) for c in bundle
                      if c.kind == "crop" and c.what == "WHEAT")
    animal_days = sum(c.detail.get("feed_days", 0.0) for c in bundle
                      if c.kind == "animal")
    saved = min(wheat_units, animal_days) * ctx.market_price("WHEAT")
    total += saved
    return total, roi(total, upfront)


# Tiles one hand can actually keep serviced. Measured rather than assumed: at
# 63 tiles the board wants ~102 op-turns a day and the crew that covers it is 12
# hands of 24 turns, so most of a hand goes to travel, not to ops.
TILES_PER_HAND = 5.0


def crew_needed(n_tiles):
    return math.ceil(max(0.0, n_tiles) / TILES_PER_HAND)


def reserve_cash(day, n_animals, crew, wheat_price, dry_days=2.0,
                 committed_tiles=0, floor=0.0):
    """Reserve = Days_dry_spell * Cost_daily_burn.

    Daily burn is the wheat the herd eats plus the crew's wage, so the reserve
    scales with the farm instead of being a fixed constant.

    TWO THINGS THIS HAS TO GET RIGHT, both learned by getting them wrong:

    * The crew must be the one the farm WILL need, not the one it has. Crew size
      is sized to the current task list, so on day 0 it is 1 and a reserve built
      from it is about $2. Spending against that buys 20 tiles on day 3 and then
      cannot afford a single hand to water them -- measured, the board went 20
      tiles on day 3 to 8 on day 9 and the paired margin fell 115,067.
    * It needs a FLOOR. The rest of the agent refuses to hire while
      `money - cost < SPEND_RESERVE`, so a reserve below that number does not
      merely under-save, it silently disables hiring altogether.
    """
    want = max(int(crew), crew_needed(committed_tiles))
    feed = n_animals * float(wheat_price)
    wages = sum(hire_cost(i) for i in range(max(0, want)))
    return max(float(floor), dry_days * (feed + wages))
