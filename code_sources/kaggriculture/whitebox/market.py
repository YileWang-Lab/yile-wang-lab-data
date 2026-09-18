"""Module 5 of 6 -- MARKET ORDER GENERATOR. Fully decoupled from movement.

Market orders never depend on where a unit is standing, so this module never
sees a position. It sees stock, prices, the clock and the opponent's public
farm, and it emits at most `MAX_ORDERS` (10 -- the engine silently drops the
rest) entries for the turn's `market` list.

ONE THING IT MUST RESPECT, AND IT IS NOT OBVIOUS. `SELL` draws from
`private["shed"]`. A HARVEST or PICKUP puts the unit in question's own
inventory, and only a `DROP` on a shed-access tile moves it to the shed. So the
sellable set is the SHED, never the carried stock, and a plan to sell earlier
than the goods arrive is not a market decision at all (HANDOFF rule 5).

THE ENDGAME PATH IS THE MEASURED ONE. `endgame_orders` is the strategy graded in
HANDOFF section 38, kept intact:

  deadline mask    drop buys that cannot be grown, harvested and sold in time.
                   Derived, not guessed: (30 - first_yield_day) * 24 - 1.
  front-run        their liquidation round is a PHYSICAL bound set by animals
                   held and hands hired, both public: T = 719 - (ceil(A/W) + 1).
                   Selling into an undrained market one step earlier matters
                   because MILK's above_target is 1.60 over T=122 -- ~100 units
                   takes it from $160 to the $1 floor and second place banks
                   nothing.
  liquidation      empty the shed at 716+, everything at 718.
  squeeze          DELIBERATELY ABSENT. Measured -3,068 a seed, 0 wins in 144.
                   The premise needs opponents to still need feed wheat; they
                   buy 0-7 units at step >= 670 having already stockpiled.
"""
from whitebox import econ

try:
    from whitebox import market_model as MM
except Exception:
    MM = None
try:
    from whitebox import opponent_model as OM
except Exception:
    OM = None
import os as _os_top
MARKET_TIMING = _os_top.environ.get("WB_MARKET_TIMING", "1") != "0"
FRONTRUN_MIN_UNITS = int(_os_top.environ.get("WB_FRONTRUN_MIN_UNITS", "6"))
FRONTRUN_LEAD_DAYS = int(_os_top.environ.get("WB_FRONTRUN_LEAD", "3"))

MAX_ORDERS = econ.MAX_ORDERS


def _carried_quantity(snap, item):
    carried = getattr(snap, "carried", None)
    if callable(carried):
        return int(carried().get(item, 0) or 0)
    return sum(int(inv.get(item, 0) or 0)
               for inv in getattr(snap, "inventories", ()))

# ---------------------------------------------------------------------------
# PACED SELLING (2026-08-25). Measured defect, not a hypothesis.
#
# `spread`'s cap is `TOWN_DAY * 0.8` and its docstring calls that "about one day
# of town demand per turn-batch". But the town center consumes ONCE PER DAY
# (turnsPerDay 24, consumption interval 24) while that cap is applied EVERY
# TURN, so on any turn the shed has stock the "trickle" is up to 16 MILK
# against 20.5 absorbed in a whole day. Traced over one game (seed 4000 vs
# kawa), the two spread products came out opposite:
#
#   WOOL  8 sales of 8-16 units, ~3 days apart. Price ROSE 232 -> 246 and the
#         book DRAINED (9,957 -> 9,782): the town ate faster than we sold.
#   MILK  price COLLAPSED 154 -> 5. A 36-unit sale on day 17 (the front-run
#         override, bounded only by `oneshot_capacity` = the crash depth), then
#         19, 9, 7, 5. 215 units sold, most of them given away.
#
# WOOL was already doing the right thing by accident -- we simply never hold
# enough of it to hit the cap. MILK hits it constantly. So the fix is to make
# the pacing explicit rather than incidental:
#
#   A  ABSORPTION PACE. A batch may not exceed what the town has taken since
#      our last sale of that item -- `TOWN_DAY * elapsed_days`. This is what
#      "trickle" always meant; it was just never measured against the clock.
#   B  GLUT GATE. Below `PACE_MIN_PX` of the item's undisturbed price, sell
#      nothing and let the book recover. MILK recovers in 1.9 days and WOOL in
#      3.4, so waiting is cheap mid-game and impossible late -- which is why
#      this whole layer is off past `ENDGAME_START`, where unsold stock is
#      worth zero and DUSK's liquidation must be free to dump.
#   C  The front-run override may outrun the PACE (that is its entire purpose)
#      but not the GATE: front-running into a floored book sells at $5.
#
# Applies to `spread` items only. `free` (EGG, WHEAT) never crashes, and
# `timed` (MELON, TOMATO, CARROT) is meant to be one sale sized to the curve.
# Archived A/B: every tested PACED arm regressed (-$143 to -$3,290). Keep the
# readable mechanism as evidence, but do not expose a production environment
# seam which can silently reactivate a falsified policy.
PACED = False
PACE_MIN_PX = float(_os_top.environ.get("WB_PACE_MIN_PX", "0.45"))
_PACE = {"seat": None, "step": -1, "last": {}}


def _pace_reset_if_new(snap):
    if _PACE["seat"] != snap.seat or snap.step < _PACE["step"]:
        _PACE["seat"], _PACE["last"] = snap.seat, {}
    _PACE["step"] = snap.step


def _pace_allowance(snap, item):
    """Units the town has absorbed since our last sale of `item`. None = first."""
    last = _PACE["last"].get(item)
    if last is None:
        return None
    days = max(0.0, (snap.step - last) / float(econ.TURNS_PER_DAY))
    return (MM.TOWN_DAY.get(item, 8.0) if MM is not None else 8.0) * days


