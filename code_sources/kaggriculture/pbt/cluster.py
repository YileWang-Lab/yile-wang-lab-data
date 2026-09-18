"""K-Means (K=5) over accumulated opponent feature vectors.

Written out rather than pulled from sklearn: the venv does not carry it, the
data is a few hundred six-dim points, and Lloyd's algorithm with k-means++ seeding
is twenty lines. Features are z-scored first -- cash_burn_rate_day5 spans
hundreds while premium_crop_ratio spans 0..1, and without scaling the burn rate
is the only dimension the distance sees.
"""
import json, math, os, random

from pbt.features import KEYS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CENTERS = os.path.join(ROOT, "models", "cluster_centers.json")


def _stats(rows):
    mu = {k: sum(r[k] for r in rows) / len(rows) for k in KEYS}
    sd = {k: (sum((r[k] - mu[k]) ** 2 for r in rows) / len(rows)) ** 0.5 or 1.0 for k in KEYS}
    return mu, sd


def _z(r, mu, sd):
    return [(r[k] - mu[k]) / sd[k] for k in KEYS]


def _d2(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b))


def kmeans(rows, k=5, iters=50, seed=0):
    if len(rows) < k:
        k = max(1, len(rows))
    mu, sd = _stats(rows)
    pts = [_z(r, mu, sd) for r in rows]
    rng = random.Random(seed)
    centers = [pts[rng.randrange(len(pts))]]
    while len(centers) < k:                       # k-means++ seeding
        d = [min(_d2(p, c) for c in centers) for p in pts]
        tot = sum(d) or 1.0
        pick, acc = rng.random() * tot, 0.0
        for p, w in zip(pts, d):
            acc += w
            if acc >= pick:
                centers.append(p); break
        else:
            centers.append(pts[rng.randrange(len(pts))])
    for _ in range(iters):
        groups = [[] for _ in centers]
        for p in pts:
            groups[min(range(len(centers)), key=lambda i: _d2(p, centers[i]))].append(p)
        new = []
        for i, g in enumerate(groups):
            new.append([sum(c) / len(g) for c in zip(*g)] if g else centers[i])
        if all(_d2(a, b) < 1e-9 for a, b in zip(new, centers)):
            centers = new; break
        centers = new
    labels = [min(range(len(centers)), key=lambda i: _d2(p, centers[i])) for p in pts]
    return centers, labels, mu, sd


def fit_and_save(rows, k=5):
    if not rows:
        return None
    centers, labels, mu, sd = kmeans(rows, k=k)
    sizes = {i: labels.count(i) for i in range(len(centers))}
    payload = {"centers": centers, "mu": mu, "sd": sd, "keys": list(KEYS),
               "sizes": sizes, "n": len(rows)}
    os.makedirs(os.path.dirname(CENTERS), exist_ok=True)
    json.dump(payload, open(CENTERS, "w"), indent=1)
    return payload


def assign(vec, payload):
    if not payload:
        return None
    z = [(vec[k] - payload["mu"][k]) / (payload["sd"][k] or 1.0) for k in payload["keys"]]
    return min(range(len(payload["centers"])),
               key=lambda i: _d2(z, payload["centers"][i]))
