"""Daily-hire + idle-hand overlay, appended to the baked submission.

Ladder losses traced to a defect baked into all five tapes: **day 1 is empty**
-- 0 hand slots, 0 hand actions, 0 HIRE orders -- so the farm runs day 1 on the
farmer alone while animals go untended. Four hires cost fib(0..3) = $7 and the
tape leaves $23 on hand, so this is not a cash problem; the schedule simply
never hires that day.

Hiring alone is not enough: the tape has no scripted work for those bodies, so
they would stand idle. This overlay therefore does two things -- it keeps a
minimum crew every day, and it drives any hand the tape has left with PASS
using live farm state.

The filler is deliberately restricted to WATER / FEED / CARE /
COLLECT_FERTILIZER / HARVEST. It never DIGs, PLANTs, BUILDs or PLACEs: those
consume seeds and tiles the tape has budgeted, and a spare body must never
change the board the tape is counting on.
"""

def overlay_src(min_hands=4, fill_idle=1, cash_floor=2, day1_only=0):
    src = _TEMPLATE
    src = src.replace("__MINH__", str(int(min_hands)))
    src = src.replace("__FILL__", str(bool(fill_idle)))
    src = src.replace("__FLOOR__", str(int(cash_floor)))
    src = src.replace("__DAY1ONLY__", str(bool(day1_only)))
    return src


_TEMPLATE = '''

# ============ daily-hire + idle-hand overlay (route/overlay.py) ============
_OV_MIN_HANDS = __MINH__
_OV_CASH_FLOOR = __FLOOR__
_OV_MAX_HANDS = 14
_OV_DAY1_ONLY = __DAY1ONLY__
_OV_FILL_IDLE = __FILL__
_OV_SHED = [(4, 4), (5, 4), (4, 5), (5, 5)]
_OV_BASE_AGENT = agent


def _ov_pos(farm, idx):
    if idx == 0:
        return tuple(farm["farmer"])
    hs = farm.get("hands") or []
    return tuple(hs[idx - 1]) if idx - 1 < len(hs) else None


def _ov_step_toward(a, b):
    if a[1] < b[1]:
        return ["SOUTH"]
    if a[1] > b[1]:
        return ["NORTH"]
    if a[0] < b[0]:
        return ["EAST"]
    if a[0] > b[0]:
        return ["WEST"]
    return None


def _ov_fib(n):
    x, y = 1, 1
    for _ in range(n):
        x, y = y, x + y
    return x


def _ov_tape_hires(action):
    return sum(1 for x in (action.get("market") or []) if x and x[0] == "HIRE")


def _ov_jobs(farm, inv):
    """Safe outstanding work: never mutates what the tape has budgeted."""
    out = []
    for y, row in enumerate(farm.get("tiles") or []):
        for x, t in enumerate(row):
            if not isinstance(t, dict):
                continue
            if "animal" in t:
                if t.get("yield_units", 0) > 0:
                    out.append(((x, y), ["HARVEST"], 90))
                if not t.get("cared_today"):
                    out.append(((x, y), ["CARE"], 70))
                if not t.get("fed_today") and inv.get("WHEAT", 0) > 0:
                    out.append(((x, y), ["FEED"], 100))
                if t.get("fertilizer_available"):
                    out.append(((x, y), ["COLLECT_FERTILIZER"], 20))
            elif t.get("kind") == "PLANT":
                if not t.get("watered_today"):
                    out.append(((x, y), ["WATER"], 80))
                if t.get("yield_units", 0) > 0:
                    out.append(((x, y), ["HARVEST"], 85))
    return out


def agent(obs):
    action = _OV_BASE_AGENT(obs)
    try:
        o = obs if isinstance(obs, dict) else dict(obs)
        step = int(o.get("step", 0) or 0)
        if not step:
            step = int(o.get("day", 0) or 0) * 24 + int(o.get("hour", 0) or 0)
        day, hour = step // 24, step % 24
        seat = int(o.get("player", 0) or 0)
        farms = o.get("farms") or []
        if seat >= len(farms):
            return action
        farm = farms[seat]
        money = float(farm.get("money", 0) or 0)
        live = len(farm.get("hands") or [])
        hires_today = int(farm.get("hires_today", 0) or 0)

        # 1. keep a minimum crew. Hands are cleared every night, so a day with
        #    no HIRE is a day with no labour at all.
        market = [list(x) for x in (action.get("market") or [])]
        planned = sum(1 for x in market if x and x[0] == "HIRE")
        want = _OV_MIN_HANDS - (live + planned)
        # Never hire on a day the tape hires: _do_hire bumps hires_today, and the
        # tape's own HIRE list is priced fib(hires_today) assuming it starts at 0.
        # Pre-empting four hires reprices its five from $7 to $81 and it goes
        # crewless. Measured 0% win rate.
        if _ov_tape_hires(action) > 0:
            want = 0
        if _OV_DAY1_ONLY and day != 1:
            want = 0
        if hour <= 2 and want > 0 and len(market) < 10:
            for k in range(want):
                cost = _ov_fib(hires_today + planned + k)
                if money - cost < _OV_CASH_FLOOR or len(market) >= 10:
                    break
                if live + planned + k >= _OV_MAX_HANDS:
                    break
                market.append(["HIRE"])
                money -= cost
            action["market"] = market[:10]

        # 2. Drive hands ONLY on a day the tape owns no hands at all.
        #    A tape PASS is a hand holding station: the next scripted action for
        #    that hand assumes its current square, so moving it desynchronises
        #    the rest of its schedule. Measured: filling tape-owned hands drops
        #    the win rate against ref_A from 62% to 0%. Day 1 is the one day
        #    every tape ships with zero hand slots, so those bodies are ours.
        tape_owns = any(h and h[0] != "PASS" for h in (action.get("hands") or []))
        if _OV_FILL_IDLE and live and not tape_owns and _ov_tape_hires(action) == 0:
            hands = [list(h) if h else ["PASS"] for h in (action.get("hands") or [])]
            hands = (hands + [["PASS"]] * live)[:live]
            invs = ((o.get("private") or {}).get("inventories") or [{}])
            busy = set()
            for i, h in enumerate(hands):
                if h and h[0] != "PASS":
                    busy.add(i)
            jobs = _ov_jobs(farm, {})
            taken = set()
            for i in range(live):
                if i in busy:
                    continue
                pos = _ov_pos(farm, i + 1)
                if pos is None:
                    continue
                inv = invs[i + 1] if i + 1 < len(invs) else {}
                cand = [j for j in _ov_jobs(farm, inv) if j[0] not in taken]
                if not cand:
                    break
                cand.sort(key=lambda j: (-j[2] + abs(j[0][0] - pos[0]) + abs(j[0][1] - pos[1]) * 1.0))
                tgt, ops, _pri = cand[0]
                taken.add(tgt)
                if pos == tgt:
                    hands[i] = list(ops)
                else:
                    mv = _ov_step_toward(pos, tgt)
                    if mv:
                        hands[i] = mv
            action["hands"] = hands
    except Exception:
        return action
    return action
'''
