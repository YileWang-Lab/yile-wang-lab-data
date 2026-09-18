"""Head to head: the decision tree against every build we have submitted.

Not a pool average -- the direct question. Both seats, same seeds, paired.
"""
import json, os, statistics, sys, multiprocessing as mp
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _HERE]
sys.path.insert(0, ROOT)
from route.search import to_params                       # noqa: E402

RIVALS = [("SHIPPED 55614625", "submission/main.py"),
          ("BEST_b0_tapeswap", "deliver/BEST_b0_tapeswap.py"),
          ("ALT_struct", "deliver/ALT_struct.py"),
          ("kawa tape", "opponents/kaggriculture-multi-route-farming-agent.py"),
          ("v111", "opponents/v111-8c4s-economic-core-premium-lead.py")]
OURS = [("scheduler alone", "identity"),
        ("scheduler + market", "agents/sched_overlay.py")]
_W, _n = {}, [0]


def _init(g): _W["g"] = g


def _load(path):
    import importlib.util
    _n[0] += 1
    sp = importlib.util.spec_from_file_location(f"h_{os.getpid()}_{_n[0]}",
                                                os.path.join(ROOT, path))
    m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m)
    return getattr(m, "_submission_entry", None) or m.agent


def _mine(kind):
    import importlib.util
    if kind.endswith(".py"):
        return _load(kind)
    _n[0] += 1
    sp = importlib.util.spec_from_file_location(
        f"m_{os.getpid()}_{_n[0]}", os.path.join(ROOT, "dynamic", "rl", "agent_rl.py"))
    m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m)
    m.configure(_W["g"])
    if kind.startswith("tree"):
        from dynamic.tree.policy import TreePolicy
        m.set_policy(TreePolicy(blend=float(kind.split(":")[1])))
    else:
        from dynamic.rl.linear_policy import (LinearDailyNet, LinearSellNet,
                                              DEFAULT_INTERACTIONS, NumpyWhiteBox,
                                              whitebox_weights)
        d, s = LinearDailyNet(), LinearSellNet(interactions=DEFAULT_INTERACTIONS)
        dw, sw = whitebox_weights(d, s)
        m.set_policy(NumpyWhiteBox(dw, sw, d.names, s.names, s.idx, explore=False))
    return m.agent


def play(job):
    mine_lbl, mine_kind, rival_lbl, rival_path, seed, seat = job
    try:
        from planner.simulate import Simulator
        me, op = _mine(mine_kind), _load(rival_path)
        pair = [me, op] if seat == 0 else [op, me]
        sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
        m0, m1 = sim.run_episode(pair[0], pair[1])
        us, them = (m0, m1) if seat == 0 else (m1, m0)
        return (mine_lbl, rival_lbl, seed, us - them, None)
    except Exception:
        import traceback
        return (mine_lbl, rival_lbl, seed, 0.0, traceback.format_exc()[-160:])


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    g = to_params(dict(json.load(open(os.path.join(
        ROOT, "dynamic", "best_genome3.json")))["genome"]))
    g["OPP_MODEL"] = 1; g["SHED_PANIC_FRACTION"] = 0.40
    import random
    rng = random.Random(606060)
    seeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(n)]
    jobs = [(ml, mk, rl, rp, s, st) for ml, mk in OURS for rl, rp in RIVALS
            for s in seeds for st in (0, 1)]
    print(f"{len(jobs):,} games  ({len(OURS)} of ours x {len(RIVALS)} rivals x "
          f"{n} seeds x 2 seats)", flush=True)
    with mp.get_context("forkserver").Pool(workers, initializer=_init,
                                           initargs=(g,)) as pool:
        res = pool.map(play, jobs, chunksize=2)
    errs = [e for *_x, e in res if e]
    if errs:
        print(f"{len(errs)} errors; first:\n{errs[0]}")
    per = {}
    for ml, rl, seed, m, e in res:
        if e: continue
        per.setdefault((ml, rl, seed), []).append(m)
    paired = {}
    for (ml, rl, seed), v in per.items():
        if len(v) == 2:
            paired.setdefault((ml, rl), []).append(sum(v))
    print()
    print(f"{'our agent':<18}{'rival':<20}{'paired margin':>15}{'se':>8}{'我们赢':>9}")
    for ml, _mk in OURS:
        for rl, _rp in RIVALS:
            v = paired.get((ml, rl))
            if not v: continue
            m = statistics.mean(v)
            se = statistics.pstdev(v) / len(v) ** 0.5 if len(v) > 1 else 0.0
            w = sum(1 for x in v if x > 0)
            print(f"{ml:<18}{rl:<20}{m:>+15,.0f}{se:>8,.0f}{w:>5}/{len(v)}")
        print()


if __name__ == "__main__":
    main()
