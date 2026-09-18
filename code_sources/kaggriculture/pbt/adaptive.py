"""v2 protocol: runtime opponent identification -> per-family counter params.

Implements the adaptive agent the protocol describes, using the measured
counter table instead of K-Means. Clustering was dropped for a reason worth
recording: with only six opponents whose farms are trivially separable at day 4
(cow/sheep counts differ by construction), nearest-centroid on the raw feature
vector is both exact and cheaper than K-Means, and the counter table it indexes
turned out to have only one discriminating row anyway.
"""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ADAPTIVE_SRC = '''

# ============ adaptive counter-parameter overlay (pbt/adaptive.py) ============
_AD_STEP = 96                     # day 4: builds committed, families separable
_AD_CENTROIDS = __CENTROIDS__
_AD_COUNTER = __COUNTER__
_AD_DEFAULT = __DEFAULT__
_AD_KEYS = __KEYS__
_AD_STATE = {"family": None, "applied": False}
_AD_BASE_AGENT = agent


def _ad_features(farm):
    c = {k: 0 for k in _AD_KEYS}
    c["hands"] = len(farm.get("hands") or [])
    c["quadrants"] = len(farm.get("unlocked_quadrants") or [])
    c["money"] = float(farm.get("money", 0) or 0)
    for row in farm.get("tiles") or []:
        for t in row:
            if not isinstance(t, dict):
                continue
            for f in ("crop", "animal", "kind"):
                v = str(t.get(f, "")).upper()
                if v in c:
                    c[v] += 1
                    break
    return c


def _ad_classify(feat):
    best, bd = None, None
    for name, cen in _AD_CENTROIDS.items():
        d = 0.0
        for k in _AD_KEYS:
            # money spans thousands while tile counts span tens; normalise or it
            # is the only feature that matters.
            scale = 1000.0 if k == "money" else 1.0
            d += ((feat.get(k, 0) - cen.get(k, 0)) / scale) ** 2
        if bd is None or d < bd:
            best, bd = name, d
    return best


def agent(obs):
    try:
        o = obs if isinstance(obs, dict) else dict(obs)
        step = int(o.get("step", 0) or 0)
        if not step:
            step = int(o.get("day", 0) or 0) * 24 + int(o.get("hour", 0) or 0)
        if step == 0:
            _AD_STATE["family"], _AD_STATE["applied"] = None, False
            for k, v in _AD_DEFAULT.items():
                globals()[k] = v
        if step == _AD_STEP and not _AD_STATE["applied"]:
            seat = int(o.get("player", 0) or 0)
            farms = o.get("farms") or []
            if len(farms) > 1:
                fam = _ad_classify(_ad_features(farms[1 - seat]))
                _AD_STATE["family"] = fam
                _AD_STATE["applied"] = True
                for k, v in _AD_COUNTER.get(fam, _AD_DEFAULT).items():
                    globals()[k] = v
    except Exception:
        pass
    return _AD_BASE_AGENT(obs)
'''


def build(out_path, counter_table, centroids, keys, default):
    from route.bake import bake
    bake(default, out=out_path, note="adaptive base")
    src = (ADAPTIVE_SRC
           .replace("__CENTROIDS__", repr(centroids))
           .replace("__COUNTER__", repr(counter_table))
           .replace("__DEFAULT__", repr(default))
           .replace("__KEYS__", repr(list(keys))))
    with open(out_path, "a") as f:
        f.write(src)
        # Every appended layer must re-close the file with a NEW final callable.
        # bake() already wrote _submission_entry, but rebinding `agent` above does
        # not move it in the namespace, so without this the last *new* callable is
        # _ad_classify and Kaggle would run that instead (HANDOFF section 21).
        f.write("\n\ndef _adaptive_entry(obs):\n    return agent(obs)\n")
    return out_path
