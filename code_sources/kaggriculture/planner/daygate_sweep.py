"""Test the endgame hypothesis: does our own late dumping cost us won games?

Ladder loss forensics (planner-side, 7 struct losses vs 7 struct wins, replay
margin traced per day) found the losses are ENDGAME collapses, not early
deficits. In 4 of the 7 we led by +6,900 to +9,400 at day 15 and lost all of it
by day 29; every win grew monotonically over the same window. Mean swing from
day 15 to day 29 is -4,400 in losses against +10,551 in wins.

HANDOFF section 14 names the mechanism -- "front-running only pays while there
is a price to win; at the floor both players clear at the same few dollars" --
and IV_MIN_PRICE was tested against it, landing at +100 on 12 of 24 seeds, i.e.
chance. But that was a season-long field mean, and a gate that only bites after
day 20 is diluted by the twenty days where it changes nothing. That is exactly
the shape a mean would hide, so this sweeps a DAY gate instead and additionally
reports the late-window margin swing, not just the final margin.
"""
import importlib.util, multiprocessing, os, random, statistics, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from planner.simulate import Simulator  # noqa: E402
from route.bake import bake  # noqa: E402

LIVE = {"_PREEMPT_MIN_FUTURE_QUANTITY": 0, "_PREEMPT_MAX_BATCH": 30,
        "INTERVENE": 1, "IV_DUMP_FRAC": 0.7, "IV_LEAD": 3, "IV_FERT": 1,
        "IV_STRUCT": 1, "IV_MIN_PRICE": 0.20}
DEF = ["6c12s_4q_first_yarn", "6c12s_4q_second_yarn", "6c8s_3q", "10c4s_3q", "8c6s_3q"]
B0 = {**LIVE, "TAPE_MAP": ["6c12s_4q_second_yarn"] + DEF[1:]}
POOL = ["kaggriculture-multi-route-farming-agent",
        "v111-8c4s-economic-core-premium-lead",
        "kaggriculture-frontier-the-soil-remembers-rain",
        "kaggriculture-3000-socre",
        "kaggriculture-breaking-the-tie-2883-score",
        "kaggriculture-rank-your-agent",
        "15-16-strict-future-v25-meta-reset",
        "strong-barnyard-economist",
        "kaggriculture-pure-architecture-2600-elo-v3"]
VARIANTS = [("live", dict(B0))]
for sd in (16, 18, 20, 22, 24, 26):
    VARIANTS.append((f"stop{sd}", {**B0, "IV_STOP_DAY": sd}))
for sd, ld in ((20, 0.3), (22, 0.3), (20, 0.5), (24, 0.4)):
    VARIANTS.append((f"stop{sd}_late{int(ld*100)}", {**B0, "IV_STOP_DAY": sd, "IV_LATE_DUMP": ld}))
_n = [0]


def _load(p):
    _n[0] += 1
    s = importlib.util.spec_from_file_location(f"dg_{os.getpid()}_{_n[0]}", p)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return getattr(m, "_submission_entry", None) or m.agent


def play(job):
    lbl, path, opp, seed, seat = job
    try:
        me = _load(path); op = _load(os.path.join(ROOT, "opponents", f"{opp}.py"))
        pair = [me, op] if seat == 0 else [op, me]
        sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
        marks = {}

        def probe(o):
            d = int(o.get("day", 0))
            if d in (15, 29) and d not in marks:
                f = o["farms"]
                marks[d] = f[seat]["money"] - f[1 - seat]["money"]
        me2 = (lambda o: (probe(o), me(o))[1])
        pair = [me2, op] if seat == 0 else [op, me2]
        m0, m1 = sim.run_episode(pair[0], pair[1])
        us, them = (m0, m1) if seat == 0 else (m1, m0)
        return (lbl, opp, seed, seat, us - them, marks.get(15, 0.0), None)
    except Exception:
        import traceback
        return (lbl, opp, seed, seat, 0.0, 0.0, traceback.format_exc()[-200:])


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    paths = {}
    for lbl, p in VARIANTS:
        q = os.path.join(ROOT, "agents", "daygate", f"{lbl}.py")
        os.makedirs(os.path.dirname(q), exist_ok=True)
        bake(p, out=q, note=f"daygate {lbl}"); paths[lbl] = q
    rng = random.Random(90210)
    seeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(n)]
    jobs = [(l, paths[l], o, s, seat) for l, _ in VARIANTS
            for o in POOL for s in seeds for seat in (0, 1)]
    print(f"{len(VARIANTS)} variants x {len(POOL)} opp x {n} seeds x 2 = {len(jobs):,} games")
    t0 = time.time()
    with multiprocessing.get_context("forkserver").Pool(workers) as pool:
        res = pool.map(play, jobs, chunksize=4)
    print(f"elapsed {time.time()-t0:.0f}s")
    errs = [r[6] for r in res if r[6]]
    if errs:
        print(f"{len(errs)} errors; first {errs[0][-200:]}")

    pr, d15 = {}, {}
    for lbl, opp, seed, seat, m, m15, err in res:
        if err: continue
        pr.setdefault((lbl, opp, seed), []).append(m)
        d15.setdefault((lbl, opp, seed), []).append(m15)
    per, per15 = {}, {}
    for k, v in pr.items():
        if len(v) == 2:
            per.setdefault(k[0], {})[k[1:]] = sum(v)
            per15.setdefault(k[0], {})[k[1:]] = sum(d15[k])
    b = per.get("live", {}); b15 = per15.get("live", {})
    print()
    print(f"{'variant':<18} {'final margin':>14} {'vs live':>10} {'+/-se':>7} {'t':>6} "
          f"{'win%':>7} {'d15->end swing':>15}")
    rows = []
    for lbl, _ in VARIANTS:
        d = per.get(lbl, {})
        if not d: continue
        diffs = [d[k] - b[k] for k in d if k in b]
        dm = statistics.mean(diffs) if diffs else 0.0
        dse = (statistics.pstdev(diffs) / len(diffs) ** 0.5) if len(diffs) > 1 else 0.0
        sw = statistics.mean([d[k] - per15[lbl][k] for k in d if k in per15.get(lbl, {})])
        rows.append((lbl, statistics.mean(d.values()), dm, dse, dm / dse if dse else 0.0,
                     sum(1 for v in d.values() if v > 0) / len(d), sw))
    rows.sort(key=lambda r: -r[2])
    for lbl, mm, dm, dse, t, wr, sw in rows:
        print(f"{lbl:<18} {mm:>14,.0f} {dm:>+10,.0f} {dse:>7,.0f} {t:>6.1f} {wr:>6.1%} {sw:>+15,.0f}")


if __name__ == "__main__":
    main()
