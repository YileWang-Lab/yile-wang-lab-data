"""What do the current ladder leaders actually DO, measured from their winning
replays -- and how does our live submission differ?

Reads recorded replays only (no agent execution), so it works on adaptive
opponents that cannot be extracted or replayed (HANDOFF section 10). Realised
per-unit prices are recovered by re-simulating the recorded actions through
planner.simulate with the commit hook, which is exact -- the replay's own
action list only carries requested quantities, and an order for 100 units at
an opening price of $200 may realise a fraction of that.

Usage:
    /home/yilewang/kagg-env/bin/python -m planner.analyze_top
"""
import collections
import glob
import json
import multiprocessing
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from planner.simulate import Simulator  # noqa: E402

LOG_DIR = os.path.join(ROOT, "logs", "planner")
MANIFEST = os.path.join(LOG_DIR, "top_replays.json")

TILE_OPS = {"PLANT", "WATER", "HARVEST", "FERTILIZE", "FEED", "CARE",
            "COLLECT_FERTILIZER", "DIG", "BUILD_COOP", "BUILD_PASTURE",
            "PLACE", "PICKUP", "DROP"}
MOVES = {"NORTH", "SOUTH", "EAST", "WEST"}


def analyse(path_seat):
    path, seat, label = path_seat
    try:
        d = json.load(open(path))
        seed = d["info"]["seed"]
        cfg = d.get("configuration", {})
        steps = d["steps"]

        s0 = steps[0][0]["observation"]
        sim = Simulator.from_observation(
            {"day": s0["day"], "hour": s0["hour"], "player": 0, "farms": s0["farms"],
             "market": s0["market"], "town": s0["town"],
             "private": steps[0][0]["observation"]["private"]},
            opp_private=steps[0][1]["observation"]["private"],
            configuration={k: v for k, v in cfg.items() if k in
                           ("boardSize", "startingMoney", "maxMarketOrdersPerTurn", "turnsPerDay",
                            "shedCapacity", "weedSpawnChance", "townShopUnlockInterval",
                            "townShopSellInterval", "townCenterSellInterval",
                            "farmHandCostMult", "episodeSteps", "marketParams")},
            seed=seed)

        sold = collections.Counter()
        revenue = collections.Counter()
        spent = collections.Counter()

        def on_commit(pid, op, item, price):
            if pid != seat:
                return
            if op == "SELL":
                sold[item] += 1
                revenue[item] += price
            else:
                spent[op + ":" + str(item)] += price

        sim.on_commit = on_commit

        ops = collections.Counter()
        moves = passes = unit_turns = hires = land = 0
        peak_hands = 0
        first_sale_day = {}

        for i in range(1, len(steps)):
            a = steps[i][seat].get("action")
            if isinstance(a, dict):
                for o in (a.get("market") or []):
                    if not isinstance(o, list) or not o:
                        continue
                    if o[0] == "HIRE":
                        hires += 1
                    elif o[0] == "BUY_LAND":
                        land += 1
                    elif o[0] == "SELL" and len(o) >= 2:
                        first_sale_day.setdefault(o[1], i // 24)
                units = [a.get("farmer") or ["PASS"]] + list(a.get("hands") or [])
                for u in units:
                    if not isinstance(u, list) or not u:
                        continue
                    unit_turns += 1
                    if u[0] in MOVES:
                        moves += 1
                    elif u[0] == "PASS":
                        passes += 1
                    elif u[0] in TILE_OPS:
                        ops[u[0]] += 1
            sim.step_actions(steps[i][0]["action"], steps[i][1]["action"])
            peak_hands = max(peak_hands, len(sim.farms[seat]["hands"]))

        return {"label": label, "path": os.path.basename(path), "seat": seat,
                "money": sim.farms[seat]["money"], "opp_money": sim.farms[1 - seat]["money"],
                "sold": dict(sold), "revenue": dict(revenue), "spend": dict(spent),
                "ops": dict(ops), "moves": moves, "passes": passes,
                "unit_turns": unit_turns, "hires": hires, "land": land,
                "peak_hands": peak_hands, "first_sale_day": first_sale_day, "err": None}
    except Exception:
        import traceback
        return {"label": label, "path": os.path.basename(path), "err": traceback.format_exc()[-300:]}


def main():
    picks = json.load(open(MANIFEST))
    jobs = []
    for p in picks:
        path = os.path.join(ROOT, "replays", f"episode-{p['episode']}-replay.json")
        if os.path.exists(path):
            jobs.append((path, p["seat"], p["team"]))

    # our own live submission's games, for a like-for-like comparison
    ours = json.load(open("/tmp/claude-1818200050/-home-yilewang/12e9e33c-6cb5-4a53-939b-9c2b0d0b6776/scratchpad/v3_episodes2.json"))
    for r in ours:
        path = os.path.join(ROOT, "replays", f"episode-{r['episode']}-replay.json")
        if os.path.exists(path):
            jobs.append((path, r["us_seat"], "OURS(v3)"))

    print(f"analysing {len(jobs)} replays...")
    t0 = time.time()
    with multiprocessing.get_context("forkserver").Pool(14) as pool:
        res = pool.map(analyse, jobs)
    print(f"elapsed {time.time()-t0:.0f}s")

    errs = [r for r in res if r.get("err")]
    for e in errs[:3]:
        print(f"ERROR {e['path']}: {e['err'][-200:]}")
    res = [r for r in res if not r.get("err")]

    by_team = collections.defaultdict(list)
    for r in res:
        by_team[r["label"]].append(r)

    print(f"\n{'='*118}")
    print("WHAT THE LADDER LEADERS DO  (their biggest wins; OURS = our live submission's real games)")
    print(f"{'='*118}")
    print(f"{'team':<20} {'n':>2} {'money':>9} {'hires':>6} {'hands':>6} {'ops':>6} {'use%':>6} "
          f"{'units':>6} {'$/unit':>7} {'revenue':>9} {'spend':>8}")
    rows = []
    for team, rs in by_team.items():
        m = statistics.mean([r["money"] for r in rs])
        hires = statistics.mean([r["hires"] for r in rs])
        hands = statistics.mean([r["peak_hands"] for r in rs])
        ops = statistics.mean([sum(r["ops"].values()) for r in rs])
        ut = statistics.mean([r["unit_turns"] for r in rs])
        units = statistics.mean([sum(r["sold"].values()) for r in rs])
        rev = statistics.mean([sum(r["revenue"].values()) for r in rs])
        spend = statistics.mean([sum(r["spend"].values()) for r in rs])
        rows.append((team, len(rs), m, hires, hands, ops, 100 * ops / max(ut, 1),
                     units, rev / max(units, 1), rev, spend))
    rows.sort(key=lambda r: -r[2])
    for r in rows:
        print(f"{r[0]:<20} {r[1]:>2} {r[2]:>9,.0f} {r[3]:>6.0f} {r[4]:>6.1f} {r[5]:>6.0f} "
              f"{r[6]:>5.1f}% {r[7]:>6.0f} {r[8]:>7.1f} {r[9]:>9,.0f} {r[10]:>8,.0f}")

    print(f"\n{'='*118}")
    print("PRODUCT MIX -- units sold @ realised $/unit")
    print(f"{'='*118}")
    prods = ["MELON", "STRAWBERRY", "MILK", "WOOL", "EGG", "WHEAT", "FERTILIZER", "CARROT", "TOMATO"]
    print(f"{'team':<20} " + " ".join(f"{p[:9]:>13}" for p in prods))
    for team, rs in sorted(by_team.items(), key=lambda kv: -statistics.mean([r["money"] for r in kv[1]])):
        cells = []
        for p in prods:
            u = statistics.mean([r["sold"].get(p, 0) for r in rs])
            v = statistics.mean([r["revenue"].get(p, 0) for r in rs])
            cells.append(f"{u:>5.0f}@${v/max(u,1):>5.0f}" if u else f"{'-':>13}")
        print(f"{team:<20} " + " ".join(cells))

    print(f"\n{'='*118}")
    print("REVENUE SHARE BY PRODUCT (% of that team's total realised revenue)")
    print(f"{'='*118}")
    print(f"{'team':<20} " + " ".join(f"{p[:9]:>11}" for p in prods))
    for team, rs in sorted(by_team.items(), key=lambda kv: -statistics.mean([r["money"] for r in kv[1]])):
        tot = statistics.mean([sum(r["revenue"].values()) for r in rs])
        cells = []
        for p in prods:
            v = statistics.mean([r["revenue"].get(p, 0) for r in rs])
            cells.append(f"{100*v/max(tot,1):>10.1f}%")
        print(f"{team:<20} " + " ".join(cells))

    out = os.path.join(LOG_DIR, f"top_analysis_{time.strftime('%Y%m%d_%H%M%S')}.json")
    json.dump(res, open(out, "w"), indent=1, default=str)
    print(f"\nraw: {out}")


if __name__ == "__main__":
    main()
