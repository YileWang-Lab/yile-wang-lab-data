import sys
import copy

import agent_frontier
import agent_moon
import agent_v14
import agent_hamburger

def agent(obs, config=None):
    step = int(obs.get("step", 0))
    
    # 1. Moon Trace Router (Newest Frontier)
    moon_action = agent_moon.agent(copy.deepcopy(obs), config)
    
    # 2. Frontier Trace Router (Classic)
    frontier_action = agent_frontier.agent(copy.deepcopy(obs), config)
    
    # 3. Hamburger Agent (Robust heuristics)
    hamburger_action = agent_hamburger.agent(copy.deepcopy(obs), config)
    
    # 4. V14 Price-Aware Market Gate
    v14_action = agent_v14.agent(copy.deepcopy(obs))

    # STRATEGY:
    # Late game chaos (>500 steps): Moon traces run out, so we fallback to Hamburger.
    if step > 500:
        return hamburger_action

    # Early/Mid game: Favor Moon over Frontier if Moon has a valid action
    final_action = copy.deepcopy(moon_action)
    
    # Market Override Gate
    moon_market = final_action.get("market", [])
    v14_market = v14_action.get("market", [])
    
    if moon_market:
        # If V14 says HOLD (no market actions), we override the trace and HOLD for better prices.
        if not v14_market:
            final_action["market"] = []
    
    return final_action
