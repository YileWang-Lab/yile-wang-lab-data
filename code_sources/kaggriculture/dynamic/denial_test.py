"""The objective was wrong: we already earn what the tape earns.

Measured over 4 opponents x 3 seeds x both seats:

    50-tile planner   own 86,386   opponent 131,522   paired -45,136
    tape              own 86,119   opponent  80,601   paired  +5,518

Our economy is already tape-equivalent -- 0.3% apart on own bank. The entire
gap is that the opponent banks $50,921 MORE against us than against the tape.
Seven scaling experiments, the season-plan transplant and the triage rewrite
were all aimed at making us earn more, which was never the deficit.

The mechanism is market denial. The tape sells 1,621 units to our 1,107 at
$78.4 each against our $109.0, and the books are shared and shallow: from the
10,000 baseline, price hits the $1 floor after roughly 62 STRAWBERRY, 59 WOOL,
76 MILK, 158 MELON. Every unit it sells is a unit of headroom the opponent
cannot sell into. Our higher realised price is therefore a SYMPTOM: we hold
stock behind RESERVE_PRICE waiting for a good quote while the opponent sells
into the book we politely left full.

This sweeps the sell policy from patient to indiscriminate. If denial is the
mechanism, lowering the reserves should RAISE paired margin while LOWERING both
our price per unit and possibly our own bank -- a signature no other hypothesis
tonight predicts.
"""
import importlib.util, json, multiprocessing, os, random, statistics, sys, time

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
        m0, m1 = sim.run_episode(pair[0], pair[1])
        us, them = (m0, m1) if seat == 0 else (m1, m0)
        return (lbl, opp, seed, seat, us, them, None)
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

    V = [("live (patient)", dict(base))]
    for sc in (0.5, 0.25, 0.1, 0.0):
        V.append((f"reserve_x{sc}", {**base, "RESERVE_PRICE_SCALE": sc}))
    # sell everything, every turn, from the first day
    V.append(("dump_all", {**base, "RESERVE_PRICE_SCALE": 0.0,
                           "SHED_PANIC_FRACTION": 0.01}))
    V.append(("dump_all_nofront", {**base, "RESERVE_PRICE_SCALE": 0.0,
                                   "SHED_PANIC_FRACTION": 0.01, "FRONT_RUN": 0}))
    # denial should pair with volume, so also at 74 tiles
    TC = ["TC_COW", "TC_SHEEP", "TC_GOOSE", "TC_MELON", "TC_STRAWBERRY", "TC_WHEAT"]
    t = dict(g); cur = sum(t[k] for k in TC); f = 74 / cur
    for k in TC:
        t[k] = int(round(t[k] * f))
    tc = {k: t[k] for k in TC}
    V.append(("t74_dump_all", {**base, **tc, "RESERVE_PRICE_SCALE": 0.0,
                               "SHED_PANIC_FRACTION": 0.01,
                               "SEED_BATCH_PER_TURN": 16}))

    rng = random.Random(1732051)
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

    pr, mine, theirs = {}, {}, {}
    for l, o, s, st, us, them, e in res:
        if e: continue
        pr.setdefault((l, o, s), []).append(us - them)
        mine.setdefault(l, []).append(us); theirs.setdefault(l, []).append(them)
    per = {}
    for k, v in pr.items():
        if len(v) == 2:
            per.setdefault(k[0], {})[k[1:]] = sum(v)
    b = per.get("live (patient)", {})
    print()
    print(f"{'variant':<20} {'paired margin':>14} {'vs live':>11} {'own bank':>10} "
          f"{'opp bank':>10}")
    rows = []
    for lbl, _ in V:
        d = per.get(lbl, {})
        if not d: continue
        diffs = [d[k] - b[k] for k in d if k in b]
        dm = statistics.mean(diffs) if diffs else 0.0
        rows.append((lbl, statistics.mean(d.values()), dm,
                     statistics.mean(mine[lbl]), statistics.mean(theirs[lbl])))
    rows.sort(key=lambda r: -r[2])
    for lbl, mm, dm, om, tm in rows:
        print(f"{lbl:<20} {mm:>14,.0f} {dm:>+11,.0f} {om:>10,.0f} {tm:>10,.0f}")
    print(f"{'TAPE reference':<20} {5518:>14,} {'':>11} {86119:>10,} {80601:>10,}")


if __name__ == "__main__":
    main()
