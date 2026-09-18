"""Where does the money come from, per product, for us and for the opponent?

The paired margin is us minus them, and every diagnostic in this project until
now measured only our own side. This one prices BOTH players' sales through the
engine's own commit hook, so units and dollars are exact rather than inferred,
and reports what each product actually earned per unit.

The comparison that matters is against the ceiling: `metered` is what the same
number of units would have earned if they had been spread out so the book never
crashed -- sold at the town's drain rate. The gap between realised and metered
is the money the sell POLICY is leaving on the table; the gap in units is the
money the SCHEDULER is leaving on the table. They need different fixes and the
totals say which one is binding.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _HERE]
sys.path.insert(0, ROOT)

from dynamic import market_model as MM          # noqa: E402
from planner.simulate import Simulator, _agent_caller  # noqa: E402

ITEMS = ["MELON", "STRAWBERRY", "MILK", "WOOL", "EGG", "WHEAT", "FERTILIZER"]
_n = [0]


def _load(path, genome=None):
    import importlib.util
    _n[0] += 1
    spec = importlib.util.spec_from_file_location(f"ra_{os.getpid()}_{_n[0]}", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    if genome is not None:
        m.configure(genome)
        return m.agent
    return getattr(m, "_submission_entry", None) or m.agent


def audit(a0, a1, seed, g0=None):
    me = _load(a0, g0) if g0 is not None else _load(a0)
    op = _load(a1)
    sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
    units = [{}, {}]
    cash = [{}, {}]
    bought = [{}, {}]

    def on_commit(pid, opn, item, price):
        if opn == "SELL":
            units[pid][item] = units[pid].get(item, 0) + 1
            cash[pid][item] = cash[pid].get(item, 0) + price
        elif opn == "BUY_PRODUCT":
            bought[pid][item] = bought[pid].get(item, 0) + 1
            cash[pid][item] = cash[pid].get(item, 0) - price
    sim.on_commit = on_commit
    c0, c1 = _agent_caller(me), _agent_caller(op)
    while sim.step < 719:
        sim.step_actions(c0(sim.observation_for(0), sim.cfg),
                         c1(sim.observation_for(1), sim.cfg))
    shops = tuple(sim.town.get("unlocked_shops", []))
    return units, cash, bought, shops, sim.farms[0]["money"], sim.farms[1]["money"]


def metered_ceiling(item, n, shops, days=20):
    """What `n` units would fetch spread at the town's own absorption rate, so
    the book never runs away from the seller."""
    rate = max(1.0, MM.drain_rate(item, shops))
    inv = MM.MARKET_I0
    total = 0.0
    left = n
    for _ in range(days):
        k = int(min(left, rate))
        total += MM.revenue(item, inv, k)
        left -= k
        inv = max(MM.MARKET_I0, inv + k - rate)
        if left <= 0:
            break
    if left > 0:
        total += MM.revenue(item, inv, left)
    return total


def main():
    seeds = [int(x) for x in (sys.argv[1:] or ["1009", "2024", "77"])]
    K = os.path.join(ROOT, "opponents", "kaggriculture-multi-route-farming-agent.py")
    from route.search import to_params
    g = json.load(open(os.path.join(ROOT, "dynamic", "best_genome.json")))["genome"]
    p = to_params(dict(g))
    p["OPP_MODEL"] = 1
    for lbl, a0, gg in (("dynamic scheduler", os.path.join(ROOT, "dynamic", "agent2.py"), p),
                        ("the tape (kawa)", K, None)):
        agg_u = {}
        agg_c = {}
        agg_ou = {}
        agg_oc = {}
        ceil = {}
        banks = []
        for seed in seeds:
            u, c, b, shops, m0, m1 = audit(a0, K, seed, gg)
            banks.append((m0, m1))
            for it in ITEMS:
                agg_u[it] = agg_u.get(it, 0) + u[0].get(it, 0)
                agg_c[it] = agg_c.get(it, 0) + c[0].get(it, 0)
                agg_ou[it] = agg_ou.get(it, 0) + u[1].get(it, 0)
                agg_oc[it] = agg_oc.get(it, 0) + c[1].get(it, 0)
                ceil[it] = ceil.get(it, 0) + metered_ceiling(it, u[0].get(it, 0), shops)
        n = len(seeds)
        print(f"\n=== {lbl} vs kawa, {n} seeds "
              f"(bank {sum(a for a, _ in banks) / n:,.0f} v "
              f"{sum(b for _, b in banks) / n:,.0f}) ===")
        print(f"{'item':<12}{'our u':>7}{'our $':>10}{'$/u':>7}"
              f"{'metered $':>11}{'left on table':>14}{'their u':>9}{'their $':>10}{'$/u':>7}")
        tl = 0
        for it in ITEMS:
            uu = agg_u[it] / n
            cc = agg_c[it] / n
            ce = ceil[it] / n
            ou = agg_ou[it] / n
            oc = agg_oc[it] / n
            tl += max(0.0, ce - cc)
            print(f"{it:<12}{uu:>7.0f}{cc:>10,.0f}{cc / max(1, uu):>7.0f}"
                  f"{ce:>11,.0f}{ce - cc:>+14,.0f}{ou:>9.0f}{oc:>10,.0f}"
                  f"{oc / max(1, ou):>7.0f}")
        print(f"{'TOTAL':<12}{sum(agg_u.values()) / n:>7.0f}"
              f"{sum(agg_c.values()) / n:>10,.0f}{'':>7}"
              f"{sum(ceil.values()) / n:>11,.0f}{tl:>+14,.0f}"
              f"{sum(agg_ou.values()) / n:>9.0f}{sum(agg_oc.values()) / n:>10,.0f}")


if __name__ == "__main__":
    main()
