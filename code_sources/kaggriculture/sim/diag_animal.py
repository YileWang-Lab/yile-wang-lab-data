"""Why does an animal-heavy build score ~200 instead of ~40,000?

Tracks the full animal pipeline day by day:
  bought (shed) -> carried (inventory) -> placed (tile) -> fed -> producing
A break anywhere in that chain zeroes the build.
"""
import sys
sys.path.insert(0, "/home/yilewang/kaggriculture")
import json
from kaggle_environments import make
from search.agent_instance import load_instance

base = json.load(open("/home/yilewang/kaggriculture/search/checkpoints/best_genome.json"))["params"]
params = dict(base)
params["TARGET_COUNTS"] = {"COW": 7, "SHEEP": 3, "STRAWBERRY": 0, "MELON": 0, "WHEAT": 0}

mod = load_instance(params)
env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": 7}, debug=True)
env.reset(num_agents=2)

print(f"{'day':>3} {'money':>8} {'shed_animals':>12} {'carried':>8} {'placed':>7} "
      f"{'structs':>8} {'fed':>4} {'yield':>6} {'wheat':>6} {'hands':>5}")
for step in range(720):
    st = env.state
    obs = dict(st[0].observation)
    obs["player"] = 0
    a = mod.agent(obs)
    env.step([a, {"farmer": ["PASS"], "hands": [], "market": []}])

    # Sample at MIDDAY: end-of-day refresh clears hands and fed_today, so an
    # hour-23 sample always reads hands=0/fed=0 and looks like a broken agent
    # even when both are working.
    if step % 24 != 12:
        continue
    o = env.state[0].observation
    farm, priv = o["farms"][0], o["private"]
    shed = priv["shed"]
    shed_animals = sum(shed.get(k, 0) for k in ("COW", "SHEEP", "GOOSE"))
    carried = sum(sum(v for k, v in (inv or {}).items() if k in ("COW", "SHEEP", "GOOSE"))
                  for inv in priv["inventories"])
    placed = fed = yields = structs = 0
    for row in farm["tiles"]:
        for t in row:
            if isinstance(t, dict):
                if "animal" in t:
                    placed += 1
                    fed += int(t.get("fed_today", False))
                    yields += t.get("yield_units", 0)
                elif t.get("kind") in ("COOP", "PASTURE"):
                    structs += 1
    print(f"{o['day']:>3} {farm['money']:>8,.0f} {shed_animals:>12} {carried:>8} {placed:>7} "
          f"{structs:>8} {fed:>4} {yields:>6} {shed.get('WHEAT',0):>6} {len(farm['hands']):>5}")
    if o["day"] >= 14:
        break
