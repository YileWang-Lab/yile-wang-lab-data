"""Phase 1: full-genome (mu+lambda) search over route/agent.py's parameter
space, using planner.simulate.Simulator instead of kaggle_environments.

Reuses route/search.py's PARAM_SPACE / random_genome / mutate / crossover /
sanitise / to_params verbatim (imported, not copied -- those are pure
functions with no coupling to the real-engine evaluation backend route/search.py
happens to use). What changes is the evaluation backend and, critically, the
matchup set: route/search.py's `build_matchups` scored each generation against
only kawa + one rotating reference + self-play (2+2+2 = 6 games), which diluted
the signal toward self-play (~0 margin) and left the eventual champion
(best_self1.json, gen116, fitness -8192) never fully exercised against the
hardest 3 of the 9-agent pool. This scores every genome against the FULL
uniform pool every generation -- affordable now because the fast simulator
runs ~90 games/sec vs kaggle_environments' ~0.3-0.5 games/sec/worker.

Usage:
    /home/yilewang/kagg-env/bin/python -m planner.genome_search \
        --population 40 --generations 100 --seeds-per-gen 4 --workers 26
"""
import argparse
import importlib.util
import json
import multiprocessing
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from planner.simulate import Simulator  # noqa: E402
from route.search import (PARAM_SPACE, SEED_DEFAULTS, random_genome, mutate,  # noqa: E402
                          crossover, sanitise, to_params)

ROUTE_AGENT_PATH = os.path.join(ROOT, "route", "agent.py")
OPPONENT_DIR = os.path.join(ROOT, "opponents")
CKPT_DIR = os.path.join(ROOT, "planner", "checkpoints")
LOG_DIR = os.path.join(ROOT, "logs", "planner")
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

# route/checkpoints/best_self1.json -- the historical champion, fitness -8192
# under the OLD narrow matchup. Seeded into generation 0 so the search never
# does worse than a genome we already know how to build.
GEN116_GENOME = {
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
    "RES_MILK": 34.04680791271699, "RES_WOOL": 112.10608388056207, "RES_STRAWBERRY": 1.0,
    "RES_MELON": 41.82690366455841, "RES_FERTILIZER": 34.34010556168379,
    "RES_EGG": 9.242162933220143, "RES_WHEAT": 25.079837795842593,
}

_counter = [0]


