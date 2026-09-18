"""Extract each unit's TARGET tile from the tape, and test whether it is learnable.

WHY THIS AND NOT THE PREVIOUS ATTEMPT. `dynamic/tree/perturn.py` measured that
the tape's tile operations are learnable (82.4% held out, +49.3 over majority)
and its MOVEMENT is not (26.0% against a 26.3% majority -- worse than guessing).
Movement is 50.7% of everything it does.

The reason is structural: a unit steps north on turn 6 because of where it means
to be on turn 12, and that intention is not in the current tile, the cash, or
the opponent. No state-to-action function can express it.

But state-to-GOAL can. Decompose:

    move_t = Path(pos_t -> target)      deterministic, Manhattan, no learning
    target = f(state)                   a function, and therefore learnable

This file does the first half of that claim honestly: extract the targets, then
measure whether they are predictable at all. If they are not, the decomposition
buys nothing and we stop here rather than building a pipeline on top of it.

TARGET EXTRACTION IS A READABLE HEURISTIC, not a model: a unit's target is the
tile where a run of moves ENDS. Walk the trajectory, and whenever a unit issues
a tile operation, label every preceding consecutive move in that day with that
tile. Moves that never lead to an operation are labelled "no target" -- those
are repositioning, and treating them as goal-directed would be inventing data.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _HERE]
sys.path.insert(0, ROOT)

from dynamic.tree.perturn import (OPS, TAPE, _agg, _mk, _unit_pos,  # noqa: E402
                                  unit_features)

MOVES = {"NORTH", "SOUTH", "EAST", "WEST"}
TILE_OPS = {"WATER", "HARVEST", "FEED", "CARE", "PLANT", "PLACE", "FERTILIZE",
            "COLLECT_FERTILIZER", "DIG", "BUILD_COOP", "BUILD_PASTURE"}
OPPS = ["v111-8c4s-economic-core-premium-lead", "kaggriculture-3000-socre"]
OUT = os.path.join(ROOT, "logs", "tree", "targets.json")


def collect(seed, opp_name):
    """One tape game -> rows of (features, target) for MOVING units.

    Two passes: play the game recording each unit's ops and positions, then walk
    each unit's day backwards so a tile op labels the moves that led to it.
    """
    from planner.simulate import Simulator, _agent_caller
    me, op = _mk(TAPE), _mk(os.path.join("opponents", opp_name + ".py"))
    sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
    c0, c1 = _agent_caller(me), _agent_caller(op)
    log = []
    while sim.step < 719:
        o = sim.observation_for(0)
        farm, opp = o["farms"][0], o["farms"][1]
        priv = sim.privates[0]
        day, hour = o["day"], o["hour"]
        agg = _agg(farm, opp, float(opp.get("money", 0)))
        a = c0(o, sim.cfg)
        if isinstance(a, dict):
            units = [a.get("farmer")] + list(a.get("hands") or [])
            for idx, u in enumerate(units):
                if not u:
                    continue
                log.append({"day": day, "hour": hour, "idx": idx,
                            "op": u[0], "pos": _unit_pos(farm, idx),
                            "x": unit_features(farm, opp, priv, idx, day, hour,
                                               float(farm.get("money", 0)), agg)})
        sim.step_actions(a, c1(sim.observation_for(1), sim.cfg))

    # label: a tile op assigns its tile as the target of the moves before it,
    # within the same day and the same unit
    rows = []
    by = {}
    for e in log:
        by.setdefault((e["day"], e["idx"]), []).append(e)
    for _k, seq in by.items():
        pending = []
        for e in seq:
            if e["op"] in MOVES:
                pending.append(e)
            elif e["op"] in TILE_OPS:
                for p in pending:
                    rows.append((p["x"], e["pos"], p["pos"]))
                pending = []
            else:
                pending = []
    return rows


def main():
    n_seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    import random
    rng = random.Random(4321)
    seeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(n_seeds)]
    games = []
    for i, s in enumerate(seeds):
        for opp in OPPS:
            g = collect(s, opp)
            games.append(g)
            print(f"  seed {i + 1}/{n_seeds} vs {opp[:20]}: +{len(g):,} moves "
                  f"with a target (total {sum(len(x) for x in games):,})",
                  flush=True)
    json.dump({"games": [[(x, list(t), list(p)) for x, t, p in g]
                         for g in games]}, open(OUT, "w"))
    n = sum(len(g) for g in games)
    print(f"\n{n:,} goal-directed moves -> {OUT}")


if __name__ == "__main__":
    main()
