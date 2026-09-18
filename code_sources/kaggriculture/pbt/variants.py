"""Mutation operators, mapped onto what is actually mutable in this agent.

The eight axes in the protocol assume a hand-written farming policy. This
lineage replays a precomputed 720-step tape, so planting dates and irrigation
budgets are compiled into the tape and cannot be perturbed. The axes are mapped
onto the surfaces that do exist and do move the score:

  v1 crop schedule  -> which tape gets selected (portfolio: 6c12s / 10c4s / ...)
  v2 trade limits   -> preempt price ratio and future-quantity gate
  v3 allocation     -> preempt batch size and fraction
  v4 mixed          -> tape + trade together
  v5 module swap    -> clone-distance gate (preempt against anyone vs clones)
  v6 extreme        -> one tape pinned for the whole season
  v7 learning rate  -> _DEMAND_ALPHA (demand smoothing step)
  v8 noise          -> small gaussian on every constant
"""
import random

ROUTES = ["10c4s_3q", "8c6s_3q", "6c8s_3q",
          "6c12s_4q_first_yarn", "6c12s_4q_second_yarn"]

BOUNDS = {
    "_PREEMPT_FRACTION":            (0.0, 4.0, "float"),
    "_PREEMPT_MAX_BATCH":           (1, 60, "int"),
    "_PREEMPT_MAX_CLONE_DISTANCE":  (0, 40, "int"),
    "_PREEMPT_MIN_PRICE_RATIO":     (0.0, 2.0, "float"),
    "_PREEMPT_MIN_FUTURE_QUANTITY": (0, 20, "int"),
    "_PREEMPT_START":               (0, 400, "int"),
    "_PREEMPT_STOP":                (400, 719, "int"),
    "_WEED_REPLAY_STEPS":           (1, 24, "int"),
    "_DEMAND_ALPHA":                (0.0, 1.0, "float"),
}


def _clip(key, v):
    lo, hi, kind = BOUNDS[key]
    v = max(lo, min(hi, v))
    return int(round(v)) if kind == "int" else round(float(v), 4)


def _jitter(g, key, rng, scale):
    lo, hi, _ = BOUNDS[key]
    g[key] = _clip(key, g[key] + rng.gauss(0, (hi - lo) * scale))


def make_variants(base_genome, rng):
    """Eight variants, each one change, with a human-readable note."""
    out = []

    def V(note, **kw):
        g = dict(base_genome); g.update(kw); out.append((note, g))

    g1 = dict(base_genome)
    g1["FORCE_ROUTE"] = rng.choice(ROUTES)
    out.append((f"v1 crop schedule: tape pinned to {g1['FORCE_ROUTE']}", g1))

    g2 = dict(base_genome)
    _jitter(g2, "_PREEMPT_MIN_PRICE_RATIO", rng, 0.12)
    _jitter(g2, "_PREEMPT_MIN_FUTURE_QUANTITY", rng, 0.12)
    out.append(("v2 trade limits: price-ratio and future-qty gates jittered", g2))

    g3 = dict(base_genome)
    _jitter(g3, "_PREEMPT_MAX_BATCH", rng, 0.20)
    _jitter(g3, "_PREEMPT_FRACTION", rng, 0.20)
    out.append(("v3 allocation: preempt batch and fraction jittered", g3))

    g4 = dict(base_genome)
    g4["FORCE_ROUTE"] = rng.choice(ROUTES)
    _jitter(g4, "_PREEMPT_MAX_BATCH", rng, 0.15)
    out.append((f"v4 mixed: tape {g4['FORCE_ROUTE']} + batch change", g4))

    V("v5 module swap: preempt against any opponent, not only clones",
      _PREEMPT_MAX_CLONE_DISTANCE=40)

    g6 = dict(base_genome)
    g6["FORCE_ROUTE"] = rng.choice(ROUTES)
    g6["_PREEMPT_MAX_BATCH"] = rng.choice([1, 60])
    out.append((f"v6 extreme: tape {g6['FORCE_ROUTE']} pinned, "
                f"batch={g6['_PREEMPT_MAX_BATCH']}", g6))

    g7 = dict(base_genome)
    _jitter(g7, "_DEMAND_ALPHA", rng, 0.25)
    out.append((f"v7 learning rate: _DEMAND_ALPHA -> {g7['_DEMAND_ALPHA']}", g7))

    g8 = dict(base_genome)
    for k in BOUNDS:
        _jitter(g8, k, rng, 0.05)
    out.append(("v8 noise: small gaussian on every constant", g8))

    return out[:8]
