"""GA over dynamic/agent2.py, re-run on top of this session's valuation work.

The genome in `dynamic/best_genome.json` was searched against `dynamic/agent.py`
BEFORE any of the market model, the opportunity allocator or the ENPV veto
existed, and it peaked at generation 1 and then went 17 generations without
improving. It is an optimum of a different agent.

That matters because of the pattern this session established: additive and
subtractive changes hold (+2,865 allocator, +4,208 veto) while every wholesale
replacement breaks (-53,163 free-argmax layout, -90,059 knapsack purchasing,
-12,542 even for a pure re-ordering of the same purchases). The reading is that
the genome's parameters are CO-ADAPTED, so a hand-written subsystem dropped on
top of them fights the co-adaptation. A search does not have that problem: it
re-adapts everything at once.

So this run seeds from the current shipped configuration -- allocator and veto
on -- and lets the portfolio and the cash-flow split move together, with the two
new labour prices in the genome. Fitness is unchanged: paired margin with common
random numbers over the pool, both seats, ladder-range seeds.

DO NOT EDIT dynamic/agent2.py WHILE THIS RUNS. Workers re-exec the file per
evaluation, so an edit silently corrupts the fitness signal.
"""
"""Original header, for the run that produced best_genome.json:
Overnight GA over dynamic/agent.py, targeting the cash-flow tradeoff.

Six expansion hypotheses were refuted tonight, and together they identify one
constraint rather than six problems: CAPITAL AND LABOUR COMPETE FOR THE SAME
CASH, and labour is what converts capital into product.

    proportional scale-up        -87,245
    crew floor (MIN_CREW)        -52,000
    crew + tiles together        -62,285
    cycling-crop portfolios     -150,176
    geese (uncapped market)     -183,427
    front-loaded purchases   t62 -29,537 / t74 -42,897 vs the same tiles bought slowly

The last one is the tell: front-loading did not just fail, it CUT work turns
(2,290 -> 1,840 at 62 tiles), because cash spent on assets early is cash not
available to hire. At 50 tiles the planner sits at the optimum of that tradeoff
and earns more per work-turn than the tape does.

So this search does not sweep size again. It sweeps the knobs that set the
cash-flow split -- hire budget share, spend reserve, purchase throttles, feed
buffer, land threshold -- plus the schedule controls, and lets portfolio move
only slowly around the known optimum. Fitness is paired margin with common
random numbers over the full 9-agent pool, both seats.
"""
import argparse, importlib.util, json, multiprocessing, os, random, statistics, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HERE = os.path.dirname(os.path.abspath(__file__))
# Running this as a script puts dynamic/ on sys.path[0], where dynamic/search.py
# shadows the top-level `search` package that route.evaluate imports -- which
# surfaces as a circular-import error inside route.search. Strip it. This must
# run at module scope so forkserver workers, which re-import this module, get it
# too.
sys.path[:] = [q for q in sys.path if os.path.abspath(q or ".") != _HERE]
sys.path.insert(0, ROOT)
from planner.simulate import Simulator  # noqa: E402
from route.search import to_params  # noqa: E402

DYN = os.path.join(ROOT, "dynamic", "agent2.py")
CKPT = os.path.join(ROOT, "dynamic", "best_genome2.json")
LOG_DIR = os.path.join(ROOT, "logs", "dynamic_optimization2")
os.makedirs(LOG_DIR, exist_ok=True)
PROGRESS = os.path.join(LOG_DIR, "PROGRESS.md")

POOL = ["kaggriculture-multi-route-farming-agent",
        "v111-8c4s-economic-core-premium-lead",
        "kaggriculture-frontier-the-soil-remembers-rain",
        "kaggriculture-3000-socre",
        "kaggriculture-breaking-the-tie-2883-score",
        "kaggriculture-rank-your-agent",
        "15-16-strict-future-v25-meta-reset",
        "strong-barnyard-economist",
        "kaggriculture-pure-architecture-2600-elo-v3"]

