"""Concentrate the dump on the DEEP markets only.

planner/frontrun_audit.py (144 games, every firing tracked against the
opponent's recovered sales) settles the timing question: we clear ahead of them
on 94-99% of firings, and same-step collisions -- which the engine prices
identically for both players -- are rare. Position is not the problem.

The realised prices are, and they sort exactly by market depth:

    FERTILIZER  493 units to floor   we get +1.1 per unit
    MELON       158                            +24.3
    MILK         76                             -2.8
    STRAWBERRY   62                             -2.1
    WOOL         59                             -2.2

Dumping a block into a shallow book walks our OWN later units down; the town
then drains, the price recovers, and the opponent sells into the recovery above
our average. We take the whole price impact and hand them the rebound.

intervene_sweep round 3 already tested REMOVING items (no_strawberry, no_milk,
wool_fert, ...) and found all 11 variants within +/-120 of each other, so this
is not a rerun of that: the audit predicts something narrower and untested --
that the dump should be CONCENTRATED on the two deep books rather than trimmed
from the shallow ones. Fixed item sets are included as controls so a win cannot
be confused with simply firing less often.
"""
import importlib.util, multiprocessing, os, random, statistics, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from planner.simulate import Simulator  # noqa: E402
from route.bake import bake  # noqa: E402

LIVE = {"_PREEMPT_MIN_FUTURE_QUANTITY": 0, "_PREEMPT_MAX_BATCH": 30, "INTERVENE": 1,
        "IV_DUMP_FRAC": 0.7, "IV_LEAD": 3, "IV_FERT": 1, "IV_STRUCT": 1,
        "IV_MIN_PRICE": 0.20}
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

ALL5 = ("MELON", "MILK", "STRAWBERRY", "WOOL", "FERTILIZER")
V = [
    ("live_all5", dict(B0)),
    ("deep_melon_fert", {**B0, "IV_ITEMS": ("MELON", "FERTILIZER")}),
    ("melon_only", {**B0, "IV_ITEMS": ("MELON",)}),
    ("fert_only", {**B0, "IV_ITEMS": ("FERTILIZER",)}),
    ("deep3_add_wheat", {**B0, "IV_ITEMS": ("MELON", "FERTILIZER", "WHEAT")}),
    ("deep4_add_egg", {**B0, "IV_ITEMS": ("MELON", "FERTILIZER", "WHEAT", "EGG")}),
    # controls: the shallow books alone, and the complement of the deep set
    ("shallow_only", {**B0, "IV_ITEMS": ("MILK", "STRAWBERRY", "WOOL")}),
    # deep books at a bigger fraction, since depth is what tolerates volume
    ("deep_d100", {**B0, "IV_ITEMS": ("MELON", "FERTILIZER"), "IV_DUMP_FRAC": 1.0}),
    ("deep_d90_shallow_off", {**B0, "IV_ITEMS": ("MELON", "FERTILIZER"),
                              "IV_DUMP_FRAC": 0.9}),
]
_n = [0]


def _load(p):
    _n[0] += 1
    s = importlib.util.spec_from_file_location(f"di_{os.getpid()}_{_n[0]}", p)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return getattr(m, "_submission_entry", None) or m.agent


def play(job):
    lbl, path, opp, seed, seat = job
    try:
        me = _load(path); op = _load(os.path.join(ROOT, "opponents", f"{opp}.py"))
        pair = [me, op] if seat == 0 else [op, me]
        sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
        m0, m1 = sim.run_episode(pair[0], pair[1])
        us, them = (m0, m1) if seat == 0 else (m1, m0)
        return (lbl, opp, seed, seat, us - them, None)
    except Exception:
        import traceback
        return (lbl, opp, seed, seat, 0.0, traceback.format_exc()[-200:])


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 90
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 26
    paths = {}
    for lbl, p in V:
        q = os.path.join(ROOT, "agents", "depth", f"{lbl}.py")
        os.makedirs(os.path.dirname(q), exist_ok=True)
        bake(p, out=q, note=lbl); paths[lbl] = q
    rng = random.Random(271828)
    seeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(n)]
    jobs = [(l, paths[l], o, s, seat) for l, _ in V for o in POOL
            for s in seeds for seat in (0, 1)]
    print(f"{len(V)} variants x {len(POOL)} opp x {n} seeds x 2 = {len(jobs):,} games", flush=True)
    t0 = time.time()
    with multiprocessing.get_context("forkserver").Pool(workers) as pool:
        res = pool.map(play, jobs, chunksize=4)
    print(f"elapsed {time.time()-t0:.0f}s", flush=True)
    errs = [r[5] for r in res if r[5]]
    if errs:
        print(f"{len(errs)} errors; first {errs[0][-200:]}")
    pr = {}
    for l, o, s, seat, m, e in res:
        if not e:
            pr.setdefault((l, o, s), []).append(m)
    per = {}
    for k, v in pr.items():
        if len(v) == 2:
            per.setdefault(k[0], {})[k[1:]] = sum(v)
    b = per.get("live_all5", {})
    print()
    print(f"{'variant':<22} {'n':>5} {'paired margin':>14} {'vs live':>10} "
          f"{'+/-se':>7} {'t':>6} {'win%':>7}")
    rows = []
    for lbl, _ in V:
        d = per.get(lbl, {})
        if not d: continue
        diffs = [d[k] - b[k] for k in d if k in b]
        dm = statistics.mean(diffs) if diffs else 0.0
        dse = (statistics.pstdev(diffs) / len(diffs) ** 0.5) if len(diffs) > 1 else 0.0
        rows.append((lbl, len(d), statistics.mean(d.values()), dm, dse,
                     dm / dse if dse else 0.0,
                     sum(1 for v in d.values() if v > 0) / len(d)))
    rows.sort(key=lambda r: -r[3])
    for lbl, nn, mm, dm, dse, t, wr in rows:
        print(f"{lbl:<22} {nn:>5} {mm:>14,.0f} {dm:>+10,.0f} {dse:>7,.0f} {t:>6.1f} {wr:>6.1%}")


if __name__ == "__main__":
    main()
