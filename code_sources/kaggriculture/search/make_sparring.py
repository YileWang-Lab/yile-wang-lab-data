"""Turn downloaded ladder replays into replay-playback sparring opponents.

Why this is a faithful sparring partner despite being a fixed tape: the two
farms are fully independent -- the ONLY coupling between players is the shared
market (prices/inventory). So an opponent's actions on their own farm are
almost entirely unaffected by what we do, and replaying them reproduces both
their production curve and, crucially, their *sell pressure on the shared
market* at the right times. That sell pressure is exactly what our previous
starter/random-only fitness signal was missing.

Caveat kept in mind by callers: the tape cannot react to us, so it will not
punish exploitative play. It is a strong benchmark, not a Nash opponent.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "opponents")


def extract(replay_path, out_dir=OUT_DIR):
    with open(replay_path) as f:
        d = json.load(f)
    teams = d["info"].get("TeamNames", ["?", "?"])
    rewards = d.get("rewards", [0, 0])
    steps = d["steps"]

    me = next((i for i, t in enumerate(teams) if t == "Karl0106"), 0)
    opp = 1 - me
    name = "".join(c if c.isalnum() else "_" for c in teams[opp]).strip("_").lower()

    # steps[i][p]["action"] is the action the agent SUBMITTED at step i.
    actions = []
    for step_states in steps:
        a = step_states[opp].get("action") if opp < len(step_states) else None
        if not isinstance(a, dict):
            a = {"farmer": ["PASS"], "hands": [], "market": []}
        actions.append({
            "farmer": a.get("farmer") or ["PASS"],
            "hands": a.get("hands") or [],
            "market": a.get("market") or [],
        })

    os.makedirs(out_dir, exist_ok=True)
    # The tape is only faithful at its ORIGINAL seed: weed spawns and shop
    # unlock order are seeded, and a tape replayed under a different seed
    # desyncs badly (measured: Hamed's 46,563 route scores 12,934 at seed=1
    # because its plantings land on weeds and its sells hit the wrong shop
    # demand). Store the seed so the evaluator can pin it.
    meta = {
        "source_episode": os.path.basename(replay_path),
        "team": teams[opp],
        "final_money": rewards[opp],
        "our_money": rewards[me],
        "n_steps": len(actions),
        "seed": d.get("info", {}).get("seed"),
    }
    path = os.path.join(out_dir, f"{name}.json")
    with open(path, "w") as f:
        json.dump({"meta": meta, "actions": actions}, f)
    print(f"{path}  team={teams[opp]!r} scored={rewards[opp]:,.0f} "
          f"(we scored {rewards[me]:,.0f}) steps={len(actions)} seed={meta['seed']}")
    return path


if __name__ == "__main__":
    replay_dir = sys.argv[1] if len(sys.argv) > 1 else "/tmp/replays"
    for name in sorted(os.listdir(replay_dir)):
        if name.endswith(".json"):
            extract(os.path.join(replay_dir, name))
