"""Solve the endgame by rollout search on OUR OWN states, not by imitation.

WHY NOT LEARN IT FROM THE TOP LADDER. Measured: the state-distribution distance
between us and the eleven strongest teams we hold replays for does not narrow
toward the buzzer, it WIDENS -- 0.40 over days 6-11, 1.33 over days 18-23, where
they work ~74 producing tiles and we work ~40. The endgame is where we differ
most, so it is the worst place to imitate them.

WHY ROLLOUT SEARCH WORKS HERE WHEN IT DOES NOT EARLIER. A rollout to the buzzer
costs 0.59 s from day 3 but only ~0.1 s from day 25, because it is five days
instead of twenty-seven. That is what makes exhaustive evaluation affordable
late and not early -- and the states being searched are the ones our own agent
actually reaches, so there is no distribution to transfer across.

WHAT IS SEARCHED. Terminal policy only: when to stop planting, when to start
liquidating, and how hard to dump. Those are the decisions whose consequences
fit inside the remaining horizon, so a rollout measures them almost exactly
rather than estimating them.

PAIRED, and against the agent's own current setting: every variant plays from
the SAME clone with the same opponent and seed, so the difference is the policy
and nothing else.
"""
import json
import multiprocessing as mp
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _HERE]
sys.path.insert(0, ROOT)

from route.search import to_params  # noqa: E402

OPPS = ["kaggriculture-multi-route-farming-agent",
        "v111-8c4s-economic-core-premium-lead",
        "kaggriculture-3000-socre",
        "strong-barnyard-economist"]
_n = [0]
_G = {}

# Terminal knobs, and why each is a candidate rather than a guess:
#   TERMINAL_STEP        reward is cash on hand, so anything unsold at the
#                        buzzer is worth zero -- but liquidating too early
#                        dumps into a book that has not been drained yet.
#   SHED_PANIC_FRACTION  governs 79% of all units we offer; late in the season
#                        there is no production left to protect, so the right
#                        value there need not be the right value at day 10.
#   PLANT_MISS_TOLERANCE late plantings compete for the crew with harvesting.
#   RAMP_START_DAY       when the sell reserve starts winding down.
VARIANTS = [
    ("current", {}),
    ("terminal 660", {"TERMINAL_STEP": 660}),
    ("terminal 672", {"TERMINAL_STEP": 672}),
    ("terminal 700", {"TERMINAL_STEP": 700}),
    ("terminal 712", {"TERMINAL_STEP": 712}),
    ("panic 0.15 late", {"SHED_PANIC_FRACTION": 0.15}),
    ("panic 0.70 late", {"SHED_PANIC_FRACTION": 0.70}),
    ("ramp from 24", {"RAMP_START_DAY": 24}),
    ("ramp from 28", {"RAMP_START_DAY": 28}),
    ("no late plant", {"PLANT_MISS_TOLERANCE": 0}),
    ("term 672 + panic .70", {"TERMINAL_STEP": 672, "SHED_PANIC_FRACTION": 0.70}),
    ("term 700 + ramp 24", {"TERMINAL_STEP": 700, "RAMP_START_DAY": 24}),
]


def _genome():
    g = json.load(open(os.path.join(ROOT, "dynamic", "best_genome3.json")))["genome"]
    p = to_params(dict(g))
    p["OPP_MODEL"] = 1
    p["SHED_PANIC_FRACTION"] = 0.40
    return p


def _init(g):
    _G["g"] = g


def _mk(path, genome=None):
    import importlib.util
    _n[0] += 1
    spec = importlib.util.spec_from_file_location(
        f"eg_{os.getpid()}_{_n[0]}", os.path.join(ROOT, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    if genome is not None:
        m.configure(genome)
        return m.agent
    return getattr(m, "_submission_entry", None) or m.agent


def probe(job):
    """Play to `switch_day` under the current policy, then branch."""
    seed, opp, switch_day, label, overrides = job
    try:
        from planner.simulate import Simulator, _agent_caller
        me = _mk("dynamic/agent4.py", _G["g"])
        op = _mk(os.path.join("opponents", opp + ".py"))
        sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
        c0, c1 = _agent_caller(me), _agent_caller(op)
        while sim.step < switch_day * 24:
            sim.step_actions(c0(sim.observation_for(0), sim.cfg),
                             c1(sim.observation_for(1), sim.cfg))
        branch = sim.clone()
        g2 = dict(_G["g"])
        g2.update(overrides)
        # Fresh instances: the scheduler keeps per-episode state, so reusing one
        # would carry the pre-switch plan into the branch.
        me2 = _mk("dynamic/agent4.py", g2)
        op2 = _mk(os.path.join("opponents", opp + ".py"))
        d0, d1 = _agent_caller(me2), _agent_caller(op2)
        while branch.step < 719:
            branch.step_actions(d0(branch.observation_for(0), branch.cfg),
                                d1(branch.observation_for(1), branch.cfg))
        us, them = branch.farms[0]["money"], branch.farms[1]["money"]
        return (label, seed, opp, us - them, None)
    except Exception:
        import traceback
        return (label, seed, opp, 0.0, traceback.format_exc()[-180:])


def main():
    n_seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 16
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 24
    switch_day = int(sys.argv[3]) if len(sys.argv) > 3 else 22
    import random
    rng = random.Random(24680)
    seeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(n_seeds)]
    jobs = [(s, o, switch_day, lbl, ov) for lbl, ov in VARIANTS
            for o in OPPS for s in seeds]
    print(f"{len(jobs):,} rollouts, branching at day {switch_day} "
          f"({len(VARIANTS)} terminal policies)", flush=True)
    with mp.get_context("forkserver").Pool(workers, initializer=_init,
                                           initargs=(_genome(),)) as pool:
        res = pool.map(probe, jobs, chunksize=2)
    errs = [e for *_x, e in res if e]
    if errs:
        print(f"{len(errs)} errors; first:\n{errs[0]}", flush=True)

    by = {}
    for lbl, seed, opp, margin, e in res:
        if e:
            continue
        by.setdefault(lbl, {})[(seed, opp)] = margin
    base = by.get("current", {})
    print()
    print(f"{'terminal policy':<24}{'margin':>12}{'vs current':>13}{'se':>8}{'t':>7}"
          f"{'wins':>9}")
    rows = []
    for lbl, _ov in VARIANTS:
        d = by.get(lbl)
        if not d:
            continue
        diffs = [d[k] - base[k] for k in d if k in base]
        m = statistics.mean(diffs) if diffs else 0.0
        se = (statistics.pstdev(diffs) / len(diffs) ** 0.5) if len(diffs) > 1 else 0.0
        w = sum(1 for x in diffs if x > 0)
        rows.append((m / se if se > 1e-9 else 0.0, lbl,
                     statistics.mean(d.values()), m, se, w, len(diffs)))
    for t, lbl, mm, m, se, w, n in sorted(rows, reverse=True):
        flag = "  <<<" if t >= 2.0 else ""
        print(f"{lbl:<24}{mm:>12,.0f}{m:>+13,.0f}{se:>8,.0f}{t:>7.2f}"
              f"{w:>5}/{n:<3}{flag}")


if __name__ == "__main__":
    main()
