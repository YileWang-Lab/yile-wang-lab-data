"""Phase 1 MVP: rolling-horizon portfolio search for the self-built planner.

route/agent.py's own diagnosis (HANDOFF section 13) is that after 124
generations of real-engine GA search it plateaued at paired margin -8,192
against the reference pool, and the shortfall is "in the economy (revenue per
unit and product mix), not the routing". This module replaces the *fixed*
TARGET_COUNTS genome (searched once, offline, against the slow real engine)
with a set of candidate portfolios evaluated by full-season rollout through
planner.simulate.Simulator -- ~1200 steps/sec, ~500-1000x faster than driving
kaggle_environments, so far more candidates fit in the same wall-clock budget
than the historical run could afford.

This does NOT touch route/agent.py. Every candidate is a fresh module instance
(importlib, unique name) configured via the existing `configure(params)` entry
point -- the same mechanism route/search.py already uses.

Usage:
    /home/yilewang/kagg-env/bin/python -m planner.portfolio_search
"""
import csv
import importlib.util
import json
import multiprocessing
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from planner.simulate import Simulator  # noqa: E402

ROUTE_AGENT_PATH = os.path.join(ROOT, "route", "agent.py")
OPPONENT_DIR = os.path.join(ROOT, "opponents")
LOG_DIR = os.path.join(ROOT, "logs", "planner")
os.makedirs(LOG_DIR, exist_ok=True)

# Same 9-agent pool as route/tournament.py / HANDOFF section 15.
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

SEEDS = [1009, 24071, 88301, 150011, 271829, 333667, 481123, 592049]  # 8 seeds

BASE_GENOME = {
    # route/checkpoints/best_self1.json, gen116, fitness -8192 (real engine).
    "TC_COW": 5, "TC_SHEEP": 6, "TC_GOOSE": 0, "TC_MELON": 6, "TC_STRAWBERRY": 24, "TC_WHEAT": 4,
    "MAX_HANDS": 16, "HIRE_BUDGET_FRACTION": 0.6082751915289906, "SPEND_RESERVE": 436.6750146003864,
    "SURVIVAL_RESERVE_FRACTION": 0.0, "WHEAT_FEED_BUFFER_MULT": 1.385207857196197,
    "LAND_BUY_CASH_MULTIPLE": 3.685968955243266, "ANIMAL_BUY_CAP_PER_TURN": 6, "SEED_BATCH_PER_TURN": 3,
    "BUY_ANIMALS_FIRST": 0, "SHED_PANIC_FRACTION": 0.2, "RAMP_START_DAY": 28, "RAMP_END_DAY": 29,
    "RESERVE_PRICE_SCALE": 1.1654919922710392, "COLLECT_FERT_VALUE": 0.0, "IDLE_TOPUP": 0,
    "IDLE_MAX_TRAVEL": 13, "FRONT_RUN": 0, "TERMINAL_STEP": 706, "OPP_MODEL": 0,
    "OPP_SCALE_LO": 0.7785363754978746, "OPP_SCALE_HI": 2.3366588665848442, "OPP_HORIZON_DAYS": 2,
    "PLANT_MISS_TOLERANCE": 13, "RP_COW": 0.5175838466511128, "RP_SHEEP": 0.8533504283379038,
    "RP_WHEAT": 0.0, "RP_MELON": 0.0, "RP_STRAWBERRY": 0.0, "RP_GOOSE": 0.9430746524571036,
    "WHEAT_SELL_SURPLUS": 0,
    "RESERVE_PRICE": {"MILK": 34.04680791271699, "WOOL": 112.10608388056207, "STRAWBERRY": 1.0,
                      "MELON": 41.82690366455841, "FERTILIZER": 34.34010556168379,
                      "EGG": 9.242162933220143, "WHEAT": 25.079837795842593},
}


def _variant(name, **overrides):
    g = dict(BASE_GENOME)
    g.update(overrides)
    return (name, g)


# Candidates informed by the market-curve math worked out earlier this
# session: EGG barely crashes (20,000 units to floor) yet gen116 found
# TC_GOOSE=0; STRAWBERRY crashes fast (linear, 62 units to floor) yet carries
# the largest single allocation (24 tiles). Both are worth testing directly
# rather than trusting the historical search found the true optimum on that
# axis -- it plateaued, and plateau != optimum.
CANDIDATES = [
    ("gen116_baseline", dict(BASE_GENOME)),
    _variant("more_goose", TC_GOOSE=8, TC_STRAWBERRY=18),
    _variant("more_goose_big", TC_GOOSE=14, TC_STRAWBERRY=12, TC_MELON=4),
    _variant("less_strawberry", TC_STRAWBERRY=12, TC_WHEAT=10, TC_MELON=8),
    _variant("more_wheat", TC_WHEAT=16, TC_STRAWBERRY=16),
    _variant("8c4s_style", TC_COW=8, TC_SHEEP=4, TC_MELON=6, TC_STRAWBERRY=12, TC_WHEAT=8, TC_GOOSE=4),
    _variant("more_animals", TC_COW=8, TC_SHEEP=10, TC_STRAWBERRY=14, TC_MELON=4),
    _variant("balanced_egg_wheat", TC_COW=5, TC_SHEEP=6, TC_GOOSE=6, TC_MELON=6,
             TC_STRAWBERRY=14, TC_WHEAT=10),
    _variant("no_strawberry", TC_STRAWBERRY=0, TC_WHEAT=14, TC_MELON=14, TC_GOOSE=8),
    _variant("melon_heavy", TC_MELON=16, TC_STRAWBERRY=10, TC_WHEAT=4),
]

