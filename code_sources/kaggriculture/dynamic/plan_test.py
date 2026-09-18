"""Does the tape's SEASON PLAN transfer to a dynamic scheduler?

The plan is a declarative target from dynamic/seasonplan.py -- tile -> (role,
come-online day) -- with 73 of 75 tiles identical across four seeds. It is not
the tape's actions, which were already measured unusable as a policy
(planner/bc_play.py: $288 against $89k, with a control proving the network was
correct and the failure was covariate shift).

The plan carries two separable things, so they are tested separately. If they
are only useful together, that is worth knowing; if one carries all the value,
the other is noise to drop.

  LAYOUT  27 STRAWBERRY / 20 MELON / 14 animals / 12 WHEAT on specific tiles,
          against our searched 21/8/13/8. Note this is a portfolio our own
          role-gradient sweep would never have found: it measured all 24
          single-role perturbations of the 50-tile optimum negative, MELON+2 at
          -72,661, yet the tape runs 20 melon profitably at 75 tiles.

  ORDER   cheap tiles first (day 0: 12 melon at $80, 7 wheat at $10), expensive
          strawberry at $100 deferred to days 11-12 behind the third quadrant.
          Six scaling experiments tonight all failed through cash; this ordering
          is a sequence known to be feasible from $3,000.
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
DYN = os.path.join(ROOT, "dynamic", "agent.py")


def play(job):
    lbl, params, opp, seed, seat = job
    try:
        me = _load(DYN, params)
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
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 32
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    g = json.load(open(os.path.join(ROOT, "planner", "checkpoints",
                                    "best_genome1.json")))["genome"]
    base = to_params(dict(g))
    base.update({"SCHEDULE_DRIVEN": 0, "USE_PLAN": 0})

    def P(**kw):
        p = dict(base); p.update(kw); p["USE_PLAN"] = 1
        p.setdefault("SEED_BATCH_PER_TURN", 16)
        return p

    V = [
        ("baseline 50t", dict(base)),
        # layout only -- the tape's tiles and roles, planted as soon as possible
        ("plan_layout", P(PLAN_GATE_DAYS=0)),
        # layout + build order
        ("plan_full", P(PLAN_GATE_DAYS=1)),
        ("plan_full_slack2", P(PLAN_GATE_DAYS=1, PLAN_SLACK=2)),
        # plan plus the tape's crew trajectory
        ("plan_full_sched", P(PLAN_GATE_DAYS=1, SCHEDULE_DRIVEN=1)),
        ("plan_layout_sched", P(PLAN_GATE_DAYS=0, SCHEDULE_DRIVEN=1)),
        # plan with land bought on the tape's schedule (day 6 / day 11)
        ("plan_full_land", P(PLAN_GATE_DAYS=1, LAND_BUY_CASH_MULTIPLE=1.05)),
        ("plan_all", P(PLAN_GATE_DAYS=1, SCHEDULE_DRIVEN=1,
                       LAND_BUY_CASH_MULTIPLE=1.05, ANIMAL_BUY_CAP_PER_TURN=4)),
        # the plan's own feed/seed needs are larger than the 50-tile settings
        ("plan_all_fed", P(PLAN_GATE_DAYS=1, SCHEDULE_DRIVEN=1,
                           LAND_BUY_CASH_MULTIPLE=1.05, ANIMAL_BUY_CAP_PER_TURN=4,
                           WHEAT_FEED_BUFFER_MULT=2.0, MAX_HANDS=20)),
    ]
    rng = random.Random(112358)
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
    b = per.get("baseline 50t", {})
    print()
    print(f"{'variant':<20} {'paired margin':>14} {'vs base':>11} {'bank':>9} "
          f"{'work':>6} {'units':>6} {'build':>6}")
    rows = []
    for lbl, params in V:
        d = per.get(lbl, {})
        if not d: continue
        diffs = [d[k] - b[k] for k in d if k in b]
        dm = statistics.mean(diffs) if diffs else 0.0
        me = _load(DYN, params)
        opp = _load(os.path.join(ROOT, "opponents",
                                 "v111-8c4s-economic-core-premium-lead.py"))
        c, h, r, bank = trace(me, opp, 1009)
        work = c["produce"] + c["enable"] + c["build"]
        rows.append((lbl, statistics.mean(d.values()), dm,
                     statistics.mean(bk[lbl]), work, sum(h.values()), c["build"]))
    rows.sort(key=lambda r: -r[2])
    for lbl, mm, dm, bank, work, units, build in rows:
        print(f"{lbl:<20} {mm:>14,.0f} {dm:>+11,.0f} {bank:>9,.0f} {work:>6,} "
              f"{units:>6,} {build:>6,}")
    print(f"{'TAPE reference':<20} {'':>14} {'':>11} {96293:>9,} {2576:>6,} "
          f"{1164:>6,} {265:>6,}")


if __name__ == "__main__":
    main()
