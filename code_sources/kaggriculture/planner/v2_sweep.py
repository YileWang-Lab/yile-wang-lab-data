"""Test the MIN_CREW bootstrap fix on planner/route_v2.py against the pool.

Deliberately a separate file from route/agent.py: HANDOFF's operational rule is
never to edit an agent file while a search may be re-execing it per episode.

MIN_CREW=0 must reproduce the unmodified agent exactly -- that identity is the
first thing checked, because a "gain" that comes from having accidentally
changed the baseline is worthless.

Usage:
    /home/yilewang/kagg-env/bin/python -m planner.v2_sweep --seeds 40
"""
import argparse
import importlib.util
import json
import multiprocessing
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from planner.simulate import Simulator  # noqa: E402
from route.search import to_params  # noqa: E402

V2 = os.path.join(ROOT, "planner", "route_v2.py")
V1 = os.path.join(ROOT, "route", "agent.py")
LOG_DIR = os.path.join(ROOT, "logs", "planner")
GENOME = os.path.join(ROOT, "planner", "checkpoints", "best_genome1.json")

REF_POOL = [
    "kaggriculture-multi-route-farming-agent",
    "v111-8c4s-economic-core-premium-lead",
    "kaggriculture-frontier-the-soil-remembers-rain",
    "kaggriculture-3000-socre",
    "kaggriculture-breaking-the-tie-2883-score",
    "kaggriculture-rank-your-agent",
    "15-16-strict-future-v25-meta-reset",
    "strong-barnyard-economist",
    "kaggriculture-pure-architecture-2600-elo-v3",
]

_n = [0]


def _load_route(path, params):
    _n[0] += 1
    spec = importlib.util.spec_from_file_location(f"v2_{os.getpid()}_{_n[0]}", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.configure(params)
    return m.agent


def _load_ref(name):
    _n[0] += 1
    spec = importlib.util.spec_from_file_location(
        f"v2ref_{os.getpid()}_{_n[0]}", os.path.join(ROOT, "opponents", f"{name}.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.agent


def play(job):
    label, path, params, opp, seed, seat = job
    try:
        me = _load_route(path, params)
        op = _load_ref(opp)
        pair = [me, op] if seat == 0 else [op, me]
        sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
        m0, m1 = sim.run_episode(pair[0], pair[1])
        us, them = (m0, m1) if seat == 0 else (m1, m0)
        return (label, opp, seed, seat, us - them, None)
    except Exception:
        import traceback
        return (label, opp, seed, seat, 0.0, traceback.format_exc()[-250:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=40)
    ap.add_argument("--workers", type=int, default=24)
    args = ap.parse_args()

    base = json.load(open(GENOME))["genome"]
    bp = to_params(dict(base))

    variants = [("v1_baseline", V1, dict(bp))]
    variants.append(("v2_mincrew0", V2, {**bp, "MIN_CREW": 0}))
    for mc in (6, 8, 10, 12, 14):
        variants.append((f"v2_crew{mc}", V2, {**bp, "MIN_CREW": mc, "MIN_CREW_UNTIL_DAY": 14}))
    for d in (8, 20, 29):
        variants.append((f"v2_crew10_d{d}", V2, {**bp, "MIN_CREW": 10, "MIN_CREW_UNTIL_DAY": d}))

    import random
    rng = random.Random(777)
    seeds = [rng.randrange(10**6, 2**31 - 1) for _ in range(args.seeds)]

    jobs = [(lbl, path, params, opp, s, seat)
            for lbl, path, params in variants
            for opp in REF_POOL for s in seeds for seat in (0, 1)]
    print(f"{len(variants)} variants x {len(REF_POOL)} opponents x {len(seeds)} seeds x 2 "
          f"= {len(jobs):,} games")

    t0 = time.time()
    with multiprocessing.get_context("forkserver").Pool(args.workers) as pool:
        res = pool.map(play, jobs, chunksize=4)
    print(f"elapsed {time.time()-t0:.0f}s")

    errs = [r for r in res if r[5]]
    if errs:
        print(f"{len(errs)} errors; first: {errs[0][5][-250:]}")

    paired = {}
    for lbl, opp, seed, seat, m, err in res:
        if not err:
            paired.setdefault((lbl, opp, seed), []).append(m)
    per = {}
    for (lbl, opp, seed), ms in paired.items():
        if len(ms) == 2:
            per.setdefault(lbl, {})[(opp, seed)] = sum(ms)

    b = per.get("v1_baseline", {})
    print()
    print(f"{'variant':<20} {'n':>5} {'paired margin':>15} {'vs v1':>10} {'+/-se':>8} "
          f"{'t':>6} {'wins':>7}")
    rows = []
    for lbl, _, _ in variants:
        d = per.get(lbl, {})
        if not d:
            continue
        ms = list(d.values())
        diffs = [d[k] - b[k] for k in d if k in b]
        dm = statistics.mean(diffs) if diffs else 0.0
        dse = (statistics.pstdev(diffs) / (len(diffs) ** 0.5)) if len(diffs) > 1 else 0.0
        rows.append((lbl, len(ms), statistics.mean(ms), dm, dse,
                     dm / dse if dse else 0.0, sum(1 for m in ms if m > 0) / len(ms)))
    rows.sort(key=lambda r: -r[3])
    for lbl, n, mm, dm, dse, t, wr in rows:
        print(f"{lbl:<20} {n:>5} {mm:>15,.0f} {dm:>+10,.0f} {dse:>8,.0f} {t:>6.1f} {wr:>7.1%}")

    id_check = [r for r in rows if r[0] == "v2_mincrew0"]
    if id_check:
        print()
        print(f"IDENTITY CHECK  v2 with MIN_CREW=0 vs unmodified v1: "
              f"{id_check[0][3]:+,.0f} (must be ~0 for the comparison to mean anything)")

    ts = time.strftime("%Y%m%d_%H%M%S")
    with open(os.path.join(LOG_DIR, "planner_progress.log"), "a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} v2_sweep MIN_CREW best={rows[0][0]} "
                f"delta={rows[0][3]:+.0f} t={rows[0][5]:.1f}\n")


if __name__ == "__main__":
    main()
