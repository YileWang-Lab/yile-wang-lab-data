"""Single-leaf perturbation scan: which route steps are SOFT?

WHAT THIS ANSWERS. The tape is uneditable -- entry 312 assumes everything
entries 0-311 did, and four separate probes collapsed the run (HANDOFF section
4). But "uneditable" was measured on the tape as a whole, never per step. The
perfect-fit CART makes the per-step question cheap for the first time: change
exactly one key, keep the eleven guards, and measure how much of the damage the
guards absorb. Steps where they absorb all of it are SOFT and are where any
future edit has to live.

This is a MEASUREMENT, not an improvement. Every variant here is expected to
lose; the deliverable is the ranking and the size of the loss.

THE LEAF IS NOT THE KEY, and this is the one place the tree representation is
misleading. `grow` splits until pure, so every key whose action is identical --
and PASS steps are the overwhelming majority -- lands in the SAME leaf. Editing
that leaf node would silently change hundreds of keys at once, and the run would
collapse for reasons that had nothing to do with the step under test. So an edit
here does not write to a leaf: `isolate` inserts three integer comparisons that
split the single key (legacy, label, step) out of its leaf and leaves every other
key routed to the original. `_verify_isolation` then re-checks all 7,190 keys and
requires that EXACTLY ONE changed, before a single game is played.

DISCIPLINE, all of it paid for earlier in this project:

  * PAIRED, common random numbers, both seats per seed. A byte-identical mirror
    scores 0 (HANDOFF rule 1 -- raw win rate is invalid here, an identical copy
    wins seat 0 only 15% of the time).
  * PAIRED WIN RATE as the headline, margin alongside. Section 29: the win rate
    is more sensitive on every real effect and still returns exactly zero on the
    null, and the advantage is largest exactly when the margin is noisy.
  * An IDENTITY CONTROL. Variant 0 is the unmodified tree and must return
    +0 margin, 0.0pp and a 0% firing rate. Section 21 wasted three measurements
    on parameters that turned out to be inert; identical rows are the symptom.
  * FIRING RATE and the CONDITIONAL mean, never just the mean (HANDOFF rule 4).
    A leaf edit only fires in games that both select that table and reach that
    step, and a change worth +858 read as -18 on a sample that fired 28 times.

WHY THE CENSUS COMES FIRST. A key that no game ever selects has a firing rate of
zero by construction, and scanning it burns a full pool run to measure nothing.
Ten tables exist but a given episode walks exactly one of them, so most keys are
unreachable in most games. The census plays the pool once and counts which
(legacy, label, step) keys are actually looked up, and the scan then spends its
budget on the reachable ones, most-visited first.

RUNS AT 10 WORKERS ON PURPOSE. dynamic/rl/train.py owns the 26 physical cores
while it is training; extra load only slows it, never corrupts it.

    python dynamic/tape/leaf_scan.py [n_seeds] [workers] [mode]

    mode  pass_all (default) | pass_farmer | pass_hands | drop_market | shift1
    env   SCAN_TOP=12       how many keys to scan
          SCAN_STEPS=a:b    restrict candidates to this step range
          SCAN_CENSUS=2     seeds used for the reachability census
          SCAN_MIN_SEEN=.25 drop keys seen in fewer than this share of census
                            games -- their firing rate is too low to measure
          SCAN_DESYNC=1     also run the half-applied 'tree-only' arm, whose
                            gap to 'coherent' is the guard-desync cost
"""
import collections
import copy
import importlib.util
import json
import multiprocessing
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_HERE = os.path.dirname(os.path.abspath(__file__))
# Running this as a script puts dynamic/tape/ on sys.path[0], where this file
# would shadow modules the pipeline imports by name.
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _HERE]
sys.path.insert(0, ROOT)

from dynamic.tape.tree_table import (          # noqa: E402
    LABELS, LABEL_CODE, SUFFIX, _walk, load, rows_from_tables)

# The round-robin of HANDOFF section 7. kawa is included here on purpose: the
# scan measures damage against the field we actually play, and kawa is in it.
#
# FOUR OPPONENT FILES IMPORT NON-STDLIB MODULES at module scope and cannot be
# loaded in this venv -- `structured-economic-policy` and `adaptive-farming-
# strategy` both pull in IPython, and `findings-from-zero-to-top-meta` and
# `precomputed-schedule-policy` do the same. The tree_equiv run of 2026-08-21
# lost 48 of its 144 games to exactly this and then reported "NOT EQUIVALENT"
# for what was purely a missing import. `preflight` below refuses to start
# rather than let it happen again.
POOL = ["kaggriculture-multi-route-farming-agent",
        "v111-8c4s-economic-core-premium-lead",
        "kaggriculture-3000-socre",
        "kaggriculture-rank-your-agent",
        "kaggriculture-ttv1",
        "strong-barnyard-economist"]

