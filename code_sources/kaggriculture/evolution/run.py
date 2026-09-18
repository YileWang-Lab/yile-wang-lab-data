"""Unattended evolution loop over the tape+market agents.

Design notes that differ from a plain GA, each for a measured reason:

  Screening uses COMMON RANDOM NUMBERS and scores the paired DIFFERENCE against
  the parent. Raw paired margin has sd ~20,000 per game; the CRN difference has
  sd ~1,000, which is the only reason a +200 effect is detectable at all inside
  a few hundred games.

  Survivors must clear the threshold on the DIFFERENCE, not on absolute margin,
  and must not lose win rate. The ladder ranks on a TrueSkill-style win/loss
  rating in which margin does not appear, so a mutant that buys margin with win
  rate is a regression however good its paired margin looks.

  Promotion re-evaluates on a LARGER, DISJOINT seed set before a child becomes
  a parent. Screening ranks on the same data that selected the candidate, so the
  screen's own number is optimistically biased; the promotion pass is what the
  reported gain is quoted from.

Safety: never touches submission/main.py, never calls the Kaggle CLI, discards
any mutant worse than -5,000, and trims its own logs.
"""
import argparse
import json
import os
import random
import shutil
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from evolution.ops import (B0, LIVE, SHIPPED, POOL, AGENT_DIR, LOG_DIR,
                           build, mutate, evaluate, compare, DEFAULT_MAP,
                           B0_MAP, FAMILY)  # noqa: E402

PROGRESS = os.path.join(LOG_DIR, "PROGRESS.md")
EVOLOG = os.path.join(LOG_DIR, "evolution.log")
FINAL = os.path.join(LOG_DIR, "FINAL_REPORT.md")
BEST_OUT = os.path.join(ROOT, "evolution", "best_mutant.py")


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(EVOLOG, "a") as f:
        f.write(line + "\n")


def trim_logs(limit_mb=200):
    tot = 0
    files = []
    for fn in os.listdir(LOG_DIR):
        p = os.path.join(LOG_DIR, fn)
        if os.path.isfile(p):
            st = os.stat(p)
            tot += st.st_size
            files.append((st.st_mtime, p, st.st_size))
    if tot < limit_mb * 1e6:
        return
    files.sort()
    for _, p, sz in files:
        if tot < limit_mb * 1e6 * 0.7:
            break
        if os.path.basename(p) in ("PROGRESS.md", "FINAL_REPORT.md", "evolution.log"):
            continue
        os.remove(p); tot -= sz