_counter = [0]


def _load_route(genome):
    _counter[0] += 1
    spec = importlib.util.spec_from_file_location(
        f"route_cand_{os.getpid()}_{_counter[0]}", ROUTE_AGENT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.configure(genome)
    return mod


def _load_ref(name):
    _counter[0] += 1
    path = os.path.join(OPPONENT_DIR, f"{name}.py")
    spec = importlib.util.spec_from_file_location(
        f"ref_{name.replace('-', '_')}_{os.getpid()}_{_counter[0]}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.agent


def play_one(job):
    cand_name, genome, opp_name, seed, seat = job
    try:
        candidate = _load_route(genome).agent
        opponent = _load_ref(opp_name)
        pair = [candidate, opponent] if seat == 0 else [opponent, candidate]
        sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
        m0, m1 = sim.run_episode(pair[0], pair[1])
        us, opp = (m0, m1) if seat == 0 else (m1, m0)
        return (cand_name, opp_name, seed, seat, us, opp, None)
    except Exception as exc:
        import traceback
        return (cand_name, opp_name, seed, seat, 0.0, 0.0, traceback.format_exc()[-300:])


def build_jobs():
    jobs = []
    for cand_name, genome in CANDIDATES:
        for opp_name in REF_POOL:
            for seed in SEEDS:
                for seat in (0, 1):
                    jobs.append((cand_name, genome, opp_name, seed, seat))
    return jobs


def main(workers=26):
    jobs = build_jobs()
    print(f"{len(CANDIDATES)} candidates x {len(REF_POOL)} opponents x {len(SEEDS)} seeds x 2 seats "
          f"= {len(jobs)} games, {workers} workers")
    t0 = time.time()
    ctx = multiprocessing.get_context("forkserver")
    with ctx.Pool(workers) as pool:
        results = pool.map(play_one, jobs, chunksize=4)
    elapsed = time.time() - t0
    print(f"elapsed {elapsed:.1f}s ({len(jobs)/elapsed:.1f} games/s)")

    errors = [r for r in results if r[6]]
    if errors:
        print(f"{len(errors)} errors, first: {errors[0][6]}")

    by_cand = {}
    for cand_name, opp_name, seed, seat, us, opp, err in results:
        if err:
            continue
        by_cand.setdefault(cand_name, []).append(us - opp)

    ts = time.strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(LOG_DIR, f"portfolio_search_{ts}.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["candidate", "n_games", "paired_margin_mean", "paired_wins", "win_rate"])
        ranked = []
        for cand_name, _ in CANDIDATES:
            margins = by_cand.get(cand_name, [])
            n = len(margins)
            mean_m = sum(margins) / n if n else float("nan")
            wins = sum(1 for m in margins if m > 0)
            wr = wins / n if n else 0.0
            w.writerow([cand_name, n, f"{mean_m:.1f}", wins, f"{wr:.3f}"])
            ranked.append((cand_name, mean_m, wins, n, wr))

    ranked.sort(key=lambda r: -r[1])
    print()
    print(f"{'candidate':<22} {'n':>4} {'paired_margin':>15} {'wins':>6} {'win_rate':>9}")
    for cand_name, mean_m, wins, n, wr in ranked:
        print(f"{cand_name:<22} {n:>4} {mean_m:>15,.1f} {wins:>6} {wr:>9.1%}")

    log_line = (f"{time.strftime('%Y-%m-%d %H:%M:%S')} portfolio_search "
                f"n_candidates={len(CANDIDATES)} n_games={len(jobs)} elapsed={elapsed:.1f}s "
                f"winner={ranked[0][0]} winner_margin={ranked[0][1]:.1f} "
                f"baseline_margin={dict((r[0], r[1]) for r in ranked).get('gen116_baseline', float('nan')):.1f} "
                f"csv={csv_path}")
    with open(os.path.join(ROOT, "logs", "planner_progress.log"), "a") as f:
        f.write(log_line + "\n")
    print()
    print(log_line)
    return ranked


if __name__ == "__main__":
    main()
