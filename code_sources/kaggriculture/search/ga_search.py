"""(mu + lambda) evolution strategy over the agent's execution/spending
hyperparameters, evaluated on the real kaggriculture environment in parallel
across all CPU cores.

Each generation:
  1. Evaluate every genome in the population against a fixed matchup set
     (starter, random, and self-play against the current incumbent) using a
     multiprocessing.Pool sized to the machine's core count.
  2. Rank by mean (my_money - opponent_money) across matchups.
  3. Keep the top `elite` genomes unchanged; refill the rest of the
     population via mutation of randomly-chosen elites (with a small
     crossover chance), plus a couple of fresh random genomes each
     generation to keep exploring.
  4. Checkpoint the best genome (and a run log) to disk after every
     generation so progress survives interruption.
"""
import json
import multiprocessing
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from search.evaluate import evaluate_candidate  # noqa: E402

# Wall-clock deadline for one whole generation's batch of jobs (each job is
# one candidate x 5 episodes). Generous margin over the ~15-30s normal case;
# a backstop against a genuinely pathological genome (e.g. one that drives
# the market order loop to its 100k-iteration safety cap repeatedly), not a
# per-job budget -- fast jobs finishing early don't wait on slow ones.
JOB_TIMEOUT = 120

# Physical core count, not logical (hyperthreads oversubscribe badly here:
# this workload is single-threaded CPU-bound Python, and kaggle_environments'
# per-turn deepcopy/schema-validate/structify overhead scales with how much
# is built on the farm, so a densely-built candidate agent is much heavier
# per episode than a sparse one -- confirmed by direct measurement: 48
# workers on 26 physical cores took 6+ minutes to not even finish one
# generation, while 24 workers on 24 physical cores did one in 14.6s.

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CKPT_DIR = os.path.join(ROOT, "search", "checkpoints")
os.makedirs(CKPT_DIR, exist_ok=True)

BASE_RESERVE_PRICE = {
    "WHEAT": 20, "CARROT": 15, "TOMATO": 25, "STRAWBERRY": 60, "MELON": 80,
    "EGG": 20, "MILK": 80, "WOOL": 90, "FERTILIZER": 10,
}

