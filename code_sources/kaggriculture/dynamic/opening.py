"""Where the opening $3,000 goes, day by day, us against the tape.

Section 33 ends five independent investigations at the same place: the farm is
half the size and it is decided in the first ten days. Section 34 puts a number
on why that matters -- a dollar on days 0-9 is worth 2.00 +- 0.19 at the buzzer
and a dollar after day 10 is worth exactly 1.00 +- 0.00.

So the question is narrow and quantified: on days 2-8 we hold $171-360 while
the tape is building toward 68 producing tiles. This decomposes both openings
into inflows and outflows per category per day, off the engine's own commit
hook, so the answer is what was actually spent rather than what was intended.

Categories are chosen so each maps to a lever we can pull: seed, animals, land
and hires are separate decisions in the scheduler, and wheat bought for feed is
separated from wheat sold because those net out in a plain cash trace and hide
the churn (an earlier episode round-tripped 292 units of bought wheat straight
back to the market).
"""
import json
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _HERE]
sys.path.insert(0, ROOT)

from route.search import to_params  # noqa: E402

TAPE = "opponents/kaggriculture-multi-route-farming-agent.py"
_n = [0]


def _mk(path, genome=None):
    import importlib.util
    _n[0] += 1
    spec = importlib.util.spec_from_file_location(
        f"op_{os.getpid()}_{_n[0]}", os.path.join(ROOT, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    if genome is not None:
        m.configure(genome)
        return m.agent
    return getattr(m, "_submission_entry", None) or m.agent


def _genome():
    g = json.load(open(os.path.join(ROOT, "dynamic", "best_genome3.json")))["genome"]
    p = to_params(dict(g))
    p["OPP_MODEL"] = 1
    p["SHED_PANIC_FRACTION"] = 0.40
    return p


def audit(path, genome, seed, opp=TAPE, days=14):
    """Per-day cash decomposition for the agent in seat 0."""
    from planner.simulate import Simulator, _agent_caller
    me = _mk(path, genome)
    op = _mk(opp)
    sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
    flow = {}

    def on_commit(pid, opn, item, price):
        if pid != 0:
            return
        d = sim.step // 24
        f = flow.setdefault(d, {"sell": 0.0, "seed": 0.0, "animal": 0.0,
                                "feed": 0.0, "land": 0.0, "hire": 0.0})
        if opn == "SELL":
            f["sell"] += price
        elif opn == "BUY_PRODUCT":
            f["feed"] -= price
        elif opn == "BUY_SEED":
            f["seed"] -= price
        elif opn == "BUY_ANIMAL":
            f["animal"] -= price
        elif opn == "BUY_LAND":
            f["land"] -= price
        elif opn == "HIRE":
            f["hire"] -= price
    sim.on_commit = on_commit

    c0, c1 = _agent_caller(me), _agent_caller(op)
    tiles, cash = {}, {}
    while sim.step < days * 24:
        o = sim.observation_for(0)
        if o["hour"] == 0:
            f = sim.farms[0]
            cash[o["day"]] = f["money"]
            tiles[o["day"]] = sum(
                1 for row in f["tiles"] for t in row
                if isinstance(t, dict) and (t.get("kind") == "PLANT" or t.get("animal")))
        sim.step_actions(c0(o, sim.cfg), c1(sim.observation_for(1), sim.cfg))
    return flow, cash, tiles


def main():
    n_seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 14
    import random
    rng = random.Random(13579)
    seeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(n_seeds)]
    g = _genome()

    for label, path, gen in (("OURS  (dynamic scheduler)", "dynamic/agent4.py", g),
                             ("TAPE  (kawa)", TAPE, None)):
        agg, cash, tiles = {}, {}, {}
        for s in seeds:
            f, c, t = audit(path, gen, s, days=days)
            for d, v in f.items():
                a = agg.setdefault(d, {k: [] for k in v})
                for k, x in v.items():
                    a[k].append(x)
            for d, v in c.items():
                cash.setdefault(d, []).append(v)
            for d, v in t.items():
                tiles.setdefault(d, []).append(v)
        print(f"\n=== {label}, mean of {n_seeds} seeds ===")
        print(f"{'day':>4}{'cash':>9}{'tiles':>7}{'sell in':>9}{'seed':>8}"
              f"{'animal':>9}{'feed':>8}{'land':>8}{'hire':>7}{'net':>9}")
        for d in range(days):
            a = agg.get(d, {})
            def m(k):
                v = a.get(k) or [0.0]
                return sum(v) / n_seeds
            net = m("sell") + m("seed") + m("animal") + m("feed") + m("land") + m("hire")
            print(f"{d:>4}{statistics.mean(cash.get(d, [0])):>9,.0f}"
                  f"{statistics.mean(tiles.get(d, [0])):>7.0f}"
                  f"{m('sell'):>9,.0f}{m('seed'):>8,.0f}{m('animal'):>9,.0f}"
                  f"{m('feed'):>8,.0f}{m('land'):>8,.0f}{m('hire'):>7,.0f}"
                  f"{net:>+9,.0f}")


if __name__ == "__main__":
    main()
