"""Emit the route table as a flat 1-D array over an explicit state space.

This REPLACES `pbt/treeroute.py` as the editing substrate. Same guarantee --
`_kawa_actions` returns a proxy so all three table readers resolve together --
but the tape becomes an addressable array instead of a compressed CART blob.

WHY THIS AND NOT THE TREE. The CART was structure for its own sake. It cost
41 KB of opaque base64, needed a decode step at first use, and answered a
lookup in ~13 comparisons that an array answers in one. Nothing depended on
its branch structure: the leaves were already (table, step) references. The
tree's only real product was the SUBSTRATE -- a dict you could override one
key in -- and a flat array is a strictly better substrate.

THE STATE SPACE, written down. A route decision is a function of exactly three
things and the tape has always known it:

    legacy  in {0, 1}      `_kawa_use_legacy_layout(obs)`, a per-seat latch
    label   in {0 .. 4}    `_kawa_route_label(obs)`, pure
    step    in {0 .. 718}

    s1 = (legacy * 5 + label) * 719 + step          |s1| = 2 * 5 * 719 = 7,190

There is no s2. The opponent does not enter the ROUTE -- it enters the eleven
guards, which are already white-box and already reactive. See the module note
at the bottom of this docstring before adding an opponent axis.

THE CODE SPACE IS THE SAME SPACE. `s1` decomposes as `table * 719 + step`,
because table index IS `legacy * 5 + label`. So a code and a key are the same
kind of integer, and the identity table is `_FR_CODES[i] = i`:

    _FR_CODES[i] = j     state i plays whatever state j plays
    _FR_EDITS[i] = act   state i plays this literal action instead

The first is a re-point (free, always a legal action, cannot desync the ten
arrays); the second is a novel action. Both are consulted by all three readers.

WHY THE ARRAY IS NOT WRITTEN OUT AS A LITERAL. 7,190 identity ints cost 42,028
bytes of source -- MORE than the tree blob it replaces, to say nothing. It is
built with `list(range(_FR_N))` and deviations are applied from a sparse
`_FR_REMAP`, so the file carries only what actually differs from the tape while
`_FR_CODES` is still a real, mutable, indexable list at runtime. Vectorised
work loads it into numpy on the tooling side: `dynamic/tape/route_array.py`.

NO NUMPY IN THE AGENT, deliberately. The lookup runs 3 reads x 720 turns =
2,160 times per episode; boxed numpy scalar indexing is slower than list
indexing at that size, and the base agent's stdlib-only import set (base64,
copy, json, math, zlib) is a property worth keeping when the sandbox is
someone else's. numpy is a search-time tool, not a runtime one.

ON ADDING s2 (an opponent axis). The layout `(legacy, label, step)` extends to
`(opp, legacy, label, step)` by prefixing a stride -- the code below needs one
extra multiply. Do NOT do it yet. Only 2,133 of the 7,190 keys are reachable
at all (29.7%; 4 of the 10 tables are never selected), edits at reachable keys
measured between -6k and -299k, and an opponent axis multiplies the parameters
to fit by |s2| while the pool that scores them stays the same size. Condition
on the opponent in the guards, where it is already free, until there is
evidence a route-level split pays.
"""
import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Order is load-bearing: it defines the index space. table = legacy * 5 + label.
LABELS = ("10c4s_3q", "8c6s_3q", "6c8s_3q",
          "6c12s_4q_first_yarn", "6c12s_4q_second_yarn")
SUFFIX = {"10c4s_3q": "10C4S_3Q", "8c6s_3q": "8C6S_3Q", "6c8s_3q": "6C8S_3Q",
          "6c12s_4q_first_yarn": "6C12S_4Q_FIRST_YARN",
          "6c12s_4q_second_yarn": "6C12S_4Q_SECOND_YARN"}
NAMES = [("_LEGACY_ACTIONS_" if lg else "_ACTIONS_") + SUFFIX[lb]
         for lg in (0, 1) for lb in LABELS]


def base_tables(path):
    """The ten arrays, read from the agent file being flattened.

    Never from a snapshot on disk: a snapshot can go stale against the file
    being baked, and an array fitted to a stale table is a silent behaviour
    change wearing an equivalence proof.
    """
    spec = importlib.util.spec_from_file_location("flatroute_base", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    tables = [getattr(m, n) for n in NAMES]
    lengths = {len(t) for t in tables}
    if len(lengths) != 1:
        raise ValueError("tables differ in length: %s" % sorted(lengths))
    return tables, lengths.pop()


_TEMPLATE = '''

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

_FR_LABELS = __LABELS__
_FR_LABEL_CODE = {_n: _i for _i, _n in enumerate(_FR_LABELS)}
_FR_NLABEL = len(_FR_LABELS)
_FR_STEPS = __STEPS__
_FR_N = 2 * _FR_NLABEL * _FR_STEPS
_FR_TABLES = [__TABLES__]

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
'''


def flatroute_src(base):
    """The appended source block, fitted to `base`'s own ten arrays."""
    _tables, n_steps = base_tables(base)     # validated, not embedded
    return (_TEMPLATE
            .replace("__LABELS__", repr(list(LABELS)))
            .replace("__STEPS__", repr(n_steps))
            .replace("__TABLES__", ", ".join(NAMES)))
