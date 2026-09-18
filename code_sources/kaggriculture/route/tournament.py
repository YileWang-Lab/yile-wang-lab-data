"""Round-robin between every loadable reference agent (and ours).

Each pair plays both seat orders on every seed, because seat is not neutral:
_process_market resolves players in order and _end_of_day spawns player 0's
weeds first, so a score measured in one seat says nothing about the other.
"""
import argparse
import itertools
import json
import multiprocessing
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

REFS = [
    # Ordered by measured strength against our build (paired margin, 20 seeds x
    # both seats). kawa is in a class of its own: +1,176 against us where the
    # next-hardest is +13,311.
    "kaggriculture-multi-route-farming-agent",          # kawa  +1,176
    "kaggriculture-frontier-the-soil-remembers-rain",   #       +13,311
    "v111-8c4s-economic-core-premium-lead",             #       +14,798
    "kaggriculture-breaking-the-tie-2883-score",        #       +17,284
    "kaggriculture-rank-your-agent",
    "kaggriculture-3000-socre",
    "15-16-strict-future-v25-meta-reset",               # Kaito Fukami v25, +27,512
    "strong-barnyard-economist",                        #       +33,887
    "kaggriculture-pure-architecture-2600-elo-v3",      #       +39,589
]


_adc = [0]

HYBRID_CONFIGS = {
    "HYBRID_passthrough": {"OVERRIDE_SELLS": 0},
}

# Searched overrides for the base agent's hand-set runtime constants.
TUNED_CONFIGS = {
    "TUNED_v12_mf0_b30": {"_PREEMPT_MIN_FUTURE_QUANTITY": 0, "_PREEMPT_MAX_BATCH": 30},
    "TUNED_v11_aggro": {"_PREEMPT_FRACTION": 3.0, "_PREEMPT_MAX_BATCH": 40,
                        "_PREEMPT_MAX_CLONE_DISTANCE": 40, "_PREEMPT_START": 0},
    # PBT round-5 champion.
    "PBT_r5": {"_PREEMPT_FRACTION": 2.9166, "_PREEMPT_MAX_BATCH": 32,
               "_PREEMPT_MAX_CLONE_DISTANCE": 40, "_PREEMPT_MIN_FUTURE_QUANTITY": 0},
}


def _make(name):
    from search.evaluate import load_ref_agent
    if name in TUNED_CONFIGS:
        from route.batch import load_base
        return load_base(TUNED_CONFIGS[name]).agent
    if name in HYBRID_CONFIGS:
        from route.hybrid import make_agent
        return make_agent(HYBRID_CONFIGS[name])
    if name == "ADAPTIVE_v2":
        import importlib.util
        global _adc
        _adc[0] += 1
        sp = importlib.util.spec_from_file_location(
            f"adap_{_adc[0]}_{os.getpid()}", os.path.join(ROOT, "agents", "adaptive_v2.py"))
        md = importlib.util.module_from_spec(sp); sp.loader.exec_module(md)
        return md.agent
    if name == "OURS":
        from route.evaluate import load_route_instance
        best = os.path.join(ROOT, "route", "checkpoints", "best_route6.json")
        params = json.load(open(best)).get("params") if os.path.exists(best) else {}
        return load_route_instance(params or {}).agent
    return load_ref_agent(name)


def play(job):
    from kaggle_environments import make
    a, b, seed = job
    try:
        env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": seed},
                   debug=False)
        env.run([_make(a), _make(b)])
        f = env.steps[-1]
        return (a, b, seed,
                float(f[0].observation["farms"][0]["money"]),
                float(f[1].observation["farms"][1]["money"]), None)
    except Exception as exc:
        return (a, b, seed, 0.0, 0.0, repr(exc)[:200])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="*", default=[11, 47, 101])
    ap.add_argument("--workers", type=int, default=26)
    ap.add_argument("--include-ours", action="store_true")
    ap.add_argument("--include-hybrid", action="store_true")
    ap.add_argument("--include-tuned", action="store_true")
    args = ap.parse_args()

    agents = list(REFS)
    if args.include_hybrid:
        agents += list(HYBRID_CONFIGS)
    if args.include_tuned:
        agents += list(TUNED_CONFIGS) + ["ADAPTIVE_v2"]
    if args.include_ours:
        agents += ["OURS"]
    jobs = [(a, b, s) for a, b in itertools.permutations(agents, 2) for s in args.seeds]
    print(f"{len(agents)} agents, {len(jobs)} games", flush=True)

    ctx = multiprocessing.get_context("forkserver")
    with ctx.Pool(processes=args.workers) as pool:
        results = pool.map(play, jobs)

    wins = defaultdict(int); games = defaultdict(int)
    money = defaultdict(float); errs = defaultdict(int)
    head = defaultdict(lambda: [0, 0])
    for a, b, s, ma, mb, err in results:
        if err:
            errs[a] += 1; errs[b] += 1
            continue
        games[a] += 1; games[b] += 1
        money[a] += ma; money[b] += mb
        if ma > mb:
            wins[a] += 1; head[(a, b)][0] += 1
        elif mb > ma:
            wins[b] += 1; head[(a, b)][1] += 1

    print(f"\n{'agent':<46}{'win%':>7}{'W':>5}{'G':>5}{'mean $':>11}{'err':>5}")
    table = sorted(agents, key=lambda x: -(wins[x] / max(games[x], 1)))
    for name in table:
        g = max(games[name], 1)
        print(f"{name:<46}{wins[name]/g:>6.0%}{wins[name]:>5}{games[name]:>5}"
              f"{money[name]/g:>11,.0f}{errs[name]:>5}")
    with open(os.path.join(ROOT, "route", "checkpoints", "tournament.json"), "w") as f:
        json.dump({"results": [list(r) for r in results]}, f, indent=1)
    print("\nsaved -> route/checkpoints/tournament.json")


if __name__ == "__main__":
    main()
