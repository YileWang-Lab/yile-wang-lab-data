"""The fitted trees as a Policy the scheduler can run.

White-box end to end: every decision traces to a path of axis-aligned tests on
named features, and `explain()` prints the path that produced the current move.

The trees decide WHAT, the scheduler still decides HOW -- which unit walks where,
what it touches, in what order. That is the same division that made the linear
policy safe, and it is what keeps a wrong tree from desynchronising anything:
a bad crop choice costs one tile's yield, not the schedule.
"""
import json
import os

from dynamic.rl import policy_api as PA


class TreePolicy(PA.Policy):
    WHITEBOX = True

    def __init__(self, path=None, blend=1.0):
        path = path or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))), "logs", "tree", "trees.json")
        blob = json.load(open(path))
        self.trees = blob["trees"]
        self.names = blob["names"]
        self.blend = float(blend)
        self.traj = {"daily": [], "sell": []}
        self.last_path = []

    def reset(self):
        self.traj = {"daily": [], "sell": []}

    def _walk(self, tree, x, trace=None):
        node = tree
        while "feat" in node:
            f, thr = node["feat"], node["thr"]
            go_left = x[f] <= thr
            if trace is not None:
                trace.append(f"{self.names[f]} {'<=' if go_left else '>'} {thr:.3f}")
            node = node["left"] if go_left else node["right"]
        return node["pred"]

    def daily(self, obs_vec):
        x = obs_vec
        trace = []
        crop_i = self._walk(self.trees["crop"], x, trace)
        hire = self._walk(self.trees["hire"], x)
        land = self._walk(self.trees["land"], x)
        animal = self._walk(self.trees["animal"], x)
        self.last_path = trace

        # crop_pref MULTIPLIES the scheduler's ENPV, so a preference is a
        # correction on a derived value rather than a replacement for it. blend
        # 1.0 doubles the chosen crop's score; 0.0 is the untouched scheduler.
        pref = {c: 1.0 for c in PA.CROPS}
        if 0 <= crop_i < len(PA.CROPS):
            pref[PA.CROPS[crop_i]] = 1.0 + self.blend
        # hire is an ABSOLUTE count in the replays; the API wants a delta off
        # the scheduler's own estimate, and the scheduler already sizes to the
        # task list, so this only nudges within the allowed range.
        delta = max(PA.CREW_DELTAS[0], min(PA.CREW_DELTAS[-1], hire - 3))
        return PA.Decision(crop_pref=pref, crew_delta=int(delta),
                           buy_land=bool(land),
                           animal=PA.ANIMAL_CHOICES[animal]
                                  if 0 <= animal < len(PA.ANIMAL_CHOICES) else None)

    def sell(self, market_vec, holdings):
        # No sell tree: the sell decision is governed by the scheduler's own
        # marginal-value rule, which is derived rather than cloned.
        return {p: 1.0 for p in PA.PRODUCTS}

    def explain(self):
        return " AND ".join(self.last_path) if self.last_path else "(no decision yet)"
