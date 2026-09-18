"""Behavioural-cloning dataset: (state features, action) pairs from tape play.

The tapes bank ~$96k where our planner banks ~$84k against the same opponent,
and 124 GA generations only closed 76% of the original gap. The idea here is to
stop searching from a random point and start from the tapes' own decisions.

WHAT IS AND IS NOT LEARNABLE HERE. A tape is a fixed 719-step action list; it
does not read the board. So the (state -> action) mapping it induces is only
meaningful because the tape's own state trajectory is nearly deterministic --
the network will largely learn "on day d, hour h, standing on a tile in state s,
do op o". That still transfers, because the tape itself transfers across seeds,
but it caps what cloning can be worth: a perfect clone of kawa is kawa.

The value is therefore NOT in beating the tape by imitation. It is that a
learned policy is board-relative and can be applied to a DIFFERENT layout,
which the raw tape cannot -- HANDOFF section 4 established that grafting tape
actions onto another board collapses the run. So features are deliberately
board-relative (what is on the tile I am standing on, what do I carry, what is
adjacent) rather than absolute (tile 37 of the layout).

Actions are recorded as the base op only. PLANT/PICKUP/PLACE carry an item
argument that is far better resolved by rule at execution time -- there is
exactly one sensible crop to plant on a tile whose role is known -- than by
asking a classifier to reproduce a 30-way joint vocabulary from limited data.
"""
import argparse
import importlib.util
import multiprocessing
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from planner.simulate import Simulator  # noqa: E402

OUT_DIR = os.path.join(ROOT, "planner", "bc")
os.makedirs(OUT_DIR, exist_ok=True)

CROPS = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON"]
ANIMALS = ["GOOSE", "COW", "SHEEP"]
OPS = ["PASS", "NORTH", "SOUTH", "EAST", "WEST", "PLANT", "WATER", "HARVEST",
       "FERTILIZE", "DIG", "BUILD_COOP", "BUILD_PASTURE", "FEED",
       "COLLECT_FERTILIZER", "CARE", "DROP", "PICKUP", "PLACE"]
OP_IDX = {o: i for i, o in enumerate(OPS)}
N_OPS = len(OPS)

TAPES = [
    "kaggriculture-multi-route-farming-agent",
    "v111-8c4s-economic-core-premium-lead",
    "kaggriculture-3000-socre",
    "kaggriculture-breaking-the-tie-2883-score",
]
_n = [0]


def _load(name):
    _n[0] += 1
    p = os.path.join(ROOT, "opponents", f"{name}.py")
    s = importlib.util.spec_from_file_location(f"bc_{os.getpid()}_{_n[0]}", p)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return getattr(m, "_submission_entry", None) or m.agent


def features(obs, seat, unit_idx, pos):
    """~56 board-relative floats describing one unit's decision context."""
    farm = obs["farms"][seat]
    priv = obs["private"]
    shed = priv.get("shed") or {}
    seeds = priv.get("seeds") or {}
    invs = priv.get("inventories") or [{}]
    inv = invs[unit_idx] if unit_idx < len(invs) else {}
    tiles = farm["tiles"]
    x, y = int(pos[0]), int(pos[1])
    f = []

    # position / time
    f += [x / 9.0, y / 9.0, (abs(x - 4.5) + abs(y - 4.5)) / 9.0,
          obs["day"] / 30.0, obs["hour"] / 24.0, min(unit_idx, 15) / 15.0]

    tile = tiles[y][x]
    is_locked = 1.0 if tile == "LOCKED" else 0.0
    is_empty = 1.0 if tile is None else 0.0
    d = tile if isinstance(tile, dict) else {}
    kind = d.get("kind")
    crop = d.get("crop")
    animal = d.get("animal")
    f += [is_locked, is_empty,
          1.0 if kind == "WEED" else 0.0,
          1.0 if kind == "COOP" and not animal else 0.0,
          1.0 if kind == "PASTURE" and not animal else 0.0]
    f += [1.0 if crop == c else 0.0 for c in CROPS]
    f += [1.0 if animal == a else 0.0 for a in ANIMALS]
    # plant detail
    f += [min(obs["day"] - d.get("planted_day", obs["day"]), 20) / 20.0 if crop else 0.0,
          1.0 if d.get("watered_today") else 0.0,
          min(d.get("yield_units", 0), 6) / 6.0,
          1.0 if d.get("fertilized_until_day", -1) >= obs["day"] else 0.0,
          min(d.get("consecutive_unwatered", 0), 2) / 2.0]
    # animal detail
    f += [1.0 if d.get("fed_today") else 0.0,
          1.0 if d.get("cared_today") else 0.0,
          1.0 if d.get("fertilizer_available") else 0.0,
          min(d.get("consecutive_unfed", 0), 2) / 2.0,
          min(d.get("pending_care_bonus", 0), 3) / 3.0]
    # carried
    f += [min(inv.get("WHEAT", 0), 10) / 10.0,
          min(inv.get("FERTILIZER", 0), 10) / 10.0,
          1.0 if any(inv.get(a, 0) for a in ANIMALS) else 0.0,
          min(sum(inv.values()), 20) / 20.0]
    # shed / cash / seeds
    f += [min(shed.get("WHEAT", 0), 100) / 100.0,
          min(shed.get("FERTILIZER", 0), 100) / 100.0,
          min(sum(shed.values()), 100) / 100.0,
          min(farm["money"], 150000) / 150000.0]
    f += [1.0 if shed.get(a, 0) else 0.0 for a in ANIMALS]
    f += [min(seeds.get(c, 0), 20) / 20.0 for c in CROPS]
    # board census
    n_plant = n_animal = n_empty = n_weed = n_struct = 0
    for row in tiles:
        for t in row:
            if t is None:
                n_empty += 1
            elif isinstance(t, dict):
                if t.get("kind") == "PLANT":
                    n_plant += 1
                elif "animal" in t:
                    n_animal += 1
                elif t.get("kind") == "WEED":
                    n_weed += 1
                else:
                    n_struct += 1
    f += [n_plant / 50.0, n_animal / 20.0, n_empty / 50.0, n_weed / 20.0, n_struct / 20.0,
          len(farm.get("unlocked_quadrants") or ["NW"]) / 4.0,
          min(len(farm.get("hands") or []), 20) / 20.0]
    # adjacent tiles: does each direction hold something actionable?
    for dx, dy in ((0, -1), (0, 1), (1, 0), (-1, 0)):
        nx, ny = x + dx, y + dy
        if not (0 <= nx < 10 and 0 <= ny < 10):
            f.append(-1.0)
            continue
        t = tiles[ny][nx]
        if t is None:
            f.append(0.5)
        elif t == "LOCKED":
            f.append(-1.0)
        elif isinstance(t, dict):
            if t.get("kind") == "PLANT":
                f.append(1.0 if not t.get("watered_today") else 0.25)
            elif "animal" in t:
                f.append(1.0 if not t.get("fed_today") else 0.25)
            else:
                f.append(0.0)
        else:
            f.append(0.0)
    return f


