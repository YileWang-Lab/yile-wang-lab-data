"""Measure the shadow price of capital, lambda(t) = d NAV_T / d C_t.

WHY THIS EXISTS. MODEL.md section 15 states the defect exactly: the scheduler
solves a per-decision argmax while the game is sequential with a binding cash
constraint,

    V_t(C, L) = max_a ( ENPV(a) + V_{t+1}(C - c_a, L + l_a) )

and no per-asset ENPV contains the second term. Its physical meaning is the
compounding value of cash: a dollar on day 3 buys a tile that funds two more on
day 8, and a myopic allocator prices that dollar at face value.

THE CLOSED FORM IS A GUESS; THIS IS A MEASUREMENT. The usual patch is an assumed
curve, lambda(t) = (1+r)^(T_snowball - t), with r and T_snowball picked by hand.
Both are avoidable. Clone the live engine at day t, inject a marginal amount of
cash, let the SAME myopic agent play both branches to the buzzer, and difference
the final banks:

    lambda(t) ~ ( NAV_T(C_t + delta) - NAV_T(C_t) ) / delta

That is the derivative of V_{t+1} with respect to cash, sampled directly off the
real engine. No assumed rate, no assumed snowball horizon -- if the curve turns
out flat, the whole premise is wrong and we learn that instead of encoding it.

WHY IT IS OFFLINE. A rollout from day 3 to the buzzer costs 0.59 s against an
`actTimeout` of 1 s per turn, so one branch barely fits and five do not. Measure
the curve here, ship the fitted analytic form.

PAIRED, always. Both branches run from the same clone with the same opponent and
the same seed, so the difference is the injection and nothing else.
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

SEASON_DAYS = 30
OPPS = ["kaggriculture-multi-route-farming-agent",
        "v111-8c4s-economic-core-premium-lead",
        "kaggriculture-3000-socre"]
_n = [0]
_G = {}


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
        f"sp_{os.getpid()}_{_n[0]}", os.path.join(ROOT, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    if genome is not None:
        m.configure(genome)
        return m.agent
    return getattr(m, "_submission_entry", None) or m.agent


def _finish(sim, tag):
    """Play a cloned state to the buzzer with fresh agent instances.

    Fresh instances matter: the scheduler keeps per-episode state in S, so
    reusing one across two branches would leak the first branch's plan into the
    second and the difference would not be the injection.
    """
    from planner.simulate import _agent_caller
    me = _mk("dynamic/agent4.py", _G["g"])
    op = _mk(os.path.join("opponents", tag + ".py"))
    c0, c1 = _agent_caller(me), _agent_caller(op)
    while sim.step < 719:
        sim.step_actions(c0(sim.observation_for(0), sim.cfg),
                         c1(sim.observation_for(1), sim.cfg))
    return sim.farms[0]["money"]


def probe(job):
    """One (seed, opponent, day) sample of lambda."""
    seed, opp, day, delta = job
    try:
        from planner.simulate import Simulator, _agent_caller
        me = _mk("dynamic/agent4.py", _G["g"])
        op = _mk(os.path.join("opponents", opp + ".py"))
        sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
        c0, c1 = _agent_caller(me), _agent_caller(op)
        while sim.step < day * 24:
            sim.step_actions(c0(sim.observation_for(0), sim.cfg),
                             c1(sim.observation_for(1), sim.cfg))
        cash_at_t = sim.farms[0]["money"]
        base = _finish(sim.clone(), opp)
        bumped = sim.clone()
        bumped.farms[0]["money"] += delta
        with_cash = _finish(bumped, opp)
        return (day, (with_cash - base) / float(delta), cash_at_t, None)
    except Exception:
        import traceback
        return (day, None, 0.0, traceback.format_exc()[-200:])


def main():
    n_seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    delta = float(sys.argv[3]) if len(sys.argv) > 3 else 2000.0
    days = [int(x) for x in (sys.argv[4].split(",") if len(sys.argv) > 4
                             else range(0, 28, 2))]
    import random
    rng = random.Random(90210)
    seeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(n_seeds)]
    jobs = [(s, o, d, delta) for s in seeds for o in OPPS for d in days]
    print(f"{len(jobs):,} paired rollouts, delta=${delta:,.0f}", flush=True)
    with mp.get_context("forkserver").Pool(workers, initializer=_init,
                                           initargs=(_genome(),)) as pool:
        res = pool.map(probe, jobs, chunksize=2)
    errs = [e for *_x, e in res if e]
    if errs:
        print(f"{len(errs)} errors; first:\n{errs[0]}", flush=True)

    by = {}
    cash = {}
    for day, lam, c, e in res:
        if e or lam is None:
            continue
        by.setdefault(day, []).append(lam)
        cash.setdefault(day, []).append(c)
    print()
    print(f"{'day':>5}{'lambda':>10}{'se':>8}{'n':>5}{'cash at t':>12}   "
          f"marginal $1 at day t is worth this many $ at the buzzer")
    out = {}
    for d in sorted(by):
        v = by[d]
        m = statistics.mean(v)
        se = statistics.pstdev(v) / len(v) ** 0.5 if len(v) > 1 else 0.0
        out[d] = {"lambda": m, "se": se, "n": len(v),
                  "cash": statistics.mean(cash[d])}
        bar = "#" * max(0, min(40, int(round(m * 8))))
        print(f"{d:>5}{m:>10.2f}{se:>8.2f}{len(v):>5}"
              f"{statistics.mean(cash[d]):>12,.0f}   {bar}")
    json.dump(out, open(os.path.join(ROOT, "logs", "shadow_price.json"), "w"),
              indent=1)
    print(f"\nwrote logs/shadow_price.json")


if __name__ == "__main__":
    main()
