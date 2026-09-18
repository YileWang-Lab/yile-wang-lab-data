"""(mu + lambda) evolution over the route agent's plan genome.

The plan -- portfolio mix, crew size, spend priorities, sell reserves -- is what
this searches; the daily route itself is solved deterministically by
route/router.py and is not part of the genome.

Fitness is mean own-bank across the matchup set rather than margin. We are still
behind the reference agents, and margin against a much stronger fixed opponent
is dominated by their score, which our actions barely move; own-bank is the
signal that actually differentiates candidates while we are climbing. Win rate
is tracked and reported so the switch to margin can be made once it matters.

Reference agents stay in the matchup set at all times: an earlier champion that
was tuned only against `starter` won 100% locally and scored 485 on the real
ladder (HANDOFF pitfall #3).
"""
import argparse
import json
import multiprocessing
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from route.evaluate import evaluate_candidate  # noqa: E402

CKPT_DIR = os.path.join(ROOT, "route", "checkpoints")
os.makedirs(CKPT_DIR, exist_ok=True)

JOB_TIMEOUT = 180

REF_OPPONENTS = [
    # Ordered by measured strength against our build (paired margin, 20 seeds x
    # both seats). kawa is in a class of its own: +1,176 against us where the
    # next-hardest is +13,311.
    "kaggriculture-multi-route-farming-agent",          # kawa  +1,176
    "kaggriculture-frontier-the-soil-remembers-rain",   #       +13,311
    "v111-8c4s-economic-core-premium-lead",             #       +14,798
    "kaggriculture-breaking-the-tie-2883-score",        #       +17,284
    "kaggriculture-rank-your-agent",
    "kaggriculture-3000-socre",
    "15-16-strict-future-v25-meta-reset",               # Kaito Fukami v25, +27,512
    "strong-barnyard-economist",                        #       +33,887
    "kaggriculture-pure-architecture-2600-elo-v3",      #       +39,589
]