N_FEAT = None


def collect(job):
    seed, tape_name, opp_name = job
    X, Y = [], []
    try:
        tape = _load(tape_name)
        opp = _load(opp_name)
        sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)

        def recording(obs):
            a = tape(obs)
            seat = int(obs.get("player", 0))
            farm = obs["farms"][seat]
            units = [("farmer", farm["farmer"], a.get("farmer"))]
            for i, hp in enumerate(farm.get("hands") or []):
                ha = (a.get("hands") or [])
                units.append((f"h{i}", hp, ha[i] if i < len(ha) else None))
            for ui, (_, pos, act) in enumerate(units):
                if not isinstance(act, list) or not act:
                    continue
                op = act[0]
                if op not in OP_IDX:
                    continue
                X.append(features(obs, seat, ui, pos))
                Y.append(OP_IDX[op])
            return a

        sim.run_episode(recording, opp)
        return np.array(X, dtype=np.float32), np.array(Y, dtype=np.int16), None
    except Exception:
        import traceback
        return None, None, traceback.format_exc()[-300:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=400)
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--out", default="bc_dataset.npz")
    args = ap.parse_args()

    import random
    rng = random.Random(20260819)
    jobs = []
    for i in range(args.games):
        tape = TAPES[i % len(TAPES)]
        opp = TAPES[(i // len(TAPES)) % len(TAPES)]
        jobs.append((rng.randrange(10 ** 6, 2 ** 31 - 1), tape, opp))
    print(f"collecting from {args.games} games ({len(TAPES)} tapes)")
    t0 = time.time()
    with multiprocessing.get_context("forkserver").Pool(args.workers) as pool:
        res = pool.map(collect, jobs, chunksize=2)
    errs = [r[2] for r in res if r[2]]
    if errs:
        print(f"{len(errs)} errors; first: {errs[0][-300:]}")
    Xs = [r[0] for r in res if r[0] is not None and len(r[0])]
    Ys = [r[1] for r in res if r[1] is not None and len(r[1])]
    X = np.concatenate(Xs); Y = np.concatenate(Ys)
    print(f"elapsed {time.time()-t0:.0f}s  -> {X.shape[0]:,} samples x {X.shape[1]} features")
    counts = np.bincount(Y, minlength=N_OPS)
    print("action distribution:")
    for i, c in sorted(enumerate(counts), key=lambda kv: -kv[1]):
        if c:
            print(f"  {OPS[i]:<20} {c:>9,} ({100*c/len(Y):>5.1f}%)")
    np.savez_compressed(os.path.join(OUT_DIR, args.out), X=X, Y=Y, ops=np.array(OPS))
    print(f"saved {os.path.join(OUT_DIR, args.out)}")


if __name__ == "__main__":
    main()
