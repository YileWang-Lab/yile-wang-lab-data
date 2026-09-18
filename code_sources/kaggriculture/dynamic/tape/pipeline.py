"""The tape as a named, toggleable pipeline. 100% faithful by construction.

WHAT THE TAPE ACTUALLY IS. Not an action list -- a 7,190-entry route table plus
ELEVEN reactive guard layers, three of them stateful, applied in a fixed order
(kawa source, lines 990-1002). That structure is why editing it fails: change
one table entry and ten state machines downstream keep running on an assumption
that is now false, with nothing to signal it.

WHY THIS COMPOSES THE ORIGINAL FUNCTIONS INSTEAD OF RETYPING THEM. A hand-typed
copy would reach 100% only if every one of ~400 lines were transcribed
perfectly, and it would buy nothing: the same code with different names is
exactly as unmodifiable. What makes editing safe is not new source, it is
STRUCTURE -- each layer named, individually switchable, and a verifier that says
whether swapping one changed anything else.

So each stage delegates to the original implementation and the pipeline is ours.
Fidelity is then 100% by construction rather than by careful typing, and the
interesting operations become possible and checkable:

    p = Pipeline()                      # bit-identical to kawa
    p.disable("v17_r5_counter")         # drop one guard, measure the cost
    p.replace("preempt_shift", mine)    # swap in our own market_model logic
    p.verify()                          # did anything ELSE move?

STATE IS THE HAZARD, and it is why `reset()` exists. Three layers keep
module-level dictionaries keyed by seat (`_WEED_STATE`, `_SHIFT_STATE`,
`_V17_FEED_RESCUE_STATE`, ...). Two Pipeline objects in one process share them,
so an episode must reset them or the previous game leaks in -- the same class of
bug that made two agent instances share a plan earlier in this project.
"""
import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _HERE]
sys.path.insert(0, ROOT)

KAWA = os.path.join(ROOT, "opponents",
                    "kaggriculture-multi-route-farming-agent.py")

# The order is load-bearing: feed guard runs before room evacuation because a
# starving animal outranks shed space, and terminal liquidation runs last so it
# sees every order the other layers added.
# stage name -> the original function that implements it. Names are ours (short
# and readable); the functions are kawa's, so fidelity does not depend on
# transcription.
STAGE_FN = (
    ("weed_repair",         "_weed_repair_action"),
    ("feed_guard",          "_v17_feed_guard"),
    ("room_evac",           "_v17_room_evac"),
    ("repay_shift",         "_repay_shift"),
    ("rank_sell_slots",     "_rank_sell_slots"),
    ("preempt_shift",       "_preempt_shift"),
    ("r5_counter",          "_v17_r5_counter"),
    ("md_counter",          "_v17_md_counter"),
    ("room_guard",          "_v17_room_guard"),
    ("terminal_liquidation", "_terminal_liquidation"),
)
STAGES = tuple(name for name, _fn in STAGE_FN)

# Module-level, seat-keyed state that must be cleared between episodes.
STATE_VARS = ("_WEED_STATE", "_SHIFT_STATE", "_V17_FEED_RESCUE_STATE",
              "_V17_ROOM_EVAC_STATE", "_V17_ROOM_GUARD_STATE",
              "_KAWA_LAYOUT_FALLBACK")

_counter = [0]


