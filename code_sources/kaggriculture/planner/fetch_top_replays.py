"""Refresh the ladder map for the current top-N and download the replays where
each top team WON by the biggest margin.

The ladder moved since HANDOFF section 10 was written (tetsuya 3048->3132,
kawa 3196->3125, and peikopon / ReCurSiON / Thomas Tschinkel / Kobe BRYANT /
Gekkotron are all new in the top 8). Their winning games are the only honest
picture of what currently beats what.

Downloads only -- extraction and agreement-checking are separate steps, because
HANDOFF section 10 established that most of these agents are adaptive and their
traces must NOT be replayed blindly (pbt/agreement.py).

Usage:
    /home/yilewang/kagg-env/bin/python -m planner.fetch_top_replays --top 8 --per-team 2
"""
import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pbt.build_pool import _api, leaderboard, crawl, CACHE, REPLAYS  # noqa: E402


def pick_wins(cache, team, k=2, min_margin=5000):
    """Episodes where `team` won by the largest margin."""
    got = []
    for eid, rec in cache["episodes"].items():
        if len(rec) != 2:
            continue
        for i, a in enumerate(rec):
            b = rec[1 - i]
            if a["team"] == team and a["reward"] > b["reward"]:
                margin = a["reward"] - b["reward"]
                if margin >= min_margin:
                    got.append((margin, int(eid), a["seat"], b["team"], a["reward"], b["reward"]))
    got.sort(reverse=True)
    return got[:k]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--per-team", type=int, default=2)
    ap.add_argument("--min-margin", type=float, default=5000)
    args = ap.parse_args()

    api = _api()
    teams = leaderboard(api, n=args.top)
    print("current top of ladder:")
    for t in teams:
        print(f"  {t['team']:<26} {t['score']:>8.1f}  (team_id {t['team_id']})")

    # Force a refresh for these teams so we get their CURRENT submission.
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {"episodes": {}, "teams": {}}
    for t in teams:
        cache["teams"].pop(str(t["team_id"]), None)
    json.dump(cache, open(CACHE, "w"))

    print("\ncrawling episode metadata (no replay bytes yet)...")
    cache = crawl(api, teams)

    print(f"\ncached: {len(cache['teams'])} teams, {len(cache['episodes'])} episodes")
    print("\npicking each team's biggest wins:")
    picks = []
    for t in teams:
        wins = pick_wins(cache, t["team"], k=args.per_team, min_margin=args.min_margin)
        for margin, eid, seat, opp, mine, theirs in wins:
            print(f"  {t['team']:<24} ep {eid} seat{seat} {mine:>9,.0f} vs {theirs:>9,.0f} "
                  f"(+{margin:>8,.0f}) vs {opp}")
            picks.append((t["team"], eid, seat))

    print(f"\ndownloading {len(picks)} replays...")
    ok = 0
    for team, eid, seat in picks:
        dest = os.path.join(REPLAYS, f"episode-{eid}-replay.json")
        if os.path.exists(dest):
            print(f"  {eid} already present")
            ok += 1
            continue
        try:
            api.competition_download_replay(eid, REPLAYS)
            ok += 1
            print(f"  {eid} ok ({team})")
        except Exception as e:
            print(f"  {eid} FAILED {repr(e)[:100]}")
        time.sleep(0.5)
    print(f"\n{ok}/{len(picks)} replays available")

    manifest = os.path.join(ROOT, "logs", "planner", "top_replays.json")
    json.dump([{"team": t, "episode": e, "seat": s} for t, e, s in picks],
              open(manifest, "w"), indent=1)
    print(f"manifest: {manifest}")


if __name__ == "__main__":
    main()
