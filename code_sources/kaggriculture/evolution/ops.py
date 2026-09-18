"""Mutation operators and the CRN evaluator for the evolution run.

Budget is deliberately NOT spent on market-layer parameter perturbation. Rounds
1-6 of planner/intervene_sweep.py already swept dump fraction, price gate, lead,
the dump item set, the base tape's _PREEMPT_* constants, seat-conditional play
and sell suppression over ~68,000 games, and planner/ladder_sweep.py then scored
the survivors against the 80 real ladder opponents we actually faced: the live
configuration is already optimal there, with the best alternative at +23. A
+/-10-30% jitter would rediscover the same optimum.

The budget goes to two places instead:

  TAPE_MAP combinations (40%). kawa picks among five tapes with a five-bucket
  rule. Correcting bucket 0 alone measured +1,841 (t=13.7). But that search
  tested each bucket INDEPENDENTLY, and the buckets are not independent: the
  label is recomputed every turn from the shops unlocked so far, so a game
  starts in bucket 4 and moves as the town draws, and the agent can run two
  tapes in one episode. Joint assignments have never been searched.

  Tape window splices (40%). Genuinely untested. HANDOFF section 4 established
  that EDITING a tape is fatal (a day-0 quantity change costs -107k) because
  every downstream PLACE/PLANT assumes exactly the shed the tape bought. But
  bucket 0 proved that replacing a tape WHOLESALE works. A mid-season window
  swap sits between those two results, and nothing on file predicts which way
  it goes. The prior is bad -- section 4 says continuations are not
  interchangeable -- so most of these should be discarded; that is the point of
  measuring rather than assuming.

Screening uses common random numbers: every variant plays the identical
(opponent, seed, seat) list, and a candidate is scored on the PAIRED DIFFERENCE
against its parent. Raw paired margin has sd ~20,000 per game, so the 40-game
screen in the original plan could not resolve its own +200 threshold (SE ~4,500
without CRN, ~224 with). At ~100 paired games the CRN difference has SE ~100,
which can.
"""
import importlib.util
import json
import multiprocessing
import os
import random
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from planner.simulate import Simulator  # noqa: E402
from route.bake import bake  # noqa: E402

