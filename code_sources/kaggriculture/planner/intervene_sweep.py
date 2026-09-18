"""Re-test the shelved market-intervention refinements at 10-20x the sample
size that originally made them ambiguous.

Motivation (measured 2026-08-19 from 80 real ladder games of submission
55600561): our win rate is 78% and the margin distribution is extremely tight
-- 49% of games are decided by under $3,000 on banks of $50k-160k, and ALL 18
losses would flip on a consistent +$6,000. A +$2,000 edge is worth ~12
percentage points of ladder win rate. So refinements worth "only" a few
hundred are worth far more than HANDOFF sections 12/14 credited them.

Those sections shelved three ideas -- structural forecast (IV_STRUCT), staged
dumping (IV_STAGED), price-floor gate (IV_MIN_PRICE) -- each on 24-32 paired
seeds, where the reported effects (+258, -386, +100) sat inside the noise band.
planner.simulate runs ~90 games/sec across 26 workers versus
kaggle_environments' ~0.3/sec/worker, so the same decisions can now be made on
hundreds of paired seeds instead of dozens.

Scoring is PAIRED MARGIN (both seat orders on every seed, summed), per
HANDOFF's rule 1 -- never win rate on same-tape matchups.

Usage:
    /home/yilewang/kagg-env/bin/python -m planner.intervene_sweep --seeds 150
"""
import argparse
import csv
import importlib.util
import multiprocessing
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from planner.simulate import Simulator  # noqa: E402
from route.bake import bake  # noqa: E402

LOG_DIR = os.path.join(ROOT, "logs", "planner")
VARIANT_DIR = os.path.join(ROOT, "agents", "sweep")
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(VARIANT_DIR, exist_ok=True)

# What is live on the ladder right now (submission 55600561, score 2624.1).
SHIPPED = {"_PREEMPT_MIN_FUTURE_QUANTITY": 0, "_PREEMPT_MAX_BATCH": 30,
           "INTERVENE": 1, "IV_DUMP_FRAC": 0.8, "IV_LEAD": 3, "IV_FERT": 1}


def _v(name, **over):
    p = dict(SHIPPED)
    p.update(over)
    return (name, p)


ROUND2 = [
    ("shipped", dict(SHIPPED)),
    # Round 1 (n=800 paired) resolved HANDOFF section 12's "ambiguous" call:
    # struct is +276 at t=8.3, not noise. slot_first is -327 (t=-10.8) and
    # lead 2/4 are both negative, so lead=3 is confirmed optimal.
    _v("struct", IV_STRUCT=1),
    _v("struct_d70", IV_STRUCT=1, IV_DUMP_FRAC=0.7),
    _v("struct_d75", IV_STRUCT=1, IV_DUMP_FRAC=0.75),
    _v("struct_mp20", IV_STRUCT=1, IV_MIN_PRICE=0.20),
    _v("struct_d70_mp20", IV_STRUCT=1, IV_DUMP_FRAC=0.7, IV_MIN_PRICE=0.20),
    _v("struct_d75_mp10", IV_STRUCT=1, IV_DUMP_FRAC=0.75, IV_MIN_PRICE=0.10),
    _v("d70", IV_DUMP_FRAC=0.7),
]

VARIANTS = [
    ("shipped", dict(SHIPPED)),
    # HANDOFF section 12: +258 field mean / -29 direct at n=32. Ambiguous.
    _v("struct", IV_STRUCT=1),
    # HANDOFF section 14: +100 at 12/24 wins -- exactly chance.
    _v("minprice_10", IV_MIN_PRICE=0.10),
    _v("minprice_20", IV_MIN_PRICE=0.20),
    # Order-slot position. intervene.py argues this is safe in the direction
    # that matters but it is shipped at 0; never measured at size.
    _v("slot_first", IV_SLOT_FIRST=1),
    # Combinations of the two that individually looked positive.
    _v("struct_minprice", IV_STRUCT=1, IV_MIN_PRICE=0.10),
    _v("struct_slotfirst", IV_STRUCT=1, IV_SLOT_FIRST=1),
    # Dump fraction was tuned at n=40 (HANDOFF section 6). Re-check the
    # neighbourhood at size now that it is cheap.
    _v("dump_70", IV_DUMP_FRAC=0.7),
    _v("dump_90", IV_DUMP_FRAC=0.9),
    _v("lead_2", IV_LEAD=2),
    _v("lead_4", IV_LEAD=4),
]

# Round 2 winner (n=1440 paired, t=18.7, better on 70.7% of seeds).
BEST2 = {"IV_STRUCT": 1, "IV_DUMP_FRAC": 0.7, "IV_MIN_PRICE": 0.20}

