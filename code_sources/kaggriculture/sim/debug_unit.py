import sys
sys.path.insert(0, "/home/yilewang/kaggriculture")
sys.path.insert(0, "/home/yilewang/kaggriculture/agent")
from kaggle_environments import make
import main as agent_mod

env = make("kaggriculture", configuration={"episodeSteps": 720}, debug=True)
env.reset(num_agents=2)

TARGET_TILE = None  # discover a COW tile dynamically once built

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

    if TARGET_TILE is None:
        for y, row in enumerate(farm0["tiles"]):
            for x, t in enumerate(row):
                if isinstance(t, dict) and t.get("animal") == "COW":
                    TARGET_TILE = (x, y)
                    break
            if TARGET_TILE:
                break

    # find which unit owns TARGET_TILE
    owner = None
    if TARGET_TILE is not None:
        for u, zone in agent_mod.S["zones"].items():
            if TARGET_TILE in zone:
                owner = u
                break

    positions = [farm0["farmer"]] + list(farm0["hands"])
    owner_pos = positions[owner] if owner is not None and owner < len(positions) else None
    owner_inv = priv0["inventories"][owner] if owner is not None and owner < len(priv0["inventories"]) else None

    day, hour = env.state[0].observation["day"], env.state[0].observation["hour"]
    owner_zone = agent_mod.S["zones"].get(owner, []) if owner is not None else None
    owner_wheat_need = agent_mod._zone_daily_wheat(owner) if owner is not None else None
    print(f"step={step} day={day} hour={hour} n_hands={len(farm0['hands'])} zone_sig={agent_mod.S['zone_sig']} "
          f"target_tile={TARGET_TILE} owner_unit={owner} owner_zone_len={len(owner_zone) if owner_zone else 0} "
          f"owner_wheat_need={owner_wheat_need} last_day={agent_mod.S['last_day_for_unit'].get(owner) if owner is not None else None} "
          f"owner_pos={owner_pos} owner_inv={dict(owner_inv) if owner_inv else None} "
          f"day_tasks_owner={agent_mod.S['day_tasks'].get(owner) if owner is not None else None} "
          f"errand_owner={agent_mod.S['errand'].get(owner) if owner is not None else None}")
    if TARGET_TILE:
        tx, ty = TARGET_TILE
        t = farm0["tiles"][ty][tx]
        print(f"    tile_state fed_today={t.get('fed_today')} unfed={t.get('consecutive_unfed')}")
