import sys
sys.path.insert(0, "/home/yilewang/kaggriculture")
sys.path.insert(0, "/home/yilewang/kaggriculture/agent")
from kaggle_environments import make
import main as agent_mod

env = make("kaggriculture", configuration={"episodeSteps": 720}, debug=True)
env.reset(num_agents=2)

for step in range(200):
    state = env.state
    obs0 = state[0].observation
    obs_dict = {
        "player": 0, "day": obs0["day"], "hour": obs0["hour"],
        "farms": obs0["farms"], "market": obs0["market"], "town": obs0["town"],
        "private": state[0].observation["private"],
    }
    action0 = agent_mod.agent(obs_dict)
    action1 = {"farmer": ["PASS"], "hands": [], "market": []}
    env.step([action0, action1])

    if step % 24 in (2, 23) or step < 26:
        farm0 = env.state[0].observation["farms"][0]
        animals = []
        for y, row in enumerate(farm0["tiles"]):
            for x, t in enumerate(row):
                if isinstance(t, dict) and "animal" in t:
                    animals.append((x, y, t["animal"], t["fed_today"], t["consecutive_unfed"], t["yield_units"]))
        d = env.state[0].observation["day"]
        h = env.state[0].observation["hour"]
        print(f"step={step} day={d} hour={h} money={farm0['money']:.0f} n_animals_alive={len(animals)}")
        for a in animals[:6]:
            print(f"   {a}")
