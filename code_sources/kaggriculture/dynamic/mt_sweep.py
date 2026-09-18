"""A/B the market-timing scheduler and the fitted opponent model, on agent3.

agent3 is a copy of agent2 with both modules added and gated off, so the first
row -- agent3 with every new switch at its default -- must reproduce agent2
EXACTLY. It is included as a separate variant rather than assumed.

Runs at 10 workers on purpose: dynamic/search2.py owns the 26 physical cores
while it is searching, and extra load only slows it, never corrupts it.

A/B the marginal-value sell rule against the fixed reserve-price gate.

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
AGENT = os.path.join(ROOT, "dynamic", "agent3.py")
AGENT2 = os.path.join(ROOT, "dynamic", "agent2.py")
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
            me = _load(params, base_genome())
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


from route.search import to_params  # noqa: E402


def base_genome():
    g = json.load(open(os.path.join(ROOT, "dynamic", "best_genome.json")))["genome"]
    p = to_params(dict(g))
    p["OPP_MODEL"] = 1          # the MV rule needs the per-turn observation
    return p


def variants(base):
    def V(**kw):
        p = dict(base)
        p.update(kw)
        return p
    W = dict(NURSE_LATE=1, NURSE_CROP="WHEAT")
    # NOTE: the baseline now has NURSE_LATE=1 by default, so the identity
    # control must switch it OFF explicitly rather than leave it unset.
    import os as _os, json as _json
    # Is the GA's reported improvement real, or is it the max over noisy
    # estimates? It scores each genome on 5 seeds x 6 opponents = 15 paired
    # games and redraws the seeds every generation, which is well inside the
    # region HANDOFF section 5 says is noise-dominated. Re-evaluate its saved
    # best at a sample size where a rank means something.
    out = [("agent2 default (base)", V())]
    for tag, fn in (("GA search2 best", "best_genome2.json"),
                    ("GA search3 best", "best_genome3.json")):
        path = _os.path.join(ROOT, "dynamic", fn)
        if not _os.path.exists(path):
            continue
        raw = _json.load(open(path))
        g = to_params(dict(raw["genome"]))
        g["OPP_MODEL"] = 1
        out.append((f"{tag} (gen {raw['gen']}, claimed {raw['fitness']:+,.0f})", g))
    return out


def report(res, V, n_seeds):
    per = {}
    for lbl, opp, seed, seat, margin, us, err in res:
        if err:
            continue
        per.setdefault((lbl, opp, seed), []).append(margin)
    paired = {}
    for (lbl, opp, seed), v in per.items():
        if len(v) == 2:
            paired.setdefault(lbl, {})[(opp, seed)] = sum(v)
    # The base is whatever the variant list puts FIRST, not a fixed label --
    # renaming the baseline silently emptied every diff once.
    b = paired.get(V[0][0], {})
    print()
    print(f"{'variant':<20}{'paired margin':>15}{'vs base':>11}{'se':>8}"
          f"{'t':>7}{'wins':>9}{'fires':>8}{'cond. mean':>12}")
    rows = []
    for lbl, _ in V:
        d = paired.get(lbl)
        if not d:
            continue
        keys = [k for k in d if k in b]
        diffs = [d[k] - b[k] for k in keys]
        fired = [x for x in diffs if x != 0.0]
        se = (statistics.pstdev(diffs) / (len(diffs) ** 0.5)) if len(diffs) > 1 else 0.0
        mean = statistics.mean(diffs) if diffs else 0.0
        rows.append((lbl, statistics.mean(d.values()), mean, se,
                     mean / se if se > 1e-9 else 0.0,
                     sum(1 for x in diffs if x > 0), len(diffs),
                     len(fired), statistics.mean(fired) if fired else 0.0))
    for lbl, mm_, dm, se, t, w, n, nf, cm in rows:
        print(f"{lbl:<20}{mm_:>15,.0f}{dm:>+11,.0f}{se:>8,.0f}{t:>7.1f}"
              f"{w:>5}/{n:<3}{100.0 * nf / max(1, n):>7.0f}%{cm:>+12,.0f}")


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
