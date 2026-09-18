"""Validate OppState against engine ground truth.

The opponent's shed and farmer inventories are private in a real game; the
simulator exposes them, so the tracker's estimate can be compared to the truth
turn by turn. The bar is EXACTNESS on the five products that decide the
suppression term (STRAWBERRY, MELON, MILK, WOOL, EGG). WHEAT and FERTILIZER
are expected to drift and the test reports them separately: wheat is bought and
eaten as feed, and floor-priced sales of both are invisible to the market
arithmetic by design (engine line 659).
"""
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dynamic.opp_state import OppState                 # noqa: E402
from planner.simulate import Simulator, _agent_caller  # noqa: E402
from route.opponent import OpponentModel               # noqa: E402

# Local loader rather than dynamic.attribute's: this file lives in dynamic/, so
# running it as a script puts dynamic/ on sys.path[0], where dynamic/search.py
# shadows the top-level search package that route.evaluate imports.
_n = [0]


def _load(path, genome=None):
    import importlib.util
    _n[0] += 1
    spec = importlib.util.spec_from_file_location(f"os_{os.getpid()}_{_n[0]}", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    if genome is not None:
        m.configure(genome)
        return m.agent
    return getattr(m, "_submission_entry", None) or m.agent

CLEAN = ["STRAWBERRY", "MELON", "MILK", "WOOL", "EGG"]
NOISY = ["WHEAT", "FERTILIZER"]


def truth_held(sim, seat):
    """Everything the opponent physically holds: shed plus every unit still in
    a farmer's or hand's hands."""
    priv = sim.privates[seat]
    out = dict(priv.get("shed", {}))
    invs = priv.get("inventories") or {}
    for inv in (invs.values() if isinstance(invs, dict) else invs):
        for k, v in (inv or {}).items():
            out[k] = out.get(k, 0) + v
    return out


def run(seed, a0, a1, g0=None):
    """Play a game, driving the tracker exactly the way the agent does, and
    compare its estimate to the simulator's private state.

    The observation pattern matters and is the same one `dynamic/agent2.py`
    uses: observe ONCE per turn, with the turn's own (pre-action) market
    inventory and the sales we issued on the PREVIOUS turn -- the inventory we
    can see already reflects last turn's commits and nothing of this turn's.
    """
    me = _load(a0, g0) if g0 is not None else _load(a0)
    op = _load(a1)
    sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
    c0, c1 = _agent_caller(me), _agent_caller(op)

    truth_sold = {}                      # ground truth: their committed sells
    def on_commit(pid, opn, item, price):
        if pid == 1 and opn == "SELL":
            truth_sold[item] = truth_sold.get(item, 0) + 1
    sim.on_commit = on_commit
    samples = []                         # (item, day, predicted supply, sold so far)

    st, om = OppState(), OpponentModel()
    my_prev = {}
    err = {k: [] for k in CLEAN + NOISY}
    sale_err = {k: [] for k in CLEAN + NOISY}
    while sim.step < 719:
        o = sim.observation_for(0)
        shops = tuple(o["town"].get("unlocked_shops", []))
        om.observe(dict(sim.market["inventory"]), sim.step, shops, my_prev)
        if om.recent and om.recent[-1][0] == sim.step:
            st.record_sales(om.recent[-1][1])
        st.observe(o["farms"][1], o["day"], o["hour"])
        st.reconcile(o["market"].get("prices") or {},
                     len(o["farms"][1].get("hands") or []))

        a = c0(o, sim.cfg)
        b = c1(sim.observation_for(1), sim.cfg)
        my_prev = {}
        for act in (a or {}).get("market", []) if isinstance(a, dict) else []:
            if act and act[0] == "SELL":
                my_prev[act[1]] = my_prev.get(act[1], 0) + int(act[2])
        sim.step_actions(a, b)

        if sim.step % 24 == 12 and sim.step > 120:
            th = truth_held(sim, 1)
            for k in err:
                err[k].append(st.held(k) - int(th.get(k, 0)))
                sale_err[k].append(st.sold[k] - truth_sold.get(k, 0))
            of = sim.observation_for(0)["farms"][1]
            d = sim.step // 24
            for k in CLEAN + NOISY:
                samples.append((k, d, st.supply(of, k, d), truth_sold.get(k, 0)))
    final = dict(truth_sold)
    supply_err = {k: [] for k in CLEAN + NOISY}
    for k, d, pred, sofar in samples:
        supply_err[k].append((pred, max(0, final.get(k, 0) - sofar)))
    return err, sale_err, supply_err


def main():
    seeds = [int(s) for s in (sys.argv[1:] or ["1009", "2024", "77", "555"])]
    K = os.path.join(ROOT, "opponents", "kaggriculture-multi-route-farming-agent.py")
    V = os.path.join(ROOT, "opponents", "v111-8c4s-economic-core-premium-lead.py")
    agg = {k: [] for k in CLEAN + NOISY}
    sagg = {k: [] for k in CLEAN + NOISY}
    pagg = {k: [] for k in CLEAN + NOISY}
    for seed in seeds:
        for opp in (K, V):
            e, se, pe = run(seed, K, opp)
            for k, v in e.items():
                agg[k].extend(v)
            for k, v in se.items():
                sagg[k].extend(v)
            for k, v in pe.items():
                pagg[k].extend(v)
    print("HELD (harvested - sold) vs the simulator's private shed+inventories")
    print(f"{'item':<12}{'mean err':>10}{'|err| mean':>12}{'max |err|':>11}"
          f"{'exact %':>9}")
    for k in CLEAN + NOISY:
        v = agg[k]
        if not v:
            continue
        tag = "" if k in CLEAN else "   (expected to drift)"
        print(f"{k:<12}{statistics.mean(v):>10.2f}"
              f"{statistics.mean(abs(x) for x in v):>12.2f}"
              f"{max(abs(x) for x in v):>11}"
              f"{100.0 * sum(1 for x in v if x == 0) / len(v):>8.1f}%{tag}")
    print()
    print("SALES recovery vs the simulator's own commit hook")
    print(f"{'item':<12}{'mean err':>10}{'|err| mean':>12}{'max |err|':>11}"
          f"{'exact %':>9}")
    for k in CLEAN + NOISY:
        v = sagg[k]
        if not v:
            continue
        print(f"{k:<12}{statistics.mean(v):>10.2f}"
              f"{statistics.mean(abs(x) for x in v):>12.2f}"
              f"{max(abs(x) for x in v):>11}"
              f"{100.0 * sum(1 for x in v if x == 0) / len(v):>8.1f}%")
    _report_supply(pagg)


def _report_supply(pagg):
    print()
    print("SUPPLY forecast (held + future production) vs their ACTUAL remaining")
    print("sales to season end -- this is the N_them the suppression term uses")
    print(f"{'item':<12}{'pred mean':>11}{'true mean':>11}{'bias':>8}"
          f"{'|err|':>8}{'corr':>7}")
    for k in CLEAN + NOISY:
        v = pagg[k]
        if not v:
            continue
        pr = [a for a, _ in v]
        tr = [b for _, b in v]
        mp, mt = statistics.mean(pr), statistics.mean(tr)
        sp, st_ = statistics.pstdev(pr), statistics.pstdev(tr)
        cov = statistics.mean((a - mp) * (b - mt) for a, b in v)
        corr = cov / (sp * st_) if sp > 1e-9 and st_ > 1e-9 else 0.0
        print(f"{k:<12}{mp:>11.1f}{mt:>11.1f}{mp - mt:>8.1f}"
              f"{statistics.mean(abs(a - b) for a, b in v):>8.1f}{corr:>7.2f}")


if __name__ == "__main__":
    main()
