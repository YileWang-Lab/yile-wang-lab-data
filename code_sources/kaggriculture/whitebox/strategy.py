"""Module 2 of 6 -- STRATEGY DECIDER.

One job: say what the farm should BE, never how to get there. Output is a
`Plan` -- target animal and crop counts, which quadrants to own, and which
phase of the season we are in. It reads the snapshot and nothing else, and it
issues no actions.

WHY TARGETS AND NOT ACTIONS. The tape's five variants are named for exactly
this object: `10c4s_3q` is 10 cows, 4 sheep, 3 quadrants. That is the whole
strategic content of a tape -- everything else in its 719 rows is execution.
Making it a first-class value means the portfolio can be searched (which
section 16 did, and found bucket 0 mis-assigned) without touching execution.

PHASES exist because the binding constraint changes three times in a season:
cash at the start, shed capacity and labour in the middle, and the clock at the
end. A single rule set that ignores that spends day 2 money on day 25 problems.
"""
import os
import os as _os_env

from whitebox import econ
try:
    from whitebox import opponent_model as OM
except Exception:
    OM = None

try:
    from whitebox import market_model as MM
    _MM0 = MM
except Exception:
    MM = None
    _MM0 = None

# Replay-derived schedule/target modules are intentionally not imported by the
# production strategy. Historical functions below remain readable for old
# experiments, but cannot be selected by `_whitebox_entry`.
_sched = None
_ryo = None
_pkg = None
try:
    from whitebox import horizon as HZ
except Exception:
    HZ = None
# Historical strategy functions below are unreachable from ``decide``. Keep
# their names defined without importing replay/package/behaviour modules into
# the production dependency graph.
_cplan = None
CROP_PLAN = ""
PKG_PLANT = PKG_ANIMAL = PKG_EXPAND = ""


def _pkg_crops(day):
    """Target tile counts for `day`, shaped by the planting package.

    The leader's structure is the baseline; a package re-weights it and then
    renormalises to the SAME total tile count, so every arm plants a farm of the
    same size and the comparison is about mix rather than about scale.
    """
    base = dict(_ryo.crops(day) or {}) if _ryo else {}
    spec = (_pkg.PLANTING.get(PKG_PLANT) if _pkg else None) or {"source": "ryo"}
    if spec.get("source") != "scale" or not base:
        return base
    w = spec.get("weights", {})
    scaled = {k: v * w.get(k, 0.6) for k, v in base.items()}
    for k, wt in w.items():
        if k not in scaled and wt > 1.0:
            scaled[k] = sum(base.values()) * 0.15 * wt
    tot = sum(scaled.values())
    if tot <= 0:
        return base
    keep = sum(base.values()) / tot
    return {k: v * keep for k, v in scaled.items() if v * keep >= 0.5}


def _pkg_animals(day):
    # v060_competitive_champion claims livestock should be DISABLED outright to
    # avoid early capital starvation: a COW is $400 against a $100 strawberry
    # seed, and the herd is bought in the window where tiles are still empty.
    # Testable in one flag rather than argued about.
    if os.environ.get("WB_NO_LIVESTOCK", "0") == "1":
        return {}
    spec = (_pkg.ANIMALS.get(PKG_ANIMAL) if _pkg else None) or {"source": "ryo"}
    if spec.get("source") == "fixed":
        base = _ryo.animals(day) if _ryo else {}
        ramp = min(1.0, max(0.0, (day - 1) / 12.0))
        import math
        return {k: int(math.ceil(v * ramp)) for k, v in spec["targets"].items() if v * ramp >= 1}
    return _ryo.animals(day) if _ryo else {}

# "replay"   -- targets read from `whitebox/schedule.py`, the median trajectory
#               of the top 40 seats in `replays/`. Generated, readable, and the
#               only version of these numbers that anyone measured.
# "computed" -- the same decisions derived from engine economics alone, with no
#               replay input. This is the one that has to work in the end; the
#               replay table is the reference it gets graded against.
SOURCE = "computed"

PORTFOLIOS = {
    # Provisional engine-only baseline. The joint bundle optimiser described in
    # WHITEBOX_ARCHITECTURE.md will replace this fixed target.
    "theory_v0": {"animals": {"COW": 6, "SHEEP": 4}, "quadrants": 3},
}
DEFAULT_PORTFOLIO = "theory_v0"

