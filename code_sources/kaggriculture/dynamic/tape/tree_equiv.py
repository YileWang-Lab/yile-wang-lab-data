"""Is the CART equivalent to the route table? Three checks, strongest last.

The claim is EQUIVALENCE, not improvement, so the bar is exact identity rather
than a favourable mean. Each check can only fail:

  1. TABLE LEVEL   all 7,190 (legacy, label, step) keys come back exactly.
  2. ACTION LEVEL  driven from one simulator, kawa and the tree pipeline are
                   handed the SAME observation every turn and every farmer /
                   hands / market field is compared. `pipeline.verify`.
  3. PLAY LEVEL    full episodes.

Play level is where a subtle divergence would show, and it is checked two ways.

MIRROR. Tree pipeline against kawa, both seat orders per seed. HANDOFF rule 1:
raw win rate is meaningless here -- an agent against a byte-identical copy of
itself wins seat 0 only 15% of the time -- so the test is the PAIRED margin,
which a true mirror scores at exactly 0, with 0 wins and 0 losses.

POOL, and this is the strongest of the three. Play the tree against each pool
opponent, then kawa against the same opponent on the same seed and seat, and
require the two final banks to be IDENTICAL, seed by seed. Equal means or equal
win rates would pass even if the agents diverged and the differences cancelled;
per-seed identity cannot. A single mismatched seed fails the run and is printed.
"""
import importlib.util
import multiprocessing as mp
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _HERE]
sys.path.insert(0, ROOT)

# The pool, in the round-robin of HANDOFF section 7. kawa itself is excluded
# here because it is the mirror check, which is run separately.
POOL = ["v111-8c4s-economic-core-premium-lead",
        "kaggriculture-3000-socre",
        "kaggriculture-rank-your-agent",
        "kaggriculture-ttv1",
        "adaptive-farming-strategy-for-kaggriculture",
        "kaggriculture-structured-economic-policy"]

_loads = [0]


