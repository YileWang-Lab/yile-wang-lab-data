import sys
sys.path.insert(0, "/home/yilewang/kaggriculture")
from kaggle_environments import make

env = make("kaggriculture", configuration={"episodeSteps": 720}, debug=True)
env.run(["agent/main.py", "starter"])

money_by_day = {}
for step_states in env.steps:
    obs0 = step_states[0].observation
    day = obs0.get("day", None)
    if day is None:
        continue
    farms = obs0.get("farms", [])
    if not farms:
        continue
    if day not in money_by_day:
        money_by_day[day] = (farms[0]["money"], farms[1]["money"])

print("day  agent$      starter$")
for d in sorted(money_by_day):
    a, s = money_by_day[d]
    print(f"{d:>3}  {a:>10,.0f}  {s:>10,.0f}")

final = env.steps[-1]
for i, s in enumerate(final):
    print(f"Player {i}: reward={s.reward}  status={s.status}")

farm0 = final[0].observation["farms"][0]
roles = {}
counts = {}
for row in farm0["tiles"]:
    for t in row:
        if t is None:
            counts["EMPTY"] = counts.get("EMPTY", 0) + 1
        elif t == "LOCKED":
            counts["LOCKED"] = counts.get("LOCKED", 0) + 1
        elif isinstance(t, dict):
            k = t.get("kind")
            if k == "PLANT":
                key = f"PLANT:{t['crop']}"
            elif "animal" in t:
                key = f"ANIMAL:{t['animal']}"
            elif k in ("COOP", "PASTURE"):
                key = f"EMPTY_STRUCT:{k}"
            else:
                key = k
            counts[key] = counts.get(key, 0) + 1
print("\nFinal tile counts (agent):", counts)
print("hands:", len(farm0["hands"]), "unlocked:", farm0["unlocked_quadrants"])
priv = final[0].observation["private"]
print("shed:", priv["shed"])
print("seeds:", priv["seeds"])
