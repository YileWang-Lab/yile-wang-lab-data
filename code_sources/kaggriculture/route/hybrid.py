"""Hybrid agent: the strongest reference's production schedule + our market layer.

The round-robin (route/tournament.py) ranked the six loadable reference agents;
`multi-route-farming-agent` won at 72%, and ours came last at 0/36. Its edge is
a precomputed 720-step tape chosen at runtime from five variants according to
which shops the town unlocks -- 12 sheep when a YARN_STORE opens first (a
single-product shop eats 2 wool per tick), 10 cows when the milk shops appear.

The competition permits reusing published notebooks, and the user has confirmed
they want that. So this keeps their farm actions and their HIRE/BUY orders
verbatim -- those are load-bearing, the tape assumes exactly that crew and those
purchases -- and replaces only the SELL side, where our own machinery measured
better: exact opponent-sales inference (route/opponent.py, validated to zero
error on the premium products) driving per-product reserve prices, plus the
town-tick front-run.
"""
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from route.opponent import OpponentModel, town_take  # noqa: E402

BASE_AGENT = "kaggriculture-multi-route-farming-agent"
MAX_ORDERS = 10
SEASON_DAYS = 30
SHED_CAPACITY = 100

SELL_PRIORITY = ["MELON", "WOOL", "MILK", "STRAWBERRY", "TOMATO", "CARROT",
                 "EGG", "FERTILIZER", "WHEAT"]
FRONT_RUN_ITEMS = ("MELON", "MILK", "STRAWBERRY", "WOOL")

DEFAULTS = {
    "OVERRIDE_SELLS": 1,
    "FRONT_RUN": 1,
    "OPP_MODEL": 1,
    "OPP_SCALE_LO": 0.65,
    "OPP_SCALE_HI": 1.30,
    "OPP_HORIZON_DAYS": 6,
    "RESERVE_SCALE": 1.0,
    "SHED_PANIC_FRACTION": 0.62,
    "TERMINAL_STEP": 680,
    "RAMP_START_DAY": 25,
    "RAMP_END_DAY": 29,
    "RES_MILK": 55.0, "RES_WOOL": 60.0, "RES_STRAWBERRY": 45.0,
    "RES_MELON": 70.0, "RES_FERTILIZER": 25.0, "RES_EGG": 20.0, "RES_WHEAT": 12.0,
}

_counter = [0]


def _load_base():
    _counter[0] += 1
    path = os.path.join(ROOT, "opponents", f"{BASE_AGENT}.py")
    spec = importlib.util.spec_from_file_location(
        f"hybrid_base_{_counter[0]}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _get(obs, key, default=None):
    if isinstance(obs, dict):
        return obs.get(key, default)
    return getattr(obs, key, default)


def make_agent(params=None):
    """One independently-configured hybrid instance."""
    cfg = dict(DEFAULTS)
    cfg.update(params or {})
    base = _load_base()
    model = OpponentModel()
    state = {"last_sales": {}}

    reserve = {item: float(cfg.get("RES_" + item, 20.0)) for item in
               ("MILK", "WOOL", "STRAWBERRY", "MELON", "FERTILIZER", "EGG", "WHEAT")}

    def ramp(day):
        if day < cfg["RAMP_START_DAY"]:
            return 1.0
        if day >= cfg["RAMP_END_DAY"]:
            return 0.0
        span = max(1, cfg["RAMP_END_DAY"] - cfg["RAMP_START_DAY"])
        return max(0.0, 1.0 - (day - cfg["RAMP_START_DAY"]) / span)

    def agent(obs):
        action = base.agent(obs)
        if not cfg["OVERRIDE_SELLS"]:
            return action

        o = obs if isinstance(obs, dict) else dict(obs)
        player = int(o.get("player", 0) or 0)
        farms = o.get("farms") or []
        if not farms or player >= len(farms):
            return action
        day = int(o.get("day", 0) or 0)
        hour = int(o.get("hour", 0) or 0)
        step = day * 24 + hour
        private = o.get("private") or {}
        shed = dict(private.get("shed") or {})
        market = o.get("market") or {}
        prices = market.get("prices") or {}
        shops = tuple((o.get("town") or {}).get("unlocked_shops") or ())
        opp_farm = farms[1 - player] if len(farms) > 1 else None

        if cfg["OPP_MODEL"]:
            model.observe(market.get("inventory") or {}, step, shops,
                          state["last_sales"])

        orders = [list(x) for x in (action.get("market") or [])]
        their_sells = {}
        for x in orders:
            if x and x[0] == "SELL" and len(x) >= 3:
                their_sells[x[1]] = their_sells.get(x[1], 0) + int(x[2])

        # Their orders are kept verbatim, in their original positions. The tape
        # sequences SELL before BUY on purpose -- market orders settle in list
        # order, so the sale funds the purchase in the same turn. Moving sells
        # to the end starved every purchase and collapsed the run to $210.
        out = list(orders)

        shed_used = sum(shed.values())
        panic = shed_used > SHED_CAPACITY * cfg["SHED_PANIC_FRACTION"]
        terminal = step >= cfg["TERMINAL_STEP"]
        r = ramp(day)
        sold = dict(their_sells)

        for item in SELL_PRIORITY:
            if len(out) >= MAX_ORDERS:
                break
            have = int(shed.get(item, 0)) - their_sells.get(item, 0)
            if have <= 0:
                continue
            if item == "WHEAT" and not terminal:
                continue          # feed stock; the tape manages it
            if terminal:
                out.append(["SELL", item, have])
                sold[item] = sold.get(item, 0) + have
                continue
            scale, glut = 1.0, False
            if cfg["OPP_MODEL"] and opp_farm is not None:
                scale = model.reserve_scale(opp_farm, item, day, step, shops,
                                            lo=cfg["OPP_SCALE_LO"],
                                            hi=cfg["OPP_SCALE_HI"],
                                            horizon_days=int(cfg["OPP_HORIZON_DAYS"]))
                glut = scale < 1.0
            if (cfg["FRONT_RUN"] and item in FRONT_RUN_ITEMS and not panic
                    and not glut and town_take(item, step, shops) > 0):
                continue
            floor = reserve.get(item, 20.0) * cfg["RESERVE_SCALE"] * r * scale
            if prices.get(item, 0) >= floor or panic:
                out.append(["SELL", item, int(have)])
                sold[item] = sold.get(item, 0) + int(have)

        state["last_sales"] = sold
        action["market"] = out[:MAX_ORDERS]
        return action

    return agent


agent = make_agent()
