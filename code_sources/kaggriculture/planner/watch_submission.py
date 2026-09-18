"""Track a live submission's real ladder record as episodes accumulate.

publicScore is a skill rating that starts at 600 and converges with games
played, so it says nothing useful about a new submission for the first several
hours. The honest early signal is the win/loss record and margin distribution
from episode metadata, which is available immediately and needs no replay
downloads.

Usage:
    /home/yilewang/kagg-env/bin/python -m planner.watch_submission [SUBMISSION_ID]
"""
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pbt.build_pool import _api  # noqa: E402

LOG = os.path.join(ROOT, "logs", "planner", "submission_watch.log")


def record(sub_id):
    api = _api()
    eps = api.competition_list_episodes(sub_id)
    rows = []
    for e in eps:
        us = opp = None
        for a in e.agents:
            rec = {"sub": a.submission_id, "team": a.team_name,
                   "seat": a.index, "reward": a.reward}
            if a.submission_id == sub_id:
                us = rec
            else:
                opp = rec
        if us is None or opp is None:
            continue
        rows.append({"episode": e.id, "seat": us["seat"], "us": us["reward"],
                     "opp_team": opp["team"], "opp": opp["reward"],
                     "margin": us["reward"] - opp["reward"]})
    return rows


def summarise(sub_id, rows, label=""):
    if not rows:
        return f"sub {sub_id}: no completed episodes yet"
    n = len(rows)
    w = sum(1 for r in rows if r["margin"] > 0)
    mm = statistics.mean(r["margin"] for r in rows)
    med = statistics.median(r["margin"] for r in rows)
    s0 = [r for r in rows if r["seat"] == 0]
    s1 = [r for r in rows if r["seat"] == 1]
    out = (f"sub {sub_id}{label}: {w}/{n} ({100*w/n:.0f}%)  mean {mm:+,.0f}  median {med:+,.0f}  "
           f"seat0 {sum(1 for r in s0 if r['margin']>0)}/{len(s0)}  "
           f"seat1 {sum(1 for r in s1 if r['margin']>0)}/{len(s1)}")
    return out


def main():
    subs = [int(x) for x in sys.argv[1:]] or [55612771, 55600561]
    lines = []
    for s in subs:
        try:
            rows = record(s)
            line = summarise(s, rows)
        except Exception as e:
            line = f"sub {s}: FAILED {repr(e)[:100]}"
        print(line, flush=True)
        lines.append(line)
        losses = [r for r in (rows if isinstance(rows, list) else []) if r["margin"] < 0]
        if losses:
            losses.sort(key=lambda r: r["margin"])
            print("   worst losses: " + "; ".join(
                f"{r['margin']:+,.0f} vs {r['opp_team'][:18]} (seat{r['seat']})"
                for r in losses[:5]), flush=True)
    with open(LOG, "a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} " + " | ".join(lines) + "\n")


if __name__ == "__main__":
    main()