PARAM_SPACE = {
    # Round 1 pegged TARGET_HANDS/LAND_BUY_CASH_MULTIPLE at their upper bound
    # and SURVIVAL_RESERVE_FRACTION at its lower bound (best found: 32, 4.5,
    # 0.03) -- widened here so round 2 can find out whether the true optimum
    # is further out or those genuinely were the ceiling/floor.
    "TARGET_HANDS":              {"type": "int",   "low": 6,   "high": 50,  "mut": 6},
    "TILES_PER_HAND":            {"type": "float", "low": 2.0, "high": 12.0, "mut": 1.5},
    # Workload-based hand sizing. Measured sweep vs starter at the gen-15
    # portfolio: WPH 14->30k, 10->31k, 7->54k, 5->27k, 3->6.5k. Peaked at 7,
    # but the OLD tile-count formula (~4 hands) scored 67k -- i.e. for an
    # agent that still burns 60% of turns walking, extra hands cost more than
    # they produce. Left wide for the search; the real fix is movement.
    "WORK_PER_HAND":             {"type": "float", "low": 3.0, "high": 30.0, "mut": 4.0},
    "ANIMAL_WORK_PER_DAY":       {"type": "float", "low": 1.0, "high": 6.0, "mut": 0.8},
    "CROP_WORK_PER_DAY":         {"type": "float", "low": 0.5, "high": 3.0, "mut": 0.5},
    "HIRE_BUDGET_FRACTION":      {"type": "float", "low": 0.05, "high": 0.9, "mut": 0.15},
    "SPEND_RESERVE":             {"type": "float", "low": 10.0, "high": 700.0, "mut": 100.0},
    "SURVIVAL_RESERVE_FRACTION": {"type": "float", "low": 0.0, "high": 0.7, "mut": 0.12},
    "ANIMAL_BUY_CAP_PER_TURN":   {"type": "int",   "low": 1, "high": 5, "mut": 1},
    "LAND_BUY_CASH_MULTIPLE":    {"type": "float", "low": 1.2, "high": 8.0, "mut": 0.8},
    "SHED_PANIC_FRACTION":       {"type": "float", "low": 0.4, "high": 0.97, "mut": 0.12},
    "WHEAT_FEED_BUFFER_MULT":    {"type": "float", "low": 1.0, "high": 6.0, "mut": 1.0},
    "RESERVE_PRICE_SCALE":       {"type": "float", "low": 0.1, "high": 1.8, "mut": 0.3},
    # Endgame ramp: end must stay >= start for a real ramp (a degenerate
    # end<start just collapses to a hard cutoff at start -- harmless, not a
    # crash, so no special-casing needed in mutation/crossover). Round 1
    # pegged both near/at their upper bound (29, 30 -- 30 never actually
    # triggers within a 30-day season, i.e. it found the ramp mechanism
    # net-unhelpful for this agent's back-loaded payoff curve and pushed it
    # toward inert). Kept in the search rather than removed: still lets a
    # later round re-enable it if some other change makes it useful again.
    "RAMP_START_DAY":            {"type": "int",   "low": 10, "high": 29, "mut": 4},
    "RAMP_END_DAY":              {"type": "int",   "low": 20, "high": 30, "mut": 3},
    # Score-relative risk. Round 1 found RISK_MULT_BEHIND=1.5 (upper bound --
    # hold out MORE when behind, the opposite of the borrowed heuristic's
    # assumption, because this agent is *supposed* to be behind mid-game on
    # its way to a back-loaded payoff) and RISK_MULT_AHEAD~1.0 (neutral).
    # Widened upward in case the true optimum wants an even stronger hold.
    "RISK_MULT_BEHIND":          {"type": "float", "low": 0.5, "high": 2.2, "mut": 0.25},
    "RISK_MULT_AHEAD":           {"type": "float", "low": 0.5, "high": 1.5, "mut": 0.2},
    # Opponent-production-aware reserve scaling.
    "OPP_SCALE_MAX":             {"type": "float", "low": 1.0, "high": 1.6, "mut": 0.15},
    "OPP_SCALE_MIN":             {"type": "float", "low": 0.3, "high": 1.0, "mut": 0.15},
    "OPP_GROWTH_DISCOUNT_PER_TILE": {"type": "float", "low": 0.0, "high": 0.15, "mut": 0.03},
    "OPP_GROWTH_DISCOUNT_FLOOR":    {"type": "float", "low": 0.4, "high": 1.0, "mut": 0.15},
    # Portfolio mix (tiles assigned via the priority queue, in this order;
    # GOOSE fills whatever's left over). Round-1's fixed guess (13/10/50/12/14)
    # was never itself searched. Bounds are informed by
    # analysis/portfolio_optimizer.py's two-player shared-market model, which
    # found cow/sheep shrink and wheat/goose grow once a symmetric opponent
    # is competing for the same market (see STRATEGY.md section 5/9).
    "TC_COW":                    {"type": "int", "low": 0, "high": 20, "mut": 3},
    "TC_SHEEP":                  {"type": "int", "low": 0, "high": 15, "mut": 3},
    "TC_GOOSE":                  {"type": "int", "low": 0, "high": 30, "mut": 4},
    # 0 = interleave animal types, 1 = finish one type before the next.
    # Measured at the gen-15 portfolio: sheep-first-sequential 67,461 vs
    # interleaved 67,557 (a wash) vs cow-first-sequential 61,786 (clearly
    # worse), so the ordering matters but the best choice is portfolio
    # dependent -- left for the search rather than hardcoded.
    "ANIMALS_SEQUENTIAL":        {"type": "int", "low": 0, "high": 1, "mut": 1},
    "TC_STRAWBERRY":             {"type": "int", "low": 0, "high": 60, "mut": 8},
    "TC_MELON":                  {"type": "int", "low": 0, "high": 25, "mut": 4},
    "TC_WHEAT":                  {"type": "int", "low": 0, "high": 45, "mut": 6},
}

