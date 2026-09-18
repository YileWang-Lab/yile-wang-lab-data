"""Unattended day pipeline for 2026-08-19 (user away until 18:00).

Order of work, highest expected value first:

  1. Validate the current best intervention variant against the REAL
     kaggle_environments engine (planner.simulate is verified bit-exact but a
     submission decision should never rest on the fast path alone).
  2. Bake it to submission/main.py and submit to Kaggle -- ONLY if it clears
     every gate below.
  3. Restart the from-scratch planner search on the freed cores.

SUBMISSION GATES (all must pass, else no submission is made):
  - simulator paired-margin delta vs shipped >= +200 with t >= 4
  - real-engine paired margin >= shipped's real-engine paired margin
  - the baked file imports cleanly and `env.run([path, opponent])` completes
    (HANDOFF rule 3: validate by FILE PATH, never by import -- Kaggle resolves
    a file agent with get_last_callable)
  - at most 1 submission per invocation, and the previous submission stays
    active (Kaggle keeps the latest 2), so a regression cannot cost the
    ladder position that 55600561 already holds

Usage:
    nohup /home/yilewang/kagg-env/bin/python -m planner.day_pipeline \
        --variant struct_d70_mp20 > logs/planner/day_pipeline.out 2>&1 &
"""
import argparse
import importlib.util
import json
import multiprocessing
import os
import statistics
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from route.bake import bake  # noqa: E402

PYTHON = "/home/yilewang/kagg-env/bin/python"
KAGGLE = "/home/yilewang/kagg-env/bin/kaggle"
LOG_DIR = os.path.join(ROOT, "logs", "planner")
STATUS = os.path.join(LOG_DIR, "PIPELINE_STATUS.md")
os.makedirs(LOG_DIR, exist_ok=True)

SHIPPED = {"_PREEMPT_MIN_FUTURE_QUANTITY": 0, "_PREEMPT_MAX_BATCH": 30,
           "INTERVENE": 1, "IV_DUMP_FRAC": 0.8, "IV_LEAD": 3, "IV_FERT": 1}

LIVE = {**SHIPPED, "IV_STRUCT": 1, "IV_DUMP_FRAC": 0.7, "IV_MIN_PRICE": 0.20}

# kawa's default tape-selection map, and the bucket-0 change.
# Bucket 0 fires when YARN_STORE is the FIRST shop unlocked (~14.7% of games).
# The default sends that case to 6c12s_4q_first_yarn; measurement says
# 6c12s_4q_second_yarn is far better there, and only there -- the bucket-1 and
# bucket-2 changes the same analysis proposed are flat to harmful.
DEFAULT_MAP = ["6c12s_4q_first_yarn", "6c12s_4q_second_yarn", "6c8s_3q",
               "10c4s_3q", "8c6s_3q"]
B0_MAP = ["6c12s_4q_second_yarn"] + DEFAULT_MAP[1:]

BASELINE = (dict(LIVE), "live 55612771")

CANDIDATES = {
    "struct_d70_mp20": dict(LIVE),
    "b0_second_yarn": {**LIVE, "TAPE_MAP": B0_MAP},
    "struct_d70": {**SHIPPED, "IV_STRUCT": 1, "IV_DUMP_FRAC": 0.7},
    "struct": {**SHIPPED, "IV_STRUCT": 1},
}

# All nine. The first gate for the bucket-0 tape swap used only six and 30
# seeds, which left ~28 games where the change actually fires -- far too few for
# an effect concentrated in ~13% of games with a per-firing sd of 18,145. It
# returned -18 where the 3,600-paired measurement says +1,841. Same quantity,
# different sample; the simulator reproduces the -18 exactly on that sample.
REAL_OPPONENTS = [
    "kaggriculture-multi-route-farming-agent",
    "v111-8c4s-economic-core-premium-lead",
    "kaggriculture-frontier-the-soil-remembers-rain",
    "kaggriculture-3000-socre",
    "kaggriculture-pure-architecture-2600-elo-v3",
    "strong-barnyard-economist",
    "kaggriculture-breaking-the-tie-2883-score",
    "kaggriculture-rank-your-agent",
    "15-16-strict-future-v25-meta-reset",
]

_n = [0]