# cash-flow knobs get wide ranges; portfolio moves only slightly, because
# planner/role_gradient.py measured all 24 single-role perturbations negative
CASH = {
    "HIRE_BUDGET_FRACTION": (0.15, 0.95),
    "SPEND_RESERVE": (60.0, 700.0),
    "SURVIVAL_RESERVE_FRACTION": (0.02, 0.60),
    "WHEAT_FEED_BUFFER_MULT": (0.6, 3.5),
    "LAND_BUY_CASH_MULTIPLE": (1.02, 2.6),
    "ANIMAL_BUY_CAP_PER_TURN": (1, 6),
    "SEED_BATCH_PER_TURN": (2, 24),
    "MAX_HANDS": (8, 26),
    "SHED_PANIC_FRACTION": (0.15, 0.90),
    "RESERVE_PRICE_SCALE": (0.5, 3.0),
    "TERMINAL_STEP": (600, 700),
    "RAMP_START_DAY": (20, 29),
    # Hand-calibrated this session to 13 (crop allocator, flat plateau 13-17)
    # and 8 (ENPV veto, stable across three seed sets). Both are marginal
    # $/unit-turn prices, so the search can re-fit them against whatever
    # portfolio it settles on.
    "ALLOC_LABOR": (4.0, 22.0),
    "ENPV_LABOR": (3.0, 20.0),
}
PORT = {"TC_COW": (3, 9), "TC_SHEEP": (3, 10), "TC_GOOSE": (0, 5),
        "TC_MELON": (4, 12), "TC_STRAWBERRY": (14, 26), "TC_WHEAT": (4, 16)}
FLAGS = {"SCHEDULE_DRIVEN": (0, 1), "BUY_ANIMALS_FIRST": (0, 1),
         "IDLE_TOPUP": (0, 1), "FRONT_RUN": (0, 1), "OPP_MODEL": (0, 1),
         # This session's switches. ALLOC_MODE stays at 1 -- 2 measured
         # -53,163 -- and ENPV_BUY stays off for the same reason, so neither
         # is in the search space.
         "ENPV_VETO": (0, 1), "NURSE_LATE": (0, 1)}
_n = [0]


def _load(path, params=None):
    _n[0] += 1
    s = importlib.util.spec_from_file_location(f"ds_{os.getpid()}_{_n[0]}", path)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    if params is not None:
        m.configure(params); return m.agent
    return getattr(m, "_submission_entry", None) or m.agent


def mutate(g, rng, rate=0.3):
    out = dict(g)
    for k, (lo, hi) in {**CASH, **PORT}.items():
        if rng.random() > rate:
            continue
        cur = out.get(k, (lo + hi) / 2)
        if isinstance(lo, int) and isinstance(hi, int):
            out[k] = max(lo, min(hi, int(round(cur + rng.choice([-2, -1, 1, 2])))))
        else:
            out[k] = max(lo, min(hi, cur * (1.0 + rng.uniform(-0.35, 0.35))))
    for k, (lo, hi) in FLAGS.items():
        if rng.random() < rate * 0.5:
            out[k] = rng.randint(lo, hi)
    return out


def crossover(a, b, rng):
    return {k: (a[k] if rng.random() < 0.5 else b.get(k, a[k])) for k in a}


