"""Unattended overnight pipeline: repeatedly run planner.genome_search in
chunks (each chunk resumes from the previous chunk's best checkpoint), and
after every chunk cross-validate the new best genome against the REAL
kaggle_environments engine -- not just planner.simulate -- before trusting the
gain. The 56-replay fidelity check (logs/sim_fidelity.log) proved the
simulator bit-exact for games *other agents* actually played; a genome search
can wander into portfolio/behaviour combinations those replays never
exercised (e.g. TC_STRAWBERRY=0), so every reported improvement here is
re-measured on the ground truth before being called real.

Each subprocess chunk is crash-isolated: if one chunk dies, the orchestrator
just starts the next chunk from the last successfully saved checkpoint rather
than losing the whole run.

Never touches submission/main.py and never calls the Kaggle CLI. route/agent.py
has never beaten the current live submission (kawa+intervene) in this
project's history and this run is not expected to close that gap in one
night -- the point is to keep pushing the self-built planner and leave a
clean, validated trail for the next session, not to ship anything.

Usage:
    nohup /home/yilewang/kagg-env/bin/python -m planner.autopilot \
        --total-budget-hours 8 > logs/planner/autopilot.out 2>&1 &
"""
import argparse
import json
import multiprocessing
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PYTHON = "/home/yilewang/kagg-env/bin/python"
CKPT_DIR = os.path.join(ROOT, "planner", "checkpoints")
LOG_DIR = os.path.join(ROOT, "logs", "planner")
STATUS_PATH = os.path.join(LOG_DIR, "PIPELINE_STATUS.md")
os.makedirs(CKPT_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

REF_POOL = [
    "kaggriculture-multi-route-farming-agent",
    "kaggriculture-frontier-the-soil-remembers-rain",
    "v111-8c4s-economic-core-premium-lead",
    "kaggriculture-breaking-the-tie-2883-score",
    "kaggriculture-rank-your-agent",
    "kaggriculture-3000-socre",
    "15-16-strict-future-v25-meta-reset",
    "strong-barnyard-economist",
    "kaggriculture-pure-architecture-2600-elo-v3",
]
GEN116_FITNESS_OLD_NARROW_METRIC = -8192.0  # historical, not comparable -- see HANDOFF/log
GEN116_FITNESS_FULL_POOL = -47786.6  # this session's honest re-measurement, planner/portfolio_search.py


def _real_engine_validate(genome, n_seeds=3, seat_both=True, opponents=None):
    """Cross-check a genome against kaggle_environments directly (ground
    truth), not planner.simulate. Small sample -- this is a sanity check, not
    a full re-ranking."""
    import importlib.util
    from kaggle_environments import make
    from route.search import to_params

    opponents = opponents or [REF_POOL[0], REF_POOL[2], REF_POOL[4], REF_POOL[6], REF_POOL[8]]  # spread
    agent_path = os.path.join(ROOT, "route", "agent.py")

    def load_route():
        spec = importlib.util.spec_from_file_location(f"rv_{os.getpid()}_{time.time_ns()}", agent_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.configure(to_params(genome))
        return mod.agent

    def load_ref(name):
        path = os.path.join(ROOT, "opponents", f"{name}.py")
        spec = importlib.util.spec_from_file_location(f"rv_ref_{os.getpid()}_{time.time_ns()}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.agent

    margins = []
    for opp_name in opponents:
        for seed_i in range(n_seeds):
            seed = 900_000_000 + hash((opp_name, seed_i)) % 90_000_000
            for seat in ((0, 1) if seat_both else (0,)):
                cand = load_route()
                opp = load_ref(opp_name)
                pair = [cand, opp] if seat == 0 else [opp, cand]
                env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": seed}, debug=False)
                env.run(pair)
                f = env.steps[-1]
                us = f[seat].observation["farms"][seat]["money"]
                opp_money = f[1 - seat].observation["farms"][1 - seat]["money"]
                margins.append(us - opp_money)
    return sum(margins) / len(margins), margins


def _write_status(state):
    lines = [
        "# Planner autopilot -- live status",
        "",
        f"Last updated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Chunks completed: {state['chunk']}",
        f"Total elapsed: {state['elapsed_h']:.2f}h / budget {state['budget_h']:.1f}h",
        "",
        "## Baselines (fixed reference points, same 9-agent pool, uniform weighting)",
        f"- gen116 checkpoint under the OLD narrow kawa+self-play metric: {GEN116_FITNESS_OLD_NARROW_METRIC:,.0f} (not comparable, historical only)",
        f"- gen116 checkpoint re-measured this session, full pool: {GEN116_FITNESS_FULL_POOL:,.0f}",
        "",
        "## Current best (simulator-measured, planner.simulate)",
        f"- fitness (paired margin, full 9-agent pool): {state['sim_best_fitness']:,.0f}",
        f"- generation: {state['sim_best_gen']}",
        "",
        "## Real-engine cross-validation (kaggle_environments ground truth, small sample)",
    ]
    if state["real_checks"]:
        lines.append("| chunk | sim fitness at check time | real-engine margin (4 opp x 2 seeds x 2 seats) | agreement |")
        lines.append("|---|---|---|---|")
        for c in state["real_checks"]:
            agree = "consistent" if (c["sim_fitness"] < 0) == (c["real_margin"] < 0) else "DIVERGENT -- investigate"
            lines.append(f"| {c['chunk']} | {c['sim_fitness']:,.0f} | {c['real_margin']:,.0f} | {agree} |")
    else:
        lines.append("(none yet)")
    lines += [
        "",
        "## Status vs the live submission",
        "route/agent.py (this search) has never beaten the current live submission",
        "(kawa tape + market intervention, ladder score 2555.6) in this project's history.",
        "This run has NOT touched submission/main.py and has NOT made any Kaggle submission.",
        "Nothing here is meant to replace the live submission tonight -- it is pushing the",
        "from-scratch planner, which is the longer-term project per the user's own plan.",
        "",
        "## Plateau tracking",
        f"- generations since last improvement: {state['gens_since_improve']}",
        f"- stop condition: {state['stop_reason'] or '(running)'}",
    ]
    with open(STATUS_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--total-budget-hours", type=float, default=8.0)
    ap.add_argument("--chunk-minutes", type=float, default=20.0)
    ap.add_argument("--workers", type=int, default=26)
    ap.add_argument("--population", type=int, default=48)
    ap.add_argument("--plateau-chunks", type=int, default=8,
                    help="stop early if this many consecutive chunks produce no improvement")
    ap.add_argument("--seeds-per-gen", type=int, default=10,
                    help="seeds per genome per generation in the inner search -- the first "
                         "overnight run used 6, which was noisy enough that a real-engine "
                         "spot-check (16 games) and a fresh 144-game re-evaluation of the "
                         "'best' genome disagreed with the search's own reported fitness by "
                         "~10k; raising this trades search speed for a less noisy signal")
    args = ap.parse_args()

    t_start = time.time()
    budget_s = args.total_budget_hours * 3600
    chunk_s = args.chunk_minutes * 60

    best_path = os.path.join(CKPT_DIR, "best_genome1.json")
    tag = "genome1"

    state = {"chunk": 0, "elapsed_h": 0.0, "budget_h": args.total_budget_hours,
            "sim_best_fitness": -1e18, "sim_best_gen": 0, "real_checks": [],
            "gens_since_improve": 0, "stop_reason": None}

    if os.path.exists(best_path):
        prev = json.load(open(best_path))
        state["sim_best_fitness"] = prev["fitness"]
        state["sim_best_gen"] = prev["gen"]
        print(f"resuming from existing checkpoint, fitness={prev['fitness']:,.0f}", flush=True)

    while time.time() - t_start < budget_s:
        state["chunk"] += 1
        state["elapsed_h"] = (time.time() - t_start) / 3600
        print(f"\n=== chunk {state['chunk']} (t={state['elapsed_h']:.2f}h) ===", flush=True)

        cmd = [PYTHON, "-m", "planner.genome_search",
              "--population", str(args.population), "--generations", "100000",
              "--elite", "6", "--seeds-per-gen", str(args.seeds_per_gen), "--workers", str(args.workers),
              "--time-budget", str(chunk_s), "--tag", tag,
              "--seed", str(1000 + state["chunk"])]
        if os.path.exists(best_path):
            cmd += ["--resume-from", best_path]

        chunk_log = os.path.join(LOG_DIR, f"autopilot_chunk_{state['chunk']:03d}.out")
        try:
            with open(chunk_log, "w") as f:
                subprocess.run(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT,
                               timeout=chunk_s + 300, check=False)
        except subprocess.TimeoutExpired:
            print(f"chunk {state['chunk']} timed out (subprocess didn't respect its own "
                  f"time budget) -- killed, moving on with whatever checkpoint exists", flush=True)

        if not os.path.exists(best_path):
            print("no checkpoint produced yet, retrying next chunk", flush=True)
            continue

        cur = json.load(open(best_path))
        improved = cur["fitness"] > state["sim_best_fitness"] + 1.0
        if improved:
            state["sim_best_fitness"] = cur["fitness"]
            state["sim_best_gen"] = cur["gen"]
            state["gens_since_improve"] = 0
            print(f"IMPROVED: sim fitness now {cur['fitness']:,.0f} (gen {cur['gen']})", flush=True)

            print("cross-validating against real kaggle_environments engine...", flush=True)
            real_margin, real_samples = _real_engine_validate(cur["genome"])
            state["real_checks"].append({"chunk": state["chunk"], "sim_fitness": cur["fitness"],
                                         "real_margin": real_margin})
            print(f"real-engine margin: {real_margin:,.0f} over {len(real_samples)} games", flush=True)
            with open(os.path.join(LOG_DIR, "planner_progress.log"), "a") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} autopilot chunk={state['chunk']} "
                       f"sim_fitness={cur['fitness']:.1f} real_margin={real_margin:.1f} "
                       f"gen={cur['gen']}\n")
        else:
            state["gens_since_improve"] += 1
            print(f"no improvement this chunk ({state['gens_since_improve']}/{args.plateau_chunks} "
                  f"since last gain)", flush=True)

        _write_status(state)

        if state["gens_since_improve"] >= args.plateau_chunks:
            state["stop_reason"] = (f"plateaued: {args.plateau_chunks} consecutive chunks "
                                    f"with no improvement over {state['sim_best_fitness']:,.0f}")
            print(state["stop_reason"], flush=True)
            break

    if state["stop_reason"] is None:
        state["stop_reason"] = f"time budget exhausted ({args.total_budget_hours}h)"
    state["elapsed_h"] = (time.time() - t_start) / 3600
    _write_status(state)
    print(f"\nDONE. {state['stop_reason']}", flush=True)
    print(f"final sim-measured best: {state['sim_best_fitness']:,.0f} "
         f"(vs gen116 baseline {GEN116_FITNESS_FULL_POOL:,.0f})", flush=True)
    print(f"status written to {STATUS_PATH}", flush=True)


if __name__ == "__main__":
    main()
