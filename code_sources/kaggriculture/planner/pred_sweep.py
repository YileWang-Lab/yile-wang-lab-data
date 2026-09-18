"""Weighted vs median cadence estimator for the dump trigger.

The median gap is robust but slow to react when the opponent shifts strategy
mid-season. Modes: 0 median (shipped), 1 linearly weighted toward recent gaps,
2 most recent gap only.

Prior from what is already measured: IV_LEAD 2/3/4 all differ little with 3
best, which says timing PRECISION is not the binding constraint -- so this is
expected to be small. It is worth running anyway because the front-run audit
showed position is exactly what the layer buys (we clear ahead on 94-99% of
firings), so the predictor is at least pointed at the right quantity.
"""
import importlib.util, multiprocessing, os, random, statistics, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from planner.simulate import Simulator  # noqa: E402
from route.bake import bake  # noqa: E402

LIVE = {"_PREEMPT_MIN_FUTURE_QUANTITY": 0, "_PREEMPT_MAX_BATCH": 30, "INTERVENE": 1,
        "IV_DUMP_FRAC": 0.7, "IV_LEAD": 3, "IV_FERT": 1, "IV_STRUCT": 1,
        "IV_MIN_PRICE": 0.20}
DEF = ["6c12s_4q_first_yarn", "6c12s_4q_second_yarn", "6c8s_3q", "10c4s_3q", "8c6s_3q"]
B0 = {**LIVE, "TAPE_MAP": ["6c12s_4q_second_yarn"] + DEF[1:]}
POOL = ["kaggriculture-multi-route-farming-agent",
        "v111-8c4s-economic-core-premium-lead",
        "kaggriculture-frontier-the-soil-remembers-rain",
        "kaggriculture-3000-socre",
        "kaggriculture-breaking-the-tie-2883-score",
        "kaggriculture-rank-your-agent",
        "15-16-strict-future-v25-meta-reset",
        "strong-barnyard-economist",
        "kaggriculture-pure-architecture-2600-elo-v3"]
V = [("median (live)", dict(B0)),
     ("weighted", {**B0, "IV_PRED_MODE": 1}),
     ("recent_only", {**B0, "IV_PRED_MODE": 2}),
     ("weighted_lead2", {**B0, "IV_PRED_MODE": 1, "IV_LEAD": 2}),
     ("weighted_lead4", {**B0, "IV_PRED_MODE": 1, "IV_LEAD": 4}),
     ("recent_lead2", {**B0, "IV_PRED_MODE": 2, "IV_LEAD": 2})]
_n = [0]


def _load(p):
    _n[0] += 1
    s = importlib.util.spec_from_file_location(f"ps_{os.getpid()}_{_n[0]}", p)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return getattr(m, "_submission_entry", None) or m.agent


def play(job):
    lbl, path, opp, seed, seat = job
    try:
        me = _load(path); op = _load(os.path.join(ROOT, "opponents", f"{opp}.py"))
        pair = [me, op] if seat == 0 else [op, me]
        sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
        m0, m1 = sim.run_episode(pair[0], pair[1])
        us, them = (m0, m1) if seat == 0 else (m1, m0)
        return (lbl, opp, seed, seat, us - them, None)
    except Exception:
        import traceback
        return (lbl, opp, seed, seat, 0.0, traceback.format_exc()[-200:])


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 90
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    paths = {}
    for lbl, p in V:
        q = os.path.join(ROOT, "agents", "pred", f"{lbl.replace(' ','_').replace('(','').replace(')','')}.py")
        os.makedirs(os.path.dirname(q), exist_ok=True)
        bake(p, out=q, note=lbl); paths[lbl] = q
    rng = random.Random(161803)
    seeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(n)]
    jobs = [(l, paths[l], o, s, seat) for l, _ in V for o in POOL
            for s in seeds for seat in (0, 1)]
    print(f"{len(V)} variants x {len(jobs):,} games", flush=True)
    t0 = time.time()
    with multiprocessing.get_context("forkserver").Pool(workers) as pool:
        res = pool.map(play, jobs, chunksize=4)
    print(f"{time.time()-t0:.0f}s", flush=True)
    pr = {}
    for l, o, s, seat, m, e in res:
        if not e:
            pr.setdefault((l, o, s), []).append(m)
    per = {}
    for k, v in pr.items():
        if len(v) == 2:
            per.setdefault(k[0], {})[k[1:]] = sum(v)
    b = per.get("median (live)", {})
    print()
    print(f"{'variant':<18} {'paired margin':>14} {'vs live':>10} {'+/-se':>7} {'t':>6} {'win%':>7}")
    rows = []
    for lbl, _ in V:
        d = per.get(lbl, {})
        if not d: continue
        diffs = [d[k] - b[k] for k in d if k in b]
        dm = statistics.mean(diffs) if diffs else 0.0
        dse = (statistics.pstdev(diffs) / len(diffs) ** 0.5) if len(diffs) > 1 else 0.0
        rows.append((lbl, statistics.mean(d.values()), dm, dse, dm / dse if dse else 0.0,
                     sum(1 for v in d.values() if v > 0) / len(d)))
    rows.sort(key=lambda r: -r[2])
    for lbl, mm, dm, dse, t, wr in rows:
        print(f"{lbl:<18} {mm:>14,.0f} {dm:>+10,.0f} {dse:>7,.0f} {t:>6.1f} {wr:>6.1%}")


if __name__ == "__main__":
    main()
