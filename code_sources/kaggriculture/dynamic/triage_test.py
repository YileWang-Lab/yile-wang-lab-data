"""Does whole-tile triage raise the number of tiles the scheduler can sustain?

Seven scaling experiments failed tonight and the transplant of the tape's own
73-tile layout finally showed why: same layout, 811 units and $45,147 for us
against the tape's 1,164 and $96,293. The board was never the constraint --
servicing it is.

route/router.py fits an over-subscribed day by dropping the cheapest tasks one
at a time, spreading the shortfall over every tile. The engine makes that the
worst possible choice: two consecutive unwatered nights turn a plant into a
weed and two unfed nights lose the animal, so a tile served on 70% of days is
simply a dead tile. dynamic/router2.py instead abandons whole tiles, worst
value-per-turn first, and never abandons one whose asset dies today.

The question is not whether triage helps at 73 -- a first single-seed probe put
it at +19% there. It is whether triage moves the CEILING, i.e. whether the
sustainable tile count rises above ~50. So the sweep crosses tile count against
triage, and includes 50 tiles as a control where triage must be inert because
capacity already exceeds demand.
"""
import importlib.util, json, multiprocessing, os, random, statistics, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from planner.simulate import Simulator  # noqa: E402
from route.search import to_params  # noqa: E402
from dynamic.attribute import trace, _load  # noqa: E402

POOL = ["kaggriculture-multi-route-farming-agent",
        "v111-8c4s-economic-core-premium-lead",
        "kaggriculture-frontier-the-soil-remembers-rain",
        "kaggriculture-3000-socre",
        "kaggriculture-rank-your-agent",
        "strong-barnyard-economist"]
A2 = os.path.join(ROOT, "dynamic", "agent2.py")
TC = ["TC_COW", "TC_SHEEP", "TC_GOOSE", "TC_MELON", "TC_STRAWBERRY", "TC_WHEAT"]


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
    lbl, params, opp, seed, seat = job
    try:
        me = _load(A2, params)
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
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    g = json.load(open(os.path.join(ROOT, "planner", "checkpoints",
                                    "best_genome1.json")))["genome"]
    base = to_params(dict(g))
    base.update({"SCHEDULE_DRIVEN": 0, "USE_PLAN": 0, "USE_TRIAGE": 0,
                 "DYNAMIC_VALUE": 0})

    V = []
    for tiles in (50, 58, 66, 74):
        tc = scaled(g, tiles)
        tcp = {k: tc[k] for k in TC}
        for tri in (0, 1):
            V.append((f"t{tiles}{'_triage' if tri else ''}",
                      {**base, **tcp, "USE_TRIAGE": tri, "DYNAMIC_VALUE": tri,
                       "SEED_BATCH_PER_TURN": 16}))
    # the tape's own plan, with and without triage
    V.append(("plan73", {**base, "USE_PLAN": 1, "SEED_BATCH_PER_TURN": 16}))
    V.append(("plan73_triage", {**base, "USE_PLAN": 1, "USE_TRIAGE": 1,
                                "DYNAMIC_VALUE": 1, "SEED_BATCH_PER_TURN": 16}))
    for kr in (0.75, 0.9):
        V.append((f"plan73_tri_kr{int(kr*100)}",
                  {**base, "USE_PLAN": 1, "USE_TRIAGE": 1, "DYNAMIC_VALUE": 1,
                   "KEEP_RATIO": kr, "SEED_BATCH_PER_TURN": 16}))

    rng = random.Random(1414213)
    seeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(n)]
    jobs = [(l, p, o, s, st) for l, p in V for o in POOL for s in seeds for st in (0, 1)]
    print(f"{len(V)} variants x {len(jobs):,} games", flush=True)
    t0 = time.time()
    with multiprocessing.get_context("forkserver").Pool(workers) as pool:
        res = pool.map(play, jobs, chunksize=4)
    print(f"{time.time()-t0:.0f}s", flush=True)
    errs = [r[6] for r in res if r[6]]
    if errs:
        print(f"{len(errs)} errors; first {errs[0][-250:]}")

    pr, bk = {}, {}
    for l, o, s, st, m, us, e in res:
        if e: continue
        pr.setdefault((l, o, s), []).append(m); bk.setdefault(l, []).append(us)
    per = {}
    for k, v in pr.items():
        if len(v) == 2:
            per.setdefault(k[0], {})[k[1:]] = sum(v)
    b = per.get("t50", {})
    print()
    print(f"{'variant':<20} {'paired margin':>14} {'vs t50':>11} {'bank':>9} "
          f"{'work':>6} {'units':>6}")
    for lbl, params in V:
        d = per.get(lbl, {})
        if not d: continue
        diffs = [d[k] - b[k] for k in d if k in b]
        dm = statistics.mean(diffs) if diffs else 0.0
        me = _load(A2, params)
        opp = _load(os.path.join(ROOT, "opponents",
                                 "v111-8c4s-economic-core-premium-lead.py"))
        c, h, r, bank = trace(me, opp, 1009)
        work = c["produce"] + c["enable"] + c["build"]
        print(f"{lbl:<20} {statistics.mean(d.values()):>14,.0f} {dm:>+11,.0f} "
              f"{statistics.mean(bk[lbl]):>9,.0f} {work:>6,} {sum(h.values()):>6,}")
    print(f"{'TAPE reference':<20} {'':>14} {'':>11} {96293:>9,} {2576:>6,} {1164:>6,}")


if __name__ == "__main__":
    main()
