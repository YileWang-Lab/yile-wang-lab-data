

# =========== route table as a flat array (pbt/flatroute.py) ===========
# The tape, addressed. State s1 = (legacy * 5 + label) * 719 + step, one int in
# [0, 7190). `_FR_CODES[i]` is another such int and decodes as
# `divmod(code, 719) -> (table, step)`, so identity is `_FR_CODES[i] == i` and
# the ten arrays above are still the only place actions live.
#
#     _FR_REMAP[i] = j      state i plays state j's action   (edit a code)
#     _FR_EDITS[i] = act    state i plays this literal action (edit an action)
#
# `_kawa_actions` returns a proxy rather than a list so that all THREE readers
# of the table -- the base lookup, `_trace_actor_action` (current step, weed
# replay) and `_future_sells` (step + 1, pre-empt borrow) -- go through the same
# array. An edit is therefore coherent at every site by construction.
#
# With both dicts empty this file is the base agent exactly, to the dollar.
# Equivalence is a property of a BUILD, not of the generator: re-run
# `dynamic/tape/v3_bench.py` and `dynamic/tape/v3_submit_check.py` after
# regenerating rather than trusting a number in a comment.

_FR_LABELS = ['10c4s_3q', '8c6s_3q', '6c8s_3q', '6c12s_4q_first_yarn', '6c12s_4q_second_yarn']
_FR_LABEL_CODE = {_n: _i for _i, _n in enumerate(_FR_LABELS)}
_FR_NLABEL = len(_FR_LABELS)
_FR_STEPS = 719
_FR_N = 2 * _FR_NLABEL * _FR_STEPS
_FR_TABLES = [_ACTIONS_10C4S_3Q, _ACTIONS_8C6S_3Q, _ACTIONS_6C8S_3Q, _ACTIONS_6C12S_4Q_FIRST_YARN, _ACTIONS_6C12S_4Q_SECOND_YARN, _LEGACY_ACTIONS_10C4S_3Q, _LEGACY_ACTIONS_8C6S_3Q, _LEGACY_ACTIONS_6C8S_3Q, _LEGACY_ACTIONS_6C12S_4Q_FIRST_YARN, _LEGACY_ACTIONS_6C12S_4Q_SECOND_YARN]

_FR_REMAP = {}          # sparse: state index -> state index whose action to play
_FR_EDITS = {}          # sparse: state index -> literal action dict

# A real list, so search tooling can mutate it in place and numpy can wrap it.
_FR_CODES = list(range(_FR_N))
for _k, _v in _FR_REMAP.items():
    _FR_CODES[_k] = _v


def _fr_key(legacy, label, step):
    """(legacy, label, step) -> s1. The one place the layout is defined."""
    return (legacy * _FR_NLABEL + _FR_LABEL_CODE[label]) * _FR_STEPS + step


def _fr_lookup(legacy, label, step):
    step = min(max(0, int(step)), _FR_STEPS - 1)
    i = _fr_key(legacy, label, step)
    act = _FR_EDITS.get(i)
    if act is not None:
        return act
    t, s = divmod(_FR_CODES[i], _FR_STEPS)
    return _FR_TABLES[t][s]


class _FrRoute(object):
    """Indexes like the array it replaces. len() and [int] are the only uses."""

    __slots__ = ("_legacy", "_label")

    def __init__(self, legacy, label):
        self._legacy, self._label = legacy, label

    def __len__(self):
        return _FR_STEPS

    def __getitem__(self, step):
        return _fr_lookup(self._legacy, self._label, step)


_FR_ROUTES = {(_lg, _lb): _FrRoute(_lg, _lb)
              for _lg in (0, 1) for _lb in _FR_LABELS}


def _kawa_actions(obs):
    # Same two calls in the same order as the original (source 135-136).
    # `_kawa_use_legacy_layout` latches per seat and must run once per call, and
    # `_kawa_route_label` is resolved at call time so a tape-selection override
    # appended after this block still wins.
    label = _kawa_route_label(obs)
    legacy = 1 if _kawa_use_legacy_layout(obs) else 0
    return _FR_ROUTES[(legacy, label)]


def _flatroute_entry(obs):
    return agent(obs)
