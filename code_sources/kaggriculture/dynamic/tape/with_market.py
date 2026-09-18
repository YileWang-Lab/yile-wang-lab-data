"""The rebuilt pipeline plus v3's market overlay, scored against the pool.

v3 = the route table and its eleven guards, PLUS the market-intervention overlay
we wrote (`pbt/intervene.py`). The overlay is a pure wrapper -- it edits market
orders and never touches a tile -- so it composes onto the pipeline exactly as
it composed onto the original file.

Three agents are measured, and the middle one is the control that makes the
other two readable:

    pipeline            the rebuild alone; must equal kawa, since verify()
                        already showed the actions are bit-identical
    pipeline + market   the reconstruction of v3
    submission/main.py  the shipped v3 itself

If the rebuild is faithful, rows one and three bracket row two and the shipped
file and the reconstruction land on the same number. Any gap is a defect in the
composition, not in the pipeline, because the actions were already verified.
"""
import json
import multiprocessing as mp
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _HERE]
sys.path.insert(0, ROOT)

POOL = ["kaggriculture-multi-route-farming-agent",
        "v111-8c4s-economic-core-premium-lead",
        "kaggriculture-frontier-the-soil-remembers-rain",
        "kaggriculture-3000-socre",
        "kaggriculture-rank-your-agent",
        "strong-barnyard-economist"]
_n = [0]


def _load(path):
    import importlib.util
    _n[0] += 1
    spec = importlib.util.spec_from_file_location(
        f"wm_{os.getpid()}_{_n[0]}", os.path.join(ROOT, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def make_market_pipeline():
    """Pipeline + the v3 market overlay, wired through the overlay's own source.

    `intervene_src` emits a module that expects a module-level `agent` to wrap,
    which is how route/bake.py appends it after the tape source. Building it in
    a scratch namespace keeps that contract without writing a file.
    """
    from dynamic.tape.pipeline import Pipeline
    from pbt.intervene import PREMIUM_FERT, intervene_src

    p = Pipeline()
    ns = {"agent": p.agent}
    # the shipped configuration, verbatim from HANDOFF section 0
    src = intervene_src(enabled=1, dump_frac=0.7, lead=3, struct=1,
                        min_price=0.20, items=PREMIUM_FERT)
    exec(compile(src, "<intervene>", "exec"), ns)
    return ns["agent"]


def _tree_pipeline(with_market):
    """The 11 guards, but the route TABLE replaced by the decision tree."""
    from dynamic.tape.pipeline import Pipeline
    from dynamic.tree.agent_tree import load
    p = Pipeline().use_tree(load())
    if not with_market:
        return p.agent
    from pbt.intervene import PREMIUM_FERT, intervene_src
    ns = {"agent": p.agent}
    exec(compile(intervene_src(enabled=1, dump_frac=0.7, lead=3, struct=1,
                               min_price=0.20, items=PREMIUM_FERT),
                 "<intervene>", "exec"), ns)
    return ns["agent"]


def build(kind):
    if kind == "pipeline":
        from dynamic.tape.pipeline import Pipeline
        return Pipeline().agent
    if kind == "pipeline+market":
        return make_market_pipeline()
    if kind == "tree":
        return _tree_pipeline(False)
    if kind == "tree+market":
        return _tree_pipeline(True)
    m = _load(kind)
    return getattr(m, "_submission_entry", None) or m.agent


def play(job):
    label, kind, opp, seed, seat = job
    try:
        from planner.simulate import Simulator
        me = build(kind)
        om = _load(os.path.join("opponents", opp + ".py"))
        op = getattr(om, "_submission_entry", None) or om.agent
        pair = [me, op] if seat == 0 else [op, me]
        sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
        m0, m1 = sim.run_episode(pair[0], pair[1])
        us, them = (m0, m1) if seat == 0 else (m1, m0)
        return (label, opp, seed, seat, us - them, None)
    except Exception:
        import traceback
        return (label, opp, seed, seat, 0.0, traceback.format_exc()[-220:])


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 32
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    cands = [("TREE + 11 guards", "tree"),
             ("TREE + guards + market", "tree+market"),
             ("table + guards + market (v3)", "pipeline+market"),
             ("SHIPPED v3", "submission/main.py")]
    import random
    rng = random.Random(20260821)
    seeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(n)]
    jobs = [(l, k, o, s, st) for l, k in cands for o in POOL
            for s in seeds for st in (0, 1)]
    print(f"{len(jobs):,} games ({len(cands)} agents x {len(POOL)} opponents x "
          f"{n} seeds x 2 seats)", flush=True)
    with mp.get_context("forkserver").Pool(workers) as pool:
        res = pool.map(play, jobs, chunksize=2)
    errs = [e for *_x, e in res if e]
    if errs:
        print(f"{len(errs)} errors; first:\n{errs[0]}")

    per = {}
    for lbl, opp, seed, seat, m, e in res:
        if e:
            continue
        per.setdefault((lbl, opp, seed), []).append(m)
    paired = {}
    for (lbl, opp, seed), v in per.items():
        if len(v) == 2:
            paired.setdefault(lbl, {})[(opp, seed)] = sum(v)

    print()
    print(f"{'agent':<26}{'paired margin':>15}{'se':>8}{'win rate':>11}{'W-L':>10}")
    for lbl, _k in cands:
        d = paired.get(lbl)
        if not d:
            continue
        v = list(d.values())
        se = statistics.pstdev(v) / len(v) ** 0.5 if len(v) > 1 else 0.0
        w = sum(1 for x in v if x > 0)
        l = sum(1 for x in v if x < 0)
        print(f"{lbl:<26}{statistics.mean(v):>+15,.0f}{se:>8,.0f}"
              f"{100.0 * w / max(1, w + l):>10.1f}%{w:>6}-{l}")

    print()
    print(f"{'agent':<26}" + "".join(f"{o[:11]:>13}" for o in POOL))
    for lbl, _k in cands:
        d = paired.get(lbl)
        if not d:
            continue
        row = ""
        for o in POOL:
            vals = [x for (oo, _s), x in d.items() if oo == o]
            row += f"{statistics.mean(vals):>+13,.0f}" if vals else f"{'-':>13}"
        print(f"{lbl:<26}{row}")


if __name__ == "__main__":
    main()
