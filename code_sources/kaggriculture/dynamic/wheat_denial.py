"""Wheat throughput as the denial lever -- the last hypothesis standing.

Established tonight: our own bank already matches the tape's (86,386 vs 86,119)
and the entire paired-margin gap is that the opponent banks $50,921 more against
us than against it. Denial, not earnings.

Two engine facts constrain how denial can possibly be achieved.

  Buying to dump is impossible. _commit_unit quotes BUY_PRODUCT at
  market_price(inv - 1), i.e. post-buy, "so a buy/sell round-trip against an
  unchanged market nets zero". Denial has to be PRODUCED.

  Only wheat has room. From the 10,000 baseline the price floors after ~62
  STRAWBERRY, 59 WOOL, 76 MILK, 158 MELON -- past that, extra volume denies
  nothing because the opponent's units clear at $1 either way. WHEAT is
  logarithmic: 20,000 units still fetch ~$20. It is the only book deep enough
  for volume to be a weapon, which is also why the seven scaling experiments
  failed -- they scaled the capped products.

The tape sells 605 wheat and buys 502 for feed; we sell 284 and buy 446, i.e.
we are a net wheat CONSUMER (-162) where it is a net seller (+103).

planner/role_gradient.py scored WHEAT+2 at -70,058, but compensated
proportionally across every role. Trading wheat against STRAWBERRY specifically
cost -1,099 while nearly doubling wheat output, which is a different experiment
and the one this follows.

Reports the OPPONENT's bank per variant, not just ours -- the term that went
unmeasured all night and turned out to be the whole deficit.
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


def play(job):
    lbl, params, opp, seed, seat = job
    try:
        me = _load(A2, params)
        op = _load(os.path.join(ROOT, "opponents", f"{opp}.py"))
        pair = [me, op] if seat == 0 else [op, me]
        sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
        sold = {"n": 0}

        def hook(pid, o, item, price):
            if pid == seat and o == "SELL" and item == "WHEAT":
                sold["n"] += 1
        sim.on_commit = hook
        m0, m1 = sim.run_episode(pair[0], pair[1])
        us, them = (m0, m1) if seat == 0 else (m1, m0)
        return (lbl, opp, seed, seat, us, them, sold["n"], None)
    except Exception:
        import traceback
        return (lbl, opp, seed, seat, 0.0, 0.0, 0, traceback.format_exc()[-250:])


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 32
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 26
    g = json.load(open(os.path.join(ROOT, "planner", "checkpoints",
                                    "best_genome1.json")))["genome"]
    base = to_params(dict(g))
    base.update({"SCHEDULE_DRIVEN": 0, "USE_PLAN": 0, "USE_TRIAGE": 0,
                 "DYNAMIC_VALUE": 0})

    def W(wheat, straw, **kw):
        p = dict(base)
        p["TC_WHEAT"] = wheat
        p["TC_STRAWBERRY"] = straw
        p["SEED_BATCH_PER_TURN"] = 20
        p.update(kw)
        return p

    V = [("live w8 s21", dict(base))]
    for w, s in ((14, 15), (20, 9), (26, 3), (29, 0)):
        V.append((f"w{w} s{s}", W(w, s)))
    # buy the feed instead of withholding the crop, as the tape does
    V.append(("w20 s9 feedbuy", W(20, 9, WHEAT_FEED_BUFFER_MULT=2.5)))
    V.append(("w26 s3 feedbuy", W(26, 3, WHEAT_FEED_BUFFER_MULT=2.5)))
    # fewer mouths, so more of the crop reaches the market
    V.append(("w26 s3 lowanim", W(26, 3, TC_COW=3, TC_SHEEP=3,
                                  WHEAT_FEED_BUFFER_MULT=2.5)))

    rng = random.Random(2236068)
    seeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(n)]
    jobs = [(l, p, o, s, st) for l, p in V for o in POOL for s in seeds
            for st in (0, 1)]
    print(f"{len(V)} variants x {len(jobs):,} games", flush=True)
    t0 = time.time()
    with multiprocessing.get_context("forkserver").Pool(workers) as pool:
        res = pool.map(play, jobs, chunksize=4)
    print(f"{time.time() - t0:.0f}s", flush=True)
    errs = [r[7] for r in res if r[7]]
    if errs:
        print(f"{len(errs)} errors; first {errs[0][-250:]}")

    pr, mine, theirs, wh = {}, {}, {}, {}
    for l, o, s, st, us, them, w, e in res:
        if e:
            continue
        pr.setdefault((l, o, s), []).append(us - them)
        mine.setdefault(l, []).append(us)
        theirs.setdefault(l, []).append(them)
        wh.setdefault(l, []).append(w)
    per = {}
    for k, v in pr.items():
        if len(v) == 2:
            per.setdefault(k[0], {})[k[1:]] = sum(v)
    b = per.get("live w8 s21", {})
    print()
    print(f"{'variant':<18} {'paired':>11} {'vs live':>10} {'own':>9} "
          f"{'OPPONENT':>10} {'wheat sold':>11}")
    rows = []
    for lbl, _ in V:
        d = per.get(lbl, {})
        if not d:
            continue
        diffs = [d[k] - b[k] for k in d if k in b]
        dm = statistics.mean(diffs) if diffs else 0.0
        rows.append((lbl, statistics.mean(d.values()), dm,
                     statistics.mean(mine[lbl]), statistics.mean(theirs[lbl]),
                     statistics.mean(wh[lbl])))
    rows.sort(key=lambda r: -r[2])
    for lbl, mm, dm, om, tm, w in rows:
        print(f"{lbl:<18} {mm:>11,.0f} {dm:>+10,.0f} {om:>9,.0f} {tm:>10,.0f} "
              f"{w:>11.0f}")
    print(f"{'TAPE':<18} {5518:>11,} {'':>10} {86119:>9,} {80601:>10,} {605:>11}")


if __name__ == "__main__":
    main()
