"""Coordinate descent over the genome, scored by paired win rate.

The GA is doing badly here for a reason that is now measured rather than
guessed: a genome-level comparison has sd ~32,500 per paired game, so scoring 48
mutants on 24 paired games each means selection is driven by roughly +-10pp of
noise while real effects are a few points. Six generations produced nothing --
every winner confirmed negative, and twice the reference won its own generation.

Coordinate descent does not have that problem. It moves ONE parameter at a time
and gives every variant the full sample, so each comparison is the same kind of
A/B that produced every gain this session (+2,865 allocator, +4,208 veto, +2,049
late wheat). It cannot find interactions the way a GA can in principle, but a GA
that cannot resolve its own fitness finds nothing at all.

Scoring is the paired win rate against the reference on shared seeds, which
`dynamic/metric_test.py` measured 29-45% more sensitive than paired margin on
the noisy comparisons, and exactly zero on an exact null. Both numbers are
reported so a disagreement between them is visible rather than hidden.

Run: python dynamic/coord_descent.py [seeds] [workers] [batch]
"""
import json
import multiprocessing
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _HERE]
sys.path.insert(0, ROOT)

from route.search import to_params  # noqa: E402

AGENT = os.path.join(ROOT, "dynamic", "agent4.py")
POOL = ["kaggriculture-multi-route-farming-agent",
        "v111-8c4s-economic-core-premium-lead",
        "kaggriculture-frontier-the-soil-remembers-rain",
        "kaggriculture-3000-socre",
        "kaggriculture-rank-your-agent",
        "strong-barnyard-economist"]
_n = [0]

# One axis per line: the values to try around the current setting. Chosen to
# straddle it, so a null result is visible as a symmetric pair rather than a
# one-sided push.
AXES = {
    "ALLOC_LABOR":              [8.0, 10.0, 16.0, 20.0],
    "ENPV_LABOR":               [5.0, 6.5, 10.0, 12.0],
    "ENPV_DRY_DAYS":            [1.0, 3.0, 4.0],
    "HIRE_BUDGET_FRACTION":     [0.35, 0.45, 0.62, 0.75],
    "SPEND_RESERVE":            [150.0, 240.0, 480.0, 700.0],
    "SURVIVAL_RESERVE_FRACTION": [0.10, 0.14, 0.26, 0.35],
    "WHEAT_FEED_BUFFER_MULT":   [0.7, 0.85, 1.3, 1.8],
    "LAND_BUY_CASH_MULTIPLE":   [1.15, 1.4, 2.0, 2.4],
    "ANIMAL_BUY_CAP_PER_TURN":  [1, 3, 4],
    "SEED_BATCH_PER_TURN":      [4, 5, 10, 14],
    "MAX_HANDS":                [14, 17, 23, 26],
    "SHED_PANIC_FRACTION":      [0.12, 0.16, 0.28, 0.40],
    "RESERVE_PRICE_SCALE":      [0.9, 1.1, 1.5, 1.9],
    "COLLECT_FERT_VALUE":       [150.0, 240.0, 420.0, 600.0],
    "TERMINAL_STEP":            [660, 675, 697, 705],
    "PLANT_MISS_TOLERANCE":     [0, 2, 6, 10],
    "IDLE_MAX_TRAVEL":          [10, 14, 22, 26],
    "TC_COW":                   [3, 4, 6, 7],
    "TC_SHEEP":                 [5, 6, 8, 9],
    "TC_GOOSE":                 [0, 1, 3, 4],
    "TC_MELON":                 [6, 7, 9, 10],
    "TC_STRAWBERRY":            [17, 19, 23, 25],
    "TC_WHEAT":                 [4, 5, 8, 10],
    "BUY_ANIMALS_FIRST":        [0],
    "IDLE_TOPUP":               [0],
    "FRONT_RUN":                [0],
    "WHEAT_SELL_SURPLUS":       [0],
}