AGENT_DIR = os.path.join(ROOT, "evolution", "agents")
LOG_DIR = os.path.join(ROOT, "logs", "evolution")
os.makedirs(AGENT_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

TAPES = ["6c12s_4q_first_yarn", "6c12s_4q_second_yarn", "6c8s_3q",
         "10c4s_3q", "8c6s_3q"]
DEFAULT_MAP = list(TAPES)

# The five tapes are only THREE distinct behaviours. Measured pairwise over all
# 719 steps:
#   10c4s vs 6c8s   1.4% of steps differ
#   10c4s vs 8c6s   0.7%
#   6c8s  vs 8c6s   0.7%
#   first_yarn vs second_yarn        76.5%
#   3q family vs either 4q tape      71-79%
# and day 0 is byte-identical across all five.
#
# So 10c4s_3q / 6c8s_3q / 8c6s_3q are one tape with 5-10 tweaked steps. This
# retro-explains both earlier tape-map results: correcting bucket 0
# (first_yarn -> second_yarn) was worth +1,841 because it swaps between two
# genuinely different tapes, while the bucket 1 and 2 proposals were flat to
# harmful because they mostly shuffle within the 3q family, which is nearly a
# no-op.
#
# Two consequences for the operators below:
#   - the real TAPE_MAP space is 3^5 = 243, not 5^5 = 3,125
#   - a splice whose source and destination share a family changes almost
#     nothing, so splices are constrained to cross family (the first smoke test
#     spliced 10c4s into 8c6s and altered exactly 0 steps)
FAMILY = {"6c12s_4q_first_yarn": "F", "6c12s_4q_second_yarn": "S",
          "6c8s_3q": "Q", "10c4s_3q": "Q", "8c6s_3q": "Q"}
REPRESENTATIVE = ["6c12s_4q_first_yarn", "6c12s_4q_second_yarn", "8c6s_3q"]

SHIPPED = {"_PREEMPT_MIN_FUTURE_QUANTITY": 0, "_PREEMPT_MAX_BATCH": 30,
           "INTERVENE": 1, "IV_DUMP_FRAC": 0.8, "IV_LEAD": 3, "IV_FERT": 1}
LIVE = {**SHIPPED, "IV_STRUCT": 1, "IV_DUMP_FRAC": 0.7, "IV_MIN_PRICE": 0.20}
B0_MAP = ["6c12s_4q_second_yarn"] + DEFAULT_MAP[1:]
B0 = {**LIVE, "TAPE_MAP": list(B0_MAP)}

POOL = [
    "kaggriculture-multi-route-farming-agent",
    "v111-8c4s-economic-core-premium-lead",
    "kaggriculture-frontier-the-soil-remembers-rain",
    "kaggriculture-3000-socre",
    "kaggriculture-breaking-the-tie-2883-score",
    "kaggriculture-rank-your-agent",
    "15-16-strict-future-v25-meta-reset",
    "strong-barnyard-economist",
    "kaggriculture-pure-architecture-2600-elo-v3",
]

# Market-layer knobs are frozen (see module docstring). These are the planner
# and execution knobs, which are orthogonal to the tape and were never swept
# alongside it.
JITTER_KEYS = {
    "IV_LEAD": ("int", 1, 6),
    "_PREEMPT_MAX_BATCH": ("int", 8, 60),
    "_PREEMPT_MAX_CLONE_DISTANCE": ("int", 2, 60),
    "_PREEMPT_STOP": ("int", 600, 719),
}

_n = [0]


def _load(path):
    _n[0] += 1
    s = importlib.util.spec_from_file_location(f"ev_{os.getpid()}_{_n[0]}", path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return getattr(m, "_submission_entry", None) or m.agent


# ------------------------------------------------------------------ mutation

def mutate_tape_map(genome, rng):
    """Move one or two buckets, drawing from the three DISTINCT tapes rather
    than all five -- swapping 10c4s for 8c6s is a 5-step change and wastes the
    evaluation slot."""
    g = json.loads(json.dumps(genome))
    m = list(g.get("TAPE_MAP") or DEFAULT_MAP)
    n = rng.choice([1, 1, 1, 2])
    for _ in range(n):
        b = rng.randrange(5)
        choices = [t for t in REPRESENTATIVE if FAMILY[t] != FAMILY[m[b]]]
        m[b] = rng.choice(choices) if choices else rng.choice(REPRESENTATIVE)
    g["TAPE_MAP"] = m
    return g, "map[" + "".join(FAMILY[t] for t in m) + "]"


def mutate_splice(genome, rng):
    """Replace a day-window of one tape with another tape's same window.

    Source and destination are forced into different families; a same-family
    splice alters ~0 steps. Windows start at day 1 or later because day 0 is
    identical across all five tapes, so splicing it is by construction a no-op.
    """
    g = json.loads(json.dumps(genome))
    dst = rng.choice(REPRESENTATIVE)
    src = rng.choice([t for t in REPRESENTATIVE if FAMILY[t] != FAMILY[dst]])
    d0 = rng.randrange(1, 26)
    d1 = min(29, d0 + rng.choice([2, 3, 4, 5, 6]))
    g["TAPE_SPLICE"] = {"dst": dst, "src": src, "day0": d0, "day1": d1}
    return g, f"splice({FAMILY[dst]}<-{FAMILY[src]},d{d0}-{d1})"


def mutate_jitter(genome, rng):
    g = json.loads(json.dumps(genome))
    k = rng.choice(list(JITTER_KEYS))
    kind, lo, hi = JITTER_KEYS[k]
    cur = g.get(k, {"IV_LEAD": 3, "_PREEMPT_MAX_BATCH": 30,
                    "_PREEMPT_MAX_CLONE_DISTANCE": 6, "_PREEMPT_STOP": 680}[k])
    f = 1.0 + rng.uniform(-0.30, 0.30)
    v = int(round(cur * f))
    v = max(lo, min(hi, v))
    if v == cur:
        v = max(lo, min(hi, cur + rng.choice([-2, -1, 1, 2])))
    g[k] = v
    return g, f"{k}={v}"


OPERATORS = [(mutate_tape_map, 0.40), (mutate_splice, 0.40), (mutate_jitter, 0.20)]


def mutate(genome, rng):
    r = rng.random()
    acc = 0.0
    for fn, w in OPERATORS:
        acc += w
        if r <= acc:
            return fn(genome, rng)
    return OPERATORS[-1][0](genome, rng)


# ---------------------------------------------------------------- evaluation

def build(genome, name):
    path = os.path.join(AGENT_DIR, f"{name}.py")
    splice = genome.pop("TAPE_SPLICE", None)
    bake(genome, out=path, note=f"evolution {name}")
    if splice:
        genome["TAPE_SPLICE"] = splice
        _apply_splice(path, splice)
    return path


def _apply_splice(path, sp):
    """Append a layer that overwrites one tape's day-window with another's.

    Done as an appended layer rather than by rewriting the compressed tape
    constants, so the base file stays byte-identical to the audited original
    and a splice can never corrupt anything but itself.
    """
    src = f"""

# ============ tape window splice (evolution/ops.py) ============
_SP = {sp!r}
_SP_DONE = [False]


def _sp_install():
    if _SP_DONE[0]:
        return
    _SP_DONE[0] = True
    try:
        dst = globals().get("_ACTIONS_" + _SP["dst"].upper())
        src_t = globals().get("_ACTIONS_" + _SP["src"].upper())
        if not dst or not src_t:
            return
        lo, hi = _SP["day0"] * 24, min(len(dst), (_SP["day1"] + 1) * 24)
        for i in range(lo, hi):
            if i < len(src_t):
                dst[i] = src_t[i]
    except Exception:
        pass


_SP_BASE_AGENT = agent


def agent(obs):
    _sp_install()
    return _SP_BASE_AGENT(obs)
"""
    with open(path, "a") as f:
        f.write(src)


def _play(job):
    path, opp_name, seed, seat = job
    try:
        me = _load(path)
        op = _load(os.path.join(ROOT, "opponents", f"{opp_name}.py"))
        pair = [me, op] if seat == 0 else [op, me]
        sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
        m0, m1 = sim.run_episode(pair[0], pair[1])
        us, them = (m0, m1) if seat == 0 else (m1, m0)
        return (path, opp_name, seed, seat, us - them, None)
    except Exception:
        import traceback
        return (path, opp_name, seed, seat, 0.0, traceback.format_exc()[-200:])


def evaluate(paths, seeds, pool=None, workers=26):
    """Play every path over the identical (opponent, seed, seat) grid.

    Returns {path: {(opponent, seed): paired_margin}} -- paired over the two
    seat orders, so a mirror scores exactly 0 (HANDOFF rule 1)."""
    pool = pool or POOL
    jobs = [(p, o, s, seat) for p in paths for o in pool for s in seeds
            for seat in (0, 1)]
    with multiprocessing.get_context("forkserver").Pool(workers) as ex:
        res = ex.map(_play, jobs, chunksize=4)
    errs = [r[5] for r in res if r[5]]
    acc = {}
    for path, opp, seed, seat, m, err in res:
        if not err:
            acc.setdefault(path, {}).setdefault((opp, seed), []).append(m)
    out = {}
    for path, d in acc.items():
        out[path] = {k: sum(v) for k, v in d.items() if len(v) == 2}
    return out, errs


def head_to_head(job):
    """One game between two of OUR versions. Module-level so the pool can
    pickle it."""
    pa, pb, seed, seat = job
    try:
        A, Bx = _load(pa), _load(pb)
        pair = [A, Bx] if seat == 0 else [Bx, A]
        sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
        m0, m1 = sim.run_episode(pair[0], pair[1])
        us, them = (m0, m1) if seat == 0 else (m1, m0)
        return (pa, pb, seed, us - them, None)
    except Exception:
        import traceback
        return (pa, pb, seed, 0.0, traceback.format_exc()[-200:])


def compare(child, parent):
    """CRN paired difference of child vs parent on their shared keys."""
    keys = [k for k in child if k in parent]
    if not keys:
        return 0.0, 0.0, 0.0, 0
    diffs = [child[k] - parent[k] for k in keys]
    dm = statistics.mean(diffs)
    dse = (statistics.pstdev(diffs) / len(diffs) ** 0.5) if len(diffs) > 1 else 0.0
    wr = sum(1 for k in keys if child[k] > 0) / len(keys)
    return dm, dse, wr, len(keys)
