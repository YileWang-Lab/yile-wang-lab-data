"""Tune the market layer against REAL LADDER OPPONENTS instead of the public
reference pool.

Why this exists: the same shipped change measured +670 against the 9 public
reference agents but only +178 across our 80 real ladder games
(planner/replay_counterfactual.py). The public pool systematically over-states
the layer, because those are predictable published tapes and the dump predictor
works best against exactly that. Optimising against the pool therefore optimises
the wrong distribution.

This sweeps variants against the 80 recorded opponents we actually faced, at the
real seeds, replaying their exact actions and swapping only our side.

TWO LIMITATIONS, both real:
  1. Opponents are traces, not policies. An adaptive opponent would have reacted
     to our change. HANDOFF section 10 measured farmer-agreement of 37-65% for
     the top of the ladder, so many of these are adaptive.
  2. 80 fixed opponents is a small, fixed sample and tuning hard against it will
     overfit. Treat a win here as necessary, not sufficient -- anything that
     looks good must still clear the public pool and the real engine before it
     ships.

Usage:
    /home/yilewang/kagg-env/bin/python -m planner.ladder_sweep
"""
import importlib.util
import json
import multiprocessing
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from planner.simulate import Simulator  # noqa: E402
from route.bake import bake  # noqa: E402

LOG_DIR = os.path.join(ROOT, "logs", "planner")
VARIANT_DIR = os.path.join(ROOT, "agents", "ladder")
os.makedirs(VARIANT_DIR, exist_ok=True)
EPISODES = "/tmp/claude-1818200050/-home-yilewang/12e9e33c-6cb5-4a53-939b-9c2b0d0b6776/scratchpad/v3_episodes2.json"

SHIPPED = {"_PREEMPT_MIN_FUTURE_QUANTITY": 0, "_PREEMPT_MAX_BATCH": 30,
           "INTERVENE": 1, "IV_DUMP_FRAC": 0.8, "IV_LEAD": 3, "IV_FERT": 1}
LIVE = {**SHIPPED, "IV_STRUCT": 1, "IV_DUMP_FRAC": 0.7, "IV_MIN_PRICE": 0.20}


def _v(name, **over):
    p = dict(LIVE)
    p.update(over)
    return (name, p)


DEFAULT_MAP = ["6c12s_4q_first_yarn", "6c12s_4q_second_yarn", "6c8s_3q",
               "10c4s_3q", "8c6s_3q"]
B0_MAP = ["6c12s_4q_second_yarn"] + DEFAULT_MAP[1:]

VARIANTS = [
    ("v3_old", dict(SHIPPED)),
    ("live_55612771", dict(LIVE)),
    # The bucket-0 tape swap. Against the 9-agent reference pool it is
    # +1,841 unconditional / +14,662 conditional (t=17.2, better in 81% of the
    # 452 games where it fires). But the real-engine gate's 6-opponent sample
    # put it at -18, so the open question is whether the edge is a property of
    # the reference pool rather than of the ladder. These 80 opponents are the
    # ones we actually faced.
    ("b0_second_yarn", {**LIVE, "TAPE_MAP": B0_MAP}),
    _v("lead2", IV_LEAD=2),
    _v("lead4", IV_LEAD=4),
    _v("lead5", IV_LEAD=5),
    _v("d60", IV_DUMP_FRAC=0.60),
    _v("d80", IV_DUMP_FRAC=0.80),
    _v("d90", IV_DUMP_FRAC=0.90),
    _v("mp00", IV_MIN_PRICE=0.0),
    _v("mp10", IV_MIN_PRICE=0.10),
    _v("mp30", IV_MIN_PRICE=0.30),
    _v("nostruct", IV_STRUCT=0),
    _v("squeeze8", IV_SQUEEZE=8),
    _v("repay", IV_REPAY=1),
    _v("d80_mp10", IV_DUMP_FRAC=0.80, IV_MIN_PRICE=0.10),
    _v("d60_mp30", IV_DUMP_FRAC=0.60, IV_MIN_PRICE=0.30),
]

_n = [0]


