"""Is seed supply the bottleneck behind the idle turns?

dynamic/attribute.py found the labour is identical to the tape's (6,890 vs
6,914 unit-turns) but 1,794 of ours go to PASS against the tape's 706 -- 1,088
wasted turns, 16% of the workforce. It also found WHEAT is by far the most
turn-efficient source at 0.91 units per upkeep turn (strawberry 0.38, animals
0.42), that our wheat efficiency EQUALS the tape's, and that we nonetheless
harvest 116 wheat to its 390.

Wheat is not an ongoing crop: the tile empties at harvest and must be replanted,
which costs a seed. We buy 71 seeds a season against the tape's 199, and
_order_seeds is capped at SEED_BATCH_PER_TURN=6 per turn and by `want`, which
only counts role tiles that are empty RIGHT NOW. If seeds are the binding
constraint then tiles sit empty, there is no task to route a hand to, and the
hand passes -- which is exactly the idle number.

This raises the seed cap alone, holding portfolio and crew fixed, and reports
idle turns and wheat volume next to the margin so the mechanism is visible
rather than inferred from the score.
"""
import collections, importlib.util, json, multiprocessing, os, statistics, sys, time

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
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    g = json.load(open(os.path.join(ROOT, "planner", "checkpoints",
                                    "best_genome1.json")))["genome"]
    base = to_params(dict(g))
    variants = [("base_seed6", dict(base))]
    for sb in (10, 14, 20, 30):
        variants.append((f"seed{sb}", {**base, "SEED_BATCH_PER_TURN": sb}))
    # seeds cost cash; also try relaxing the spend reserve alongside
    variants.append(("seed20_res100", {**base, "SEED_BATCH_PER_TURN": 20,
                                       "SPEND_RESERVE": 100.0}))
    variants.append(("seed20_wheat16", {**base, "SEED_BATCH_PER_TURN": 20,
                                        "TC_WHEAT": 16, "TC_STRAWBERRY": 13}))

    import random
    rng = random.Random(1357)
    seeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(n_seeds)]
    jobs = [(l, p, o, s, seat) for l, p in variants for o in POOL
            for s in seeds for seat in (0, 1)]
    print(f"{len(variants)} variants x {len(POOL)} opp x {n_seeds} seeds x 2 = {len(jobs):,}")
    t0 = time.time()
    with multiprocessing.get_context("forkserver").Pool(workers) as pool:
        res = pool.map(play, jobs, chunksize=4)
    print(f"elapsed {time.time()-t0:.0f}s")
    errs = [r[6] for r in res if r[6]]
    if errs:
        print(f"{len(errs)} errors; first {errs[0][-200:]}")

    pr, banks = {}, {}
    for l, o, s, seat, m, us, e in res:
        if e: continue
        pr.setdefault((l, o, s), []).append(m)
        banks.setdefault(l, []).append(us)
    per = {}
    for k, v in pr.items():
        if len(v) == 2:
            per.setdefault(k[0], {})[k[1:]] = sum(v)
    b = per.get("base_seed6", {})

    # mechanism probe: idle turns and wheat volume on a fixed seed
    print()
    print(f"{'variant':<16} {'paired margin':>14} {'vs base':>10} {'own bank':>10} "
          f"{'idle':>7} {'wheat u':>8} {'build':>7}")
    for lbl, params in variants:
        d = per.get(lbl, {})
        if not d: continue
        diffs = [d[k] - b[k] for k in d if k in b]
        dm = statistics.mean(diffs) if diffs else 0.0
        me = _load(DYN, params)
        opp = _load(os.path.join(ROOT, "opponents",
                                 "v111-8c4s-economic-core-premium-lead.py"))
        c, h, r, bank = trace(me, opp, 1009)
        print(f"{lbl:<16} {statistics.mean(d.values()):>14,.0f} {dm:>+10,.0f} "
              f"{statistics.mean(banks[lbl]):>10,.0f} {c['idle']:>7,} "
              f"{h.get('WHEAT',0):>8,} {c['build']:>7,}")


if __name__ == "__main__":
    main()
