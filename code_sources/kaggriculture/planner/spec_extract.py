"""Aggregate the tape's decompiled schedule across many seeds into a
PLANNER SPECIFICATION: the concrete, measurable targets our from-scratch
planner has to hit.

Answers "can the tape be turned back into a reference for the planner?" --
instead of a scalar fitness to minimise, this produces per-metric targets
(labour, throughput, unit price realised, product mix) with the gap on each,
so the planner work becomes "close these specific numbers".

Usage:
    /home/yilewang/kagg-env/bin/python -m planner.spec_extract --seeds 24
"""
import argparse
import collections
import json
import multiprocessing
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from planner.decompile import load_agent, trace, totals  # noqa: E402

LOG_DIR = os.path.join(ROOT, "logs", "planner")
os.makedirs(LOG_DIR, exist_ok=True)

GENOME = os.path.join(ROOT, "planner", "checkpoints", "best_genome1.json")
OPPONENTS = ["v111", "frontier"]


def job(args):
    who, opp, seed = args
    try:
        ag = load_agent(who, genome_path=GENOME)
        op = load_agent(opp)
        days, mine, theirs = trace(ag, op, seed)
        t = totals(days)
        turns = sum(d["unit_turns"] for d in days.values())
        ops = sum(sum(d["ops"].values()) for d in days.values())
        moves = sum(d["moves"] for d in days.values())
        passes = sum(d["passes"] for d in days.values())
        peak_hands = max((d.get("end_hands", 0) for d in days.values()), default=0)
        return {
            "who": who, "opp": opp, "seed": seed, "money": mine, "opp_money": theirs,
            "hires": t["hires"], "land": t["land"],
            "unit_turns": turns, "ops": ops, "moves": moves, "passes": passes,
            "peak_hands": peak_hands,
            "sold": dict(t["sold_real"]), "revenue": dict(t["revenue_real"]),
            "spend": sum(t["spent_real"].values()),
            "op_counts": dict(t["ops"]),
            "err": None,
        }
    except Exception:
        import traceback
        return {"who": who, "opp": opp, "seed": seed, "err": traceback.format_exc()[-300:]}


def agg(rows, key):
    vals = [r[key] for r in rows if r.get("err") is None]
    return statistics.mean(vals) if vals else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=24)
    ap.add_argument("--workers", type=int, default=13)
    args = ap.parse_args()

    import random
    rng = random.Random(99)
    seeds = [rng.randrange(10**6, 2**31 - 1) for _ in range(args.seeds)]

    jobs = [(who, opp, s) for who in ("kawa", "route") for opp in OPPONENTS for s in seeds]
    print(f"{len(jobs)} traces ({args.seeds} seeds x {len(OPPONENTS)} opponents x 2 agents)")
    t0 = time.time()
    with multiprocessing.get_context("forkserver").Pool(args.workers) as pool:
        res = pool.map(job, jobs)
    print(f"elapsed {time.time()-t0:.0f}s")

    errs = [r for r in res if r.get("err")]
    if errs:
        print(f"{len(errs)} errors; first:\n{errs[0]['err']}")
    res = [r for r in res if not r.get("err")]

    K = [r for r in res if r["who"] == "kawa"]
    R = [r for r in res if r["who"] == "route"]

    print(f"\n{'='*92}")
    print(f"PLANNER SPECIFICATION -- targets extracted from the tape ({len(K)} kawa traces, {len(R)} route traces)")
    print(f"{'='*92}")
    print(f"{'metric':<34} {'kawa (target)':>16} {'route (ours)':>16} {'gap':>14} {'ratio':>8}")

    def line(name, k, r, fmt=",.0f"):
        gap = r - k
        ratio = (r / k) if k else 0.0
        print(f"{name:<34} {format(k, fmt):>16} {format(r, fmt):>16} {format(gap, '+,.0f'):>14} {ratio:>7.2f}x")

    line("final money", agg(K, "money"), agg(R, "money"))
    line("total realised revenue",
         statistics.mean([sum(r["revenue"].values()) for r in K]),
         statistics.mean([sum(r["revenue"].values()) for r in R]))
    line("total spend", agg(K, "spend"), agg(R, "spend"))
    print()
    line("LABOUR: total hires", agg(K, "hires"), agg(R, "hires"))
    line("LABOUR: peak hands", agg(K, "peak_hands"), agg(R, "peak_hands"), ".1f")
    line("LABOUR: unit-turns available", agg(K, "unit_turns"), agg(R, "unit_turns"))
    line("THROUGHPUT: useful ops", agg(K, "ops"), agg(R, "ops"))
    ko, ru = agg(K, "ops") / max(agg(K, "unit_turns"), 1), agg(R, "ops") / max(agg(R, "unit_turns"), 1)
    print(f"{'THROUGHPUT: useful-op rate':<34} {ko:>15.1%} {ru:>16.1%} {ru-ko:>+13.1%}")
    line("  moves", agg(K, "moves"), agg(R, "moves"))
    line("  passes", agg(K, "passes"), agg(R, "passes"))
    print()

    ku = statistics.mean([sum(r["sold"].values()) for r in K])
    ru_ = statistics.mean([sum(r["sold"].values()) for r in R])
    line("MARKET: total units sold", ku, ru_)
    kr = statistics.mean([sum(r["revenue"].values()) for r in K])
    rr = statistics.mean([sum(r["revenue"].values()) for r in R])
    print(f"{'MARKET: avg $ / unit sold':<34} {kr/max(ku,1):>16.1f} {rr/max(ru_,1):>16.1f} "
          f"{rr/max(ru_,1)-kr/max(ku,1):>+14.1f} {(rr/max(ru_,1))/max(kr/max(ku,1),0.01):>7.2f}x")

    print()
    print(f"{'per-product  units @ $/unit':<34} {'kawa':>16} {'route':>16} {'rev gap':>14}")
    prods = sorted({p for r in res for p in r["sold"]})
    for p in prods:
        ku_ = statistics.mean([r["sold"].get(p, 0) for r in K])
        kr_ = statistics.mean([r["revenue"].get(p, 0) for r in K])
        ru2 = statistics.mean([r["sold"].get(p, 0) for r in R])
        rr2 = statistics.mean([r["revenue"].get(p, 0) for r in R])
        print(f"  {p:<32} {f'{ku_:,.0f}@${kr_/max(ku_,1):.0f}':>16} {f'{ru2:,.0f}@${rr2/max(ru2,1):.0f}':>16} "
              f"{rr2-kr_:>+14,.0f}")

    print()
    print(f"{'op counts':<34} {'kawa':>16} {'route':>16} {'gap':>14}")
    allops = sorted({o for r in res for o in r["op_counts"]})
    for o in allops:
        k = statistics.mean([r["op_counts"].get(o, 0) for r in K])
        rv = statistics.mean([r["op_counts"].get(o, 0) for r in R])
        line("  " + o, k, rv)

    out = os.path.join(LOG_DIR, f"planner_spec_{time.strftime('%Y%m%d_%H%M%S')}.json")
    json.dump({"kawa": K, "route": R}, open(out, "w"), indent=1)
    print(f"\nraw: {out}")


if __name__ == "__main__":
    main()
