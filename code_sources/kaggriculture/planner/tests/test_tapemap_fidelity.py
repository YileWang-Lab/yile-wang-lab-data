"""Why does the simulator say the bucket-0 tape swap is worth +1,966 while the
real engine says -18?

The simulator is verified bit-exact on 56 recorded replays and on 18 live
agent-vs-agent games, so a disagreement this large (5 sigma) is not sampling
noise -- something about THIS change behaves differently on the two paths, and
whichever side is wrong has to be found before anything ships.

Runs the identical matchup on both engines, seed by seed, and reports the first
seed where they disagree.

Usage:
    /home/yilewang/kagg-env/bin/python -m planner.tests.test_tapemap_fidelity
"""
import importlib.util
import multiprocessing
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from planner.simulate import Simulator  # noqa: E402
from route.bake import bake  # noqa: E402

LIVE = {"_PREEMPT_MIN_FUTURE_QUANTITY": 0, "_PREEMPT_MAX_BATCH": 30,
        "INTERVENE": 1, "IV_DUMP_FRAC": 0.7, "IV_LEAD": 3, "IV_FERT": 1,
        "IV_STRUCT": 1, "IV_MIN_PRICE": 0.20}
DEFAULT_MAP = ["6c12s_4q_first_yarn", "6c12s_4q_second_yarn", "6c8s_3q",
               "10c4s_3q", "8c6s_3q"]
B0_MAP = ["6c12s_4q_second_yarn"] + DEFAULT_MAP[1:]

_n = [0]


def _load(path):
    _n[0] += 1
    spec = importlib.util.spec_from_file_location(f"tf_{os.getpid()}_{_n[0]}", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return getattr(m, "_submission_entry", None) or m.agent


def one(job):
    label, path, opp_name, seed, seat = job
    opp_path = os.path.join(ROOT, "opponents", f"{opp_name}.py")
    try:
        sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
        a, b = _load(path), _load(opp_path)
        pair = [a, b] if seat == 0 else [b, a]
        s0, s1 = sim.run_episode(pair[0], pair[1])
        sim_us = s0 if seat == 0 else s1

        from kaggle_environments import make
        env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": seed}, debug=False)
        a2, b2 = _load(path), _load(opp_path)
        pair2 = [a2, b2] if seat == 0 else [b2, a2]
        env.run(pair2)
        f = env.steps[-1]
        real_us = f[seat].observation["farms"][seat]["money"]
        return (label, seed, seat, sim_us, real_us, None)
    except Exception:
        import traceback
        return (label, seed, seat, 0, 0, traceback.format_exc()[-300:])


def main():
    live_p = os.path.join(ROOT, "agents", "tf_live.py")
    b0_p = os.path.join(ROOT, "agents", "tf_b0.py")
    bake(LIVE, out=live_p, note="fidelity: live default map")
    bake({**LIVE, "TAPE_MAP": B0_MAP}, out=b0_p, note="fidelity: bucket-0 map")

    import random
    rng = random.Random(4242)
    seeds = [rng.randrange(10**6, 2**31 - 1) for _ in range(24)]
    opp = "v111-8c4s-economic-core-premium-lead"

    jobs = []
    for s in seeds:
        jobs.append(("live", live_p, opp, s, 0))
        jobs.append(("b0", b0_p, opp, s, 0))

    with multiprocessing.get_context("forkserver").Pool(20) as pool:
        res = pool.map(one, jobs)

    by = {}
    for label, seed, seat, sim_us, real_us, err in res:
        if err:
            print(f"ERROR {label} seed {seed}: {err[-200:]}")
            continue
        by.setdefault(seed, {})[label] = (sim_us, real_us)

    print(f"{'seed':>12} {'variant':>7} {'sim':>10} {'real':>10} {'agree':>7}   "
          f"{'sim delta':>10} {'real delta':>11}")
    n_mismatch = 0
    n_effect_sim = 0
    n_effect_real = 0
    for seed in seeds:
        d = by.get(seed, {})
        if "live" not in d or "b0" not in d:
            continue
        for lab in ("live", "b0"):
            sm, rl = d[lab]
            agree = abs(sm - rl) < 0.01
            if not agree:
                n_mismatch += 1
            print(f"{seed:>12} {lab:>7} {sm:>10,.0f} {rl:>10,.0f} {'OK' if agree else 'DIFF':>7}", end="")
            if lab == "b0":
                sd = d["b0"][0] - d["live"][0]
                rd = d["b0"][1] - d["live"][1]
                if abs(sd) > 1:
                    n_effect_sim += 1
                if abs(rd) > 1:
                    n_effect_real += 1
                print(f"   {sd:>+10,.0f} {rd:>+11,.0f}")
            else:
                print()
    print()
    print(f"engine mismatches: {n_mismatch}/{2*len(seeds)}")
    print(f"seeds where the map change altered play -- simulator: {n_effect_sim}, "
          f"real engine: {n_effect_real}  (of {len(seeds)})")
    if n_mismatch == 0 and n_effect_sim != n_effect_real:
        print("\nBoth engines reproduce each agent exactly, but the change bites on a")
        print("DIFFERENT set of seeds. That points at the selection rule's inputs, not")
        print("at the simulator's physics.")


if __name__ == "__main__":
    main()
