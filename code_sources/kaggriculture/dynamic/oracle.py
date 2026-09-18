"""The upper bound on distilling the tape: give our scheduler its ACTUAL decisions.

Every distillation attempt so far fitted an approximation of the tape's daily
choices and then played it:

    section 21   behavioural cloning of raw actions      92.8% accurate -> $288
    section 32   linear fit of decision conditions       89-100%  -> -46,972
    section 33   depth-3 trees from eleven top players   85-97%   -> -55,671

Each failure could in principle be blamed on the fit. This removes that excuse.
Instead of a model of the tape's decisions, feed our scheduler the tape's REAL
decisions, read off a live game of the tape on the SAME seed against the SAME
opponent -- a perfect distillation, accuracy 100% by construction.

If the oracle still loses, no tree, network or rule list over daily decisions
can succeed, because they are all bounded above by it. That turns "our fit was
not good enough" into a measured question instead of an open one.

WHAT IS TRANSFERRED, and what deliberately is not: the daily decisions the
policy API exposes -- which crop to favour, how many hands, whether to buy land,
which animal. NOT the per-turn tile actions, because those are the tape's own
719-step schedule and section 4 established three times over that they cannot be
moved onto another agent. The question here is precisely whether the DECISIONS
carry the tape's advantage or whether its EXECUTION does.
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

TAPE = "opponents/kaggriculture-multi-route-farming-agent.py"
OPPS = ["v111-8c4s-economic-core-premium-lead",
        "kaggriculture-3000-socre",
        "kaggriculture-rank-your-agent",
        "strong-barnyard-economist"]
_n = [0]
_G = {}


def _mk(path, genome=None):
    import importlib.util
    _n[0] += 1
    spec = importlib.util.spec_from_file_location(
        f"or_{os.getpid()}_{_n[0]}", os.path.join(ROOT, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    if genome is not None:
        m.configure(genome)
        return m
    return m


def _init(g):
    _G["g"] = g


def record_tape(seed, opp):
    """Play the tape and record what it decided on each day."""
    from planner.simulate import Simulator, _agent_caller
    tm = _mk(TAPE)
    om = _mk(os.path.join("opponents", opp + ".py"))
    tape = getattr(tm, "_submission_entry", None) or tm.agent
    other = getattr(om, "_submission_entry", None) or om.agent
    sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
    c0, c1 = _agent_caller(tape), _agent_caller(other)
    per_day, cur = {}, None
    while sim.step < 719:
        o = sim.observation_for(0)
        day, hour = o["day"], o["hour"]
        if hour == 0:
            cur = {"plant": {}, "hire": 0, "land": 0, "animal": None,
                   "hands": len(o["farms"][0].get("hands") or [])}
            per_day[day] = cur
        a = c0(o, sim.cfg)
        if isinstance(a, dict) and cur is not None:
            for u in [a.get("farmer")] + list(a.get("hands") or []):
                if u and u[0] == "PLANT" and len(u) > 1:
                    cur["plant"][u[1]] = cur["plant"].get(u[1], 0) + 1
                if u and u[0] == "PLACE" and len(u) > 1:
                    cur["animal"] = u[1]
            for m in a.get("market") or []:
                if not m:
                    continue
                if m[0] == "HIRE":
                    cur["hire"] += 1
                elif m[0] == "BUY_LAND":
                    cur["land"] = 1
        sim.step_actions(a, c1(sim.observation_for(1), sim.cfg))
    return per_day


class OraclePolicy:
    """Replays the tape's real daily decisions into our scheduler."""

    WHITEBOX = True

    def __init__(self, per_day, blend=1.0):
        from dynamic.rl import policy_api as PA
        self.PA = PA
        self.d = per_day
        self.blend = float(blend)
        self.traj = {"daily": [], "sell": []}
        self.day = 0

    def reset(self):
        self.traj = {"daily": [], "sell": []}

    def daily(self, obs_vec):
        PA = self.PA
        rec = self.d.get(self.day) or {}
        self.day += 1
        pref = {c: 1.0 for c in PA.CROPS}
        pl = rec.get("plant") or {}
        if pl:
            top = max(pl, key=pl.get)
            if top in pref:
                pref[top] = 1.0 + self.blend
        delta = max(PA.CREW_DELTAS[0],
                    min(PA.CREW_DELTAS[-1], rec.get("hire", 0) - 3))
        a = rec.get("animal")
        return PA.Decision(crop_pref=pref, crew_delta=int(delta),
                           buy_land=bool(rec.get("land", 0)),
                           animal=a if a in PA.ANIMAL_CHOICES else None)

    def sell(self, market_vec, holdings):
        return {p: 1.0 for p in self.PA.PRODUCTS}


