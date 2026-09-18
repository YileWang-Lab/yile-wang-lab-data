"""Persistent opponent pool and gene pool for population-based training."""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "pbt", "state.json")

# The six loadable reference agents. ref_A is the round-robin winner
# (multi-route, 66-72%), not v111 -- v111 measured 5th.
REFS = {
    "ref_A": "kaggriculture-multi-route-farming-agent",
    "ref_B": "kaggriculture-3000-socre",
    "ref_C": "kaggriculture-rank-your-agent",
    "ref_D": "kaggriculture-ttv1",
    "ref_E": "v111-8c4s-economic-core-premium-lead",
    "ref_F": "ref-pipeline-highscore",
}
POOL_MAX = 15
GENE_MAX = 10

# Champion genome from the batch rounds: +17pp over the published agent.
SEED_GENOME = {
    "_PREEMPT_ENABLED": True, "_PREEMPT_FRACTION": 1.0, "_PREEMPT_MAX_BATCH": 30,
    "_PREEMPT_MAX_CLONE_DISTANCE": 6, "_PREEMPT_MIN_PRICE_RATIO": 0.0,
    "_PREEMPT_MIN_FUTURE_QUANTITY": 0, "_PREEMPT_START": 120,
    "_PREEMPT_STOP": 680, "_WEED_REPLAY_STEPS": 8, "_DEMAND_ALPHA": 0.25,
}


def load():
    if os.path.exists(STATE):
        with open(STATE) as f:
            return json.load(f)
    return {
        "round": 0,
        "streak": 0,
        "opponent_pool": [
            {"id": k, "ref": v, "path": None, "score_history": [], "generation": 0}
            for k, v in REFS.items()
        ],
        "gene_pool": [
            {"id": "ref_A", "genome": dict(SEED_GENOME), "rank": 1.0,
             "win_rate": 0.62, "generation": 0}
        ],
        "history": [],
    }


def save(state):
    with open(STATE, "w") as f:
        json.dump(state, f, indent=1)


def prune(state):
    pool = state["opponent_pool"]
    if len(pool) > POOL_MAX:
        non_ref = [p for p in pool if p["id"] not in REFS]
        non_ref.sort(key=lambda p: (p["generation"], p["id"]))
        drop = {id(p) for p in non_ref[:len(pool) - POOL_MAX]}
        state["opponent_pool"] = [p for p in pool if id(p) not in drop]
    genes = state["gene_pool"]
    if len(genes) > GENE_MAX:
        genes.sort(key=lambda g: -g.get("win_rate", 0.0))
        state["gene_pool"] = genes[:GENE_MAX]
