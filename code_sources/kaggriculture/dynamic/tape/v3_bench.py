"""Treeify the v3 submission, then prove the tree is the same agent, and play it.

Two questions, and they are not the same question:

  EQUIVALENCE  is `submission/v3_tree.py` the same function as
               `submission/v3_base.py`? This can only fail. The bar is exact
               identity of every final bank, seed by seed and seat by seat --
               not equal means, not equal win rates, both of which pass even
               when the agents diverge and the differences happen to cancel.

  PERFORMANCE  what does it actually score against the pool? Reported because
               it was asked for; it is NOT evidence about the tree. A perfect
               tree scores exactly what the array scored, so this section is a
               description of v3, not of the treeification.

HANDOFF rule 1. The mirror arms are same-tape matchups, so win rate is
meaningless there -- an agent against a byte-identical copy of itself wins seat
0 only 15% of the time. Mirrors are scored by PAIRED MARGIN: both seat orders
per seed, summed, which a true mirror scores at exactly 0. Only the POOL
section, where the opponent is a different agent, is scored by win rate.

HANDOFF rule 3. Every agent is loaded BY PATH and resolved with the
`get_last_callable` rule Kaggle uses -- the last callable in namespace
insertion order. That is the whole point of checking the tree file: appending
the block moves the picked entry to `_treeroute_entry`, and this harness runs
whatever Kaggle would run rather than what we hope it picks.

HANDOFF section 21. `base_vs_base` is the identity control. It must come back
at exactly +0 with 0 wins and 0 losses. If it does not, the harness is leaking
per-seat module state between games and NOTHING else in the run means anything
-- the v3 file keeps `_WEED_STATE`, `_SHIFT_STATE`, `_KAWA_LAYOUT_FALLBACK` and
the `_IV` market state at module level, keyed by seat, so a reused module
silently carries yesterday's episode into today's.

    python dynamic/tape/v3_bench.py                 # treeify + verify + play
    V3_SEEDS=12 V3_POOL_SEEDS=6 python dynamic/tape/v3_bench.py
    V3_SKIP_BUILD=1 python dynamic/tape/v3_bench.py # reuse an existing tree
"""
import importlib.util
import multiprocessing as mp
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _HERE]
sys.path.insert(0, ROOT)

BASE = os.path.join(ROOT, "submission", "v3_base.py")

# Which derived build is under test. Every one of these is a pure REPRESENTATION
# change over the same agent, so every one must come back EQUIVALENT:
#
#   tree           the CART blob            pbt/treeify.py   (superseded)
#   flat           addressable state array  pbt/flatify.py
#   expanded       all 12 blobs as literals pbt/expand.py
#   flat_expanded  both of the above
#
# The arm is labelled "tree" throughout the report whichever is selected: what
# the row asserts -- this build is the same function as the base -- does not
# depend on which representation produced it.
BUILDS = ("tree", "flat", "expanded", "flat_expanded")
LAYER = os.environ.get("V3_LAYER", "flat")
if LAYER not in BUILDS:
    raise SystemExit("V3_LAYER must be one of %s, not %r" % (", ".join(BUILDS), LAYER))
TREE = os.path.join(ROOT, "submission", "v3_%s.py" % LAYER)

# Physical cores. CLAUDE.md: never 52 -- the second thread of each core buys
# nothing here and halves the per-worker cache.
WORKERS = int(os.environ.get("V3_WORKERS", "26"))
SEEDS = int(os.environ.get("V3_SEEDS", "12"))
POOL_SEEDS = int(os.environ.get("V3_POOL_SEEDS", "6"))
SEED0 = int(os.environ.get("V3_SEED0", "9000"))

POOL = ["v111-8c4s-economic-core-premium-lead",
        "kaggriculture-3000-socre",
        "kaggriculture-rank-your-agent",
        "kaggriculture-ttv1",
        "strong-barnyard-economist",
        "kaggriculture-multi-route-farming-agent"]

_loads = [0]