def play(job):
    label, mode, opp, seed, seat = job
    try:
        from planner.simulate import Simulator
        if mode == "tape":
            m = _mk(TAPE)
            me = getattr(m, "_submission_entry", None) or m.agent
        else:
            m = _mk("dynamic/rl/agent_rl.py", _G["g"])
            me = m.agent
            if mode.startswith("oracle"):
                per_day = record_tape(seed, opp)
                m.set_policy(OraclePolicy(per_day,
                                          float(mode.split(":")[1])))
            else:
                from dynamic.rl.linear_policy import (
                    LinearDailyNet, LinearSellNet, DEFAULT_INTERACTIONS,
                    NumpyWhiteBox, whitebox_weights)
                d, s = LinearDailyNet(), LinearSellNet(
                    interactions=DEFAULT_INTERACTIONS)
                dw, sw = whitebox_weights(d, s)
                m.set_policy(NumpyWhiteBox(dw, sw, d.names, s.names, s.idx,
                                           explore=False))
        om = _mk(os.path.join("opponents", opp + ".py"))
        op = getattr(om, "_submission_entry", None) or om.agent
        pair = [me, op] if seat == 0 else [op, me]
        sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
        m0, m1 = sim.run_episode(pair[0], pair[1])
        us, them = (m0, m1) if seat == 0 else (m1, m0)
        return (label, opp, seed, us - them, None)
    except Exception:
        import traceback
        return (label, opp, seed, 0.0, traceback.format_exc()[-200:])


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 16
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    g = to_params(dict(json.load(open(os.path.join(
        ROOT, "dynamic", "best_genome3.json")))["genome"]))
    g["OPP_MODEL"] = 1
    g["SHED_PANIC_FRACTION"] = 0.40
    import random
    rng = random.Random(97531)
    seeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(n)]
    cands = [("scheduler alone", "plain"),
             ("+ tape's REAL decisions", "oracle:1.0"),
             ("+ tape's REAL, blend 3", "oracle:3.0"),
             ("the tape itself", "tape")]
    jobs = [(l, m, o, s, st) for l, m in cands for o in OPPS
            for s in seeds for st in (0, 1)]
    print(f"{len(jobs):,} games", flush=True)
    with mp.get_context("forkserver").Pool(workers, initializer=_init,
                                           initargs=(g,)) as pool:
        res = pool.map(play, jobs, chunksize=2)
    errs = [e for *_x, e in res if e]
    if errs:
        print(f"{len(errs)} errors; first:\n{errs[0]}")
    per = {}
    for lbl, opp, seed, m, e in res:
        if e:
            continue
        per.setdefault((lbl, opp, seed), []).append(m)
    paired = {}
    for (lbl, opp, seed), v in per.items():
        if len(v) == 2:
            paired.setdefault(lbl, []).append(sum(v))
    base = statistics.mean(paired.get("scheduler alone") or [0])
    print()
    print(f"{'agent':<26}{'paired margin':>15}{'vs scheduler':>14}{'se':>8}")
    for lbl, _m in cands:
        v = paired.get(lbl)
        if not v:
            continue
        mm = statistics.mean(v)
        se = statistics.pstdev(v) / len(v) ** 0.5 if len(v) > 1 else 0.0
        print(f"{lbl:<26}{mm:>+15,.0f}{mm - base:>+14,.0f}{se:>8,.0f}")


if __name__ == "__main__":
    main()
