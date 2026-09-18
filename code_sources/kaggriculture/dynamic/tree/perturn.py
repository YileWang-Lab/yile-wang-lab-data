"""Per-TURN decision tree from the tape: one row per unit per turn.

This is a different target from anything measured so far. Section 32 fitted the
tape's DAILY decisions, and `dynamic/oracle.py` showed even a perfect copy of
those is -24,608 -- the tape's advantage is not in what it decides each morning.
So the remaining hypothesis is that it lives in the per-turn EXECUTION, and that
is what this extracts: for every unit on every turn, the operation the tape
chose, against the state that unit could see.

FEATURES ARE LOCAL PLUS GLOBAL, which is the whole design question. A unit's
choice depends on the tile it is standing on (can I water here? is there yield
to take?), on where it is relative to the shed, and on the season-wide state
(day, cash, crew size, what the opponent is doing). All named, all scalar.

WHAT THIS CAN AND CANNOT CAPTURE, stated up front so the result is readable
either way. An op like WATER or HARVEST is a function of the tile underfoot, and
a tree should get those. MOVEMENT is not: the tape walks a unit north for six
turns because of where it intends to be on turn twelve, and no function of the
current tile can express that. If the fitted tree scores well on tile ops and
badly on movement, that localises the tape's advantage precisely.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _HERE]
sys.path.insert(0, ROOT)

TAPE = "opponents/kaggriculture-multi-route-farming-agent.py"
OPPS = ["v111-8c4s-economic-core-premium-lead",
        "kaggriculture-3000-socre",
        "kaggriculture-rank-your-agent"]
OUT = os.path.join(ROOT, "logs", "tree", "perturn.json")

OPS = ["NORTH", "SOUTH", "EAST", "WEST", "PASS", "WATER", "HARVEST", "FEED",
       "CARE", "PLANT", "PLACE", "FERTILIZE", "COLLECT_FERTILIZER", "DIG",
       "BUILD_COOP", "BUILD_PASTURE", "PICKUP", "DROP"]
OP_INDEX = {o: i for i, o in enumerate(OPS)}

FEATURES = [
    "unit_idx", "x", "y", "dist_shed", "day", "hour", "step_in_day",
    "cash", "crew", "shed_fill",
    "here_empty", "here_locked", "here_weed", "here_plant", "here_animal",
    "here_structure", "here_yield", "here_watered", "here_unwatered",
    "here_fed", "here_cared", "here_fert_ready", "here_age",
    "n_empty_adj", "n_plant_adj", "our_producing", "our_weeds",
    "opp_producing", "opp_cash", "carrying",
]
_n = [0]


def _mk(path):
    import importlib.util
    _n[0] += 1
    spec = importlib.util.spec_from_file_location(
        f"pt_{os.getpid()}_{_n[0]}", os.path.join(ROOT, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return getattr(m, "_submission_entry", None) or m.agent


def _unit_pos(farm, idx):
    if idx == 0:
        f = farm.get("farmer")
    else:
        hs = farm.get("hands") or []
        f = hs[idx - 1] if idx - 1 < len(hs) else None
    if isinstance(f, dict):
        return int(f.get("x", 0)), int(f.get("y", 0))
    if isinstance(f, (list, tuple)) and len(f) >= 2:
        return int(f[0]), int(f[1])
    return 0, 0


def unit_features(farm, opp, priv, idx, day, hour, cash, agg):
    x, y = _unit_pos(farm, idx)
    tiles = farm["tiles"]
    t = tiles[y][x] if 0 <= y < len(tiles) and 0 <= x < len(tiles[0]) else None
    d = t if isinstance(t, dict) else {}
    kind = d.get("kind")
    n_empty = n_plant = 0
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx, ny = x + dx, y + dy
        if 0 <= ny < len(tiles) and 0 <= nx < len(tiles[0]):
            nt = tiles[ny][nx]
            if nt is None:
                n_empty += 1
            elif isinstance(nt, dict) and nt.get("kind") == "PLANT":
                n_plant += 1
    inv = (priv.get("inventories") or [{}])
    carry = 0
    if idx < len(inv) and isinstance(inv[idx], dict):
        carry = sum(inv[idx].values())
    return [
        idx, x, y, abs(x - 4) + abs(y - 4), day, hour, hour,
        min(2.0, cash / 20000.0), len(farm.get("hands") or []),
        min(1.0, sum((priv.get("shed") or {}).values()) / 100.0),
        1.0 if t is None else 0.0,
        1.0 if t == "LOCKED" else 0.0,
        1.0 if kind == "WEED" else 0.0,
        1.0 if kind == "PLANT" else 0.0,
        1.0 if d.get("animal") else 0.0,
        1.0 if kind in ("COOP", "PASTURE") else 0.0,
        float(d.get("yield_units", 0) or 0),
        1.0 if d.get("watered_today") else 0.0,
        float(d.get("consecutive_unwatered", 0) or 0),
        1.0 if d.get("fed_today") else 0.0,
        1.0 if d.get("cared_today") else 0.0,
        1.0 if d.get("fertilizer_available") else 0.0,
        float(day - int(d.get("planted_day", d.get("placed_day", day)))),
        n_empty, n_plant, agg[0], agg[1], agg[2], agg[3], carry,
    ]


def _agg(farm, opp, opp_cash):
    def count(f):
        p = w = 0
        for row in (f or {}).get("tiles") or []:
            for t in row:
                if isinstance(t, dict):
                    if t.get("kind") == "PLANT" or t.get("animal"):
                        p += 1
                    elif t.get("kind") == "WEED":
                        w += 1
        return p, w
    op_, ow = count(farm)
    pp, _ = count(opp)
    return [op_, ow, pp, min(2.0, opp_cash / 20000.0)]


def collect(seed, opp_name):
    """One tape game -> per-unit-per-turn rows."""
    from planner.simulate import Simulator, _agent_caller
    me, op = _mk(TAPE), _mk(os.path.join("opponents", opp_name + ".py"))
    sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
    c0, c1 = _agent_caller(me), _agent_caller(op)
    rows = []
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
                op_name = u[0]
                if op_name not in OP_INDEX:
                    continue
                rows.append((unit_features(farm, opp, priv, idx, day, hour,
                                           float(farm.get("money", 0)), agg),
                             OP_INDEX[op_name]))
        sim.step_actions(a, c1(sim.observation_for(1), sim.cfg))
    return rows


def main():
    n_seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    import random
    rng = random.Random(8642)
    seeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(n_seeds)]
    games = []
    for i, s in enumerate(seeds):
        for opp in OPPS:
            g = collect(s, opp)
            games.append(g)
            print(f"  seed {i + 1}/{n_seeds} vs {opp[:22]}: +{len(g):,} rows "
                  f"(total {sum(len(x) for x in games):,})", flush=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({"games": games, "features": FEATURES, "ops": OPS}, open(OUT, "w"))
    import collections
    c = collections.Counter(y for g in games for _x, y in g)
    tot = sum(c.values())
    print(f"\n{tot:,} unit-turns -> {OUT}")
    print(f"  {'op':<22}{'count':>9}{'share':>8}")
    for i, n in c.most_common(10):
        print(f"  {OPS[i]:<22}{n:>9,}{100 * n / tot:>7.1f}%")


if __name__ == "__main__":
    main()