def _pace_gate_ok(snap, item):
    """False when the book is already too deep to be worth selling into."""
    if PACE_MIN_PX <= 0:
        return True
    inv = int(snap.market_inv.get(item, econ.MARKET_I0) or econ.MARKET_I0)
    base = econ.price(item, econ.MARKET_I0)
    return base <= 0 or econ.price(item, inv) >= PACE_MIN_PX * base


def _pace_record(snap, item):
    _PACE["last"][item] = snap.step
PREMIUM = ("MILK", "WOOL", "MELON", "STRAWBERRY", "EGG")
LIQUIDATION_ORDER = ("MELON", "MILK", "WOOL", "STRAWBERRY", "TOMATO",
                     "CARROT", "EGG", "WHEAT", "FERTILIZER")
# Rule-level ordering used by the public room-guard mechanism.  It is a
# deterministic preference over currently visible stock, not a replay tape.
CAPACITY_PUBLIC_PRIORITY = (
    "WOOL", "MILK", "EGG", "MELON", "STRAWBERRY", "TOMATO", "CARROT",
    "FERTILIZER", "WHEAT",
)
ENDGAME_START = 670
SELL_FLOOR = 2             # never volunteer a sale at the $1 floor

# ---------------------------------------------------------------------------
# THE LAST 50 STEPS, as measured. This is the whole endgame policy in one place.
#
#   670..710   MARKET ONLY. Deadline masking plus policy-sized selling. The
#              route is NOT touched: the tape still runs 52 HARVESTs, 50 WATERs
#              and 9 FEEDs here, and taking those over costs -1,655 to -7,954 a
#              seed (measured at windows 8/12/25/50, both a collector-only and a
#              full layered husbandry planner, with and without hiring).
#   T_opp-1    FRONT-RUN. Their liquidation turn is a PHYSICAL bound from public
#              state: T = 719 - (ceil(A_opp / W_opp) + 1). Sell premium stock
#              into slot 0 one step before it. This is the ONLY place price
#              suppression works, because the town has no time to refill:
#              MILK recovers in 1.9 days and WOOL in 3.4, and neither fits in
#              the steps that remain.
#   711..718   ROUTE TAKEOVER, 8 steps. Nothing planted can still grow, so every
#              turn is worth what it converts to shed stock. Collector only:
#              carry -> shed -> DROP, HARVEST what is reachable and bankable.
#              +303 sim / +302 real, 85.8% / 90.3% paired win. At 12 steps this
#              turns negative (-70) and at 50 it is -13,601: the window is the
#              width of the region where the objective changed, not a parameter.
#   716..718   TERMINAL LIQUIDATION. Empty the shed; everything at 718.
#
# DELIBERATELY ABSENT, each refuted with a measurement:
#   wheat squeeze     -3,068 a seed, 0 wins in 144. Needs the opponent to still
#                     need feed; they buy 0-7 wheat at step >= 670.
#   selling animals   impossible -- `SELL` quotes only `item in PRODUCTS`.
#   price suppression 19 SHEEP or 20 COW would be needed merely to match the
#                     town's daily drain before any glut could form.
#   exact subset DP   ties the greedy collector on win rate (85.4% each) and
#                     loses the head-to-head 42.9%.
# ---------------------------------------------------------------------------


# ------------------------------------------------------------------ endgame