# Crop mix, as a share of plantable tiles. WHEAT is not grown for revenue -- it
# is animal feed, and an animal eats 1/day, so the wheat target is driven by
# herd size and days remaining, not by price.
# Derived, not chosen. `market_model.crop_mix` fills each crop to the larger of
# its trickle ceiling (town absorption x selling days) and its one-shot ceiling
# (units before the price halves), in descending base price. See
# `market_model.diversified_targets` for why the diversified basket is the
# higher-revenue allocation and not merely the safer one.
try:
    from whitebox import market_model as _MM0
    CROP_MIX = _MM0.crop_mix()
except Exception:
    CROP_MIX = {"MELON": 0.45, "STRAWBERRY": 0.30, "WHEAT": 0.25}

PHASE_OPEN = "open"        # buy the herd and the land; cash-bound
PHASE_BUILD = "build"      # fill tiles, grow the crew; labour-bound
PHASE_RUN = "run"          # steady production; shed- and market-bound
PHASE_ENDGAME = "endgame"  # clock-bound; see market.py

# An animal eats one WHEAT a day and two unfed nights lose it outright. Feed is
# therefore bought as a ROLLING BUFFER, not as a season total: the old
# `herd * days_left` asked for 345 units into a shed that holds 100 items in
# total, so the target was unreachable, the "sell surplus wheat" rule could
# never fire, and the buffer never actually covered anything.
# Measured 2026-08-25 against 193 ladder replays: at hour 23 mid-game the
# top-40 seats hold 11.9 shed items of which 7.6 are WHEAT, and they lose ~0
# produce to the end-of-day overflow discard (peak occupancy 33 of 100). This
# agent held 39.7 WHEAT out of 40.0 -- the feed buffer WAS the shed -- and
# destroyed 61.9 units a game. WHEAT is `free` policy (town takes 32.8 a day,
# price never crashes), so it can be bought the day it is needed; hoarding four
# days of it buys nothing and costs the room the produce needs at rollover.
# 4 days / cap 60 was the pre-2026-08-25 setting; 2 / 16 is confirmed +3,076
# paired margin (t +4.94) on 576 cells drawn from seeds neither the sequence
# search nor the parameter sweep ever saw. The gain is entirely in THEIR bank
# (-3,535, t -3.04; ours -459, t -0.64): we stop draining 40-60 WHEAT out of
# the town book, so wheat stays cheap and their wheat sales are worth less.
FEED_COVER_DAYS = int(_os_env.environ.get("WB_FEED_DAYS", "2"))
FEED_MAX = int(_os_env.environ.get("WB_FEED_MAX", "16"))


class Plan:
    __slots__ = ("phase", "portfolio", "target_animals", "target_quadrants",
                 "crop_mix", "wheat_needed", "cash_floor", "animal_budget",
                 "crop_targets", "execution_variant", "service_cash_floor",
                 "fertilizer_target", "paid_weed_turnover",
                 "survival_feed_hard_core")

    def __init__(self, phase, portfolio, target_animals, target_quadrants,
                 crop_mix, wheat_needed, cash_floor, animal_budget=1.0):
        self.phase = phase
        self.portfolio = portfolio
        self.target_animals = target_animals
        self.target_quadrants = target_quadrants
        self.crop_mix = crop_mix
        self.wheat_needed = wheat_needed
        self.cash_floor = cash_floor
        # Cash protecting already-observable husbandry obligations only.
        # ``cash_floor`` historically also bundled a fixed five-hand reserve;
        # a crew-conditioned optimiser must instead price every candidate
        # Fibonacci block explicitly and therefore reads this separated term.
        self.service_cash_floor = float(cash_floor)
        # Share of spendable cash that may go into livestock this turn. The herd
        # is bought over the first week, not in one step-0 order, because a tile
        # with no crop on it and no hand to work it earns nothing either.
        self.animal_budget = animal_budget
        # Tile COUNTS the farm should own, not shares. A share has no stopping
        # condition; a count does.
        self.crop_targets = {}
        # Optional isolated execution correction. Historical version wrappers
        # leave this unset and retain their recorded behaviour.
        self.execution_variant = None
        # Total fertilizer units justified for the current route, including
        # stock already held.  Zero keeps every historical version unchanged;
        # the isolated paid-input arm sets it from a public-equation solve.
        self.fertilizer_target = 0
        # Orthogonal live-state capability: price a weed together with the
        # current-market seed needed to reuse its released tile.  This is a
        # boolean rather than another execution-variant string so fertilizer,
        # routing and capital capabilities remain independently auditable.
        self.paid_weed_turnover = False
        # Optional operation-level survival constraint. Historical wrappers
        # retain their measured tile-bundle routing; a selected research arm
        # may require a positive-value urgent FEED to survive independently of
        # CARE/HARVEST/fertilizer work on the same animal.
        self.survival_feed_hard_core = False

    def __repr__(self):
        return ("Plan(%s, %s, animals=%s, quads=%d, wheat=%d, floor=%d)"
                % (self.phase, self.portfolio, self.target_animals,
                   self.target_quadrants, self.wheat_needed, self.cash_floor))


