"""Scale with GEESE -- the one product the market cannot saturate.

Everything measured tonight says the gap is 23% fewer WORK turns (2,097 against
the tape's 2,576), not efficiency: revenue per work-turn is $35.34 for us and
$35.98 for the tape, and our turn allocation is better than the tape's at every
scale (work fraction 40.4% vs 37.2%, movement 42.3% vs 50.2%).

Every previous attempt to add work turns diluted revenue instead, and the price
curves say why. The high-value products are market-capped -- selling from the
10,000 baseline, price reaches the $1 floor after roughly 62 STRAWBERRY, 59
WOOL, 76 MILK, 158 MELON -- and we already sell 159 strawberry. Adding tiles
therefore means adding cheap product, which is exactly what cycle_test showed:
units 821 -> 1,135 while the bank fell 74,878 -> 42,200.

EGG is the exception. Its curve is logarithmic: the 80th unit still fetches 84%
of base, and ~20,000 units are sellable before the floor. GOOSE is also the
cheapest animal ($300), the fastest to first yield (day 4), produces EVERY day
(interval 1, so 2 eggs/day fed and cared), and measured 0.60 units per upkeep
turn against strawberry's 0.38. No agent on the visible ladder places a single
goose.

So this holds the existing 50-tile recipe fixed and adds geese on top -- the
only expansion that neither displaces a high-value role nor sells into a capped
market.
"""
import importlib.util, json, multiprocessing, os, statistics, sys, time

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
    n_seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    g = json.load(open(os.path.join(ROOT, "planner", "checkpoints",
                                    "best_genome1.json")))["genome"]
    base = to_params(dict(g))
    base["SCHEDULE_DRIVEN"] = 0

    def P(**kw):
        p = dict(base); p.update(kw); p["SEED_BATCH_PER_TURN"] = 20
        return p

    variants = [("base 50t", dict(base))]
    for extra in (6, 12, 18, 25):
        variants.append((f"+{extra}goose {50+extra}t", P(TC_GOOSE=2 + extra)))
    variants.append(("+18goose sched", P(TC_GOOSE=20, SCHEDULE_DRIVEN=1)))
    variants.append(("+25goose sched", P(TC_GOOSE=27, SCHEDULE_DRIVEN=1)))

    import random
    rng = random.Random(8080)
    seeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(n_seeds)]
    jobs = [(l, p, o, s, st) for l, p in variants for o in POOL
            for s in seeds for st in (0, 1)]
    print(f"{len(variants)} variants x {len(jobs):,} games", flush=True)
    t0 = time.time()
    with multiprocessing.get_context("forkserver").Pool(workers) as pool:
        res = pool.map(play, jobs, chunksize=4)
    print(f"{time.time()-t0:.0f}s", flush=True)
    errs = [r[6] for r in res if r[6]]
    if errs:
        print(f"{len(errs)} errors: {errs[0][-200:]}")

    pr, bk = {}, {}
    for l, o, s, st, m, us, e in res:
        if e: continue
        pr.setdefault((l, o, s), []).append(m)
        bk.setdefault(l, []).append(us)
    per = {}
    for k, v in pr.items():
        if len(v) == 2:
            per.setdefault(k[0], {})[k[1:]] = sum(v)
    b = per.get("base 50t", {})
    print()
    print(f"{'variant':<18} {'paired margin':>14} {'vs base':>10} {'bank':>9} "
          f"{'work':>6} {'units':>6} {'$/work':>8} {'EGG':>6}")
    for lbl, params in variants:
        d = per.get(lbl, {})
        if not d: continue
        diffs = [d[k] - b[k] for k in d if k in b]
        dm = statistics.mean(diffs) if diffs else 0.0
        me = _load(DYN, params)
        opp = _load(os.path.join(ROOT, "opponents",
                                 "v111-8c4s-economic-core-premium-lead.py"))
        c, h, r, bank = trace(me, opp, 1009)
        work = c["produce"] + c["enable"] + c["build"]
        print(f"{lbl:<18} {statistics.mean(d.values()):>14,.0f} {dm:>+10,.0f} "
              f"{statistics.mean(bk[lbl]):>9,.0f} {work:>6,} {sum(h.values()):>6,} "
              f"{bank/work if work else 0:>8.2f} {h.get('GOOSE',0):>6,}")
    print(f"{'TAPE reference':<18} {'':>14} {'':>10} {96293:>9,} {2576:>6,} "
          f"{1164:>6,} {37.40:>8.2f} {0:>6,}")


if __name__ == "__main__":
    main()
