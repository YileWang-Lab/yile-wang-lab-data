"""Is a ladder agent a replayable tape, or adaptive?

Extracting one episode gives a *trace*, not a policy. If the agent replays a
fixed 719-step tape, three traces from three different games agree almost
perfectly and the tape can be reconstructed by majority vote (this is how the
V16-RC5 notebook rebuilt its route, reporting 99.91% market agreement). If the
agent reacts to its opponent, the traces diverge and blind replay produces a
degraded agent that only looked strong in the game it was copied from.

Run this BEFORE trusting any extracted pool member.
"""
import os, sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
REPLAYS = os.path.join(ROOT, "replays")


def agreement(traces):
    """Fraction of steps where all traces issue the identical action."""
    n = min(len(t) for t in traces)
    same_f = same_m = same_h = 0
    for i in range(n):
        fs = {tuple(t[i]["farmer"]) for t in traces}
        ms = {tuple(tuple(o) for o in t[i]["market"]) for t in traces}
        hs = {tuple(tuple(h) for h in t[i]["hands"]) for t in traces}
        same_f += len(fs) == 1
        same_m += len(ms) == 1
        same_h += len(hs) == 1
    return same_f / n, same_h / n, same_m / n, n


def majority(traces):
    """Per-step majority vote across traces."""
    n = min(len(t) for t in traces)
    out = []
    for i in range(n):
        f = Counter(tuple(t[i]["farmer"]) for t in traces).most_common(1)[0][0]
        h = Counter(tuple(tuple(x) for x in t[i]["hands"]) for t in traces).most_common(1)[0][0]
        m = Counter(tuple(tuple(o) for o in t[i]["market"]) for t in traces).most_common(1)[0][0]
        out.append({"farmer": list(f), "hands": [list(x) for x in h],
                    "market": [list(o) for o in m]})
    return out


def fetch(api, eid):
    path = os.path.join(REPLAYS, f"episode-{eid}-replay.json")
    if os.path.exists(path):
        return path
    api.competition_episode_replay(eid, path=REPLAYS, quiet=True)
    cand = [f for f in os.listdir(REPLAYS) if str(eid) in f]
    return os.path.join(REPLAYS, cand[0]) if cand else None
