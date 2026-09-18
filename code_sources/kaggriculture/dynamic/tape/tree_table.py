"""The route table as a perfect-fit CART. Equivalence only -- no new capability.

WHAT THIS IS, STATED PLAINLY. The tape's route lookup is a total function

    (legacy, label, step) -> action

over 10 x 719 = 7,190 keys, every key distinct. This file fits a CART to that
function with `max_depth=None` and `min_samples_leaf=1`, so the tree drives every
node to purity and reproduces the lookup exactly. It is the same function in a
different representation: a binary search where the table did an index. It adds
nothing, and is not meant to -- the deliverable is the VERIFIED EQUIVALENCE.

WHY STEP ALONE IS NOT ENOUGH, since that was the original plan. `_kawa_actions`
(kawa source 127-144) picks among TEN tables, not one: five route labels x
current/legacy. Neither selector is constant within an episode --
`_kawa_route_label` reads `town.unlocked_shops`, which grows as the town unlocks
shops, so the label can switch mid-game; `_kawa_use_legacy_layout` latches a
decision between steps 24 and 71 by reading the OPPONENT's board. A tree keyed on
step alone therefore cannot be a faithful copy, and would fail verification
rather than pass it. Both selectors stay in kawa's hands (see
`Pipeline.use_table_tree`) so their state evolves identically; only the array
indexing is replaced.

LEAVES ARE CODEBOOK INDICES. Actions repeat heavily across steps and tables, so
each distinct action is stored once and leaves hold its index. That is a
compression of the leaf values, not of the function: lookup still returns the
action belonging to the key. The caller copies before mutating (kawa's
`_copy_action` deep-copies), so a shared leaf object cannot be aliased.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _HERE]
sys.path.insert(0, ROOT)

TABLES = os.path.join(ROOT, "logs", "tape", "tables.json")
OUT = os.path.join(ROOT, "logs", "tape", "route_tree.json")

# Ordinal codes for the label feature. CART splits numerically, so the order
# only decides which grouping a split can express, never which function is fit --
# purity is reached regardless.
LABELS = ("10c4s_3q", "8c6s_3q", "6c8s_3q",
          "6c12s_4q_first_yarn", "6c12s_4q_second_yarn")
LABEL_CODE = {name: i for i, name in enumerate(LABELS)}
SUFFIX = {"10c4s_3q": "10C4S_3Q", "8c6s_3q": "8C6S_3Q", "6c8s_3q": "6C8S_3Q",
          "6c12s_4q_first_yarn": "6C12S_4Q_FIRST_YARN",
          "6c12s_4q_second_yarn": "6C12S_4Q_SECOND_YARN"}
FEATURES = ("legacy", "label", "step")


def _canon(action):
    """Canonical text for an action, used only to detect duplicates."""
    return json.dumps({
        "farmer": list((action or {}).get("farmer") or ["PASS"]),
        "hands": [list(h or ["PASS"]) for h in ((action or {}).get("hands") or [])],
        "market": [list(m) for m in ((action or {}).get("market") or [])],
    }, sort_keys=True, separators=(",", ":"))


def rows_from_tables(tables):
    """(x, y) training rows, one per (legacy, label, step) key.

    x is [legacy, label_code, step]; y is a codebook index. Returns the codebook
    too, so a leaf can be turned back into an action.
    """
    codebook, index = [], {}
    X, y = [], []
    for legacy in (0, 1):
        prefix = "_LEGACY_ACTIONS_" if legacy else "_ACTIONS_"
        for label in LABELS:
            key = prefix + SUFFIX[label]
            table = tables.get(key)
            if table is None:
                raise KeyError(f"{key} missing from tables.json")
            for step, action in enumerate(table):
                text = _canon(action)
                slot = index.get(text)
                if slot is None:
                    slot = index[text] = len(codebook)
                    codebook.append(json.loads(text))
                X.append([legacy, LABEL_CODE[label], step])
                y.append(slot)
    return X, y, codebook


# --------------------------------------------------------------------- CART

def _gini_cost(counts_sq, n):
    """Weighted Gini of one side: n * (1 - sum p^2) = n - sum(c^2)/n."""
    return 0.0 if n == 0 else n - counts_sq / n


TIE = 1e-9


def _best_split(X, y, rows):
    """Lowest-Gini `feature <= threshold` split, or None if the node is pure.

    Gini is swept incrementally: moving one row from right to left changes a
    single class count, and `sum(c^2)` updates in O(1) as
    (c+1)^2 - c^2 = 2c + 1. So each feature costs one sort plus one linear pass.

    TIES ARE BROKEN TOWARD THE MEDIAN, and that is load-bearing rather than
    cosmetic. Over a stretch of steps whose actions are all distinct, every
    split scores the same Gini -- each side is entirely singleton classes, so
    the cost is n - 2 wherever the cut falls. First-wins tie-breaking then peels
    one row at a time and the "tree" degenerates into a 719-deep linked list:
    same function, but O(n) lookups and a recursion limit to worry about.
    Preferring the most balanced cut among equals gives the log2(n) depth this
    representation is supposed to have, and changes nothing about the fit.
    """
    first = y[rows[0]]
    if all(y[r] == first for r in rows):
        return None

    n = len(rows)
    half = n / 2.0
    best = None            # (cost, imbalance, feat, thr)
    for feat in range(len(FEATURES)):
        order = sorted(rows, key=lambda r: X[r][feat])
        # everything starts on the right
        right = {}
        for r in order:
            right[y[r]] = right.get(y[r], 0) + 1
        right_sq = sum(c * c for c in right.values())
        left, left_sq, n_left = {}, 0, 0

        for i in range(n - 1):
            r = order[i]
            cls = y[r]
            c = left.get(cls, 0)
            left_sq += 2 * c + 1
            left[cls] = c + 1
            n_left += 1
            c = right[cls]
            right_sq -= 2 * c - 1
            right[cls] = c - 1

            v, nxt = X[r][feat], X[order[i + 1]][feat]
            if v == nxt:                     # cannot split between equal values
                continue
            cost = _gini_cost(left_sq, n_left) + _gini_cost(right_sq, n - n_left)
            imbalance = abs(n_left - half)
            if (best is None or cost < best[0] - TIE
                    or (cost < best[0] + TIE and imbalance < best[1])):
                best = (cost, imbalance, feat, v)
    return None if best is None else (best[2], best[3])


def grow(X, y, rows=None, depth=0):
    """Fit until pure. max_depth=None, min_samples_leaf=1, exactly as specified."""
    rows = list(range(len(y))) if rows is None else rows
    split = _best_split(X, y, rows)
    if split is None:
        return {"leaf": y[rows[0]], "n": len(rows), "depth": depth}
    feat, thr = split
    left = [r for r in rows if X[r][feat] <= thr]
    right = [r for r in rows if X[r][feat] > thr]
    if not left or not right:                # unsplittable duplicate keys
        return {"leaf": y[rows[0]], "n": len(rows), "depth": depth}
    return {"feat": feat, "thr": thr, "n": len(rows),
            "left": grow(X, y, left, depth + 1),
            "right": grow(X, y, right, depth + 1)}


def _walk(node, x):
    while "leaf" not in node:
        node = node["left"] if x[node["feat"]] <= node["thr"] else node["right"]
    return node["leaf"]


def stats(node):
    """(nodes, leaves, max depth) -- the shape claim, measured not asserted."""
    nodes = leaves = 0
    deepest = 0
    stack = [(node, 0)]
    while stack:
        nd, d = stack.pop()
        nodes += 1
        deepest = max(deepest, d)
        if "leaf" in nd:
            leaves += 1
        else:
            stack.append((nd["left"], d + 1))
            stack.append((nd["right"], d + 1))
    return nodes, leaves, deepest


# ------------------------------------------------------------------ runtime

class TreeTable:
    """Runtime lookup. Returns the SHARED action -- copy before mutating.

    `n_steps` carries the table length so the caller can reproduce kawa's clamp
    (`min(max(0, step), len(actions) - 1)`) without re-entering `_kawa_actions`,
    whose legacy selector has a side effect and must run exactly once a turn.
    """

    def __init__(self, tree, codebook, n_steps):
        self.tree = tree
        self.codebook = codebook
        self.n_steps = n_steps

    def lookup(self, legacy, label, step):
        step = min(max(0, int(step)), self.n_steps - 1)
        return self.codebook[_walk(self.tree,
                                   (1 if legacy else 0, LABEL_CODE[label], step))]

    def save(self, path=OUT):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump({"features": list(FEATURES), "labels": list(LABELS),
                       "n_steps": self.n_steps,
                       "tree": self.tree, "codebook": self.codebook}, f,
                      separators=(",", ":"))
        return path


def load(path=OUT):
    d = json.load(open(path))
    return TreeTable(d["tree"], d["codebook"], d["n_steps"])


def build(tables_path=TABLES):
    tables = json.load(open(tables_path))
    X, y, codebook = rows_from_tables(tables)
    lengths = {len(v) for k, v in tables.items()
               if k.startswith("_ACTIONS_") or k.startswith("_LEGACY_ACTIONS_")}
    if len(lengths) != 1:
        raise ValueError(f"tables differ in length: {sorted(lengths)}")
    return TreeTable(grow(X, y), codebook, lengths.pop()), X, y


def selftest(tt, X, y):
    """Every training key must come back exactly. This is the equivalence claim
    at the table level; play-level equivalence is `pipeline.verify`."""
    bad = 0
    for x, target in zip(X, y):
        if _walk(tt.tree, x) != target:
            bad += 1
    return len(X) - bad, len(X)


if __name__ == "__main__":
    tt, X, y = build()
    ok, total = selftest(tt, X, y)
    nodes, leaves, depth = stats(tt.tree)
    print(f"rows (keys)        {total:,}")
    print(f"distinct actions   {len(tt.codebook):,}  (codebook)")
    print(f"nodes / leaves     {nodes:,} / {leaves:,}")
    print(f"max depth          {depth}")
    print(f"exact lookups      {ok:,}/{total:,} = {100.0 * ok / total:.2f}%")
    path = tt.save()
    print(f"wrote {path}  ({os.path.getsize(path):,} bytes)")