PARAM_SPACE = {
    # Portfolio. The single biggest lever: milk sits *below* the market's
    # baseline inventory even in a head-to-head against the 8-cow reference,
    # i.e. the town still wants milk that nobody is supplying.
    "TC_COW":                    {"type": "int",   "low": 0,   "high": 26,  "mut": 3},
    "TC_SHEEP":                  {"type": "int",   "low": 0,   "high": 20,  "mut": 3},
    "TC_GOOSE":                  {"type": "int",   "low": 0,   "high": 30,  "mut": 4},
    "TC_MELON":                  {"type": "int",   "low": 0,   "high": 30,  "mut": 4},
    "TC_STRAWBERRY":             {"type": "int",   "low": 0,   "high": 60,  "mut": 6},
    "TC_WHEAT":                  {"type": "int",   "low": 0,   "high": 40,  "mut": 5},
    # Crew. Sized from routed workload at runtime; these bound it.
    "MAX_HANDS":                 {"type": "int",   "low": 4,   "high": 24,  "mut": 3},
    "HIRE_BUDGET_FRACTION":      {"type": "float", "low": 0.05, "high": 0.9, "mut": 0.12},
    # Spending.
    "SPEND_RESERVE":             {"type": "float", "low": 0.0, "high": 800.0, "mut": 120.0},
    "SURVIVAL_RESERVE_FRACTION": {"type": "float", "low": 0.0, "high": 1.0, "mut": 0.15},
    "WHEAT_FEED_BUFFER_MULT":    {"type": "float", "low": 1.0, "high": 6.0, "mut": 0.7},
    "LAND_BUY_CASH_MULTIPLE":    {"type": "float", "low": 1.0, "high": 5.0, "mut": 0.6},
    "ANIMAL_BUY_CAP_PER_TURN":   {"type": "int",   "low": 1,   "high": 6,   "mut": 1},
    "SEED_BATCH_PER_TURN":       {"type": "int",   "low": 1,   "high": 20,  "mut": 3},
    "BUY_ANIMALS_FIRST":         {"type": "int",   "low": 0,   "high": 1,   "mut": 1},
    # Selling.
    "SHED_PANIC_FRACTION":       {"type": "float", "low": 0.2, "high": 0.95, "mut": 0.12},
    "RAMP_START_DAY":            {"type": "int",   "low": 12,  "high": 29,  "mut": 3},
    "RAMP_END_DAY":              {"type": "int",   "low": 13,  "high": 30,  "mut": 3},
    "RESERVE_PRICE_SCALE":       {"type": "float", "low": 0.2, "high": 2.5, "mut": 0.3},
    # Route: how hard a unit fights to keep the fertilizer round. Low values
    # make it the first thing dropped when a unit is over-subscribed.
    "COLLECT_FERT_VALUE":        {"type": "float", "low": 0.0, "high": 950.0, "mut": 150.0},
    # Whether an idle unit goes looking for marginal work, and how far it will
    # walk for it. Worth +37% vs starter and -4pp head-to-head, so the sign
    # genuinely depends on how contested the market is.
    "IDLE_TOPUP":                {"type": "int",   "low": 0,   "high": 1,   "mut": 1},
    "IDLE_MAX_TRAVEL":           {"type": "int",   "low": 1,   "high": 18,  "mut": 4},
    # Sale timing, lifted from the strongest reference agent's runtime layer.
    "FRONT_RUN":                 {"type": "int",   "low": 0,   "high": 1,   "mut": 1},
    "TERMINAL_STEP":             {"type": "int",   "low": 600, "high": 719, "mut": 25},
    # Opponent modelling: how hard the predicted glut/scarcity ratio is allowed
    # to move our reserve price, and how far ahead it looks.
    "OPP_MODEL":                 {"type": "int",   "low": 0,   "high": 1,   "mut": 1},
    "OPP_SCALE_LO":              {"type": "float", "low": 0.2, "high": 1.0, "mut": 0.15},
    "OPP_SCALE_HI":              {"type": "float", "low": 1.0, "high": 2.5, "mut": 0.25},
    "OPP_HORIZON_DAYS":          {"type": "int",   "low": 1,   "high": 14,  "mut": 3},
    # Planting throttle. High values disable it (no realistic farm ever has 40
    # tiles behind on watering), so the search can switch it off entirely --
    # it is worth +8k vs starter but is a wash head-to-head.
    "PLANT_MISS_TOLERANCE":      {"type": "int",   "low": 0,   "high": 40,  "mut": 6},
    # Which roles claim the near-shed, early-unlocked tiles. A role at the back
    # of the queue lands in quadrants we may never buy and silently does not exist.
    "RP_COW":                    {"type": "float", "low": 0.0, "high": 1.0, "mut": 0.2},
    "RP_SHEEP":                  {"type": "float", "low": 0.0, "high": 1.0, "mut": 0.2},
    "RP_WHEAT":                  {"type": "float", "low": 0.0, "high": 1.0, "mut": 0.2},
    "RP_MELON":                  {"type": "float", "low": 0.0, "high": 1.0, "mut": 0.2},
    "RP_STRAWBERRY":             {"type": "float", "low": 0.0, "high": 1.0, "mut": 0.2},
    "RP_GOOSE":                  {"type": "float", "low": 0.0, "high": 1.0, "mut": 0.2},
    "WHEAT_SELL_SURPLUS":        {"type": "int",   "low": 0,   "high": 1,   "mut": 1},
    # Per-product reserve prices. Previously only a single global scale existed,
    # which cannot express "hold wool, dump milk" -- and measurement showed
    # exactly that split: we realised $19.8/unit on wool where the reference got
    # $61.0, while beating them 4.7x on milk.
    "RES_MILK":                  {"type": "float", "low": 1.0, "high": 260.0, "mut": 30.0},
    "RES_WOOL":                  {"type": "float", "low": 1.0, "high": 260.0, "mut": 30.0},
    "RES_STRAWBERRY":            {"type": "float", "low": 1.0, "high": 260.0, "mut": 30.0},
    "RES_MELON":                 {"type": "float", "low": 1.0, "high": 320.0, "mut": 35.0},
    "RES_FERTILIZER":            {"type": "float", "low": 1.0, "high": 120.0, "mut": 15.0},
    "RES_EGG":                   {"type": "float", "low": 1.0, "high": 80.0,  "mut": 12.0},
    "RES_WHEAT":                 {"type": "float", "low": 1.0, "high": 80.0,  "mut": 12.0},
}

