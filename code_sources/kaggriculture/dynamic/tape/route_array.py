"""The flat route table as numpy, for search tooling. Never imported by an agent.

`pbt/flatroute.py` ships the tape as a plain list because the agent indexes it
2,160 times an episode and stdlib-only is worth keeping in someone else's
sandbox. Everything OFFLINE wants the opposite: bulk masks, elementwise diffs,
whole-region rewrites. That is this module.

    from dynamic.tape.route_array import RouteArray
    r = RouteArray.load("submission/v3_flat.py")

    r.codes                     int32[7190], identity by default
    r.key(legacy, label, step)  -> int      r.unkey(i) -> (legacy, label, step)
    r.action(i)                 -> dict     the action state i currently plays
    r.reach                     bool[7190], which states an episode ever visits
    r.patch(path)               write _FR_REMAP / _FR_EDITS back into a file

REACHABILITY IS THE NUMBER THAT MATTERS. The state space is 7,190 but most of
it is unreachable -- `_kawa_route_label` never returns some labels and the
legacy latch never flips for others, so those rows are dead weight in any
search. `RouteArray.measure_reach` plays the pool and records which keys were
actually asked for. Search the mask, not the space; and report the mask size
alongside any result, because "no improvement found in 7,190 states" and "no
improvement found in 2,133 states" are different claims.

ON s2. `codes` is s1-only on purpose (see `pbt/flatroute.py`'s docstring). If
an opponent axis is ever justified, `RouteArray` grows an `n_opp` stride in
`key`/`unkey` and nothing else here changes -- but multiplying the parameters
by |s2| against a fixed-size pool makes the search harder before it makes the
agent better, so the burden of proof is on the split.
"""
import importlib.util
import json
import os
import re
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _HERE]
sys.path.insert(0, ROOT)

LABELS = ("10c4s_3q", "8c6s_3q", "6c8s_3q",
          "6c12s_4q_first_yarn", "6c12s_4q_second_yarn")
N_LABEL = len(LABELS)
_loads = [0]


