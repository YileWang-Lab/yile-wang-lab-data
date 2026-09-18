"""Evaluate one route-agent genome across a batch of episodes.

Mirrors search/evaluate.py, but loads route/agent.py instead of agent/main.py.
Kept as a separate file so the route work never touches anything the currently
running parameter search imports (HANDOFF pitfall #2).
"""
import importlib.util
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kaggle_environments import make  # noqa: E402
from search.evaluate import load_ref_agent, make_replay_agent, replay_seed  # noqa: E402

EPISODE_STEPS = 720
AGENT_PATH = os.path.join(ROOT, "route", "agent.py")
_counter = [0]


def load_route_instance(params=None):
    """Fresh module per episode: the agent keeps the day's tours and layout in
    module globals, so a cached import would leak state across episodes and
    silently corrupt the benchmark."""
    _counter[0] += 1
    spec = importlib.util.spec_from_file_location(f"route_agent_{_counter[0]}", AGENT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if params:
        mod.configure(params)
    else:
        mod._reset_state()
    return mod


def resolve_opponent(spec):
    if isinstance(spec, (tuple, list)):
        kind, arg = spec[0], spec[1]
        if kind == "route":
            return load_route_instance(arg).agent
        if kind == "ref":
            return load_ref_agent(arg)
        if kind == "replay":
            return make_replay_agent(arg)
    return spec


def run_one(params, opponent_spec, seed, seat=0):
    candidate = load_route_instance(params)
    opponent = resolve_opponent(opponent_spec)
    if isinstance(opponent_spec, (tuple, list)) and opponent_spec[0] == "replay":
        seed = replay_seed(opponent_spec[1]) or seed
    env = make("kaggriculture", configuration={"episodeSteps": EPISODE_STEPS, "seed": seed},
               debug=False)
    pair = [candidate.agent, opponent] if seat == 0 else [opponent, candidate.agent]
    env.run(pair)
    final = env.steps[-1]
    return (float(final[seat].observation["farms"][seat]["money"]),
            float(final[1 - seat].observation["farms"][1 - seat]["money"]))


def evaluate_candidate(job):
    results = []
    try:
        for m in job["matchups"]:
            opponent_spec, seed = m[0], m[1]
            seat = m[2] if len(m) > 2 else 0
            results.append(run_one(job["params"], opponent_spec, seed, seat))
    except Exception:
        return {"cand_id": job["cand_id"], "results": results, "error": traceback.format_exc()}
    return {"cand_id": job["cand_id"], "results": results, "error": None}