def _fresh_kawa():
    """A private copy of the module, so two pipelines cannot share its state."""
    _counter[0] += 1
    spec = importlib.util.spec_from_file_location(
        f"kawa_pipe_{os.getpid()}_{_counter[0]}", KAWA)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Pipeline:
    """The tape, stage by stage. Identical to kawa until something is changed."""

    def __init__(self, module=None):
        self.k = module or _fresh_kawa()
        self.enabled = {s: True for s in STAGES}
        self.tree = None
        self.blend_p = None
        self.table_tree = None
        self.override = {}
        self._snapshot = {v: getattr(self.k, v, None) for v in STATE_VARS}

    # ------------------------------------------------------------- structure
    def disable(self, stage):
        if stage not in self.enabled:
            raise KeyError(f"{stage} is not a stage; have {STAGES}")
        self.enabled[stage] = False
        return self

    def replace(self, stage, fn):
        """Swap one layer for our own `fn(obs, action, step) -> action`."""
        if stage not in self.enabled:
            raise KeyError(f"{stage} is not a stage; have {STAGES}")
        self.override[stage] = fn
        return self

    def reset(self):
        """Clear the seat-keyed state the guards accumulate."""
        import copy as _c
        for v, val in self._snapshot.items():
            if val is not None:
                setattr(self.k, v, _c.deepcopy(val))
        return self

    # ------------------------------------------------------------- execution
    def blend_tree(self, tree_agent, p, seed=0):
        """Use the tree's action with probability `p`, the table's otherwise.

        This is the fidelity-performance curve: p=0 is the table exactly, p=1 is
        the tree alone, and everything between says how much deviation the
        route can absorb. It answers "would a MORE accurate tree work?" with a
        measurement instead of an argument.
        """
        import random as _r
        self.tree = tree_agent
        self.blend_p = float(p)
        self.blend_rng = _r.Random(seed)
        return self

    def use_tree(self, tree_agent):
        """Replace the 7,190-entry ROUTE TABLE with state-conditional rules.

        This is the point of the whole exercise. The table is uneditable --
        entry 312 assumes everything entries 0-311 did, so changing one breaks
        the rest silently (HANDOFF section 4, four confirmations). A tree has no
        downstream assumptions: every leaf is a standalone "when the board looks
        like this, do that", so any single rule can be rewritten or deleted.

        The ELEVEN GUARDS STAY. They are not part of the table -- they handle
        weeds, starving animals, shed overflow, unaffordable orders and the
        terminal liquidation, and all of that work is still needed whatever
        produces the base action.
        """
        self.tree = tree_agent
        return self

    def use_table_tree(self, tt):
        """Serve the base action from a perfect-fit CART instead of the array.

        EQUIVALENCE ONLY. `dynamic/tape/tree_table.py` fits the lookup
        (legacy, label, step) -> action to purity, so this is a binary search
        where the table did an index -- the same function, and no new capability.
        Distinct from `use_tree`, which swaps in state-conditional rules and
        therefore is NOT equivalent.

        The two selectors stay kawa's. `_kawa_use_legacy_layout` latches state
        per seat, so it must run once per turn exactly as `_kawa_actions` runs
        it, or the tree would diverge on the games where the latch fires.
        """
        self.table_tree = tt
        return self

    def table(self, obs):
        """The route table this observation selects (5 tables, by shop order)."""
        return self.k._kawa_actions(obs)

    def base_action(self, obs, step):
        """(route entry, clamped step) for this turn, from the tree if loaded.

        The clamp is returned rather than recomputed by the caller because kawa
        passes the CLAMPED step on to the guard layers (kawa source 991-992),
        and recomputing it would mean a second `_kawa_actions` call.
        """
        k = self.k
        if self.table_tree is None:
            actions = self.table(obs)
            step = min(max(0, step), len(actions) - 1)
            return k._copy_action(actions[step]), step
        # same two calls, same order, as _kawa_actions (kawa source 135-136)
        label = k._kawa_route_label(obs)
        legacy = k._kawa_use_legacy_layout(obs)
        entry = self.table_tree.lookup(legacy, label, step)
        step = min(max(0, step), self.table_tree.n_steps - 1)
        return k._copy_action(entry), step

    def act(self, obs):
        k = self.k
        step = int(k._get(obs, "step", 0) or 0)
        bp = getattr(self, "blend_p", None)
        if getattr(self, "tree", None) is not None and bp is None:
            action = k._copy_action(self.tree.agent(obs))
        elif getattr(self, "tree", None) is not None:
            base, _ = self.base_action(obs, step)
            if self.blend_rng.random() < bp:
                t = k._copy_action(self.tree.agent(obs))
                # unit-level blend: swap whole unit orders, not whole turns, so
                # the deviation rate is per decision and comparable to accuracy
                base["farmer"] = t["farmer"]
                base["hands"] = t["hands"]
            action = base
        else:
            action, step = self.base_action(obs, step)
        for name, fname in STAGE_FN:
            if name in self.override:
                action = self.override[name](obs, action, step)
                continue
            if not self.enabled[name]:
                continue
            fn = getattr(k, fname)
            # _rank_sell_slots takes a configuration rather than a step
            action = (fn(obs, action, None) if name == "rank_sell_slots"
                      else fn(obs, action, step))
        return k._align_hands(action, obs)

    def agent(self, obs, config=None):
        return self.act(obs if isinstance(obs, dict) else dict(obs))


def verify(n_seeds=3, opponents=("v111-8c4s-economic-core-premium-lead",
                                 "kaggriculture-3000-socre"),
           build=None):
    """Play kawa and the pipeline on the SAME states; compare every field.

    Driven from one simulator so a difference is the pipeline's, not two games
    drifting apart. Returns (same, total, first differences).
    """
    from planner.simulate import Simulator, _agent_caller
    ref_mod = _fresh_kawa()
    ref = getattr(ref_mod, "_submission_entry", None) or ref_mod.agent

    import random
    rng = random.Random(1357)
    seeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(n_seeds)]
    same = total = 0
    diffs = []
    for seed in seeds:
        for opp in opponents:
            spec = importlib.util.spec_from_file_location(
                f"opp_{seed}_{opp[:6]}",
                os.path.join(ROOT, "opponents", opp + ".py"))
            om = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(om)
            other = getattr(om, "_submission_entry", None) or om.agent

            p = (build() if build else Pipeline())
            sim = Simulator.new_episode(configuration={"episodeSteps": 720},
                                        seed=seed)
            c1 = _agent_caller(other)
            while sim.step < 719:
                o = sim.observation_for(0)
                got = ref(o)
                mine = p.act(o)
                for key in ("farmer", "hands", "market"):
                    total += 1
                    if json.dumps(got.get(key)) == json.dumps(mine.get(key)):
                        same += 1
                    elif len(diffs) < 5:
                        diffs.append((sim.step, key, str(got.get(key))[:64],
                                      str(mine.get(key))[:64]))
                sim.step_actions(got, c1(sim.observation_for(1), sim.cfg))
    return same, total, diffs


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    build = None
    if "tree" in sys.argv[2:]:
        from dynamic.tape.tree_table import load as _load_tree
        _tt = _load_tree()
        build = lambda: Pipeline().use_table_tree(_tt)     # noqa: E731
        print("base action served by the CART, not the array")
    same, total, diffs = verify(n, build=build)
    print(f"identical action fields: {same:,}/{total:,} = "
          f"{100 * same / total:.2f}%")
    if diffs:
        print("\nfirst differences (step, field):")
        for st, k, a, b in diffs:
            print(f"  step {st:>4} {k}\n     kawa: {a}\n     ours: {b}")
    else:
        print("\nthe pipeline is bit-identical to the original.")