# Round 3: WHICH products should the layer dump at all?
# planner/analyze_top.py on 23 real replays showed our live submission
# realising STRAWBERRY at $60/unit and MILK at $70/unit where plain kawa --
# running the identical tape -- gets $200 and $152, while our WOOL comes in at
# $217 against kawa's $155. That comparison is confounded (the leaders'
# replays are their biggest wins, i.e. weak opponents and low market
# pressure), so the hypothesis "the dump list is wrong, not just its
# parameters" is tested here under controlled common-random-number conditions
# instead of being read off the replays.
_ALL5 = ("MELON", "MILK", "STRAWBERRY", "WOOL", "FERTILIZER")


def _v3(name, items):
    p = dict(SHIPPED)
    p.update(BEST2)
    p["IV_ITEMS"] = items
    return (name, p)


ROUND3 = [
    ("shipped", dict(SHIPPED)),
    ("best2_all5", {**SHIPPED, **BEST2}),
    _v3("no_strawberry", ("MELON", "MILK", "WOOL", "FERTILIZER")),
    _v3("no_milk", ("MELON", "STRAWBERRY", "WOOL", "FERTILIZER")),
    _v3("no_straw_milk", ("MELON", "WOOL", "FERTILIZER")),
    _v3("wool_only", ("WOOL",)),
    _v3("wool_fert", ("WOOL", "FERTILIZER")),
    _v3("wool_melon_fert", ("MELON", "WOOL", "FERTILIZER")),
    _v3("no_fert", ("MELON", "MILK", "STRAWBERRY", "WOOL")),
    _v3("add_wheat", _ALL5 + ("WHEAT",)),
    _v3("add_egg_wheat", _ALL5 + ("WHEAT", "EGG")),
]

# Round 3 refuted the item-set hypothesis (no_strawberry +496 vs unchanged +495),
# so the shipped item set stands. BEST3 is what is now live as submission 55612771.
BEST3 = {**BEST2}


def _v4(name, **over):
    p = dict(SHIPPED)
    p.update(BEST3)
    p.update(over)
    return (name, p)


# Round 4: the base TAPE's own preempt constants. HANDOFF searched these via PBT
# but section 5 records that PBT scored variants on 12 games, "so noise dominated
# and 10 rounds of optimisation moved backwards". They have never been measured
# with common random numbers at this sample size. _PREEMPT_MAX_CLONE_DISTANCE is
# the interesting one: section 6 found kawa's preemption is fully armed against us
# because our clone distance is 0, and raising OUR gate changes when we fire.
ROUND4 = [
    ("live_55612771", dict({**SHIPPED, **BEST3})),
    _v4("mp15", IV_MIN_PRICE=0.15),
    _v4("mp25", IV_MIN_PRICE=0.25),
    _v4("mp30", IV_MIN_PRICE=0.30),
    _v4("d65", IV_DUMP_FRAC=0.65),
    _v4("d60", IV_DUMP_FRAC=0.60),
    _v4("staged", IV_STAGED=1),
    _v4("pf_batch40", _PREEMPT_MAX_BATCH=40),
    _v4("pf_batch20", _PREEMPT_MAX_BATCH=20),
    _v4("pf_frac2", _PREEMPT_FRACTION=2.0),
    _v4("pf_clone40", _PREEMPT_MAX_CLONE_DISTANCE=40),
    _v4("pf_start0", _PREEMPT_START=0),
    _v4("pf_ratio10", _PREEMPT_MIN_PRICE_RATIO=0.10),
    _v4("pf_stop700", _PREEMPT_STOP=700),
]

# Round 5: SEAT-CONDITIONAL play. Rounds 1-4 tuned parameters that apply
# identically from both seats. Seat is not neutral -- HANDOFF section 5 measured
# two byte-identical agents splitting 6/40 against seat 0, and our own live
# ladder record has the same shape (seat0 34/46 = 74%, seat1 29/35 = 83%).
# section 14 called this "not fixable from the agent side", but the seat IS
# readable at runtime from obs["player"], so the layer can simply play
# differently from the disadvantaged seat. Nothing in HANDOFF tries this.
def _v5(name, **over):
    p = dict(SHIPPED)
    p.update(BEST3)
    p.update(over)
    return (name, p)


ROUND5 = [
    ("live_55612771", dict({**SHIPPED, **BEST3})),
    _v5("s0_dump90", IV_SEAT0_DUMP=0.90),
    _v5("s0_dump100", IV_SEAT0_DUMP=1.00),
    _v5("s0_mp05", IV_SEAT0_MINPRICE=0.05),
    _v5("s0_mp00", IV_SEAT0_MINPRICE=0.0),
    _v5("s0_dump90_mp05", IV_SEAT0_DUMP=0.90, IV_SEAT0_MINPRICE=0.05),
    _v5("s0_dump100_mp00", IV_SEAT0_DUMP=1.00, IV_SEAT0_MINPRICE=0.0),
    _v5("s0_dump50", IV_SEAT0_DUMP=0.50),
    _v5("s0_mp35", IV_SEAT0_MINPRICE=0.35),
    _v5("s0_dump50_mp35", IV_SEAT0_DUMP=0.50, IV_SEAT0_MINPRICE=0.35),
]

