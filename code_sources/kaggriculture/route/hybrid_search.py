"""Search the strongest reference agent's hand-set runtime constants.

Its 720-step tapes are already optimised and are left untouched. What was never
optimised is the runtime layer wrapped around them -- preemption thresholds,
weed-replay depth, demand smoothing -- which are plain module-level scalars.

The decisive matchup is against the *unmodified* base agent: that is a direct
measurement of whether a tuned constant set actually beats the published one.
Fitness is mean own bank across the matchup set; `beat_base` is reported
separately because that is the number that has to exceed 50%.
"""
import argparse, importlib.util, json, multiprocessing, os, random, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

BASE_PATH = os.path.join(ROOT, "opponents", "kaggriculture-multi-route-farming-agent.py")
CKPT = os.path.join(ROOT, "route", "checkpoints")
os.makedirs(CKPT, exist_ok=True)

PARAM_SPACE = {
    "_PREEMPT_ENABLED":            {"type": "int",   "low": 0,   "high": 1,   "mut": 1},
    "_PREEMPT_FRACTION":           {"type": "float", "low": 0.0, "high": 4.0, "mut": 0.5},
    "_PREEMPT_MAX_BATCH":          {"type": "int",   "low": 1,   "high": 60,  "mut": 8},
    "_PREEMPT_MAX_CLONE_DISTANCE": {"type": "int",   "low": 0,   "high": 40,  "mut": 5},
    "_PREEMPT_MIN_PRICE_RATIO":    {"type": "float", "low": 0.0, "high": 2.0, "mut": 0.25},
    "_PREEMPT_MIN_FUTURE_QUANTITY":{"type": "int",   "low": 0,   "high": 20,  "mut": 3},
    "_PREEMPT_START":              {"type": "int",   "low": 0,   "high": 400, "mut": 50},
    "_PREEMPT_STOP":               {"type": "int",   "low": 400, "high": 719, "mut": 40},
    "_WEED_REPLAY_STEPS":          {"type": "int",   "low": 1,   "high": 24,  "mut": 4},
    "_DEMAND_ALPHA":               {"type": "float", "low": 0.0, "high": 1.0, "mut": 0.15},
}
SEED_DEFAULTS = {   # the published values
    "_PREEMPT_ENABLED": 1, "_PREEMPT_FRACTION": 1.0, "_PREEMPT_MAX_BATCH": 12,
    "_PREEMPT_MAX_CLONE_DISTANCE": 6, "_PREEMPT_MIN_PRICE_RATIO": 0.0,
    "_PREEMPT_MIN_FUTURE_QUANTITY": 4, "_PREEMPT_START": 120, "_PREEMPT_STOP": 680,
    "_WEED_REPLAY_STEPS": 8, "_DEMAND_ALPHA": 0.25,
}
OPPONENTS = ["BASE", "kaggriculture-3000-socre", "kaggriculture-rank-your-agent",
             "v111-8c4s-economic-core-premium-lead"]
_n = [0]


def load_base(params=None):
    _n[0] += 1
    spec = importlib.util.spec_from_file_location(f"hb_{_n[0]}_{os.getpid()}", BASE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for k, v in (params or {}).items():
        if k in PARAM_SPACE:
            setattr(mod, k, bool(v) if k == "_PREEMPT_ENABLED" else v)
    return mod.agent


def evaluate(job):
    from kaggle_environments import make
    from search.evaluate import load_ref_agent
    out = []
    try:
        for opp, seed, seat in job["matchups"]:
            me = load_base(job["params"])
            other = load_base(None) if opp == "BASE" else load_ref_agent(opp)
            pair = [me, other] if seat == 0 else [other, me]
            env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": seed},
                       debug=False)
            env.run(pair)
            f = env.steps[-1]
            mine = float(f[seat].observation["farms"][seat]["money"])
            theirs = float(f[1 - seat].observation["farms"][1 - seat]["money"])
            out.append((opp, mine, theirs))
    except Exception:
        import traceback
        return {"cand_id": job["cand_id"], "results": out, "error": traceback.format_exc()}
    return {"cand_id": job["cand_id"], "results": out, "error": None}


def clamp(spec, v):
    v = max(spec["low"], min(spec["high"], v))
    return int(round(v)) if spec["type"] == "int" else float(v)


def mutate(g, rng, rate=0.35):
    c = dict(g)
    for k, spec in PARAM_SPACE.items():
        if rng.random() < rate:
            c[k] = clamp(spec, c[k] + rng.gauss(0, spec["mut"]))
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--population", type=int, default=32)
    ap.add_argument("--generations", type=int, default=100000)
    ap.add_argument("--elite", type=int, default=6)
    ap.add_argument("--workers", type=int, default=26)
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--time-budget", type=float, default=86400)
    ap.add_argument("--tag", default="hyb1")
    a = ap.parse_args()

    rng = random.Random(a.seed)
    best_path = os.path.join(CKPT, f"best_{a.tag}.json")
    pop = [dict(SEED_DEFAULTS)] + [mutate(SEED_DEFAULTS, rng, 0.5)
                                   for _ in range(a.population - 1)]
    best_fit, t0 = -1e18, time.time()
    ctx = multiprocessing.get_context("forkserver")
    with ctx.Pool(processes=a.workers) as pool:
        for gen in range(a.generations):
            if time.time() - t0 > a.time_budget:
                break
            seeds = [rng.randrange(1, 10 ** 6) for _ in range(3)]
            matchups = ([("BASE", s, i % 2) for i, s in enumerate(seeds)] +
                        [(OPPONENTS[1], seeds[0], 0), (OPPONENTS[2], seeds[1], 1),
                         (OPPONENTS[3], seeds[2], 0)])
            jobs = [{"cand_id": i, "params": g, "matchups": matchups}
                    for i, g in enumerate(pop)]
            try:
                res = pool.map_async(evaluate, jobs).get(timeout=600)
            except multiprocessing.TimeoutError:
                print(f"[gen {gen}] timeout", flush=True); continue
            scored = []
            for r in res:
                if r["error"]:
                    scored.append((-1e9, 0.0, pop[r["cand_id"]])); continue
                mine = [m for _, m, _ in r["results"]]
                vb = [(m, t) for o, m, t in r["results"] if o == "BASE"]
                beat = sum(1 for m, t in vb if m > t) / max(len(vb), 1)
                scored.append((sum(mine) / len(mine), beat, pop[r["cand_id"]]))
            scored.sort(key=lambda x: -x[0])
            if scored[0][0] > best_fit:
                best_fit = scored[0][0]
                json.dump({"genome": scored[0][2], "params": scored[0][2],
                           "fitness": best_fit, "beat_base": scored[0][1], "gen": gen},
                          open(best_path, "w"), indent=2)
            print(f"[gen {gen:>4}] best=${scored[0][0]:>10,.0f} beat_base={scored[0][1]:.2f} "
                  f"median=${scored[len(scored)//2][0]:>10,.0f} t={time.time()-t0:.0f}s", flush=True)
            elites = [g for _, _, g in scored[:a.elite]]
            pop = [dict(g) for g in elites]
            while len(pop) < a.population:
                pop.append(mutate(rng.choice(elites), rng))
    print(f"done best ${best_fit:,.0f} -> {best_path}")


if __name__ == "__main__":
    main()
