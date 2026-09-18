"""agent3 = agent2 + the market-timing scheduler and the fitted opponent model.

A COPY on purpose. `dynamic/search2.py` is running a GA whose workers re-exec
dynamic/agent2.py once per evaluation, so editing that file mid-search silently
corrupts the fitness signal. Everything here is additive on top of agent2 and
gated off by default, so agent3 with no parameters is agent2 exactly.

Fully dynamic scheduler -- NO tape, no recorded actions, no JSON payload.

Every action is derived at runtime from the board. The only thing taken from
the tape is its ECONOMIC TRAJECTORY (how many hands per day, when to buy land,
when to buy animals) -- read off as targets in planner/schedule_diff.py, not as
actions. Cloning the tape's ACTIONS was measured and failed decisively
(planner/bc_play.py: $288 against the tape's $89k, with a control proving the
network was correct and the failure was covariate shift). Cloning its
TRAJECTORY is a different object: it is 30 numbers, and a dynamic scheduler is
free to reach them however the actual board allows.

WHY THIS IS NOT THE TWO EXPERIMENTS THAT ALREADY FAILED TODAY.

The farm economy is a chain: land unlocks tiles -> tiles create seed demand ->
seeds create PLANT tasks -> PLANT tasks justify a crew -> the crew does the
work that fills the shed. route/agent.py sizes its crew to TODAY's task list,
which is circular: a small crew produces a small task list which justifies a
small crew. Measured, it hires 188 times to the tape's 277 and lands 67 PLANT
and 13 PLACE ops to the tape's 186 and 53, while its realised price per unit is
BETTER than the tape's ($89.7 vs $79.6) and its useful-op rate is higher
(44.5% vs 40.1%). It is not less efficient; it runs a farm two thirds the size,
well.

  planner/scale_sweep.py  raised the portfolio without raising the crew:
                          monotonically worse, -87,245 at 74 tiles.
  planner/v2_sweep.py     raised the crew without raising the portfolio:
                          -13k to -52k, the hands stood idle on fib-priced cash.

Each moved one end of the chain. The tape moves BOTH, in a specific order --
land on days 6 and 11, all 14 animals placed by day 11, then a flat ~12 hands a
day sustained to the end. That combination is what neither experiment tested,
and it is what this module follows.
"""
"""Route-planning agent.

Architecture: the *plan* (what goes on which tile, how many hands, when to buy)
is searched offline; the *route* is solved at the start of each day by
route/router.py and then followed. This replaces the greedy per-turn patrol in
agent/main.py, which measured 25% useful / 60% movement against the strongest
reference agent's 52% / 43%.

The daily route is solved from the observed state rather than baked into a
720-step tape, because weed spawns are seeded off a stream shared between both
farms (so a tape can never be reproduced exactly -- see HANDOFF pitfall #5).
Solving it fresh each morning keeps the routing win and stays robust to weeds,
escaped animals and refused hires.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from route.geom import (SHED_SET, SHED_TILES, SPAWN, dist, dist_to_shed,  # noqa: E402
                        quadrant_of, steps_between)
from route.opponent import OpponentModel  # noqa: E402
from route.router import TURNS_PER_DAY, Task, Unit, partition, plan_day  # noqa: E402
from dynamic.router2 import plan_day as plan_day2  # noqa: E402
from dynamic.router2 import task_value as _task_value2  # noqa: E402
from dynamic import market_model as MM  # noqa: E402
from dynamic.opp_state import OppState  # noqa: E402
from dynamic import task_value as TV  # noqa: E402
from dynamic import opportunity as OPP  # noqa: E402
from dynamic import enpv as EN  # noqa: E402
from dynamic import market_timing as MT  # noqa: E402
from dynamic import opp_predict as OPRED  # noqa: E402

# ------------------------------------------------------------ engine mirrors

CROPS = {
    "WHEAT":      {"seed": 10, "first_yield_day": 2, "max_yield_day": 4, "interval": 0, "max_yield": 6, "ongoing": False},
    "CARROT":     {"seed": 20, "first_yield_day": 2, "max_yield_day": 3, "interval": 0, "max_yield": 4, "ongoing": False},
    "TOMATO":     {"seed": 50, "first_yield_day": 8, "max_yield_day": 8, "interval": 1, "max_yield": 4, "ongoing": True},
    "STRAWBERRY": {"seed": 100, "first_yield_day": 10, "max_yield_day": 10, "interval": 2, "max_yield": 4, "ongoing": True},
    "MELON":      {"seed": 80, "first_yield_day": 10, "max_yield_day": 12, "interval": 0, "max_yield": 6, "ongoing": False},
}
ANIMALS = {
    "GOOSE": {"cost": 300, "structure": "COOP",    "first_yield_day": 4, "interval": 1, "max_held": 4, "product": "EGG"},
    "COW":   {"cost": 400, "structure": "PASTURE", "first_yield_day": 8, "interval": 2, "max_held": 6, "product": "MILK"},
    "SHEEP": {"cost": 500, "structure": "PASTURE", "first_yield_day": 6, "interval": 3, "max_held": 6, "product": "WOOL"},
}
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
TOWN_SHOP_SELL_INTERVAL = 4
TOWN_CENTER_SELL_INTERVAL = 24
LAND_ORDER = ["NE", "SW", "SE"]
LAND_PRICES = [1000, 2000, 4000]
SEASON_DAYS = 30
SHED_CAPACITY = 100
MAX_ORDERS = 10

# Roles claim tiles nearest-to-shed first, in descending ROLE_PRIORITY. Animals
# lead because they need 3-4 ops every single day plus a wheat delivery, so they
# are the tiles worth having closest to the shed (HANDOFF pitfall #10).
#
# Priority is not cosmetic. The queue is laid over tiles sorted by quadrant
# unlock order, so a role sitting behind a 50-tile portfolio is placed entirely
# in SW/SE and -- since we typically only unlock NW+NE -- never physically
# exists. WHEAT sat exactly there, which is why raising TC_WHEAT to 18 barely
# dented the ~316 wheat we were buying every season. Searchable for that reason.
ROLE_FILL_ORDER = ("COW", "SHEEP", "MELON", "STRAWBERRY", "WHEAT", "GOOSE")
ROLE_PRIORITY = {"COW": 0.95, "SHEEP": 0.90, "WHEAT": 0.80,
                 "MELON": 0.60, "STRAWBERRY": 0.50, "GOOSE": 0.10}

# ------------------------------------------------------------------- genome

TARGET_COUNTS = {"COW": 8, "SHEEP": 4, "MELON": 8, "STRAWBERRY": 16, "WHEAT": 12, "GOOSE": 0}
MAX_HANDS = 16

# The tape's economic trajectory, median over 6 seeds (planner/schedule_diff.py).
# Targets, not actions: hands wanted on each day, and the day each extra
# quadrant is bought. Followed only as far as cash actually allows.
CREW_SCHEDULE = (1, 5, 5, 6, 6, 6, 7, 9, 12, 13, 12, 13, 13, 12, 12, 9, 13, 10,
                 13, 13, 13, 13, 13, 13, 13, 12, 12, 12, 12, 11)
LAND_SCHEDULE = (6, 11, 99)     # day each extra quadrant is targeted
ANIMAL_DEADLINE = 12            # every animal placed by here, as the tape does
SCHEDULE_DRIVEN = 1             # 0 falls back to route/agent.py's demand sizing

# SEASON PLAN. A declarative target extracted from the tape by
# dynamic/seasonplan.py -- which tile holds which role, and the day it comes
# online -- NOT the tape's actions. 73 of its 75 tiles are identical across four
# seeds, so this is a plan rather than a reaction to one board.
#
# It carries the two things every scaling attempt tonight was missing. First the
# SHAPE: 27 STRAWBERRY / 20 MELON / 14 PASTURE / 12 WHEAT, against our searched
# 21/8/13/8 -- the tape runs 2.5x the melon (a deep book, and the only product
# where the front-run audit measured a positive price edge, +24.3) and gets 390
# wheat units from just 12 tiles by cycling them, where we get 116 from 8.
# Second the ORDER: cheap tiles first (day 0 is 12 melon at $80 and 7 wheat at
# $10), expensive strawberry at $100 deferred to days 11-12 once the third
# quadrant is open and cash exists. That ordering is a cash-flow sequence known
# to be feasible from $3,000, which is exactly what six refuted scaling
# experiments kept violating.
#
# SEASON_PLAN is {(x,y): (role, day)}; empty falls back to _build_layout.
SEASON_PLAN = {}
USE_PLAN = 0                    # 0 = ignore the plan entirely (formula layout)

# Density-preserving scheduler (dynamic/router2.py). 0 = route/router.py.
# route/router.py fits an over-subscribed day by dropping the lowest-value
# tasks one at a time, which spreads the shortfall across every tile. That is
# the wrong shape of sacrifice here: the engine kills a plant on its second
# consecutive unwatered night, so a tile served on 70% of days is a dead tile,
# and 73 tiles at 70% care is 73 losses where 50 at full care would be 50
# survivors. USE_TRIAGE abandons whole tiles instead, cheapest-value-per-turn
# first, and never abandons one whose asset dies today.
USE_TRIAGE = 0
KEEP_RATIO = 1.0                # fraction of crew capacity to plan against
DYNAMIC_VALUE = 0               # value tasks from tile state, not op name
PLAN_GATE_DAYS = 1              # honour the plan's come-online day
PLAN_SLACK = 0                  # allow planting this many days early
HIRE_BUDGET_FRACTION = 0.35
SPEND_RESERVE = 150
SURVIVAL_RESERVE_FRACTION = 1 / 3
WHEAT_FEED_BUFFER_MULT = 2.5
LAND_BUY_CASH_MULTIPLE = 1.6
ANIMAL_BUY_CAP_PER_TURN = 2
SEED_BATCH_PER_TURN = 4
BUY_ANIMALS_FIRST = 1
SHED_PANIC_FRACTION = 0.62
RAMP_START_DAY = 25
RAMP_END_DAY = 29
RESERVE_PRICE_SCALE = 1.0
COLLECT_FERT_VALUE = 200.0
# The placement errand is pure gain and always on. The top-up (sending an
# otherwise-idle unit to the nearest outstanding tile) is not: it lifted the
# vs-starter bank 37% but *cost* us head-to-head against the strongest
# reference, because the extra product lands in a market that opponent has
# already crashed. Left to the search to resolve.
IDLE_TOPUP = 1
IDLE_MAX_TRAVEL = 18
# Sale timing. Within a step the engine runs _process_market before
# _town_consume, so a sale placed on a step the town drains goes into the market
# *before* the drain lifts the price, while the same sale one step later goes in
# after it. Holding one step is worth most on the steep glut curves -- MELON and
# WOOL are quadratic above I0, MILK and STRAWBERRY linear -- which is exactly the
# set the strongest reference agent front-runs.
FRONT_RUN = 1
FRONT_RUN_ITEMS = ("MELON", "MILK", "STRAWBERRY", "WOOL")
TERMINAL_STEP = 680
# Opponent modelling. route/opponent.py recovers the opponent's per-step sales
# exactly from the public market inventory and projects their visible tiles
# forward; the ratio of that supply to the town's remaining demand scales our
# reserve price per product. A predicted glut also cancels the front-run hold --
# there is no point waiting one step for a better price if they are about to
# bury the market in the same product.
# Planting is throttled by a feedback signal rather than a tuned cap: if any
# living crop already missed a watering yesterday, the crew is already behind
# and planting more tiles just converts seed money into weeds. A plant that
# misses two consecutive waterings dies, so consecutive_unwatered >= 1 is the
# earliest honest warning. Measured: 25 of ~37 crop tiles ended the season as
# weeds before this existed.
PLANT_MISS_TOLERANCE = 0
# Whether surplus feed wheat may be sold at all while animals are alive.
# Buying feed and selling it back is pure loss on the order slots and the cash
# float even though the engine prices a round trip at par.
WHEAT_SELL_SURPLUS = 0
# MARGINAL-VALUE SELLING (dynamic/market_model.py). 0 keeps the fixed
# RESERVE_PRICE gate, which compares the quoted price against a constant.
#
# That constant answers the wrong question. Market inventory is an accumulator
# and _town_consume subtracts the same amount whatever we do, so a unit sold now
# clears every LATER sale by both players one slope lower, for the rest of the
# season. The value of selling is therefore
#
#     MV = P(inv) + alpha * |P'(inv)| * (N_them - N_us)
#
# and the sign of the second term is the whole story: pushing volume into a book
# we ourselves still have to sell into is self-harm, which is what the wheat-
# flooding and capped-book-flooding experiments were measuring. On WOOL at its
# usual late inventory the same $24 quote carries an MV of +343 if the opponent
# has 50 units still coming and -295 if we do -- a fixed reserve of 53 answers
# neither case.
#
# MV is compared against the SAME reserve the fixed gate uses, so this changes
# the valuation and not the thresholds.
# Measured, 3 seeds, us against kawa (dynamic/revenue_audit.py):
#
#   MILK   we sell 156 at $138, they sell 265 at $141  ->  margin  -15,789
#   the TAPE against the same opponent floods milk 248 units, both players
#   realise $40, and the margin on the product is -28.
#
# The tape does not win milk. It NEUTRALISES it, and that is worth +15,761
# because the deficit it erases is larger than the revenue it gives up. Same
# shape on STRAWBERRY: we realise $168 to their $188 over 166 units to their
# 274, for -23,625; crushing that book to ~$60 would leave -6,480.
#
# So the posture has to be signed, and MV already carries the sign:
#   N_them > N_us  -> SUPPRESS. Sell now, skip the front-run hold. Every unit
#                     costs them more than it costs us.
#   N_them < N_us  -> METER. Sell at the town's absorption rate so the book
#                     never runs away from us; we are the one who has to sell
#                     into it later.
# The earlier flooding experiments that measured negative all flooded by
# PRODUCING more or by buying to dump. This is neither: it is the same units,
# re-timed, and it costs nothing to try.
MV_MARKET = 0
MV_ALPHA = 1.0          # trust in the suppression term
MV_OPP_GAIN = 1.0       # scales N_them; the structural forecast under-reads ~2.5x
MV_SELF_GAIN = 1.0      # scales N_us
# WHERE THIS HAS TO ACT. Attributing every unit we offer to the branch that
# offered it (3 seeds, vs kawa) gives:
#
#     shed-panic dump  79%      terminal dump  19%      the price gate  2-3%
#
# The reserve price, the front-run hold and the opponent's reserve scale
# together govern one sale in forty. That is why every sell-policy sweep in
# this project has come back with identical rows: the gate is not binding, it
# is nearly dead code. The agent's real sell policy is "the shed passed 20% ->
# dump everything", which is also, by accident, why our realised $/unit is
# HIGHER than the tape's -- dumping in small frequent batches meters the book.
#
# So the posture is applied where the volume actually is: on a panic turn, sell
# in MV order and stop as soon as the shed is back under the threshold. The
# books the opponent out-supplies get dumped (suppression is what they are for);
# the books we out-supply are kept for later, subject to the 100-item cap that
# discards anything we fail to clear by nightfall.
MV_POSTURE = 1          # 0 = MV only re-prices the gate; 1 = it also sets timing
MV_METER_MULT = 1.0     # units per turn when metering, as a multiple of drain
MV_PANIC_ORDER = 0      # 1 = clear the shed in MV order, only as far as needed

# ECONOMIC TASK VALUE (dynamic/task_value.py). 0 keeps OP_VALUE, which ranks a
# day's work by op NAME: a melon harvest and a wheat harvest both score 900,
# though one is six units at $250 and the other six at $25. 1 prices every task
# through the live market instead, which is where the scheduler's own objective
#
#     J = sum_task V_task - lambda * C_move
#
# gets its V. Survival tasks (a plant one missed watering from being a weed, an
# animal one missed feed from escaping) stay ranked above every revenue
# comparison, because the engine's rule is absolute.
ECON_VALUE = 0
ECON_ALPHA = 1.0        # suppression trust inside the task price
ECON_LAMBDA = 0.0       # dollars charged per step of travel; 0 = router decides

# BUILD ORDER IN TIME, not in priority. Producing tiles by day 3 / 9 / 12, from
# the same $3,000 opening:
#
#     us     8 / 19 / 37       the tape   23 / 44 / 68
#
# and the tape is RICHER at day 12 too ($10.3k against our $1.5k), so this is
# not a cash trade-off we are choosing -- it is a ramp we never start. Two
# causes, both about WHEN a tile is planted rather than what is on it:
#
#  1. We buy STRAWBERRY seed at $100 a tile on day 0. Twenty-one of them is
#     $2,100 of a $3,000 opening, and none of it yields before day 12. The tape
#     spends day 0 on 12 melon at $80 and 7 wheat at $10 and defers strawberry
#     to days 11-12, once cash exists.
#  2. WHEAT sits at ROLE_PRIORITY 0.014, so its tiles are laid last, into
#     quadrants we never unlock. Wheat is the early-cash engine: $10 a tile,
#     first yield on day 2, six units by day 4, which is roughly 18x in four
#     days. Raising its PRIORITY instead costs -75,378, because that hands it
#     the near-shed tiles for the whole season; the tape gets 390 units out of
#     12 tiles by CYCLING them, which is a schedule, not a priority.
#
# DEFER_* holds a role off until cash can carry it. NURSE_CROP fills the tile
# in the meantime with something that pays before the real role is due -- wheat
# is non-ongoing, so the harvest that empties it deletes the plant and hands the
# tile back with no cleanup.
DEFER_STRAWBERRY = 0
DEFER_MELON = 0
#
# The same crop cycles at the OTHER end of the season too, and there the tile is
# free. `_last_plant_day` is 19 for strawberry and 17 for melon, but 25 for
# wheat: after day 17 any tile that dies is dead for the rest of the season,
# because its own role can no longer return anything. Our board loses 10 tiles
# over the last third (49 -> 39) where the tape holds ~70 flat. Replanting those
# with wheat costs $10 and displaces nothing, because nothing else can grow
# there any more.
# MEASURED, three disjoint seed sets against the 6-agent pool, paired margin:
#   NURSE_LATE + WHEAT   +1,768 (t=4.7, n=144)   +1,893 (t=6.6, n=240)
#                        +2,049 (t=9.3, n=360), 72% of paired seeds
# Controls: NURSE_LATE with no NURSE_CROP is exactly +0, and NURSE_CROP="MELON"
# is exactly +0 (melon's last plant day is 17, so it can never be the refill).
# Mechanism confirmed rather than assumed -- the two agents are identical
# through day 19 and then diverge, holding 4-5 more producing tiles to the end
# (day 27: 42 against 37) and lifting wheat output 245 -> 282.
#
# DEFER_* is the same idea at the other end and it does NOT work: strawberry is
# an ongoing crop with a 4-yield lifetime cap, so every day it is held back is a
# yield it never takes. -10,029 at day 8, -14,860 at day 11, -32,276 at day 14.
# Nursing recovers +4,000 to +6,000 of that but never the whole cost.
NURSE_CROP = "WHEAT"    # "" = leave a deferred tile empty; "WHEAT" = cycle it
NURSE_UNTIL_DAY = 0
NURSE_LATE = 1          # 1 = refill tiles whose own role is past its last day

# OPPORTUNITY-COST ALLOCATION (dynamic/opportunity.py). NURSE_LATE above is a
# hand-found instance of one rule:
#
#     V_task = V_self + V_suppress - V_opportunity
#     V_opportunity(tile, t) = max over feasible c of E[Profit(c, tile, t)]
#
# After day 19 nothing but WHEAT and CARROT can still be planted, so the
# feasible set collapses, V_opportunity goes to 0, and any positive-profit crop
# should be planted automatically. Hand-finding those windows does not scale;
# this computes the feasible set and each member's profit instead, and the same
# arithmetic immediately turned up two more that nobody had looked for --
# `_last_plant_day` below is keyed on max_yield_day where the engine's binding
# constraint is first_yield_day, so it refuses MELON from day 18 (it still makes
# its full 6 units through day 19) and WHEAT from day 26 (2 units, $100, on a
# $10 seed).
#
#   0  off; the static layout decides, as searched
#   1  fall back: keep the tile's searched role while it is feasible and
#      profitable, otherwise plant the best thing that still is. This is the
#      general form of NURSE_LATE and should reproduce it.
#   2  full: plant the argmax whenever it beats the searched role.
ALLOC_MODE = 1
ALLOC_LABOR = 13.0      # $/unit-turn at the margin; flat plateau over 13-17

# `_last_plant_day` below keys on max_yield_day, but the engine's binding
# constraint on HARVEST is first_yield_day -- max_yield_day only bounds how much
# accrues. The gap refuses plantings that would still pay:
#   MELON  17 -> 19 (still its full 6 units: the accrual window shuts at age 10)
#   WHEAT  25 -> 27 (2 units, ~$100, on a $10 seed and four unit-turns)
# The allocator IDENTIFIES those windows and the old bound then filters them out
# downstream, so this switch is what lets them actually be planted.
#
# MEASURED AND REFUTED: -1,546 (t=-7.0, n=288) on its own, -1,656 with the
# allocator, -2,085 with the hand-coded refill. Both windows have positive GROSS
# profit under `opportunity.expected_profit` and negative NET value in the game,
# so the flat $/unit-turn labour price understates what a late planting really
# costs -- it waters every day until harvest against a crew that is winding
# down, and it finishes inside the terminal liquidation window. Left off, and
# left reachable so the next person does not re-derive it.
TRUE_LAST_PLANT_DAY = 0

# GLOBAL RESOURCE VALUATION (dynamic/enpv.py). The allocator above chooses among
# CROPS for one tile. The real competition is wider -- $400 is a cow, or four
# strawberry tiles, or two days of a bigger crew, or a quarter of a quadrant:
#
#     V(C,L,P,t) = max over a of  ENPV(a) + V(C-c_a, L-l_a, P-p_a, t)
#
# ENPV_BUY replaces BUY_ANIMALS_FIRST / SEED_BATCH_PER_TURN /
# ANIMAL_BUY_CAP_PER_TURN / SPEND_RESERVE with that ranking. It does NOT touch
# the layout -- ALLOC_MODE=2 measured -53,163, so the searched layout's answer
# about WHERE a role belongs is kept. What changes is the ORDER cash is spent in
# when it is short (days 3-12, exactly where the tape pulls ahead) and the
# ability to DECLINE a purchase whose ENPV has gone negative: with 6 sheep
# already owned the seventh is worth -118, and the searched genome buys 7.
#
# Ranking is by ENPV per unit of the SCARCEST resource, not by ROI. A wheat tile
# is ROI 12.5 against melon's 11.5, but they consume the same one tile and
# return $125 against $923, and we end seasons with $97k unspent -- cash has
# never been the binding constraint here.
# ENPV_BUY replaces the searched throttle wholesale and measures -90,059. Every
# wholesale replacement in this project has: the genome's parameters are
# co-adapted, and a principled subsystem dropped in on top of them breaks the
# co-adaptation faster than its own correctness repays. The ONE change that has
# worked (ALLOC_MODE) is additive -- it acts only where the existing policy does
# nothing at all.
#
# ENPV_VETO is the subtractive form of the same discipline: keep the searched
# purchase order exactly as it is, and only DECLINE a purchase whose ENPV has
# gone negative. It can remove spending, never redirect it. The case it exists
# for is measurable: with six sheep already owned the seventh is worth -118
# against the wool book they have already filled, and the genome buys seven.
# MEASURED, three disjoint seed sets, paired margin against the 6-agent pool:
#   ENPV_VETO at ENPV_LABOR=8   +3,626 (t=3.4)  +4,619 (t=5.1)  +4,378 (t=4.6)
# L10 and L13 are on the same plateau but swing more between sets (+2,126 to
# +4,876); 8 is the stable point. Above ~20 the veto starts refusing purchases
# that pay and it turns sharply negative (-3,279 at 20, -27,650 at 30).
#
# NOTE: the veto needs `S["econ"]`, which is only built while ALLOC_MODE or
# ECON_VALUE is on. With ALLOC_MODE=0 it is silently inert -- measured as two
# byte-identical rows, which is the symptom section 21 warns about.
ENPV_BUY = 0
ENPV_VETO = 1           # 1 = refuse purchases with ENPV <= 0, keep the rest
ENPV_LABOR = 8.0        # $/unit-turn for the veto; ALLOC_LABOR=13 for crops
ENPV_DRY_DAYS = 2.0     # Reserve_cash = Days_dry_spell * Cost_daily_burn
ENPV_REPEAT = 6         # cap on identical picks per turn
# Mean-variance utility: ENPV_risk = E[NPV] - lambda*Var(NPV). Subtractive by
# construction, which is the shape that has worked here -- it can only make the
# veto more conservative, never redirect a dollar. The case for it is the veto's
# own instability: at ENPV_LABOR 10 and 13 it swings between +2,126 and +4,876
# across seed sets, which is what an unpenalised point estimate does when the
# quantity behind it is uncertain. Variance is in dollars squared, so lambda is
# small; 1e-5 to 1e-3 is the range worth scanning.
# MEASURED AND INERT: lambda 1e-5 fires on 0% of games, 1e-4 on 2% (+11), 1e-3
# on 31% (+228, t=0.5). The veto is a binary ENPV > 0 test, so a penalty small
# enough not to refuse everything is too small to flip the sign. Kept because it
# is the right object if ENPV is ever used for RANKING rather than a sign test.
ENPV_RISK_LAMBDA = 0.0
ENPV_DEATH_PROB = 0.0   # per-asset probability of losing the tile outright

# PURCHASE ORDER BY ENPV. The tape's own opening, read off its issued orders:
#
#   day 0   MELON x12, WHEAT x7, buy_WHEAT x9, HIRE x5, COW x2, SHEEP x2
#           -> 23 producing tiles by day 1, on $3,094 of a $3,000 opening
#   days 1-10  cash never above $1,534; it runs the whole ramp at near zero
#   day 11  cash jumps to $14,794 as the melon lands, and it buys 23 STRAWBERRY
#
# Twelve melon on day 0, against our TC_MELON of 8 for the WHOLE SEASON -- and
# melon is the one book that never recovers (30 units of season demand against
# 158 to the floor), so being first into it is the one place quota preemption
# is real.
#
# `_order_seeds` walks a hardcoded list, so when cash runs out it is WHEAT and
# STRAWBERRY that got bought and MELON that did not. This sorts the same lists
# by ENPV. It is not a replacement: batch sizes, per-turn caps and the reserve
# are untouched and the same total is spent. Only the sequence changes, and only
# where cash binds.
ENPV_ORDER = 0

# MARKET TIMING (dynamic/market_timing.py). `_process_market` runs before
# `_town_consume` in the same step, so a sale held across a town tick is quoted
# after the drain instead of before it, and the gain is closed form:
#
#     gain_per_unit(i) = |P'(q)| * d_tick(i)
#
# Derived at a mid-season book, against the hardcoded FRONT_RUN_ITEMS:
#
#     MILK        $6.30/unit      in the list
#     WOOL        $4.64           in the list
#     STRAWBERRY  $1.37           in the list
#     MELON       $0.00           IN THE LIST, and worth nothing -- no shop
#                                 sells melon, so its tick drain is 0 and
#                                 holding only donates a step to the opponent
#
# Holding is capped at 3 steps by the 4-step tick, so this cannot become the
# open-ended metering that measured -32,749.
MT_TIMING = 0           # 1 = hold by computed gain instead of the fixed list
MT_HOLD_THRESHOLD = 1.0  # $/unit below which holding is not worth the step
MT_QUEUE = 0            # 1 = give the 10 order slots to the highest total value

# FITTED OPPONENT SUPPLY (dynamic/opp_predict.py). Every price term consumes
# N_them, and the structural forecast under-reads it by ~2.5x. Ridge least
# squares on public features, held out BY GAME:
#
#     item         model bias / |err| / corr     structural bias / |err| / corr
#     STRAWBERRY      -0.9 /  11.3 / 0.99            -136.4 / 136.4 /  0.54
#     MILK             1.3 /  11.6 / 0.97             -75.7 /  75.7 /  0.65
#     WOOL             0.5 /  12.5 / 0.92             -47.7 /  48.0 /  0.80
#     WHEAT           16.1 /  75.1 / 0.75            -308.1 / 308.1 / -0.48
#
# Degrades gracefully: with no fitted theta it returns the structural forecast,
# so the caller is never worse off than agent2.
OPP_PREDICT = 0

# OPP_DUMP_VETO: the predictor as an extra SIGNAL, not as a price input.
#
# OPP_PREDICT above swaps the estimator of N_them, and N_them is an input to
# every price the agent computes -- so although `sale_value` itself is untouched,
# the whole price signal moves, and it measured -18,502. Both explanations for
# that were tested and refuted (re-calibrating ENPV_LABOR is monotonically
# worse; re-fitting on our own games is unchanged), which leaves the finding
# that the 2.5x under-read was LOAD-BEARING: it makes the agent behave as if the
# books were emptier than they are, and aggression is what it lacks.
#
# So this is the additive form. Prices keep the structural forecast exactly, and
# the prediction is consulted only to DECLINE: if the opponent's predicted
# supply of a product exceeds what the town can still absorb by OPP_DUMP_RATIO,
# that book is going to be flooded whatever we do, and buying more capacity to
# produce into it is throwing seed at a market that will be on the floor.
#
#     flood(i) = E[Q_opp(i)] / D_i(t, shops) > OPP_DUMP_RATIO   ->  veto role i
#
# Subtractive by construction: it can only remove a purchase, never redirect one
# and never move a price.
#
# MEASURED AND REFUTED, and the sign is the reason, not the calibration:
# -144,968 / -129,410 / -121,217 / -115,251 at ratios 1.0 / 1.5 / 2.5 / 4.0,
# monotone in the ratio, 0 or 1 paired wins in 240 at every setting.
#
# Two things are wrong with it. First the ratio is structurally above 1 for the
# low-drain books whatever the opponent does -- MELON's town demand is 1 unit a
# day, so E[Q_opp]/D explodes and the veto kills our highest-ENPV crop. Second,
# and fatally, the SIGN is backwards against the marginal-value rule:
#
#     MV = P + alpha*|P'|*(N_them - N_us)
#
# N_them > N_us makes the suppression term POSITIVE. A book the opponent is
# about to flood is worth MORE to us, not less, because every unit we put in
# ahead of them costs them more than it costs us. Declining to produce into it
# is the metering logic that measured -32,749. Section 19 says the same thing
# from the other direction: the tape WINS by flooding books, because at a
# crushed price level the larger producer comes out ahead.
#
# Left reachable and defaulted off. If it is ever revisited, the version worth
# testing is the opposite sign.
OPP_DUMP_VETO = 0
OPP_DUMP_RATIO = 1.5
OPP_MODEL = 1
OPP_SCALE_LO = 0.65
OPP_SCALE_HI = 1.30
OPP_HORIZON_DAYS = 6

RESERVE_PRICE = {
    "MELON": 70, "WOOL": 60, "MILK": 55, "STRAWBERRY": 45, "TOMATO": 20,
    "CARROT": 15, "EGG": 20, "WHEAT": 12, "FERTILIZER": 25,
}
SELL_PRIORITY_ORDER = ["MELON", "WOOL", "MILK", "STRAWBERRY", "TOMATO",
                       "CARROT", "EGG", "FERTILIZER", "WHEAT"]

OP_VALUE = {
    "FEED": 1000.0, "PLACE": 950.0, "HARVEST": 900.0, "WATER": 800.0,
    "CARE": 700.0, "BUILD_PASTURE": 600.0, "BUILD_COOP": 600.0,
    "PLANT": 500.0, "DIG": 400.0, "FERTILIZE": 300.0,
    "COLLECT_FERTILIZER": 200.0,
}

_GENOME_KEYS = ("MAX_HANDS", "SCHEDULE_DRIVEN", "ANIMAL_DEADLINE",
                "USE_PLAN", "PLAN_GATE_DAYS", "PLAN_SLACK",
                "USE_TRIAGE", "KEEP_RATIO", "DYNAMIC_VALUE",
                "HIRE_BUDGET_FRACTION", "SPEND_RESERVE",
                "SURVIVAL_RESERVE_FRACTION", "WHEAT_FEED_BUFFER_MULT",
                "LAND_BUY_CASH_MULTIPLE", "ANIMAL_BUY_CAP_PER_TURN", "SEED_BATCH_PER_TURN", "BUY_ANIMALS_FIRST",
                "SHED_PANIC_FRACTION", "RAMP_START_DAY", "RAMP_END_DAY",
                "RESERVE_PRICE_SCALE", "COLLECT_FERT_VALUE",
                "IDLE_TOPUP", "IDLE_MAX_TRAVEL", "FRONT_RUN", "TERMINAL_STEP",
                "OPP_MODEL", "OPP_SCALE_LO", "OPP_SCALE_HI", "OPP_HORIZON_DAYS",
                "PLANT_MISS_TOLERANCE", "WHEAT_SELL_SURPLUS",
                "MV_MARKET", "MV_ALPHA", "MV_OPP_GAIN", "MV_SELF_GAIN",
                "MV_POSTURE", "MV_METER_MULT", "MV_PANIC_ORDER",
                "ECON_VALUE", "ECON_ALPHA", "ECON_LAMBDA",
                "DEFER_STRAWBERRY", "DEFER_MELON", "NURSE_CROP", "NURSE_UNTIL_DAY",
                "NURSE_LATE", "ALLOC_MODE", "ALLOC_LABOR", "TRUE_LAST_PLANT_DAY",
                "ENPV_BUY", "ENPV_VETO", "ENPV_LABOR", "ENPV_DRY_DAYS",
                "ENPV_REPEAT", "ENPV_RISK_LAMBDA", "ENPV_DEATH_PROB",
                "ENPV_ORDER", "MT_TIMING", "MT_HOLD_THRESHOLD", "MT_QUEUE",
                "OPP_PREDICT", "OPP_DUMP_VETO", "OPP_DUMP_RATIO")


# Set to raise instead of warn when a sweep passes a key this agent does not
# have. Three separate measurements were wasted tonight on silently ignored
# parameters -- TERMINAL_STEP (which lives in route/agent.py and does not exist
# in the tape build), a mis-signed PLAN_GATE_DAYS guard, and a market sweep
# whose variants all returned byte-identical numbers. Identical rows across
# variants is the symptom; this makes the cause loud.
STRICT_PARAMS = 0


def configure(params):
    """Apply a searched genome. Mirrors agent/main.py's interface so the same
    search harness can drive this agent."""
    g = globals()
    known = set(_GENOME_KEYS) | {"RESERVE_PRICE", "STRICT_PARAMS"}
    known |= {"TC_" + r for r in ROLE_FILL_ORDER}
    known |= {"RP_" + r for r in ROLE_FILL_ORDER}
    known |= {"RES_" + k for k in RESERVE_PRICE}
    unknown = [k for k in params if k not in known]
    if unknown:
        msg = f"configure(): ignoring unknown parameters {sorted(unknown)}"
        if params.get("STRICT_PARAMS", STRICT_PARAMS):
            raise ValueError(msg)
        import sys as _sys
        print("WARNING " + msg, file=_sys.stderr)
    for key in _GENOME_KEYS:
        if key in params:
            g[key] = params[key]
    for role in ROLE_FILL_ORDER:
        key = "TC_" + role
        if key in params:
            TARGET_COUNTS[role] = int(params[key])
        rp = "RP_" + role
        if rp in params:
            ROLE_PRIORITY[role] = float(params[rp])
    if "RESERVE_PRICE" in params:
        RESERVE_PRICE.update(params["RESERVE_PRICE"])
    g["OP_VALUE"] = dict(OP_VALUE, COLLECT_FERTILIZER=float(COLLECT_FERT_VALUE))
    _reset_state()


S = {}


def _reset_state():
    S.clear()
    S.update({"layout": None, "day": -1, "tours": {}, "progress": {},
              "target_units": 1, "bought": {a: 0 for a in ANIMALS},
              "pending": [], "idle_target": {},
              "opp": OpponentModel(), "oppst": OppState(), "last_sales": {},
              "alloc": {}})


_reset_state()


def _fib(n):
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def _hire_cost(n_already_today):
    return _fib(n_already_today)


def _cum_hire_cost(n):
    return sum(_fib(i) for i in range(n))


# ------------------------------------------------------------------- layout

def _load_season_plan():
    """Read dynamic/season_plan.json into the {(x,y): (role, day)} form."""
    import json as _json
    path = os.path.join(_ROOT, "dynamic", "season_plan.json")
    if not os.path.exists(path):
        return {}
    try:
        raw = _json.load(open(path))["plan"]
    except Exception:
        return {}
    out = {}
    for k, v in raw.items():
        x, y = k.split(",")
        role = v["role"]
        # PASTURE in the plan means "an animal lives here"; the layout wants the
        # animal, and the tape's 14 pastures are its 6 cow / 8 sheep split.
        out[(int(x), int(y))] = (role, int(v["day"]))
    return out


def _plan_layout(board_size, plan):
    """Turn the extracted plan into a role map, splitting PASTURE into the
    tape's own cow/sheep mix by distance to the shed (cows first, being the
    cheaper and faster-yielding of the two)."""
    layout = {}
    pastures = []
    for pos, (role, day) in plan.items():
        if role == "PASTURE":
            pastures.append(pos)
        elif role in ("COOP",):
            layout[pos] = "GOOSE"
        else:
            layout[pos] = role
    pastures.sort(key=lambda t: (dist_to_shed(t), t[1], t[0]))
    n_cow = int(TARGET_COUNTS.get("COW", 6))
    for i, pos in enumerate(pastures):
        layout[pos] = "COW" if i < n_cow else "SHEEP"
    for y in range(board_size):
        for x in range(board_size):
            layout.setdefault((x, y), "EMPTY")
    return layout


def _build_layout(board_size):
    """Assign a role to every tile, nearest-to-shed first, quadrant by quadrant
    in the order land actually unlocks. Tiles past the end of the portfolio stay
    EMPTY -- never an animal, which is the filler bug that had the last search
    optimising around instant bankruptcy for 800+ generations (pitfall #7)."""
    quad_rank = {"NW": 0}
    for i, q in enumerate(LAND_ORDER):
        quad_rank[q] = i + 1
    tiles = [(x, y) for y in range(board_size) for x in range(board_size)]
    tiles.sort(key=lambda t: (quad_rank[quadrant_of(t[0], t[1], board_size)],
                              dist_to_shed(t), t[1], t[0]))
    tiles = [t for t in tiles if t not in SHED_SET or True]

    layout = {}
    queue = []
    for role in sorted(ROLE_FILL_ORDER, key=lambda r: (-ROLE_PRIORITY.get(r, 0.5), r)):
        queue.extend([role] * max(0, int(TARGET_COUNTS.get(role, 0))))
    for i, tile in enumerate(tiles):
        layout[tile] = queue[i] if i < len(queue) else "EMPTY"
    return layout


def _unlocked(farm, tile):
    x, y = tile
    return farm["tiles"][y][x] != "LOCKED"


# --------------------------------------------------------------- task build

def _last_plant_day(crop):
    """Latest day a fresh planting still returns something before day 29.

    HARVEST is gated on `first_yield_day` for both crop kinds (engine line 457);
    `max_yield_day` only bounds accrual, so using it here refuses plantings that
    would still return units. See TRUE_LAST_PLANT_DAY.
    """
    cd = CROPS[crop]
    if TRUE_LAST_PLANT_DAY or cd["ongoing"]:
        return SEASON_DAYS - 1 - cd["first_yield_day"]
    return SEASON_DAYS - 1 - cd["max_yield_day"]


def _in_fert_window(tile, crop, day):
    cd = CROPS[crop]
    age = day - tile["planted_day"]
    if cd["ongoing"]:
        return age >= cd["first_yield_day"] - 1
    return (cd["max_yield_day"] + 1) // 2 <= age <= cd["max_yield_day"]


def _should_harvest(tile, crop, day):
    cd = CROPS[crop]
    if tile.get("yield_units", 0) <= 0:
        return False
    age = day - tile["planted_day"]
    if age < cd["first_yield_day"]:
        return False
    if cd["ongoing"]:
        return True
    if day >= SEASON_DAYS - 2:
        return True
    return age >= cd["max_yield_day"] or tile["yield_units"] >= cd["max_yield"]


def _mk(pos, ops, carry=None, tile=None, day=0):
    if ECON_VALUE and S.get("econ") is not None:
        value = TV.value(tile, ops, day, S["econ"], OP_VALUE)
    elif DYNAMIC_VALUE and tile is not None:
        value = _task_value2(tile, ops, day, OP_VALUE)
    else:
        value = max(OP_VALUE.get(o[0], 100.0) for o in ops)
    return Task(pos, ops, carry=carry, value=value)


def _watering_debt(farm):
    """Living crop tiles that already missed a watering. Non-zero means the crew
    could not keep up yesterday."""
    debt = 0
    for row in farm["tiles"]:
        for tile in row:
            if isinstance(tile, dict) and tile.get("kind") == "PLANT" \
                    and tile.get("consecutive_unwatered", 0) >= 1:
                debt += 1
    return debt


def _build_tasks(farm, private, day, board_size):
    tiles = farm["tiles"]
    may_plant = _watering_debt(farm) <= PLANT_MISS_TOLERANCE
    seeds = dict(private.get("seeds") or {})
    shed = dict(private.get("shed") or {})
    avail_animal = {a: int(shed.get(a, 0)) for a in ANIMALS}
    tasks = []

    for pos, role in S["layout"].items():
        if role == "EMPTY":
            continue
        x, y = pos
        tile = tiles[y][x]
        if tile == "LOCKED":
            continue

        if role in ANIMALS:
            spec = ANIMALS[role]
            if tile is None:
                tasks.append(_mk(pos, [["BUILD_" + spec["structure"]]], tile=tile, day=day))
            elif isinstance(tile, dict) and tile.get("animal") == role:
                core = []
                if not tile.get("fed_today"):
                    core.append(["FEED"])
                if not tile.get("cared_today"):
                    core.append(["CARE"])
                if tile.get("yield_units", 0) > 0:
                    core.append(["HARVEST"])
                if core:
                    carry = {"WHEAT": 1} if ["FEED"] in core else None
                    tasks.append(_mk(pos, core, carry=carry, tile=tile, day=day))
                if tile.get("fertilizer_available"):
                    tasks.append(_mk(pos, [["COLLECT_FERTILIZER"]], tile=tile, day=day))
            elif isinstance(tile, dict) and tile.get("kind") == spec["structure"]:
                if avail_animal.get(role, 0) > 0:
                    avail_animal[role] -= 1
                    tasks.append(_mk(pos, [["PLACE", role]], carry={role: 1}, tile=tile, day=day))
            elif isinstance(tile, dict) and "animal" not in tile:
                tasks.append(_mk(pos, [["DIG"]], tile=tile, day=day))
            continue

        # crop role. On an EMPTY tile the role in force is the one whose day
        # has come -- possibly the nurse crop, possibly nothing yet.
        if tile is None:
            eff = _effective_role(role, day)
            if eff is None:
                continue
            role = eff
        cd = CROPS.get(role)
        if cd is None:
            continue
        if tile is None:
            plan_day = (S.get("plan") or {}).get(pos, (None, -1))[1]
            if PLAN_GATE_DAYS and plan_day >= 0 and day < plan_day - PLAN_SLACK:
                continue
            if may_plant and day <= _last_plant_day(role) and seeds.get(role, 0) > 0:
                seeds[role] -= 1
                # WATER must ride along in the same visit: _new_plant starts a
                # crop at consecutive_unwatered=1, so a seedling left unwatered
                # on its planting day is already a weed by the nightly refresh.
                tasks.append(_mk(pos, [["PLANT", role], ["WATER"]], tile=tile, day=day))
        elif isinstance(tile, dict) and tile.get("kind") == "PLANT":
            crop = tile["crop"]
            ops = []
            harvest = _should_harvest(tile, crop, day)
            terminal = harvest and not CROPS[crop]["ongoing"]
            if not terminal:
                if (not tile.get("watered_today")) and _in_fert_window(tile, crop, day) \
                        and tile.get("fertilized_until_day", -1) < day:
                    ops.append(["FERTILIZE"])
                if not tile.get("watered_today"):
                    ops.append(["WATER"])
            if harvest:
                ops.append(["HARVEST"])
            if ops:
                carry = {"FERTILIZER": 1} if ["FERTILIZE"] in ops else None
                tasks.append(_mk(pos, ops, carry=carry, tile=tile, day=day))
        elif isinstance(tile, dict) and tile.get("kind") == "WEED":
            if day <= _last_plant_day(role):
                tasks.append(_mk(pos, [["DIG"]], tile=tile, day=day))
    return tasks


# ------------------------------------------------------------- day planning

def _make_units(n_units, farmer_pos):
    """Hands hired at hour h are appended by that turn's market phase and first
    act at h+1. Only 10 market orders clear per turn, so hands 11+ land a turn
    later than the first ten."""
    units = [Unit(0, tuple(farmer_pos), 0)]
    for i in range(1, n_units):
        units.append(Unit(i, SPAWN, 1 if i <= 10 else 2))
    return units


def _size_crew(tasks, money, farmer_pos, day=0):
    """Crew for the day.

    With SCHEDULE_DRIVEN the size comes from CREW_SCHEDULE rather than from the
    length of today's task list, because demand-driven sizing cannot bootstrap
    (see the module docstring). Cash still caps it -- the fib ladder is real and
    a hand nobody can pay for is not hired -- but an empty task list no longer
    collapses the crew to one, which is the feedback loop that kept the farm at
    two thirds size.
    """
    cash_cap = 1
    budget = money * HIRE_BUDGET_FRACTION
    for h in range(1, int(MAX_HANDS) + 1):
        if _cum_hire_cost(h) <= budget:
            cash_cap = h + 1
        else:
            break
    if SCHEDULE_DRIVEN:
        want = CREW_SCHEDULE[min(day, len(CREW_SCHEDULE) - 1)]
        return max(1, min(want, cash_cap))
    if not tasks:
        return 1
    cash_cap = 1
    budget = money * HIRE_BUDGET_FRACTION
    for h in range(1, int(MAX_HANDS) + 1):
        if _cum_hire_cost(h) <= budget:
            cash_cap = h + 1
        else:
            break
    for n in range(1, cash_cap + 1):
        _, leftover = partition(tasks, _make_units(n, farmer_pos))
        if not leftover:
            return n
    return cash_cap


def _plan_day(farm, private, day, board_size):
    tasks = _build_tasks(farm, private, day, board_size)
    farmer_pos = tuple(farm["farmer"])
    n_units = _size_crew(tasks, farm["money"], farmer_pos, day)
    units = _make_units(n_units, farmer_pos)
    shed_stock = dict(private.get("shed") or {})
    if USE_TRIAGE:
        tours, _undone, dropped = plan_day2(units, tasks, shed_stock, day, KEEP_RATIO)
        # abandoned tiles must also stop pulling seed, or the cash leaks into
        # ground nobody will ever water
        S["dropped"] = dropped
    else:
        tours, _undone = plan_day(units, tasks, shed_stock)
        S["dropped"] = set()
    for tour in tours.values():
        tour["carry_list"] = sorted(tour["carry"].items())
    S["tours"] = tours
    S["progress"] = {i: {"carry_i": 0, "stop_i": 0, "op_i": 0} for i in tours}
    S["target_units"] = n_units


# ------------------------------------------------------------- route follow

def _unit_position(farm, idx):
    if idx == 0:
        return farm["farmer"]
    hands = farm.get("hands") or []
    return hands[idx - 1] if idx - 1 < len(hands) else None


def _op_valid(op, tile, inv, seeds):
    name = op[0]
    is_dict = isinstance(tile, dict)
    if name == "FEED":
        return is_dict and "animal" in tile and not tile.get("fed_today") and inv.get("WHEAT", 0) > 0
    if name == "CARE":
        return is_dict and "animal" in tile and not tile.get("cared_today")
    if name == "COLLECT_FERTILIZER":
        return is_dict and "animal" in tile and tile.get("fertilizer_available")
    if name == "HARVEST":
        return is_dict and tile.get("yield_units", 0) > 0
    if name == "WATER":
        return is_dict and tile.get("kind") == "PLANT" and not tile.get("watered_today")
    if name == "FERTILIZE":
        return is_dict and tile.get("kind") == "PLANT" and inv.get("FERTILIZER", 0) > 0
    if name == "PLANT":
        return tile is None and seeds.get(op[1], 0) > 0
    if name in ("BUILD_COOP", "BUILD_PASTURE"):
        return tile is None
    if name == "PLACE":
        return (inv.get(op[1], 0) > 0 and is_dict
                and tile.get("kind") == ANIMALS[op[1]]["structure"] and "animal" not in tile)
    if name == "DIG":
        return tile is not None and not (is_dict and "animal" in tile)
    return True


def _unit_action(idx, farm, private, board_size, claimed):
    raw = _unit_position(farm, idx)
    if raw is None:
        return ["PASS"]
    pos = (raw[0], raw[1])
    shed = private.get("shed") or {}
    seeds = private.get("seeds") or {}
    inventories = private.get("inventories") or [{}]
    inv = inventories[idx] if idx < len(inventories) else {}

    tour = S["tours"].get(idx)
    if not tour:
        return _idle_action(idx, farm, private, S["day"], pos, inv, claimed)
    prog = S["progress"][idx]

    while prog["carry_i"] < len(tour["carry_list"]):
        item, want = tour["carry_list"][prog["carry_i"]]
        prog["carry_i"] += 1
        have = int(shed.get(item, 0))
        take = min(int(want), have)
        if take > 0 and pos in SHED_SET:
            return ["PICKUP", item, take]

    tiles = farm["tiles"]
    while prog["stop_i"] < len(tour["stops"]):
        target, ops = tour["stops"][prog["stop_i"]]
        if pos != tuple(target):
            moves = steps_between(pos, target)
            if moves:
                return [moves[0]]
        tile = tiles[target[1]][target[0]]
        while prog["op_i"] < len(ops):
            op = ops[prog["op_i"]]
            prog["op_i"] += 1
            if _op_valid(op, tile, inv, seeds):
                return list(op)
        prog["stop_i"] += 1
        prog["op_i"] = 0
    return _idle_action(idx, farm, private, S["day"], pos, inv, claimed)



# ------------------------------------------------------ opportunistic filler

def _live_ops(role, tile, day, seeds, may_plant=True):
    """Work this tile has outstanding right now, ignoring who carries what.
    Inventory is checked separately by _op_valid at the moment of issue."""
    if role in ANIMALS:
        spec = ANIMALS[role]
        if tile is None:
            return [["BUILD_" + spec["structure"]]]
        if not isinstance(tile, dict):
            return []
        if tile.get("animal") == role:
            ops = []
            if not tile.get("fed_today"):
                ops.append(["FEED"])
            if not tile.get("cared_today"):
                ops.append(["CARE"])
            if tile.get("yield_units", 0) > 0:
                ops.append(["HARVEST"])
            if tile.get("fertilizer_available"):
                ops.append(["COLLECT_FERTILIZER"])
            return ops
        if tile.get("kind") == spec["structure"] and "animal" not in tile:
            return [["PLACE", role]]
        if "animal" not in tile:
            return [["DIG"]]
        return []

    if tile is None:
        role = _effective_role(role, day)
        if role is None:
            return []
    cd = CROPS.get(role)
    if cd is None:
        return []
    if tile is None:
        if may_plant and day <= _last_plant_day(role) and seeds.get(role, 0) > 0:
            return [["PLANT", role], ["WATER"]]
        return []
    if not isinstance(tile, dict):
        return []
    if tile.get("kind") == "PLANT":
        ops = []
        if not tile.get("watered_today"):
            ops.append(["WATER"])
        if _should_harvest(tile, tile["crop"], day):
            ops.append(["HARVEST"])
        return ops
    if tile.get("kind") == "WEED" and day <= _last_plant_day(role):
        return [["DIG"]]
    return []


def _pending_now(farm, private, day):
    """Every tile with outstanding work, recomputed once per turn. The engine
    applies all of a turn's unit actions after the agent returns, so farm state
    is frozen for the whole call and one scan serves every unit."""
    tiles = farm["tiles"]
    seeds = private["seeds"]
    may_plant = _watering_debt(farm) <= PLANT_MISS_TOLERANCE
    out = []
    for pos, role in S["layout"].items():
        if role == "EMPTY":
            continue
        tile = tiles[pos[1]][pos[0]]
        if tile == "LOCKED":
            continue
        ops = _live_ops(role, tile, day, seeds, may_plant)
        if ops:
            out.append((pos, ops))
    return out


def _free_structures(farm, animal, claimed):
    spec = ANIMALS[animal]
    out = []
    for pos, role in S["layout"].items():
        if role != animal or pos in claimed:
            continue
        tile = farm["tiles"][pos[1]][pos[0]]
        if isinstance(tile, dict) and tile.get("kind") == spec["structure"] and "animal" not in tile:
            out.append(pos)
    return out


def _idle_action(idx, farm, private, day, pos, inv, claimed):
    """What a unit does on a turn its routed tour has no work for.

    Pure upside: it only ever replaces a PASS. It also closes the animal
    build-out lag -- a cow bought at hour 3 lands in the shed at hour 4, long
    after the morning route was solved, so without this it sits there until
    tomorrow's plan and the herd comes online ~10 days late.
    """
    tiles = farm["tiles"]
    shed = private["shed"]
    seeds = private["seeds"]

    carried = next((a for a in ANIMALS if inv.get(a, 0) > 0), None)
    if carried:
        spots = _free_structures(farm, carried, claimed)
        if spots:
            target = min(spots, key=lambda p: (dist(pos, p), p))
            claimed.add(target)
            if pos == target:
                return ["PLACE", carried]
            return [steps_between(pos, target)[0]]
    else:
        for a in ("COW", "SHEEP", "GOOSE"):
            if int(shed.get(a, 0)) <= 0 or not _free_structures(farm, a, claimed):
                continue
            if pos in SHED_SET:
                return ["PICKUP", a, 1]
            target = min(SHED_TILES, key=lambda p: (dist(pos, p), p))
            return [steps_between(pos, target)[0]]

    if not IDLE_TOPUP:
        S["idle_target"].pop(idx, None)
        return ["PASS"]
    sticky = S["idle_target"].get(idx)
    candidates = S.get("pending") or ()
    best, best_ops, best_d = None, None, None
    for tpos, ops in candidates:
        if tpos in claimed:
            continue
        tile = tiles[tpos[1]][tpos[0]]
        usable = [o for o in ops if _op_valid(o, tile, inv, seeds)]
        if not usable:
            continue
        d = dist(pos, tpos)
        if d > IDLE_MAX_TRAVEL:
            continue
        if tpos == sticky:
            d -= 2  # mild hysteresis so a unit finishes the trip it started
        if best_d is None or d < best_d:
            best, best_ops, best_d = tpos, usable, d
    if best is None:
        S["idle_target"].pop(idx, None)
        return ["PASS"]
    claimed.add(best)
    S["idle_target"][idx] = best
    if pos == best:
        return list(best_ops[0])
    return [steps_between(pos, best)[0]]


# ----------------------------------------------------------------- market

def _placed_animals(farm):
    n = 0
    for row in farm["tiles"]:
        for tile in row:
            if isinstance(tile, dict) and "animal" in tile:
                n += 1
    return n


def _ramp(day):
    if day < RAMP_START_DAY:
        return 1.0
    if day >= RAMP_END_DAY:
        return 0.0
    span = max(1, RAMP_END_DAY - RAMP_START_DAY)
    return max(0.0, 1.0 - (day - RAMP_START_DAY) / span)


def _alloc_role(role, day):
    """Opportunity-cost choice of crop for an EMPTY tile, or None.

    Cached per (role, day): the answer depends only on the day's market, which
    is fixed once `S["econ"]` is built for the morning.
    """
    ctx = S.get("econ")
    if ctx is None:
        return role
    key = (role, day)
    if key in S["alloc"]:
        return S["alloc"][key]

    def price_of(crop):
        return ctx.unit_price(crop)

    static = 0.0
    if role in OPP.CROPS and day <= OPP.last_plant_day(role):
        static = OPP.expected_profit(role, day, price_of(role), ALLOC_LABOR)
    if ALLOC_MODE == 1 and static > 0.0:
        out = role
    else:
        cand, profit = OPP.best(day, price_of, ALLOC_LABOR)
        if static > 0.0 and profit <= static:
            out = role
        else:
            out = cand
    S["alloc"][key] = out
    return out


def _effective_role(role, day):
    """The role this EMPTY tile should be planted with today.

    None means "not yet" -- the tile is being held for a role whose day has not
    come, and nothing should be bought or scheduled for it.
    """
    if role in ANIMALS:
        return role
    if ALLOC_MODE:
        return _alloc_role(role, day)
    start = 0
    if role == "STRAWBERRY":
        start = int(DEFER_STRAWBERRY)
    elif role == "MELON":
        start = int(DEFER_MELON)
    if day >= start:
        if (NURSE_LATE and NURSE_CROP and day > _last_plant_day(role)
                and day <= _last_plant_day(NURSE_CROP)):
            return NURSE_CROP
        return role
    if NURSE_CROP and day <= int(NURSE_UNTIL_DAY):
        # Only worth it if the nurse crop finishes before the real role is due;
        # otherwise the tile is still occupied on the day it is wanted.
        cd = CROPS.get(NURSE_CROP)
        if cd and day + cd["max_yield_day"] + 1 <= start:
            return NURSE_CROP
    return None


def _role_demand(farm, day):
    """Seeds and animals still wanted by the layout, on unlocked land."""
    want = {}
    for pos, role in S["layout"].items():
        if role == "EMPTY" or not _unlocked(farm, pos):
            continue
        x, y = pos
        tile = farm["tiles"][y][x]
        if role in ANIMALS:
            if not (isinstance(tile, dict) and "animal" in tile):
                want[role] = want.get(role, 0) + 1
        elif tile is None:
            eff = _effective_role(role, day)
            if eff is None or day > _last_plant_day(eff):
                continue
            if pos in (S.get("dropped") or ()):
                continue
            want[eff] = want.get(eff, 0) + 1
    return want


def _enpv_rank(names, farm, private, day, kind):
    """`names` sorted by the ENPV of the next unit, best first. Falls back to
    the given order when no market context exists."""
    ctx = S.get("econ")
    if ctx is None:
        return list(names)
    shed = private.get("shed") or {}
    wheat_px = ctx.market_price("WHEAT")
    own_wheat = float(shed.get("WHEAT", 0))
    scored = []
    for n in names:
        if kind == "animal":
            have = _animal_count(farm, n) + int(shed.get(n, 0))
            v, _ = EN.enpv_animal(n, day, ctx, c_labor=ENPV_LABOR,
                                  wheat_price=wheat_px, own_wheat=own_wheat,
                                  n_same=have)
        else:
            v, _ = EN.enpv_crop(n, day, ctx, c_labor=ENPV_LABOR,
                                n_pending=_pending_units(farm, n, day))
        scored.append((v, n))
    scored.sort(key=lambda r: -r[0])
    return [n for _, n in scored]


def _order_animals(orders, money, want, shed, seeds, shed_used, order=None):
    """Animals are the compounding asset -- an animal yields every day from
    placement to the end of the season -- but seed for a strawberry planted on
    day 1 also compounds. Which claim on early cash wins is genuinely unobvious,
    so BUY_ANIMALS_FIRST is left to the search rather than guessed here.
    Throttled per turn, and capped by shed room since a bought animal sits in
    the shed until placed."""
    for role in (order or ("COW", "SHEEP", "GOOSE")):
        if len(orders) >= MAX_ORDERS:
            break
        need = want.get(role, 0) - int(shed.get(role, 0))
        if need <= 0:
            continue
        cost = ANIMALS[role]["cost"]
        room = max(0, SHED_CAPACITY - shed_used - 5)
        afford = int(max(0, money - SPEND_RESERVE) // cost)
        n = int(min(need, afford, room, ANIMAL_BUY_CAP_PER_TURN))
        if n > 0:
            orders.append(["BUY_ANIMAL", role, n])
            money -= n * cost
    return money


def _order_seeds(orders, money, want, shed, seeds, shed_used, order=None):
    """Seeds never enter the shed, so they cost no capacity -- only cash.
    Batched per turn rather than bought as a whole portfolio at once."""
    for crop in (order or ("WHEAT", "STRAWBERRY", "MELON", "CARROT", "TOMATO")):
        if len(orders) >= MAX_ORDERS:
            break
        need = want.get(crop, 0) - int(seeds.get(crop, 0))
        if need <= 0:
            continue
        cost = CROPS[crop]["seed"]
        afford = int(max(0, money - SPEND_RESERVE) // cost)
        n = int(min(need, afford, SEED_BATCH_PER_TURN))
        if n > 0:
            orders.append(["BUY_SEED", crop, n])
            money -= n * cost
    return money


def _opp_flood(item, day, shops):
    """E[Q_opp(i)] / (town demand still to come). Above 1 the book is heading
    for the floor on their supply alone, whatever we do."""
    theta = _load_theta().get(item)
    if not theta:
        return 0.0
    opp_farm = S.get("opp_farm")
    if opp_farm is None:
        return 0.0
    st = S["oppst"]
    x = OPRED.feature_row(item, opp_farm, day, st,
                          st.forecast_production(opp_farm, item, day))
    predicted = OPRED.predict(theta, x)
    demand = MM.drain_rate(item, shops) * max(1.0, SEASON_DAYS - day)
    return predicted / max(1.0, demand)


def _enpv_veto(want, farm, private, day, shops=()):
    """Drop roles whose next unit has negative ENPV, leaving the rest alone."""
    ctx = S.get("econ")
    if ctx is None or not want:
        return want
    shed = private.get("shed") or {}
    wheat_px = ctx.market_price("WHEAT")
    own_wheat = float(shed.get("WHEAT", 0))
    out = {}
    for role, n in want.items():
        if n <= 0:
            continue
        if role in ANIMALS:
            have = _animal_count(farm, role) + int(shed.get(role, 0))
            v, _ = EN.enpv_animal(role, day, ctx, c_labor=ENPV_LABOR,
                                  wheat_price=wheat_px, own_wheat=own_wheat,
                                  n_same=have, risk_lambda=ENPV_RISK_LAMBDA,
                                  death_prob=ENPV_DEATH_PROB)
        elif role in CROPS:
            v, _ = EN.enpv_crop(role, day, ctx, c_labor=ENPV_LABOR,
                                n_pending=_pending_units(farm, role, day),
                                risk_lambda=ENPV_RISK_LAMBDA,
                                death_prob=ENPV_DEATH_PROB)
        else:
            v = 1.0
        if v <= 0:
            continue
        if OPP_DUMP_VETO:
            item = ANIMALS[role]["product"] if role in ANIMALS else role
            if _opp_flood(item, day, shops) > OPP_DUMP_RATIO:
                continue
        out[role] = n
    return out


def _enpv_orders(orders, money, want, shed, seeds, shed_used, farm, day):
    """Spend cash in ENPV order, under a reserve sized to the daily burn.

    Returns the money left. Emits the same BUY_SEED / BUY_ANIMAL orders the
    fixed-throttle path does -- only the choice of which, and how many, differs.
    """
    ctx = S.get("econ")
    if ctx is None:
        return money
    free_tiles = sum(1 for pos, role in S["layout"].items()
                     if role != "EMPTY" and _unlocked(farm, pos)
                     and farm["tiles"][pos[1]][pos[0]] is None)
    turns_left = TURNS_PER_DAY * max(1, S.get("target_units", 1))
    placed = _placed_animals(farm)
    wheat_px = ctx.market_price("WHEAT")
    committed = sum(1 for pos, role in S["layout"].items()
                    if role != "EMPTY" and _unlocked(farm, pos)
                    and isinstance(farm["tiles"][pos[1]][pos[0]], dict))
    reserve = EN.reserve_cash(day, placed, S.get("target_units", 1), wheat_px,
                              dry_days=ENPV_DRY_DAYS,
                              committed_tiles=committed + free_tiles,
                              floor=SPEND_RESERVE)
    own_wheat = float(shed.get("WHEAT", 0))

    cands = []
    for role, n_want in want.items():
        if n_want <= 0:
            continue
        if role in ANIMALS:
            have = _animal_count(farm, role) + int(shed.get(role, 0))
            v, det = EN.enpv_animal(role, day, ctx, c_labor=ENPV_LABOR,
                                    wheat_price=wheat_px, own_wheat=own_wheat,
                                    n_same=have)
            room = max(0, SHED_CAPACITY - shed_used - 5)
            if v > 0 and room > 0:
                cands.append(EN.Candidate(
                    "animal", role, v, ANIMALS[role]["cost"],
                    turns=EN.ANIMAL_TURNS_PER_DAY * max(1, SEASON_DAYS - 1 - day),
                    tiles=1, detail={"feed_days": SEASON_DAYS - 1 - day}))
        elif role in CROPS:
            pending = _pending_units(farm, role, day)
            v, det = EN.enpv_crop(role, day, ctx, c_labor=ENPV_LABOR,
                                  n_pending=pending)
            if v > 0:
                cands.append(EN.Candidate("crop", role, v, CROPS[role]["seed"],
                                          turns=det.get("turns", 0), tiles=1,
                                          detail=det))
    if not cands:
        return money

    _, picks = EN.knapsack(cands, money, free_tiles, turns_left,
                           reserve=reserve, repeat=int(ENPV_REPEAT))
    batch = {}
    for c in picks:
        key = (c.kind, c.what)
        batch[key] = batch.get(key, 0) + 1
    for (kind, what), n in sorted(batch.items(), key=lambda kv: -kv[1]):
        if len(orders) >= MAX_ORDERS:
            break
        if kind == "animal":
            have = int(shed.get(what, 0))
            n = min(n, max(0, want.get(what, 0) - have))
            if n > 0:
                orders.append(["BUY_ANIMAL", what, n])
                money -= n * ANIMALS[what]["cost"]
        else:
            n = min(n, max(0, want.get(what, 0) - int(seeds.get(what, 0))))
            if n > 0:
                orders.append(["BUY_SEED", what, n])
                money -= n * CROPS[what]["seed"]
    return money


def _animal_count(farm, role):
    n = 0
    for row in farm["tiles"]:
        for tile in row:
            if isinstance(tile, dict) and tile.get("animal") == role:
                n += 1
    return n


def _pending_units(farm, crop, day):
    """Units of `crop` our own living tiles will still produce -- the `prior`
    that makes the next tile of it marginal rather than the first."""
    total = 0.0
    for row in farm["tiles"]:
        for tile in row:
            if isinstance(tile, dict) and tile.get("kind") == "PLANT" \
                    and tile.get("crop") == crop:
                age = day - int(tile.get("planted_day", day))
                units, _, _ = OPP.yield_plan(crop, max(0, day - age))
                total += units
    return total


def _town_demand_now(item, step, shops):
    """Units of `item` the town removes from the market at this step."""
    demand = 1 if item != "FERTILIZER" and step % TOWN_CENTER_SELL_INTERVAL == 0 else 0
    if step % TOWN_SHOP_SELL_INTERVAL == 0:
        for shop in shops:
            products = SHOP_PRODUCTS.get(shop, ())
            if item in products:
                demand += 2 if len(products) == 1 else 1
    return demand


_THETA = {}
_THETA_LOADED = [False]


def _load_theta():
    """Read the fitted coefficients once. Absent file -> empty -> the
    structural forecast, which is exactly agent2's behaviour."""
    if _THETA_LOADED[0]:
        return _THETA
    _THETA_LOADED[0] = True
    try:
        import json as _json
        path = os.path.join(_ROOT, "dynamic", "opp_theta.json")
        if os.path.exists(path):
            _THETA.update(_json.load(open(path)).get("theta") or {})
    except Exception:
        pass
    return _THETA


def _mv_supply(opp_farm, item, day):
    """N_them: units of `item` the opponent can still put on the market."""
    st = S["oppst"]
    if OPP_PREDICT:
        theta = _load_theta().get(item)
        if theta:
            structural = st.forecast_production(opp_farm, item, day)
            x = OPRED.feature_row(item, opp_farm, day, st, structural)
            return OPRED.predict(theta, x) * MV_OPP_GAIN
    return st.supply(opp_farm, item, day, gain=MV_OPP_GAIN)


def _mv_own_supply(farm, private, item, day):
    """N_us: what WE still have to sell -- the shed plus our own tiles' output.

    Same estimator as the opponent side, run on our own farm, so the two terms
    of the suppression difference are measured the same way and a bias in the
    forecast largely cancels between them.
    """
    held = int((private.get("shed") or {}).get(item, 0))
    return held + MV_SELF_GAIN * S["oppst"].forecast_production(farm, item, day)


def _market_orders(farm, private, day, hour, prices, shops=(), opp_farm=None,
                   market_inv=None):
    orders = []
    money = farm["money"]
    shed = private.get("shed") or {}
    seeds = private.get("seeds") or {}
    shed_used = sum(shed.values())
    survival_reserve = SPEND_RESERVE * SURVIVAL_RESERVE_FRACTION

    # 1. Hire. Only worth issuing early -- a hand hired at hour 20 has no day
    #    left to work, and the crew size was already routed for at hour 0.
    if hour <= 1:
        target_hands = S["target_units"] - 1
        n_hands = len(farm.get("hands") or [])
        hires_today = farm.get("hires_today", 0)
        k = 0
        while n_hands + k < target_hands and len(orders) < MAX_ORDERS:
            cost = _hire_cost(hires_today + k)
            if money - cost < SPEND_RESERVE:
                break
            orders.append(["HIRE"])
            money -= cost
            k += 1

    # 2. Feed wheat, ahead of every discretionary purchase: a starved animal
    #    loses its banked CARE bonus, which is most of its value.
    animals = _placed_animals(farm)
    if animals > 0 and len(orders) < MAX_ORDERS:
        # Never stock more feed than the season can still consume. Without the
        # days-left cap the feed block keeps buying a full buffer through the
        # terminal-liquidation window, which then sells it straight back: 292
        # units of bought wheat round-tripped in one episode.
        days_left = max(0, SEASON_DAYS - day)
        target_stock = int(min(animals * WHEAT_FEED_BUFFER_MULT, animals * days_left))
        have = int(shed.get("WHEAT", 0))
        room = max(0, SHED_CAPACITY - shed_used)
        if have < target_stock and room > 0:
            price = max(1, prices.get("WHEAT", 25))
            afford = int(max(0, money - survival_reserve) // price)
            n = int(min(target_stock - have, afford, room, 40))
            if n > 0:
                orders.append(["BUY_PRODUCT", "WHEAT", n])
                money -= n * price

    want = _role_demand(farm, day)
    if ENPV_VETO:
        want = _enpv_veto(want, farm, private, day, shops)
    if _watering_debt(farm) > PLANT_MISS_TOLERANCE:
        for crop in CROPS:
            want.pop(crop, None)

    # 3/4. Animals and seeds, in the order the search prefers.
    if ENPV_BUY:
        money = _enpv_orders(orders, money, want, shed, seeds, shed_used,
                             farm, day)
    else:
        a_order = c_order = None
        if ENPV_ORDER:
            a_order = _enpv_rank(("COW", "SHEEP", "GOOSE"), farm, private, day,
                                 "animal")
            c_order = _enpv_rank(("WHEAT", "STRAWBERRY", "MELON", "CARROT",
                                  "TOMATO"), farm, private, day, "crop")
        if BUY_ANIMALS_FIRST:
            money = _order_animals(orders, money, want, shed, seeds, shed_used,
                                   a_order)
            money = _order_seeds(orders, money, want, shed, seeds, shed_used,
                                 c_order)
        else:
            money = _order_seeds(orders, money, want, shed, seeds, shed_used,
                                 c_order)
            money = _order_animals(orders, money, want, shed, seeds, shed_used,
                                   a_order)

    # 5. Land. On the tape's schedule when SCHEDULE_DRIVEN, otherwise only once
    #    the next quadrant already has roles waiting.
    #
    #    The old `wanted` test is a hard cap disguised as a guard: it needs a
    #    non-EMPTY role in the next quadrant, and the layout only has roles for
    #    as many tiles as TARGET_COUNTS sums to. At the searched optimum that
    #    sum is exactly 50 -- precisely NW + NE -- so SW never holds a role,
    #    `wanted` is permanently False, and the third quadrant can never be
    #    bought however much cash accumulates. Measured: the season ends with
    #    $97k unspent on 50 tiles while the tape works 75.
    if len(orders) < MAX_ORDERS:
        n_extra = len(farm.get("unlocked_quadrants", ["NW"])) - 1
        if n_extra < len(LAND_PRICES):
            price = LAND_PRICES[n_extra]
            nxt = LAND_ORDER[n_extra]
            if SCHEDULE_DRIVEN:
                due = day >= LAND_SCHEDULE[min(n_extra, len(LAND_SCHEDULE) - 1)]
                if due and money >= price * LAND_BUY_CASH_MULTIPLE:
                    orders.append(["BUY_LAND"])
                    money -= price
            else:
                wanted = any(role != "EMPTY" and quadrant_of(p[0], p[1], 10) == nxt
                             for p, role in S["layout"].items())
                if wanted and money >= price * LAND_BUY_CASH_MULTIPLE:
                    orders.append(["BUY_LAND"])
                    money -= price

    # 6. Sell. Iterate the priority list, never the raw shed -- the shed also
    #    holds live animals and a SELL of a non-product aborts the whole slot
    #    (pitfall #8).
    step = day * 24 + hour
    sold = {}
    ramp = _ramp(day)
    panic = shed_used > SHED_CAPACITY * SHED_PANIC_FRACTION

    order = SELL_PRIORITY_ORDER
    room_needed = 0
    if MV_PANIC_ORDER and panic and opp_farm is not None and market_inv is not None:
        # Highest marginal value first. MV already carries the sign of the
        # suppression term, so a book the opponent still has to sell into sorts
        # above one we do -- exactly the pair we want dumped and kept.
        def _mv_of(it):
            n = int(shed.get(it, 0))
            if n <= 0:
                return -1e9
            return MM.sale_value(it, int(market_inv.get(it, MM.MARKET_I0)),
                                 _mv_own_supply(farm, private, it, day),
                                 _mv_supply(opp_farm, it, day),
                                 discount=MV_ALPHA)
        order = sorted(SELL_PRIORITY_ORDER, key=_mv_of, reverse=True)
        room_needed = int(shed_used - SHED_CAPACITY * SHED_PANIC_FRACTION)
    # Reward is money on hand, so anything still in the shed at the buzzer is
    # worth exactly nothing. Liquidate unconditionally near the end.
    terminal = step >= TERMINAL_STEP
    freed = 0
    for item in order:
        if len(orders) >= MAX_ORDERS:
            break
        if room_needed and freed >= room_needed:
            panic = False        # enough space recovered; the gate decides the rest
            room_needed = 0
        have = int(shed.get(item, 0))
        if have <= 0:
            continue
        if terminal:
            # Wheat is the one product we are also still *buying* during the
            # liquidation window, to feed animals through their final
            # production days. Dumping it here just gets it re-bought next turn
            # -- 303 units churned that way in one episode. Hold it to the last
            # day, when the feed no longer has a production left to fund.
            if item == "WHEAT" and animals > 0 and day < SEASON_DAYS - 1:
                continue
            orders.append(["SELL", item, have])
            sold[item] = sold.get(item, 0) + have
            continue
        if item == "WHEAT" and animals > 0 and not WHEAT_SELL_SURPLUS:
            continue
        if item == "WHEAT":
            # Reserve the feed buffer against *every* sell path, panic included.
            # Panic-selling it and re-buying it next turn churned ~292 units of
            # bought wheat straight back out to the market, which is most of why
            # our spend ran 2.2x the reference's.
            have -= int(animals * WHEAT_FEED_BUFFER_MULT)
            if have <= 0:
                continue
        scale = 1.0
        glut = False
        suppress = None
        qty = int(have)
        if MV_MARKET and opp_farm is not None and market_inv is not None:
            inv = int(market_inv.get(item, MM.MARKET_I0))
            n_us = _mv_own_supply(farm, private, item, day)
            n_them = _mv_supply(opp_farm, item, day)
            value = MM.sale_value(item, inv, n_us, n_them, discount=MV_ALPHA)
            suppress = n_them > n_us
            if MV_POSTURE and not suppress and not panic:
                # We are the larger remaining supplier: this book is ours to
                # sell into later, so do not run it away from ourselves.
                rate = MV_METER_MULT * MM.drain_rate(item, shops) / float(TURNS_PER_DAY)
                qty = int(min(have, max(1, round(rate * TURNS_PER_DAY / 6.0))))
        elif OPP_MODEL and opp_farm is not None:
            scale = S["opp"].reserve_scale(opp_farm, item, day, step, shops,
                                           lo=OPP_SCALE_LO, hi=OPP_SCALE_HI,
                                           horizon_days=int(OPP_HORIZON_DAYS))
            glut = scale < 1.0
            value = prices.get(item, 0)
        else:
            value = prices.get(item, 0)
        # Hold one step for the town's tick to lift the price -- unless the
        # opponent is about to flood this product anyway, in which case waiting
        # just means selling after them into a worse market.
        if MT_TIMING and market_inv is not None:
            # Hold only where the arriving town tick actually pays for the step.
            gain, k = MT.hold_gain(item, int(market_inv.get(item, MM.MARKET_I0)),
                                   step, shops)
            hold = (FRONT_RUN and not panic and not glut
                    and k > 0 and gain >= MT_HOLD_THRESHOLD)
        else:
            hold = (FRONT_RUN and item in FRONT_RUN_ITEMS and not panic and not glut
                    and _town_demand_now(item, step, shops) > 0)
        if MV_POSTURE and suppress:
            hold = False          # racing them is the entire point
        if hold:
            continue
        reserve = RESERVE_PRICE.get(item, 20) * RESERVE_PRICE_SCALE * ramp * scale
        if value >= reserve or panic:
            orders.append(["SELL", item, qty])
            sold[item] = sold.get(item, 0) + qty
            freed += qty
    S["last_sales"] = sold
    if MT_QUEUE and len(orders) > MAX_ORDERS and market_inv is not None:
        # A slot costs the same whatever the quantity, so when more orders
        # compete than there are slots, rank by TOTAL value per slot. Non-SELL
        # orders keep their position: a missed HIRE or BUY cannot be re-placed
        # later at the same price.
        keep = [o for o in orders if o[0] != "SELL"]
        sells = [o for o in orders if o[0] == "SELL"]
        sells.sort(key=lambda o: -(int(o[2]) * MM.price(
            o[1], int(market_inv.get(o[1], MM.MARKET_I0)))))
        orders = keep + sells
    return orders[:MAX_ORDERS]


# ------------------------------------------------------------------- agent

def _guard_plant_atomicity(actions, seeds):
    """If total PLANT requests for one crop in a turn exceed seeds held, the
    engine drops ALL of them. Trim the excess to PASS so the rest still land."""
    counts = {}
    for a in actions:
        if len(a) >= 2 and a[0] == "PLANT":
            counts[a[1]] = counts.get(a[1], 0) + 1
    over = {c: n - int(seeds.get(c, 0)) for c, n in counts.items() if n > int(seeds.get(c, 0))}
    if not over:
        return actions
    out = []
    for a in actions:
        if len(a) >= 2 and a[0] == "PLANT" and over.get(a[1], 0) > 0:
            over[a[1]] -= 1
            out.append(["PASS"])
        else:
            out.append(a)
    return out


def agent(obs):
    obs = obs if isinstance(obs, dict) else dict(obs)
    player = obs.get("player", 0)
    farms = obs.get("farms") or []
    if not farms or player >= len(farms):
        return {"farmer": ["PASS"], "hands": [], "market": []}
    farm = farms[player]
    private = obs.get("private") or {}
    private = {
        "shed": private.get("shed") or {},
        "seeds": private.get("seeds") or {},
        "inventories": private.get("inventories") or [{}],
    }
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    board_size = len(farm["tiles"])

    if day == 0 and hour == 0:
        _reset_state()
    if S.get("layout") is None:
        # USE_PLAN is a separate switch on purpose. The first version gated this
        # on `PLAN_GATE_DAYS >= 0`, which is true for 0, so the plan loaded even
        # when it was meant to be off -- the "baseline" silently ran the tape's
        # 73-tile layout with parameters searched for 50 and scored -164,312
        # against its real -76,238, and three variants returned byte-identical
        # numbers because they were the same agent.
        plan = (SEASON_PLAN or _load_season_plan()) if USE_PLAN else {}
        S["plan"] = plan if isinstance(plan, dict) else {}
        S["layout"] = (_plan_layout(board_size, S["plan"]) if S["plan"]
                       else _build_layout(board_size))

    if ECON_VALUE or ALLOC_MODE:
        # Built before the day is planned, from the market as it stands this
        # morning. N_them is what the opponent can still put on each book and
        # N_us is our own remaining supply, measured the same way so the bias in
        # the structural forecast largely cancels between them.
        opp = farms[1 - player] if len(farms) > 1 else None
        inv = (obs.get("market") or {}).get("inventory") or {}
        shops = tuple((obs.get("town") or {}).get("unlocked_shops") or ())
        n_us, n_them = {}, {}
        for it in MM.PRODUCTS:
            n_us[it] = _mv_own_supply(farm, private, it, day)
            n_them[it] = _mv_supply(opp, it, day) if opp is not None else 0.0
        S["econ"] = TV.Ctx(inv, shops, day, n_us, n_them, alpha=ECON_ALPHA)
        S["alloc"] = {}
        S["opp_farm"] = opp

    if S["day"] != day:
        S["day"] = day
        _plan_day(farm, private, day, board_size)

    S["pending"] = _pending_now(farm, private, day)
    claimed = set()
    n_hands = len(farm.get("hands") or [])
    farmer_action = _unit_action(0, farm, private, board_size, claimed)
    hands_actions = [_unit_action(i + 1, farm, private, board_size, claimed)
                     for i in range(n_hands)]

    guarded = _guard_plant_atomicity([farmer_action] + hands_actions, private["seeds"])
    farmer_action, hands_actions = guarded[0], guarded[1:]

    market_obj = obs.get("market") or {}
    prices = market_obj.get("prices") or {}
    town = obs.get("town") or {}
    shops = tuple(town.get("unlocked_shops") or ())
    opp_farm = farms[1 - player] if len(farms) > 1 else None
    inventory = market_obj.get("inventory") or {}
    if OPP_MODEL or MV_MARKET or ECON_VALUE or ALLOC_MODE:
        # Our own realised sales are within a unit or two of what we requested:
        # we only ever ask for exactly what the shed holds, so the per-unit
        # commit loop fills the order.
        S["opp"].observe(inventory, day * 24 + hour, shops,
                         S.get("last_sales") or {})
    if (MV_MARKET or ECON_VALUE or ALLOC_MODE) and opp_farm is not None:
        # Must run EVERY turn: the harvest measurement is an intra-day drop in
        # the opponent's tile yield_units, and a skipped turn merges a harvest
        # into a night refresh and loses it.
        if S["opp"].recent and S["opp"].recent[-1][0] == day * 24 + hour:
            S["oppst"].record_sales(S["opp"].recent[-1][1])
        S["oppst"].observe(opp_farm, day, hour)
        S["oppst"].reconcile(prices, len(opp_farm.get("hands") or []))
    orders = _market_orders(farm, private, day, hour, prices, shops, opp_farm,
                            inventory)

    return {"farmer": farmer_action, "hands": hands_actions, "market": orders}