def opp_clear_round(opp):
    """719 - (ceil(A / W) + 1). None when they hold no animals.

    A PICKUP is one hand action, so emptying A animals takes ceil(A/W) turns and
    the merged SELL costs one more. Both inputs are public.
    """
    animals = len(opp.animals)
    if animals <= 0:
        return None
    workers = max(1, opp.workers)
    return 719 - ((animals + workers - 1) // workers + 1)


def mask_deadlines(orders, step):
    out = []
    for o in orders:
        if o and len(o) >= 2:
            op, item = o[0], str(o[1])
            if op == "BUY_SEED" and step > econ.SEED_DEADLINE.get(item, 719):
                continue
            if op == "BUY_ANIMAL" and step > econ.ANIMAL_DEADLINE.get(item, 719):
                continue
        out.append(o)
    return out


def endgame_orders(snap, orders, front_run=True):
    """The section 38 endgame layer, as a function of the snapshot."""
    step = snap.step
    orders = mask_deadlines(list(orders), step)
    already = {str(o[1]) for o in orders if o and o[0] == "SELL" and len(o) >= 2}

    clear = opp_clear_round(snap.opp)
    if front_run and clear is not None and step == clear - 1:
        for item in PREMIUM:
            if len(orders) >= MAX_ORDERS or item in already:
                continue
            have = int(snap.shed.get(item, 0) or 0)
            if have > 0:
                # Slot order matters: `_process_market` walks the 10 slots in
                # order and quotes both players against the same pre-commit
                # inventory at each slot, so an earlier slot sells first.
                orders.insert(0, ["SELL", item, have])
                already.add(item)

    if step >= 716:
        planned = {}
        for o in orders:
            if o and o[0] == "SELL" and len(o) >= 3:
                planned[str(o[1])] = planned.get(str(o[1]), 0) + max(0, int(o[2]))
        for item in LIQUIDATION_ORDER:
            have = int(snap.shed.get(item, 0) or 0)
            extra = have if step >= 718 else max(0, have - planned.get(item, 0))
            if extra > 0 and len(orders) < MAX_ORDERS:
                orders.append(["SELL", item, extra])
    return orders[:MAX_ORDERS]


# ------------------------------------------------------------- steady state

def _sell_batch(snap, item, want, tracker=None, opponent_timing=True):
    """How much of `item` to sell THIS TURN, by its computed sell policy.

    `whitebox/market_model.py` derives three policies from the engine's own
    curves, and they are not interchangeable:

      free    (EGG, WHEAT)  never halves at any volume -- sell it all.
      spread  (MILK, WOOL, STRAWBERRY)  halves in 31-42 units, but the town eats
              the glut back in 1.2-3.4 days. Sell about one day of town demand
              per turn-batch and let the clock refill the book. Dumping these is
              how a front-runner takes -94% off us; trickling makes that
              impossible because there is never a big position to take.
      timed   (MELON, TOMATO, CARROT, FERTILIZER)  the town absorbs ~1 MELON a
              DAY against a 112-unit half-life, so a melon glut NEVER lifts.
              One sale, sized to the curve, and never a trickle that walks the
              price down for the rest of the season.
    """
    inv = int(snap.market_inv.get(item, econ.MARKET_I0) or econ.MARKET_I0)
    if MM is None:
        n = 0
        for i in range(min(int(want), 60)):
            if econ.price(item, inv + i) < SELL_FLOOR:
                break
            n += 1
        return n
    _B = 1.0
    _timing = MARKET_TIMING and bool(opponent_timing)
    _lead, _units = FRONTRUN_LEAD_DAYS, FRONTRUN_MIN_UNITS
    cap = MM.safe_batch(item, min(int(want), 200), inv, SELL_FLOOR)
    policy = MM.SELL_POLICY.get(item, "spread")
    if policy == "spread":
        cap = min(cap, max(1, int(MM.TOWN_DAY.get(item, 8) * 0.8 * _B)))
    cap = max(0, int(cap * _B)) if _B != 1.0 else cap

    # Rules A and B. Mid-game only: past ENDGAME_START unsold stock is worth
    # nothing and `endgame_orders` owns the decision anyway.
    paced = (PACED and MM is not None and snap.step < ENDGAME_START
             and MM.SELL_POLICY.get(item) == "spread")
    if paced:
        if not _pace_gate_ok(snap, item):
            return 0
        allow = _pace_allowance(snap, item)
        if allow is not None:
            cap = min(cap, max(0, int(allow)))

    # MARKET TIMING (2026-08-24, revised same day). Two public signals, not
    # one -- `earliest_available` answers "when does their FIRST tile ripen",
    # which fires on a single stray tile and is blind to anything they already
    # harvested and are simply sitting on:
    #
    #   FUTURE   `earliest_sellable`: the step by which a THRESHOLD volume
    #            (`FRONTRUN_MIN_UNITS`, not one unit) is both ripe AND
    #            plausibly carried back to their shed -- volume and travel
    #            time, not just ripening. If that step is within
    #            `FRONTRUN_LEAD_DAYS`, front-run now.
    #   PRESENT  `tracker.holdings(item)`: what section on OpponentTracker
    #            (2026-08-23) already infers they are SITTING ON, exact for
    #            MELON/EGG/CARROT/TOMATO/STRAWBERRY (never the biased MILK/
    #            WOOL/WHEAT/FERTILIZER half -- see state.py). Computed every
    #            turn via `tr.observe` regardless, so using it here costs
    #            nothing new; not using it was leaving inferred stock
    #            invisible to the one decision it is actually for.
    #
    # Either signal alone front-runs; this is DUSK's front-run trigger
    # (section 38) generalised from one last-8-step check to every mid-game
    # turn, using public state instead of the physical opp_clear_round bound.
    if _timing and OM is not None:
        try:
            fired = False
            step_avail = OM.earliest_sellable(snap.opp, item, snap.day, _units)
            if step_avail is not None and step_avail - snap.step <= _lead * 24:
                fired = True
            if (tracker is not None and item in tracker.RELIABLE
                    and tracker.holdings(item) >= _units):
                fired = True
            if fired:
                boost = min(int(want), MM.oneshot_capacity(item))
                # Rule C. `oneshot_capacity` is the CRASH DEPTH -- the point the
                # price halves -- so an unbounded front-run sells exactly the
                # batch that destroys the book. Under pacing the boost is still
                # allowed to break the pace, but only while the gate holds.
                if paced and not _pace_gate_ok(snap, item):
                    boost = 0
                cap = max(cap, boost)
        except Exception:
            pass
    return cap


def feed_orders(snap, plan, consume_service_reserve=False):
    """Buy the rolling wheat buffer. FIRST in the turn's order list, always.

    Not gated on owning an animal: `plan.wheat_needed` already counts the herd
    we are in the middle of buying, and gating on the placed herd is what
    deadlocked the whole agent. Feed also comes ahead of seed and land because
    the market queue is capped at ten orders and cash is the binding constraint
    early -- an order that loses its slot to a $80 melon seed costs an animal.
    """
    wheat = int(snap.shed.get("WHEAT", 0) or 0)
    if wheat >= plan.wheat_needed or snap.step > econ.SEED_DEADLINE["WHEAT"]:
        return []
    px = max(1, econ.price("WHEAT", int(snap.market_inv.get("WHEAT", econ.MARKET_I0) or econ.MARKET_I0)))
    gap = min(plan.wheat_needed - wheat, snap.shed_room)
    # ``service_cash_floor`` is money earmarked for this exact feed purchase,
    # not money that the feed order must preserve. Historical arms subtract
    # the whole floor for compatibility. The opt-in unified arm protects only
    # the non-service remainder while WHEAT consumes its named reserve.
    protected = float(plan.cash_floor)
    if consume_service_reserve:
        protected = max(
            0.0,
            protected - float(getattr(plan, "service_cash_floor", 0.0) or 0.0),
        )
    afford = int(max(0.0, snap.me.money - protected) // px)
    n = max(0, min(gap, afford, 20))
    return [["BUY_PRODUCT", "WHEAT", n]] if n else []


# ---------------------------------------------------------------------------
# ROLLOVER FLUSH (2026-08-25). An engine fact nothing in this agent knew.
#
# `_end_of_day` calls `_drop_inventories_to_shed(private, shedCapacity)`, which
# empties EVERY hand inventory into the shed up to 100 items and then runs
# `del inv[item]` whether or not the deposit fit: "overflow is discarded". So
# produce carried past a full shed at the day boundary is DESTROYED, silently.
#
# This is also why no unit ever emits a DROP mid-game -- measured 0 DROPs in
# 5,515 unit-actions -- and why the shed reads ~0 all day and jumps at the
# rollover: delivery is automatic and once-daily, not a shed round trip.
#
# Measured cost before this existed (16 seeds x 3 opponents, champion sequence):
# 6.5 nights of 23 overflow, 61.9 units and $1,629 destroyed a game, 2.9% of
# bank, concentrated on days 16-26 once the herd is producing.
#
# The fix is a SELL, so it is legal at the market layer (rule 5): the goods
# being freed are already in the shed. Cheapest marginal price first, so the
# room is bought with the stock we would least miss, and feed is protected.
# Selling into a crashed book at $5 still beats $0, and a sale at the $1 floor
# does not even add to market inventory (engine: "Sales at $1 do not increase
# market supply"), so the price impact of the flush is bounded by construction.
# Overflow destruction is an exact engine fact; this particular proactive
# flush action nevertheless measured approximately zero and is not promoted.
FLUSH = False
FLUSH_HOUR = int(_os_top.environ.get("WB_FLUSH_HOUR", "21"))
SHED_CAP = 100


def rollover_flush(snap, plan, already):
    """SELLs that free exactly enough shed room for what the hands are carrying."""
    if not FLUSH or snap.hour < FLUSH_HOUR or snap.step >= ENDGAME_START:
        return []
    carried = 0
    for iv in snap.inventories:
        for k, v in iv.items():
            if k in econ.SELLABLE:
                carried += int(v or 0)
    if carried <= 0:
        return []
    shed_tot = sum(int(v or 0) for v in snap.shed.values())
    # what the regular orders are already taking out of the shed this turn
    pending = sum(int(o[2]) for o in already
                  if o and o[0] == "SELL" and len(o) > 2)
    overflow = carried - max(0, SHED_CAP - shed_tot + pending)
    if overflow <= 0:
        return []
    priced = []
    for item in econ.SELLABLE:
        have = int(snap.shed.get(item, 0) or 0)
        if item == "WHEAT":
            have = max(0, have - plan.wheat_needed)     # feed is not spare room
        have -= sum(int(o[2]) for o in already
                    if o and o[0] == "SELL" and len(o) > 2 and o[1] == item)
        if have <= 0:
            continue
        inv = int(snap.market_inv.get(item, econ.MARKET_I0) or econ.MARKET_I0)
        priced.append((econ.price(item, inv), item, have))
    priced.sort()
    out = []
    for _, item, have in priced:
        if overflow <= 0:
            break
        n = min(have, overflow)
        if n > 0:
            out.append(["SELL", item, n])
            overflow -= n
    return out


def _guaranteed_day_batch(snap, item, want):
    """Current stock supported by exact public drain through this game day.

    The market commits before town consumption.  At hour zero, the interval to
    the next day boundary is the natural inventory-accounting period because
    carried unit stock is automatically deposited at that boundary.  Existing
    shops are public; still-hidden shop instances contribute their enumerated
    minimum, never a fixed-seed average.  A marginal unit at the engine's $1
    floor is retained for later unless exact capacity requires its sale.
    """
    if MM is None or int(getattr(snap, "hour", -1)) != 0:
        return 0
    end = min(719, (int(snap.day) + 1) * econ.TURNS_PER_DAY)
    drain, _upper = MM.town_take_bounds(
        snap, item, start_step=int(snap.step), end_step=end,
    )
    qty = min(max(0, int(want)), max(0, int(drain)))
    inv = int(snap.market_inv.get(item, econ.MARKET_I0) or econ.MARKET_I0)
    while qty > 0:
        marginal = (econ.sell_revenue(item, qty, inv)
                    - econ.sell_revenue(item, qty - 1, inv))
        if marginal > econ.PRICE_FLOOR:
            break
        qty -= 1
    return qty


def _exact_overflow_sales(snap, plan, planned):
    """Minimum extra sales preventing known carried stock from being lost.

    End-of-day auto-deposit uses one shared 100-item shed.  Given current shed,
    current carried inventories, and already planned sales, the overflow is an
    exact integer.  Allocate that many extra sales to the highest exact next
    marginal revenues; the engine curves are separable and non-increasing, so
    this greedy merge is the exact maximum-revenue allocation.
    """
    planned = dict(planned)
    sold = sum(planned.values())
    carried = sum(max(0, int(qty or 0))
                  for inv in snap.inventories for qty in inv.values())
    overflow = max(0, int(snap.shed_used) - sold + carried - SHED_CAP)
    if overflow <= 0:
        return planned

    marginals = []
    for item in econ.SELLABLE:
        reserve = int(plan.wheat_needed) if item == "WHEAT" else 0
        have = max(0, int(snap.shed.get(item, 0) or 0) - reserve)
        base = min(have, max(0, int(planned.get(item, 0))))
        inv = int(snap.market_inv.get(item, econ.MARKET_I0) or econ.MARKET_I0)
        prior = econ.sell_revenue(item, base, inv)
        for extra in range(1, have - base + 1):
            revenue = econ.sell_revenue(item, base + extra, inv)
            marginals.append((-(revenue - prior), item, extra))
            prior = revenue
    marginals.sort()
    for _neg_value, item, _sequence in marginals[:overflow]:
        planned[item] = planned.get(item, 0) + 1
    return planned


def _inventory_after_sale(item, qty, inventory):
    """Exact engine book after one sale; $1 units do not add supply."""
    inv = max(0, int(inventory))
    for _ in range(max(0, int(qty))):
        if econ.price(item, inv) > econ.PRICE_FLOOR:
            inv += 1
    return inv


def robust_sale_cash(snap, orders, opponent_capacity=econ.SHED_CAPACITY):
    """Cash guaranteed after a conserved hidden opponent shed allocation.

    The opponent can place at most one shared shed's stock ahead of our product
    sales.  For every integer allocation ``h[p]`` with
    ``sum(h[p]) <= shedCapacity``, price our exact current sale after ``h[p]``
    opponent units.  A min-plus allocation DP returns the worst total cash.
    Own quantities are capped by current shed stock and the ten-order engine
    queue, so the result is a physical lower bound that may safely finance
    later orders in the same market phase.
    """
    stock = {item: max(0, int(qty or 0))
             for item, qty in snap.shed.items()}
    quantities = {}
    for order in (orders or ())[:MAX_ORDERS]:
        if not order or len(order) < 3 or order[0] != "SELL":
            continue
        item = str(order[1])
        if item not in econ.SELLABLE:
            continue
        qty = min(max(0, int(order[2] or 0)), stock.get(item, 0))
        if qty <= 0:
            continue
        stock[item] = stock.get(item, 0) - qty
        quantities[item] = quantities.get(item, 0) + qty
    if not quantities:
        return 0.0

    capacity = max(0, int(opponent_capacity))
    item_costs = []
    for item, qty in sorted(quantities.items()):
        inv = int(snap.market_inv.get(item, econ.MARKET_I0) or econ.MARKET_I0)
        costs = []
        after = inv
        for hidden in range(capacity + 1):
            if hidden > 0 and econ.price(item, after) > econ.PRICE_FLOOR:
                after += 1
            costs.append(float(econ.sell_revenue(item, qty, after)))
        item_costs.append(costs)

    inf = float("inf")
    dp = [inf] * (capacity + 1)
    dp[0] = 0.0
    for costs in item_costs:
        nxt = [inf] * (capacity + 1)
        for used, prior in enumerate(dp):
            if prior == inf:
                continue
            for hidden in range(capacity - used + 1):
                total = used + hidden
                nxt[total] = min(nxt[total], prior + costs[hidden])
        dp = nxt
    return float(min(dp))


def robust_one_step_wait_gain(snap, orders,
                              opponent_capacity=econ.SHED_CAPACITY):
    """Worst sale-cash gain from waiting through the current public drain.

    Let ``q[p]`` be the aggregate live-shed quantity in the executable sale
    queue, ``I[p]`` the current public market book, ``d[p]`` the exact town
    consumption after this market phase, and ``h[p]`` one conserved hidden
    opponent shed allocation.  The one-step inventory option is

    ``min_(sum h[p] <= H) sum_p [R(q[p], I[p]-d[p] after h[p])
                                  - R(q[p], I[p] after h[p])]``.

    The opponent allocation is shared by both terms and across products.  It
    may represent either existing hidden shed stock or output banked before the
    next market phase; no opponent policy or timing fingerprint is assumed.
    A positive result therefore proves that the exact public drain improves
    this bundle for every physical allocation of one opponent shed.
    """
    if MM is None:
        return 0.0

    stock = {item: max(0, int(qty or 0))
             for item, qty in snap.shed.items()}
    quantities = {}
    for order in (orders or ())[:MAX_ORDERS]:
        if not order or len(order) < 3 or order[0] != "SELL":
            continue
        item = str(order[1])
        if item not in econ.SELLABLE:
            continue
        qty = min(max(0, int(order[2] or 0)), stock.get(item, 0))
        if qty <= 0:
            continue
        stock[item] = stock.get(item, 0) - qty
        quantities[item] = quantities.get(item, 0) + qty
    if not quantities:
        return 0.0

    capacity = max(0, int(opponent_capacity))
    item_gains = []
    for item, qty in sorted(quantities.items()):
        low, high = MM.town_take_bounds(
            snap, item, start_step=int(snap.step),
            end_step=int(snap.step) + 1,
        )
        # Over this one engine transition all active shops are already public.
        # Refuse the option if a nonstandard configuration makes that false.
        if int(low) != int(high):
            return 0.0
        drain = max(0, int(low))
        inv = int(snap.market_inv.get(item, econ.MARKET_I0)
                  or econ.MARKET_I0)
        now_after = inv
        wait_after = inv - drain
        gains = []
        for hidden in range(capacity + 1):
            if hidden > 0:
                if econ.price(item, now_after) > econ.PRICE_FLOOR:
                    now_after += 1
                if econ.price(item, wait_after) > econ.PRICE_FLOOR:
                    wait_after += 1
            gains.append(float(
                econ.sell_revenue(item, qty, wait_after)
                - econ.sell_revenue(item, qty, now_after)
            ))
        item_gains.append(gains)

    inf = float("inf")
    dp = [inf] * (capacity + 1)
    dp[0] = 0.0
    for gains in item_gains:
        nxt = [inf] * (capacity + 1)
        for used, prior in enumerate(dp):
            if prior == inf:
                continue
            for hidden in range(capacity - used + 1):
                total = used + hidden
                nxt[total] = min(nxt[total], prior + gains[hidden])
        dp = nxt
    return float(min(dp))


def defer_strictly_dominated_sales(snap, plan, orders, unit_actions=None):
    """Remove current-stock sales only under an executable one-step proof.

    This post-process runs *after* the capital master, so it cannot let a freed
    slot or hypothetical sale cash select a current purchase.  Waiting is legal
    only when the current queue contains sales and nothing that spends cash,
    the live bank already covers the computed daily service reserve, no DROP
    changes shed occupancy in the current unit phase, and neither rollover nor
    the endgame boundary occurs before the next market phase.  V86 then
    re-evaluates the retained stock from the next public observation; no hidden
    state or remembered commitment is required.
    """
    kept = [list(order) for order in (orders or ())][:MAX_ORDERS]
    if not kept or any(not order or order[0] != "SELL" for order in kept):
        return kept
    if any(action and action[0] == "DROP" for action in (unit_actions or ())):
        return kept

    step = int(getattr(snap, "step", 0) or 0)
    if step >= ENDGAME_START - 1:
        return kept
    turns_per_day = (MM._config_int(snap, "turnsPerDay", econ.TURNS_PER_DAY)
                     if MM is not None else econ.TURNS_PER_DAY)
    if step % turns_per_day == turns_per_day - 1:
        return kept

    money = float(getattr(getattr(snap, "me", None), "money", 0.0) or 0.0)
    reserve = max(0.0, float(getattr(plan, "cash_floor", 0.0) or 0.0))
    if money < reserve:
        return kept

    capacity = (MM._config_int(snap, "shedCapacity", econ.SHED_CAPACITY)
                if MM is not None else econ.SHED_CAPACITY)
    if int(getattr(snap, "shed_used", 0) or 0) > capacity:
        return kept
    # Decision-theoretic strict dominance is weak improvement in every state
    # and strict improvement in at least one.  A floor-saturating 100-unit
    # allocation can make the worst gain exactly zero, so requiring the minimum
    # itself to be positive would incorrectly discard a valid option.
    worst_gain = robust_one_step_wait_gain(snap, kept, capacity)
    possible_gain = robust_one_step_wait_gain(snap, kept, 0)
    if worst_gain < 0.0 or possible_gain <= 0.0:
        return kept
    return []


def steady_orders(snap, plan, tracker=None, sale_variant=None):
    if sale_variant == "day_boundary_liquidation":
        planned = {}
        if int(getattr(snap, "hour", -1)) == 0:
            for item in LIQUIDATION_ORDER:
                have = int(snap.shed.get(item, 0) or 0)
                if item == "WHEAT":
                    have = max(0, have - int(plan.wheat_needed))
                if have > 0:
                    planned[item] = have
        planned = _exact_overflow_sales(snap, plan, planned)
        return [["SELL", item, planned[item]] for item in LIQUIDATION_ORDER
                if planned.get(item, 0) > 0][:MAX_ORDERS]

    if sale_variant == "guaranteed_day_drain":
        planned = {}
        for item in LIQUIDATION_ORDER:
            have = int(snap.shed.get(item, 0) or 0)
            if item == "WHEAT":
                have = max(0, have - int(plan.wheat_needed))
            qty = _guaranteed_day_batch(snap, item, have)
            if qty > 0:
                planned[item] = qty
        planned = _exact_overflow_sales(snap, plan, planned)
        return [["SELL", item, planned[item]] for item in LIQUIDATION_ORDER
                if planned.get(item, 0) > 0][:MAX_ORDERS]

    orders = []
    if PACED:
        _pace_reset_if_new(snap)
    # sell everything that is not feed, sized to the price curve
    for item in LIQUIDATION_ORDER:
        if len(orders) >= MAX_ORDERS:
            break
        have = int(snap.shed.get(item, 0) or 0)
        if item == "WHEAT":
            have = max(0, have - plan.wheat_needed)
        if item == "FERTILIZER":
            carried = _carried_quantity(snap, "FERTILIZER")
            reserve = max(
                0,
                int(getattr(plan, "fertilizer_target", 0) or 0) - carried,
            )
            have = max(0, have - reserve)
        if have <= 0:
            continue
        n = _sell_batch(
            snap, item, have, tracker,
            opponent_timing=(sale_variant not in (
                "observation_only_timing", "one_step_inventory_option",
                "cashflow_service_timing",
            )),
        )
        if n > 0:
            orders.append(["SELL", item, n])
            if PACED:
                _pace_record(snap, item)

    # 3. shed pressure: 100 items total and a full shed freezes all commerce
    if snap.shed_room < 10:
        for item in LIQUIDATION_ORDER:
            if len(orders) >= MAX_ORDERS:
                break
            have = int(snap.shed.get(item, 0) or 0)
            if item == "FERTILIZER":
                carried = _carried_quantity(snap, "FERTILIZER")
                reserve = max(
                    0,
                    int(getattr(plan, "fertilizer_target", 0) or 0)
                    - carried,
                )
                have = max(0, have - reserve)
            if have and not any(o[0] == "SELL" and o[1] == item for o in orders):
                orders.append(["SELL", item, have])
    return orders[:MAX_ORDERS]


def acquisition_orders(snap, plan, bridge_reserve=None):
    """Buy toward the plan's targets. The only place capital is committed.

    Ordered by payback, not by preference. An animal is a stream: a COW costs
    $400 and returns 1 MILK every 2 days from day 8, so it pays back only if
    bought early enough -- which is exactly what `ANIMAL_DEADLINE` encodes. Land
    is bought when the tiles we own are full, because an empty quadrant earns
    nothing and $1,000 of cash does.
    """
    orders, spend = [], max(0.0, snap.me.money - plan.cash_floor)
    livestock = spend * plan.animal_budget

    have = snap.me.animal_counts()
    in_shed = {k: int(snap.shed.get(k, 0) or 0) for k in econ.ANIMALS}
    room = snap.shed_room

    # 1. Animals. Their sticker price is not their day-zero cash requirement:
    # before first production they also create a deterministic feed obligation.
    # Reserve that bridge at the live wheat curve. This is a solvency constraint,
    # not a fitted throttle; without it the computed opening spent $3,000 down to
    # $4 on assets that could not pay for their own care before day 8-10.
    # Experimental until animals and crops are selected by one joint cash-flow
    # optimiser. In isolation this improved margin but reduced our own bank.
    if bridge_reserve is None:
        bridge_reserve = _os_top.environ.get("WB_ANIMAL_BRIDGE", "0") != "0"
    else:
        bridge_reserve = bool(bridge_reserve)
    for kind in sorted(plan.target_animals, key=lambda k: econ.ANIMALS[k]["cost"]):
        want = plan.target_animals[kind] - have.get(kind, 0) - in_shed.get(kind, 0)
        if want <= 0 or snap.step > econ.ANIMAL_DEADLINE[kind]:
            continue
        cost = econ.ANIMALS[kind]["cost"]
        feed_days = min(snap.days_left, econ.ANIMALS[kind]["first_yield_day"])
        feed_reserve = (econ.buy_cost("WHEAT", feed_days,
                                     int(snap.market_inv.get("WHEAT", econ.MARKET_I0)))
                        if bridge_reserve else 0)
        commitment = cost + feed_reserve
        n = 0
        while (n < want and n < room and livestock >= cost
               and spend >= commitment):
            n += 1
            livestock -= cost
            # Only `cost` leaves the bank this turn. The feed component is
            # removed from the planning budget so seed/land purchases cannot
            # consume it; the cash itself remains available for daily feed.
            spend -= commitment
        if n > 0 and len(orders) < MAX_ORDERS:
            orders.append(["BUY_ANIMAL", kind, n])
            room -= n

    # 2. seed enough to keep every free tile planted. Seeds do not use the shed.
    free = len([p for p in snap.me.empty]) + 4
    live_crops = {}
    for tile in snap.me.crops.values():
        crop = tile.get("crop")
        if crop:
            live_crops[crop] = live_crops.get(crop, 0) + 1
    for crop, share in sorted(plan.crop_mix.items(), key=lambda kv: -kv[1]):
        if snap.step > econ.SEED_DEADLINE.get(crop, 719):
            continue
        if getattr(plan, "crop_targets", None):
            want = (int(plan.crop_targets.get(crop, 0) or 0)
                    - int(live_crops.get(crop, 0) or 0)
                    - int(snap.seeds.get(crop, 0) or 0))
        else:
            want = int(free * share) - int(snap.seeds.get(crop, 0) or 0)
        cost = econ.CROPS[crop]["seed"]
        n = int(min(max(0, want), spend // cost, 12))
        if n > 0 and len(orders) < MAX_ORDERS:
            orders.append(["BUY_SEED", crop, n])
            spend -= n * cost

    # 3. land, once the tiles we own are worked out
    #
    # HARD CAP AT 3 QUADRANTS, never 4. `LAND_PRICES = (1000, 2000, 4000)` buys
    # NE then SW then SE; the SE purchase is the expensive one and it is the
    # one skipped. Locked, not merely defaulted: `plan.target_quadrants` is
    # clamped here regardless of what a package or portfolio asks for, so this
    # cannot be silently reopened by picking a different config elsewhere.
    #
    # The tradeoff is a wider farm against a more productive one, and the
    # asset-per-dollar comparison favours the smaller farm: $4,000 for the SE
    # quadrant buys 25 more tiles, but $4,000 is 10 COWs ($400 each) or 40
    # STRAWBERRY seed batches, either of which returns a stream, where a raw
    # tile returns nothing until it is planted AND crewed AND kept watered --
    # and this project has already measured labour, not land, as the binding
    # constraint (section 40: MAX_HANDS above ~11 loses money on a farm this
    # size for want of an extra dollar of crew, not want of an extra tile).
    MAX_QUADRANTS = econ.MAX_OWNED_QUADRANTS
    owned_extra = len(snap.me.unlocked) - 1
    if (owned_extra < min(plan.target_quadrants, MAX_QUADRANTS) - 1
            and econ.can_buy_land(len(snap.me.unlocked))
            and len(snap.me.empty) <= 4 and snap.days_left >= 8):
        price = econ.LAND_PRICES[owned_extra]
        if spend >= price * 1.4 and len(orders) < MAX_ORDERS:
            orders.append(["BUY_LAND"])
    return orders


def orders(snap, plan, tracker=None, sale_variant=None):
    if plan.phase == "endgame":
        base = []
    else:
        feed = feed_orders(
            snap, plan,
            consume_service_reserve=(
                sale_variant == "cashflow_service_timing"
            ),
        )
        feed_qty = sum(
            max(0, int(order[2])) for order in feed
            if len(order) >= 3 and order[0] == "BUY_PRODUCT"
            and order[1] == "WHEAT"
        )
        fertilizer_have = (
            int(snap.shed.get("FERTILIZER", 0) or 0)
            + _carried_quantity(snap, "FERTILIZER")
        )
        fertilizer_qty = min(
            max(0, int(getattr(plan, "fertilizer_target", 0) or 0)
                - fertilizer_have),
            max(0, int(snap.shed_room) - feed_qty),
        )
        fertilizer = ([
            ["BUY_PRODUCT", "FERTILIZER", fertilizer_qty]
        ] if fertilizer_qty else [])
        rest = (acquisition_orders(
                    snap, plan,
                    bridge_reserve=(False if sale_variant in (
                        "observation_only_timing", "one_step_inventory_option",
                        "cashflow_service_timing",
                    ) else None),
                )
                + steady_orders(snap, plan, tracker, sale_variant))
        # Ahead of acquisition in the queue: the ten-order cap is real, and a
        # flush that loses its slot is produce destroyed for a seed purchase.
        prerequisites = feed + fertilizer
        base = (prerequisites
                + rollover_flush(snap, plan, prerequisites + rest) + rest)
    if snap.step >= ENDGAME_START:
        return endgame_orders(
            snap, base,
            front_run=(sale_variant not in (
                "guaranteed_day_drain", "day_boundary_liquidation",
                "observation_only_timing", "one_step_inventory_option",
                "cashflow_service_timing",
            )),
        )
    return mask_deadlines(base, snap.step)[:MAX_ORDERS]


def same_turn_bank_orders(snap, orders, unit_actions):
    """Sell goods deposited by a DROP that executes earlier this same turn.

    Unit actions resolve before market orders. The ordinary market snapshot is
    therefore one action stale exactly when a unit is about to DROP: those
    goods are absent from ``snap.shed`` but are legal to sell moments later.
    Merge their exact inventories into a front-of-queue SELL. This is a timing
    bridge between the route and market masters, derived solely from the
    engine's commit order; it never guesses an opponent action.
    """
    banked = {}
    for idx, action in enumerate(unit_actions or ()):
        if not action or action[0] != "DROP" or idx >= len(snap.inventories):
            continue
        for item, qty in snap.inventories[idx].items():
            if item not in econ.SELLABLE or item == "WHEAT":
                continue
            n = max(0, int(qty or 0))
            if n:
                banked[item] = banked.get(item, 0) + n
    if not banked:
        return [list(order) for order in (orders or ())][:MAX_ORDERS]

    remaining = [list(order) for order in (orders or ())]
    priority = []
    for item in LIQUIDATION_ORDER:
        extra = banked.get(item, 0)
        if extra <= 0:
            continue
        inv = int(snap.market_inv.get(item, econ.MARKET_I0) or econ.MARKET_I0)
        if snap.step < 716 and econ.price(item, inv) <= SELL_FLOOR:
            continue
        existing = 0
        kept = []
        for order in remaining:
            if (len(order) >= 3 and order[0] == "SELL"
                    and str(order[1]) == item):
                existing += max(0, int(order[2] or 0))
            else:
                kept.append(order)
        remaining = kept
        priority.append(["SELL", item, existing + extra])
    return (priority + remaining)[:MAX_ORDERS]


def capacity_reserve_orders(snap, plan, orders, unit_actions,
                            projected=None, target=99, preference="price"):
    """Add only the sales proved necessary before the daily auto-deposit.

    The engine deposits every unit inventory after the last callback of a day,
    discarding anything beyond ``shedCapacity``.  Public high-scoring agents
    avoid this by projecting the unit phase and retaining a one-slot cushion.
    This implementation is tape-free: it uses the current snapshot, current
    unit actions, current market orders and the exact state projection only.

    The function is deliberately a post-process.  It cannot fund or select a
    purchase, and it never sells wheat needed by the current feed certificate
    or fertilizer named by the current plan.  If a quantity, slot, or price is
    unknown, the parent order list is preserved unchanged.
    """
    kept = [list(order) for order in (orders or ())][:MAX_ORDERS]
    step = int(getattr(snap, "step", 0) or 0)
    hour = int(getattr(snap, "hour", step % econ.TURNS_PER_DAY) or 0)
    if hour != econ.TURNS_PER_DAY - 1 or step >= ENDGAME_START:
        return kept
    try:
        target = max(0, min(int(target), int(econ.SHED_CAPACITY)))
        if projected is None:
            from whitebox import state as _state
            projected = _state.project_unit_phase(snap, unit_actions)
        # Every order is settled before the end-of-day deposit.  Count only
        # physically fillable sells; an oversized SELL is not a capacity
        # credit and must not make the certificate optimistic.
        available = {
            str(item): max(0, int(qty or 0))
            for item, qty in dict(projected.shed or {}).items()
        }
        planned_sells = {}
        for order in kept:
            if not order:
                continue
            op = str(order[0])
            if op == "SELL" and len(order) >= 3:
                item = str(order[1])
                want = max(0, int(order[2] or 0))
                take = min(want, available.get(item, 0))
                available[item] = available.get(item, 0) - take
                planned_sells[item] = planned_sells.get(item, 0) + want

        carried = sum(
            max(0, int(qty or 0))
            for inventory in (projected.inventories or ())
            for qty in inventory.values()
        )
        # Do not reserve room for a same-turn BUY_PRODUCT/BUY_ANIMAL.  Those
        # orders are capacity-gated by the engine itself, and treating their
        # requested quantity as committed would sell useful stock merely to
        # make an uncommitted purchase fit.  The portable public rule is to
        # reserve only stock already present after this turn's unit phase.
        total = sum(available.values()) + carried
        # ``available`` already subtracts the physically fillable existing
        # sells, so only the post-unit shed plus carried inventory is counted.
        need = max(0, int(total) - target)
        if need <= 0:
            return kept

        wheat_reserve = max(0, int(getattr(plan, "wheat_needed", 0) or 0))
        fertilizer_reserve = max(
            0, int(getattr(plan, "fertilizer_target", 0) or 0)
            - sum(int(iv.get("FERTILIZER", 0) or 0)
                  for iv in (projected.inventories or ()))
        )
        candidates = []
        for item in econ.SELLABLE:
            have = int(available.get(item, 0) or 0)
            if item == "WHEAT":
                have = max(0, have - wheat_reserve)
            if item == "FERTILIZER":
                have = max(0, have - fertilizer_reserve)
            if have <= 0:
                continue
            inventory = int(snap.market_inv.get(item, econ.MARKET_I0)
                            or econ.MARKET_I0)
            px = float(econ.price(item, inventory))
            if px <= SELL_FLOOR and step < 718:
                continue
            # Prefer an item with no remaining planned sell.  The public
            # room-guard ordering is available as a rule-level option; the
            # default quote ordering remains the conservative baseline for
            # this helper.  Neither branch reads a future route or tape.
            if preference == "public":
                rank = (CAPACITY_PUBLIC_PRIORITY.index(item)
                        if item in CAPACITY_PUBLIC_PRIORITY
                        else len(CAPACITY_PUBLIC_PRIORITY))
                candidates.append((planned_sells.get(item, 0) > 0, rank,
                                   item, have))
            else:
                candidates.append((planned_sells.get(item, 0) > 0, -px,
                                   item, have))
        candidates.sort()
        for _planned, _neg_px, item, have in candidates:
            if need <= 0:
                break
            qty = min(need, have)
            if qty <= 0:
                continue
            index = next(
                (i for i, order in enumerate(kept)
                 if order and len(order) >= 3 and str(order[0]) == "SELL"
                 and str(order[1]) == item),
                -1,
            )
            if index >= 0:
                kept[index][2] = max(0, int(kept[index][2] or 0)) + qty
            elif len(kept) < MAX_ORDERS:
                kept.append(["SELL", item, qty])
            else:
                continue
            planned_sells[item] = planned_sells.get(item, 0) + qty
            need -= qty
        return kept[:MAX_ORDERS]
    except Exception:
        # This is an optional post-process.  Any malformed or incomplete
        # observation must fail closed and leave the parent market plan intact.
        return [list(order) for order in (orders or ())][:MAX_ORDERS]
