"""Is adaptive dump sizing worth anything, or is it just "dump more"?

The fixed 70% fraction ignores market depth, which differs by two orders of
magnitude: the 80th unit sold returns 75% of base for MELON and 84% for
FERTILIZER/EGG/WHEAT, but 1% for WOOL, MILK and STRAWBERRY. So a single
fraction is wrong in both directions at once.

_iv_optimal_qty replaces it with the engine's own price curve (inlined and
verified to match market_price exactly at every probe) plus the opponent's sale
VOLUME, which _iv_observe already infers and previously discarded. Unit k is
worth p(inv+k) now against p(inv+opp_vol+k) after their block lands.

A first pass on 45 ladder replays put the best floor at +31 (t=0.5) -- inside
noise, and under-powered: one of three new parameters, on a small sample.

THE CONTROL THAT MATTERS. At floor 0.25-0.55 the adaptive sizer dumps MORE than
70% on the deep products (60 units against 42) and only restricts the shallow
ones once floor >= 0.70. So any small gain could simply be "dump more", with the
price curve contributing nothing. Fixed fractions of 0.8/0.9/1.0 are therefore
measured alongside: if they match the adaptive variants, the machinery is
decoration and should not ship.
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

V = [("live_d70", dict(B0))]
# CONTROL: plain fixed fractions. If these match the adaptive rows, the curve
# and the opponent-volume signal are contributing nothing.
for f in (0.80, 0.90, 1.00):
    V.append((f"fixed_d{int(f*100)}", {**B0, "IV_DUMP_FRAC": f}))
# adaptive, floor swept across the range where it goes from "more" to "less"
for f in (0.30, 0.45, 0.60, 0.75):
    V.append((f"adapt_f{int(f*100)}", {**B0, "IV_ADAPT": 1, "IV_MARGINAL_FLOOR": f}))
# the other two new knobs, at the best-looking floor
for vm in (0.5, 2.0):
    V.append((f"adapt_f45_vol{vm}", {**B0, "IV_ADAPT": 1, "IV_MARGINAL_FLOOR": 0.45,
                                     "IV_VOL_MULT": vm}))
for mq in (30, 100):
    V.append((f"adapt_f45_max{mq}", {**B0, "IV_ADAPT": 1, "IV_MARGINAL_FLOOR": 0.45,
                                     "IV_MAX_QTY": mq}))
_n = [0]


def _load(p):
    _n[0] += 1
    s = importlib.util.spec_from_file_location(f"as_{os.getpid()}_{_n[0]}", p)
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
        q = os.path.join(ROOT, "agents", "adapt", f"{lbl}.py")
        os.makedirs(os.path.dirname(q), exist_ok=True)
        bake(p, out=q, note=lbl); paths[lbl] = q
    rng = random.Random(31415)
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
    b = per.get("live_d70", {})
    print()
    print(f"{'variant':<20} {'n':>5} {'paired margin':>14} {'vs live_d70':>13} "
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
        tag = "  <-- CONTROL" if lbl.startswith("fixed_") else ""
        print(f"{lbl:<20} {nn:>5} {mm:>14,.0f} {dm:>+13,.0f} {dse:>7,.0f} {t:>6.1f} "
              f"{wr:>6.1%}{tag}")


if __name__ == "__main__":
    main()
