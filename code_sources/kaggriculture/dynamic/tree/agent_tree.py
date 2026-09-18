"""A standalone decision-tree agent. No action table anywhere at runtime.

THE POINT. The tape's 7,190-entry table is uneditable -- change one entry and
every later entry's assumptions break silently (HANDOFF section 4, confirmed
four times). This replaces it with state-conditional rules: "when the board
looks like this, do that". Those have no downstream assumptions, so any single
rule can be rewritten, deleted or hand-tuned without breaking the rest.

TWO STAGES, because one tree cannot do both jobs. Measured on held-out games:

    tile ops (water/harvest/feed/...)   82.4%   +49.3 over majority
    movement, predicted directly        26.0%   -0.4  (worse than guessing)
    movement, via target + path         56.3%   +23.2

Movement fails as a direct state-to-action map because a unit steps north on
turn 6 for where it means to be on turn 12, and that intention is not in the
current tile. Predicting the TARGET instead is a function of state, and the
step toward a target is arithmetic. So:

    stage 1   op tree      -> what to do, or MOVE
    stage 2   target tree  -> which way, when stage 1 says MOVE

Both are depth-limited CART over the same 30 named features, so every leaf is
a readable conjunction of conditions on quantities like `here_yield`,
`here_unwatered`, `dist_shed`, `day`.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _HERE]
sys.path.insert(0, ROOT)

from dynamic.tree.fit import grow                                # noqa: E402
from dynamic.tree.perturn import (FEATURES, OPS, _agg, _unit_pos,  # noqa: E402
                                  unit_features)

MOVES = ("NORTH", "SOUTH", "EAST", "WEST")
OUT = os.path.join(ROOT, "logs", "tree", "agent_trees.json")

# Ops the agent may emit at a tile. PLANT and PLACE carry an argument, so they
# are predicted as a bare op and the argument filled from what the unit holds.
TILE_OPS = ("WATER", "HARVEST", "FEED", "CARE", "FERTILIZE",
            "COLLECT_FERTILIZER", "DIG", "PLANT", "PLACE",
            "BUILD_COOP", "BUILD_PASTURE", "PICKUP", "DROP")


def _serialise(node):
    """Node objects -> plain dicts, so a trained tree is a readable JSON file."""
    if node is None:
        return None
    if node.feat is None:
        return {"leaf": node.pred, "n": node.n}
    return {"feat": node.feat, "thr": node.thr, "n": node.n,
            "left": _serialise(node.left), "right": _serialise(node.right)}


def _walk(d, x):
    """Predict from the serialised form -- what the shipped agent runs."""
    while d is not None and "leaf" not in d:
        d = d["left"] if x[d["feat"]] <= d["thr"] else d["right"]
    return (d or {}).get("leaf", 0)


def as_rules(d, names, ops, depth=0, path=(), out=None, min_n=40):
    """The tree as text: one line per leaf, conditions and all."""
    out = [] if out is None else out
    if d is None:
        return out
    if "leaf" in d:
        if d.get("n", 0) >= min_n:
            cond = " and ".join(path) if path else "always"
            out.append(f"  if {cond}:  -> {ops[d['leaf']]}   (n={d['n']})")
        return out
    f, t = names[d["feat"]], d["thr"]
    as_rules(d["left"], names, ops, depth + 1, path + (f"{f} <= {t:g}",), out)
    as_rules(d["right"], names, ops, depth + 1, path + (f"{f} > {t:g}",), out)
    return out


class TreeAgent:
    """Stage 1 picks the op; stage 2 picks the direction when it says MOVE."""

    def __init__(self, op_tree, move_tree, seeds_hint=None):
        self.op_tree = op_tree
        self.move_tree = move_tree
        self.seeds_hint = seeds_hint or {}

    # ------------------------------------------------------------- inference
    def _unit_action(self, farm, opp, priv, idx, day, hour, cash, agg):
        x = unit_features(farm, opp, priv, idx, day, hour, cash, agg)
        op = OPS[_walk(self.op_tree, x)]
        if op in MOVES:
            d = _walk(self.move_tree, x)
            return [MOVES[d]] if 0 <= d < len(MOVES) else ["PASS"]
        if op == "PLANT":
            seeds = priv.get("seeds") or {}
            best = max(seeds, key=lambda c: seeds.get(c, 0)) if seeds else None
            return ["PLANT", best] if seeds.get(best, 0) > 0 else ["PASS"]
        if op == "PLACE":
            shed = priv.get("shed") or {}
            for a in ("COW", "SHEEP", "GOOSE"):
                if int(shed.get(a, 0) or 0) > 0:
                    return ["PLACE", a]
            return ["PASS"]
        return [op]

    def agent(self, obs, config=None):
        o = obs if isinstance(obs, dict) else dict(obs)
        seat = int(o.get("player", 0) or 0)
        farms = o.get("farms") or []
        if not farms or seat >= len(farms):
            return {"farmer": ["PASS"], "hands": [], "market": []}
        farm = farms[seat]
        opp = farms[1 - seat] if len(farms) > 1 else {}
        priv = o.get("private") or {}
        day, hour = int(o.get("day", 0) or 0), int(o.get("hour", 0) or 0)
        cash = float(farm.get("money", 0) or 0)
        agg = _agg(farm, opp, float(opp.get("money", 0) or 0))
        n_hands = len(farm.get("hands") or [])
        farmer = self._unit_action(farm, opp, priv, 0, day, hour, cash, agg)
        hands = [self._unit_action(farm, opp, priv, i + 1, day, hour, cash, agg)
                 for i in range(n_hands)]
        return {"farmer": farmer, "hands": hands,
                "market": self._market(farm, priv, day, hour, n_hands)}

    def _market(self, farm, priv, day, hour, n_hands):
        """Market orders are NOT from a tree.

        They are a handful of explicit economic rules, because the market is the
        one place where we already have exact models -- `market_model` mirrors
        the engine's price curve bit for bit -- and a tree fitted to someone
        else's order log would be strictly worse than the arithmetic.
        """
        out = []
        shed = dict(priv.get("shed") or {})
        cash = float(farm.get("money", 0) or 0)
        if hour <= 1 and n_hands < 12 and cash > 400:
            out.append(["HIRE"])
        animals = sum(1 for row in farm.get("tiles", [])
                      for t in row if isinstance(t, dict) and t.get("animal"))
        need = max(0, int(animals * 2) - int(shed.get("WHEAT", 0) or 0))
        if need > 0 and cash > 300:
            out.append(["BUY_PRODUCT", "WHEAT", min(need, 20)])
        for item in ("MELON", "WOOL", "MILK", "STRAWBERRY", "EGG",
                     "FERTILIZER"):
            have = int(shed.get(item, 0) or 0)
            if have > 0:
                out.append(["SELL", item, have])
        return out[:10]


def train(games, depth_op=8, depth_move=8, min_leaf=25):
    """Fit both stages. `games` is a list of [(features, op_index)] lists."""
    rows = [r for g in games for r in g]
    X = [x for x, _y in rows]
    y = [_y for _x, _y in rows]
    op_tree = grow(X, y, range(len(FEATURES)), depth_op, min_leaf=min_leaf)
    mv = [(x, OPS[o]) for x, o in rows if OPS[o] in MOVES]
    move_tree = grow([x for x, _d in mv],
                     [MOVES.index(d) for _x, d in mv],
                     range(len(FEATURES)), depth_move, min_leaf=min_leaf)
    return op_tree, move_tree


def save(op_tree, move_tree, path=OUT):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump({"features": FEATURES, "ops": OPS, "moves": MOVES,
               "op_tree": _serialise(op_tree),
               "move_tree": _serialise(move_tree)}, open(path, "w"))
    return path


def load(path=OUT):
    blob = json.load(open(path))
    return TreeAgent(blob["op_tree"], blob["move_tree"])
