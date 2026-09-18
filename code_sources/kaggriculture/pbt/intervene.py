"""Market-intervention overlay: the one counter-lever this architecture allows.

Everything else in the counter-parameter list (opening hire count, feed volume,
quadrant timing, crop preference) is compiled into the tape and cannot be moved
from outside -- measured, touching farm state drops the win rate against ref_A
from 62% to 0-5% (HANDOFF section 18). Market orders are different: they change
no tile, so they are safe to add.

Two mechanisms, both timed off the exact opponent-sales inference:

  dump    -- their sale cadence per premium item is measured from public market
             inventory; one turn before the predicted sale we push stock into
             the book so they quote into a depressed market.
  squeeze -- against an animal-heavy opponent, buy wheat inside their feeding
             window. BUY_PRODUCT removes inventory, which lifts the price they
             must pay for feed.
"""

_TEMPLATE = '''

# ============ market intervention overlay (pbt/intervene.py) ============
_IV_ENABLED = __ENABLED__
_IV_DUMP_FRAC = __DUMP__
_IV_LEAD = __LEAD__
_IV_SQUEEZE = __SQUEEZE__
_IV_REPAY = __REPAY__          # conserve total volume: repay pulled-forward units
_IV_MIRROR = __MIRROR__        # only act when the boards look near-mirrored
_IV_MIRROR_STEPS = (216, 240, 264)
_IV_MIN_OBS = 3
# Front-running only pays while there is a price to win. Once a product sits
# near its floor both players clear at the same few dollars, so dumping buys
# nothing and drives our own later units down with it. Measured in a real ladder
# loss: FERTILIZER went 43 -> 26 -> 10 -> 1 while we sold 2,738 units to the
# opponent's 1,697, and the game turned in exactly that window.
# kawa ships the same idea as _PREEMPT_MIN_PRICE_RATIO but leaves it at 0.0.
_IV_MIN_PRICE = __MINPRICE__
# Seat-conditional overrides. HANDOFF section 5 established that seat is not
# neutral -- _end_of_day rolls player 0's weeds first and _process_market
# resolves atomic orders in player order, and two byte-identical agents split
# 6/40 in seat 0's favour... against it. Our own live ladder record shows the
# same shape: seat0 34/46 (74%) vs seat1 29/35 (83%).
# The seat is readable at runtime (obs["player"]), so the layer can simply play
# differently from the disadvantaged seat. Negative/None means "same as the
# seat-agnostic value" and the whole thing compiles out.
# Sell SUPPRESSION. Every layer so far only ADDS sales; this one withholds the
# tape's own SELL orders while the price is below `base * _IV_HOLD_RATIO`, so
# stock waits for the town's next consumption tick instead of clearing into a
# floored book.
#
# Legitimacy: this rewrites action["market"] only. HANDOFF section 4 established
# the TAPE cannot be edited and section 11 that no tile-op substitution survives,
# but both are about farm actions -- market orders change no tile and are the one
# channel the tape tolerates (that is why the whole intervention layer exists).
#
# Motivation: planner/analyze_top.py over 23 replays puts us at 1,813 units sold
# at $80.4 each against ReCurSiON's 1,404 at $129.6. We are the highest-volume,
# lowest-price seller on the ladder. Suppression is the only lever that trades
# volume for price.
#
# Two hard safety valves, both non-negotiable:
#   - the shed holds 100 items and end-of-day overflow is DISCARDED, so
#     suppression stops entirely above _IV_HOLD_SHED_MAX;
#   - money in the shed at the buzzer scores zero, so suppression stops after
#     _IV_HOLD_STOP_STEP.
_IV_HOLD_RATIO = __HOLDRATIO__
_IV_HOLD_SHED_MAX = __HOLDSHEDMAX__
_IV_HOLD_STOP_STEP = __HOLDSTOP__
# Day gate. Ladder loss forensics (7 losses vs 7 wins, replay margin traced per
# day) show our losses are ENDGAME collapses rather than early deficits: in 4 of
# 7 we led by +6,900 to +9,400 at day 15 and bled it all away by day 29, while
# every win grew monotonically over the same window. Mean swing d15->d29 is
# -4,400 in losses against +10,551 in wins.
#
# HANDOFF section 14 already recorded the mechanism -- "front-running only pays
# while there is a price to win; at the floor both players clear at the same few
# dollars" -- and IV_MIN_PRICE was tested against it, scoring +100 on 12 of 24
# seeds, i.e. chance. But that was a FIELD MEAN over the whole season. A gate
# that only matters after ~day 20 is diluted by the twenty days where it does
# nothing, which is exactly the shape that measurement would miss.
#
# 0 disables (unchanged behaviour).
# Adaptive dump sizing. A fixed fraction is wrong in both directions because
# market depth differs by two orders of magnitude between products. Selling the
# 80th unit of a run returns, as a fraction of base price:
#     MELON .75   FERTILIZER .84   EGG .84   WHEAT .84
#     WOOL  .01   MILK       .01   STRAWBERRY .01
# so 70% of a wool stock craters the price we are trying to win, while 70% of a
# melon stock leaves most of the depth unused. Cumulative revenue makes the same
# point: 40 wool returns 6,809 and 80 wool returns 7,949 -- the second 40 units
# are worth $1,140 between them.
#
# The right quantity is computable exactly, because the engine's price curve is
# closed-form and the opponent's sale VOLUME is already inferred (see
# _iv_observe, which computes `theirs` and then throws the number away).
# Front-running unit k is worth  p(inv + k) - p(inv + their_volume + k)  --
# what we get selling ahead of them, minus what the same unit fetches after
# their block lands. Dump while that difference is positive and the unit still
# clears above the floor.
# Cadence estimator. The median gap is robust to outliers but slow to react if
# the opponent shifts strategy mid-season. 0 = median (shipped), 1 = linearly
# weighted toward recent gaps, 2 = most recent gap only.
#
# Prior: IV_LEAD 2/3/4 were all measured and differ little with 3 best, which
# says timing PRECISION is not the binding constraint. But the front-run audit
# shows position is what this layer actually buys (we clear ahead on 94-99% of
# firings), so the predictor is at least aimed at the right thing.
_IV_PRED_MODE = __PREDMODE__
_IV_ADAPT = __ADAPT__
_IV_MARGINAL_FLOOR = __MARGFLOOR__   # stop once a unit fetches < this x base
_IV_VOL_MULT = __VOLMULT__           # scale on the inferred opponent volume
_IV_MAX_QTY = __MAXQTY__
_IV_STOP_DAY = __STOPDAY__
_IV_LATE_DUMP = __LATEDUMP__      # dump fraction once past _IV_STOP_DAY, if still on
_IV_SEAT0_DUMP = __SEAT0DUMP__
_IV_SEAT0_MINPRICE = __SEAT0MINPRICE__
# Market orders settle in list order, so a slot's position is a price. Our dumps
# were appended last, behind the tape's own sells, which means our units clear
# into a book those sells already pushed down. Moving them to the front is safe
# in the direction that matters: the earlier failure was moving the tape's OWN
# sells behind its buys and starving them of cash -- putting extra sells first
# gives the tape's buys MORE cash, not less.
_IV_SLOT_FIRST = __SLOTFIRST__
_IV_BASE_PRICE = {"MELON": 250, "MILK": 160, "STRAWBERRY": 120, "WOOL": 200,
                  "FERTILIZER": 100, "WHEAT": 25, "EGG": 50, "CARROT": 35,
                  "TOMATO": 60}
_IV_STRUCT = __STRUCT__      # predict from the opponent's visible tiles too
_IV_STAGED = __STAGED__      # split the dump into two tranches instead of one
_IV_PREMIUM = __ITEMS__
_IV_DEBT = {}
_IV_MIRRORED = [None]
_IV_SHOPS = {
    "BAKERY": ("EGG", "WHEAT"), "PIZZA_SHOP": ("MILK", "TOMATO", "WHEAT"),
    "BRUNCH_SPOT": ("EGG", "WHEAT", "STRAWBERRY"), "YARN_STORE": ("WOOL",),
    "ICE_CREAM_SHOP": ("STRAWBERRY", "MILK", "WHEAT"), "PET_CAFE": ("CARROT",),
    "SMOOTHIE_SHOP": ("STRAWBERRY", "MILK"),
    "FARMERS_MARKET": ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY"),
}
_IV_ALL = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK",
           "WOOL", "FERTILIZER")
_IV = {"prev": None, "prev_step": None, "hits": {}, "last": {}, "mine": {},
       "vols": {}}
_IV_BASE_AGENT = agent


def _iv_town(item, step, shops):
    take = 1 if item != "FERTILIZER" and step % 24 == 0 else 0
    if step % 4 == 0:
        for s in shops:
            pr = _IV_SHOPS.get(s, ())
            if item in pr:
                take += 2 if len(pr) == 1 else 1
    return take


def _iv_observe(inv, step, shops):
    """Opponent sales fall out exactly: inv[t+1] = inv[t] + mine + theirs - town."""
    if _IV["prev"] is not None and _IV["prev_step"] is not None and step > _IV["prev_step"]:
        for item in _IV_ALL:
            delta = int(inv.get(item, 0)) - int(_IV["prev"].get(item, 0))
            taken = sum(_iv_town(item, s, shops)
                        for s in range(_IV["prev_step"], step))
            theirs = delta + taken - int(_IV["mine"].get(item, 0))
            if theirs > 0:
                h = _IV["hits"].setdefault(item, [])
                h.append(step)
                if len(h) > 12:
                    del h[0]
                # The inferred VOLUME was previously discarded. It is the input
                # the adaptive sizer needs: how big a block are we racing?
                v = _IV["vols"].setdefault(item, [])
                v.append(int(theirs))
                if len(v) > 12:
                    del v[0]
                _IV["last"][item] = step
    _IV["prev"] = dict(inv)
    _IV["prev_step"] = step
    _IV["mine"] = {}


def _iv_signature(farm):
    keys = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
            "COW", "SHEEP", "GOOSE", "PASTURE", "COOP", "WEED")
    c = {k: 0 for k in keys}
    for row in (farm.get("tiles") or []):
        for t in row:
            if not isinstance(t, dict):
                continue
            for f in ("crop", "animal", "kind"):
                v = str(t.get(f, "")).upper()
                if v in c:
                    c[v] += 1
                    break
    return (len(farm.get("hands") or []),
            len(farm.get("unlocked_quadrants") or []),
            tuple(c[k] for k in sorted(c)))


def _iv_near_mirror(farms, seat):
    """Same public shape on both boards means production cannot separate the
    game and only sale timing can."""
    if len(farms) < 2:
        return False
    a, b = _iv_signature(farms[seat]), _iv_signature(farms[1 - seat])
    d = abs(a[0] - b[0]) + 3 * abs(a[1] - b[1]) + sum(abs(x - y) for x, y in zip(a[2], b[2]))
    return d <= 6


_IV_ANIMAL = {"GOOSE": ("EGG", 4, 1), "COW": ("MILK", 8, 2), "SHEEP": ("WOOL", 6, 3)}
_IV_CROP = {"WHEAT": (2, 4, 0), "CARROT": (2, 3, 0), "TOMATO": (8, 8, 1),
            "STRAWBERRY": (10, 10, 2), "MELON": (10, 12, 0)}


def _iv_struct_next(item, farms, seat, step):
    """Next day the opponent's *visible* tiles produce `item`.

    The cadence predictor only sees what they already sold; this sees what they
    are about to have. An animal placed on day p yields on
    p + first_yield_day + k*interval by the engine's own refresh rule, and a
    crop's first yield is fixed by its growth table -- both readable straight
    off the public board before a single unit has been sold.
    """
    if len(farms) < 2:
        return None
    opp = farms[1 - seat]
    day = step // 24
    best = None
    for row in (opp.get("tiles") or []):
        for t in row:
            if not isinstance(t, dict):
                continue
            a = t.get("animal")
            if a and a in _IV_ANIMAL and _IV_ANIMAL[a][0] == item:
                _, first, iv = _IV_ANIMAL[a]
                start = int(t.get("placed_day", day)) + first
                d = start if start >= day else start + iv * (((day - start) // iv) + 1)
                if t.get("yield_units", 0) > 0:
                    d = day
                best = d if best is None else min(best, d)
            elif t.get("kind") == "PLANT" and t.get("crop") == item:
                first, mx, iv = _IV_CROP.get(item, (99, 99, 0))
                start = int(t.get("planted_day", day)) + first
                d = start if start >= day else (
                    start + iv * (((day - start) // iv) + 1) if iv else day)
                if t.get("yield_units", 0) > 0:
                    d = day
                best = d if best is None else min(best, d)
    return None if best is None else best * 24


_IV_MP = {
    "WHEAT":      (25, 400, "sqrt", 0.80, "log", 0.20),
    "CARROT":     (35, 450, "hinge", 1.00, "sqrt", 0.70),
    "TOMATO":     (60, 200, "hinge", 0.40, "sqrt", 0.60),
    "STRAWBERRY": (120, 100, "sqrt", 0.70, "linear", 1.60),
    "MELON":      (250, 300, "log", 0.20, "sq", 3.60),
    "EGG":        (50, 332, "hinge", 0.40, "log", 0.20),
    "MILK":       (160, 122, "sqrt", 0.60, "linear", 1.60),
    "WOOL":       (200, 105, "log", 0.20, "sq", 3.20),
    "FERTILIZER": (100, 200, "linear", 0.40, "linear", 0.40),
}


def _iv_shape(f, x, T):
    import math
    x = max(0.0, x)
    if f == "linear": return x
    if f == "sq":     return x * x
    if f == "sqrt":   return math.sqrt(x)
    if f == "log":    return math.log(1.0 + x)
    if f == "hinge":
        if not T or T <= 0: return x
        u = x / T
        return u + 8.0 * max(0.0, u - 1.0) ** 2
    return x


def _iv_price(item, inv):
    """The engine's own price function, inlined (kaggriculture.market_price)."""
    p = _IV_MP.get(item)
    if not p:
        return 0
    base, T, bf, bt, af, at = p
    if inv < 10000:
        amp = bt * base / _iv_shape(bf, T, T)
        v = base + amp * _iv_shape(bf, 10000 - inv, T)
    else:
        amp = at * base / _iv_shape(af, T, T)
        v = base - amp * _iv_shape(af, inv - 10000, T)
    return max(1, int(round(v)))


def _iv_optimal_qty(item, inv, have, opp_vol):
    """How many units to push ahead of an opponent block of `opp_vol`.

    Unit k is worth p(inv+k) now against p(inv+opp_vol+k) after their block
    lands, so the gain from front-running it is the difference. Take units while
    that gain is positive and the unit still clears the floor guard.
    """
    base = _IV_MP.get(item, (100,))[0]
    floor = base * _IV_MARGINAL_FLOOR
    vol = int(max(0, opp_vol) * _IV_VOL_MULT)
    n = 0
    while n < have and n < _IV_MAX_QTY:
        now = _iv_price(item, inv + n)
        if now < floor:
            break
        later = _iv_price(item, inv + vol + n)
        if now - later <= 0 and n > 0:
            break
        n += 1
    return n


def _iv_volume(item):
    v = _IV["vols"].get(item) or []
    if not v:
        return 0
    sv = sorted(v[-6:])
    return sv[len(sv) // 2]


def _iv_predict(item, step):
    h = _IV["hits"].get(item) or []
    if len(h) < _IV_MIN_OBS:
        return None
    gaps = [b - a for a, b in zip(h, h[1:]) if b > a]
    if not gaps:
        return None
    if _IV_PRED_MODE == 2:
        period = gaps[-1]
    elif _IV_PRED_MODE == 1:
        w = list(range(1, len(gaps) + 1))
        period = int(round(sum(g * x for g, x in zip(gaps, w)) / sum(w)))
    else:
        sg = sorted(gaps)
        period = sg[len(sg) // 2]
    if period <= 0:
        return None
    return h[-1] + period


def agent(obs):
    action = _IV_BASE_AGENT(obs)
    if not _IV_ENABLED:
        return action
    try:
        o = obs if isinstance(obs, dict) else dict(obs)
        step = int(o.get("step", 0) or 0)
        if not step:
            step = int(o.get("day", 0) or 0) * 24 + int(o.get("hour", 0) or 0)
        if step == 0:
            _IV.update({"prev": None, "prev_step": None, "hits": {}, "last": {},
                        "mine": {}, "vols": {}})
            _IV_DEBT.clear(); _IV_MIRRORED[0] = None
        seat = int(o.get("player", 0) or 0)
        farms = o.get("farms") or []
        market = o.get("market") or {}
        shops = tuple((o.get("town") or {}).get("unlocked_shops") or ())
        _iv_observe(market.get("inventory") or {}, step, shops)
        if seat >= len(farms) or len(farms) < 2:
            return action
        shed = ((o.get("private") or {}).get("shed") or {})
        orders = [list(x) for x in (action.get("market") or [])]
        already = {x[1] for x in orders if x and x[0] == "SELL" and len(x) >= 2}

        if _IV_HOLD_RATIO > 0 and step < _IV_HOLD_STOP_STEP:
            shed_used = sum(int(v or 0) for v in shed.values())
            if shed_used <= _IV_HOLD_SHED_MAX:
                kept = []
                prices_now = market.get("prices") or {}
                for x in orders:
                    if x and x[0] == "SELL" and len(x) >= 2:
                        base = _IV_BASE_PRICE.get(x[1], 100)
                        px = float(prices_now.get(x[1], 0) or 0)
                        if px < base * _IV_HOLD_RATIO:
                            continue
                    kept.append(x)
                orders = kept
                already = {x[1] for x in orders if x and x[0] == "SELL" and len(x) >= 2}

        if _IV_MIRROR and step in _IV_MIRROR_STEPS:
            _IV_MIRRORED[0] = _iv_near_mirror(farms, seat)
        gate_ok = (not _IV_MIRROR) or bool(_IV_MIRRORED[0])

        # Repay first: units pulled forward are subtracted from the tape's own
        # later SELL of the same item, so the two-turn total is conserved and we
        # never sell stock twice.
        if _IV_REPAY and _IV_DEBT:
            newo = []
            for x in orders:
                if x and x[0] == "SELL" and len(x) >= 3 and _IV_DEBT.get(x[1], 0) > 0:
                    q = int(x[2]); cut = min(q, _IV_DEBT[x[1]])
                    _IV_DEBT[x[1]] -= cut; q -= cut
                    if q <= 0:
                        continue
                    x = [x[0], x[1], q]
                newo.append(x)
            orders = newo
            already = {x[1] for x in orders if x and x[0] == "SELL" and len(x) >= 2}

        day_now = step // 24
        if _IV_STOP_DAY and day_now >= _IV_STOP_DAY and _IV_LATE_DUMP <= 0:
            gate_ok = False

        # dump ahead of their predicted sale
        for item in (_IV_PREMIUM if gate_ok else ()):
            if len(orders) >= 10 or item in already:
                continue
            nxt = _iv_predict(item, step)
            if _IV_STRUCT:
                sn = _iv_struct_next(item, farms, seat, step)
                # take whichever signal fires first -- behaviour or board state
                if sn is not None and (nxt is None or sn < nxt):
                    nxt = sn
            if nxt is None or not (step < nxt <= step + _IV_LEAD):
                continue
            _mp = _IV_MIN_PRICE
            if seat == 0 and _IV_SEAT0_MINPRICE is not None:
                _mp = _IV_SEAT0_MINPRICE
            if _mp > 0:
                px = float((market.get("prices") or {}).get(item, 0) or 0)
                base = _IV_BASE_PRICE.get(item, 100)
                if px < base * _mp:
                    continue
            have = int(shed.get(item, 0) or 0)
            frac = _IV_DUMP_FRAC
            if _IV_STOP_DAY and day_now >= _IV_STOP_DAY and _IV_LATE_DUMP > 0:
                frac = _IV_LATE_DUMP
            if seat == 0 and _IV_SEAT0_DUMP is not None:
                frac = _IV_SEAT0_DUMP
            if _IV_STAGED:
                # two tranches: a smaller lead-in avoids driving the price off a
                # cliff with one block, so the later units clear higher
                frac = _IV_DUMP_FRAC * (0.5 if nxt - step > 1 else 1.0)
            if _IV_ADAPT:
                inv_now = int((market.get("inventory") or {}).get(item, 10000) or 10000)
                qty = _iv_optimal_qty(item, inv_now, have, _iv_volume(item))
            else:
                qty = int(have * frac)
            if qty > 0:
                if _IV_SLOT_FIRST:
                    orders.insert(0, ["SELL", item, qty])
                else:
                    orders.append(["SELL", item, qty])
                if _IV_REPAY:
                    _IV_DEBT[item] = _IV_DEBT.get(item, 0) + qty

        # squeeze feed price against an animal-heavy opponent
        if _IV_SQUEEZE and len(orders) < 10:
            opp = farms[1 - seat]
            animals = sum(1 for row in (opp.get("tiles") or []) for t in row
                          if isinstance(t, dict) and "animal" in t)
            if animals >= _IV_SQUEEZE:
                money = float(farms[seat].get("money", 0) or 0)
                px = max(1, int((market.get("prices") or {}).get("WHEAT", 25)))
                room = 100 - sum(shed.values())
                n = int(min(animals, room, max(0, (money - 500) // px)))
                if n > 0 and not any(x[0] == "BUY_PRODUCT" and x[1] == "WHEAT"
                                     for x in orders if x):
                    orders.append(["BUY_PRODUCT", "WHEAT", n])
        action["market"] = orders[:10]
        for x in action["market"]:
            if x and x[0] == "SELL" and len(x) >= 3:
                _IV["mine"][x[1]] = _IV["mine"].get(x[1], 0) + int(x[2])
    except Exception:
        return action
    return action
'''


