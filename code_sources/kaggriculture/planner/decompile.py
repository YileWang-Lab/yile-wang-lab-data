"""Decompile a tape (or any agent) into an explicit day-by-day schedule spec,
and diff two agents' schedules on the same seed.

The tape banks ~$170k where our from-scratch planner banks ~$68k, and 124+
generations of parameter search never closed that. Blind search treats the tape
as a black box; this reads its decisions out directly, so the gap becomes a
list of specific differences (portfolio, hire curve, land timing, sell timing,
labour efficiency) instead of a scalar to minimise.

Everything is recovered by stepping planner.simulate and recording what each
agent actually did -- no assumptions about the tape's internals, so it works
equally on the tape, on route/agent.py, and on any reference agent.

Usage:
    python -m planner.decompile --a <agentspec> --b <agentspec> --seed N
    python -m planner.decompile --a kawa --b route --seed 1009

agentspec: "kawa", "submission", "route", or a path to a .py file.
"""
import argparse
import collections
import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from planner.simulate import Simulator, market_price, ANIMALS, CROPS  # noqa: E402

_n = [0]

ALIASES = {
    "kawa": os.path.join(ROOT, "opponents", "kaggriculture-multi-route-farming-agent.py"),
    "submission": os.path.join(ROOT, "submission", "main.py"),
    "v111": os.path.join(ROOT, "opponents", "v111-8c4s-economic-core-premium-lead.py"),
    "frontier": os.path.join(ROOT, "opponents", "kaggriculture-frontier-the-soil-remembers-rain.py"),
}

TILE_OPS = {"PLANT", "WATER", "HARVEST", "FERTILIZE", "FEED", "CARE",
            "COLLECT_FERTILIZER", "DIG", "BUILD_COOP", "BUILD_PASTURE",
            "PLACE", "PICKUP", "DROP"}
MOVES = {"NORTH", "SOUTH", "EAST", "WEST"}