# Round 6: SELL SUPPRESSION -- the first lever that trades volume for price.
# Every layer to date only adds sales. analyze_top.py measured us as the
# highest-volume lowest-price seller on the ladder (1,813 units @ $80.4 vs
# ReCurSiON's 1,404 @ $129.6), and rounds 4-5 showed the parameter space of
# the ADD-side is exhausted, so this is the remaining structural direction.
def _v6(name, **over):
    p = dict(SHIPPED)
    p.update(BEST3)
    p.update(over)
    return (name, p)


ROUND6 = [
    ("live_55612771", dict({**SHIPPED, **BEST3})),
    _v6("hold10", IV_HOLD_RATIO=0.10),
    _v6("hold20", IV_HOLD_RATIO=0.20),
    _v6("hold30", IV_HOLD_RATIO=0.30),
    _v6("hold40", IV_HOLD_RATIO=0.40),
    _v6("hold20_shed85", IV_HOLD_RATIO=0.20, IV_HOLD_SHED_MAX=85),
    _v6("hold20_shed55", IV_HOLD_RATIO=0.20, IV_HOLD_SHED_MAX=55),
    _v6("hold20_stop500", IV_HOLD_RATIO=0.20, IV_HOLD_STOP_STEP=500),
    _v6("hold20_stop660", IV_HOLD_RATIO=0.20, IV_HOLD_STOP_STEP=660),
    _v6("hold30_shed85", IV_HOLD_RATIO=0.30, IV_HOLD_SHED_MAX=85),
]

OPPONENTS = [
    "kaggriculture-multi-route-farming-agent",       # kawa -- the hardest, and the tape we run
    "v111-8c4s-economic-core-premium-lead",
    "kaggriculture-frontier-the-soil-remembers-rain",
    "kaggriculture-3000-socre",
]

ROUND2_OPPONENTS = OPPONENTS + [
    "kaggriculture-breaking-the-tie-2883-score",
    "kaggriculture-rank-your-agent",
    "15-16-strict-future-v25-meta-reset",
    "strong-barnyard-economist",
    "kaggriculture-pure-architecture-2600-elo-v3",
]

_n = [0]
_cache = {}