def _load(path):
    """Load a file agent and resolve it the way Kaggle does.

    `get_last_callable` walks the module namespace in INSERTION order, so a
    rebound name keeps its original position and the last *newly defined*
    callable wins. Reproducing that here is the point: the tree file appends a
    block, which moves the picked entry, and the harness must run whatever
    Kaggle would run rather than a name we assume is still there.

    Loaded under a unique module name every call, never imported. The v3 file
    holds per-seat state in module globals; sharing a module between episodes
    would carry state across them.
    """
    _loads[0] += 1
    spec = importlib.util.spec_from_file_location(
        "a_%d_%d" % (os.getpid(), _loads[0]), path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    picked = None
    for name, value in vars(m).items():
        if callable(value) and not name.startswith("__"):
            picked = (name, value)
    if picked is None:
        raise RuntimeError("no callable in %s" % path)
    return picked[1]


def _opp_path(name):
    return os.path.join(ROOT, "opponents", name + ".py")


def preflight():
    """Load everything once, in the parent, before a single game is scheduled.

    An opponent that raises at import (several in this directory do -- they
    carry a top-level `from IPython.display import ...`) otherwise produces one
    dead job per (seed, seat) and the run reports a wall of tracebacks that look
    like divergences.
    """
    for path in (BASE, TREE):
        if not os.path.exists(path):
            raise SystemExit("missing: %s" % path)
        _load(path)
    ok, broken = [], []
    for name in POOL:
        try:
            _load(_opp_path(name))
            ok.append(name)
        except Exception as exc:
            broken.append("%s: %s: %s" % (name, type(exc).__name__, exc))
    if broken:
        print("  dropped (will not load in this venv):")
        for b in broken:
            print("    " + b)
    if not ok:
        raise SystemExit("no usable opponents")
    return ok


def entry_names():
    """What Kaggle would pick for each file, for the record."""
    out = []
    for path in (BASE, TREE):
        spec = importlib.util.spec_from_file_location("probe", path)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        picked = None
        for name, value in vars(m).items():
            if callable(value) and not name.startswith("__"):
                picked = name
        out.append((os.path.basename(path), picked))
    return out


# ------------------------------------------------------------------- workers

def _play(a_path, b_path, seed):
    """One episode, a_path in seat 0. Returns both final banks."""
    from planner.simulate import Simulator
    a, b = _load(a_path), _load(b_path)
    sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
    return sim.run_episode(a, b)


def _mirror_job(job):
    """arm, seed, seat -> our margin. Both seat orders are summed by `report`."""
    arm, left, right, seed, seat = job
    try:
        me, other = (left, right) if seat == 0 else (right, left)
        m0, m1 = _play(me, other, seed)
        # Un-swap, so a margin is always ours-minus-theirs whichever seat
        # `left` sat in and the two orders of a seed can be summed.
        us, them = (m0, m1) if seat == 0 else (m1, m0)
        return (arm, seed, seat, us - them, None)
    except Exception:
        import traceback
        return (arm, seed, seat, 0.0, traceback.format_exc()[-400:])


def _pool_job(job):
    """Both arms in ONE worker on ONE seed, so their banks are comparable.

    Splitting them across workers would still be deterministic, but running
    them side by side makes a mismatch attributable to the arm rather than to
    anything the worker carried in.
    """
    opp, seed, seat = job
    try:
        opp_path = _opp_path(opp)
        out = {}
        for arm, path in (("tree", TREE), ("base", BASE)):
            if seat == 0:
                m0, m1 = _play(path, opp_path, seed)
                out[arm] = (m0, m1)
            else:
                m0, m1 = _play(opp_path, path, seed)
                out[arm] = (m1, m0)
        return (opp, seed, seat, out["tree"], out["base"], None)
    except Exception:
        import traceback
        return (opp, seed, seat, None, None, traceback.format_exc()[-400:])


# -------------------------------------------------------------------- report

def _paired(rows):
    """Paired margin per seed: both seat orders summed. A mirror scores +0."""
    per = {}
    for _arm, seed, _seat, margin, err in rows:
        if err:
            continue
        per.setdefault(seed, []).append(margin)
    return {s: sum(v) for s, v in per.items() if len(v) == 2}


def report_mirror(name, rows):
    errs = [r for r in rows if r[4]]
    paired = _paired(rows)
    total = sum(paired.values())
    nonzero = [s for s, v in paired.items() if v != 0]
    wins = sum(1 for r in rows if not r[4] and r[3] > 0)
    losses = sum(1 for r in rows if not r[4] and r[3] < 0)
    print("  %-14s paired %+12.1f   nonzero seeds %2d/%-2d   W-L %d-%d%s"
          % (name, total, len(nonzero), len(paired), wins, losses,
             "   ERRORS %d" % len(errs) if errs else ""))
    if errs:
        print("    first error: " + errs[0][4].strip().splitlines()[-1])
    return total, nonzero, errs


def main():
    t0 = time.time()

    if not os.environ.get("V3_SKIP_BUILD"):
        print("=" * 78)
        print("BUILD  %s, from v3's own tables" % LAYER)
        print("=" * 78)
        from pbt.expand import expand
        from pbt.flatify import flatify
        from pbt.treeify import treeify
        tmp = os.path.join(ROOT, "submission", "v3_expanded.py")
        if LAYER == "tree":
            treeify(BASE, TREE)
        elif LAYER == "flat":
            flatify(BASE, TREE)
        elif LAYER == "expanded":
            expand(BASE, TREE)
        else:                                    # flat_expanded: expand, then flatten
            expand(BASE, tmp)
            flatify(tmp, TREE)
        print("  %s  %d bytes"
              % (os.path.basename(BASE), os.path.getsize(BASE)))
        print("  %s  %d bytes  (+%d)"
              % (os.path.basename(TREE), os.path.getsize(TREE),
                 os.path.getsize(TREE) - os.path.getsize(BASE)))

    for fname, picked in entry_names():
        print("  kaggle entry  %-16s -> %s" % (fname, picked))

    pool = preflight()
    print("  pool: %s" % ", ".join(pool))

    seeds = [SEED0 + i for i in range(SEEDS)]
    pool_seeds = [SEED0 + i for i in range(POOL_SEEDS)]

    mirror_jobs = []
    for arm, left, right in (("base_vs_base", BASE, BASE),
                             ("tree_vs_tree", TREE, TREE),
                             ("tree_vs_base", TREE, BASE)):
        for seed in seeds:
            for seat in (0, 1):
                mirror_jobs.append((arm, left, right, seed, seat))
    pool_jobs = [(o, s, t) for o in pool for s in pool_seeds for t in (0, 1)]

    print("\n  %d mirror episodes + %d pool episodes on %d workers"
          % (len(mirror_jobs), 2 * len(pool_jobs), WORKERS))

    ctx = mp.get_context("forkserver")
    with ctx.Pool(WORKERS) as p:
        mirror = p.map(_mirror_job, mirror_jobs, chunksize=1)
        pooled = p.map(_pool_job, pool_jobs, chunksize=1)

    print("\n" + "=" * 78)
    print("SELF-PLAY  paired margin, both seat orders summed (HANDOFF rule 1)")
    print("=" * 78)
    by_arm = {}
    for r in mirror:
        by_arm.setdefault(r[0], []).append(r)
    verdict = True
    for arm in ("base_vs_base", "tree_vs_tree", "tree_vs_base"):
        total, nonzero, errs = report_mirror(arm, by_arm.get(arm, []))
        if total != 0 or nonzero or errs:
            verdict = False
    print("  base_vs_base is the identity control: anything but +0 means the")
    print("  harness leaks per-seat module state and no other row is evidence.")

    print("\n" + "=" * 78)
    print("EQUIVALENCE  per-game final banks, tree vs base on the same seed")
    print("=" * 78)
    bad = [r for r in pooled if r[5]]
    mismatch = [r for r in pooled if not r[5] and r[3] != r[4]]
    good = len(pooled) - len(bad) - len(mismatch)
    for r in mismatch[:8]:
        print("  MISMATCH %-42s seed %d seat %d  tree %s  base %s"
              % (r[0], r[1], r[2], r[3], r[4]))
    for r in bad[:3]:
        print("  ERROR    %-42s seed %d seat %d\n    %s"
              % (r[0], r[1], r[2], r[5].strip().splitlines()[-1]))
    print("  %d/%d games bank-identical%s"
          % (good, len(pooled),
             "" if not bad else "   (%d errored)" % len(bad)))
    if mismatch or bad:
        verdict = False

    print("\n" + "=" * 78)
    print("POOL  what v3 scores. Win rate is meaningful here: real opponents.")
    print("=" * 78)
    agg = {}
    for opp, _seed, _seat, tree, _base, err in pooled:
        if err:
            continue
        us, them = tree
        d = agg.setdefault(opp, [0, 0, 0, 0.0])
        d[0] += 1
        d[1] += 1 if us > them else 0
        d[2] += 1 if us < them else 0
        d[3] += us - them
    tn = tw = tl = 0
    tm = 0.0
    for opp in sorted(agg, key=lambda o: -agg[o][1] / max(1, agg[o][0])):
        n, w, l, m = agg[opp]
        tn, tw, tl, tm = tn + n, tw + w, tl + l, tm + m
        print("  %-42s %3d games  %5.1f%%  mean %+9.1f"
              % (opp[:42], n, 100.0 * w / n, m / n))
    if tn:
        print("  %-42s %3d games  %5.1f%%  mean %+9.1f"
              % ("TOTAL", tn, 100.0 * tw / tn, tm / tn))

    print("\n" + "=" * 78)
    print("VERDICT  %s" % ("EQUIVALENT -- the tree is the same agent as the array"
                           if verdict else
                           "NOT EQUIVALENT -- do not submit, this is a bug"))
    print("=" * 78)
    print("  %.1f min" % ((time.time() - t0) / 60.0))
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())