def _load(path):
    _n[0] += 1
    spec = importlib.util.spec_from_file_location(f"ls_{os.getpid()}_{_n[0]}", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return getattr(m, "_submission_entry", None) or m.agent


def make_trace_agent(steps, seat):
    acts = [steps[i][seat].get("action") for i in range(len(steps))]

    def agent(obs):
        i = int(obs.get("day", 0)) * 24 + int(obs.get("hour", 0)) + 1
        if i < len(acts) and isinstance(acts[i], dict):
            return acts[i]
        return {"farmer": ["PASS"], "hands": [], "market": []}
    return agent


def run_one(job):
    name, path, ep, our_seat = job
    rp = os.path.join(ROOT, "replays", f"episode-{ep}-replay.json")
    try:
        d = json.load(open(rp))
        cfg = d.get("configuration", {})
        steps = d["steps"]
        me = _load(path)
        opp = make_trace_agent(steps, 1 - our_seat)
        sim = Simulator.new_episode(
            configuration={k: v for k, v in cfg.items() if k in
                           ("boardSize", "startingMoney", "maxMarketOrdersPerTurn", "turnsPerDay",
                            "shedCapacity", "weedSpawnChance", "townShopUnlockInterval",
                            "townShopSellInterval", "townCenterSellInterval",
                            "farmHandCostMult", "episodeSteps", "marketParams")},
            seed=d["info"]["seed"])
        pair = [me, opp] if our_seat == 0 else [opp, me]
        m0, m1 = sim.run_episode(pair[0], pair[1])
        us, them = (m0, m1) if our_seat == 0 else (m1, m0)
        return (name, ep, us - them, None)
    except Exception:
        import traceback
        return (name, ep, 0.0, traceback.format_exc()[-200:])


def main():
    rows = json.load(open(EPISODES))
    games = [r for r in rows
             if os.path.exists(os.path.join(ROOT, "replays", f"episode-{r['episode']}-replay.json"))]
    print(f"{len(games)} real ladder games")

    paths = {}
    for name, params in VARIANTS:
        p = os.path.join(VARIANT_DIR, f"lad_{name}.py")
        bake(params, out=p, note=f"ladder sweep {name}")
        paths[name] = p

    jobs = [(name, paths[name], r["episode"], r["us_seat"])
            for name, _ in VARIANTS for r in games]
    print(f"{len(VARIANTS)} variants x {len(games)} games = {len(jobs):,} episodes")
    t0 = time.time()
    with multiprocessing.get_context("forkserver").Pool(14) as pool:
        res = pool.map(run_one, jobs, chunksize=4)
    print(f"elapsed {time.time()-t0:.0f}s")

    errs = [r for r in res if r[3]]
    if errs:
        print(f"{len(errs)} errors; first: {errs[0][3][-200:]}")

    by = {}
    for name, ep, margin, err in res:
        if not err:
            by.setdefault(name, {})[ep] = margin

    base = by.get("live_55612771", {})
    truth = {r["episode"]: r["margin"] for r in games}

    print()
    print("Scored against the 80 opponents we ACTUALLY faced (their recorded actions).")
    print(f"{'variant':<18} {'n':>4} {'mean margin':>13} {'record':>9} "
          f"{'vs live':>9} {'+/-se':>7} {'t':>6}")
    out = []
    for name, _ in VARIANTS:
        d = by.get(name, {})
        if not d:
            continue
        ms = list(d.values())
        wins = sum(1 for m in ms if m > 0)
        diffs = [d[e] - base[e] for e in d if e in base]
        dm = statistics.mean(diffs) if diffs else 0.0
        dsd = statistics.pstdev(diffs) if len(diffs) > 1 else 0.0
        dse = dsd / (len(diffs) ** 0.5) if diffs else 0.0
        out.append((name, len(ms), statistics.mean(ms), wins, dm, dse,
                    dm / dse if dse else 0.0))
    out.sort(key=lambda r: -r[4])
    for name, n, mm, wins, dm, dse, t in out:
        print(f"{name:<18} {n:>4} {mm:>13,.0f} {wins:>4}/{n:<4} {dm:>+9,.0f} {dse:>7,.0f} {t:>6.1f}")

    print()
    print("Reminder: opponents are TRACES. An adaptive opponent would have reacted,")
    print("and 80 fixed opponents is a small sample that can be overfit. A win here is")
    print("necessary but not sufficient -- it must still clear the pool and the real engine.")

    ts = time.strftime("%Y%m%d_%H%M%S")
    json.dump({k: v for k, v in by.items()},
              open(os.path.join(LOG_DIR, f"ladder_sweep_{ts}.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