def play(job):
    gid, params, opp, seed, seat = job
    try:
        me = _load(DYN, params)
        op = _load(os.path.join(ROOT, "opponents", f"{opp}.py"))
        pair = [me, op] if seat == 0 else [op, me]
        sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
        m0, m1 = sim.run_episode(pair[0], pair[1])
        us, them = (m0, m1) if seat == 0 else (m1, m0)
        return (gid, opp, seed, seat, us - them, None)
    except Exception:
        import traceback
        return (gid, opp, seed, seat, -1e9, traceback.format_exc()[-150:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--population", type=int, default=96)
    ap.add_argument("--generations", type=int, default=400)
    ap.add_argument("--elite", type=int, default=10)
    ap.add_argument("--seeds", type=int, default=6)
    ap.add_argument("--workers", type=int, default=26)
    ap.add_argument("--patience", type=int, default=50)
    ap.add_argument("--hours", type=float, default=9.0)
    args = ap.parse_args()

    seed_genome = json.load(open(os.path.join(ROOT, "dynamic",
                                              "best_genome.json")))["genome"]
    base = to_params(dict(seed_genome))
    base["SCHEDULE_DRIVEN"] = 0
    # the shipped defaults this session established
    base.update({"OPP_MODEL": 1, "ALLOC_MODE": 1, "ALLOC_LABOR": 13.0,
                 "ENPV_VETO": 1, "ENPV_LABOR": 8.0, "NURSE_LATE": 1})
    rng = random.Random(20260820)
    pop = [dict(base)] + [mutate(base, rng, 0.4) for _ in range(args.population - 1)]

    best, best_fit, stale = dict(base), -1e18, 0
    t0 = time.time()
    with open(os.path.join(LOG_DIR, "search.log"), "w") as f:
        f.write("")

    for gen in range(args.generations):
        if time.time() - t0 > args.hours * 3600:
            print("time budget reached", flush=True); break
        seeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(args.seeds)]
        jobs = [(i, g, o, s, seat) for i, g in enumerate(pop)
                for o in POOL for s in seeds for seat in (0, 1)]
        with multiprocessing.get_context("forkserver").Pool(args.workers) as pool:
            res = pool.map(play, jobs, chunksize=8)
        paired = {}
        for gid, opp, sd, seat, m, err in res:
            paired.setdefault((gid, opp, sd), []).append(m)
        fit = {}
        for (gid, opp, sd), v in paired.items():
            if len(v) == 2 and min(v) > -1e8:
                fit.setdefault(gid, []).append(sum(v))
        scored = sorted(((statistics.mean(v), gid) for gid, v in fit.items() if v),
                        reverse=True)
        if not scored:
            print("all genomes errored", flush=True); break
        gbest, gid = scored[0]
        improved = gbest > best_fit + 1.0
        if improved:
            best_fit, best, stale = gbest, dict(pop[gid]), 0
            json.dump({"genome": best, "fitness": best_fit, "gen": gen},
                      open(CKPT, "w"), indent=1)
        else:
            stale += 1
        line = (f"gen {gen:>4} best {gbest:>+12,.0f}  overall {best_fit:>+12,.0f}  "
                f"median {statistics.median(s for s, _ in scored):>+12,.0f}  "
                f"stale {stale}  {time.time()-t0:.0f}s")
        print(line, flush=True)
        with open(os.path.join(LOG_DIR, "search.log"), "a") as f:
            f.write(line + "\n")
        with open(PROGRESS, "w") as f:
            f.write(f"# dynamic/ GA progress\n\n{time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    f"- generation {gen}/{args.generations}, {(time.time()-t0)/3600:.2f}h\n"
                    f"- best paired margin vs 9-agent pool: **{best_fit:+,.0f}**\n"
                    f"- reference on the SAME pool and seeds: shipped "
                    f"tape+market **+12,160**, unmodified kawa **+11,628**, "
                    f"this session's hand-tuned agent2 **-73,390**\n"
                    f"- generations since improvement: {stale}/{args.patience}\n\n"
                    f"Re-searching on top of the opportunity allocator and the\n"
                    f"ENPV veto. The old genome is an optimum of a different\n"
                    f"agent: it was searched before any of the market model\n"
                    f"existed, and it peaked at generation 1.\n")
        if stale >= args.patience:
            print(f"plateau after {stale} generations", flush=True); break
        elites = [pop[g] for _, g in scored[:args.elite]]
        newpop = list(elites)
        while len(newpop) < args.population:
            a, b = rng.choice(elites), rng.choice(elites)
            newpop.append(mutate(crossover(a, b, rng), rng))
        pop = newpop

    print(f"DONE best {best_fit:+,.0f} after {(time.time()-t0)/3600:.2f}h", flush=True)


if __name__ == "__main__":
    main()