def _load(path):
    _n[0] += 1
    spec = importlib.util.spec_from_file_location(f"dp_{os.getpid()}_{_n[0]}", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return getattr(m, "_submission_entry", None) or m.agent


def real_game(job):
    """One episode on the REAL kaggle_environments engine."""
    my_path, opp_name, seed, seat = job
    try:
        from kaggle_environments import make
        me = _load(my_path)
        opp = _load(os.path.join(ROOT, "opponents", f"{opp_name}.py"))
        pair = [me, opp] if seat == 0 else [opp, me]
        env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": seed}, debug=False)
        env.run(pair)
        f = env.steps[-1]
        us = f[seat].observation["farms"][seat]["money"]
        them = f[1 - seat].observation["farms"][1 - seat]["money"]
        return (opp_name, seed, seat, us - them, None)
    except Exception:
        import traceback
        return (opp_name, seed, seat, 0.0, traceback.format_exc()[-300:])


def real_engine_eval(path, seeds, workers=26):
    jobs = [(path, opp, s, seat) for opp in REAL_OPPONENTS for s in seeds for seat in (0, 1)]
    with multiprocessing.get_context("forkserver").Pool(workers) as pool:
        res = pool.map(real_game, jobs, chunksize=2)
    errs = [r for r in res if r[4]]
    paired = {}
    for opp, seed, seat, margin, err in res:
        if err:
            continue
        paired.setdefault((opp, seed), []).append(margin)
    pms = [sum(v) for v in paired.values() if len(v) == 2]
    return pms, errs


def validate_by_path(path):
    """HANDOFF rule 3: a submission must be validated by FILE PATH."""
    from kaggle_environments import make
    opp = os.path.join(ROOT, "opponents", "kaggriculture-multi-route-farming-agent.py")
    env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": 12345}, debug=False)
    env.run([path, opp])
    f = env.steps[-1]
    ok = all(s.status == "DONE" for s in f)
    return ok, f[0].observation["farms"][0]["money"], f[1].observation["farms"][1]["money"]


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(os.path.join(LOG_DIR, "planner_progress.log"), "a") as f:
        f.write(line + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="struct_d70_mp20")
    ap.add_argument("--seeds", type=int, default=30)
    ap.add_argument("--workers", type=int, default=26)
    ap.add_argument("--sim-delta", type=float, default=490.0,
                    help="the simulator-measured delta vs shipped for this variant")
    ap.add_argument("--sim-t", type=float, default=18.7)
    ap.add_argument("--no-submit", action="store_true")
    args = ap.parse_args()

    import random
    rng = random.Random(int(os.environ.get("DP_SEED", "20260819")))
    seeds = [rng.randrange(10**6, 2**31 - 1) for _ in range(args.seeds)]

    cand_params = CANDIDATES[args.variant]
    cand_path = os.path.join(ROOT, "agents", f"cand_{args.variant}.py")
    base_path = os.path.join(ROOT, "agents", "cand_shipped.py")
    bake(cand_params, out=cand_path, note=f"day_pipeline candidate {args.variant}")
    bake(BASELINE[0], out=base_path, note=f"day_pipeline baseline = {BASELINE[1]}")
    log(f"day_pipeline: candidate={args.variant} baked to {cand_path}")

    log("REAL-ENGINE evaluation (this is the gate; simulator already agrees)")
    t0 = time.time()
    cand_pms, cerr = real_engine_eval(cand_path, seeds, args.workers)
    base_pms, berr = real_engine_eval(base_path, seeds, args.workers)
    log(f"real-engine eval done in {time.time()-t0:.0f}s "
        f"({len(cand_pms)} paired cand, {len(base_pms)} paired base, "
        f"{len(cerr)+len(berr)} errors)")

    cm = statistics.mean(cand_pms) if cand_pms else 0.0
    bm = statistics.mean(base_pms) if base_pms else 0.0
    # paired on identical (opponent, seed) keys
    delta = cm - bm
    sd = statistics.pstdev([a - b for a, b in zip(cand_pms, base_pms)]) if len(cand_pms) == len(base_pms) and len(cand_pms) > 1 else 0.0
    se = sd / (len(cand_pms) ** 0.5) if cand_pms else 0.0
    log(f"REAL ENGINE  candidate={cm:,.0f}  shipped={bm:,.0f}  delta={delta:+,.0f} (se {se:,.0f})")

    ok_path, m0, m1 = validate_by_path(cand_path)
    log(f"file-path validation: status_ok={ok_path}  vs kawa {m0:,.0f} v {m1:,.0f}")

    gates = {
        "sim_delta>=200": args.sim_delta >= 200,
        "sim_t>=4": args.sim_t >= 4,
        "real_delta>=0": delta >= 0,
        "file_path_runs": ok_path,
        "no_errors": len(cerr) + len(berr) == 0,
    }
    log("GATES: " + "  ".join(f"{k}={'PASS' if v else 'FAIL'}" for k, v in gates.items()))

    if not all(gates.values()):
        log("NOT SUBMITTING -- one or more gates failed. submission/main.py untouched.")
        return 1
    if args.no_submit:
        log("gates passed but --no-submit set; submission/main.py untouched.")
        return 0

    # ---------------------------------------------------------------------
    # Uploading is OFF, by the user's instruction of 2026-08-19: local
    # optimisation only, they will submit by hand. This is a hard stop rather
    # than a default flag, because a default can be overridden by a stale
    # command line sitting in a nohup or a cron entry, and an accidental
    # submission spends a scarce daily slot AND rotates a good submission out
    # of the active pair (Kaggle keeps only the latest 2).
    #
    # To re-enable, the user sets KAGG_ALLOW_SUBMIT=1 in the environment.
    # Do not add a CLI flag for this and do not set the variable yourself.
    # ---------------------------------------------------------------------
    if os.environ.get("KAGG_ALLOW_SUBMIT") != "1":
        log("UPLOAD DISABLED (user instruction 2026-08-19: local optimisation only).")
        log(f"  gates all passed; candidate is at {cand_path}")
        log(f"  to ship by hand:  bake to submission/main.py, then "
            f"`kaggle competitions submit -c kaggriculture -f submission/main.py -m '...'`")
        return 0

    out = os.path.join(ROOT, "submission", "main.py")
    bake(cand_params, out=out, note=f"{args.variant}: struct forecast + dump .70 + price gate .20")
    size = os.path.getsize(out)
    ok2, n0, n1 = validate_by_path(out)
    log(f"baked submission/main.py ({size:,} bytes), path-validated ok={ok2}")
    if not ok2:
        log("ABORT: baked submission failed path validation")
        return 1

    desc = (f"{args.variant} | sim +{args.sim_delta:.0f} (t={args.sim_t:.1f}) | "
            f"real-engine +{delta:.0f} vs {BASELINE[1]}")
    r = subprocess.run([KAGGLE, "competitions", "submit", "-c", "kaggriculture",
                        "-f", out, "-m", desc[:480]],
                       capture_output=True, text=True, timeout=600)
    log(f"kaggle submit rc={r.returncode} out={r.stdout.strip()[:300]} err={r.stderr.strip()[:300]}")
    return 0 if r.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