def _load_agent(name):
    """Load an opponent file under a unique module name (never by import)."""
    _loads[0] += 1
    path = os.path.join(ROOT, "opponents", name + ".py")
    spec = importlib.util.spec_from_file_location(
        f"opp_{os.getpid()}_{_loads[0]}", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return getattr(m, "_submission_entry", None) or m.agent


_TREE = []


def _tree():
    """One deserialisation per worker -- the JSON is ~1 MB and never changes."""
    if not _TREE:
        from dynamic.tape.tree_table import load
        _TREE.append(load())
    return _TREE[0]


def _arm(which):
    """The three things being compared, built the same way every time.

    `pipe` is the control: the same 11-layer Pipeline with the ARRAY still doing
    the lookup. If `tree` disagrees with `kawa`, `pipe` says whether the tree or
    the pipeline decomposition is responsible -- without it a failure is only
    "something in this stack differs".
    """
    from dynamic.tape.pipeline import Pipeline, _fresh_kawa
    if which == "kawa":
        m = _fresh_kawa()
        return getattr(m, "_submission_entry", None) or m.agent
    if which == "pipe":
        return Pipeline().agent
    return Pipeline().use_table_tree(_tree()).agent


ARMS = ("tree", "pipe", "kawa")


# --------------------------------------------------------------- play level

def _pool_game(job):
    """Same seed, same seat, same opponent -- once with the tree, once with kawa.

    Both are played inside ONE worker so nothing about the environment differs
    between them except which of the two produces the base action.
    """
    opp, seed, seat = job
    try:
        from planner.simulate import Simulator
        out = {}
        for which in ARMS:
            me = _arm(which)
            other = _load_agent(opp)
            pair = (me, other) if seat == 0 else (other, me)
            sim = Simulator.new_episode(configuration={"episodeSteps": 720},
                                        seed=seed)
            m0, m1 = sim.run_episode(pair[0], pair[1])
            out[which] = (m0, m1) if seat == 0 else (m1, m0)
        return (opp, seed, seat, out, None)
    except Exception:
        import traceback
        return (opp, seed, seat, None, traceback.format_exc()[-400:])


def _mirror_game(job):
    """Tree pipeline vs kawa. Both seat orders are played by the caller."""
    seed, seat = job
    try:
        from planner.simulate import Simulator
        me = _arm("tree")
        other = _arm("kawa")
        pair = (me, other) if seat == 0 else (other, me)
        sim = Simulator.new_episode(configuration={"episodeSteps": 720},
                                    seed=seed)
        m0, m1 = sim.run_episode(pair[0], pair[1])
        us, them = (m0, m1) if seat == 0 else (m1, m0)
        return (seed, seat, us - them, None)
    except Exception:
        import traceback
        return (seed, seat, 0.0, traceback.format_exc()[-400:])


def _seeds(n, salt=20260821):
    import random
    rng = random.Random(salt)
    return [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(n)]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 26
    failures = []

    # ---------------------------------------------------------- 1. table
    print("=" * 66)
    print("1. TABLE LEVEL -- every key returns its own action")
    from dynamic.tape import tree_table as tt_mod
    tt, X, y = tt_mod.build()
    ok, total = tt_mod.selftest(tt, X, y)
    nodes, leaves, depth = tt_mod.stats(tt.tree)
    print(f"   keys {total:,}   distinct actions {len(tt.codebook):,}")
    print(f"   nodes {nodes:,}  leaves {leaves:,}  max depth {depth}")
    print(f"   exact {ok:,}/{total:,} = {100.0 * ok / total:.2f}%")
    if ok != total:
        failures.append(f"table level: {total - ok} keys wrong")
    path = tt.save()
    print(f"   saved {path} ({os.path.getsize(path):,} bytes)")

    # --------------------------------------------------------- 2. action
    print()
    print("=" * 66)
    print("2. ACTION LEVEL -- lockstep against kawa on identical observations")
    from dynamic.tape.pipeline import Pipeline, verify
    loaded = tt_mod.load()
    same, tot, diffs = verify(3, build=lambda: Pipeline().use_table_tree(loaded))
    print(f"   identical action fields {same:,}/{tot:,} = "
          f"{100.0 * same / tot:.2f}%")
    if same != tot:
        failures.append(f"action level: {tot - same} fields differ")
        for st, key, a, b in diffs:
            print(f"   step {st:>4} {key}\n      kawa: {a}\n      tree: {b}")

    # ----------------------------------------------------------- 3. play
    print()
    print("=" * 66)
    print(f"3a. MIRROR -- tree vs kawa, {n} seeds x both seats (paired margin)")
    seeds = _seeds(n)
    ctx = mp.get_context("forkserver")
    with ctx.Pool(workers) as pool:
        res = pool.map(_mirror_game, [(s, st) for s in seeds for st in (0, 1)])
    errs = [e for *_x, e in res if e]
    if errs:
        failures.append(f"mirror: {len(errs)} errors")
        print(f"   {len(errs)} errors; first:\n{errs[0]}")
    per = {}
    for seed, seat, margin, e in res:
        if not e:
            per.setdefault(seed, []).append(margin)
    paired = [sum(v) for v in per.values() if len(v) == 2]
    wins = sum(1 for p in paired if p > 0)
    losses = sum(1 for p in paired if p < 0)
    nonzero = [p for p in paired if p != 0]
    print(f"   paired margin  sum {sum(paired):+,.0f}   "
          f"W-L {wins}-{losses}   nonzero seeds {len(nonzero)}/{len(paired)}")
    if nonzero:
        failures.append(f"mirror: {len(nonzero)} seeds with nonzero margin")
        print(f"   first nonzero margins: {nonzero[:5]}")

    print()
    print(f"3b. POOL -- per-seed final banks, tree vs kawa against {len(POOL)} "
          f"opponents")
    jobs = [(o, s, st) for o in POOL for s in seeds for st in (0, 1)]
    print(f"   {len(jobs):,} paired games ({2 * len(jobs):,} episodes)",
          flush=True)
    with ctx.Pool(workers) as pool:
        res = pool.map(_pool_game, jobs, chunksize=1)
    errs = [(o, s, e) for o, s, _st, _o, e in res if e]
    if errs:
        failures.append(f"pool: {len(errs)} errors")
        print(f"   {len(errs)} errors; first ({errs[0][0]}, seed {errs[0][1]}):")
        print("   " + errs[0][2].replace("\n", "\n   "))
    shown = 0
    by_opp = {}
    tot = {"tree": 0, "pipe": 0}
    for opp, seed, seat, out, e in res:
        if e:
            continue
        rec = by_opp.setdefault(opp, {"n": 0, "tree": 0, "pipe": 0, "wins": 0})
        rec["n"] += 1
        if out["tree"][0] > out["tree"][1]:
            rec["wins"] += 1
        for arm in ("tree", "pipe"):
            if out[arm] == out["kawa"]:
                rec[arm] += 1
                tot[arm] += 1
            elif arm == "tree" and shown < 5:
                shown += 1
                print(f"   MISMATCH {opp} seed {seed} seat {seat}: "
                      f"tree {out['tree'][0]:,.0f} v {out['tree'][1]:,.0f}   "
                      f"kawa {out['kawa'][0]:,.0f} v {out['kawa'][1]:,.0f}   "
                      f"(control pipe {out['pipe'][0]:,.0f} v "
                      f"{out['pipe'][1]:,.0f})")
    played = sum(r["n"] for r in by_opp.values())
    print()
    print(f"   games where the final banks equal kawa's, seed by seed")
    print(f"   {'opponent':<46}{'n':>5}{'tree':>7}{'pipe':>7}{'tree W':>8}")
    for opp in POOL:
        rec = by_opp.get(opp)
        if not rec:
            continue
        print(f"   {opp:<46}{rec['n']:>5}{rec['tree']:>7}{rec['pipe']:>7}"
              f"{rec['wins']:>8}")
    print(f"   {'TOTAL':<46}{played:>5}{tot['tree']:>7}{tot['pipe']:>7}")
    if tot["tree"] != played:
        failures.append(f"pool: {played - tot['tree']}/{played} games differ "
                        f"from kawa (control: pipe differs in "
                        f"{played - tot['pipe']})")

    print()
    print("=" * 66)
    if failures:
        print("NOT EQUIVALENT:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("EQUIVALENT: identical at the table, at every action field, and in "
          "every episode played.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
