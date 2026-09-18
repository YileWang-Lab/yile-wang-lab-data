"""How much deviation from the route can the tape absorb?

The claim under test: the tree agent fails only because it disagrees with the
table, so a MORE accurate tree would work. That is a statement about the shape
of the fidelity-performance curve, and it is measurable.

Blend the two at a controlled rate p -- take the tree's unit orders with
probability p, the table's otherwise -- and sweep p. p=0 is the table exactly
and p=1 is the tree alone, so both ends are controls.

If performance falls gracefully, accuracy is the binding constraint and a better
tree is worth building. If it collapses at a few percent, no achievable accuracy
helps and the representation is the problem, not the fit.
"""
import multiprocessing as mp
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _HERE]
sys.path.insert(0, ROOT)

OPPS = ["v111-8c4s-economic-core-premium-lead", "kaggriculture-3000-socre",
        "kaggriculture-rank-your-agent"]
_n = [0]


def play(job):
    p_dev, opp, seed, seat = job
    try:
        import importlib.util
        from planner.simulate import Simulator
        from dynamic.tape.pipeline import Pipeline
        from dynamic.tree.agent_tree import load
        pipe = Pipeline()
        if p_dev > 0:
            pipe.blend_tree(load(), p_dev, seed=seed)
        _n[0] += 1
        spec = importlib.util.spec_from_file_location(
            f"fo_{os.getpid()}_{_n[0]}",
            os.path.join(ROOT, "opponents", opp + ".py"))
        om = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(om)
        other = getattr(om, "_submission_entry", None) or om.agent
        pair = [pipe.agent, other] if seat == 0 else [other, pipe.agent]
        sim = Simulator.new_episode(configuration={"episodeSteps": 720},
                                    seed=seed)
        m0, m1 = sim.run_episode(pair[0], pair[1])
        us, them = (m0, m1) if seat == 0 else (m1, m0)
        return (p_dev, opp, seed, us - them, None)
    except Exception:
        import traceback
        return (p_dev, opp, seed, 0.0, traceback.format_exc()[-200:])


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 16
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    RATES = [0.0, 0.01, 0.02, 0.05, 0.10, 0.25, 0.50, 1.0]
    import random
    rng = random.Random(31415)
    seeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(n)]
    jobs = [(r, o, s, st) for r in RATES for o in OPPS
            for s in seeds for st in (0, 1)]
    print(f"{len(jobs):,} games, deviation rates {RATES}", flush=True)
    with mp.get_context("forkserver").Pool(workers) as pool:
        res = pool.map(play, jobs, chunksize=2)
    errs = [e for *_x, e in res if e]
    if errs:
        print(f"{len(errs)} errors; first:\n{errs[0]}")
    per = {}
    for r, opp, seed, m, e in res:
        if e:
            continue
        per.setdefault((r, opp, seed), []).append(m)
    paired = {}
    for (r, opp, seed), v in per.items():
        if len(v) == 2:
            paired.setdefault(r, []).append(sum(v))
    print()
    print(f"{'deviation':>10}{'paired margin':>15}{'se':>8}{'win rate':>10}   "
          f"(0 = the table, 1 = the tree)")
    base = statistics.mean(paired.get(0.0) or [0])
    for r in RATES:
        v = paired.get(r)
        if not v:
            continue
        se = statistics.pstdev(v) / len(v) ** 0.5 if len(v) > 1 else 0.0
        w = sum(1 for x in v if x > 0)
        bar = "#" * max(0, min(30, int(30 * (statistics.mean(v) - min(-320000, base))
                                       / max(1.0, base + 320000))))
        print(f"{100 * r:>9.0f}%{statistics.mean(v):>+15,.0f}{se:>8,.0f}"
              f"{100.0 * w / len(v):>9.0f}%   {bar}")


if __name__ == "__main__":
    main()
