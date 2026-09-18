"""Does a portfolio of CYCLING crops close the build/labour gap?

dynamic/attribute.py, re-measured with schedule forcing off, gives the honest
comparison against the tape:

    route   5,190 unit-turns   103 build   826 units   $83,667
    tape    6,914 unit-turns   265 build 1,164 units   $96,293

Labour is 0.75x and build actions are 0.39x. Forcing the tape's labour volume
does not help -- SCHEDULE_DRIVEN=1 reaches 6,890 turns but sends 1,120 of the
extra 1,700 straight to PASS and BANKS $18.5k LESS. The crew is small because
there is no work, not the other way round.

The work comes from build actions, and build comes from crops that CYCLE.
STRAWBERRY is `ongoing`: planted once, it yields on a timer and the tile is
never freed, so it generates watering and nothing else. WHEAT and MELON are not
ongoing -- harvest deletes the plant, the tile empties, and it must be replanted.
Our portfolio is 21 strawberry against 16 cycling tiles, so most of the board
cannot generate build work.

Wheat is also the most turn-efficient source measured, at 0.91 units per upkeep
turn against strawberry's 0.38, and our wheat efficiency already EQUALS the
tape's -- we simply run four times less of it (116 units against 390).

planner/role_gradient.py scored WHEAT+2 at -70,058, but that test compensated
proportionally across every other role. Trading wheat against STRAWBERRY
specifically cost only -1,099 while nearly doubling wheat output, which is a
different experiment. This sweeps the cycling/ongoing balance directly.
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
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    g = json.load(open(os.path.join(ROOT, "planner", "checkpoints",
                                    "best_genome1.json")))["genome"]
    base = to_params(dict(g))
    base["SCHEDULE_DRIVEN"] = 0          # honest baseline; forcing labour was refuted

    def P(**kw):
        p = dict(base); p.update(kw); p["SEED_BATCH_PER_TURN"] = 20
        return p

    variants = [
        ("base(w8,s21)", dict(base)),
        ("w16_s13", P(TC_WHEAT=16, TC_STRAWBERRY=13)),
        ("w24_s5", P(TC_WHEAT=24, TC_STRAWBERRY=5)),
        ("w20_s9_m10", P(TC_WHEAT=20, TC_STRAWBERRY=9, TC_MELON=10)),
        ("w28_s0_m10", P(TC_WHEAT=28, TC_STRAWBERRY=0, TC_MELON=10)),
        # cycling-heavy AND bigger, since more build work may now justify labour
        ("w24_s5_sched", P(TC_WHEAT=24, TC_STRAWBERRY=5, SCHEDULE_DRIVEN=1)),
        ("w30_s6_t66", P(TC_WHEAT=30, TC_STRAWBERRY=6, TC_MELON=10,
                         TC_COW=6, TC_SHEEP=8, TC_GOOSE=6)),
        ("w30_s6_t66_sched", P(TC_WHEAT=30, TC_STRAWBERRY=6, TC_MELON=10,
                               TC_COW=6, TC_SHEEP=8, TC_GOOSE=6, SCHEDULE_DRIVEN=1)),
    ]
    import random
    rng = random.Random(2468)
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
    b = per.get("base(w8,s21)", {})
    print()
    print(f"{'variant':<18} {'paired margin':>14} {'vs base':>10} {'bank':>9} "
          f"{'turns':>7} {'build':>6} {'idle':>6} {'units':>6}")
    print(f"{'TAPE (reference)':<18} {'':>14} {'':>10} {96293:>9,} {6914:>7,} "
          f"{265:>6,} {706:>6,} {1164:>6,}")
    for lbl, params in variants:
        d = per.get(lbl, {})
        if not d: continue
        diffs = [d[k] - b[k] for k in d if k in b]
        dm = statistics.mean(diffs) if diffs else 0.0
        me = _load(DYN, params)
        opp = _load(os.path.join(ROOT, "opponents",
                                 "v111-8c4s-economic-core-premium-lead.py"))
        c, h, r, bank = trace(me, opp, 1009)
        tot = sum(c[k] for k in ("produce", "enable", "build", "logistics",
                                 "move", "waste", "idle"))
        print(f"{lbl:<18} {statistics.mean(d.values()):>14,.0f} {dm:>+10,.0f} "
              f"{statistics.mean(banks[lbl]):>9,.0f} {tot:>7,} {c['build']:>6,} "
              f"{c['idle']:>6,} {sum(h.values()):>6,}")


if __name__ == "__main__":
    main()