def write_progress(state):
    L = ["# Evolution progress", "",
         f"Updated {time.strftime('%Y-%m-%d %H:%M:%S')}   round {state['round']}/{state['max_rounds']}"
         f"   elapsed {state['elapsed']/60:.0f} min", ""]
    L += ["## Baselines (fast simulator, paired margin over the 9-agent pool)", "",
          "| agent | paired margin | win rate |", "|---|---|---|"]
    for n, (m, w) in state["baselines"].items():
        L.append(f"| {n} | {m:+,.0f} | {w:.1%} |")
    L += ["", "## Round-robin between our own versions (paired margin, row vs column)", ""]
    L += state.get("rr_lines", ["(pending)"])
    L += ["", "## Best mutant so far", ""]
    b = state.get("best")
    if b:
        L += [f"- label: `{b['label']}`",
              f"- screen delta vs parent: **{b['screen']:+,.0f}** (se {b['screen_se']:,.0f})",
              f"- promotion delta on DISJOINT seeds: **{b['promo']:+,.0f}** (se {b['promo_se']:,.0f}, n={b['promo_n']})",
              f"- win rate {b['wr']:.1%} vs parent {b['parent_wr']:.1%}",
              f"- genome: `{json.dumps(b['genome'])}`"]
    else:
        L.append("(none has cleared promotion yet)")
    L += ["", "## Per-round summary", "",
          "| round | mutants | survived screen | promoted | best promo delta |", "|---|---|---|---|---|"]
    for r in state["rounds"]:
        L.append(f"| {r['round']} | {r['n']} | {r['screened']} | {r['promoted']} | "
                 f"{r['best']:+,.0f} |")
    L += ["", "## Safety", "",
          "- `submission/main.py` untouched; no Kaggle call is made by this process.",
          "- mutants below -5,000 vs parent are discarded immediately.",
          f"- stop condition: {state.get('stop') or '(running)'}"]
    with open(PROGRESS, "w") as f:
        f.write("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=20)
    ap.add_argument("--mutants", type=int, default=200)
    ap.add_argument("--screen-seeds", type=int, default=12)
    ap.add_argument("--promo-seeds", type=int, default=40)
    ap.add_argument("--workers", type=int, default=26)
    ap.add_argument("--threshold", type=float, default=200.0)
    ap.add_argument("--patience", type=int, default=3)
    args = ap.parse_args()

    open(EVOLOG, "w").close()
    rng = random.Random(20260819)
    t0 = time.time()
    state = {"round": 0, "max_rounds": args.rounds, "elapsed": 0,
             "baselines": {}, "rounds": [], "best": None, "stop": None}

    # ---------------- step 1: baselines
    log("STEP 1  baselines")
    base_paths = {n: build(dict(g), f"base_{n}")
                  for n, g in (("v3", SHIPPED), ("struct", LIVE), ("b0", B0))}
    bseeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(40)]
    res, errs = evaluate(list(base_paths.values()), bseeds, workers=args.workers)
    if errs:
        log(f"  {len(errs)} errors, first: {errs[0][:150]}")
    for n, p in base_paths.items():
        d = res.get(p, {})
        m = statistics.mean(d.values()) if d else 0.0
        w = sum(1 for v in d.values() if v > 0) / max(1, len(d))
        state["baselines"][n] = (m, w)
        log(f"  {n:<7} paired margin {m:>+10,.0f}   win {w:>6.1%}   n={len(d)}")
    with open(os.path.join(LOG_DIR, "baseline.csv"), "w") as f:
        f.write("agent,paired_margin,win_rate,n\n")
        for n, (m, w) in state["baselines"].items():
            f.write(f"{n},{m:.1f},{w:.4f},{len(res.get(base_paths[n],{}))}\n")

    # ---------------- step 2: round-robin between our own versions
    log("STEP 2  round-robin between our versions")
    rr = ["| | " + " | ".join(base_paths) + " |",
          "|---|" + "---|" * len(base_paths)]
    from evolution.ops import head_to_head
    import multiprocessing
    names = list(base_paths)
    jobs = []
    rrseeds = bseeds[:16]
    for a in names:
        for b in names:
            if a == b:
                continue
            for s in rrseeds:
                for seat in (0, 1):
                    jobs.append((base_paths[a], base_paths[b], s, seat))

    with multiprocessing.get_context("forkserver").Pool(args.workers) as ex:
        rrres = ex.map(head_to_head, jobs, chunksize=4)
    agg = {}
    for pa, pb, seed, m, err in rrres:
        if not err:
            agg.setdefault((pa, pb), []).append(m)
    for a in names:
        row = [a]
        for b in names:
            if a == b:
                row.append("--")
            else:
                v = agg.get((base_paths[a], base_paths[b]), [])
                row.append(f"{sum(v)/max(1,len(v)/2):+,.0f}" if v else "?")
        rr.append("| " + " | ".join(row) + " |")
        log("  " + " ".join(f"{c:>12}" for c in row))
    state["rr_lines"] = rr
    write_progress(state)

    # ---------------- steps 3-5: mutate, screen, promote, iterate
    parents = [("b0", dict(B0), base_paths["b0"])]
    parent_res = {base_paths["b0"]: res[base_paths["b0"]]}
    stale = 0

    for rnd in range(1, args.rounds + 1):
        state["round"] = rnd
        state["elapsed"] = time.time() - t0
        log(f"ROUND {rnd}  parents={[p[0] for p in parents]}")
        sseeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(args.screen_seeds)]

        kids = []
        seen = set()
        while len(kids) < args.mutants and len(seen) < args.mutants * 6:
            pname, pg, ppath = parents[rng.randrange(len(parents))]
            g, lbl = mutate(pg, rng)
            key = json.dumps(g, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            kids.append((f"r{rnd}_m{len(kids)}", lbl, g, pname, ppath))

        paths = {}
        for name, lbl, g, pname, ppath in kids:
            paths[name] = build(dict(g), name)

        # screen every child AND every parent on the identical CRN grid
        allp = list(paths.values()) + [p[2] for p in parents]
        sres, serrs = evaluate(allp, sseeds, workers=args.workers)
        if serrs:
            log(f"  screen: {len(serrs)} errors, first {serrs[0][:120]}")

        survivors = []
        for name, lbl, g, pname, ppath in kids:
            c = sres.get(paths[name], {})
            p = sres.get(ppath, {})
            dm, dse, wr, n = compare(c, p)
            pwr = sum(1 for v in p.values() if v > 0) / max(1, len(p))
            if dm < -5000:
                continue
            if dm >= args.threshold and wr >= pwr - 1e-9:
                survivors.append((name, lbl, g, pname, ppath, dm, dse, wr, pwr))
        survivors.sort(key=lambda r: -r[5])
        log(f"  {len(kids)} mutants -> {len(survivors)} cleared screen (>=+{args.threshold:.0f}, win not down)")

        # promote the top few on a larger DISJOINT seed set
        promoted = []
        if survivors:
            pseeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(args.promo_seeds)]
            top = survivors[:6]
            ppaths = [paths[s[0]] for s in top] + list({s[4] for s in top})
            pres, perrs = evaluate(ppaths, pseeds, workers=args.workers)
            for name, lbl, g, pname, ppath, dm, dse, wr, pwr in top:
                c, p = pres.get(paths[name], {}), pres.get(ppath, {})
                pdm, pdse, pwr2, pn = compare(c, p)
                cwr = sum(1 for v in c.values() if v > 0) / max(1, len(c))
                bwr = sum(1 for v in p.values() if v > 0) / max(1, len(p))
                log(f"    {lbl:<28} screen {dm:>+8,.0f}  promo {pdm:>+8,.0f} "
                    f"(se {pdse:>6,.0f})  win {cwr:.1%} vs {bwr:.1%}")
                if pdm >= args.threshold and cwr >= bwr - 1e-9:
                    promoted.append((name, lbl, g, paths[name], pdm, pdse, pn, cwr, bwr))
        promoted.sort(key=lambda r: -r[4])

        best_delta = promoted[0][4] if promoted else (survivors[0][5] if survivors else 0.0)
        state["rounds"].append({"round": rnd, "n": len(kids),
                                "screened": len(survivors), "promoted": len(promoted),
                                "best": best_delta})

        if promoted:
            stale = 0
            nm, lbl, g, pth, pdm, pdse, pn, cwr, bwr = promoted[0]
            if state["best"] is None or pdm > state["best"]["promo"]:
                state["best"] = {"label": lbl, "genome": g, "screen": 0.0,
                                 "screen_se": 0.0, "promo": pdm, "promo_se": pdse,
                                 "promo_n": pn, "wr": cwr, "parent_wr": bwr,
                                 "path": pth}
                shutil.copy(pth, BEST_OUT)
                log(f"  NEW BEST {lbl}  promo {pdm:+,.0f} (se {pdse:,.0f})")
            parents = [(nm, g, pth) for nm, lbl, g, pth, *_ in promoted[:3]]
        else:
            stale += 1
            log(f"  no promotion ({stale}/{args.patience} stale rounds)")

        state["elapsed"] = time.time() - t0
        write_progress(state)
        trim_logs()

        if stale >= args.patience:
            state["stop"] = f"plateau: {stale} rounds with no promotion above +{args.threshold:.0f}"
            break
    else:
        state["stop"] = f"completed {args.rounds} rounds"

    state["elapsed"] = time.time() - t0
    write_progress(state)

    b = state["best"]
    with open(FINAL, "w") as f:
        f.write("# Evolution final report\n\n")
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  "
                f"{state['round']} rounds, {state['elapsed']/60:.0f} min\n\n")
        f.write(f"Stop: {state['stop']}\n\n## Baselines\n\n")
        f.write("| agent | paired margin | win rate |\n|---|---|---|\n")
        for n, (m, w) in state["baselines"].items():
            f.write(f"| {n} | {m:+,.0f} | {w:.1%} |\n")
        f.write("\n## Best mutant\n\n")
        if b:
            f.write(f"- label `{b['label']}`\n- promotion delta on disjoint seeds "
                    f"**{b['promo']:+,.0f}** (se {b['promo_se']:,.0f}, n={b['promo_n']})\n")
            f.write(f"- win rate {b['wr']:.1%} vs parent {b['parent_wr']:.1%}\n")
            f.write(f"- genome `{json.dumps(b['genome'])}`\n")
            f.write(f"- code saved to `evolution/best_mutant.py`\n")
            f.write("\nLadder-equivalent: this project's own measurements put a consistent\n"
                    "+2,000 paired margin at roughly 90% win rate and +6,000 at flipping every\n"
                    "loss on file, so read the number against that scale rather than as money.\n")
        else:
            f.write("No mutant cleared promotion. The parent stands.\n")
        f.write("\n## Rounds\n\n| round | mutants | screened | promoted | best |\n|---|---|---|---|---|\n")
        for r in state["rounds"]:
            f.write(f"| {r['round']} | {r['n']} | {r['screened']} | {r['promoted']} | {r['best']:+,.0f} |\n")
        f.write("\n## Not searched, and why\n\n"
                "Market-layer parameters (dump fraction, price gate, lead, item set, the base\n"
                "tape's _PREEMPT_* constants, seat-conditional play, sell suppression) were\n"
                "swept over ~68,000 games in planner/intervene_sweep.py rounds 1-6 and then\n"
                "checked against the 80 real ladder opponents in planner/ladder_sweep.py, where\n"
                "the live configuration is already optimal (best alternative +23). Re-jittering\n"
                "them would rediscover the same optimum.\n\n"
                "The five tapes are only three distinct behaviours (10c4s/6c8s/8c6s differ by\n"
                "0.7-1.4% of steps; day 0 is identical across all five), so the tape-map space\n"
                "is 3^5 = 243 rather than 5^5, and splices are constrained to cross-family.\n")
    log(f"DONE  {state['stop']}")
    log(f"report: {FINAL}")


if __name__ == "__main__":
    main()
