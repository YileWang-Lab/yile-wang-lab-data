"""Why is the tape's 51st-to-75th tile profitable when ours is not?

Five independent ways of adding scale were refuted tonight, every one making
the planner poorer: proportional portfolio scale-up (-87,245), a crew floor
(-52,000), crew and tiles together (-62,285), cycling-crop-heavy portfolios
(-150,176), and geese (-183,427). Meanwhile at 50 tiles the planner earns MORE
per work-turn than the tape. It is not less efficient; every marginal tile
simply costs more than it returns.

The one hypothesis left standing is TIMING of capital. The tape's economic
trajectory, read off as targets in planner/schedule_diff.py, front-loads
everything: land on days 6 and 11, all 14 animals placed by day 11, then a flat
~12 hands a day. Ours buys land late and animals in a trickle. An animal placed
on day 6 has 24 days to repay $400-500 of capital plus a wheat a day; the same
animal placed on day 18 has 12, and the feed bill is unchanged. Same asset,
half the payback window.

That predicts something specific and falsifiable: the loss from scaling should
shrink as purchases move EARLIER, even with portfolio and crew held fixed. This
sweeps purchase timing directly -- animal deadline, land schedule, and the cash
reserve that gates both -- rather than sweeping size again.
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
        return (lbl, opp, seed, seat, 0.0, 0.0, traceback.format_exc()[-200:])


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 32
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 26
    g = json.load(open(os.path.join(ROOT, "planner", "checkpoints",
                                    "best_genome1.json")))["genome"]
    base = to_params(dict(g)); base["SCHEDULE_DRIVEN"] = 0

    def P(**kw):
        p = dict(base); p.update(kw); return p

    V = [("base 50t", dict(base))]
    # timing alone, portfolio unchanged -- does front-loading help even at 50?
    V.append(("early_land", P(SCHEDULE_DRIVEN=1, CREW_SCHEDULE=None,
                              LAND_BUY_CASH_MULTIPLE=1.05)))
    V.append(("cheap_land", P(LAND_BUY_CASH_MULTIPLE=1.05)))
    V.append(("cheap_land_res80", P(LAND_BUY_CASH_MULTIPLE=1.05, SPEND_RESERVE=80.0)))
    V.append(("anim_fast", P(ANIMAL_BUY_CAP_PER_TURN=6, LAND_BUY_CASH_MULTIPLE=1.05)))
    V.append(("anim_fast_res80", P(ANIMAL_BUY_CAP_PER_TURN=6,
                                   LAND_BUY_CASH_MULTIPLE=1.05, SPEND_RESERVE=80.0)))
    # the same timing, now WITH the extra tiles that previously lost money
    for tiles, tc in ((62, dict(TC_COW=6, TC_SHEEP=8, TC_GOOSE=2, TC_MELON=10,
                                TC_STRAWBERRY=24, TC_WHEAT=12)),
                      (74, dict(TC_COW=7, TC_SHEEP=9, TC_GOOSE=3, TC_MELON=12,
                                TC_STRAWBERRY=31, TC_WHEAT=12))):
        V.append((f"t{tiles} slow", P(**tc)))
        V.append((f"t{tiles} frontload", P(ANIMAL_BUY_CAP_PER_TURN=6,
                                           LAND_BUY_CASH_MULTIPLE=1.05,
                                           SPEND_RESERVE=80.0,
                                           SEED_BATCH_PER_TURN=16, **tc)))
    V = [(l, {k: v for k, v in p.items() if v is not None}) for l, p in V]

    rng = random.Random(99991)
    seeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(n)]
    jobs = [(l, p, o, s, st) for l, p in V for o in POOL for s in seeds for st in (0, 1)]
    print(f"{len(V)} variants x {len(jobs):,} games", flush=True)
    t0 = time.time()
    with multiprocessing.get_context("forkserver").Pool(workers) as pool:
        res = pool.map(play, jobs, chunksize=4)
    print(f"{time.time()-t0:.0f}s", flush=True)
    errs = [r[6] for r in res if r[6]]
    if errs:
        print(f"{len(errs)} errors; first {errs[0][-200:]}")

    pr, bk = {}, {}
    for l, o, s, st, m, us, e in res:
        if e: continue
        pr.setdefault((l, o, s), []).append(m); bk.setdefault(l, []).append(us)
    per = {}
    for k, v in pr.items():
        if len(v) == 2:
            per.setdefault(k[0], {})[k[1:]] = sum(v)
    b = per.get("base 50t", {})
    print()
    print(f"{'variant':<20} {'paired margin':>14} {'vs base':>10} {'bank':>9} "
          f"{'work':>6} {'units':>6}")
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
                     statistics.mean(bk[lbl]), work, sum(h.values())))
    rows.sort(key=lambda r: -r[2])
    for lbl, mm, dm, bank, work, units in rows:
        print(f"{lbl:<20} {mm:>14,.0f} {dm:>+10,.0f} {bank:>9,.0f} {work:>6,} {units:>6,}")
    print(f"{'TAPE reference':<20} {'':>14} {'':>10} {96293:>9,} {2576:>6,} {1164:>6,}")


if __name__ == "__main__":
    main()
