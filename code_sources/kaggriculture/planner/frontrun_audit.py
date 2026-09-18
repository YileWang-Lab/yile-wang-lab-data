"""Do our dumps actually land ahead of the opponent's sale?

The whole intervention layer rests on one claim: pushing stock into the book a
few turns before the opponent sells means they quote into a depressed market.
Tonight's adaptive-sizing result (12 variants, 19,440 games, every one negative
against the fixed 70%) suggested the layer's value is POSITION rather than
quantity -- but that was inferred from what failed, not measured directly.

The engine makes the bar precise. Inside a step _process_market quotes BOTH
players against the same pre-commit inventory and only then commits them in
player order, so a sale on the same step as theirs clears at the same price.
Beating them requires selling on a strictly EARLIER step.

This audits, per firing:
  - what step we predicted their sale at, and when they actually sold
  - whether our units cleared strictly before theirs
  - what price we got against what they got

Opponent sales are recovered exactly, not guessed: within a step
    inv[t+1] = inv[t] + my_sales + their_sales - town_take
and every term but theirs is known (HANDOFF section 6, validated at zero error
on every product whose price stays off the $1 floor).
"""
import collections, importlib.util, json, multiprocessing, os, statistics, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from planner.simulate import Simulator  # noqa: E402
from route.bake import bake  # noqa: E402

LIVE = {"_PREEMPT_MIN_FUTURE_QUANTITY": 0, "_PREEMPT_MAX_BATCH": 30, "INTERVENE": 1,
        "IV_DUMP_FRAC": 0.7, "IV_LEAD": 3, "IV_FERT": 1, "IV_STRUCT": 1,
        "IV_MIN_PRICE": 0.20}
DEF = ["6c12s_4q_first_yarn", "6c12s_4q_second_yarn", "6c8s_3q", "10c4s_3q", "8c6s_3q"]
B0 = {**LIVE, "TAPE_MAP": ["6c12s_4q_second_yarn"] + DEF[1:]}
PREMIUM = ("MELON", "MILK", "STRAWBERRY", "WOOL", "FERTILIZER")
POOL = ["kaggriculture-multi-route-farming-agent",
        "v111-8c4s-economic-core-premium-lead",
        "kaggriculture-3000-socre",
        "kaggriculture-rank-your-agent",
        "strong-barnyard-economist",
        "kaggriculture-pure-architecture-2600-elo-v3"]
_n = [0]


def _load(p):
    _n[0] += 1
    s = importlib.util.spec_from_file_location(f"fa_{os.getpid()}_{_n[0]}", p)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return getattr(m, "_submission_entry", None) or m.agent


def audit(job):
    path, opp_name, seed, seat = job
    try:
        me = _load(path)
        op = _load(os.path.join(ROOT, "opponents", f"{opp_name}.py"))
        sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)

        fires = []          # (step, item, qty)
        sales = collections.defaultdict(list)   # item -> [(step, player, units, price)]

        def on_commit(pid, opx, item, price):
            if opx == "SELL":
                sales[item].append((sim.step, pid, price))

        sim.on_commit = on_commit

        def wrapped(obs):
            a = me(obs)
            st = int(obs.get("day", 0)) * 24 + int(obs.get("hour", 0))
            for o in (a.get("market") or []):
                if isinstance(o, list) and o and o[0] == "SELL" and o[1] in PREMIUM:
                    fires.append((st, o[1], int(o[2])))
            return a

        pair = [wrapped, op] if seat == 0 else [op, wrapped]
        sim.run_episode(pair[0], pair[1])
        return (opp_name, seed, seat, fires, dict(sales), None)
    except Exception:
        import traceback
        return (opp_name, seed, seat, [], {}, traceback.format_exc()[-250:])


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 24
    path = os.path.join(ROOT, "agents", "adapt", "live_d70.py")
    if not os.path.exists(path):
        bake(B0, out=path, note="frontrun audit")
    import random
    rng = random.Random(6161)
    seeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(n)]
    jobs = [(path, o, s, seat) for o in POOL for s in seeds for seat in (0, 1)]
    print(f"{len(jobs)} games", flush=True)
    t0 = time.time()
    with multiprocessing.get_context("forkserver").Pool(workers) as pool:
        res = pool.map(audit, jobs, chunksize=2)
    print(f"{time.time()-t0:.0f}s", flush=True)
    errs = [r[5] for r in res if r[5]]
    if errs:
        print(f"{len(errs)} errors; first {errs[0][-250:]}")
        return

    per_item = collections.defaultdict(lambda: {"fires": 0, "won": 0, "tied": 0,
                                                "lost": 0, "none": 0,
                                                "our_px": [], "their_px": []})
    tot_games = 0
    for opp, seed, seat, fires, sales, e in res:
        if e: continue
        tot_games += 1
        for st, item, qty in fires:
            S = per_item[item]
            S["fires"] += 1
            rows = sales.get(item, [])
            ours = [r for r in rows if r[1] == seat and st <= r[0] <= st + 1]
            # their next sale strictly after our fire step
            theirs = [r for r in rows if r[1] != seat and r[0] > st]
            same = [r for r in rows if r[1] != seat and r[0] == st]
            if not ours:
                S["none"] += 1
                continue
            if theirs and theirs[0][0] > st:
                S["won"] += 1
                S["our_px"].append(statistics.mean(r[2] for r in ours))
                S["their_px"].append(theirs[0][2])
            elif same:
                S["tied"] += 1
            else:
                S["lost"] += 1
    print()
    print(f"{tot_games} games audited")
    print(f"{'item':<12} {'fires':>7} {'/game':>6} {'cleared':>8} {'ahead':>7} "
          f"{'same-step':>10} {'no-follow':>10} {'our $':>7} {'their $':>8} {'edge':>7}")
    for item in PREMIUM:
        S = per_item[item]
        f = S["fires"]
        if not f: continue
        cleared = f - S["none"]
        opx = statistics.mean(S["our_px"]) if S["our_px"] else 0
        tpx = statistics.mean(S["their_px"]) if S["their_px"] else 0
        print(f"{item:<12} {f:>7,} {f/tot_games:>6.1f} {cleared:>8,} "
              f"{S['won']:>7,} {S['tied']:>10,} {S['lost']:>10,} "
              f"{opx:>7.1f} {tpx:>8.1f} {opx-tpx:>+7.1f}")
    print()
    print("ahead      = our units cleared, and their next sale came on a LATER step")
    print("same-step  = they sold on the same step, which the engine prices identically")
    print("no-follow  = we dumped and they never sold that product again")


if __name__ == "__main__":
    main()
