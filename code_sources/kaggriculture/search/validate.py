"""Robust final evaluation of a genome/params checkpoint: many more episodes
than the search uses per-generation (which trades sample size for speed), so
we're not reporting a number the GA's noise could have inflated.
"""
import json
import multiprocessing
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from search.evaluate import evaluate_candidate  # noqa: E402
from search.ga_search import fitness_of, win_rate_of  # noqa: E402


def validate(params, n_starter=15, n_random=10, seed_base=999_000, workers=None):
    workers = workers or multiprocessing.cpu_count()
    matchups = ([("starter", seed_base + i) for i in range(n_starter)]
                + [("random", seed_base + 500 + i) for i in range(n_random)])
    # split into per-worker jobs of ~1 matchup each for max parallelism
    jobs = [{"cand_id": i, "params": params, "matchups": [m]} for i, m in enumerate(matchups)]
    with multiprocessing.Pool(workers) as pool:
        outputs = pool.map(evaluate_candidate, jobs)
    results = []
    errors = []
    for out in outputs:
        if out["error"]:
            errors.append(out["error"])
        else:
            results.extend(out["results"])
    return results, errors


if __name__ == "__main__":
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "search", "checkpoints", "best_genome.json")
    with open(path) as f:
        data = json.load(f)
    params = data["params"]
    print(f"validating checkpoint: generation={data.get('generation')} search_fitness={data.get('fitness')}")
    results, errors = validate(params)
    if errors:
        print(f"{len(errors)} episode(s) errored; first:\n{errors[0]}")
    print(f"n_episodes={len(results)}")
    print(f"mean_fitness (my$-opp$)={fitness_of(results):.1f}")
    print(f"win_rate={win_rate_of(results):.3f}")
    my_moneys = [m for m, _ in results]
    opp_moneys = [o for _, o in results]
    print(f"mean my$={sum(my_moneys)/len(my_moneys):.0f}  mean opp$={sum(opp_moneys)/len(opp_moneys):.0f}")
    print(f"min my$={min(my_moneys):.0f}  max my$={max(my_moneys):.0f}")