STEP, LABEL, LEGACY = 2, 1, 0                  # indices into FEATURES
_loads = [0]


def _load_agent(name):
    """Load an opponent by PATH, never by import (HANDOFF rule 3)."""
    _loads[0] += 1
    path = os.path.join(ROOT, "opponents", name + ".py")
    spec = importlib.util.spec_from_file_location(
        f"leaf_{os.getpid()}_{_loads[0]}", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return getattr(m, "_submission_entry", None) or m.agent


def preflight():
    """Load every opponent once, in the parent, before any game is scheduled.

    A file that raises at import produces one dead job per (seed, seat) and the
    rows are silently dropped, so the run finishes looking healthy on a fraction
    of the intended sample. Failing here costs a second and names the file.
    """
    broken = []
    for name in POOL:
        try:
            _load_agent(name)
        except Exception as exc:
            broken.append(f"{name}: {type(exc).__name__}: {exc}")
    if broken:
        raise SystemExit("these opponents cannot be loaded in this venv:\n  "
                         + "\n  ".join(broken))


# ------------------------------------------------------------------- editing

def _find_leaf(tree, x):
    """(parent, side, leaf) for key `x`. parent is None if the root is a leaf."""
    node, parent, side = tree, None, None
    while "leaf" not in node:
        parent = node
        side = "left" if x[node["feat"]] <= node["thr"] else "right"
        node = node[side]
    return parent, side, node


def _isolating_subtree(old, new, x):
    """A subtree that returns `new` for exactly `x` and `old` for everything else.

    Three nested integer comparisons, one per feature. For feature f with value
    v the shape is

        f <= v-1  -> old
        f <= v    -> (next feature)
        else      -> old

    which pins f to exactly v because every feature is an integer code. Built
    innermost-first so the three tests nest. `old` is REUSED rather than copied:
    the walk is read-only, so one shared node keeps the edit O(1) in memory.
    """
    cur = new
    for f in (LEGACY, LABEL, STEP):            # outermost ends up being STEP
        v = x[f]
        inner = {"feat": f, "thr": v - 1, "left": old, "right": cur}
        cur = {"feat": f, "thr": v, "left": inner, "right": old}
    return cur


def isolate(tt, key, action):
    """Point `key` at `action`, leaving all 7,189 other keys untouched.

    Returns an `undo()` that restores the tree exactly, so one worker can scan
    many keys without re-deserialising the 780 KB JSON each time.
    """
    slot = len(tt.codebook)
    tt.codebook.append(action)
    parent, side, leaf = _find_leaf(tt.tree, key)
    sub = _isolating_subtree(leaf, {"leaf": slot}, key)
    if parent is None:
        tt.tree = sub
    else:
        parent[side] = sub

    def undo():
        del tt.codebook[slot:]
        if parent is None:
            tt.tree = leaf
        else:
            parent[side] = leaf
    return undo


def _verify_isolation(tt, X, y, key):
    """Exactly one of the 7,190 keys may differ. Cheap, and it runs before games.

    An isolation bug is the failure mode that would look like a real result: the
    edit silently hits a whole family of steps, the run collapses, and the step
    under test takes the blame.
    """
    changed = [i for i, (x, target) in enumerate(zip(X, y))
               if _walk(tt.tree, x) != target]
    if len(changed) != 1 or tuple(X[changed[0]]) != tuple(key):
        raise AssertionError(
            f"isolation failed for {key}: {len(changed)} keys changed"
            f"{' at ' + str(X[changed[0]]) if len(changed) == 1 else ''}")


# ----------------------------------------------------------------- mutations

def mutate(action, mode, nxt=None):
    """The perturbation under test. `nxt` is the following step's action."""
    a = copy.deepcopy(action)
    if mode == "pass_farmer":
        a["farmer"] = ["PASS"]
    elif mode == "pass_hands":
        a["hands"] = [["PASS"] for _ in (a.get("hands") or [])]
    elif mode == "pass_all":
        a["farmer"] = ["PASS"]
        a["hands"] = [["PASS"] for _ in (a.get("hands") or [])]
    elif mode == "drop_market":
        a["market"] = []
    elif mode == "shift1":
        if nxt is None:
            return None
        a["farmer"] = copy.deepcopy(nxt.get("farmer") or ["PASS"])
        a["hands"] = copy.deepcopy(nxt.get("hands") or [])
    else:
        raise ValueError(f"unknown mode {mode}")
    return None if a == action else a          # inert edit: not worth a run


# ------------------------------------------------------------------- census

class _Recorder:
    """Wraps a TreeTable and records which key each turn actually looked up."""

    def __init__(self, tt, sink):
        self.tt, self.sink = tt, sink
        self.n_steps = tt.n_steps

    def lookup(self, legacy, label, step):
        s = min(max(0, int(step)), self.n_steps - 1)
        self.sink.append((1 if legacy else 0, LABEL_CODE[label], s))
        return self.tt.lookup(legacy, label, step)


_TT = []


def _tree():
    """One deserialisation per worker; the JSON is ~780 KB and never changes."""
    if not _TT:
        _TT.append(load())
    return _TT[0]


def _census_game(job):
    opp, seed, seat = job
    try:
        from planner.simulate import Simulator
        from dynamic.tape.pipeline import Pipeline
        sink = []
        me = Pipeline().use_table_tree(_Recorder(_tree(), sink)).agent
        other = _load_agent(opp)
        pair = (me, other) if seat == 0 else (other, me)
        sim = Simulator.new_episode(configuration={"episodeSteps": 720},
                                    seed=seed)
        sim.run_episode(pair[0], pair[1])
        return (collections.Counter(sink), None)
    except Exception:
        import traceback
        return (collections.Counter(), traceback.format_exc()[-400:])


# --------------------------------------------------------------------- games

def _patch_table(k, key, action):
    """Point the MODULE's array at the edit too, so the lookahead agrees.

    THREE call sites read the raw table and the tree replaces only one of them:

      line 990  the base lookup                    -- replaced by the tree
      line 361  `_trace_actor_action`, CURRENT step -- `_weed_repair_action`
                replays a deferred op by asking the array what this step was
                supposed to do, for up to `_WEED_REPLAY_STEPS` = 8 steps
      line 299  `_future_sells`, step + 1           -- `_preempt_shift` borrows
                tomorrow's premium sells into today and books the amount in
                `_SHIFT_STATE["due"]`, which `_repay_shift` subtracts next turn

    A tree-only edit is therefore HALF APPLIED: the base action changes while
    two guards keep acting on the plan the tape used to have. The damage that
    produces is desync, not economics, and attributing it to the edited step
    would be wrong. Patching the array makes all three sites agree.

    Safe because `Pipeline.__init__` builds its own private module via
    `_fresh_kawa()`, so this array belongs to this episode and nothing else.
    """
    legacy, lb, step = key
    attr = ("_LEGACY_ACTIONS_" if legacy else "_ACTIONS_") + SUFFIX[LABELS[lb]]
    getattr(k, attr)[step] = action


def _game(job):
    """One episode. `vid` None is the identity control -- the tree unmodified.

    `vid` is (key, arm). arm 'coherent' patches the module array as well as the
    tree; arm 'tree_only' deliberately does not, and the gap between the two is
    how much of the loss is guard desync rather than the step itself.
    """
    vid, action, opp, seed, seat = job
    key, arm = vid if vid is not None else (None, None)
    undo = None
    try:
        from planner.simulate import Simulator
        from dynamic.tape.pipeline import Pipeline
        tt = _tree()
        if key is not None:
            undo = isolate(tt, key, action)
        p = Pipeline().use_table_tree(tt)
        if key is not None and arm == "coherent":
            _patch_table(p.k, key, action)
        me = p.agent
        other = _load_agent(opp)
        pair = (me, other) if seat == 0 else (other, me)
        sim = Simulator.new_episode(configuration={"episodeSteps": 720},
                                    seed=seed)
        m0, m1 = sim.run_episode(pair[0], pair[1])
        us, them = (m0, m1) if seat == 0 else (m1, m0)
        return (vid, opp, seed, seat, us - them, None)
    except Exception:
        import traceback
        return (vid, opp, seed, seat, 0.0, traceback.format_exc()[-400:])
    finally:
        if undo is not None:
            undo()


# -------------------------------------------------------------------- report

def report(res, order, visits, census_games):
    per = {}
    for key, opp, seed, _seat, margin, err in res:
        if err:
            continue
        per.setdefault((key, opp, seed), []).append(margin)
    paired = {}
    for (key, opp, seed), v in per.items():
        if len(v) == 2:
            paired.setdefault(key, {})[(opp, seed)] = sum(v)

    base = paired.get(None, {})
    print()
    print(f"{'key (legacy,label,step)':<34}{'paired':>10}{'d margin':>11}"
          f"{'t':>7}{'win pp':>9}{'W-L-T':>12}{'fires':>7}{'cond':>10}"
          f"{'seen':>7}")
    for key in order:
        d = paired.get(key)
        if not d:
            continue
        keys = [k for k in d if k in base]
        diffs = [d[k] - base[k] for k in keys]
        if not diffs:
            continue
        fired = [x for x in diffs if x != 0.0]
        wins = sum(1 for x in diffs if x > 0)
        losses = sum(1 for x in diffs if x < 0)
        ties = len(diffs) - wins - losses
        # Section 29: ties excluded, standard sign test, reported as points
        # above 50. A true null returns exactly +0.0.
        decided = wins + losses
        pp = (100.0 * wins / decided - 50.0) if decided else 0.0
        mean = statistics.mean(diffs)
        se = (statistics.pstdev(diffs) / len(diffs) ** 0.5) if len(diffs) > 1 else 0.0
        if key is None:
            name, seen = "IDENTITY CONTROL (unmodified)", ""
        else:
            k, arm = key
            tag = "" if arm == "coherent" else "  [tree-only]"
            name = f"lg{k[0]} {LABELS[k[1]][:14]} step={k[2]}{tag}"
            seen = f"{visits.get(k, 0) / max(1, census_games):.1f}"
        print(f"{name:<34}{statistics.mean(d.values()):>10,.0f}{mean:>+11,.0f}"
              f"{(mean / se if se > 1e-9 else 0.0):>7.1f}{pp:>+9.1f}"
              f"{wins:>4}-{losses}-{ties:<5}"
              f"{100.0 * len(fired) / len(diffs):>6.0f}%"
              f"{(statistics.mean(fired) if fired else 0.0):>+10,.0f}{seen:>7}")
    print()
    print("d margin / win pp are versus the identity control on the SAME seed, "
          "opponent and seat pair.")
    print("fires = share of paired games the edit changed at all; cond = mean "
          "margin among those (HANDOFF rule 4).")
    print("seen  = mean lookups of that key per census episode.")


# ----------------------------------------------------------------------- main

def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    mode = sys.argv[3] if len(sys.argv) > 3 else "pass_all"
    top = int(os.environ.get("SCAN_TOP", "12"))
    census_seeds = int(os.environ.get("SCAN_CENSUS", "2"))
    lo, hi = 0, 10 ** 9
    if os.environ.get("SCAN_STEPS"):
        lo, hi = (int(v) for v in os.environ["SCAN_STEPS"].split(":"))

    import random
    rng = random.Random(int(os.environ.get("SCANSEED", "20260821")))
    seeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(n)]
    ctx = multiprocessing.get_context("forkserver")

    preflight()
    tt = load()
    tables = json.load(open(os.path.join(ROOT, "logs", "tape", "tables.json")))
    X, y, _cb = rows_from_tables(tables)
    print(f"tree: {len(tt.codebook):,} distinct actions, "
          f"{tt.n_steps:,} steps x {2 * len(LABELS)} tables = {len(X):,} keys")

    # ------------------------------------------------------- 1. reachability
    print()
    print(f"1. CENSUS -- which keys do real games look up? "
          f"({len(POOL)} opponents x {census_seeds} seeds x 2 seats)", flush=True)
    cjobs = [(o, s, st) for o in POOL for s in seeds[:census_seeds] for st in (0, 1)]
    t0 = time.time()
    with ctx.Pool(workers) as pool:
        cres = pool.map(_census_game, cjobs, chunksize=1)
    cerrs = [e for _c, e in cres if e]
    if cerrs:
        print(f"   {len(cerrs)} errors; first:\n{cerrs[0]}")
    visits = collections.Counter()
    for c, _e in cres:
        visits.update(c)
    print(f"   {time.time() - t0:.0f}s   {len(visits):,} of {len(X):,} keys "
          f"reachable ({100.0 * len(visits) / len(X):.1f}%)")
    tabs = collections.Counter((k[0], k[1]) for k in visits)
    for (lg, lb), cnt in tabs.most_common():
        print(f"   legacy={lg} {LABELS[lb]:<22} {cnt:>4} distinct steps seen")

    # -------------------------------------------------------- 2. candidates
    # RANKING BY VISIT COUNT CONFINES THE SCAN TO THE OPENING. Measured
    # 2026-08-21: ordering by -visits put all twelve candidates inside steps
    # 0-20 and every one of them was catastrophic, which was never in doubt.
    # The cause is that `_kawa_route_label` reads `town.unlocked_shops` and
    # shops only ever unlock, so every episode starts in the same table and
    # leaves it once the town grows -- visit counts peak at step 0 and decay,
    # and "most visited first" is "earliest first" wearing a disguise.
    #
    # So visits are a REACHABILITY FILTER only: a key seen in too few census
    # games has a firing rate near zero and cannot be measured whatever it is
    # worth. Order is then a golden-ratio low-discrepancy sweep over the step
    # range -- deterministic, and every prefix of it is spread evenly across the
    # whole route, so inert edits being skipped cannot cluster the sample.
    floor = float(os.environ.get("SCAN_MIN_SEEN", "0.25")) * len(cjobs)
    cands = [k for k in visits if lo <= k[2] <= hi and visits[k] >= floor]
    cands.sort(key=lambda k: ((k[2] * 0.6180339887498949) % 1.0, k))
    print(f"   {len(cands):,} keys pass the reachability floor "
          f"(seen in >= {floor:.0f} of {len(cjobs)} census games); "
          f"steps {min((k[2] for k in cands), default=-1)}-"
          f"{max((k[2] for k in cands), default=-1)}")
    # 'coherent' is the correct semantics and the default. SCAN_DESYNC=1 adds
    # the half-applied arm alongside it, on the SAME keys and seeds, so the two
    # rows differ only in whether the guards' lookahead saw the edit.
    arms = ("coherent", "tree_only") if os.environ.get("SCAN_DESYNC") else ("coherent",)
    variants, order, picked = [], [None], 0
    for key in cands:
        if picked >= top:
            break
        legacy, lb, step = key
        prefix = "_LEGACY_ACTIONS_" if legacy else "_ACTIONS_"
        table = tables[prefix + {
            "10c4s_3q": "10C4S_3Q", "8c6s_3q": "8C6S_3Q", "6c8s_3q": "6C8S_3Q",
            "6c12s_4q_first_yarn": "6C12S_4Q_FIRST_YARN",
            "6c12s_4q_second_yarn": "6C12S_4Q_SECOND_YARN"}[LABELS[lb]]]
        nxt = table[step + 1] if step + 1 < len(table) else None
        edited = mutate(table[step], mode, nxt)
        if edited is None:                     # the edit is a no-op at this key
            continue
        undo = isolate(tt, key, edited)
        try:
            _verify_isolation(tt, X, y, key)   # before any game is played
        finally:
            undo()
        picked += 1
        for arm in arms:
            variants.append(((key, arm), edited))
            order.append((key, arm))
    print()
    print(f"2. CANDIDATES -- {len(variants) // len(arms)} keys x {len(arms)} "
          f"arm(s) {arms}, mode '{mode}', isolation verified on all "
          f"{len(X):,} keys for each")

    # -------------------------------------------------------------- 3. games
    jobs = [(None, None, o, s, st) for o in POOL for s in seeds for st in (0, 1)]
    jobs += [(v, a, o, s, st) for v, a in variants
             for o in POOL for s in seeds for st in (0, 1)]
    print()
    print(f"3. SCAN -- ({len(variants)} variants + 1 control) x {len(POOL)} "
          f"opponents x {n} seeds x 2 seats = {len(jobs):,} episodes", flush=True)
    t0 = time.time()
    with ctx.Pool(workers) as pool:
        res = pool.map(_game, jobs, chunksize=1)
    print(f"   {time.time() - t0:.0f}s", flush=True)
    errs = [r[5] for r in res if r[5]]
    if errs:
        print(f"   {len(errs)} errors; first:\n{errs[0]}")

    report(res, order, visits, len(cjobs))
    ctrl = [r for r in res if r[0] is None]
    print()
    print("Read the control row first: anything other than +0 / +0.0pp / 0% "
          f"means the harness is not paired and nothing below is valid "
          f"({len(ctrl)} control episodes).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
