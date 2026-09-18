"""Does crew capacity actually bind under a given genome?

The whole scheduler line rests on this. At the searched 50-tile portfolio the
answer is no -- mean utilisation 35%, max 43%, over-subscribed on 0 days of 30 --
which is why task value, triage and every coefficient of
`J = sum V_task - lambda*C_move` measure as exactly inert. Nothing is ever
dropped, so the thing that decides what to drop cannot matter.

Run this before spending anything on scheduler quality.
"""
import json
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _HERE]
sys.path.insert(0, ROOT)

from planner.simulate import Simulator  # noqa: E402


def _load(path, genome=None):
    import importlib.util
    spec = importlib.util.spec_from_file_location("up_mod", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    if genome is not None:
        m.configure(genome)
    return m


def probe(params, seeds=(1009, 2024, 77), opp=None):
    opp = opp or os.path.join(ROOT, "opponents",
                              "kaggriculture-multi-route-farming-agent.py")
    m = _load(os.path.join(ROOT, "dynamic", "agent2.py"), params)
    om = _load(opp)
    opp_fn = getattr(om, "_submission_entry", None) or om.agent
    rows = []
    orig = m._plan_day

    def wrapped(farm, private, day, board_size):
        r = orig(farm, private, day, board_size)
        tasks = m._build_tasks(farm, private, day, board_size)
        cap = 24 * m.S.get("target_units", 1)
        rows.append((day, len(tasks), sum(t.n_ops for t in tasks), cap))
        return r
    m._plan_day = wrapped
    banks = []
    for seed in seeds:
        sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
        banks.append(sim.run_episode(m.agent, opp_fn))
    u = [100.0 * d / max(1, c) for _, _, d, c in rows]
    tiles = [n for _, n, _, _ in rows]
    return {"util_mean": statistics.mean(u), "util_max": max(u),
            "over": sum(1 for x in u if x > 100), "days": len(u),
            "tiles_max": max(tiles),
            "bank": statistics.mean(b[0] for b in banks),
            "opp_bank": statistics.mean(b[1] for b in banks)}


def main():
    from route.search import to_params
    g = json.load(open(os.path.join(ROOT, "dynamic", "best_genome.json")))["genome"]
    base = to_params(dict(g))
    base["OPP_MODEL"] = 1

    def V(**kw):
        p = dict(base)
        p.update(kw)
        return p

    cases = [
        ("50 tiles (searched)", V()),
        ("plan, gate on", V(USE_PLAN=1, PLAN_GATE_DAYS=1, SEED_BATCH_PER_TURN=16)),
        ("plan, gate off", V(USE_PLAN=1, PLAN_GATE_DAYS=0, SEED_BATCH_PER_TURN=16)),
        ("plan + sched + land", V(USE_PLAN=1, PLAN_GATE_DAYS=1, SEED_BATCH_PER_TURN=16,
                                  SCHEDULE_DRIVEN=1, LAND_BUY_CASH_MULTIPLE=1.05,
                                  ANIMAL_BUY_CAP_PER_TURN=4)),
    ]
    print(f"{'config':<24}{'peak tiles':>11}{'util mean':>11}{'util max':>10}"
          f"{'days>100%':>11}{'our bank':>10}{'opp bank':>10}")
    for lbl, p in cases:
        r = probe(p)
        print(f"{lbl:<24}{r['tiles_max']:>11}{r['util_mean']:>10.0f}%"
              f"{r['util_max']:>9.0f}%{r['over']:>6}/{r['days']:<4}"
              f"{r['bank']:>10,.0f}{r['opp_bank']:>10,.0f}")


if __name__ == "__main__":
    main()
