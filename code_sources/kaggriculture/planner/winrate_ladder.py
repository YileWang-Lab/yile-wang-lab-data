"""Same win-rate-vs-margin question, but on the REAL ladder distribution.

winrate_check.py answered it on the 9-agent reference pool and found b0 buys
+786 margin for -0.06% win rate. But that pool is saturated -- we win 87% of
those games -- so it has little resolution left to detect a win-rate change.
The real ladder sits at 60-78%, where a win-rate difference is actually visible.

These are the 80 opponents we actually faced, replaying their recorded actions
with only our side swapped. Same two limitations as ladder_sweep.py: they are
traces rather than policies, and 80 is a small fixed sample.
"""
import importlib.util, json, multiprocessing, os, statistics, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from planner.simulate import Simulator  # noqa: E402
from route.bake import bake  # noqa: E402
from planner.ladder_sweep import make_trace_agent, EPISODES, SHIPPED, LIVE, B0_MAP  # noqa: E402

VARIANTS = [("v3", dict(SHIPPED)), ("struct", dict(LIVE)),
            ("b0", {**LIVE, "TAPE_MAP": B0_MAP})]
_n = [0]


def _load(p):
    _n[0] += 1
    s = importlib.util.spec_from_file_location(f"wl_{os.getpid()}_{_n[0]}", p)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return getattr(m, "_submission_entry", None) or m.agent


def run_one(job):
    name, path, ep, seat = job
    try:
        d = json.load(open(os.path.join(ROOT, "replays", f"episode-{ep}-replay.json")))
        cfg = d.get("configuration", {})
        me = _load(path); opp = make_trace_agent(d["steps"], 1 - seat)
        sim = Simulator.new_episode(
            configuration={k: v for k, v in cfg.items() if k in
                           ("boardSize", "startingMoney", "maxMarketOrdersPerTurn", "turnsPerDay",
                            "shedCapacity", "weedSpawnChance", "townShopUnlockInterval",
                            "townShopSellInterval", "townCenterSellInterval",
                            "farmHandCostMult", "episodeSteps", "marketParams")},
            seed=d["info"]["seed"])
        pair = [me, opp] if seat == 0 else [opp, me]
        m0, m1 = sim.run_episode(pair[0], pair[1])
        us, them = (m0, m1) if seat == 0 else (m1, m0)
        return (name, ep, us - them, None)
    except Exception:
        import traceback
        return (name, ep, 0.0, traceback.format_exc()[-200:])


def main():
    rows = json.load(open(EPISODES))
    games = [r for r in rows if os.path.exists(
        os.path.join(ROOT, "replays", f"episode-{r['episode']}-replay.json"))]
    paths = {}
    for name, params in VARIANTS:
        p = os.path.join(ROOT, "agents", "ladder", f"wl_{name}.py")
        bake(params, out=p, note=f"winrate ladder {name}"); paths[name] = p
    jobs = [(n, paths[n], r["episode"], r["us_seat"]) for n, _ in VARIANTS for r in games]
    print(f"{len(VARIANTS)} variants x {len(games)} real ladder games = {len(jobs)} episodes")
    t0 = time.time()
    with multiprocessing.get_context("forkserver").Pool(20) as pool:
        res = pool.map(run_one, jobs, chunksize=4)
    print(f"elapsed {time.time()-t0:.0f}s")

    by = {}
    for name, ep, m, err in res:
        if not err:
            by.setdefault(name, {})[ep] = m
    base = by.get("struct", {})
    print()
    print(f"{'variant':<8} {'n':>4} {'WIN RATE':>10} {'record':>9} {'mean margin':>13} "
          f"{'dWin vs struct':>15} {'dMargin':>10}")
    for name, _ in VARIANTS:
        g = by.get(name, {})
        if not g:
            continue
        ms = list(g.values()); w = sum(1 for m in ms if m > 0)
        keys = [k for k in g if k in base]
        dwin = statistics.mean([(1 if g[k] > 0 else 0) - (1 if base[k] > 0 else 0) for k in keys])
        dmar = statistics.mean([g[k] - base[k] for k in keys])
        print(f"{name:<8} {len(ms):>4} {w/len(ms):>9.1%} {w:>4}/{len(ms):<4} "
              f"{statistics.mean(ms):>13,.0f} {dwin:>+14.2%} {dmar:>+10,.0f}")
    print()
    print("The ladder rates on win/loss. dMargin is not rewarded.")


if __name__ == "__main__":
    main()
