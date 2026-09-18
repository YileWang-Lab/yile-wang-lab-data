"""Does the distilled white-box policy actually PLAY better than the scheduler?

Accuracy is not performance. Section 21's behavioural cloning reached 92.8%
action accuracy and banked $288, so a held-out agreement number -- however it is
computed -- settles nothing on its own. This plays it.
"""
import json, os, statistics, sys, multiprocessing as mp
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _HERE]
sys.path.insert(0, ROOT)
from route.search import to_params                       # noqa: E402

POOL = ["kaggriculture-multi-route-farming-agent", "v111-8c4s-economic-core-premium-lead",
        "kaggriculture-frontier-the-soil-remembers-rain", "kaggriculture-3000-socre",
        "kaggriculture-rank-your-agent", "strong-barnyard-economist"]
_W, _n = {}, [0]


def _genome():
    g = json.load(open(os.path.join(ROOT, "dynamic", "best_genome3.json")))["genome"]
    p = to_params(dict(g)); p["OPP_MODEL"] = 1; p["SHED_PANIC_FRACTION"] = 0.40
    return p


def _init(genome, ck):
    _W["genome"], _W["ck"] = genome, ck


class TorchLinear:
    """Policy wrapper over the two linear nets. WHITEBOX so agent_rl feeds the
    122 named features to the daily head."""
    WHITEBOX = True

    def __init__(self, dnet, snet, explore=False):
        import torch
        self.t, self.d, self.s, self.explore = torch, dnet.eval(), snet.eval(), explore
        self.traj = {"daily": [], "sell": []}

    def reset(self):
        self.traj = {"daily": [], "sell": []}

    def daily(self, v):
        from dynamic.rl import policy_api as PA
        with self.t.no_grad():
            lg, _ = self.d(self.t.tensor(v, dtype=self.t.float32))
        w = self.t.softmax(lg["crop_pref"], -1)
        pick = lambda k: int(lg[k].argmax())          # noqa: E731
        return PA.Decision(
            crop_pref={c: float(w[i]) * len(PA.CROPS) for i, c in enumerate(PA.CROPS)},
            crew_delta=PA.CREW_DELTAS[pick("crew_delta")],
            buy_land=bool(pick("buy_land")),
            animal=PA.ANIMAL_CHOICES[pick("animal")])

    def sell(self, v, holdings):
        from dynamic.rl import policy_api as PA
        with self.t.no_grad():
            lg, _ = self.s(self.t.tensor(v, dtype=self.t.float32))
        idx = lg.argmax(-1).tolist()
        return {it: PA.SELL_LEVELS[idx[i]] for i, it in enumerate(PA.PRODUCTS)}


def _plain(path):
    import importlib.util
    _n[0] += 1
    spec = importlib.util.spec_from_file_location(
        f"pl_{os.getpid()}_{_n[0]}", os.path.join(ROOT, path))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return getattr(m, "_submission_entry", None) or m.agent


def _agent(kind):
    if kind.endswith(".py"):
        return _plain(kind)
    import importlib.util, torch
    from dynamic.rl.linear_policy import LinearDailyNet, LinearSellNet, DEFAULT_INTERACTIONS
    _n[0] += 1
    spec = importlib.util.spec_from_file_location(
        f"ed_{os.getpid()}_{_n[0]}", os.path.join(ROOT, "dynamic", "rl", "agent_rl.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    d, s = LinearDailyNet(), LinearSellNet(interactions=DEFAULT_INTERACTIONS)
    if kind == "distilled":
        ck = torch.load(_W["ck"], map_location="cpu", weights_only=False)
        d.load_state_dict(ck["daily"]); s.load_state_dict(ck["sell"])
    m.configure(_W["genome"]); m.set_policy(TorchLinear(d, s))
    return m.agent


def _opp(name):
    import importlib.util
    _n[0] += 1
    spec = importlib.util.spec_from_file_location(
        f"eo_{os.getpid()}_{_n[0]}", os.path.join(ROOT, "opponents", f"{name}.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return getattr(m, "_submission_entry", None) or m.agent


def play(job):
    lbl, kind, opp, seed, seat = job
    try:
        from planner.simulate import Simulator
        me, op = _agent(kind), _opp(opp)
        pair = [me, op] if seat == 0 else [op, me]
        sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
        m0, m1 = sim.run_episode(pair[0], pair[1])
        us, them = (m0, m1) if seat == 0 else (m1, m0)
        return (lbl, opp, seed, seat, us - them, None)
    except Exception:
        import traceback
        return (lbl, opp, seed, seat, 0.0, traceback.format_exc()[-200:])


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    ck = sys.argv[3] if len(sys.argv) > 3 else os.path.join(ROOT, "logs", "rl", "best.pt")
    import random
    rng = random.Random(555111)
    seeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(n)]
    cands = [("identity (scheduler)", "identity"), ("RL trained", "distilled"),
             ("SHIPPED tape+market", "submission/main.py"),
             ("kawa tape", "opponents/kaggriculture-multi-route-farming-agent.py")]
    jobs = [(l, k, o, s, st) for l, k in cands for o in POOL for s in seeds for st in (0, 1)]
    print(f"{len(jobs):,} games", flush=True)
    with mp.get_context("forkserver").Pool(workers, initializer=_init,
                                           initargs=(_genome(), ck)) as pool:
        res = pool.map(play, jobs, chunksize=4)
    errs = [e for *_x, e in res if e]
    if errs:
        print(f"{len(errs)} errors; first:\n{errs[0]}")
    per = {}
    for lbl, opp, seed, seat, mg, e in res:
        if e: continue
        per.setdefault((lbl, opp, seed), []).append(mg)
    paired = {}
    for (lbl, opp, seed), v in per.items():
        if len(v) == 2: paired.setdefault(lbl, {})[(opp, seed)] = sum(v)
    base = paired.get("identity (scheduler)", {})
    print(f"\n{'variant':<24}{'paired':>12}{'vs base':>11}{'se':>8}{'t':>7}{'W-L':>10}")
    for lbl, _k in cands:
        d = paired.get(lbl) or {}
        diffs = [d[k] - base[k] for k in d if k in base]
        if not diffs: continue
        mean = statistics.mean(diffs)
        se = statistics.pstdev(diffs) / len(diffs) ** 0.5 if len(diffs) > 1 else 0.0
        w = sum(1 for x in diffs if x > 0); l = sum(1 for x in diffs if x < 0)
        print(f"{lbl:<24}{statistics.mean(d.values()):>12,.0f}{mean:>+11,.0f}"
              f"{se:>8,.0f}{mean / se if se > 1e-9 else 0:>7.2f}{w:>7}-{l}")


if __name__ == "__main__":
    main()
