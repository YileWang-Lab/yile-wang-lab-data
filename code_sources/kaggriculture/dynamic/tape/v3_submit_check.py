"""Would Kaggle actually run `submission/v3_tree.py`, and run it the same?

`dynamic/tape/v3_bench.py` proved equivalence through `planner.simulate`, which
is our own driver. That is the right tool for a fast 336-episode sweep, but it
is NOT the thing that scores the competition, so on its own it cannot answer
"is this submittable". HANDOFF rule 3: validate BY FILE PATH through
`kaggle_environments`, never by import, because Kaggle resolves a file agent
with `get_last_callable` and the appended tree block moves which callable that
picks (`_submission_entry` -> `_treeroute_entry`).

Three things this checks that the simulator sweep cannot:

  STATUS    every episode ends DONE/DONE. An agent that raises is not scored 0
            on the turn, it is marked INVALID and the match is forfeit -- and a
            forfeit still produces a plausible-looking bank number, so only the
            status field distinguishes it from a loss.
  IDENTITY  tree and base final banks equal, seed by seed, under the real
            engine rather than ours.
  BUDGET    the tree is ~50 comparisons where the array was one index, called
            three times a turn over 720 turns. Kaggle enforces a per-episode
            agent time limit, so the overhead is measured, not assumed.

    python dynamic/tape/v3_submit_check.py
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _HERE]
sys.path.insert(0, ROOT)

from kaggle_environments import make  # noqa: E402

BASE = os.path.join(ROOT, "submission", "v3_base.py")
LAYER = os.environ.get("V3_LAYER", "flat")       # 'tree' (CART) or 'flat' (array)
TREE = os.path.join(ROOT, "submission", "v3_%s.py" % LAYER)

OPPS = ["v111-8c4s-economic-core-premium-lead",
        "kaggriculture-3000-socre",
        "kaggriculture-rank-your-agent",
        "strong-barnyard-economist",
        "kaggriculture-multi-route-farming-agent"]
SEEDS = [int(s) for s in os.environ.get("V3_SEEDS", "9000,9001,9002").split(",")]


def run(path_a, path_b, seed):
    """One episode by FILE PATH. Returns (banks, statuses, wall seconds)."""
    env = make("kaggriculture",
               configuration={"episodeSteps": 720, "seed": seed}, debug=False)
    t0 = time.time()
    env.run([path_a, path_b])
    dt = time.time() - t0
    final = env.steps[-1]
    banks = (float(final[0].observation["farms"][0]["money"]),
             float(final[1].observation["farms"][1]["money"]))
    return banks, tuple(s.status for s in final), dt


def main():
    print("=" * 76)
    print("SUBMISSION CHECK  kaggle_environments, agents loaded by file path")
    print("=" * 76)

    bad = 0
    t_tree = t_base = 0.0
    n = 0
    for opp in OPPS:
        opp_path = os.path.join(ROOT, "opponents", opp + ".py")
        for seed in SEEDS:
            for seat in (0, 1):
                row = {}
                for arm, path in (("tree", TREE), ("base", BASE)):
                    pair = (path, opp_path) if seat == 0 else (opp_path, path)
                    banks, status, dt = run(pair[0], pair[1], seed)
                    us = banks[0] if seat == 0 else banks[1]
                    them = banks[1] if seat == 0 else banks[0]
                    mine = status[0] if seat == 0 else status[1]
                    row[arm] = (us, them, mine, status)
                    if arm == "tree":
                        t_tree += dt
                    else:
                        t_base += dt
                n += 1
                tr, ba = row["tree"], row["base"]
                ok_status = tr[3] == ("DONE", "DONE")
                ok_same = (tr[0], tr[1]) == (ba[0], ba[1])
                if not (ok_status and ok_same):
                    bad += 1
                    print("  FAIL %-40s seed %d seat %d" % (opp[:40], seed, seat))
                    if not ok_status:
                        print("       status %s (must be DONE/DONE)" % (tr[3],))
                    if not ok_same:
                        print("       tree %s  base %s" % (tr[:2], ba[:2]))

    print("\n  %d/%d episodes DONE/DONE and bank-identical to base" % (n - bad, n))
    print("  mean episode wall time   tree %.2fs   base %.2fs   (+%.1f%%)"
          % (t_tree / n, t_base / n, 100.0 * (t_tree - t_base) / max(t_base, 1e-9)))
    print("\n" + "=" * 76)
    print("VERDICT  %s" % ("SUBMITTABLE" if not bad else "DO NOT SUBMIT"))
    print("=" * 76)
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