def _load_module(path):
    """Fresh module every call -- the agent holds per-seat state in globals."""
    _loads[0] += 1
    spec = importlib.util.spec_from_file_location(
        "ra_%d_%d" % (os.getpid(), _loads[0]), path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class RouteArray(object):
    """A flattened v3 tape: 7,190 states, each pointing at one (table, step)."""

    def __init__(self, path, codes, edits, tables, n_steps):
        self.path = path
        self.codes = codes              # int32[N], code i decodes to (table, step)
        self.edits = dict(edits)        # state -> literal action dict
        self.tables = tables            # the ten arrays, as-is
        self.n_steps = n_steps
        self.n = 2 * N_LABEL * n_steps
        self._reach = None

    # ------------------------------------------------------------- construction

    @classmethod
    def load(cls, path):
        m = _load_module(path)
        if not hasattr(m, "_FR_CODES"):
            raise SystemExit(
                "%s has no _FR_CODES -- flatify it first:\n"
                "    python pbt/flatify.py <base.py> %s" % (path, path))
        return cls(path,
                   np.asarray(m._FR_CODES, dtype=np.int32),
                   m._FR_EDITS, m._FR_TABLES, m._FR_STEPS)

    # ------------------------------------------------------------- state space

    def key(self, legacy, label, step):
        code = label if isinstance(label, int) else LABELS.index(label)
        return (legacy * N_LABEL + code) * self.n_steps + step

    def unkey(self, i):
        table, step = divmod(int(i), self.n_steps)
        legacy, code = divmod(table, N_LABEL)
        return legacy, LABELS[code], step

    def keys(self, legacy=None, label=None, steps=None):
        """Vectorised slice of the state space. All args optional."""
        idx = np.arange(self.n, dtype=np.int32)
        table, step = np.divmod(idx, self.n_steps)
        lg, code = np.divmod(table, N_LABEL)
        m = np.ones(self.n, dtype=bool)
        if legacy is not None:
            m &= (lg == legacy)
        if label is not None:
            m &= (code == (label if isinstance(label, int) else LABELS.index(label)))
        if steps is not None:
            lo, hi = steps
            m &= (step >= lo) & (step < hi)
        return idx[m]

    # ------------------------------------------------------------------ actions

    def action(self, i):
        """The action state i currently plays, edits included."""
        i = int(i)
        if i in self.edits:
            return self.edits[i]
        t, s = divmod(int(self.codes[i]), self.n_steps)
        return self.tables[t][s]

    def fingerprints(self):
        """int32[N] -- equal entries are byte-equal actions. For dedup/diff."""
        seen, out = {}, np.empty(self.n, dtype=np.int32)
        for i in range(self.n):
            txt = json.dumps(self.action(i), sort_keys=True, separators=(",", ":"))
            out[i] = seen.setdefault(txt, len(seen))
        return out

    def diff(self, other):
        """States where two RouteArrays play different actions."""
        return np.nonzero(self.fingerprints() != other.fingerprints())[0]

    # ------------------------------------------------------------ reachability

    @property
    def reach(self):
        if self._reach is None:
            raise RuntimeError("call measure_reach() or load_reach() first")
        return self._reach

    def measure_reach(self, opponents=None, seeds=(9000, 9001, 9002)):
        """Play the pool with the lookup instrumented; record which keys fire.

        Counts every read, including `_trace_actor_action`'s replay and
        `_future_sells`' step+1 peek -- a state one of those touches is
        reachable even if the base lookup never asks for it.
        """
        from planner.simulate import Simulator
        if opponents is None:
            opponents = ["v111-8c4s-economic-core-premium-lead",
                         "kaggriculture-3000-socre",
                         "kaggriculture-rank-your-agent",
                         "strong-barnyard-economist",
                         "kaggriculture-multi-route-farming-agent"]
        hit = np.zeros(self.n, dtype=bool)
        for opp in opponents:
            opp_path = os.path.join(ROOT, "opponents", opp + ".py")
            for seed in seeds:
                for seat in (0, 1):
                    m = _load_module(self.path)
                    inner = m._fr_lookup

                    def traced(legacy, label, step, _f=inner, _m=m):
                        s = min(max(0, int(step)), _m._FR_STEPS - 1)
                        hit[(legacy * N_LABEL + _m._FR_LABEL_CODE[label])
                            * _m._FR_STEPS + s] = True
                        return _f(legacy, label, step)

                    m._fr_lookup = traced
                    # The proxy resolves `_fr_lookup` from module globals at call
                    # time, so rebinding the name is enough -- no class surgery.
                    ours = m._flatroute_entry
                    them = _load_module(opp_path)
                    pick = None
                    for name, val in vars(them).items():
                        if callable(val) and not name.startswith("__"):
                            pick = val
                    sim = Simulator.new_episode(
                        configuration={"episodeSteps": 720}, seed=seed)
                    if seat == 0:
                        sim.run_episode(ours, pick)
                    else:
                        sim.run_episode(pick, ours)
        self._reach = hit
        return hit

    def reach_report(self):
        r = self.reach
        lines = ["reachable %d / %d states (%.1f%%)"
                 % (r.sum(), self.n, 100.0 * r.sum() / self.n)]
        for lg in (0, 1):
            for ci, lb in enumerate(LABELS):
                k = self.keys(legacy=lg, label=ci)
                n = int(r[k].sum())
                if n:
                    st = [self.unkey(i)[2] for i in k[r[k]]]
                    lines.append("  legacy=%d %-22s %4d states, steps %d..%d"
                                 % (lg, lb, n, min(st), max(st)))
        dead = [("legacy=%d " % lg) + lb
                for lg in (0, 1) for ci, lb in enumerate(LABELS)
                if not r[self.keys(legacy=lg, label=ci)].any()]
        if dead:
            lines.append("  never selected: " + ", ".join(dead))
        return "\n".join(lines)

    # ----------------------------------------------------------------- writing

    def patch(self, dst, remap=None, edits=None):
        """Rewrite `_FR_REMAP` / `_FR_EDITS` in a flat agent file.

        Textual on purpose: the rest of the file is not reparsed, reformatted or
        re-baked, so a patched agent stays byte-identical everywhere else and
        `cmp` still localises any surprise.
        """
        src = open(self.path).read()
        for name, val in (("_FR_REMAP", remap), ("_FR_EDITS", edits)):
            if val is None:
                continue
            body = ("{}" if not val else
                    "{\n" + "".join("    %r: %r,\n" % (int(k), v)
                                    for k, v in sorted(val.items())) + "}")
            new, n = re.subn(r"^%s = \{\}" % name, "%s = %s" % (name, body),
                             src, count=1, flags=re.M)
            if n != 1:
                raise SystemExit("could not find `%s = {}` in %s -- patch a "
                                 "freshly flatified file, not a patched one"
                                 % (name, self.path))
            src = new
        with open(dst, "w") as f:
            f.write(src)
        return dst


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        ROOT, "submission", "v3_flat.py")
    r = RouteArray.load(path)
    print("%s" % path)
    print("  state space  2 legacy x %d labels x %d steps = %d"
          % (N_LABEL, r.n_steps, r.n))
    print("  codes        identity in %d / %d states"
          % (int((r.codes == np.arange(r.n)).sum()), r.n))
    print("  distinct actions %d" % len(set(r.fingerprints().tolist())))
    print("  edits        %d" % len(r.edits))
    print("\nmeasuring reachability over the pool ...")
    r.measure_reach()
    print(r.reach_report())
    return 0


if __name__ == "__main__":
    sys.exit(main())