ENDGAME_START = 670        # HANDOFF section 38: the last 50 steps
PHASE_OPENING_END = 100    # the opening is fixed; everyone strong plays it alike
PHASE_MID_START = PHASE_OPENING_END


def feed_demand(snap, targets):
    """Wheat to hold right now, for the herd we HAVE PLUS the herd we are buying.

    Counting only placed animals is a deadlock: `market.steady_orders` bought
    feed only when `herd > 0`, and the herd only survived when feed existed, so
    the farm reached day 8 with $11, no animals and no wheat, having never
    issued a single `BUY_PRODUCT WHEAT`. Animals sitting in the shed waiting to
    be placed, and the shortfall against today's target, both eat tomorrow.
    """
    have = snap.me.animal_counts()
    placed = sum(have.values())
    in_shed = sum(int(snap.shed.get(k, 0) or 0) for k in econ.ANIMALS)
    incoming = sum(max(0, targets.get(k, 0) - have.get(k, 0) - int(snap.shed.get(k, 0) or 0))
                   for k in econ.ANIMALS)
    effective = placed + in_shed + min(incoming, 4)
    days = min(FEED_COVER_DAYS, max(1, snap.days_left))
    # Never ask for more than the shed can actually take alongside produce.
    return int(min(effective * days, FEED_MAX))


def _animal_budget(day):
    """Share of spendable cash livestock may take, by day.

    Flat 1.0 let the acquisition module put every spare dollar into animals the
    moment the schedule asked for any, which starves seed and crew on exactly
    the days the replay table shows winners buying both. The ramp mirrors the
    table: nothing on day 0 (the mined herd is still zero), a small share while
    the crop base goes in, most of it once production is paying.
    """
    if day <= 0:
        return 0.0
    if day <= 3:
        return 0.30
    return 0.80


def phase_of(snap):
    if snap.step >= ENDGAME_START:
        return PHASE_ENDGAME
    if snap.day <= 3:
        return PHASE_OPEN
    if snap.day <= 12:
        return PHASE_BUILD
    return PHASE_RUN


import os as _os2
PHASE_SWITCH = _os2.environ.get("WB_PHASE_SWITCH", "1") != "0"
OPP_TARGETS = _os2.environ.get("WB_OPP_TARGETS", "1") != "0"
RECOVERY_HEALTH = 1.5      # cash below this multiple of daily obligations -> recover


def cash_health(snap, feed_floor, crew_floor):
    """Cash as a multiple of what feed + a round of hires cost right now.

    Below 1.0 the existing floor already blocks new spending (`acquisition_orders`
    nets `money - cash_floor`), so this threshold sits ABOVE that -- it is a
    warning the floor cannot give, because the floor is binary (can we afford
    today) while this is a trend (are we bleeding toward it).
    """
    obligations = max(1.0, feed_floor + crew_floor)
    return float(snap.me.money) / obligations


FRONTRUN_LEAD_DAYS = int(_os2.environ.get("WB_FRONTRUN_LEAD", "3"))