SEED_DEFAULTS = {
    "TC_COW": 8, "TC_SHEEP": 4, "TC_GOOSE": 0, "TC_MELON": 8,
    "TC_STRAWBERRY": 16, "TC_WHEAT": 12, "MAX_HANDS": 16,
    "HIRE_BUDGET_FRACTION": 0.35, "SPEND_RESERVE": 150.0,
    "SURVIVAL_RESERVE_FRACTION": 1 / 3, "WHEAT_FEED_BUFFER_MULT": 2.5,
    "LAND_BUY_CASH_MULTIPLE": 1.6, "ANIMAL_BUY_CAP_PER_TURN": 2,
    "SEED_BATCH_PER_TURN": 4, "BUY_ANIMALS_FIRST": 1,
    "SHED_PANIC_FRACTION": 0.62, "RAMP_START_DAY": 25, "RAMP_END_DAY": 29,
    "RESERVE_PRICE_SCALE": 1.0, "COLLECT_FERT_VALUE": 200.0,
    "IDLE_TOPUP": 0, "IDLE_MAX_TRAVEL": 18,
    "FRONT_RUN": 0, "TERMINAL_STEP": 680,
    "OPP_MODEL": 1, "OPP_SCALE_LO": 0.65, "OPP_SCALE_HI": 1.30, "OPP_HORIZON_DAYS": 6,
    "PLANT_MISS_TOLERANCE": 2,
    "RP_COW": 0.95, "RP_SHEEP": 0.90, "RP_WHEAT": 0.80,
    "RP_MELON": 0.60, "RP_STRAWBERRY": 0.50, "RP_GOOSE": 0.10,
    "WHEAT_SELL_SURPLUS": 0,
    "RES_MILK": 55.0, "RES_WOOL": 60.0, "RES_STRAWBERRY": 45.0, "RES_MELON": 70.0,
    "RES_FERTILIZER": 25.0, "RES_EGG": 20.0, "RES_WHEAT": 12.0,
}


def _clamp(spec, v):
    v = max(spec["low"], min(spec["high"], v))
    return int(round(v)) if spec["type"] == "int" else float(v)


def random_genome(rng):
    g = {}
    for k, spec in PARAM_SPACE.items():
        if spec["type"] == "int":
            g[k] = rng.randint(spec["low"], spec["high"])
        else:
            g[k] = rng.uniform(spec["low"], spec["high"])
    return g


def mutate(genome, rng, rate=0.3):
    child = dict(genome)
    for k, spec in PARAM_SPACE.items():
        if rng.random() < rate:
            child[k] = _clamp(spec, child[k] + rng.gauss(0, spec["mut"]))
    return child


def crossover(a, b, rng):
    return {k: (a[k] if rng.random() < 0.5 else b[k]) for k in PARAM_SPACE}


def sanitise(genome):
    """Constraints the genome cannot express. A portfolio bigger than the board
    is silently truncated by the layout builder anyway; the ramp must not invert."""
    g = dict(genome)
    if g["RAMP_END_DAY"] <= g["RAMP_START_DAY"]:
        g["RAMP_END_DAY"] = min(30, g["RAMP_START_DAY"] + 1)
    return g


def to_params(genome):
    p = sanitise(genome)
    # RES_* are flattened in the genome (the ES only mutates scalars) and are
    # rebuilt into the per-product dict the agent's configure() expects.
    reserve = {item: p.pop("RES_" + item) for item in
               ("MILK", "WOOL", "STRAWBERRY", "MELON", "FERTILIZER", "EGG", "WHEAT")
               if "RES_" + item in p}
    if reserve:
        p["RESERVE_PRICE"] = reserve
    return p


def build_matchups(gen, rng, incumbent):
    """Real opponents only, and both seat orders.

    `starter` was dropped: an earlier champion tuned with it in the mix won
    every local game and scored 485 on the ladder (pitfall #3). Seeds are drawn
    from the ladder's own 32-bit range rather than 1..10^6, and each reference is
    played from BOTH seats on the same seed -- seat is not neutral here, so a
    one-sided sample rewards genomes that happen to suit seat 0.
    """
    ref_a = REF_OPPONENTS[0]
    ref_b = REF_OPPONENTS[1 + (gen % (len(REF_OPPONENTS) - 1))]
    s1, s2 = (rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(2))
    matchups = [(("ref", ref_a), s1, 0), (("ref", ref_a), s1, 1),
                (("ref", ref_b), s2, 0), (("ref", ref_b), s2, 1)]
    if incumbent is not None:
        s3 = rng.randrange(10 ** 6, 2 ** 31 - 1)
        matchups.append((("route", incumbent), s3, 0))
        matchups.append((("route", incumbent), s3, 1))
    return matchups


