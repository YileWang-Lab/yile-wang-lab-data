"""Histogram of what every unit actually spends its turns on, plus a per-turn
trace for one day. If an animal build is starving, the answer is here: either
the actions never get issued, or they get issued and the engine no-ops them.
"""
import sys
sys.path.insert(0, "/home/yilewang/kaggriculture")
import json
from collections import Counter
from kaggle_environments import make
from search.agent_instance import load_instance

base = json.load(open("/home/yilewang/kaggriculture/search/checkpoints/best_genome.json"))["params"]
params = dict(base)
params["TARGET_COUNTS"] = {"COW": 7, "SHEEP": 3, "GOOSE": 0,
                           "STRAWBERRY": 0, "MELON": 0, "WHEAT": 0}

mod = load_instance(params)
env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": 7}, debug=True)
env.reset(num_agents=2)

hist = Counter()
TRACE_DAY = 9
for step in range(24 * 12):
    st = env.state
    obs = dict(st[0].observation)
    obs["player"] = 0
    day, hour = obs["day"], obs["hour"]
    a = mod.agent(obs)

    ops = [a["farmer"][0]] + [h[0] for h in a["hands"]]
    for op in ops:
        hist[op] += 1

    if day == TRACE_DAY:
        farm = obs["farms"][0]
        priv = obs["private"]
        pos = [farm["farmer"]] + list(farm["hands"])
        invs = priv["inventories"]
        detail = []
        for i, op in enumerate(ops):
            p = pos[i] if i < len(pos) else None
            inv = {k: v for k, v in (invs[i] or {}).items()} if i < len(invs) else {}
            detail.append(f"u{i}@{p}{op}{inv if inv else ''}")
        print(f"  h{hour:>2} shedW={priv['shed'].get('WHEAT',0)} "
              f"mkt={[o[:3] for o in a['market']][:3]} | " + "  ".join(detail))

    env.step([a, {"farmer": ["PASS"], "hands": [], "market": []}])

print("\naction histogram over 12 days (all units):")
for op, n in hist.most_common():
    print(f"  {op:<20} {n:>5}")