TRIM_FACTOR = float(_os2.environ.get("WB_TRIM_FACTOR", "0.7"))
# The HORIZON target-trim A/B lives only in the historical leader strategy;
# `decide()` calls `_decide_computed` and never reaches it. Seal the old switch
# so production cannot accidentally enable an unqualified point estimate.
HORIZON_TARGETS = False


def opponent_adjusted_targets(snap, crop_targets):
    """Trim (never replace) a target count when the opponent will soon compete
    on it too.

    If they have NOTHING growing this item, the target is untouched (no
    competition risk visible). If their earliest SELLABLE date is within the
    lead window, the target is trimmed -- floored, never zeroed, because the
    crop is still worth planting (we can front-run their sale, see `market.py`),
    just not worth planting at FULL scale into a market we know is about to be
    shared. Bounded discount, same reasoning as section 42's "trim, do not
    replace": the leader's target structure is the proven half and this only
    shaves it.

    HORIZON, 2026-08-24. This used to call `earliest_available` -- first single
    tile ripe, in DAYS -- while `market.py` had already moved to section 45's
    `earliest_sellable`, which is volume-gated and shed-travel-corrected. Two
    decisions about the same opponent were reading two different opponents:
    planting reacted to one stray tile of theirs (the measured firing rate on
    WOOL was 42 samples against the volume-gated 10) while selling did not.
    They now read the same signal. `WB_HORIZON_TARGETS=0` restores the old
    call for an A/B.

    The lead window, volume threshold and trim factor are transparent constants
    over the public opponent state; no behaviour classifier overrides them.
    """
    if not OPP_TARGETS:
        return dict(crop_targets)
    trim = TRIM_FACTOR
    lead = FRONTRUN_LEAD_DAYS
    units = HZ.DEFAULT_MIN_UNITS if HZ is not None else 6
    if trim >= 1.0:
        return dict(crop_targets)

    if HORIZON_TARGETS and HZ is not None:
        hz = HZ.current(snap)
        out = {}
        for crop, n in crop_targets.items():
            try:
                hit = hz.threat_in(crop, lead, units)
            except Exception:
                hit = False
            out[crop] = int(round(n * trim)) if hit else n
        return out

    if OM is None:
        return dict(crop_targets)
    out = {}
    for crop, n in crop_targets.items():
        avail = OM.earliest_available(snap.opp, crop, snap.day)
        if avail is None:
            out[crop] = n
            continue
        out[crop] = int(round(n * trim)) if (avail - snap.day) <= lead else n
    return out


