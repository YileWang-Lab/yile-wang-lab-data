"""Does moving BOTH ends of the chain work, where moving either alone failed?

  planner/scale_sweep.py   more tiles, demand-driven crew   -87,245 at 74 tiles
  planner/v2_sweep.py      more crew, 50-tile portfolio     -13k to -52k

The tape does both, in order: land on days 6 and 11, animals placed by day 11,
then ~12 hands a day sustained. dynamic/agent.py follows that trajectory as
targets. This grid crosses portfolio size against schedule-driven vs
demand-driven crew, so the interaction is visible rather than inferred.

The identity check matters: SCHEDULE_DRIVEN=0 at 50 tiles must reproduce
route/agent.py exactly, or the comparison is measuring a rewrite rather than
the change.
"""
import importlib.util, json, multiprocessing, os, random, statistics, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from planner.simulate import Simulator  # noqa: E402
from route.search import to_params  # noqa: E402

GENOME = os.path.join(ROOT, "planner", "checkpoints", "best_genome1.json")
TC = ["TC_COW", "TC_SHEEP", "TC_GOOSE", "TC_MELON", "TC_STRAWBERRY", "TC_WHEAT"]
POOL = ["kaggriculture-multi-route-farming-agent",
        "v111-8c4s-economic-core-premium-lead",
        "kaggriculture-frontier-the-soil-remembers-rain",
        "kaggriculture-3000-socre",
        "kaggriculture-rank-your-agent",
        "strong-barnyard-economist"]
_n = [0]


def _load(path, genome=None):
    _n[0] += 1
    s = importlib.util.spec_from_file_location(f"dy_{os.getpid()}_{_n[0]}", path)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    if genome is not None:
        m.configure(genome); return m.agent
    return getattr(m, "_submission_entry", None) or m.agent


def scaled(base, total):
    g = dict(base)
    cur = sum(g[k] for k in TC)
    f = total / cur
    for k in TC:
        g[k] = int(round(g[k] * f))
    drift = total - sum(g[k] for k in TC)
    if drift:
        big = max(TC, key=lambda k: g[k]); g[big] += drift
    return g


def play(job):
    lbl, path, params, opp, seed, seat = job
    try:
        me = _load(path, params)
        op = _load(os.path.join(ROOT, "opponents", f"{opp}.py"))
        pair = [me, op] if seat == 0 else [op, me]
        sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
        m0, m1 = sim.run_episode(pair[0], pair[1])
        us, them = (m0, m1) if seat == 0 else (m1, m0)
        return (lbl, opp, seed, seat, us - them, us, None)
    except Exception:
        import traceback
        return (lbl, opp, seed, seat, 0.0, 0.0, traceback.format_exc()[-250:])


def main():
    n_seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    base = json.load(open(GENOME))["genome"]
    DYN = os.path.join(ROOT, "dynamic", "agent.py")
    RTE = os.path.join(ROOT, "route", "agent.py")

    variants = [("route_baseline", RTE, to_params(dict(base)))]
    for tiles in (50, 62, 74, 86):
        for sched in (0, 1):
            g = scaled(base, tiles)
            p = to_params(dict(g)); p["SCHEDULE_DRIVEN"] = sched
            variants.append((f"t{tiles}_{'sched' if sched else 'demand'}", DYN, p))

    rng = random.Random(4711)
    seeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(n_seeds)]
    jobs = [(l, p, pr, o, s, seat) for l, p, pr in variants
            for o in POOL for s in seeds for seat in (0, 1)]
    print(f"{len(variants)} variants x {len(POOL)} opp x {n_seeds} seeds x 2 = {len(jobs):,} games")
    t0 = time.time()
    with multiprocessing.get_context("forkserver").Pool(workers) as pool:
        res = pool.map(play, jobs, chunksize=4)
    print(f"elapsed {time.time()-t0:.0f}s")
    errs = [r[6] for r in res if r[6]]
    if errs:
        print(f"{len(errs)} errors; first: {errs[0][-250:]}")

    paired, banks = {}, {}
    for lbl, opp, seed, seat, m, us, err in res:
        if err: continue
        paired.setdefault((lbl, opp, seed), []).append(m)
        banks.setdefault(lbl, []).append(us)
    per = {}
    for (lbl, opp, seed), ms in paired.items():
        if len(ms) == 2:
            per.setdefault(lbl, {})[(opp, seed)] = sum(ms)
    b = per.get("route_baseline", {})
    print()
    print(f"{'variant':<18} {'n':>4} {'paired margin':>15} {'own bank':>11} {'win%':>7} {'vs route':>12}")
    for lbl, _, _ in variants:
        d = per.get(lbl, {})
        if not d: continue
        ms = list(d.values())
        diffs = [d[k] - b[k] for k in d if k in b]
        dm = statistics.mean(diffs) if diffs else 0.0
        print(f"{lbl:<18} {len(ms):>4} {statistics.mean(ms):>15,.0f} "
              f"{statistics.mean(banks[lbl]):>11,.0f} "
              f"{sum(1 for m in ms if m>0)/len(ms):>6.1%} {dm:>+12,.0f}")
    idc = per.get("t50_demand", {})
    if idc and b:
        k = [x for x in idc if x in b]
        d = statistics.mean(idc[x] - b[x] for x in k)
        print()
        print(f"IDENTITY CHECK  t50_demand vs route/agent.py: {d:+,.0f} "
              f"(must be ~0; dynamic/agent.py is route with the schedule bolted on)")


if __name__ == "__main__":
    main()
