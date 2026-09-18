"""Run the TAPE for the opening, then hand over to our scheduler.

WHY THIS IS NOT THE THING THAT FAILED SEVEN TIMES TODAY. Every previous attempt
LEARNED something from the tape -- actions, decision conditions, per-turn ops,
targets -- and every one died of distribution shift: the rules were fitted where
the tape lives and applied where we live. This learns nothing. For the first N
days it simply IS the tape, executing its own action list against its own
resulting state, so alignment is exact by construction rather than approximate
by fitting.

WHY THE OPENING SPECIFICALLY. Section 34 measured the shadow price of capital:
a dollar on days 0-9 is worth 2.00 +- 0.19 at the buzzer, a dollar after day 10
worth exactly 1.00 +- 0.00. And section 26 measured where the farms diverge --
the tape holds 23 producing tiles on day 3 and 68 on day 12 against our 8 and
37, from the same $3,000. The opening is both where the value is and where the
two agents are closest, which is the only window in which "just do what the tape
does" can even be attempted.

THE HANDOFF IS THE WHOLE RISK. Section 4 established three times over that the
tape cannot be edited -- but this does not edit it, it truncates it. What has
never been measured is whether our scheduler can pick up a board the tape built:
it inherits ~23 producing tiles, a crew, and a shed it did not plan, and its own
state (S) has never seen the episode. If it cannot adopt that board the handoff
will show up as a cliff at exactly day N, which is a readable failure.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _HERE]
sys.path.insert(0, ROOT)

TAPE = "opponents/kaggriculture-multi-route-farming-agent.py"
_n = [0]


def _load(path, genome=None):
    import importlib.util
    _n[0] += 1
    spec = importlib.util.spec_from_file_location(
        f"pf_{os.getpid()}_{_n[0]}", os.path.join(ROOT, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    if genome is not None:
        m.configure(genome)
    return m


def make(handoff_day, genome, base="dynamic/agent4.py"):
    """An agent that is the tape until `handoff_day`, then the scheduler.

    `handoff_day = 0` is the scheduler alone and `handoff_day >= 30` is the tape
    alone, so both ends of the sweep are identity controls rather than separate
    code paths.
    """
    tape_m = _load(TAPE)
    tape = getattr(tape_m, "_submission_entry", None) or tape_m.agent
    sched_m = _load(base, genome)
    sched = sched_m.agent

    def agent(obs, config=None):
        o = obs if isinstance(obs, dict) else dict(obs)
        day = int(o.get("day", 0) or 0)
        if day < handoff_day:
            return tape(o)
        return sched(o)
    return agent


_G = {}


def _init(g):
    _G["g"] = g


def play(job):
    """Module level so it pickles: a nested function cannot cross a Pool."""
    d, opp, seed, seat = job
    try:
        from planner.simulate import Simulator
        me = make(d, _G["g"])
        om = _load(os.path.join("opponents", opp + ".py"))
        op = getattr(om, "_submission_entry", None) or om.agent
        pair = [me, op] if seat == 0 else [op, me]
        sim = Simulator.new_episode(configuration={"episodeSteps": 720},
                                    seed=seed)
        m0, m1 = sim.run_episode(pair[0], pair[1])
        us, them = (m0, m1) if seat == 0 else (m1, m0)
        return (d, opp, seed, us - them, None)
    except Exception:
        import traceback
        return (d, opp, seed, 0.0, traceback.format_exc()[-200:])


def main():
    import multiprocessing as mp
    import statistics
    from route.search import to_params

    n = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    g = to_params(dict(json.load(open(os.path.join(
        ROOT, "dynamic", "best_genome3.json")))["genome"]))
    g["OPP_MODEL"] = 1
    g["SHED_PANIC_FRACTION"] = 0.40

    OPPS = ["v111-8c4s-economic-core-premium-lead", "kaggriculture-3000-socre",
            "kaggriculture-rank-your-agent", "strong-barnyard-economist"]
    DAYS = [0, 3, 6, 9, 12, 15, 30]

    import random
    rng = random.Random(24680)
    seeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(n)]
    jobs = [(d, o, s, st) for d in DAYS for o in OPPS
            for s in seeds for st in (0, 1)]
    print(f"{len(jobs):,} games, handoff days {DAYS}", flush=True)
    with mp.get_context("forkserver").Pool(workers, initializer=_init,
                                           initargs=(g,)) as pool:
        res = pool.map(play, jobs, chunksize=2)
    errs = [e for *_x, e in res if e]
    if errs:
        print(f"{len(errs)} errors; first:\n{errs[0]}")
    per = {}
    for d, opp, seed, m, e in res:
        if e:
            continue
        per.setdefault((d, opp, seed), []).append(m)
    paired = {}
    for (d, opp, seed), v in per.items():
        if len(v) == 2:
            paired.setdefault(d, []).append(sum(v))
    print()
    print(f"{'handoff':>9}{'paired margin':>15}{'se':>8}   "
          f"(day 0 = scheduler alone, day 30 = the tape alone)")
    for d in DAYS:
        v = paired.get(d)
        if not v:
            continue
        se = statistics.pstdev(v) / len(v) ** 0.5 if len(v) > 1 else 0.0
        print(f"{('day ' + str(d)):>9}{statistics.mean(v):>+15,.0f}{se:>8,.0f}")


if __name__ == "__main__":
    main()