def _capacity_crop_targets(snap, plan):
    """Absolute tile counts from the symmetric market-capacity relaxation.

    A target quadrant contributes ``half*half - 1`` usable tiles because its
    centre-corner tile is shed access. Planned animals consume durable tiles;
    the remainder is allocated in descending base-price order, but each crop
    is capped at one player's half of the engine-derived season absorption or
    one-shot capacity. This converts output capacity to tiles with the crop's
    exact maximum yield, so a six-unit MELON bed is not treated like a
    four-unit STRAWBERRY bed.
    """
    if MM is None:
        return {}
    half = max(1, int(snap.board) // 2)
    usable = max(0, int(plan.target_quadrants) * (half * half - 1))
    usable = max(0, usable - sum(int(n or 0)
                                 for n in plan.target_animals.values()))
    left = usable
    out = {}
    for crop in sorted(plan.crop_mix,
                       key=lambda c: -econ.MARKET_PARAMS[c]["base"]):
        if left <= 0 or crop not in econ.CROPS:
            break
        units = 0.5 * float(MM.portfolio_ceiling(crop))
        per_tile = max(1, int(econ.CROPS[crop]["max_yield"]))
        cap = max(0, int(units // per_tile))
        take = min(left, cap)
        if take:
            out[crop] = take
            left -= take
    # If every modelled ceiling binds, leave the remaining tiles empty rather
    # than inventing negative-value output merely to fill land.
    return out


def decide(snap, portfolio=DEFAULT_PORTFOLIO, variant=None):
    """Snapshot -> Plan. Pure; no side effects, no actions."""
    plan = _decide_computed(snap, portfolio)
    if variant == "capacity_crops":
        plan.crop_targets = _capacity_crop_targets(snap, plan)
    elif variant == "shop_conditioned":
        # V57: present shops are known exactly; only future unlock identities
        # remain random. ``market_model.crop_mix`` integrates that finite
        # uncertainty analytically from the live step through step 718.
        plan.crop_mix = MM.crop_mix(snap=snap) if MM is not None else plan.crop_mix
        plan.portfolio = "%s:shop_conditioned" % plan.portfolio
    elif variant in ("inventory_execution", "inventory_execution_replan",
                     "crew_conditioned_inventory_execution"):
        # A certified purchase is a commitment only when the task layer adopts
        # the observable private inventory it created. No remembered plan is
        # needed: live crops plus seed stock are exact crop targets, and live,
        # shed and carried animals are exact placement/service targets.
        crops = {}
        for tile in snap.me.crops.values():
            crop = tile.get("crop")
            if crop in econ.CROPS:
                crops[crop] = crops.get(crop, 0) + 1
        for crop in econ.CROPS:
            qty = max(0, int(snap.seeds.get(crop, 0) or 0))
            if qty:
                crops[crop] = crops.get(crop, 0) + qty
        animals = snap.me.animal_counts()
        carried = snap.carried()
        for kind in econ.ANIMALS:
            animals[kind] = (max(0, int(animals.get(kind, 0) or 0))
                             + max(0, int(snap.shed.get(kind, 0) or 0))
                             + max(0, int(carried.get(kind, 0) or 0)))
        animals = {kind: qty for kind, qty in animals.items() if qty > 0}
        plan.crop_targets = crops
        total = float(sum(crops.values()))
        if total > 0:
            plan.crop_mix = {crop: qty / total
                             for crop, qty in sorted(crops.items())}
        plan.target_animals = animals
        plan.wheat_needed = feed_demand(snap, animals)
        if plan.phase != PHASE_ENDGAME:
            herd = sum(animals.values())
            feed_floor = econ.price("WHEAT", econ.MARKET_I0) * herd
            plan.cash_floor = (feed_floor
                               if variant == "crew_conditioned_inventory_execution"
                               else econ.hire_block_cost(0, 5) + feed_floor)
            plan.service_cash_floor = float(feed_floor)
        plan.portfolio = "%s:%s" % (plan.portfolio, variant)
    return plan


def opponent_crop_share(snap):
    """{item: share of the opponent's producing tiles}. Public information.

    Their tiles are fully visible, so what they are GROWING is knowable exactly
    even though their shed is not. That is the half of the opponent model that
    is reliable, and it is the half planting needs.
    """
    counts, total = {}, 0
    for t in snap.opp.crops.values():
        c = t.get("crop")
        if c:
            counts[c] = counts.get(c, 0) + 1
            total += 1
    for t in snap.opp.animals.values():
        a = t.get("animal")
        item = {"GOOSE": "EGG", "COW": "MILK", "SHEEP": "WOOL"}.get(a)
        if item:
            counts[item] = counts.get(item, 0) + 1
            total += 1
    return {k: v / float(total) for k, v in counts.items()} if total else {}


def differentiated_mix(snap, base_mix):
    """Re-weight the crop mix away from what the opponent is loaded on.

    Not diversification for its own sake. `market_model.plant_score` charges each
    crop its MEASURED front-run loss in proportion to the opponent's share of
    it, so the discount is large exactly where being second is fatal (-98% on
    STRAWBERRY) and near zero where it is not (-5% on EGG). A crop the opponent
    has ignored keeps its full value.
    """
    if MM is None:
        return dict(base_mix)
    share = opponent_crop_share(snap)
    scored = {}
    for crop in base_mix:
        scored[crop] = max(0.0, MM.plant_score(crop, share.get(crop, 0.0)))
    tot = sum(scored.values())
    if tot <= 0:
        return dict(base_mix)
    return {k: v / tot for k, v in scored.items()}


def _decide_from_leader(snap):
    """Targets read off the ladder leader's own farm, day by day.

    This is the STRUCTURE half of copying a strong player, and it is the half
    that transfers. Section 42 showed his ENDGAME does not transfer between
    tapes and the priority-order experiment showed his OPERATION ORDER does not
    transfer to a farm shaped differently from his -- his WATER-before-HARVEST
    is right on 33 strawberry beds and wrong on our handful. So take the shape,
    not the tactics: get the farm to look like his, and his tactics become
    applicable rather than merely copied.

    What the table says: eleven MELON from day 1 held to day 10 then dropped to
    zero by 13; STRAWBERRY to 33 beds by day 13, held to day 20; WHEAT ramping
    late to feed a herd that goes COW 2 -> 9 with SHEEP flat at 2-3.

    Still a white-box function: the table is measured data, and everything that
    acts on it below is arithmetic anyone can read.
    """
    day = snap.day
    herd = sum(snap.me.animal_counts().values())
    phase = phase_of(snap)
    tc = _pkg_crops(day)
    feed_floor = econ.price("WHEAT", econ.MARKET_I0) * herd
    crew_floor = econ.hire_block_cost(0, 5)

    # DYNAMIC PHASE SWITCH. The day-based phase (OPEN/BUILD/RUN/ENDGAME) says
    # nothing about whether the plan is actually AFFORDABLE right now -- it is
    # a calendar, not a read of the game. `cash_health` is the trend the
    # calendar cannot see: below RECOVERY_HEALTH, tilt planting toward the
    # fastest-cash crops (WHEAT/CARROT, both a 2-day cycle) and stop competing
    # for cash with new livestock, rather than continuing to chase day-N's
    # target structure on a bank that cannot afford it.
    health = cash_health(snap, feed_floor, crew_floor)
    recovering = PHASE_SWITCH and phase != PHASE_ENDGAME and health < RECOVERY_HEALTH
    if recovering:
        tc = dict(tc)
        for fast in ("WHEAT", "CARROT"):
            if fast in tc:
                tc[fast] = tc[fast] * 1.6

    # OPPONENT-AWARE TARGETS. Their tiles are exactly public; discount our
    # target counts by how loaded they already are on each crop.
    #
    # `crop_plan` supersedes this rather than stacking with it: it already puts
    # the opponent's growing supply into the projected inventory it prices
    # against, so trimming afterwards would charge for the same opponent twice.
    if CROP_PLAN and _cplan is not None:
        if CROP_PLAN == "free":
            room = len(getattr(snap.me, "empty", ()) or ()) + len(getattr(snap.me, "crops", {}) or {})
            n = max(0, min(room, 80))
        else:
            n = int(round(sum(tc.values())))
        got = _cplan.marginal_targets(snap, n)
        if got:
            tc = {k: float(v) for k, v in got.items()}
    else:
        tc = opponent_adjusted_targets(snap, tc)

    _tot = float(sum(tc.values()))
    mix = ({k: v / _tot for k, v in tc.items()} if _tot else dict(CROP_MIX))
    plan = Plan(phase=phase,
                portfolio="leader:ryo",
                target_animals=(_pkg_animals(day) if not recovering else {}),
                target_quadrants=((_pkg.EXPANSION.get(PKG_EXPAND) or {}).get("quadrants", 3)
                                  if _pkg else 3),
                crop_mix=mix,
                wheat_needed=feed_demand(snap, _pkg_animals(day)),
                cash_floor=0.0 if phase == PHASE_ENDGAME else (feed_floor + crew_floor),
                animal_budget=(0.0 if recovering else _animal_budget(day)))
    plan.crop_targets = {k: int(round(v)) for k, v in tc.items()}
    return plan


def _decide_from_replays(snap, portfolio):
    """Targets read straight off the mined schedule.

    Two numbers here are worth more than the rest of this module put together,
    and neither would have been guessed:

      CASH FLOOR. Strong seats run the bank down to $19-$46 for the first five
      days. The hand-picked floor this replaces was ~$270, which blocked exactly
      the early investment that the winners make -- the first build spent its
      whole stake on cows because the floor left nothing to reason with, and the
      second built nothing because the floor forbade it.
      HERD RAMP. COW 2 -> 8 across ten days, not 8 on step 0. A cow bought on
      day 0 and a cow bought on day 10 cost the same $400; the difference is
      that the day-0 one starves while the farm has no wheat.
    """
    day = snap.day
    herd = sum(snap.me.animal_counts().values())
    targets = _sched.target_animals(day)
    # The replay table says what winners GREW; the market model says what the
    # market can absorb. Use the model's basket as the target and let the
    # opponent's holdings tilt it, rather than copying a mix that was tuned
    # against a different opponent.
    mix = _MM0.crop_mix() if _MM0 is not None else (_sched.crop_mix(day) or dict(CROP_MIX))
    if PHASE_MID_START <= snap.step < ENDGAME_START:
        mix = differentiated_mix(snap, mix)
    phase = phase_of(snap)
    # The mined floor is what strong seats ACTUALLY ran at ($19 on day 3), not a
    # safety margin. Taken literally it is a floor with no breathing room, so it
    # is combined with one day's feed: going below that loses an animal, which
    # costs more than any purchase the extra cash could have made.
    # THE MINED CASH LINE IS AN ASPIRATION, NOT A FLOOR, and conflating the two
    # broke the whole mid-game. `schedule.cash_floor(day)` is what the winning
    # seats HELD on that day -- $1,757 by day 10, $13,112 by day 13, because
    # they were rich. Used as a spending floor on a farm holding $70 it makes
    # `money - floor` negative forever, so no wheat is ever bought, the animals
    # starve, the crops go unwatered and the farm is gone by step 400.
    #
    # The floor's only job is to stop us spending into insolvency, so it is
    # sized from OUR OWN obligations: one day of feed plus one round of hires.
    herd = sum(snap.me.animal_counts().values())
    feed_floor = econ.price("WHEAT", econ.MARKET_I0) * herd
    crew_floor = econ.hire_block_cost(0, 5)
    floor = 0.0 if phase == PHASE_ENDGAME else (feed_floor + crew_floor)
    return Plan(phase=phase,
                portfolio="replay:top40",
                target_animals=targets,
                target_quadrants=_sched.target_quadrants(day),
                crop_mix=mix,
                wheat_needed=feed_demand(snap, targets),
                cash_floor=floor,
                animal_budget=_animal_budget(day))


def _decide_computed(snap, portfolio=DEFAULT_PORTFOLIO):
    """The replay-free version. Same outputs, engine economics only."""
    spec = PORTFOLIOS.get(portfolio, PORTFOLIOS[DEFAULT_PORTFOLIO])
    phase = phase_of(snap)
    herd = sum(snap.me.animal_counts().values())

    # An animal eats one wheat a day. Carry a buffer, because running out costs
    # the animal (two unfed nights and it escapes, structure intact) and a lost
    # COW is $400 plus eight days of milk.
    wheat_needed = feed_demand(snap, spec["animals"])

    # Cash floor: never spend below what tomorrow's feed and crew cost.
    #
    # This number is why the first build banked $3,000: with a floor of $150 the
    # acquisition module put the entire opening stake into cows on step 0, and a
    # farm with no seed, no crew and no feed money never recovered. Labour is the
    # cheapest thing on the board -- five hires cost $12 against a cow's $400 --
    # so the floor reserves crew and seed money BEFORE capital goods, not after.
    # Sized against what the replays actually show, not intuition: strong seats
    # run at $19-$46 through day 5. The old value here was crew + seed + feed
    # reserves totalling ~$270, an order of magnitude above the evidence, and it
    # blocked the early investment that wins. The replay-free mode keeps only
    # the two reserves that protect against an outright loss -- one round of
    # hires, and one day of feed.
    crew_reserve = econ.hire_block_cost(0, 5)          # ~$12 for five hands
    feed_reserve = econ.price("WHEAT", econ.MARKET_I0) * herd
    cash_floor = 0 if phase == PHASE_ENDGAME else crew_reserve + feed_reserve

    plan = Plan(phase=phase,
                animal_budget=(0.55 if phase == PHASE_OPEN else 0.80),
                portfolio=portfolio,
                target_animals=dict(spec["animals"]),
                target_quadrants=spec["quadrants"],
                crop_mix=dict(CROP_MIX),
                wheat_needed=wheat_needed,
                cash_floor=cash_floor)
    plan.service_cash_floor = (0.0 if phase == PHASE_ENDGAME
                               else float(feed_reserve))
    return plan
