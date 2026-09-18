"""Score a trained RL checkpoint against everything we have, unattended.

Runs when training finishes (or on demand) and writes logs/rl/RESULTS.md, so a
result is waiting rather than needing a session to produce it.

WHAT IT COMPARES AGAINST, and why each one is there:

  agent4 identity      the RL agent under a zero-init policy. This is the true
                       baseline: the policy starts here, so any gain must be
                       measured from it, not from agent4 (they differ by -49.5
                       on a per-game sd of ~30,000 because of the opponent
                       forecast cache -- section 22 of the handoff).
  the 6-agent pool     the sparring set every result this session was measured on.
  submission/main.py   the shipped tape+market build, +12,160 paired on this
                       pool. This is the number that has to be beaten.
  kawa unmodified      the public tape underneath it, +11,628.

Scored by BOTH paired margin and paired win rate. They disagreed once already
this session -- SHED_PANIC_FRACTION=0.40 wins 74.9% of paired seeds on a
NEGATIVE mean margin -- and the ladder scores the win rate, so both are printed
and any disagreement is visible rather than hidden.
"""
import json
import multiprocessing as mp
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _HERE]
sys.path.insert(0, ROOT)

POOL = ["kaggriculture-multi-route-farming-agent",
        "v111-8c4s-economic-core-premium-lead",
        "kaggriculture-frontier-the-soil-remembers-rain",
        "kaggriculture-3000-socre",
        "kaggriculture-rank-your-agent",
        "strong-barnyard-economist"]
CKPT_DIR = os.path.join(ROOT, "logs", "rl")
_n = [0]


def _base_genome():
    """Resolved in the PARENT and shipped to workers, never computed after an
    agent has been loaded.

    `agent_rl.py` puts `dynamic/` on sys.path when it executes, and
    `dynamic/search.py` then shadows the top-level `search` package that
    `route.evaluate` imports -- so `from route.search import to_params` raises a
    circular-import error, but only once an agent module has already been
    exec'd. That ordering made every RL game in this script fail while the
    plain-file agents were fine.
    """
    from route.search import to_params
    g = json.load(open(os.path.join(ROOT, "dynamic", "best_genome3.json")))["genome"]
    p = to_params(dict(g))
    p["OPP_MODEL"] = 1
    p["SHED_PANIC_FRACTION"] = 0.40
    return p