def load_agent(spec, genome_path=None):
    """spec: alias, path, or 'route' (route/agent.py, optionally configured)."""
    _n[0] += 1
    if spec == "route":
        path = os.path.join(ROOT, "route", "agent.py")
        s = importlib.util.spec_from_file_location(f"dec_route_{_n[0]}", path)
        m = importlib.util.module_from_spec(s)
        s.loader.exec_module(m)
        if genome_path and os.path.exists(genome_path):
            from route.search import to_params
            m.configure(to_params(json.load(open(genome_path))["genome"]))
        return m.agent
    path = ALIASES.get(spec, spec)
    s = importlib.util.spec_from_file_location(f"dec_{_n[0]}", path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return getattr(m, "_submission_entry", None) or m.agent


def tile_census(farm):
    c = collections.Counter()
    for row in farm["tiles"]:
        for t in row:
            if t == "LOCKED":
                c["LOCKED"] += 1
            elif t is None:
                c["EMPTY"] += 1
            elif isinstance(t, dict):
                if t.get("animal"):
                    c["A:" + t["animal"]] += 1
                elif t.get("kind") == "PLANT":
                    c["P:" + t["crop"]] += 1
                elif t.get("kind") == "WEED":
                    c["WEED"] += 1
                elif t.get("kind") in ("COOP", "PASTURE"):
                    c["EMPTY_" + t["kind"]] += 1
    return c


def trace(agent, opponent, seed, seat=0, steps=720):
    """Run one episode, recording per-day decisions for `agent` at `seat`."""
    from planner.simulate import _agent_caller
    sim = Simulator.new_episode(configuration={"episodeSteps": steps}, seed=seed)
    ca, co = _agent_caller(agent), _agent_caller(opponent)

    days = collections.defaultdict(lambda: {
        "hires": 0, "land": 0, "buy_seed": collections.Counter(),
        "buy_animal": collections.Counter(), "buy_product": collections.Counter(),
        "sells": collections.Counter(), "sell_revenue": collections.Counter(),
        "sold_real": collections.Counter(), "revenue_real": collections.Counter(),
        "spent_real": collections.Counter(),
        "ops": collections.Counter(), "moves": 0, "passes": 0, "unit_turns": 0,
    })

    # Exact realised cashflow: the engine fills orders one unit at a time down
    # a moving price curve, so qty * opening_price is a large overestimate.
    live = {"day": 0}

    def _on_commit(player_id, op, item, price):
        if player_id != seat:
            return
        d = days[live["day"]]
        if op == "SELL":
            d["sold_real"][item] += 1
            d["revenue_real"][item] += price
        else:
            d["spent_real"][op + ":" + str(item)] += price

    sim.on_commit = _on_commit

    limit = steps - 1
    while sim.step < limit:
        live["day"] = sim.day
        day = sim.day
        obs_me = sim.observation_for(seat)
        obs_op = sim.observation_for(1 - seat)
        a_me = ca(obs_me, sim.cfg) if seat == 0 else ca(obs_me, sim.cfg)
        a_op = co(obs_op, sim.cfg)
        act = a_me if isinstance(a_me, dict) else {}

        d = days[day]
        prices = dict(sim.market["prices"])
        for o in (act.get("market") or []):
            if not isinstance(o, list) or not o:
                continue
            if o[0] == "HIRE":
                d["hires"] += 1
            elif o[0] == "BUY_LAND":
                d["land"] += 1
            elif o[0] == "BUY_SEED" and len(o) >= 3:
                d["buy_seed"][o[1]] += int(o[2])
            elif o[0] == "BUY_ANIMAL" and len(o) >= 3:
                d["buy_animal"][o[1]] += int(o[2])
            elif o[0] == "BUY_PRODUCT" and len(o) >= 3:
                d["buy_product"][o[1]] += int(o[2])
            elif o[0] == "SELL" and len(o) >= 3:
                d["sells"][o[1]] += int(o[2])
                d["sell_revenue"][o[1]] += int(o[2]) * prices.get(o[1], 0)

        units = [act.get("farmer") or ["PASS"]] + list(act.get("hands") or [])
        for u in units:
            if not isinstance(u, list) or not u:
                continue
            d["unit_turns"] += 1
            op = u[0]
            if op in MOVES:
                d["moves"] += 1
            elif op == "PASS":
                d["passes"] += 1
            elif op in TILE_OPS:
                d["ops"][op] += 1

        pair = (a_me, a_op) if seat == 0 else (a_op, a_me)
        sim.step_actions(pair[0], pair[1])

        if sim.step % 24 == 0:
            dd = days[day]
            dd["end_money"] = sim.farms[seat]["money"]
            dd["end_census"] = dict(tile_census(sim.farms[seat]))
            dd["end_hands"] = len(sim.farms[seat]["hands"])
            dd["quadrants"] = len(sim.farms[seat]["unlocked_quadrants"])
            dd["shed_used"] = sum(sim.privates[seat]["shed"].values())

    return days, sim.farms[seat]["money"], sim.farms[1 - seat]["money"]


def summarise(days, label):
    print(f"\n{'='*100}\n{label}\n{'='*100}")
    print(f"{'day':>3} {'money':>9} {'hnd':>3} {'q':>2} {'shed':>4} "
          f"{'ops':>4} {'mv':>4} {'pass':>4} {'use%':>5}  {'buys':<28} {'sells':<30}")
    tot_ops = tot_moves = tot_pass = tot_turns = 0
    for day in sorted(days):
        d = days[day]
        ops = sum(d["ops"].values())
        turns = d["unit_turns"]
        tot_ops += ops
        tot_moves += d["moves"]
        tot_pass += d["passes"]
        tot_turns += turns
        buys = []
        if d["hires"]:
            buys.append(f"H{d['hires']}")
        if d["land"]:
            buys.append("LAND")
        for k, v in d["buy_animal"].items():
            buys.append(f"{k[:2]}{v}")
        for k, v in d["buy_seed"].items():
            buys.append(f"{k[:2].lower()}{v}")
        for k, v in d["buy_product"].items():
            buys.append(f"+{k[:2].lower()}{v}")
        sells = " ".join(f"{k[:3].lower()}{v}" for k, v in d["sells"].most_common(5))
        use = 100.0 * ops / turns if turns else 0.0
        print(f"{day:>3} {d.get('end_money',0):>9,.0f} {d.get('end_hands',0):>3} "
              f"{d.get('quadrants',0):>2} {d.get('shed_used',0):>4} "
              f"{ops:>4} {d['moves']:>4} {d['passes']:>4} {use:>5.0f}  "
              f"{' '.join(buys):<28} {sells:<30}")
    print(f"\nTOTAL unit-turns {tot_turns:,}  useful ops {tot_ops:,} ({100*tot_ops/max(tot_turns,1):.1f}%)  "
          f"moves {tot_moves:,} ({100*tot_moves/max(tot_turns,1):.1f}%)  "
          f"pass {tot_pass:,} ({100*tot_pass/max(tot_turns,1):.1f}%)")
    return tot_turns, tot_ops, tot_moves, tot_pass


def totals(days):
    t = {"sells": collections.Counter(), "revenue": collections.Counter(),
         "sold_real": collections.Counter(), "revenue_real": collections.Counter(),
         "spent_real": collections.Counter(),
         "buy_seed": collections.Counter(), "buy_animal": collections.Counter(),
         "buy_product": collections.Counter(), "ops": collections.Counter(),
         "hires": 0, "land": 0}
    for d in days.values():
        t["sells"].update(d["sells"])
        t["revenue"].update(d["sell_revenue"])
        t["sold_real"].update(d["sold_real"])
        t["revenue_real"].update(d["revenue_real"])
        t["spent_real"].update(d["spent_real"])
        t["buy_seed"].update(d["buy_seed"])
        t["buy_animal"].update(d["buy_animal"])
        t["buy_product"].update(d["buy_product"])
        t["ops"].update(d["ops"])
        t["hires"] += d["hires"]
        t["land"] += d["land"]
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="kawa")
    ap.add_argument("--b", default="route")
    ap.add_argument("--opponent", default="v111")
    ap.add_argument("--seed", type=int, default=1009)
    ap.add_argument("--genome", default=os.path.join(ROOT, "planner", "checkpoints", "best_genome1.json"))
    ap.add_argument("--quiet", action="store_true", help="totals only, no per-day table")
    args = ap.parse_args()

    opp = load_agent(args.opponent)
    out = {}
    for label, spec in (("A:" + args.a, args.a), ("B:" + args.b, args.b)):
        ag = load_agent(spec, genome_path=args.genome)
        days, mine, theirs = trace(ag, load_agent(args.opponent), args.seed)
        out[label] = (days, mine, theirs)
        if not args.quiet:
            summarise(days, f"{label}   (vs {args.opponent}, seed {args.seed})   "
                            f"final ${mine:,.0f} vs ${theirs:,.0f}")

    print(f"\n{'='*100}\nSIDE-BY-SIDE TOTALS   (vs {args.opponent}, seed {args.seed})\n{'='*100}")
    labels = list(out)
    ta, tb = totals(out[labels[0]][0]), totals(out[labels[1]][0])
    print(f"{'metric':<26} {labels[0]:>22} {labels[1]:>22}   {'B-A':>14}")

    def row(name, x, y, fmt=",.0f"):
        d = y - x
        print(f"{name:<26} {format(x, fmt):>22} {format(y, fmt):>22}   {format(d, '+,.0f'):>14}")

    row("final money", out[labels[0]][1], out[labels[1]][1])
    row("total hires", ta["hires"], tb["hires"])
    row("land buys", ta["land"], tb["land"])
    print()
    allp = sorted(set(ta["sold_real"]) | set(tb["sold_real"]))
    print(f"{'SOLD units / REALISED $':<26} {labels[0]:>22} {labels[1]:>22}   {'B-A rev':>14}")
    for p in allp:
        xa, ra = ta["sold_real"][p], ta["revenue_real"][p]
        xb, rb = tb["sold_real"][p], tb["revenue_real"][p]
        pa = ra / xa if xa else 0.0
        pb = rb / xb if xb else 0.0
        print(f"  {p:<24} {f'{xa:,}@${pa:.0f} = ${ra:,.0f}':>22} {f'{xb:,}@${pb:.0f} = ${rb:,.0f}':>22}   {rb-ra:>+14,.0f}")
    row("TOTAL realised revenue", sum(ta["revenue_real"].values()), sum(tb["revenue_real"].values()))
    print()
    print(f"{'SPEND (realised)':<26} {labels[0]:>22} {labels[1]:>22}   {'B-A':>14}")
    for k in sorted(set(ta["spent_real"]) | set(tb["spent_real"])):
        row("  " + k[:24], ta["spent_real"][k], tb["spent_real"][k])
    row("TOTAL spend", sum(ta["spent_real"].values()), sum(tb["spent_real"].values()))
    print()
    print(f"{'BOUGHT':<26} {labels[0]:>22} {labels[1]:>22}")
    for k in ("buy_animal", "buy_seed", "buy_product"):
        for p in sorted(set(ta[k]) | set(tb[k])):
            print(f"  {k[4:]}:{p:<19} {ta[k][p]:>22,} {tb[k][p]:>22,}")
    print()
    print(f"{'OPS':<26} {labels[0]:>22} {labels[1]:>22}   {'B-A':>14}")
    for p in sorted(set(ta["ops"]) | set(tb["ops"])):
        row("  " + p, ta["ops"][p], tb["ops"][p])


if __name__ == "__main__":
    main()