def score(results):
    """Mean MARGIN, not mean own bank.

    Own bank rewards a genome for playing a rich seed, not for being better than
    the opponent it faced; margin is what the ladder actually pays. Seats are
    paired in build_matchups, so the seat term cancels in the mean.
    """
    if not results:
        return -1e9, 0.0
    margins = [a - b for a, b in results]
    wins = sum(1 for a, b in results if a > b)
    return sum(margins) / len(margins), wins / len(results)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--population", type=int, default=40)
    ap.add_argument("--generations", type=int, default=20000)
    ap.add_argument("--elite", type=int, default=6)
    ap.add_argument("--workers", type=int, default=26)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--time-budget", type=float, default=43200)
    ap.add_argument("--tag", default="route1")
    ap.add_argument("--seed-genome", default=None,
                    help="path to a best_*.json to seed the population from")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    best_path = os.path.join(CKPT_DIR, f"best_{args.tag}.json")
    log_path = os.path.join(CKPT_DIR, f"log_{args.tag}.jsonl")

    base = dict(SEED_DEFAULTS)
    if args.seed_genome and os.path.exists(args.seed_genome):
        with open(args.seed_genome) as f:
            saved = json.load(f).get("genome") or {}
        # Keys added since that run was saved keep their default.
        base.update({k: v for k, v in saved.items() if k in PARAM_SPACE})
        print(f"seeded from {args.seed_genome}", flush=True)
    population = [dict(base), dict(SEED_DEFAULTS)]
    population += [mutate(base, rng, rate=0.4) for _ in range(args.population // 3)]
    population += [mutate(SEED_DEFAULTS, rng, rate=0.5) for _ in range(args.population // 4)]
    population += [random_genome(rng) for _ in range(args.population - len(population))]

    best_genome, best_fit = None, -1e18
    incumbent = None
    t_start = time.time()

    ctx = multiprocessing.get_context("forkserver")
    with ctx.Pool(processes=args.workers) as pool:
        for gen in range(args.generations):
            if time.time() - t_start > args.time_budget:
                break
            matchups = build_matchups(gen, rng, incumbent)
            jobs = [{"cand_id": i, "params": to_params(g), "matchups": matchups}
                    for i, g in enumerate(population)]
            t0 = time.time()
            try:
                out = pool.map_async(evaluate_candidate, jobs).get(timeout=JOB_TIMEOUT)
            except multiprocessing.TimeoutError:
                print(f"[gen {gen:>4}] generation timed out, skipping", flush=True)
                continue
            eval_time = time.time() - t0

            scored, n_err = [], 0
            for res in out:
                if res["error"]:
                    n_err += 1
                    scored.append((-1e9, 0.0, population[res["cand_id"]]))
                    continue
                fit, wr = score(res["results"])
                scored.append((fit, wr, population[res["cand_id"]]))
            scored.sort(key=lambda t: -t[0])

            if scored[0][0] > best_fit:
                best_fit, best_genome = scored[0][0], dict(scored[0][2])
                with open(best_path, "w") as f:
                    json.dump({"genome": best_genome, "params": to_params(best_genome),
                               "fitness": best_fit, "gen": gen}, f, indent=2)
            incumbent = to_params(scored[0][2])

            median = scored[len(scored) // 2][0]
            print(f"[gen {gen:>4}] best_fit={scored[0][0]:>10,.0f} win_rate={scored[0][1]:.2f} "
                  f"median_fit={median:>10,.0f} errors={n_err} eval_time={eval_time:.1f}s "
                  f"total_time={time.time() - t_start:.0f}s", flush=True)
            with open(log_path, "a") as f:
                f.write(json.dumps({"gen": gen, "best": scored[0][0], "win_rate": scored[0][1],
                                    "median": median, "genome": scored[0][2]}) + "\n")

            elites = [g for _, _, g in scored[:args.elite]]
            new_pop = [dict(g) for g in elites]
            while len(new_pop) < args.population - 2:
                if rng.random() < 0.25 and len(elites) > 1:
                    a, b = rng.sample(elites, 2)
                    new_pop.append(mutate(crossover(a, b, rng), rng))
                else:
                    new_pop.append(mutate(rng.choice(elites), rng))
            new_pop += [random_genome(rng) for _ in range(args.population - len(new_pop))]
            population = new_pop

    print(f"done. best fitness ${best_fit:,.0f} -> {best_path}")


if __name__ == "__main__":
    main()
