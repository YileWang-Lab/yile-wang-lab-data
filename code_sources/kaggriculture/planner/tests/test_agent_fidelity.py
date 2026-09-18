"""Live-play fidelity: does planner.simulate produce the same final banks as
kaggle_environments when BOTH sides are real agent code making real decisions?

test_sim_fidelity.py replays *recorded actions* from real replays, which never
invokes an agent -- so it cannot catch anything about how agents are called.
This test closes that hole. It caught the missing `configuration` argument
(5 of the 9 pool agents are declared `agent(obs, config=None)` and were being
silently run on their fallback constants).

Usage:
    /home/yilewang/kagg-env/bin/python -m planner.tests.test_agent_fidelity
"""
import importlib.util
import multiprocessing
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from planner.simulate import Simulator  # noqa: E402

OPPONENT_DIR = os.path.join(ROOT, "opponents")

POOL = [
    "kaggriculture-multi-route-farming-agent",
    "kaggriculture-frontier-the-soil-remembers-rain",
    "v111-8c4s-economic-core-premium-lead",
    "kaggriculture-breaking-the-tie-2883-score",
    "kaggriculture-rank-your-agent",
    "kaggriculture-3000-socre",
    "15-16-strict-future-v25-meta-reset",
    "strong-barnyard-economist",
    "kaggriculture-pure-architecture-2600-elo-v3",
]

SEEDS = [1009, 88301]
_n = [0]


def _load(name):
    _n[0] += 1
    path = os.path.join(OPPONENT_DIR, f"{name}.py")
    spec = importlib.util.spec_from_file_location(
        f"fid_{name.replace('-', '_')}_{os.getpid()}_{_n[0]}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.agent


def one(job):
    a_name, b_name, seed = job
    try:
        sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
        s0, s1 = sim.run_episode(_load(a_name), _load(b_name))

        from kaggle_environments import make
        env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": seed}, debug=False)
        env.run([_load(a_name), _load(b_name)])
        f = env.steps[-1]
        r0 = f[0].observation["farms"][0]["money"]
        r1 = f[1].observation["farms"][1]["money"]
        return (a_name, b_name, seed, s0, s1, r0, r1, None)
    except Exception:
        import traceback
        return (a_name, b_name, seed, 0, 0, 0, 0, traceback.format_exc()[-400:])


def main():
    jobs = []
    for i, a in enumerate(POOL):
        b = POOL[(i + 1) % len(POOL)]
        for seed in SEEDS:
            jobs.append((a, b, seed))

    t0 = time.time()
    with multiprocessing.get_context("forkserver").Pool(18) as pool:
        res = pool.map(one, jobs)

    n_exact = 0
    n_total = 0
    print(f"{'matchup':<62} {'seed':>7} {'sim':>20} {'real':>20}  verdict")
    for a, b, seed, s0, s1, r0, r1, err in res:
        label = f"{a[:28]} vs {b[:28]}"
        if err:
            print(f"{label:<62} {seed:>7}  ERROR {err[-120:]}")
            continue
        n_total += 1
        exact = (abs(s0 - r0) < 0.01 and abs(s1 - r1) < 0.01)
        if exact:
            n_exact += 1
        verdict = "EXACT" if exact else f"DIVERGE (d0={s0-r0:+,.0f} d1={s1-r1:+,.0f})"
        print(f"{label:<62} {seed:>7} {s0:>9,.0f}/{s1:>9,.0f} {r0:>9,.0f}/{r1:>9,.0f}  {verdict}")

    print()
    print(f"{n_exact}/{n_total} exact matches  ({time.time()-t0:.0f}s)")
    log = os.path.join(ROOT, "logs", "sim_fidelity.log")
    with open(log, "a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} AGENT-FIDELITY (live play, both sides real "
                f"agents): {n_exact}/{n_total} exact vs kaggle_environments\n")
    return 0 if n_exact == n_total else 1


if __name__ == "__main__":
    sys.exit(main())
