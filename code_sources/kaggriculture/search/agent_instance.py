"""Loads agent/main.py as a fresh, independently-namespaced module instance.

The agent uses module-level globals for its planning state (S dict, tunable
constants). Two players in a self-play matchup calling the *same* imported
module would share that state and corrupt each other's zone/role/errand
tracking (both players number their units 0..N the same way). Loading the
source file twice under different module names gives each an isolated globals
dict, so multiple independently-configured "instances" can coexist safely
within one process.
"""
import importlib.util
import os

AGENT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent", "main.py")

_counter = [0]


def load_instance(params=None):
    _counter[0] += 1
    name = f"kaggriculture_agent_instance_{_counter[0]}"
    spec = importlib.util.spec_from_file_location(name, AGENT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if params:
        mod.configure(params)
    else:
        mod._reset_state()
    return mod
