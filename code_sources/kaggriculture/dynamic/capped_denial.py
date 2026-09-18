"""Deny through the CAPPED books -- the direction the wheat test inverted.

dynamic/wheat_denial.py refuted wheat as the lever and did so informatively:
pushing wheat sales from 285 to 536 raised the OPPONENT's bank from 106,957 to
112,248. Wheat is what they BUY for feed (the engine allows BUY_PRODUCT only for
WHEAT and FERTILIZER), so flooding it subsidises their animals.

The same run also refuted an argument I had made earlier -- that capped products
cannot deny because both players clear at $1 past the cap. The cap is the volume
the book absorbs at a GOOD price; whoever takes it first keeps it, and the other
player's units clear at the floor. Cutting strawberry from 21 tiles to 0 drove
the opponent from 106,957 to 136,975, which is that mechanism running backwards.

So denial lives in STRAWBERRY / MELON / MILK, and it is bought at a price: we
already sell 165 strawberry against a 62-unit cap, so extra strawberry is
individually unprofitable for us. The question this run answers is which term is
bigger -- our loss on the marginal unit, or their loss of the headroom. That is
precisely where "maximise ours" and "maximise ours minus theirs" disagree, and
it is the comparison nothing tonight has measured.
"""
import importlib.util
import json
import multiprocessing
import os
import random
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from planner.simulate import Simulator  # noqa: E402
from route.search import to_params  # noqa: E402
from dynamic.attribute import _load  # noqa: E402

POOL = ["kaggriculture-multi-route-farming-agent",
        "v111-8c4s-economic-core-premium-lead",
        "kaggriculture-frontier-the-soil-remembers-rain",
        "kaggriculture-3000-socre",
        "kaggriculture-rank-your-agent",
        "strong-barnyard-economist"]
A2 = os.path.join(ROOT, "dynamic", "agent2.py")
CAPPED = ("STRAWBERRY", "MELON", "MILK", "WOOL")


def play(job):
    lbl, params, opp, seed, seat = job
    try:
        me = _load(A2, params)
        op = _load(os.path.join(ROOT, "opponents", f"{opp}.py"))
        pair = [me, op] if seat == 0 else [op, me]
        sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
        ours = {k: 0 for k in CAPPED}
        theirs_sold = {k: 0 for k in CAPPED}

        def hook(pid, o, item, price):
            if o != "SELL" or item not in CAPPED:
                return
            if pid == seat:
                ours[item] += 1
            else:
                theirs_sold[item] += 1
        sim.on_commit = hook
        m0, m1 = sim.run_episode(pair[0], pair[1])
        us, them = (m0, m1) if seat == 0 else (m1, m0)
        return (lbl, opp, seed, seat, us, them,
                sum(ours.values()), sum(theirs_sold.values()), None)
    except Exception:
        import traceback
        return (lbl, opp, seed, seat, 0.0, 0.0, 0, 0, traceback.format_exc()[-250:])


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 32
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 26
    g = json.load(open(os.path.join(ROOT, "planner", "checkpoints",
                                    "best_genome1.json")))["genome"]
    base = to_params(dict(g))
    base.update({"SCHEDULE_DRIVEN": 0, "USE_PLAN": 0, "USE_TRIAGE": 0,
                 "DYNAMIC_VALUE": 0})

    def P(**kw):
        p = dict(base)
        p["SEED_BATCH_PER_TURN"] = 20
        p.update(kw)
        return p

    V = [("live s21 m8 w8", dict(base))]
    # push the capped books, paying for it out of wheat
    V.append(("s27 m8 w2", P(TC_STRAWBERRY=27, TC_WHEAT=2)))
    V.append(("s21 m14 w2", P(TC_MELON=14, TC_WHEAT=2)))
    V.append(("s25 m12 w0", P(TC_STRAWBERRY=25, TC_MELON=12, TC_WHEAT=0)))
    # more milk/wool animals, paid for out of wheat and strawberry
    V.append(("cow9 sheep9 w2", P(TC_COW=9, TC_SHEEP=9, TC_WHEAT=2,
                                  TC_STRAWBERRY=17)))
    # capped-heavy AND bigger, the combination nothing has tried
    V.append(("s30 m16 c8 s8 62t", P(TC_STRAWBERRY=30, TC_MELON=16, TC_COW=8,
                                     TC_SHEEP=8, TC_WHEAT=0, TC_GOOSE=0)))
    V.append(("s34 m20 c8 s8 70t", P(TC_STRAWBERRY=34, TC_MELON=20, TC_COW=8,
                                     TC_SHEEP=8, TC_WHEAT=0, TC_GOOSE=0)))

    rng = random.Random(3316625)
    seeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(n)]
    jobs = [(l, p, o, s, st) for l, p in V for o in POOL for s in seeds
            for st in (0, 1)]
    print(f"{len(V)} variants x {len(jobs):,} games", flush=True)
    t0 = time.time()
    with multiprocessing.get_context("forkserver").Pool(workers) as pool:
        res = pool.map(play, jobs, chunksize=4)
    print(f"{time.time() - t0:.0f}s", flush=True)
    errs = [r[8] for r in res if r[8]]
    if errs:
        print(f"{len(errs)} errors; first {errs[0][-250:]}")

    pr, mine, theirs, ov, tv = {}, {}, {}, {}, {}
    for l, o, s, st, us, them, oc, tc_, e in res:
        if e:
            continue
        pr.setdefault((l, o, s), []).append(us - them)
        mine.setdefault(l, []).append(us)
        theirs.setdefault(l, []).append(them)
        ov.setdefault(l, []).append(oc)
        tv.setdefault(l, []).append(tc_)
    per = {}
    for k, v in pr.items():
        if len(v) == 2:
            per.setdefault(k[0], {})[k[1:]] = sum(v)
    b = per.get("live s21 m8 w8", {})
    print()
    print(f"{'variant':<20} {'paired':>11} {'vs live':>10} {'own':>9} "
          f"{'OPPONENT':>10} {'our capped':>11} {'their capped':>13}")
    rows = []
    for lbl, _ in V:
        d = per.get(lbl, {})
        if not d:
            continue
        diffs = [d[k] - b[k] for k in d if k in b]
        dm = statistics.mean(diffs) if diffs else 0.0
        rows.append((lbl, statistics.mean(d.values()), dm,
                     statistics.mean(mine[lbl]), statistics.mean(theirs[lbl]),
                     statistics.mean(ov[lbl]), statistics.mean(tv[lbl])))
    rows.sort(key=lambda r: -r[2])
    for lbl, mm, dm, om, tm, oc, tc_ in rows:
        print(f"{lbl:<20} {mm:>11,.0f} {dm:>+10,.0f} {om:>9,.0f} {tm:>10,.0f} "
              f"{oc:>11.0f} {tc_:>13.0f}")
    print(f"{'TAPE':<20} {5518:>11,} {'':>10} {86119:>9,} {80601:>10,}")


if __name__ == "__main__":
    main()
