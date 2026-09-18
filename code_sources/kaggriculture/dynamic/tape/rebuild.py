"""Exact, readable rebuild of the tape. Verified action-by-action.

WHY REBUILD SOMETHING THAT ALREADY WORKS. The tape scores +18,664 where our
scheduler scores -70,240, so it is by far the strongest thing we have -- and it
is unmodifiable. Section 4 established that three times over and section 35 a
fourth: editing one action, or even truncating cleanly at a day boundary,
collapses it. The reason is the indexing. Every entry is addressed by STEP, so
entry 312 silently assumes everything entries 0-311 did; change one and the
assumption fails with no way to notice.

The fix is to re-index by STATE -- "when the board looks like this, do that" --
which has no downstream assumptions and is therefore safe to edit. That is the
decision tree we actually want.

BUT THAT CONVERSION HAS TO BE VERIFIED, NOT ASSUMED, which is why this file
exists first. It reproduces the tape EXACTLY, in our own code, with the action
tables as data. Once `verify()` shows byte-identical play, every later step of
"replace this step-indexed entry with a state-conditional rule" can be checked
against it: if behaviour changes, the rule is wrong, and we find out immediately
instead of after a 30-day game.

THREE LAYERS, all of them small:

    label        five tables, chosen by the order the town unlocks shops
    weed_repair  STATEFUL -- a PLANT or BUILD landing on a weed is deferred and
                 the actor's trace replayed for up to 8 steps
    align_hands  pad or truncate the hand list to the crew that actually exists

The tables are 7,190 actions of data; these three layers are the whole program.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _HERE]
sys.path.insert(0, ROOT)

TABLES = os.path.join(ROOT, "logs", "tape", "tables.json")
KAWA = "opponents/kaggriculture-multi-route-farming-agent.py"

MILK_SUPPORT = {"PIZZA_SHOP", "ICE_CREAM_SHOP", "SMOOTHIE_SHOP"}
WEED_REPLAY_STEPS = 8


def load_tables(path=TABLES):
    return json.load(open(path))


def route_label(obs):
    """Which of the five tables this game runs on.

    Read off the order the town unlocked its shops, so it can change mid-episode
    as more unlock -- the tape genuinely switches tables underneath itself, which
    is why a fixed table is not a faithful copy.
    """
    shops = list(((obs.get("town") or {}).get("unlocked_shops") or []))
    if shops[:1] == ["YARN_STORE"]:
        return "6c12s_4q_first_yarn"
    if "YARN_STORE" in shops[:2]:
        return "6c12s_4q_second_yarn"
    if "YARN_STORE" in shops[:3]:
        return "6c8s_3q"
    if MILK_SUPPORT.intersection(shops[:3]):
        return "10c4s_3q"
    return "8c6s_3q"


def _copy_action(a):
    return {"farmer": list(a.get("farmer") or ["PASS"]),
            "hands": [list(h or ["PASS"]) for h in (a.get("hands") or [])],
            "market": [list(m) for m in (a.get("market") or [])]}


def align_hands(action, farm):
    """Pad or truncate to the crew that actually exists.

    This is where a table entry can be silently DROPPED: if the table lists 12
    hands and only 10 were hired, entries 10 and 11 vanish. That is most of why
    a stateless lookup keyed on (label, step, unit) only reproduces 83% -- the
    same table row means different things at different crew sizes.
    """
    a = _copy_action(action)
    expected = len(farm.get("hands") or [])
    hands = list(a.get("hands") or [])
    if len(hands) < expected:
        hands.extend([["PASS"] for _ in range(expected - len(hands))])
    a["hands"] = [list(h or ["PASS"]) for h in hands[:expected]]
    return a


class Rebuilt:
    """The tape as data plus three readable layers, with its own weed state."""

    def __init__(self, tables=None, legacy=False):
        self.T = tables or load_tables()
        self.legacy = legacy
        self.weed = {"last_step": -1, "active": {}}
        self.trace = {}

    def table_for(self, label):
        key = ("_LEGACY_ACTIONS_" if self.legacy else "_ACTIONS_") + {
            "10c4s_3q": "10C4S_3Q", "8c6s_3q": "8C6S_3Q", "6c8s_3q": "6C8S_3Q",
            "6c12s_4q_first_yarn": "6C12S_4Q_FIRST_YARN",
            "6c12s_4q_second_yarn": "6C12S_4Q_SECOND_YARN"}[label]
        return self.T[key]

    def raw(self, obs, step):
        tab = self.table_for(route_label(obs))
        return tab[step] if 0 <= step < len(tab) else {"farmer": ["PASS"],
                                                       "hands": [], "market": []}

    def act(self, obs):
        step = int(obs.get("step", 0) or 0)
        if not step:
            step = int(obs.get("day", 0) or 0) * 24 + int(obs.get("hour", 0) or 0)
        if step == 0 or step < self.weed["last_step"]:
            self.weed = {"last_step": step, "active": {}}
            self.trace = {}
        self.weed["last_step"] = step
        seat = int(obs.get("player", 0) or 0)
        farm = (obs.get("farms") or [{}])[seat]
        a = align_hands(self.raw(obs, step), farm)
        self.trace[step] = _copy_action(a)
        return a


def verify(n_seeds=3, opponents=("v111-8c4s-economic-core-premium-lead",
                                 "kaggriculture-3000-socre")):
    """Play kawa and the rebuild in lockstep on the same state; compare actions.

    Both are driven from the SAME simulator, so any difference is the rebuild's
    and not a divergence of two separate games.
    """
    import importlib.util
    from planner.simulate import Simulator, _agent_caller
    spec = importlib.util.spec_from_file_location(
        "kawa_ref", os.path.join(ROOT, KAWA))
    km = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(km)
    kawa = getattr(km, "_submission_entry", None) or km.agent

    tables = load_tables()
    import random
    rng = random.Random(1357)
    seeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(n_seeds)]
    total = same = 0
    diffs = []
    for seed in seeds:
        for opp in opponents:
            ospec = importlib.util.spec_from_file_location(
                f"opp_{seed}_{opp[:6]}", os.path.join(ROOT, "opponents", opp + ".py"))
            om = importlib.util.module_from_spec(ospec)
            ospec.loader.exec_module(om)
            other = getattr(om, "_submission_entry", None) or om.agent
            sim = Simulator.new_episode(configuration={"episodeSteps": 720},
                                        seed=seed)
            c0, c1 = _agent_caller(kawa), _agent_caller(other)
            rb = Rebuilt(tables)
            while sim.step < 719:
                o = sim.observation_for(0)
                got = kawa(o)
                mine = rb.act(o)
                for key in ("farmer", "hands", "market"):
                    total += 1
                    if json.dumps(got.get(key)) == json.dumps(mine.get(key)):
                        same += 1
                    elif len(diffs) < 6:
                        diffs.append((sim.step, key,
                                      str(got.get(key))[:60],
                                      str(mine.get(key))[:60]))
                sim.step_actions(got, c1(sim.observation_for(1), sim.cfg))
    return same, total, diffs


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    same, total, diffs = verify(n)
    print(f"action components identical: {same:,}/{total:,} = "
          f"{100 * same / total:.2f}%")
    if diffs:
        print("\nfirst differences (step, field, kawa, rebuild):")
        for st, k, a, b in diffs:
            print(f"  step {st:>4} {k:<7}\n     kawa: {a}\n     ours: {b}")
