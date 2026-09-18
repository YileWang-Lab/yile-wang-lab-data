"""Re-derive the tape-selection rule by conditioning on the bucket that fires.

kawa ships five tapes and `_kawa_route_label` maps the town's shop draw onto one
of them through five hand-written buckets. HANDOFF section 11 reports the whole
mapping was searched and the default won -- but that search used the same small
samples that also called IV_STRUCT ambiguous, and IV_STRUCT turned out to be
real at +490.

The mapping has 5^5 = 3,125 settings, which is the wrong way to attack it.
Buckets are mutually exclusive, so the problem decomposes: force each tape,
record which bucket each game actually fell into, and pick the argmax tape
PER BUCKET. That is 5 measurements, not 3,125, and it gives the optimal map
directly.

The bucket cannot be precomputed from the seed. `_end_of_day` runs
`_spawn_weeds` for both players off the same RNG before `rng.choice(SHOPS)`,
so the shop draw depends on both boards' empty-tile counts (HANDOFF section 5's
"cross-opponent comparisons are confounded" warning). It is therefore observed
per game rather than derived.

Usage:
    /home/yilewang/kagg-env/bin/python -m planner.tape_sweep --seeds 120
"""
import argparse
import collections
import importlib.util
import json
import multiprocessing
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from planner.simulate import Simulator, _agent_caller  # noqa: E402
from route.bake import bake  # noqa: E402

LOG_DIR = os.path.join(ROOT, "logs", "planner")
VARIANT_DIR = os.path.join(ROOT, "agents", "tapes")
os.makedirs(VARIANT_DIR, exist_ok=True)

ROUTES = ["10c4s_3q", "8c6s_3q", "6c8s_3q",
          "6c12s_4q_first_yarn", "6c12s_4q_second_yarn"]
# what _kawa_route_label currently returns for buckets 0..4
DEFAULT_MAP = ["6c12s_4q_first_yarn", "6c12s_4q_second_yarn", "6c8s_3q",
               "10c4s_3q", "8c6s_3q"]

LIVE = {"_PREEMPT_MIN_FUTURE_QUANTITY": 0, "_PREEMPT_MAX_BATCH": 30,
        "INTERVENE": 1, "IV_DUMP_FRAC": 0.7, "IV_LEAD": 3, "IV_FERT": 1,
        "IV_STRUCT": 1, "IV_MIN_PRICE": 0.20}

MILK_SHOPS = {"PIZZA_SHOP", "ICE_CREAM_SHOP", "SMOOTHIE_SHOP"}

OPPONENTS = [
    "kaggriculture-multi-route-farming-agent",
    "v111-8c4s-economic-core-premium-lead",
    "kaggriculture-frontier-the-soil-remembers-rain",
    "kaggriculture-3000-socre",
    "kaggriculture-breaking-the-tie-2883-score",
    "kaggriculture-rank-your-agent",
]

_n = [0]


def bucket_of(shops):
    """Mirrors _kawa_route_label's bucket test order exactly."""
    if shops[:1] == ["YARN_STORE"]:
        return 0
    if "YARN_STORE" in shops[:2]:
        return 1
    if "YARN_STORE" in shops[:3]:
        return 2
    if MILK_SHOPS.intersection(shops[:3]):
        return 3
    return 4


