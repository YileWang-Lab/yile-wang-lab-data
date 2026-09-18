"""Does the planner improve if its portfolio is allowed to exceed 50 tiles?

planner/schedule_diff.py found a hard structural cap. The land-purchase branch
in route/agent.py only fires when the LAYOUT has a non-EMPTY role waiting in the
next quadrant:

    wanted = any(role != "EMPTY" and quadrant_of(...) == nxt ...)
    if wanted and money >= price * LAND_BUY_CASH_MULTIPLE:

and the current best genome's TARGET_COUNTS sums to exactly 50 -- precisely NW
(25) + NE (25). SW therefore holds no roles, `wanted` is permanently False, and
the third quadrant can never be bought however much cash accumulates. Measured:
the planner ends the season sitting on $97k of unspent cash on 50 tiles while
the tape works 75.

This is the opposite end of the chain from the MIN_CREW experiment
(planner/v2_sweep.py, -13k to -52k), which forced hires without first creating
tiles for them to work. Crew size here is demand-driven -- _size_crew returns
the smallest crew that clears the day's tasks -- so adding TILES should pull
hires, seeds and land up behind it, rather than pushing an idle crew from the front.

Scales the portfolio keeping its proportions, so the only variable is size.
"""
import importlib.util, json, multiprocessing, os, random, statistics, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from planner.simulate import Simulator  # noqa: E402
from route.search import to_params  # noqa: E402

GENOME = os.path.join(ROOT, "planner", "checkpoints", "best_genome1.json")
TC_KEYS = ["TC_COW", "TC_SHEEP", "TC_GOOSE", "TC_MELON", "TC_STRAWBERRY", "TC_WHEAT"]
OPPONENTS = ["kaggriculture-multi-route-farming-agent",
             "v111-8c4s-economic-core-premium-lead",
             "kaggriculture-frontier-the-soil-remembers-rain",
             "kaggriculture-3000-socre",
             "kaggriculture-rank-your-agent",
             "strong-barnyard-economist"]
_n = [0]


def _load(path, genome=None):
    _n[0] += 1
    s = importlib.util.spec_from_file_location(f"sc_{os.getpid()}_{_n[0]}", path)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    if genome is not None:
        m.configure(to_params(genome)); return m.agent
    return getattr(m, "_submission_entry", None) or m.agent


def scaled(base, target_total):
    """Scale TARGET_COUNTS to `target_total` tiles, preserving proportions."""
    g = dict(base)
    cur = sum(g[k] for k in TC_KEYS)
    if cur <= 0:
        return g
    f = target_total / cur
    for k in TC_KEYS:
        g[k] = int(round(g[k] * f))
    # correct rounding drift on the largest component
    drift = target_total - sum(g[k] for k in TC_KEYS)
    if drift:
        big = max(TC_KEYS, key=lambda k: g[k])
        g[big] = max(0, g[big] + drift)
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
        return (lbl, opp, seed, seat, us - them, us, None)
    except Exception:
        import traceback
        return (lbl, opp, seed, seat, 0.0, 0.0, traceback.format_exc()[-200:])


def main():
    n_seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    base = json.load(open(GENOME))["genome"]
    print(f"base TARGET_COUNTS sums to {sum(base[k] for k in TC_KEYS)} tiles")
    variants = [(f"tiles{t}", scaled(base, t)) for t in (50, 58, 66, 74, 82, 90)]
    for lbl, g in variants:
        print(f"  {lbl}: " + " ".join(f"{k[3:]}={g[k]}" for k in TC_KEYS))
    rng = random.Random(31337)
    seeds = [rng.randrange(10**6, 2**31 - 1) for _ in range(n_seeds)]
    jobs = [(lbl, g, o, s, seat) for lbl, g in variants
            for o in OPPONENTS for s in seeds for seat in (0, 1)]
    print(f"\n{len(variants)} scales x {len(OPPONENTS)} opp x {n_seeds} seeds x 2 = {len(jobs):,} games")
    t0 = time.time()
    with multiprocessing.get_context("forkserver").Pool(24) as pool:
        res = pool.map(play, jobs, chunksize=4)
    print(f"elapsed {time.time()-t0:.0f}s")
    errs = [r for r in res if r[6]]
    if errs:
        print(f"{len(errs)} errors; first: {errs[0][6][-200:]}")

    paired, banks = {}, {}
    for lbl, opp, seed, seat, m, us, err in res:
        if err:
            continue
        paired.setdefault((lbl, opp, seed), []).append(m)
        banks.setdefault(lbl, []).append(us)
    per = {}
    for (lbl, opp, seed), ms in paired.items():
        if len(ms) == 2:
            per.setdefault(lbl, {})[(opp, seed)] = sum(ms)
    base_d = per.get("tiles50", {})
    print()
    print(f"{'scale':<10} {'n':>5} {'paired margin':>15} {'own bank':>11} "
          f"{'win%':>7} {'vs tiles50':>12} {'t':>6}")
    for lbl, _ in variants:
        d = per.get(lbl, {})
        if not d:
            continue
        ms = list(d.values())
        diffs = [d[k] - base_d[k] for k in d if k in base_d]
        dm = statistics.mean(diffs) if diffs else 0.0
        dse = (statistics.pstdev(diffs) / len(diffs) ** 0.5) if len(diffs) > 1 else 0.0
        print(f"{lbl:<10} {len(ms):>5} {statistics.mean(ms):>15,.0f} "
              f"{statistics.mean(banks[lbl]):>11,.0f} "
              f"{sum(1 for m in ms if m>0)/len(ms):>6.1%} {dm:>+12,.0f} "
              f"{dm/dse if dse else 0:>6.1f}")


if __name__ == "__main__":
    main()
