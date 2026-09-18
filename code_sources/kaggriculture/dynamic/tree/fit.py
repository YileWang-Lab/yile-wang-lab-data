"""Fit shallow, readable decision trees to the top ladder's decisions.

WHY A HAND-WRITTEN CART. No dependency, and every split is an axis-aligned test
on a NAMED feature, so the fitted model prints as the rules it is:

    if cash <= 0.031:
        if day <= 0.133:  -> WHEAT
        else:             -> MELON

Depth is capped at 3-4 on purpose. With 1,479 rows a deeper tree would fit the
eleven experts' disagreements rather than what they agree on, and the point is a
policy that transfers, not one that memorises.

HELD OUT BY TEAM, NOT BY ROW. Rows from one game share its board, its shop draw
and its opponent, and rows from one TEAM share a strategy -- so a random row
split reports a fit that does not exist. Holding out whole teams asks the
question that matters: do rules learned from ten players predict the eleventh?

AND LIFT, NOT ACCURACY. Section 32's distillation reached 89-100% held-out
agreement and played -46,972, because the labels are dominated by a majority
class: predicting "no land today" is right 93% of the time. Every number here is
reported against the majority-class baseline, and the acceptance test is still
play, never agreement.
"""
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _HERE]
sys.path.insert(0, ROOT)

from dynamic.rl import policy_api as PA          # noqa: E402

ROWS = os.path.join(ROOT, "logs", "tree", "rows.json")
OUT = os.path.join(ROOT, "logs", "tree", "trees.json")


class Node:
    __slots__ = ("feat", "thr", "left", "right", "pred", "n", "dist")

    def __init__(self):
        self.feat = self.thr = self.left = self.right = None
        self.pred = None
        self.n = 0
        self.dist = None


def _gini(counts, total):
    if total <= 0:
        return 0.0
    return 1.0 - sum((c / total) ** 2 for c in counts.values())


def _counts(ys):
    d = {}
    for y in ys:
        d[y] = d.get(y, 0) + 1
    return d


def grow(X, ys, feats, depth, min_leaf=25, n_thr=12):
    node = Node()
    node.n = len(ys)
    c = _counts(ys)
    node.dist = c
    node.pred = max(c, key=c.get) if c else 0
    if depth <= 0 or len(ys) < 2 * min_leaf or len(c) < 2:
        return node
    base = _gini(c, len(ys))
    best = (0.0, None, None)
    for f in feats:
        col = [x[f] for x in X]
        lo, hi = min(col), max(col)
        if hi - lo < 1e-9:
            continue
        for k in range(1, n_thr):
            thr = lo + (hi - lo) * k / n_thr
            li = [i for i, v in enumerate(col) if v <= thr]
            if len(li) < min_leaf or len(ys) - len(li) < min_leaf:
                continue
            ls = set(li)
            yl = [ys[i] for i in li]
            yr = [ys[i] for i in range(len(ys)) if i not in ls]
            g = (len(yl) * _gini(_counts(yl), len(yl))
                 + len(yr) * _gini(_counts(yr), len(yr))) / len(ys)
            if base - g > best[0]:
                best = (base - g, f, thr)
    if best[1] is None:
        return node
    _, f, thr = best
    node.feat, node.thr = f, thr
    li = [i for i, x in enumerate(X) if x[f] <= thr]
    ls = set(li)
    node.left = grow([X[i] for i in li], [ys[i] for i in li], feats,
                     depth - 1, min_leaf, n_thr)
    node.right = grow([X[i] for i in range(len(X)) if i not in ls],
                      [ys[i] for i in range(len(ys)) if i not in ls],
                      feats, depth - 1, min_leaf, n_thr)
    return node


def predict(node, x):
    while node.feat is not None:
        node = node.left if x[node.feat] <= node.thr else node.right
        if node is None:
            break
    return node.pred


def render(node, names, labels, indent="    ", depth=0):
    pad = indent * (depth + 1)
    if node.feat is None:
        tot = sum(node.dist.values()) or 1
        lab = labels(node.pred)
        pct = 100.0 * node.dist.get(node.pred, 0) / tot
        return f"{pad}-> {lab}   (n={node.n}, {pct:.0f}% pure)\n"
    out = f"{pad}if {names[node.feat]} <= {node.thr:.3f}:\n"
    out += render(node.left, names, labels, indent, depth + 1)
    out += f"{pad}else:\n"
    out += render(node.right, names, labels, indent, depth + 1)
    return out


def to_dict(node):
    if node.feat is None:
        return {"pred": node.pred, "n": node.n}
    return {"feat": node.feat, "thr": node.thr, "n": node.n,
            "left": to_dict(node.left), "right": to_dict(node.right)}


def evaluate(node, X, ys):
    if not ys:
        return 0.0, 0.0
    acc = sum(1 for x, y in zip(X, ys) if predict(node, x) == y) / len(ys)
    c = _counts(ys)
    base = max(c.values()) / len(ys)
    return acc, base


def main():
    depth = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    blob = json.load(open(ROWS))
    rows, names = blob["rows"], blob["names"]
    teams = sorted({r["team"] for r in rows})
    print(f"{len(rows):,} rows, {len(names)} named features, {len(teams)} teams, "
          f"depth {depth}\n")

    heads = [("crop", lambda i: PA.CROPS[i] if 0 <= i < len(PA.CROPS) else "none",
              lambda r: r["crop"]),
             ("hire", lambda i: f"{i} hires", lambda r: r["hire"]),
             ("land", lambda i: ["no", "BUY LAND"][i], lambda r: r["land"]),
             ("animal", lambda i: str(PA.ANIMAL_CHOICES[i]), lambda r: r["animal"])]

    trees, report = {}, {}
    for name, lab, get in heads:
        # leave-one-team-out: rules from ten players, tested on the eleventh
        accs, bases = [], []
        for held in teams:
            tr = [r for r in rows if r["team"] != held]
            te = [r for r in rows if r["team"] == held]
            if len(te) < 20:
                continue
            node = grow([r["x"] for r in tr], [get(r) for r in tr],
                        range(len(names)), depth)
            a, b = evaluate(node, [r["x"] for r in te], [get(r) for r in te])
            accs.append(a)
            bases.append(b)
        full = grow([r["x"] for r in rows], [get(r) for r in rows],
                    range(len(names)), depth)
        trees[name] = to_dict(full)
        acc = sum(accs) / len(accs) if accs else 0.0
        base = sum(bases) / len(bases) if bases else 0.0
        report[name] = {"acc": acc, "base": base, "lift": acc - base}
        print(f"  {name:<8} leave-one-team-out {100 * acc:>5.1f}%   "
              f"majority {100 * base:>5.1f}%   lift {100 * (acc - base):>+5.1f}")

    print()
    for name, lab, get in heads:
        full = grow([r["x"] for r in rows], [get(r) for r in rows],
                    range(len(names)), depth)
        print(f"  --- {name} ---")
        print(render(full, names, lab), end="")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({"trees": trees, "names": names, "report": report},
              open(OUT, "w"), indent=1)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
