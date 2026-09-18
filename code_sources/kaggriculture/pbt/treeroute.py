"""Emit the route table as a perfect-fit CART, baked into the submission.

WHAT THIS BUYS, and what it does not. The tape is two things glued together: a
7,190-entry route table and eleven reactive guards. The guards are white-box
already -- named functions reading the observation. The TABLE was the opaque
half, and the reason section 4 says it cannot be edited. This layer replaces the
array indexing with a decision tree over (legacy, label, step). The function is
UNCHANGED -- verified at three levels on 2026-08-21:

    table   7,190/7,190 keys return their own action
    action  12,942/12,942 fields identical to kawa on the same observations
    play    96/96 pool games, final banks equal kawa's seed by seed, plus a
            12-seed mirror at paired margin exactly +0, 0 nonzero seeds

So this is SCORE-NEUTRAL BY CONSTRUCTION. It is worth shipping only as the
substrate for edits; on its own it changes nothing and can only add risk.

WHY A LIST PROXY RATHER THAN A LOOKUP FUNCTION. Three call sites read the table
and replacing only the base lookup leaves the other two acting on the plan the
tape used to have:

    line 990  `actions[step]`                     the base action
    line 361  `_trace_actor_action`, CURRENT step  `_weed_repair_action` replays
              a deferred op for up to `_WEED_REPLAY_STEPS` = 8 steps
    line 299  `_future_sells`, step + 1            `_preempt_shift` borrows
              tomorrow's premium sells into today and books the amount in
              `_SHIFT_STATE["due"]` for `_repay_shift` to subtract next turn

All three only ever call `len()` and index with an int -- no slicing, no
iteration -- so `_kawa_actions` can return an object with `__len__` and
`__getitem__` and every site goes through the tree together. An edit is then
coherent everywhere by construction instead of by remembering to patch.

THE TREE IS BUILT AT BAKE TIME, not at import. Growing it is a few seconds of
CART fitting and a Kaggle agent has an init budget, so the fitted structure ships
as a zlib+base64 blob -- the same stdlib the base agent already uses. Leaves hold
(table index, step) rather than actions, so the 3,000 distinct actions are NOT
duplicated: they stay in the ten arrays already in the file, and the blob is only
the branch structure.

EDITING. `_TR_EDITS[(legacy, label, step)] = action` overrides one key, is
consulted by all three call sites, and is the surface `dynamic/tape/leaf_scan.py`
exists to populate. Leave it empty and the file is the shipped agent exactly.
"""
import base64
import importlib.util
import json
import os
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, "opponents", "kaggriculture-multi-route-farming-agent.py")

# Order is load-bearing: it is the index space the blob's leaves refer to, and
# the order `_TR_TABLES` is emitted in. table index = legacy * 5 + label code.
LABELS = ("10c4s_3q", "8c6s_3q", "6c8s_3q",
          "6c12s_4q_first_yarn", "6c12s_4q_second_yarn")
SUFFIX = {"10c4s_3q": "10C4S_3Q", "8c6s_3q": "8C6S_3Q", "6c8s_3q": "6C8S_3Q",
          "6c12s_4q_first_yarn": "6C12S_4Q_FIRST_YARN",
          "6c12s_4q_second_yarn": "6C12S_4Q_SECOND_YARN"}
NAMES = [("_LEGACY_ACTIONS_" if lg else "_ACTIONS_") + SUFFIX[lb]
         for lg in (0, 1) for lb in LABELS]


def _base_tables(path=BASE):
    """The ten arrays, read from the agent file itself.

    Deliberately not from `logs/tape/tables.json`: that snapshot can go stale
    against the file being baked, and a tree fitted to a stale table would be a
    silent behaviour change wearing an equivalence proof.
    """
    spec = importlib.util.spec_from_file_location("treeroute_base", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    tables = [getattr(m, n) for n in NAMES]
    lengths = {len(t) for t in tables}
    if len(lengths) != 1:
        raise ValueError(f"tables differ in length: {sorted(lengths)}")
    return tables, lengths.pop()


def _flatten(root, leaf_ref):
    """Tree -> flat int array. Four slots per node, offsets are element indices.

    internal  [feat, thr, left_offset, right_offset]
    leaf      [-1, table_index, step, 0]
    """
    out = []

    def emit(nd):
        idx = len(out)
        if "leaf" in nd:
            t, s = leaf_ref[nd["leaf"]]
            out.extend((-1, t, s, 0))
            return idx
        out.extend((0, 0, 0, 0))
        left = emit(nd["left"])
        right = emit(nd["right"])
        out[idx], out[idx + 1], out[idx + 2], out[idx + 3] = \
            nd["feat"], nd["thr"], left, right
        return idx

    emit(root)
    return out


_TEMPLATE = '''

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

_TR_BLOB = "__BLOB__"
_TR_LABELS = __LABELS__
_TR_LABEL_CODE = {_n: _i for _i, _n in enumerate(_TR_LABELS)}
_TR_STEPS = __STEPS__
_TR_TABLES = [__TABLES__]
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
'''


def treeroute_src(base=BASE):
    """The appended source block, with the fitted tree inlined as a blob."""
    from dynamic.tape.tree_table import grow

    tables, n_steps = _base_tables(base)
    # Rows are the same 7,190 keys tree_table fits, but the codebook is replaced
    # by a reference into the arrays already present in the file.
    index, X, y, leaf_ref = {}, [], [], []
    for t, table in enumerate(tables):
        legacy, code = divmod(t, len(LABELS))
        for step, action in enumerate(table):
            text = json.dumps(action, sort_keys=True, separators=(",", ":"))
            slot = index.get(text)
            if slot is None:
                slot = index[text] = len(leaf_ref)
                leaf_ref.append((t, step))
            X.append([legacy, code, step])
            y.append(slot)

    nodes = _flatten(grow(X, y), leaf_ref)
    blob = base64.b64encode(zlib.compress(
        json.dumps(nodes, separators=(",", ":")).encode("ascii"), 9)).decode("ascii")
    return (_TEMPLATE
            .replace("__BLOB__", blob)
            .replace("__LABELS__", repr(list(LABELS)))
            .replace("__STEPS__", repr(n_steps))
            .replace("__TABLES__", ", ".join(NAMES)))
