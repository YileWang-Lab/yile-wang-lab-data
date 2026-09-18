"""Evaluate one candidate parameter set across a batch of episodes.

Designed to be the unit of work for a multiprocessing.Pool worker: takes a
self-contained job (params + list of (opponent_spec, seed) pairs) and returns
per-episode results. Opponent spec is one of:
  "starter" / "random"      -- kaggle_environments built-ins (WEAK; a fitness
                                signal built only on these is what drove the
                                first search to a 0-animal build that scored
                                485 on the real ladder)
  ("self", other_params)    -- a second isolated instance of this same agent,
                                configured with other_params (e.g. the current
                                incumbent)
  ("replay", name)          -- replay-playback of a real ladder opponent, built
                                by search/make_sparring.py from our own
                                downloaded episodes. Faithful because the two
                                farms are independent and only the market
                                couples them, so the tape reproduces the
                                opponent's real sell pressure at the real times.
"""
import json
import sys
import os
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kaggle_environments import make  # noqa: E402
from search.agent_instance import load_instance  # noqa: E402

EPISODE_STEPS = 720
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPPONENT_DIR = os.path.join(ROOT, "opponents")

_replay_cache = {}


def load_replay(name):
    if name not in _replay_cache:
        with open(os.path.join(OPPONENT_DIR, f"{name}.json")) as f:
            _replay_cache[name] = json.load(f)
    return _replay_cache[name]


def replay_seed(name):
    """A tape is only faithful at the seed it was recorded under."""
    return load_replay(name).get("meta", {}).get("seed")


def make_replay_agent(name):
    """Replay a recorded ladder opponent. Hands are trimmed/padded to whatever
    the live env actually granted this turn -- the tape's hand count can differ
    from ours if a HIRE was refused for lack of cash, and a mismatched hands
    list would otherwise be silently dropped by the interpreter."""
    actions = load_replay(name)["actions"]
    last = len(actions) - 1

    def agent(obs):
        step = int(obs.get("day", 0)) * 24 + int(obs.get("hour", 0))
        a = actions[min(max(step, 0), last)]
        player = obs.get("player", 0)
        farms = obs.get("farms") or []
        n_hands = len(farms[player].get("hands", [])) if player < len(farms) else 0
        hands = [list(h or ["PASS"]) for h in (a.get("hands") or [])][:n_hands]
        hands += [["PASS"]] * (n_hands - len(hands))
        return {"farmer": list(a.get("farmer") or ["PASS"]),
                "hands": hands,
                "market": [list(o) for o in (a.get("market") or [])]}
    return agent


_ref_counter = [0]


def load_ref_agent(name):
    """Load a reference agent from opponents/<name>.py as a FRESH module.

    These agents keep per-episode state in module globals exactly like ours
    does, so a cached import would leak state across episodes (and across
    workers' repeated evaluations) and silently corrupt the benchmark. A new
    module object per episode is cheap next to a 720-step game.
    """
    import importlib.util
    _ref_counter[0] += 1
    path = os.path.join(OPPONENT_DIR, f"{name}.py")
    spec = importlib.util.spec_from_file_location(
        f"ref_{name.replace('-', '_')}_{_ref_counter[0]}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.agent


def resolve_opponent(opponent_spec):
    if isinstance(opponent_spec, tuple):
        kind, arg = opponent_spec[0], opponent_spec[1]
        if kind == "self":
            return load_instance(arg).agent
        if kind == "replay":
            return make_replay_agent(arg)
        if kind == "ref":
            return load_ref_agent(arg)
    return opponent_spec  # "starter" / "random" builtin name


def run_one(params, opponent_spec, seed):
    candidate = load_instance(params)
    opponent = resolve_opponent(opponent_spec)
    if isinstance(opponent_spec, tuple) and opponent_spec[0] == "replay":
        # Pin the tape's own seed; at any other seed it desyncs and the
        # benchmark becomes meaningless (see make_sparring.py).
        seed = replay_seed(opponent_spec[1]) or seed
    env = make("kaggriculture", configuration={"episodeSteps": EPISODE_STEPS, "seed": seed}, debug=False)
    env.run([candidate.agent, opponent])
    final = env.steps[-1]
    my_money = float(final[0].observation["farms"][0]["money"])
    opp_money = float(final[1].observation["farms"][1]["money"])
    return my_money, opp_money


def evaluate_candidate(job):
    """job = {"cand_id": ..., "params": {...}, "matchups": [(opponent_spec, seed), ...]}
    Returns {"cand_id", "results": [(my$, opp$), ...], "error": str|None}."""
    cand_id = job["cand_id"]
    params = job["params"]
    matchups = job["matchups"]
    results = []
    try:
        for opponent_spec, seed in matchups:
            results.append(run_one(params, opponent_spec, seed))
    except Exception:
        return {"cand_id": cand_id, "results": results, "error": traceback.format_exc()}
    return {"cand_id": cand_id, "results": results, "error": None}