def _load(path):
    _n[0] += 1
    spec = importlib.util.spec_from_file_location(f"tp_{os.getpid()}_{_n[0]}", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return getattr(m, "_submission_entry", None) or m.agent


def play(job):
    label, path, opp_name, seed, seat = job
    try:
        me = _load(path)
        opp = _load(os.path.join(ROOT, "opponents", f"{opp_name}.py"))
        pair = [me, opp] if seat == 0 else [opp, me]
        sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
        c0, c1 = _agent_caller(pair[0]), _agent_caller(pair[1])
        limit = 719
        while sim.step < limit:
            a0 = c0(sim.observation_for(0), sim.cfg)
            a1 = c1(sim.observation_for(1), sim.cfg)
            sim.step_actions(a0, a1)
        shops = list(sim.town["unlocked_shops"])
        us, them = ((sim.farms[0]["money"], sim.farms[1]["money"]) if seat == 0
                    else (sim.farms[1]["money"], sim.farms[0]["money"]))
        return (label, opp_name, seed, seat, us - them, bucket_of(shops), None)
    except Exception:
        import traceback
        return (label, opp_name, seed, seat, 0.0, -1, traceback.format_exc()[-250:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=120)
    ap.add_argument("--workers", type=int, default=24)
    args = ap.parse_args()

    paths = {"default": os.path.join(VARIANT_DIR, "tape_default.py")}
    bake(LIVE, out=paths["default"], note="live selection rule")
    for r in ROUTES:
        p = os.path.join(VARIANT_DIR, f"tape_{r}.py")
        bake({**LIVE, "FORCE_ROUTE": r}, out=p, note=f"forced tape {r}")
        paths[r] = p

    import random
    rng = random.Random(31337)
    seeds = [rng.randrange(10**6, 2**31 - 1) for _ in range(args.seeds)]

    jobs = [(lbl, paths[lbl], opp, s, seat)
            for lbl in paths for opp in OPPONENTS for s in seeds for seat in (0, 1)]
    print(f"{len(paths)} tapes x {len(OPPONENTS)} opponents x {len(seeds)} seeds x 2 "
          f"= {len(jobs):,} games")

    t0 = time.time()
    with multiprocessing.get_context("forkserver").Pool(args.workers) as pool:
        res = pool.map(play, jobs, chunksize=4)
    print(f"elapsed {time.time()-t0:.0f}s")
    errs = [r for r in res if r[6]]
    if errs:
        print(f"{len(errs)} errors; first: {errs[0][6][-250:]}")

    paired = {}
    buckets = {}
    for lbl, opp, seed, seat, m, b, err in res:
        if err:
            continue
        paired.setdefault((lbl, opp, seed), []).append(m)
        buckets[(opp, seed)] = b

    per = {}
    for (lbl, opp, seed), ms in paired.items():
        if len(ms) == 2:
            per.setdefault(lbl, {})[(opp, seed)] = sum(ms)

    bcount = collections.Counter(buckets.values())
    print("\nbucket frequency across the seed set:")
    for b in sorted(bcount):
        print(f"  bucket {b}: {bcount[b]:>5} games  ({100*bcount[b]/max(sum(bcount.values()),1):.1f}%)"
              f"   default tape -> {DEFAULT_MAP[b] if 0 <= b < 5 else '?'}")

    print(f"\n{'tape':<24} {'overall':>12} " + " ".join(f"{'b'+str(b):>12}" for b in range(5)))
    base = per.get("default", {})
    for lbl in ["default"] + ROUTES:
        d = per.get(lbl, {})
        if not d:
            continue
        overall = statistics.mean(d.values())
        cells = []
        for b in range(5):
            vals = [v for k, v in d.items() if buckets.get(k) == b]
            cells.append(f"{statistics.mean(vals):>12,.0f}" if vals else f"{'-':>12}")
        print(f"{lbl:<24} {overall:>12,.0f} " + " ".join(cells))

    print(f"\n{'ARGMAX per bucket':<24}")
    best_map = []
    for b in range(5):
        scores = []
        for r in ROUTES:
            d = per.get(r, {})
            vals = [v for k, v in d.items() if buckets.get(k) == b]
            if vals:
                scores.append((statistics.mean(vals), len(vals), r))
        if not scores:
            best_map.append(DEFAULT_MAP[b])
            print(f"  bucket {b}: no data, keeping default {DEFAULT_MAP[b]}")
            continue
        scores.sort(reverse=True)
        top, n_top, r_top = scores[0]
        cur = [s for s in scores if s[2] == DEFAULT_MAP[b]]
        cur_v = cur[0][0] if cur else float("nan")
        best_map.append(r_top)
        flag = "" if r_top == DEFAULT_MAP[b] else "   <-- DIFFERENT from default"
        print(f"  bucket {b} (n={n_top:>4}): best={r_top:<22} {top:>10,.0f}   "
              f"default={DEFAULT_MAP[b]:<22} {cur_v:>10,.0f}{flag}")

    print(f"\nproposed map: {best_map}")
    print(f"default  map: {DEFAULT_MAP}")
    if best_map != DEFAULT_MAP:
        print("\nNOTE: per-bucket argmax is selected on the SAME data it is scored on, so the")
        print("implied gain is optimistically biased. It must be re-measured as a single")
        print("TAPE_MAP variant on fresh seeds before it can be believed, let alone shipped.")

    ts = time.strftime("%Y%m%d_%H%M%S")
    json.dump({"best_map": best_map, "default_map": DEFAULT_MAP,
               "bucket_counts": {str(k): v for k, v in bcount.items()}},
              open(os.path.join(LOG_DIR, f"tape_sweep_{ts}.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