# Seeded from round 1's best (generation 144, fitness 13876.2, see
# search/checkpoints/best_genome_round1.json) rather than the original hand
# guesses, so round 2 starts from a validated-strong point and spends its
# budget exploring the widened bounds / new portfolio dimensions instead of
# re-discovering round 1's findings.
DEFAULT_GENOME = {
    "TARGET_HANDS": 32, "TILES_PER_HAND": 6.99, "SPEND_RESERVE": 75.2,
    "WORK_PER_HAND": 7.0, "ANIMAL_WORK_PER_DAY": 4.0, "CROP_WORK_PER_DAY": 1.5,
    "HIRE_BUDGET_FRACTION": 0.25,
    "SURVIVAL_RESERVE_FRACTION": 0.03, "ANIMAL_BUY_CAP_PER_TURN": 1,
    "LAND_BUY_CASH_MULTIPLE": 4.5, "SHED_PANIC_FRACTION": 0.786,
    "WHEAT_FEED_BUFFER_MULT": 1.91, "RESERVE_PRICE_SCALE": 0.592,
    "RAMP_START_DAY": 29, "RAMP_END_DAY": 30,
    "RISK_MULT_BEHIND": 1.5, "RISK_MULT_AHEAD": 0.968,
    "OPP_SCALE_MAX": 1.273, "OPP_SCALE_MIN": 0.993,
    "OPP_GROWTH_DISCOUNT_PER_TILE": 0.032, "OPP_GROWTH_DISCOUNT_FLOOR": 0.803,
    # Animal-first portfolio. Round 2's "0 animals" optimum was an artifact of
    # three agent bugs (goose filler bomb / SELL-COW aborting market orders /
    # farthest-from-shed tile ordering) that made any animal build unplayable.
    # With those fixed, 7cow+3sheep beats the old all-crop champion 50,481 to
    # 21,628 head to head -- matching both the per-tile economics in
    # STRATEGY.md and what actually wins on the ladder.
    "ANIMALS_SEQUENTIAL": 1,
    "TC_COW": 7, "TC_SHEEP": 3, "TC_GOOSE": 0,
    "TC_STRAWBERRY": 0, "TC_MELON": 0, "TC_WHEAT": 0,
}

# A second seed genome informed by the two-player shared-market analysis
# (STRATEGY.md section 5): more wheat and geese, fewer cow/sheep, since a
# symmetric opponent crashes the animal-product markets faster than a solo
# analysis assumes. Included in the initial population alongside the round-1
# execution-parameter seed so the search can compare both starting points
# rather than requiring mutation to find its way there from scratch.
TWO_PLAYER_GENOME = dict(DEFAULT_GENOME)
TWO_PLAYER_GENOME.update({
    "TC_COW": 13, "TC_SHEEP": 10, "TC_GOOSE": 0,
    "TC_STRAWBERRY": 28, "TC_MELON": 12, "TC_WHEAT": 20,
})


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def random_genome(rng):
    g = {}
    for k, spec in PARAM_SPACE.items():
        if spec["type"] == "int":
            g[k] = rng.randint(spec["low"], spec["high"])
        else:
            g[k] = rng.uniform(spec["low"], spec["high"])
    return g


def mutate(genome, rng, rate=0.5):
    g = dict(genome)
    for k, spec in PARAM_SPACE.items():
        if rng.random() > rate:
            continue
        if spec["type"] == "int":
            step = rng.randint(-spec["mut"], spec["mut"])
            g[k] = int(clamp(g[k] + step, spec["low"], spec["high"]))
        else:
            step = rng.gauss(0, spec["mut"])
            g[k] = clamp(g[k] + step, spec["low"], spec["high"])
    return g


def crossover(a, b, rng):
    return {k: (a[k] if rng.random() < 0.5 else b[k]) for k in PARAM_SPACE}


TC_KEYS = ("TC_COW", "TC_SHEEP", "TC_GOOSE", "TC_STRAWBERRY", "TC_MELON", "TC_WHEAT")
TC_ROLE_OF = {"TC_COW": "COW", "TC_SHEEP": "SHEEP", "TC_GOOSE": "GOOSE",
              "TC_STRAWBERRY": "STRAWBERRY", "TC_MELON": "MELON", "TC_WHEAT": "WHEAT"}


