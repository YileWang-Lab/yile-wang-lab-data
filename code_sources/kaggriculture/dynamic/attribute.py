"""Where do the unit-turns go, and what does each one buy?

The gap to the tape is not efficiency in the usual sense. Measured over 32
traces each (planner/spec_extract.py), our realised price per unit is BETTER
($89.7 vs $79.6) and our useful-op rate is higher (44.5% vs 40.1%). What is
worse is volume: 1,092 units sold against 1,701.

So the question is not "what fraction of turns are useful" but "what does a
useful turn actually buy". This attributes every unit-turn in a game to a
category and then divides the harvested output by the turns spent getting it,
per role, for both agents on identical seeds.

Categories are deliberately about ECONOMIC function rather than op name:
  produce   HARVEST -- the only op that creates a sellable unit
  enable    WATER / FEED / CARE / FERTILIZE -- required upkeep, no direct output
  build     PLANT / PLACE / BUILD_* / DIG -- capacity creation
  logistics PICKUP / DROP -- moving goods, no state change on the farm
  move      N/S/E/W
  waste     an op whose engine precondition fails, so the turn does nothing
  idle      PASS
"""
import collections
import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from planner.simulate import Simulator  # noqa: E402
from route.search import to_params  # noqa: E402

MOVES = {"NORTH", "SOUTH", "EAST", "WEST"}
PRODUCE = {"HARVEST"}
ENABLE = {"WATER", "FEED", "CARE", "FERTILIZE", "COLLECT_FERTILIZER"}
BUILD = {"PLANT", "PLACE", "BUILD_COOP", "BUILD_PASTURE", "DIG"}
LOGI = {"PICKUP", "DROP"}
_n = [0]


def _load(path, genome=None):
    _n[0] += 1
    s = importlib.util.spec_from_file_location(f"at_{os.getpid()}_{_n[0]}", path)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    if genome is not None:
        m.configure(genome); return m.agent
    return getattr(m, "_submission_entry", None) or m.agent


def _valid(op, tile, inv, seeds):
    """Would the engine accept this op on this tile? Mirrors _apply_unit_action."""
    d = tile if isinstance(tile, dict) else {}
    if op in MOVES or op == "PASS":
        return True
    if op in ("DROP", "PICKUP"):
        return True          # position-gated, handled by the caller
    if tile == "LOCKED":
        return False
    if op == "PLANT":
        return tile is None
    if op == "WATER":
        return d.get("kind") == "PLANT" and not d.get("watered_today")
    if op == "HARVEST":
        return isinstance(tile, dict) and d.get("yield_units", 0) > 0
    if op == "FERTILIZE":
        return d.get("kind") == "PLANT" and inv.get("FERTILIZER", 0) > 0
    if op == "DIG":
        return tile is not None and "animal" not in d
    if op in ("BUILD_COOP", "BUILD_PASTURE"):
        return tile is None
    if op == "FEED":
        return "animal" in d and not d.get("fed_today") and inv.get("WHEAT", 0) > 0
    if op == "CARE":
        return "animal" in d and not d.get("cared_today")
    if op == "COLLECT_FERTILIZER":
        return "animal" in d and d.get("fertilizer_available")
    if op == "PLACE":
        return True
    return True