def _load_path(path, tag):
    _n[0] += 1
    spec = importlib.util.spec_from_file_location(f"{tag}_{os.getpid()}_{_n[0]}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, "_submission_entry", None) or mod.agent


def play(job):
    variant, vpath, opp_name, seed, seat = job
    try:
        me = _load_path(vpath, "v")
        opp = _load_path(os.path.join(ROOT, "opponents", f"{opp_name}.py"), "o")
        pair = [me, opp] if seat == 0 else [opp, me]
        sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
        m0, m1 = sim.run_episode(pair[0], pair[1])
        us, them = (m0, m1) if seat == 0 else (m1, m0)
        return (variant, opp_name, seed, seat, us - them, None)
    except Exception:
        import traceback
        return (variant, opp_name, seed, seat, 0.0, traceback.format_exc()[-300:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=150)
    ap.add_argument("--workers", type=int, default=26)
    ap.add_argument("--round", type=int, default=1)
    args = ap.parse_args()

    global VARIANTS, OPPONENTS
    if args.round == 2:
        VARIANTS = ROUND2
        OPPONENTS = ROUND2_OPPONENTS
    elif args.round == 3:
        VARIANTS = ROUND3
        OPPONENTS = ROUND2_OPPONENTS
    elif args.round == 4:
        VARIANTS = ROUND4
        OPPONENTS = ROUND2_OPPONENTS
    elif args.round == 5:
        VARIANTS = ROUND5
        OPPONENTS = ROUND2_OPPONENTS
    elif args.round == 6:
        VARIANTS = ROUND6
        OPPONENTS = ROUND2_OPPONENTS

    import random
    rng = random.Random(4242)
    seeds = [rng.randrange(10**6, 2**31 - 1) for _ in range(args.seeds)]

    paths = {}
    for name, params in VARIANTS:
        p = os.path.join(VARIANT_DIR, f"sweep_{name}.py")
        bake(params, out=p, note=f"sweep variant {name}")
        paths[name] = p
    print(f"baked {len(paths)} variants")

    jobs = []
    for name, _ in VARIANTS:
        for opp in OPPONENTS:
            for s in seeds:
                for seat in (0, 1):
                    jobs.append((name, paths[name], opp, s, seat))
    print(f"{len(VARIANTS)} variants x {len(OPPONENTS)} opponents x {len(seeds)} seeds x 2 seats "
          f"= {len(jobs):,} games")

    t0 = time.time()
    with multiprocessing.get_context("forkserver").Pool(args.workers) as pool:
        res = pool.map(play, jobs, chunksize=8)
    elapsed = time.time() - t0
    print(f"elapsed {elapsed:.0f}s ({len(jobs)/elapsed:.0f} games/s)")

    errs = [r for r in res if r[5]]
    if errs:
        print(f"{len(errs)} errors; first:\n{errs[0][5]}")

    # paired margin: sum both seats for the same (variant, opponent, seed)
    paired = {}
    for variant, opp, seed, seat, margin, err in res:
        if err:
            continue
        paired.setdefault((variant, opp, seed), []).append(margin)

    per_variant = {}
    per_variant_opp = {}
    for (variant, opp, seed), ms in paired.items():
        if len(ms) != 2:
            continue
        pm = sum(ms)
        per_variant.setdefault(variant, []).append(pm)
        per_variant_opp.setdefault((variant, opp), []).append(pm)

    base_by_key = {k: v for k, v in per_variant.items()}
    base_mean = statistics.mean(base_by_key.get(VARIANTS[0][0], [0.0]))

    # Per-(opponent, seed) paired difference against `shipped`. Every variant
    # plays the identical seed set against the identical opponents, so
    # differencing on the shared key cancels seed and opponent variance --
    # common random numbers. Without this the seed-to-seed spread (sd ~ 20k)
    # completely swamps the few-hundred effects being measured; with it the
    # relevant noise is only the variant's own behavioural difference.
    shipped_by_key = {}
    for (variant, opp, seed), ms in paired.items():
        if variant == VARIANTS[0][0] and len(ms) == 2:
            shipped_by_key[(opp, seed)] = sum(ms)

    ts = time.strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(LOG_DIR, f"intervene_sweep_{ts}.csv")
    rows = []
    for name, _ in VARIANTS:
        ms = per_variant.get(name, [])
        if not ms:
            continue
        diffs = []
        for (variant, opp, seed), pair_ms in paired.items():
            if variant != name or len(pair_ms) != 2:
                continue
            b = shipped_by_key.get((opp, seed))
            if b is not None:
                diffs.append(sum(pair_ms) - b)
        mean = statistics.mean(ms)
        dmean = statistics.mean(diffs) if diffs else 0.0
        dsd = statistics.pstdev(diffs) if len(diffs) > 1 else 0.0
        dse = dsd / (len(diffs) ** 0.5) if diffs else 0.0
        dwins = sum(1 for d in diffs if d > 0) / len(diffs) if diffs else 0.0
        rows.append((name, len(ms), mean, dmean, dse, dwins))

    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["variant", "n_paired", "paired_margin_mean", "delta_vs_shipped",
                    "delta_stderr", "frac_seeds_better_than_shipped"])
        for r in rows:
            w.writerow([r[0], r[1], f"{r[2]:.1f}", f"{r[3]:.1f}", f"{r[4]:.1f}", f"{r[5]:.3f}"])

    rows.sort(key=lambda r: -r[3])
    print()
    print("delta vs shipped is a PAIRED difference on identical (opponent, seed) pairs.")
    print(f"{'variant':<20} {'n':>5} {'paired_margin':>14} {'vs shipped':>12} {'+/-se':>8} {'t':>7} {'better%':>8}")
    for name, n, mean, dmean, dse, dwins in rows:
        t = (dmean / dse) if dse > 0 else 0.0
        print(f"{name:<20} {n:>5} {mean:>14,.0f} {dmean:>12,.0f} {dse:>8,.0f} {t:>7.1f} {dwins:>8.1%}")

    print()
    print("per-opponent for the top variants:")
    top = [r[0] for r in rows[:4]]
    print(f"{'variant':<20} " + " ".join(f"{o[:18]:>19}" for o in OPPONENTS))
    for name in [VARIANTS[0][0]] + [t for t in top if t != VARIANTS[0][0]]:
        cells = []
        for opp in OPPONENTS:
            ms = per_variant_opp.get((name, opp), [])
            cells.append(f"{statistics.mean(ms):>19,.0f}" if ms else f"{'-':>19}")
        print(f"{name:<20} " + " ".join(cells))

    with open(os.path.join(LOG_DIR, "planner_progress.log"), "a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} intervene_sweep seeds={args.seeds} "
                f"games={len(jobs)} best={rows[0][0]} delta={rows[0][4]:+.0f} csv={csv_path}\n")
    print(f"\ncsv: {csv_path}")


if __name__ == "__main__":
    main()