def _mk(kind, weights=None):
    """kind: 'rl' | 'identity' | a path to a plain agent file."""
    import importlib.util
    _n[0] += 1
    if kind in ("rl", "identity"):
        path = os.path.join(ROOT, "dynamic", "rl", "agent_rl.py")
    else:
        path = kind
    spec = importlib.util.spec_from_file_location(f"ev_{os.getpid()}_{_n[0]}", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    if kind in ("rl", "identity"):
        from dynamic.rl.net import DailyNet, SellNet, NumpyPolicy, to_numpy_weights
        w = weights if kind == "rl" else to_numpy_weights(DailyNet().eval(),
                                                          SellNet().eval())
        m.configure(_W["genome"])
        m.set_policy(NumpyPolicy(w, explore=False))
        return m.agent
    return getattr(m, "_submission_entry", None) or m.agent


_W = {}


def _init(weights, genome):
    _W["w"] = weights
    _W["genome"] = genome


def play(job):
    label, kind, opp, seed, seat = job
    try:
        from planner.simulate import Simulator
        me = _mk(kind, _W.get("w"))
        op = _mk(os.path.join(ROOT, "opponents", f"{opp}.py"))
        pair = [me, op] if seat == 0 else [op, me]
        sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
        m0, m1 = sim.run_episode(pair[0], pair[1])
        us, them = (m0, m1) if seat == 0 else (m1, m0)
        return (label, opp, seed, seat, us - them, None)
    except Exception:
        import traceback
        return (label, opp, seed, seat, 0.0, traceback.format_exc()[-200:])


def main():
    n_seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 26
    ckpt = sys.argv[3] if len(sys.argv) > 3 else os.path.join(CKPT_DIR, "best.npz")

    weights = None
    tag = "(no checkpoint)"
    if os.path.exists(ckpt):
        import numpy as np
        z = np.load(ckpt)
        weights = {k: z[k].astype(np.float32) for k in z.files}
        tag = os.path.basename(ckpt)

    # EVERY HISTORICAL BUILD WORTH BEATING, not just the current submission.
    # Asking "did it beat what we ship" is the wrong bar if what we ship is not
    # our best: the ladder has 55600561 at 2630.9 against 55614625's 1828.3, so
    # the shipped file is 800 points BELOW an earlier one (HANDOFF section 7).
    # deliver/ holds the two baked candidates from the tape+market line.
    cands = [("RL identity (baseline)", "identity"),
             ("SHIPPED tape+market", os.path.join(ROOT, "submission", "main.py")),
             ("kawa unmodified",
              os.path.join(ROOT, "opponents", f"{POOL[0]}.py"))]
    for label, rel in (("deliver BEST_b0_tapeswap", "deliver/BEST_b0_tapeswap.py"),
                       ("deliver ALT_struct", "deliver/ALT_struct.py")):
        path = os.path.join(ROOT, rel)
        if os.path.exists(path):
            cands.append((label, path))
    if weights is not None:
        cands.insert(0, (f"RL trained {tag}", "rl"))

    import random
    rng = random.Random(20260821)
    seeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(n_seeds)]
    jobs = [(lbl, kind, o, s, st) for lbl, kind in cands for o in POOL
            for s in seeds for st in (0, 1)]
    print(f"{len(cands)} agents x {len(POOL)} opponents x {n_seeds} seeds x 2 seats "
          f"= {len(jobs):,} games", flush=True)
    t0 = time.time()
    genome = _base_genome()          # parent side, before any agent is loaded
    with mp.get_context("forkserver").Pool(workers, initializer=_init,
                                           initargs=(weights, genome)) as pool:
        res = pool.map(play, jobs, chunksize=4)
    print(f"{time.time() - t0:.0f}s", flush=True)

    errs = [(l, e) for l, _o, _s, _st, _m, e in res if e]
    if errs:
        print(f"{len(errs)} errored games; first:\n{errs[0][0]}: {errs[0][1]}",
              flush=True)
    per = {}
    for lbl, opp, seed, seat, margin, err in res:
        if err:
            continue
        per.setdefault((lbl, opp, seed), []).append(margin)
    paired = {}
    for (lbl, opp, seed), v in per.items():
        if len(v) == 2:
            paired.setdefault(lbl, {})[(opp, seed)] = sum(v)

    base = paired.get("RL identity (baseline)", {})
    rows = []
    for lbl, _ in cands:
        d = paired.get(lbl)
        if not d:
            continue
        vals = list(d.values())
        keys = [k for k in d if k in base]
        diffs = [d[k] - base[k] for k in keys]
        w = sum(1 for x in diffs if x > 0)
        l = sum(1 for x in diffs if x < 0)
        se = (statistics.pstdev(diffs) / len(diffs) ** 0.5) if len(diffs) > 1 else 0.0
        mean = statistics.mean(diffs) if diffs else 0.0
        wr = 100.0 * w / (w + l) if (w + l) else 50.0
        wse = 100.0 * (0.25 / (w + l)) ** 0.5 if (w + l) else 0.0
        rows.append((lbl, statistics.mean(vals), mean, se,
                     mean / se if se > 1e-9 else 0.0, wr, wse,
                     (wr - 50.0) / wse if wse > 1e-9 else 0.0, w, l))

    out = ["# RL evaluation", "",
           f"Generated {time.strftime('%Y-%m-%d %H:%M')}, checkpoint `{tag}`, "
           f"{n_seeds} seeds x {len(POOL)} opponents x both seats "
           f"(n={n_seeds * len(POOL)} paired per agent).", "",
           "Everything is measured against **RL identity**, the policy's own "
           "starting point, since that is what any gain has to be added to.", "",
           "| agent | paired margin | vs baseline | se | t | win rate | t | W-L |",
           "|---|---|---|---|---|---|---|---|"]
    for lbl, mm, dm, se, t, wr, wse, wt, w, l in rows:
        out.append(f"| {lbl} | {mm:+,.0f} | {dm:+,.0f} | {se:,.0f} | {t:.2f} | "
                   f"{wr:.1f}% | {wt:.2f} | {w}-{l} |")
    text = "\n".join(out) + "\n"
    os.makedirs(CKPT_DIR, exist_ok=True)
    open(os.path.join(CKPT_DIR, "RESULTS.md"), "w").write(text)
    print()
    print(text)


if __name__ == "__main__":
    main()
