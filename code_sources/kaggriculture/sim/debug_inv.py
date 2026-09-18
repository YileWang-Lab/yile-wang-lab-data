import sys
sys.path.insert(0, "/home/yilewang/kaggriculture")
sys.path.insert(0, "/home/yilewang/kaggriculture/agent")
from kaggle_environments import make
import main as agent_mod

env = make("kaggriculture", configuration={"episodeSteps": 720}, debug=True)
env.reset(num_agents=2)

for step in range(30):
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

    farm0 = env.state[0].observation["farms"][0]
    priv0 = env.state[0].observation["private"]
    invs = priv0["inventories"]
    nonempty = [(i, dict(inv)) for i, inv in enumerate(invs) if len(inv) > 0]
    print(f"step={step} day={env.state[0].observation['day']} hour={env.state[0].observation['hour']} "
          f"action={action0['farmer']} hands_actions={action0['hands']} shed_wheat={priv0['shed'].get('WHEAT',0)} "
          f"nonempty_inv={nonempty}")