def materialize_params(genome):
    """Genome (flat, search-friendly) -> params dict accepted by agent.configure()."""
    p = {k: v for k, v in genome.items() if k not in ("RESERVE_PRICE_SCALE", *TC_KEYS)}
    p["TARGET_HANDS"] = int(round(p["TARGET_HANDS"]))
    p["ANIMAL_BUY_CAP_PER_TURN"] = int(round(p["ANIMAL_BUY_CAP_PER_TURN"]))
    p["RAMP_START_DAY"] = int(round(p["RAMP_START_DAY"]))
    p["RAMP_END_DAY"] = int(round(p["RAMP_END_DAY"]))
    p["ANIMALS_SEQUENTIAL"] = bool(round(p["ANIMALS_SEQUENTIAL"]))
    scale = genome["RESERVE_PRICE_SCALE"]
    p["RESERVE_PRICE"] = {k: v * scale for k, v in BASE_RESERVE_PRICE.items()}
    p["TARGET_COUNTS"] = {TC_ROLE_OF[k]: int(round(genome[k])) for k in TC_KEYS}
    return p


def fitness_of(results):
    if not results:
        return -1e9
    diffs = [my - opp for my, opp in results]
    return sum(diffs) / len(diffs)


def win_rate_of(results):
    if not results:
        return 0.0
    wins = sum(1 for my, opp in results if my > opp)
    ties = sum(1 for my, opp in results if my == opp)
    return (wins + 0.5 * ties) / len(results)


REPLAY_OPPONENTS = ("hamed_seyed_allaei", "alfandi_hassan")
# Strong public reference agents (extracted from the uploaded notebooks by
# opponents/extract_agents.py). These score 110k-121k against `starter` where
# our best scores ~67k, so they -- not `starter` -- define the target.
REF_OPPONENTS = (
    "kaggriculture-3000-socre",
    "kaggriculture-multi-route-farming-agent",
    "kaggriculture-rank-your-agent",
)


def build_matchups(incumbent_params, seed_base, gen=0, n_self=1):
    """Fitness matchup set, weighted toward genuinely strong opponents.

    History: a signal built on starter/random alone produced a champion that
    won 100% locally and then scored 485 on the real ladder. `starter` is kept
    only as a single cheap sanity game; the real gradient comes from the
    reference agents. They are rotated one per generation rather than all
    three every generation, because each reference episode is far slower than
    a starter episode and evaluating all of them would cut generations/hour
    by more than the extra signal is worth.
    """
    matchups = [("starter", seed_base)]
    s = seed_base + 1
    for _ in range(n_self):
        matchups.append((("self", incumbent_params), s)); s += 1
    ref = REF_OPPONENTS[gen % len(REF_OPPONENTS)]
    matchups.append((("ref", ref), s)); s += 1
    matchups.append((("replay", REPLAY_OPPONENTS[gen % len(REPLAY_OPPONENTS)]), s))
    return matchups


