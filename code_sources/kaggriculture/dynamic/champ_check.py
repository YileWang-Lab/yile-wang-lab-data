"""A/B the marginal-value sell rule against the fixed reserve-price gate.

Discipline, all of it paid for earlier in this project:

  * PAIRED MARGIN with common random numbers -- every variant plays the same
    seeds from both seats against the same opponents, and a seed contributes
    (seat0 margin + seat1 margin). A byte-identical mirror then scores 0.
  * An IDENTITY CONTROL. `mv_off` sets MV_MARKET=0, which must reproduce the
    baseline at exactly +0. Three measurements were wasted here on parameters
    that turned out to be inert, and identical rows across variants is the
    symptom of that, not of a neutral idea.
  * FIRING RATE and the CONDITIONAL distribution, not just the mean. A change
    that alters behaviour in 13% of games and is worth +858 there reads as -18
    on a sample that only fired 28 times.
"""
import json
import multiprocessing
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HERE = os.path.dirname(os.path.abspath(__file__))
# Running this as a script puts dynamic/ on sys.path[0], where dynamic/search.py
# shadows the top-level search package that route.evaluate imports.
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _HERE]
sys.path.insert(0, ROOT)

POOL = ["kaggriculture-multi-route-farming-agent",
        "v111-8c4s-economic-core-premium-lead",
        "kaggriculture-frontier-the-soil-remembers-rain",
        "kaggriculture-3000-socre",
        "kaggriculture-rank-your-agent",
        "strong-barnyard-economist"]
AGENT = os.path.join(ROOT, "dynamic", "agent2.py")
_n = [0]


def _load(path, genome=None):
    import importlib.util
    _n[0] += 1
    spec = importlib.util.spec_from_file_location(f"mv_{os.getpid()}_{_n[0]}", path)
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
        if isinstance(params, str):          # a file path: load it as-is
            me = _load(params)
        else:
            me = _load(AGENT, params)
        op = _load(os.path.join(ROOT, "opponents", f"{opp}.py"))
        pair = [me, op] if seat == 0 else [op, me]
        sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
        m0, m1 = sim.run_episode(pair[0], pair[1])
        us, them = (m0, m1) if seat == 0 else (m1, m0)
        return (lbl, opp, seed, seat, us - them, us, None)
    except Exception:
        import traceback
        return (lbl, opp, seed, seat, 0.0, 0.0, traceback.format_exc()[-300:])


def base_genome():
    from route.search import to_params
    g = json.load(open(os.path.join(ROOT, "dynamic", "best_genome.json")))["genome"]
    p = to_params(dict(g))
    p["OPP_MODEL"] = 1          # the MV rule needs the per-turn observation
    return p


def variants(base):
    import json as _json, os as _os
    from route.search import to_params as _tp
    def V(**kw):
        p = dict(base); p.update(kw); return p
    out = [("reference (base)", V())]
    ck = _os.path.join(ROOT, "dynamic", "best_genome3.json")
    if _os.path.exists(ck):
        raw = _json.load(open(ck))
        g = _tp(dict(raw["genome"])); g["OPP_MODEL"] = 1
        out.append((f"GA gen{raw['gen']} champ", g))
        # the champion's individual changes, to see which (if any) carry it
        for k in ("LAND_BUY_CASH_MULTIPLE", "TC_MELON", "TC_WHEAT",
                  "HIRE_BUDGET_FRACTION", "SEED_BATCH_PER_TURN"):
            if k in raw["genome"]:
                out.append((f"only {k}={raw['genome'][k]:.3g}",
                            V(**{k: raw["genome"][k]})))
    return out


def report(res, V, n_seeds):
    """Report BOTH metrics side by side.

    Paired margin is the project's standard, but its variance is dominated by a
    few blow-out games -- sd is ~32,500 per paired game for a genome-level
    change, so a real +2,500 effect lands at t~1.1 even at n=216. A paired WIN
    RATE discards that tail (every seed contributes +-1) and is closer to what
    the ladder scores.

    Only valid in the PAIRED form. Raw win rate is invalid here (HANDOFF rule 1:
    seat asymmetry gives a byte-identical mirror 15% at seat 0), but comparing
    against the reference on the SAME seed is immune -- a true mirror scores
    margin exactly 0 on every seed, so it ties rather than losing. Ties are
    excluded from the rate and reported, the standard sign-test treatment.
    """
    per = {}
    for lbl, opp, seed, seat, margin, us, err in res:
        if err:
            continue
        per.setdefault((lbl, opp, seed), []).append(margin)
    paired = {}
    for (lbl, opp, seed), v in per.items():
        if len(v) == 2:
            paired.setdefault(lbl, {})[(opp, seed)] = sum(v)
    b = paired.get(V[0][0], {})
    print()
    print(f"{'variant':<24}{'margin':>10}{'se':>7}{'t':>7}   "
          f"{'winrate':>8}{'se':>6}{'t':>7}{'W-L-T':>13}")
    for lbl, _ in V:
        d = paired.get(lbl)
        if not d:
            continue
        keys = [k for k in d if k in b]
        diffs = [d[k] - b[k] for k in keys]
        if not diffs:
            continue
        mean = statistics.mean(diffs)
        se = (statistics.pstdev(diffs) / (len(diffs) ** 0.5)) if len(diffs) > 1 else 0.0
        t = mean / se if se > 1e-9 else 0.0
        w = sum(1 for x in diffs if x > 0)
        l = sum(1 for x in diffs if x < 0)
        ties = len(diffs) - w - l
        n_eff = w + l
        if n_eff:
            p = w / n_eff
            wse = (0.25 / n_eff) ** 0.5
            wt = (p - 0.5) / wse
        else:
            p, wse, wt = 0.5, 0.0, 0.0
        print(f"{lbl:<24}{mean:>+10,.0f}{se:>7,.0f}{t:>7.2f}   "
              f"{100 * p:>7.1f}%{100 * wse:>5.1f}{wt:>7.2f}"
              f"{w:>5}-{l}-{ties}")


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 26
    import random
    base = base_genome()
    V = variants(base)
    rng = random.Random(int(os.environ.get('MVSEED', '90210')))
    seeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(n)]
    jobs = [(l, p, o, s, st) for l, p in V for o in POOL for s in seeds for st in (0, 1)]
    print(f"{len(V)} variants x {len(POOL)} opponents x {n} seeds x 2 seats "
          f"= {len(jobs):,} games", flush=True)
    t0 = time.time()
    with multiprocessing.get_context("forkserver").Pool(workers) as pool:
        res = pool.map(play, jobs, chunksize=4)
    print(f"{time.time() - t0:.0f}s", flush=True)
    errs = [r[6] for r in res if r[6]]
    if errs:
        print(f"{len(errs)} errors; first:\n{errs[0]}")
    report(res, V, n)


if __name__ == "__main__":
    main()
