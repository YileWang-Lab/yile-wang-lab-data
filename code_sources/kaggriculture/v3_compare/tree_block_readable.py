

# ============ route table as a perfect-fit CART (pbt/treeroute.py) ============
# Fitted to THIS file's own ten route arrays, so the tree and the tape cannot
# drift apart. It is a lookup substitution and nothing else: the eleven guards
# above are untouched and the expected score is the array's, to the dollar.
# Verify with `dynamic/tape/v3_bench.py` (fast sweep) and
# `dynamic/tape/v3_submit_check.py` (kaggle_environments, by file path).
# NOTE: equivalence is a property of a BUILD, not of this generator -- rerun
# both checks after regenerating rather than trusting a number in a comment.
# `_kawa_actions` returns a proxy rather than a list so that all THREE readers
# of the table -- the base lookup, `_trace_actor_action` (current step, weed
# replay) and `_future_sells` (step + 1, pre-empt borrow) -- resolve through the
# same tree. Editing `_TR_EDITS` is therefore coherent at every site.
import base64 as _tr_b64, json as _tr_json, zlib as _tr_zlib

_TR_BLOB = "<37980 chars of zlib+base64 -- branch structure only, no actions>"
_TR_LABELS = ['10c4s_3q', '8c6s_3q', '6c8s_3q', '6c12s_4q_first_yarn', '6c12s_4q_second_yarn']
_TR_LABEL_CODE = {_n: _i for _i, _n in enumerate(_TR_LABELS)}
_TR_STEPS = 719
_TR_TABLES = [_ACTIONS_10C4S_3Q, _ACTIONS_8C6S_3Q, _ACTIONS_6C8S_3Q, _ACTIONS_6C12S_4Q_FIRST_YARN, _ACTIONS_6C12S_4Q_SECOND_YARN, _LEGACY_ACTIONS_10C4S_3Q, _LEGACY_ACTIONS_8C6S_3Q, _LEGACY_ACTIONS_6C8S_3Q, _LEGACY_ACTIONS_6C12S_4Q_FIRST_YARN, _LEGACY_ACTIONS_6C12S_4Q_SECOND_YARN]
_TR_EDITS = {}          # (legacy, label, step) -> action, overrides one key
_TR_NODES = []


def _tr_nodes():
    if not _TR_NODES:
        _TR_NODES.extend(_tr_json.loads(
            _tr_zlib.decompress(_tr_b64.b64decode(_TR_BLOB)).decode("ascii")))
    return _TR_NODES


def _tr_lookup(legacy, label, step):
    step = min(max(0, int(step)), _TR_STEPS - 1)
    edit = _TR_EDITS.get((legacy, label, step))
    if edit is not None:
        return edit
    x = (legacy, _TR_LABEL_CODE[label], step)
    nodes = _tr_nodes()
    i = 0
    while True:
        feat = nodes[i]
        if feat < 0:
            return _TR_TABLES[nodes[i + 1]][nodes[i + 2]]
        i = nodes[i + 2] if x[feat] <= nodes[i + 1] else nodes[i + 3]


class _TrRoute(object):
    """Indexes like the array it replaces. len() and [int] are the only uses."""

    __slots__ = ("_legacy", "_label")

    def __init__(self, legacy, label):
        self._legacy, self._label = legacy, label

    def __len__(self):
        return _TR_STEPS

    def __getitem__(self, step):
        return _tr_lookup(self._legacy, self._label, step)


_TR_ROUTES = {(_lg, _lb): _TrRoute(_lg, _lb)
              for _lg in (0, 1) for _lb in _TR_LABELS}


def _kawa_actions(obs):
    # Same two calls in the same order as the original (source 135-136).
    # `_kawa_use_legacy_layout` latches per seat and must run once per call, and
    # `_kawa_route_label` is resolved at call time so a tape-selection override
    # appended after this block still wins.
    label = _kawa_route_label(obs)
    legacy = 1 if _kawa_use_legacy_layout(obs) else 0
    return _TR_ROUTES[(legacy, label)]


def _treeroute_entry(obs):
    return agent(obs)
