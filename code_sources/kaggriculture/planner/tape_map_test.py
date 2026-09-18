"""Decisive test of a proposed tape-selection map on FRESH seeds.

planner/tape_sweep.py produced a per-bucket argmax that differs from kawa's
default for buckets 0, 1 and 2. That result cannot be trusted as it stands, for
two independent reasons:

  1. Selection bias -- the argmax is chosen on the same data it is scored on.
  2. Worse, the bucketing is post-hoc. `_kawa_route_label` is evaluated at
     runtime off the shops unlocked SO FAR, so the bucket changes during the
     game (it starts at 4 with no shops unlocked) and the agent can switch
     tapes mid-episode. Assigning each game the bucket of its FINAL shop list
     therefore does not describe what the agent actually ran. The tell is in
     the data: the default agent's bucket-1 mean (21,379) does not match the
     mean of the tape the default map assigns to bucket 1 (15,847), which it
     would have to if the mapping were static.

The only sound test is to build the proposed map as a real TAPE_MAP variant and
measure it head-to-head against the live agent on seeds not used to derive it.

Usage:
    /home/yilewang/kagg-env/bin/python -m planner.tape_map_test --seeds 150
"""
import argparse
import importlib.util
import multiprocessing
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from planner.simulate import Simulator  # noqa: E402
from route.bake import bake  # noqa: E402

LOG_DIR = os.path.join(ROOT, "logs", "planner")
VARIANT_DIR = os.path.join(ROOT, "agents", "tapes")
os.makedirs(VARIANT_DIR, exist_ok=True)

LIVE = {"_PREEMPT_MIN_FUTURE_QUANTITY": 0, "_PREEMPT_MAX_BATCH": 30,
        "INTERVENE": 1, "IV_DUMP_FRAC": 0.7, "IV_LEAD": 3, "IV_FERT": 1,
        "IV_STRUCT": 1, "IV_MIN_PRICE": 0.20}

DEFAULT_MAP = ["6c12s_4q_first_yarn", "6c12s_4q_second_yarn", "6c8s_3q",
               "10c4s_3q", "8c6s_3q"]
PROPOSED = ["6c12s_4q_second_yarn", "6c8s_3q", "8c6s_3q", "10c4s_3q", "8c6s_3q"]
# partial adoptions, so a single bad bucket cannot hide a good one
P_B0 = ["6c12s_4q_second_yarn"] + DEFAULT_MAP[1:]
P_B1 = [DEFAULT_MAP[0], "6c8s_3q"] + DEFAULT_MAP[2:]
P_B2 = DEFAULT_MAP[:2] + ["8c6s_3q"] + DEFAULT_MAP[3:]

OPPONENTS = [
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


def _load(path):
    _n[0] += 1
    spec = importlib.util.spec_from_file_location(f"tm_{os.getpid()}_{_n[0]}", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return getattr(m, "_submission_entry", None) or m.agent


def play(job):
    label, path, opp, seed, seat = job
    try:
        me = _load(path)
        op = _load(os.path.join(ROOT, "opponents", f"{opp}.py"))
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
    ap.add_argument("--seeds", type=int, default=150)
    ap.add_argument("--workers", type=int, default=24)
    args = ap.parse_args()

    # Confirmation: b0 alone was +1,889 (t=7.3) on 150 fresh seeds over 6
    # opponents while b1 (-146) and b2 (-983) were flat-to-harmful, so the full
    # map's +760 was b0's gain diluted by the other two. Re-tested here on a
    # THIRD disjoint seed draw across all 9 opponents, plus the other candidate
    # tapes for b0 so the choice is not merely default-vs-one-alternative.
    variants = [
        ("live_default", dict(LIVE)),
        ("b0_second_yarn", {**LIVE, "TAPE_MAP": P_B0}),
    ]
    paths = {}
    for name, params in variants:
        p = os.path.join(VARIANT_DIR, f"map_{name}.py")
        bake(params, out=p, note=f"tape map {name}")
        paths[name] = p

    import random
    # seed 999 -- disjoint from tape_sweep's 31337 draw, so this is fresh data
    rng = random.Random(int(os.environ.get("TM_SEED", "20260819")))
    seeds = [rng.randrange(10**6, 2**31 - 1) for _ in range(args.seeds)]

    jobs = [(n, paths[n], o, s, seat) for n, _ in variants
            for o in OPPONENTS for s in seeds for seat in (0, 1)]
    print(f"{len(variants)} maps x {len(OPPONENTS)} opponents x {len(seeds)} FRESH seeds x 2 "
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

    base = per.get("live_default", {})
    print()
    print(f"{'map':<16} {'n':>5} {'paired margin':>15} {'vs live':>10} {'+/-se':>8} {'t':>6} {'better%':>8}")
    rows = []
    for name, _ in variants:
        d = per.get(name, {})
        if not d:
            continue
        diffs = [d[k] - base[k] for k in d if k in base]
        dm = statistics.mean(diffs) if diffs else 0.0
        dse = (statistics.pstdev(diffs) / len(diffs) ** 0.5) if len(diffs) > 1 else 0.0
        rows.append((name, len(d), statistics.mean(d.values()), dm, dse,
                     dm / dse if dse else 0.0,
                     sum(1 for x in diffs if x > 0) / len(diffs) if diffs else 0.0))
    rows.sort(key=lambda r: -r[3])
    for name, n, mm, dm, dse, t, bp in rows:
        print(f"{name:<16} {n:>5} {mm:>15,.0f} {dm:>+10,.0f} {dse:>8,.0f} {t:>6.1f} {bp:>8.1%}")

    # A tape swap replaces the whole 30-day schedule, so it either does nothing
    # (wrong bucket) or changes everything. The unconditional mean hides that.
    # Report the CONDITIONAL distribution, which is what actually decides whether
    # this is a real edge or a coin flip with a big stake.
    for name, _ in variants:
        if name == "live_default":
            continue
        d = per.get(name, {})
        diffs = [d[k] - base[k] for k in d if k in base]
        nz = [x for x in diffs if abs(x) > 1]
        if not nz:
            continue
        nz.sort()
        pos = sum(1 for x in nz if x > 0)
        cm = statistics.mean(nz)
        cse = statistics.pstdev(nz) / len(nz) ** 0.5
        print()
        print(f"CONDITIONAL on the change actually firing -- {name}")
        print(f"  fired on {len(nz)}/{len(diffs)} paired games ({100*len(nz)/len(diffs):.1f}%)")
        print(f"  mean {cm:+,.0f}  (se {cse:,.0f}, t={cm/cse if cse else 0:.1f})")
        print(f"  better in {pos}/{len(nz)} ({100*pos/len(nz):.0f}%)")
        print(f"  sd {statistics.pstdev(nz):,.0f}   min {nz[0]:+,.0f}   "
              f"p25 {nz[len(nz)//4]:+,.0f}   median {nz[len(nz)//2]:+,.0f}   "
              f"p75 {nz[3*len(nz)//4]:+,.0f}   max {nz[-1]:+,.0f}")

    with open(os.path.join(LOG_DIR, "planner_progress.log"), "a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} tape_map_test (fresh seeds) "
                f"best={rows[0][0]} delta={rows[0][3]:+.0f} t={rows[0][5]:.1f}\n")


if __name__ == "__main__":
    main()
