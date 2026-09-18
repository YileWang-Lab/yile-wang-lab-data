"""Tape optimiser, stage 1: can the tape survive an edit to day 0's market line?

Day 0 is the highest-leverage single step -- it sets hires, herd mix, seed mix
and the feed buffer, which is exactly the parameter set the replay analyses keep
pointing at. It is also the cheapest possible probe of tape brittleness: the
market list changes no unit position, so if anything is editable, this is.

If day-0 edits survive, there is a real search space and the optimiser can walk
outward step by step. If they collapse the run, the tape has to be rebuilt from
scratch rather than tuned.
"""

_TEMPLATE = '''

# ============ day-0 market override (pbt/tape_edit.py) ============
_D0_MARKET = __MARKET__

def _d0_patch():
    for name in ("_ACTIONS_10C4S_3Q", "_ACTIONS_8C6S_3Q", "_ACTIONS_6C8S_3Q",
                 "_ACTIONS_6C12S_4Q_FIRST_YARN", "_ACTIONS_6C12S_4Q_SECOND_YARN",
                 "_ACTIONS"):
        tape = globals().get(name)
        if isinstance(tape, list) and tape and isinstance(tape[0], dict):
            tape[0] = dict(tape[0])
            tape[0]["market"] = [list(o) for o in _D0_MARKET]

_d0_patch()


def _tape_edit_entry(obs):
    return agent(obs)
'''


def day0_src(market):
    return _TEMPLATE.replace("__MARKET__", repr([list(o) for o in market]))