def _load_route(params):
    _counter[0] += 1
    spec = importlib.util.spec_from_file_location(
        f"gsearch_cand_{os.getpid()}_{_counter[0]}", ROUTE_AGENT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.configure(to_params(params))
    return mod.agent


def _load_ref(name):
    _counter[0] += 1
    path = os.path.join(OPPONENT_DIR, f"{name}.py")
    spec = importlib.util.spec_from_file_location(
        f"gsearch_ref_{name.replace('-', '_')}_{os.getpid()}_{_counter[0]}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.agent


def play_one(job):
    cand_id, genome, opp_name, seed, seat = job
    try:
        candidate = _load_route(genome)
        opponent = _load_ref(opp_name)
        pair = [candidate, opponent] if seat == 0 else [opponent, candidate]
        sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
        m0, m1 = sim.run_episode(pair[0], pair[1])
        us, opp = (m0, m1) if seat == 0 else (m1, m0)
        return (cand_id, us - opp, None)
    except Exception:
        import traceback
        return (cand_id, -1e9, traceback.format_exc()[-300:])


def evaluate_population(pool, population, opponents, seeds):
    jobs = []
    for cand_id, genome in enumerate(population):
        for opp_name in opponents:
            for seed in seeds:
                for seat in (0, 1):
                    jobs.append((cand_id, genome, opp_name, seed, seat))
    results = pool.map(play_one, jobs, chunksize=8)
    by_cand = {}
    errors = []
    for cand_id, margin, err in results:
        by_cand.setdefault(cand_id, []).append(margin)
        if err:
            errors.append((cand_id, err))
    fitness = [sum(by_cand[i]) / len(by_cand[i]) for i in range(len(population))]
    win_rate = [sum(1 for m in by_cand[i] if m > 0) / len(by_cand[i]) for i in range(len(population))]
    return fitness, win_rate, errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--population", type=int, default=40)
    ap.add_argument("--generations", type=int, default=100)
    ap.add_argument("--elite", type=int, default=6)
    ap.add_argument("--seeds-per-gen", type=int, default=4)
    ap.add_argument("--workers", type=int, default=26)
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--time-budget", type=float, default=7200)
    ap.add_argument("--tag", default="genome1")
    ap.add_argument("--resume-from", default=None,
                    help="path to a best_*.json checkpoint to seed the population from, "
                         "instead of gen116/SEED_DEFAULTS -- for chaining search chunks")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    best_path = os.path.join(CKPT_DIR, f"best_{args.tag}.json")
    log_path = os.path.join(CKPT_DIR, f"log_{args.tag}.jsonl")

    seed_genome = GEN116_GENOME
    resume_fitness = -1e18
    if args.resume_from and os.path.exists(args.resume_from):
        with open(args.resume_from) as f:
            resumed = json.load(f)
        seed_genome = resumed["genome"]
        resume_fitness = resumed["fitness"]
        print(f"resuming from {args.resume_from} (fitness={resume_fitness:,.0f})")

    population = [dict(seed_genome), dict(GEN116_GENOME), dict(SEED_DEFAULTS)]
    population += [mutate(seed_genome, rng, rate=0.3) for _ in range(args.population // 3)]
    population += [mutate(seed_genome, rng, rate=0.55) for _ in range(args.population // 4)]
    population += [random_genome(rng) for _ in range(args.population - len(population))]

    # Start the "is this worth checkpointing" bar at the resumed fitness, not
    # -1e18. Each chunk is a fresh subprocess with a fresh random seed draw,
    # so re-evaluating the *same* resumed genome under this chunk's own seeds
    # will score it differently from its recorded value -- without this, the
    # very first generation silently overwrote a better checkpoint with a
    # worse one whenever that re-measurement came in lower than the recorded
    # fitness, discarding real progress to noise. Found live 2026-08-19: a
    # resumed -28,903 genome got overwritten with -35,173 in generation 0 of
    # the very next chunk with no genuine regression having occurred.
    best_genome, best_fit = (dict(seed_genome), resume_fitness) if resume_fitness > -1e18 else (None, -1e18)
    t_start = time.time()

    ctx = multiprocessing.get_context("forkserver")
    with ctx.Pool(processes=args.workers) as pool:
        for gen in range(args.generations):
            if time.time() - t_start > args.time_budget:
                print(f"time budget exhausted at gen {gen}")
                break
            seeds = [rng.randrange(10**6, 2**31 - 1) for _ in range(args.seeds_per_gen)]
            t0 = time.time()
            fitness, win_rate, errors = evaluate_population(pool, population, REF_POOL, seeds)
            elapsed = time.time() - t0

            ranked = sorted(range(len(population)), key=lambda i: -fitness[i])
            gen_best_i = ranked[0]
            if fitness[gen_best_i] > best_fit:
                best_fit = fitness[gen_best_i]
                best_genome = dict(population[gen_best_i])
                with open(best_path, "w") as f:
                    json.dump({"genome": best_genome, "params": to_params(best_genome),
                               "fitness": best_fit, "gen": gen}, f, indent=1)

            elites = [population[i] for i in ranked[:args.elite]]
            next_pop = list(elites)
            while len(next_pop) < args.population:
                if rng.random() < 0.15:
                    next_pop.append(random_genome(rng))
                elif rng.random() < 0.3:
                    a, b = rng.sample(elites, 2) if len(elites) >= 2 else (elites[0], elites[0])
                    next_pop.append(sanitise(mutate(crossover(a, b, rng), rng, rate=0.2)))
                else:
                    parent = rng.choice(elites)
                    next_pop.append(sanitise(mutate(parent, rng, rate=0.35)))
            population = next_pop

            log_rec = {"gen": gen, "best": fitness[gen_best_i], "win_rate": win_rate[gen_best_i],
                      "median": sorted(fitness)[len(fitness) // 2],
                      "n_errors": len(errors), "elapsed": elapsed,
                      "genome": population[0] if gen == 0 else elites[0]}
            with open(log_path, "a") as f:
                f.write(json.dumps(log_rec) + "\n")
            print(f"gen {gen:4d}  best={fitness[gen_best_i]:>12,.0f}  win_rate={win_rate[gen_best_i]:.2f}  "
                  f"median={log_rec['median']:>12,.0f}  overall_best={best_fit:>12,.0f}  "
                  f"{elapsed:.1f}s  errors={len(errors)}", flush=True)

    print(f"\nDONE. best fitness={best_fit:,.0f} (vs gen116_baseline under same pool, "
          f"see logs/planner/portfolio_search_*.csv)")
    print(f"checkpoint: {best_path}")


if __name__ == "__main__":
    main()
