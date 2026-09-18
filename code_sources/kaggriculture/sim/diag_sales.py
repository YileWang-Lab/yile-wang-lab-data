"""Our sales mix and land/hire profile vs a reference agent, same episode.

The reference schedule shows three concrete structural choices we can copy:
one land purchase only, cash-following hand counts, and ~300 units of
FERTILIZER sold (a free animal byproduct). This checks which of those we are
actually leaving on the table.
"""
import importlib.util
import json
import sys
from collections import Counter

sys.path.insert(0, "/home/yilewang/kaggriculture")
from kaggle_environments import make
from search.agent_instance import load_instance

REF = sys.argv[1] if len(sys.argv) > 1 else "v111-8c4s-economic-core-premium-lead"
spec = importlib.util.spec_from_file_location("ref", f"/home/yilewang/kaggriculture/opponents/{REF}.py")
ref = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ref)

params = json.load(open("/home/yilewang/kaggriculture/search/checkpoints/best_r3_gen15.json"))["params"]
ours = load_instance(params)

env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": 7}, debug=False)
env.reset(num_agents=2)

sells = [Counter(), Counter()]
lands = [0, 0]
hires = [0, 0]
hands_by_day = [{}, {}]
for step in range(720):
    if env.done:
        break
    st = env.state
    acts = []
    for p, fn in ((0, ours.agent), (1, ref.agent)):
        obs = dict(st[p].observation)
        obs["player"] = p
        obs["step"] = step
        a = fn(obs)
        acts.append(a)
        hands_by_day[p][step // 24] = max(hands_by_day[p].get(step // 24, 0),
                                          len(a.get("hands") or []))
        for o in (a.get("market") or []):
            if not o:
                continue
            if o[0] == "SELL" and len(o) > 2:
                sells[p][o[1]] += int(o[2])
            elif o[0] == "BUY_LAND":
                lands[p] += 1
            elif o[0] == "HIRE":
                hires[p] += 1
    env.step(acts)

for p, label in ((0, "OURS"), (1, f"REF({REF[:24]})")):
    farm = env.state[p].observation["farms"][p]
    print(f"\n{label}  final=${farm['money']:,.0f}  quadrants={len(farm['unlocked_quadrants'])} "
          f"land_orders={lands[p]}  total_hires={hires[p]}")
    print("  sells requested by product:",
          ", ".join(f"{k}={v:,}" for k, v in sells[p].most_common()))
    hs = hands_by_day[p]
    line = " ".join(f"{hs.get(d,0):>2}" for d in range(0, 30, 2))
    print(f"  hands (every 2nd day 0..28): {line}")
