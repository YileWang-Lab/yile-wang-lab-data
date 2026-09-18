"""Fidelity check: replay real ladder games' recorded actions through
planner.simulate.Simulator and diff every field against the replay's own
ground-truth state, every step. Zero divergence required.

Usage:
    /home/yilewang/kagg-env/bin/python -m planner.tests.test_sim_fidelity [replay.json ...]

With no arguments, checks every file in replays/.
"""
import glob
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from planner.simulate import Simulator


def _diff(a, b, path=""):
    """Yield human-readable diffs between two JSON-ish structures."""
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                yield f"{path}.{k}: missing in sim, replay has {b[k]!r}"
            elif k not in b:
                yield f"{path}.{k}: sim has {a[k]!r}, missing in replay"
            else:
                yield from _diff(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            yield f"{path}: len sim={len(a)} replay={len(b)}"
            return
        for i, (x, y) in enumerate(zip(a, b)):
            yield from _diff(x, y, f"{path}[{i}]")
    else:
        # Money is float in the engine; compare with a tiny tolerance.
        if isinstance(a, float) or isinstance(b, float):
            if abs(float(a) - float(b)) > 1e-6:
                yield f"{path}: sim={a!r} replay={b!r}"
        elif a != b:
            yield f"{path}: sim={a!r} replay={b!r}"


def check_replay(path, max_diffs_reported=20, verbose=True):
    d = json.load(open(path))
    seed = d["info"]["seed"]
    cfg = d.get("configuration", {})
    steps = d["steps"]
    n = len(steps)

    s0 = steps[0][0]["observation"]
    sim = Simulator.from_observation(
        {"day": s0["day"], "hour": s0["hour"], "player": 0,
         "farms": s0["farms"], "market": s0["market"], "town": s0["town"],
         "private": steps[0][0]["observation"]["private"]},
        opp_private=steps[0][1]["observation"]["private"],
        configuration={k: v for k, v in cfg.items() if k in
                       ("boardSize", "startingMoney", "maxMarketOrdersPerTurn", "turnsPerDay",
                        "shedCapacity", "weedSpawnChance", "townShopUnlockInterval",
                        "townShopSellInterval", "townCenterSellInterval", "farmHandCostMult",
                        "episodeSteps", "marketParams")},
        seed=seed,
    )

    total_diffs = 0
    first_divergence = None
    t0 = time.time()
    for i in range(1, n):
        a0 = steps[i][0]["action"]
        a1 = steps[i][1]["action"]
        sim.step_actions(a0, a1)

        truth0 = steps[i][0]["observation"]
        truth1 = steps[i][1]["observation"]
        sim_state = {
            "farms": sim.farms, "market": {"inventory": sim.market["inventory"],
                                            "prices": sim.market["prices"]},
            "town": sim.town, "day": sim.day, "hour": sim.hour,
            "private0": sim.privates[0], "private1": sim.privates[1],
        }
        truth_state = {
            "farms": truth0["farms"], "market": {"inventory": truth0["market"]["inventory"],
                                                   "prices": truth0["market"]["prices"]},
            "town": truth0["town"], "day": truth0["day"], "hour": truth0["hour"],
            "private0": truth0["private"], "private1": truth1["private"],
        }
        diffs = list(_diff(sim_state, truth_state))
        if diffs:
            total_diffs += len(diffs)
            if first_divergence is None:
                first_divergence = (i, sim.day, sim.hour, diffs[:max_diffs_reported])
                if verbose:
                    print(f"  FIRST DIVERGENCE at step {i} (day {sim.day} hour {sim.hour}):")
                    for line in diffs[:max_diffs_reported]:
                        print(f"    {line}")
                # Once state has diverged, every later step is contaminated --
                # no point continuing to accumulate noise from a bad baseline.
                break

    elapsed = time.time() - t0
    steps_done = i if first_divergence else n - 1
    rate = steps_done / elapsed if elapsed > 0 else float("inf")
    return {
        "path": path, "seed": seed, "n_steps": n, "steps_checked": steps_done,
        "total_diffs": total_diffs, "first_divergence": first_divergence,
        "elapsed": elapsed, "steps_per_sec": rate,
    }


def main():
    paths = sys.argv[1:] or sorted(glob.glob(os.path.join(ROOT, "replays", "*.json")))
    if not paths:
        print("no replays found"); return 1

    os.makedirs(os.path.join(ROOT, "logs", "planner"), exist_ok=True)
    log_path = os.path.join(ROOT, "logs", "sim_fidelity.log")
    ok = True
    with open(log_path, "a") as log:
        for p in paths:
            print(f"=== {os.path.basename(p)} ===")
            r = check_replay(p)
            status = "PASS" if r["first_divergence"] is None else "FAIL"
            if status == "FAIL":
                ok = False
            line = (f"{time.strftime('%Y-%m-%d %H:%M:%S')} {status} {os.path.basename(p)} "
                    f"seed={r['seed']} steps_checked={r['steps_checked']}/{r['n_steps']-1} "
                    f"first_divergence={r['first_divergence'][:3] if r['first_divergence'] else None} "
                    f"rate={r['steps_per_sec']:.0f}steps/s")
            print(" ", line)
            log.write(line + "\n")
    print()
    print("ALL PASS -- simulator is bit-exact against every checked replay" if ok
          else "DIVERGENCE FOUND -- do not build on this simulator until fixed")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
