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
        "player": 0,
        "day": obs0["day"], "hour": obs0["hour"],
        "farms": obs0["farms"], "market": obs0["market"], "town": obs0["town"],
        "private": state[0].observation["private"],
    }
    action0 = agent_mod.agent(obs_dict)

    obs1 = state[1].observation
    obs_dict1 = {
        "player": 1,
        "day": obs1["day"], "hour": obs1["hour"],
        "farms": obs1["farms"], "market": obs1["market"], "town": obs1["town"],
        "private": state[1].observation["private"],
    }
    action1 = {"farmer": ["PASS"], "hands": [], "market": []}

    state[0].action = action0
    state[1].action = action1
    env.step([action0, action1])

    if step < 30 or step % 24 == 0:
        farm0 = env.state[0].observation["farms"][0]
        priv0 = env.state[0].observation["private"]
        print(f"step={step:>4} day={env.state[0].observation['day']} hour={env.state[0].observation['hour']} "
              f"money={farm0['money']:.0f} farmer_pos={farm0['farmer']} action={action0['farmer']} "
              f"n_hands={len(farm0['hands'])} role_n={len(agent_mod.S['role'])} "
              f"zone0_len={len(agent_mod.S['zones'].get(0, []))} shed={dict(priv0['shed'])}")
        if step in (0, 1, 2, 5, 10, 20):
            z = agent_mod.S['zones'].get(0, [])[:8]
            print(f"    zone0 sample={z}")
            for (x, y) in z[:5]:
                t = farm0['tiles'][y][x]
                role = agent_mod.S['role'].get((x, y))
                print(f"      tile({x},{y}) role={role} state={t}")
            print(f"    day_tasks[0]={agent_mod.S['day_tasks'].get(0)}  ptr[0]={agent_mod.S['ptr'].get(0)}")