def _load(path, genome=None):
    import importlib.util
    _n[0] += 1
    spec = importlib.util.spec_from_file_location(f"cd_{os.getpid()}_{_n[0]}", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    if genome is not None:
        m.configure(genome)
        return m.agent
    return getattr(m, "_submission_entry", None) or m.agent


def play(job):
    lbl, params, opp, seed, seat = job
    try:
        from planner.simulate import Simulator
        me = _load(AGENT, params)
        op = _load(os.path.join(ROOT, "opponents", f"{opp}.py"))
        pair = [me, op] if seat == 0 else [op, me]
        sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
        m0, m1 = sim.run_episode(pair[0], pair[1])
        us, them = (m0, m1) if seat == 0 else (m1, m0)
        return (lbl, opp, seed, seat, us - them, None)
    except Exception:
        import traceback
        return (lbl, opp, seed, seat, 0.0, traceback.format_exc()[-200:])


def base_genome():
    src = None
    for cand in ("best_genome3.json", "best_genome2.json", "best_genome.json"):
        p = os.path.join(ROOT, "dynamic", cand)
        if os.path.exists(p):
            src = p
            break
    g = to_params(dict(json.load(open(src))["genome"]))
    g["OPP_MODEL"] = 1
    return g


def score(res, ref_label):
    per = {}
    for lbl, opp, seed, seat, margin, err in res:
        if err:
            continue
        per.setdefault((lbl, opp, seed), []).append(margin)
    paired = {}
    for (lbl, opp, seed), v in per.items():
        if len(v) == 2:
            paired.setdefault(lbl, {})[(opp, seed)] = sum(v)
    ref = paired.get(ref_label, {})
    out = {}
    for lbl, d in paired.items():
        if lbl == ref_label:
            continue
        diffs = [d[k] - ref[k] for k in d if k in ref]
        if not diffs:
            continue
        w = sum(1 for x in diffs if x > 0)
        l = sum(1 for x in diffs if x < 0)
        mean = statistics.mean(diffs)
        mse = (statistics.pstdev(diffs) / (len(diffs) ** 0.5)) if len(diffs) > 1 else 0.0
        if w + l:
            p = w / float(w + l)
            wse = (0.25 / (w + l)) ** 0.5
            wt = (p - 0.5) / wse
        else:
            p, wt = 0.5, 0.0
        out[lbl] = {"margin": mean, "margin_t": mean / mse if mse > 1e-9 else 0.0,
                    "pp": 100 * (p - 0.5), "wt": wt, "w": w, "l": l}
    return out


def main():
    n_seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 32
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    batch = int(sys.argv[3]) if len(sys.argv) > 3 else 7
    import random
    base = base_genome()
    rng = random.Random(13579)
    seeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(n_seeds)]

    todo = [(k, v) for k, vals in AXES.items() for v in vals]
    print(f"{len(todo)} single-parameter variants, {n_seeds} seeds x "
          f"{len(POOL)} opponents x 2 seats, {workers} workers", flush=True)
    results = {}
    t0 = time.time()
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        V = [("REF", dict(base))]
        for k, v in chunk:
            p = dict(base)
            p[k] = v
            V.append((f"{k}={v}", p))
        jobs = [(l, p, o, s, st) for l, p in V for o in POOL
                for s in seeds for st in (0, 1)]
        with multiprocessing.get_context("forkserver").Pool(workers) as pool:
            res = pool.map(play, jobs, chunksize=4)
        results.update(score(res, "REF"))
        print(f"  batch {i // batch + 1}/{-(-len(todo) // batch)} "
              f"({time.time() - t0:.0f}s)", flush=True)

    print()
    print(f"{'variant':<30}{'winrate':>9}{'t':>7}{'W-L':>10}{'margin':>10}{'t':>7}")
    for lbl, r in sorted(results.items(), key=lambda kv: -kv[1]["wt"]):
        flag = "  <<<" if r["wt"] >= 2.0 else ""
        print(f"{lbl:<30}{50 + r['pp']:>8.1f}%{r['wt']:>7.2f}"
              f"{r['w']:>6}-{r['l']:<3}{r['margin']:>+10,.0f}{r['margin_t']:>7.2f}{flag}")
    json.dump(results, open(os.path.join(ROOT, "logs", "coord_descent.json"), "w"),
              indent=1)


if __name__ == "__main__":
    main()
