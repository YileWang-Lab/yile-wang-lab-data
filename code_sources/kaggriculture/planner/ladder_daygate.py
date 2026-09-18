"""Re-test the endgame hypothesis on REAL ladder opponents.

planner/daygate_sweep.py tested a day gate against the 9-agent reference pool
and found nothing (+22 at best). But the same run exposed why that test could
not have worked: against the pool our margin GROWS by +10,225 from day 15 to
the end, identically for every variant. The pool simply does not reproduce the
endgame collapse the ladder losses show (-4,400 over the same window). Tuning
an endgame behaviour on opponents that never trigger it measures nothing.

These are the ladder opponents we actually faced, replaying their recorded
actions with only our side swapped. Same caveats as ladder_sweep.py: they are
traces rather than policies, and the sample is small and fixed.
"""
import importlib.util, json, multiprocessing, os, statistics, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from planner.simulate import Simulator  # noqa: E402
from planner.ladder_sweep import make_trace_agent  # noqa: E402
from route.bake import bake  # noqa: E402

LIVE = {"_PREEMPT_MIN_FUTURE_QUANTITY": 0, "_PREEMPT_MAX_BATCH": 30, "INTERVENE": 1,
        "IV_DUMP_FRAC": 0.7, "IV_LEAD": 3, "IV_FERT": 1, "IV_STRUCT": 1,
        "IV_MIN_PRICE": 0.20}
DEF = ["6c12s_4q_first_yarn", "6c12s_4q_second_yarn", "6c8s_3q", "10c4s_3q", "8c6s_3q"]
B0 = {**LIVE, "TAPE_MAP": ["6c12s_4q_second_yarn"] + DEF[1:]}

V = [("live", dict(B0))]
for sd in (18, 20, 22, 24):
    V.append((f"stop{sd}", {**B0, "IV_STOP_DAY": sd}))
for sd, ld in ((20, 0.3), (22, 0.3), (20, 0.5)):
    V.append((f"stop{sd}_late{int(ld*100)}", {**B0, "IV_STOP_DAY": sd, "IV_LATE_DUMP": ld}))
for f in (0.40, 0.55, 0.70, 0.85):
    V.append((f"adapt_f{int(f*100)}", {**B0, "IV_ADAPT": 1, "IV_MARGINAL_FLOOR": f}))
_n = [0]


def run(job):
    n, path, ep, seat = job
    try:
        d = json.load(open(os.path.join(ROOT, "replays", f"episode-{ep}-replay.json")))
        cfg = d.get("configuration", {})
        _n[0] += 1
        s = importlib.util.spec_from_file_location(f"ld_{os.getpid()}_{_n[0]}", path)
        m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
        me = getattr(m, "_submission_entry", None) or m.agent
        opp = make_trace_agent(d["steps"], 1 - seat)
        sim = Simulator.new_episode(configuration={k: v for k, v in cfg.items() if k in
            ("boardSize", "startingMoney", "maxMarketOrdersPerTurn", "turnsPerDay",
             "shedCapacity", "weedSpawnChance", "townShopUnlockInterval",
             "townShopSellInterval", "townCenterSellInterval", "farmHandCostMult",
             "episodeSteps", "marketParams")}, seed=d["info"]["seed"])
        pair = [me, opp] if seat == 0 else [opp, me]
        m0, m1 = sim.run_episode(pair[0], pair[1])
        us, them = (m0, m1) if seat == 0 else (m1, m0)
        return (n, ep, us - them, None)
    except Exception:
        import traceback
        return (n, ep, 0.0, traceback.format_exc()[-150:])


def main():
    paths = {}
    for n, p in V:
        q = os.path.join(ROOT, "agents", "dg2", f"{n}.py")
        os.makedirs(os.path.dirname(q), exist_ok=True)
        bake(p, out=q, note=n); paths[n] = q
    rows = json.load(open("/tmp/claude-1818200050/-home-yilewang/"
                          "12e9e33c-6cb5-4a53-939b-9c2b0d0b6776/scratchpad/losses2.json"))
    seen, games = set(), []
    for name in ("struct", "b0"):
        for r in rows[name]:
            if r["ep"] in seen:
                continue
            if os.path.exists(os.path.join(ROOT, "replays", f"episode-{r['ep']}-replay.json")):
                seen.add(r["ep"]); games.append((r["ep"], r["seat"]))
    print(f"{len(games)} real ladder replays")
    jobs = [(n, paths[n], ep, seat) for n, _ in V for ep, seat in games]
    t0 = time.time()
    with multiprocessing.get_context("forkserver").Pool(12) as pool:
        res = pool.map(run, jobs, chunksize=4)
    print(f"{time.time()-t0:.0f}s")
    errs = [r[3] for r in res if r[3]]
    if errs:
        print(f"{len(errs)} errors; first {errs[0]}")
    by = {}
    for n, ep, m, e in res:
        if not e:
            by.setdefault(n, {})[ep] = m
    base = by.get("live", {})
    print(f"{'variant':<18} {'mean margin':>13} {'record':>10} {'vs live':>10} {'t':>6}")
    out = []
    for n, _ in V:
        d = by.get(n, {})
        if not d:
            continue
        ms = list(d.values()); w = sum(1 for x in ms if x > 0)
        diffs = [d[k] - base[k] for k in d if k in base]
        dm = statistics.mean(diffs) if diffs else 0.0
        dse = (statistics.pstdev(diffs) / len(diffs) ** 0.5) if len(diffs) > 1 else 0.0
        out.append((n, statistics.mean(ms), w, len(ms), dm, dm / dse if dse else 0.0))
    out.sort(key=lambda r: -r[4])
    for n, mm, w, tot, dm, t in out:
        print(f"{n:<18} {mm:>13,.0f} {w:>4}/{tot:<5} {dm:>+10,.0f} {t:>6.1f}")


if __name__ == "__main__":
    main()
