"""Diff the ECONOMIC SCHEDULE of the tape against our planner, day by day.

spec_extract.py compares season totals, which says our planner runs a farm about
two thirds the size but does not say WHEN it falls behind. The economy here is a
chain -- land unlocks tiles, tiles create seed demand, seeds create PLANT tasks,
PLANT tasks justify a crew -- so a total that is 0.68x could originate anywhere
in it. This traces both agents on the same seed and prints the chain per day.

That ordering is also why the MIN_CREW experiment failed (planner/v2_sweep.py,
-13k to -52k): it forced hires without first creating the tiles that would give
them work, so the crew burned fib-priced cash standing idle. Any fix has to move
the INVESTMENT side first.

Usage:
    /home/yilewang/kagg-env/bin/python -m planner.schedule_diff [seed]
"""
import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from planner.simulate import Simulator  # noqa: E402
from route.search import to_params  # noqa: E402

GENOME = os.path.join(ROOT, "planner", "checkpoints", "best_genome1.json")
_n = [0]


def _load(path, genome=None):
    _n[0] += 1
    s = importlib.util.spec_from_file_location(f"sd_{os.getpid()}_{_n[0]}", path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    if genome is not None:
        m.configure(to_params(genome))
        return m.agent
    return getattr(m, "_submission_entry", None) or m.agent


def instrument(agent, log):
    """Wrap an agent so its market orders and board state are recorded per day."""
    def wrapped(obs):
        a = agent(obs)
        d = int(obs.get("day", 0))
        seat = int(obs.get("player", 0))
        farm = (obs.get("farms") or [])[seat]
        rec = log.setdefault(d, {"HIRE": 0, "LAND": 0, "seeds": {}, "animals": {},
                                 "wheat_buy": 0, "sold": 0, "money_start": None,
                                 "tiles_owned": 0, "planted": 0, "animals_placed": 0})
        if rec["money_start"] is None:
            rec["money_start"] = farm["money"]
            owned = planted = placed = 0
            for row in farm["tiles"]:
                for t in row:
                    if t == "LOCKED":
                        continue
                    owned += 1
                    if isinstance(t, dict):
                        if t.get("kind") == "PLANT":
                            planted += 1
                        elif "animal" in t:
                            placed += 1
            rec["tiles_owned"] = owned
            rec["planted"] = planted
            rec["animals_placed"] = placed
        for o in (a.get("market") or []):
            if not isinstance(o, list) or not o:
                continue
            if o[0] == "HIRE":
                rec["HIRE"] += 1
            elif o[0] == "BUY_LAND":
                rec["LAND"] += 1
            elif o[0] == "BUY_SEED":
                rec["seeds"][o[1]] = rec["seeds"].get(o[1], 0) + int(o[2])
            elif o[0] == "BUY_ANIMAL":
                rec["animals"][o[1]] = rec["animals"].get(o[1], 0) + int(o[2])
            elif o[0] == "BUY_PRODUCT" and o[1] == "WHEAT":
                rec["wheat_buy"] += int(o[2])
            elif o[0] == "SELL":
                rec["sold"] += int(o[2])
        return a
    return wrapped


def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1009
    genome = json.load(open(GENOME))["genome"]
    opp_path = os.path.join(ROOT, "opponents", "v111-8c4s-economic-core-premium-lead.py")

    klog, rlog = {}, {}
    kawa = instrument(_load(os.path.join(
        ROOT, "opponents", "kaggriculture-multi-route-farming-agent.py")), klog)
    sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
    km, _ = sim.run_episode(kawa, _load(opp_path))

    route = instrument(_load(os.path.join(ROOT, "route", "agent.py"), genome), rlog)
    sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
    rm, _ = sim.run_episode(route, _load(opp_path))

    print(f"seed {seed}   kawa banks ${km:,.0f}   route banks ${rm:,.0f}   "
          f"ratio {rm/km if km else 0:.2f}x")
    print()
    print("                    TAPE (kawa)                    |            PLANNER (route)")
    print("day  cash   til pl an | hire land seed anml whbuy | cash   til pl an | hire land seed anml whbuy")
    for d in range(30):
        k = klog.get(d, {})
        r = rlog.get(d, {})

        def f(rec):
            if not rec:
                return " " * 46
            return (f"{rec['money_start']/1000:>5.0f}k {rec['tiles_owned']:>3} "
                    f"{rec['planted']:>2} {rec['animals_placed']:>2} | "
                    f"{rec['HIRE']:>4} {rec['LAND']:>4} {sum(rec['seeds'].values()):>4} "
                    f"{sum(rec['animals'].values()):>4} {rec['wheat_buy']:>5}")
        print(f"{d:3d}  {f(k)} | {f(r)}")

    print()
    print(f"{'':16} {'TAPE':>10} {'PLANNER':>10} {'ratio':>8}")
    for label, key in (("total hires", "HIRE"), ("land buys", "LAND"),
                       ("wheat bought", "wheat_buy"), ("units sold", "sold")):
        kt = sum(v.get(key, 0) for v in klog.values())
        rt = sum(v.get(key, 0) for v in rlog.values())
        print(f"{label:<16} {kt:>10,} {rt:>10,} {rt/kt if kt else 0:>7.2f}x")
    for label, key in (("seeds bought", "seeds"), ("animals bought", "animals")):
        kt = sum(sum(v.get(key, {}).values()) for v in klog.values())
        rt = sum(sum(v.get(key, {}).values()) for v in rlog.values())
        print(f"{label:<16} {kt:>10,} {rt:>10,} {rt/kt if kt else 0:>7.2f}x")
    # peak board usage
    kp = max((v["planted"] + v["animals_placed"]) for v in klog.values())
    rp = max((v["planted"] + v["animals_placed"]) for v in rlog.values())
    kt_ = max(v["tiles_owned"] for v in klog.values())
    rt_ = max(v["tiles_owned"] for v in rlog.values())
    print(f"{'peak tiles used':<16} {kp:>10,} {rp:>10,} {rp/kp if kp else 0:>7.2f}x")
    print(f"{'peak land owned':<16} {kt_:>10,} {rt_:>10,} {rt_/kt_ if kt_ else 0:>7.2f}x")


if __name__ == "__main__":
    main()
