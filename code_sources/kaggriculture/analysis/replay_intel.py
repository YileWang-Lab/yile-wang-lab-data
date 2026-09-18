"""Extract actionable intelligence from real ladder replays.

These are OUR OWN episodes, downloaded via the official Kaggle API
(`kaggle competitions replay <id>`), so the opponent's public farm state and
submitted actions are visible the same way they are visible in-game. The point
here is not to copy anyone's policy -- it is to answer one question the local
search could not: *what does a farm that actually beats us on the ladder look
like?*

Our GA converged on 0 cows / 0 sheep because its only opponents were
`starter`/`random`/itself. On the real ladder that build scored 485.5 while
animal-heavy builds scored 2316-2613. This script measures the gap directly.
"""
import json
import os
import sys
from collections import Counter

REPLAY_DIR = sys.argv[1] if len(sys.argv) > 1 else "/tmp/replays"


def farm_composition(farm):
    counts = Counter()
    for row in farm.get("tiles", []) or []:
        for tile in row or []:
            if tile is None:
                counts["EMPTY"] += 1
            elif tile == "LOCKED":
                counts["LOCKED"] += 1
            elif isinstance(tile, dict):
                kind = tile.get("kind")
                if kind == "PLANT":
                    counts[f"crop:{tile['crop']}"] += 1
                elif "animal" in tile:
                    counts[f"animal:{tile['animal']}"] += 1
                elif kind in ("COOP", "PASTURE"):
                    counts[f"empty_struct:{kind}"] += 1
                elif kind == "WEED":
                    counts["WEED"] += 1
    return counts


def peak_animals(steps, player):
    """Max simultaneous animals held, and the day each type first appeared."""
    best = Counter()
    first_day = {}
    for step_states in steps:
        obs = step_states[0].get("observation", {})
        farms = obs.get("farms")
        if not farms or player >= len(farms):
            continue
        day = obs.get("day", 0)
        c = Counter()
        for row in farms[player].get("tiles", []) or []:
            for tile in row or []:
                if isinstance(tile, dict) and "animal" in tile:
                    c[tile["animal"]] += 1
        for k, v in c.items():
            if v > best[k]:
                best[k] = v
            if k not in first_day:
                first_day[k] = day
    return best, first_day


def money_curve(steps, player, every=6):
    out = []
    seen = set()
    for step_states in steps:
        obs = step_states[0].get("observation", {})
        farms = obs.get("farms")
        if not farms or player >= len(farms):
            continue
        day = obs.get("day", 0)
        if day % every == 0 and day not in seen:
            seen.add(day)
            out.append((day, farms[player]["money"]))
    return out


def analyse(path):
    with open(path) as f:
        d = json.load(f)
    teams = d["info"].get("TeamNames", ["?", "?"])
    rewards = d.get("rewards", [0, 0])
    steps = d["steps"]

    me = next((i for i, t in enumerate(teams) if t == "Karl0106"), 0)
    opp = 1 - me

    print(f"\n=== {os.path.basename(path)} ===")
    print(f"us(seat {me})={rewards[me]:,.0f}   opponent '{teams[opp]}'(seat {opp})={rewards[opp]:,.0f}   "
          f"{'WIN' if rewards[me] > rewards[opp] else 'LOSS'}")

    for label, seat in (("US ", me), ("OPP", opp)):
        peak, first = peak_animals(steps, seat)
        final = farm_composition(steps[-1][0]["observation"]["farms"][seat])
        animals = {k: v for k, v in final.items() if k.startswith("animal:")}
        crops = {k: v for k, v in final.items() if k.startswith("crop:")}
        print(f"  {label} peak_animals={dict(peak)} first_seen_day={first}")
        print(f"  {label} final animals={animals} crops={crops} "
              f"locked={final.get('LOCKED', 0)} empty={final.get('EMPTY', 0)}")
    print("  money by day (us / opp):")
    mc_me = dict(money_curve(steps, me))
    mc_opp = dict(money_curve(steps, opp))
    for day in sorted(mc_me):
        print(f"    day {day:>2}: {mc_me[day]:>9,.0f} / {mc_opp.get(day, 0):>9,.0f}")


if __name__ == "__main__":
    files = sorted(f for f in os.listdir(REPLAY_DIR) if f.endswith(".json"))
    if not files:
        print(f"no replays in {REPLAY_DIR}")
    for name in files:
        analyse(os.path.join(REPLAY_DIR, name))
