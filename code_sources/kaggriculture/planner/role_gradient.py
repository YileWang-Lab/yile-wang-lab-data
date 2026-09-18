"""Per-role marginal value: which way does each portfolio slot want to move?

The GA has been mutating TARGET_COUNTS jointly for ~140 generations and settled
on 50 tiles (COW 5 / SHEEP 6 / GOOSE 2 / MELON 8 / STRAWBERRY 21 / WHEAT 8).
planner/scale_sweep.py showed scaling that portfolio UP is monotonically worse,
so the binding constraint is throughput per tile rather than board size --
which makes the useful question "which role converts an operation into money
best", not "how many tiles".

A joint search answers that only implicitly and slowly. This measures it
directly: hold everything else fixed, move ONE role by +/-k tiles, and read off
the local gradient. Roles whose gradient is flat are noise the GA has been
spending its budget on; roles with a consistent sign are a direction it has not
yet exploited.

Total tile count is held constant by compensating on the role being tested
against the largest other role, so this measures COMPOSITION, not size (size is
already answered by scale_sweep).
"""
import importlib.util, json, multiprocessing, os, random, statistics, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from planner.simulate import Simulator  # noqa: E402
from route.search import to_params  # noqa: E402

GENOME = os.path.join(ROOT, "planner", "checkpoints", "best_genome1.json")
TC = ["TC_COW", "TC_SHEEP", "TC_GOOSE", "TC_MELON", "TC_STRAWBERRY", "TC_WHEAT"]
OPPONENTS = ["kaggriculture-multi-route-farming-agent",
             "v111-8c4s-economic-core-premium-lead",
             "kaggriculture-frontier-the-soil-remembers-rain",
             "kaggriculture-3000-socre",
             "kaggriculture-rank-your-agent",
             "strong-barnyard-economist"]
_n = [0]


def _load(path, genome=None):
    _n[0] += 1
    s = importlib.util.spec_from_file_location(f"rg_{os.getpid()}_{_n[0]}", path)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    if genome is not None:
        m.configure(to_params(genome)); return m.agent
    return getattr(m, "_submission_entry", None) or m.agent


def perturb(base, role, delta):
    """Move `role` by delta, compensating PROPORTIONALLY across all other roles
    so the total tile count is unchanged.

    The first version of this compensated on the single largest other role,
    which silently made the test useless: STRAWBERRY was the largest at 21, so
    "MELON-2" and "STRAWBERRY+2" both produced MELON=6/STRAWBERRY=23 -- the
    same genome, scored twice. Every perturbation was really a pairwise trade
    against STRAWBERRY rather than a gradient in one role. (The duplicate rows
    matched to the dollar, which is at least a clean determinism check.)

    Spreading the compensation keeps the rest of the portfolio's shape intact,
    so the measured difference is attributable to `role` alone.
    """
    g = dict(base)
    if g[role] + delta < 0:
        return None
    others = [k for k in TC if k != role and g[k] > 0]
    pool = sum(g[k] for k in others)
    if pool - delta < len(others):
        return None
    g[role] += delta
    # remove `delta` tiles from the others in proportion to their current size
    remaining = delta
    for i, k in enumerate(sorted(others, key=lambda k: -g[k])):
        take = round(delta * g[k] / pool) if i < len(others) - 1 else remaining
        take = max(min(take, g[k] - 1), -(50))
        g[k] -= take
        remaining -= take
        if remaining == 0:
            break
    if remaining:
        for k in sorted(others, key=lambda k: -g[k]):
            adj = max(-(g[k] - 1), -remaining) if remaining < 0 else min(g[k] - 1, remaining)
            g[k] -= adj
            remaining -= adj
            if remaining == 0:
                break
    if any(g[k] < 0 for k in TC) or sum(g[k] for k in TC) != sum(base[k] for k in TC):
        return None
    return g


def play(job):
    lbl, genome, opp, seed, seat = job
    try:
        me = _load(os.path.join(ROOT, "route", "agent.py"), genome)
        op = _load(os.path.join(ROOT, "opponents", f"{opp}.py"))
        pair = [me, op] if seat == 0 else [op, me]
        sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
        m0, m1 = sim.run_episode(pair[0], pair[1])
        us, them = (m0, m1) if seat == 0 else (m1, m0)
        return (lbl, opp, seed, seat, us - them, None)
    except Exception:
        import traceback
        return (lbl, opp, seed, seat, 0.0, traceback.format_exc()[-200:])


def main():
    n_seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    base = json.load(open(GENOME))["genome"]
    print("base: " + " ".join(f"{k[3:]}={base[k]}" for k in TC)
          + f"  (total {sum(base[k] for k in TC)})")

    variants = [("base", dict(base))]
    for role in TC:
        for d in (-4, -2, +2, +4):
            g = perturb(base, role, d)
            if g:
                variants.append((f"{role[3:]}{d:+d}", g))

    rng = random.Random(8642)
    seeds = [rng.randrange(10**6, 2**31 - 1) for _ in range(n_seeds)]
    jobs = [(lbl, g, o, s, seat) for lbl, g in variants
            for o in OPPONENTS for s in seeds for seat in (0, 1)]
    print(f"{len(variants)} variants x {len(OPPONENTS)} opp x {n_seeds} seeds x 2 "
          f"= {len(jobs):,} games")
    t0 = time.time()
    with multiprocessing.get_context("forkserver").Pool(24) as pool:
        res = pool.map(play, jobs, chunksize=4)
    print(f"elapsed {time.time()-t0:.0f}s")

    paired = {}
    for lbl, opp, seed, seat, m, err in res:
        if not err:
            paired.setdefault((lbl, opp, seed), []).append(m)
    per = {}
    for (lbl, opp, seed), ms in paired.items():
        if len(ms) == 2:
            per.setdefault(lbl, {})[(opp, seed)] = sum(ms)
    b = per.get("base", {})

    print()
    print(f"{'variant':<16} {'paired margin':>15} {'vs base':>11} {'+/-se':>8} {'t':>6}")
    rows = []
    for lbl, _ in variants:
        d = per.get(lbl, {})
        if not d:
            continue
        diffs = [d[k] - b[k] for k in d if k in b]
        dm = statistics.mean(diffs) if diffs else 0.0
        dse = (statistics.pstdev(diffs) / len(diffs) ** 0.5) if len(diffs) > 1 else 0.0
        rows.append((lbl, statistics.mean(d.values()), dm, dse, dm / dse if dse else 0.0))
    rows.sort(key=lambda r: -r[2])
    for lbl, mm, dm, dse, t in rows:
        mark = "  <-- base" if lbl == "base" else ""
        print(f"{lbl:<16} {mm:>15,.0f} {dm:>+11,.0f} {dse:>8,.0f} {t:>6.1f}{mark}")


if __name__ == "__main__":
    main()
