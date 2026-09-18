"""Search the tape-selection rule.

The three dimensions in the search protocol -- expansion rhythm, crop mix,
hiring schedule -- are compiled into the tapes and cannot be edited from
outside (measured: 0-5% win rate for any overlay that touches farm state or
pre-empts a HIRE). But the base agent ships FIVE tapes, and each one *is* a
different mix and expansion plan:

    10c4s_3q             10 cows / 4 sheep, three quadrants
    8c6s_3q               8 cows / 6 sheep, three quadrants   (default)
    6c8s_3q               6 cows / 8 sheep, three quadrants
    6c12s_4q_first_yarn   6 cows / 12 sheep, four quadrants
    6c12s_4q_second_yarn  6 cows / 12 sheep, four quadrants

`_kawa_route_label` maps the town's shop draw onto one of them through five
hand-written buckets. That mapping is the reachable version of this search: it
selects mix and expansion without touching a single tile.

Buckets, in the order the original tests them:
    0  YARN_STORE is the first shop unlocked
    1  YARN_STORE within the first two
    2  YARN_STORE within the first three
    3  a milk shop (PIZZA/ICE_CREAM/SMOOTHIE) within the first three
    4  everything else
"""
ROUTES = ["10c4s_3q", "8c6s_3q", "6c8s_3q",
          "6c12s_4q_first_yarn", "6c12s_4q_second_yarn"]
DEFAULT = ["6c12s_4q_first_yarn", "6c12s_4q_second_yarn", "6c8s_3q",
           "10c4s_3q", "8c6s_3q"]

_TEMPLATE = '''

# ============ searched tape-selection rule (pbt/tapesel.py) ============
_TS_MAP = __MAP__
_TS_MILK = {"PIZZA_SHOP", "ICE_CREAM_SHOP", "SMOOTHIE_SHOP"}


def _kawa_route_label(obs):
    shops = list(((_get(obs, "town", {}) or {}).get("unlocked_shops", []) or []))
    if shops[:1] == ["YARN_STORE"]:
        return _TS_MAP[0]
    if "YARN_STORE" in shops[:2]:
        return _TS_MAP[1]
    if "YARN_STORE" in shops[:3]:
        return _TS_MAP[2]
    if _TS_MILK.intersection(shops[:3]):
        return _TS_MAP[3]
    return _TS_MAP[4]


def _tapesel_entry(obs):
    return agent(obs)
'''


def tapesel_src(mapping):
    return _TEMPLATE.replace("__MAP__", repr(list(mapping)))