def trace(agent, opp, seed):
    cat = collections.Counter()
    harvest_units = collections.Counter()   # crop/animal product -> units taken
    per_role_turns = collections.Counter()

    def wrapped(obs):
        a = agent(obs)
        seat = int(obs.get("player", 0))
        farm = obs["farms"][seat]
        priv = obs.get("private") or {}
        seeds = priv.get("seeds") or {}
        invs = priv.get("inventories") or [{}]
        tiles = farm["tiles"]
        units = [(0, farm["farmer"], a.get("farmer"))]
        ha = a.get("hands") or []
        for i, hp in enumerate(farm.get("hands") or []):
            units.append((i + 1, hp, ha[i] if i < len(ha) else None))
        for ui, pos, act in units:
            if not isinstance(act, list) or not act:
                cat["idle"] += 1
                continue
            op = act[0]
            x, y = int(pos[0]), int(pos[1])
            tile = tiles[y][x]
            inv = invs[ui] if ui < len(invs) else {}
            if op == "PASS":
                cat["idle"] += 1
            elif op in MOVES:
                cat["move"] += 1
            elif not _valid(op, tile, inv, seeds):
                cat["waste"] += 1
            elif op in PRODUCE:
                cat["produce"] += 1
                d = tile if isinstance(tile, dict) else {}
                n = d.get("yield_units", 0)
                key = d.get("crop") or d.get("animal") or "?"
                harvest_units[key] += n
            elif op in ENABLE:
                cat["enable"] += 1
                d = tile if isinstance(tile, dict) else {}
                per_role_turns[d.get("crop") or d.get("animal") or "?"] += 1
            elif op in BUILD:
                cat["build"] += 1
            elif op in LOGI:
                cat["logistics"] += 1
            else:
                cat["other"] += 1
        return a
    sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
    m0, m1 = sim.run_episode(wrapped, opp)
    return cat, harvest_units, per_role_turns, m0


def main():
    seeds = [1009, 88301, 271829, 481123]
    genome = json.load(open(os.path.join(ROOT, "planner", "checkpoints",
                                         "best_genome1.json")))["genome"]
    results = {}
    for label, path, g in (("DYNAMIC", os.path.join(ROOT, "dynamic", "agent.py"),
                            to_params(dict(genome))),
                           ("TAPE", os.path.join(ROOT, "opponents",
                                                 "kaggriculture-multi-route-farming-agent.py"),
                            None)):
        C, H, R, banks = collections.Counter(), collections.Counter(), collections.Counter(), []
        for sd in seeds:
            me = _load(path, g)
            opp = _load(os.path.join(ROOT, "opponents",
                                     "v111-8c4s-economic-core-premium-lead.py"))
            c, h, r, bank = trace(me, opp, sd)
            C += c; H += h; R += r; banks.append(bank)
        results[label] = (C, H, R, sum(banks) / len(banks))

    n = len(seeds)
    print(f"{'category':<12} {'DYNAMIC':>12} {'TAPE':>12} {'ratio':>8}   what a turn buys")
    keys = ["produce", "enable", "build", "logistics", "move", "waste", "idle"]
    for k in keys:
        a = results["DYNAMIC"][0][k] / n
        b = results["TAPE"][0][k] / n
        print(f"{k:<12} {a:>12,.0f} {b:>12,.0f} {a/b if b else 0:>8.2f}x")
    ta = sum(results["DYNAMIC"][0][k] for k in keys) / n
    tb = sum(results["TAPE"][0][k] for k in keys) / n
    print(f"{'TOTAL turns':<12} {ta:>12,.0f} {tb:>12,.0f} {ta/tb if tb else 0:>8.2f}x")
    print()
    ua = sum(results["DYNAMIC"][1].values()) / n
    ub = sum(results["TAPE"][1].values()) / n
    print(f"{'units harvested':<12} {ua:>12,.0f} {ub:>12,.0f} {ua/ub if ub else 0:>8.2f}x")
    print(f"{'units / turn':<12} {ua/ta:>12.3f} {ub/tb:>12.3f} {(ua/ta)/(ub/tb):>8.2f}x")
    print(f"{'bank':<12} {results['DYNAMIC'][3]:>12,.0f} {results['TAPE'][3]:>12,.0f}")
    print()
    print("harvest by source (units per game), and upkeep turns spent on it")
    allk = set(results["DYNAMIC"][1]) | set(results["TAPE"][1])
    print(f"{'source':<12} {'DYN units':>10} {'DYN turns':>10} {'u/turn':>8} "
          f"{'TAPE units':>11} {'TAPE turns':>11} {'u/turn':>8}")
    for k in sorted(allk):
        du, dt = results["DYNAMIC"][1][k] / n, results["DYNAMIC"][2][k] / n
        tu, tt = results["TAPE"][1][k] / n, results["TAPE"][2][k] / n
        print(f"{k:<12} {du:>10,.0f} {dt:>10,.0f} {du/dt if dt else 0:>8.2f} "
              f"{tu:>11,.0f} {tt:>11,.0f} {tu/tt if tt else 0:>8.2f}")


if __name__ == "__main__":
    main()