def _default_workers():
    # Heuristic: assume 2-way hyperthreading, use physical core count.
    # Override with --workers if this machine's topology differs.
    logical = os.cpu_count() or 2
    return max(1, logical // 2)


def run_search(population_size=52, generations=200, elite=6, workers=None, seed=0,
                time_budget_seconds=None):
    workers = workers or _default_workers()
    rng = random.Random(seed)

    population = ([dict(DEFAULT_GENOME), dict(TWO_PLAYER_GENOME)]
                  + [random_genome(rng) for _ in range(max(0, population_size - 2))])
    incumbent_genome = dict(DEFAULT_GENOME)
    incumbent_params = materialize_params(incumbent_genome)
    best_fitness_ever = -1e18

    log_path = os.path.join(CKPT_DIR, "search_log.jsonl")
    start = time.time()

    with multiprocessing.Pool(workers) as pool:
        for gen in range(generations):
            if time_budget_seconds and time.time() - start > time_budget_seconds:
                print(f"[search] time budget exhausted at generation {gen}")
                break

            seed_base = seed * 1_000_000 + gen * 1000
            jobs = []
            for i, genome in enumerate(population):
                params = materialize_params(genome)
                matchups = build_matchups(incumbent_params, seed_base + i * 10, gen=gen)
                jobs.append({"cand_id": i, "params": params, "matchups": matchups})

            t0 = time.time()
            # Submit all jobs concurrently, then poll for completion in
            # *whatever order they actually finish*, against one shared
            # deadline for the batch. A naive "get(timeout=...) in submission
            # order" loop blocks on job[0] up to its own timeout even if
            # jobs[1..N] already finished -- that serializes waiting on
            # whichever job happens to be slowest-and-first, which is exactly
            # what stalled the first corrected run. The Pool doesn't kill a
            # timed-out worker task, it just stops waiting on it; that worker
            # frees up once the straggler finishes on its own.
            async_results = [pool.apply_async(evaluate_candidate, (job,)) for job in jobs]
            deadline = t0 + JOB_TIMEOUT
            outputs = [None] * len(jobs)
            pending = set(range(len(jobs)))
            while pending and time.time() < deadline:
                done_now = [i for i in pending if async_results[i].ready()]
                for i in done_now:
                    try:
                        outputs[i] = async_results[i].get()
                    except Exception as e:
                        outputs[i] = {"cand_id": jobs[i]["cand_id"], "results": [], "error": f"EXC: {e!r}"}
                    pending.discard(i)
                if pending:
                    time.sleep(0.2)
            for i in pending:
                outputs[i] = {"cand_id": jobs[i]["cand_id"], "results": [], "error": "TIMEOUT"}
            elapsed = time.time() - t0

            scored = []
            n_errors = 0
            for out in outputs:
                if out["error"]:
                    n_errors += 1
                    scored.append((-1e9, 0.0, out["cand_id"]))
                    continue
                fit = fitness_of(out["results"])
                wr = win_rate_of(out["results"])
                scored.append((fit, wr, out["cand_id"]))
            scored.sort(key=lambda t: t[0], reverse=True)

            best_fit, best_wr, best_id = scored[0]
            best_genome = population[best_id]
            if best_fit > best_fitness_ever:
                best_fitness_ever = best_fit
                incumbent_genome = dict(best_genome)
                incumbent_params = materialize_params(incumbent_genome)
                with open(os.path.join(CKPT_DIR, "best_genome.json"), "w") as f:
                    json.dump({"genome": incumbent_genome, "params": incumbent_params,
                               "fitness": best_fit, "win_rate": best_wr, "generation": gen}, f, indent=2)

            median_fit = scored[len(scored) // 2][0]
            print(f"[gen {gen:>4}] best_fit={best_fit:>9.1f} win_rate={best_wr:.2f} "
                  f"median_fit={median_fit:>9.1f} errors={n_errors} eval_time={elapsed:.1f}s "
                  f"total_time={time.time()-start:.0f}s")

            with open(log_path, "a") as f:
                f.write(json.dumps({"gen": gen, "best_fit": best_fit, "best_wr": best_wr,
                                     "median_fit": median_fit, "n_errors": n_errors,
                                     "elapsed": elapsed, "best_genome": best_genome}) + "\n")

            elite_ids = [t[2] for t in scored[:elite]]
            elites = [population[i] for i in elite_ids]
            next_pop = list(elites)
            while len(next_pop) < population_size - 2:
                if rng.random() < 0.3:
                    a, b = rng.sample(elites, 2) if len(elites) >= 2 else (elites[0], elites[0])
                    child = crossover(a, b, rng)
                else:
                    parent = rng.choice(elites)
                    child = parent
                child = mutate(child, rng, rate=0.5)
                next_pop.append(child)
            next_pop.append(random_genome(rng))
            next_pop.append(random_genome(rng))
            population = next_pop

    return incumbent_genome, incumbent_params, best_fitness_ever


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--population", type=int, default=52)
    ap.add_argument("--generations", type=int, default=200)
    ap.add_argument("--elite", type=int, default=6)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--time-budget", type=float, default=None)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    genome, params, fit = run_search(
        population_size=args.population, generations=args.generations, elite=args.elite,
        workers=args.workers, seed=args.seed, time_budget_seconds=args.time_budget,
    )
    print("=== FINAL BEST ===")
    print(json.dumps({"genome": genome, "params": params, "fitness": fit}, indent=2))
