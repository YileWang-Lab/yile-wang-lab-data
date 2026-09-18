"""Where does the 4x gap to the reference agents come from?

Same episode, both agents, counting what each actually does with its turns.
`useful` = actions that change farm/market state (plant, water, harvest, feed,
care, fertilize, collect, build, place). `move` = pure walking. `idle` = PASS.
An agent with the right portfolio but a low useful/turn ratio is losing to
logistics, not to strategy.
"""
import importlib.util
import json
import sys
from collections import Counter

sys.path.insert(0, "/home/yilewang/kaggriculture")
from kaggle_environments import make
from search.agent_instance import load_instance

USEFUL = {"PLANT", "WATER", "HARVEST", "FEED", "CARE", "FERTILIZE",
          "COLLECT_FERTILIZER", "BUILD_COOP", "BUILD_PASTURE", "PLACE", "DIG", "PICKUP", "DROP"}
MOVE = {"NORTH", "SOUTH", "EAST", "WEST"}

REF = sys.argv[1] if len(sys.argv) > 1 else "v111-8c4s-economic-core-premium-lead"
spec = importlib.util.spec_from_file_location("ref", f"/home/yilewang/kaggriculture/opponents/{REF}.py")
ref = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ref)

params = json.load(open("/home/yilewang/kaggriculture/search/checkpoints/best_r3_gen15.json"))["params"]
ours = load_instance(params)

env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": 7}, debug=False)
env.reset(num_agents=2)

stats = [Counter(), Counter()]
hands_seen = [0, 0]
final = None
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
        ops = [a["farmer"][0]] + [h[0] for h in (a.get("hands") or [])]
        hands_seen[p] = max(hands_seen[p], len(a.get("hands") or []))
        for op in ops:
            key = "useful" if op in USEFUL else ("move" if op in MOVE else "idle")
            stats[p][key] += 1
            stats[p][f"op:{op}"] += 1
        stats[p]["market_orders"] += len(a.get("market") or [])
    env.step(acts)

final = env.state
for p, label in ((0, "OURS"), (1, f"REF({REF[:26]})")):
    s = stats[p]
    total = s["useful"] + s["move"] + s["idle"]
    money = final[p].observation["farms"][p]["money"]
    print(f"\n{label}  final=${money:,.0f}  max_hands={hands_seen[p]}")
    print(f"  turns issued={total:,}  useful={s['useful']:,} ({s['useful']/max(total,1):.0%})  "
          f"move={s['move']:,} ({s['move']/max(total,1):.0%})  idle={s['idle']:,} ({s['idle']/max(total,1):.0%})")
    print(f"  market_orders={s['market_orders']:,}")
    tops = [(k[3:], v) for k, v in s.most_common() if k.startswith("op:")][:9]
    print("  top ops:", ", ".join(f"{k}={v}" for k, v in tops))