PREMIUM = ("MELON", "MILK", "STRAWBERRY", "WOOL")
PREMIUM_FERT = PREMIUM + ("FERTILIZER",)


def intervene_src(enabled=1, dump_frac=0.8, lead=1, squeeze=0,
                  repay=0, mirror=0, items=PREMIUM, struct=0, staged=0,
                  min_price=0.0, slot_first=0, seat0_dump=None,
                  seat0_min_price=None, hold_ratio=0.0, hold_shed_max=70,
                  hold_stop_step=600, stop_day=0, late_dump=0.0,
                  adapt=0, marginal_floor=0.25, vol_mult=1.0, max_qty=60,
                  pred_mode=0):
    return (_TEMPLATE.replace("__ENABLED__", str(bool(enabled)))
            .replace("__DUMP__", repr(float(dump_frac)))
            .replace("__LEAD__", str(int(lead)))
            .replace("__SQUEEZE__", str(int(squeeze)))
            .replace("__REPAY__", str(bool(repay)))
            .replace("__MIRROR__", str(bool(mirror)))
            .replace("__ITEMS__", repr(tuple(items)))
            .replace("__STRUCT__", str(bool(struct)))
            .replace("__STAGED__", str(bool(staged)))
            .replace("__MINPRICE__", repr(float(min_price)))
            .replace("__SLOTFIRST__", str(bool(slot_first)))
            .replace("__HOLDRATIO__", repr(float(hold_ratio)))
            .replace("__HOLDSHEDMAX__", str(int(hold_shed_max)))
            .replace("__HOLDSTOP__", str(int(hold_stop_step)))
            .replace("__SEAT0DUMP__", repr(None if seat0_dump is None else float(seat0_dump)))
            .replace("__SEAT0MINPRICE__", repr(None if seat0_min_price is None else float(seat0_min_price)))
            .replace("__STOPDAY__", str(int(stop_day)))
            .replace("__LATEDUMP__", repr(float(late_dump)))
            .replace("__ADAPT__", str(bool(adapt)))
            .replace("__MARGFLOOR__", repr(float(marginal_floor)))
            .replace("__VOLMULT__", repr(float(vol_mult)))
            .replace("__MAXQTY__", str(int(max_qty)))
            .replace("__PREDMODE__", str(int(pred_mode))))
