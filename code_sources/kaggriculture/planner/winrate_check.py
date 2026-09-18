"""Measure the bucket-0 tape swap by WIN RATE, not paired margin.

Everything in this project has been optimised on paired margin, on HANDOFF
rule 1's reasoning that win rate is meaningless for same-tape matchups. That is
correct for MEASURING STRENGTH, but the ladder does not rank by margin: Kaggle's
publicScore is a TrueSkill-style skill rating updated on win/loss. Margin does
not enter it.

For most changes the two agree -- a stronger agent wins more often AND by more.
They come apart for a FAT-TAILED change, which is exactly what a tape swap is:
it replaces the whole 30-day schedule, so it either does nothing or changes
everything. The live ladder record is consistent with that divergence:

    55614625 (b0)     second half of its games: 60% win, mean +3,126
    55600561 (v3)     second half of its games: 69% win, mean +1,506

i.e. higher margin, LOWER win rate -- which is the wrong trade for rating.

This measures both metrics on identical paired games so they can be compared
directly, and reports per-game win rate rather than paired margin.
"""
import importlib.util, json, multiprocessing, os, random, statistics, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from planner.simulate import Simulator  # noqa: E402
from route.bake import bake  # noqa: E402

SHIPPED = {"_PREEMPT_MIN_FUTURE_QUANTITY": 0, "_PREEMPT_MAX_BATCH": 30,
           "INTERVENE": 1, "IV_DUMP_FRAC": 0.8, "IV_LEAD": 3, "IV_FERT": 1}
LIVE = {**SHIPPED, "IV_STRUCT": 1, "IV_DUMP_FRAC": 0.7, "IV_MIN_PRICE": 0.20}
DEFAULT_MAP = ["6c12s_4q_first_yarn", "6c12s_4q_second_yarn", "6c8s_3q",
               "10c4s_3q", "8c6s_3q"]
B0_MAP = ["6c12s_4q_second_yarn"] + DEFAULT_MAP[1:]

VARIANTS = [("v3", dict(SHIPPED)), ("struct", dict(LIVE)),
            ("b0", {**LIVE, "TAPE_MAP": B0_MAP})]
OPPONENTS = ["kaggriculture-multi-route-farming-agent",
             "v111-8c4s-economic-core-premium-lead",
             "kaggriculture-frontier-the-soil-remembers-rain",
             "kaggriculture-3000-socre",
             "kaggriculture-breaking-the-tie-2883-score",
             "kaggriculture-rank-your-agent",
             "15-16-strict-future-v25-meta-reset",
             "strong-barnyard-economist",
             "kaggriculture-pure-architecture-2600-elo-v3"]
_n = [0]


def _load(p):
    _n[0] += 1
    s = importlib.util.spec_from_file_location(f"wr_{os.getpid()}_{_n[0]}", p)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return getattr(m, "_submission_entry", None) or m.agent


def play(job):
    lbl, path, opp, seed, seat = job
    try:
        me = _load(path); op = _load(os.path.join(ROOT, "opponents", f"{opp}.py"))
        pair = [me, op] if seat == 0 else [op, me]
        sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
        m0, m1 = sim.run_episode(pair[0], pair[1])
        us, them = (m0, m1) if seat == 0 else (m1, m0)
        return (lbl, opp, seed, seat, us - them, None)
    except Exception:
        import traceback
        return (lbl, opp, seed, seat, 0.0, traceback.format_exc()[-200:])


def main():
    n_seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    paths = {}
    for name, params in VARIANTS:
        p = os.path.join(ROOT, "agents", "tapes", f"wr_{name}.py")
        bake(params, out=p, note=f"winrate {name}"); paths[name] = p
    rng = random.Random(4242)
    seeds = [rng.randrange(10**6, 2**31 - 1) for _ in range(n_seeds)]
    jobs = [(n, paths[n], o, s, seat) for n, _ in VARIANTS
            for o in OPPONENTS for s in seeds for seat in (0, 1)]
    print(f"{len(VARIANTS)} variants x {len(OPPONENTS)} opp x {n_seeds} seeds x 2 = {len(jobs):,} games")
    t0 = time.time()
    with multiprocessing.get_context("forkserver").Pool(24) as pool:
        res = pool.map(play, jobs, chunksize=4)
    print(f"elapsed {time.time()-t0:.0f}s")

    games = {}
    for lbl, opp, seed, seat, m, err in res:
        if not err:
            games.setdefault(lbl, {})[(opp, seed, seat)] = m
    base = games.get("struct", {})
    print()
    print(f"{'variant':<8} {'games':>7} {'WIN RATE':>10} {'mean margin':>13} "
          f"{'vs struct: dWin':>16} {'dMargin':>11}")
    for name, _ in VARIANTS:
        g = games.get(name, {})
        if not g:
            continue
        ms = list(g.values())
        wr = sum(1 for m in ms if m > 0) / len(ms)
        keys = [k for k in g if k in base]
        dwin = statistics.mean([(1 if g[k] > 0 else 0) - (1 if base[k] > 0 else 0) for k in keys]) if keys else 0
        dmar = statistics.mean([g[k] - base[k] for k in keys]) if keys else 0
        print(f"{name:<8} {len(ms):>7,} {wr:>9.1%} {statistics.mean(ms):>13,.0f} "
              f"{dwin:>+15.2%} {dmar:>+11,.0f}")
    print()
    print("dWin is the per-game win-rate change on identical (opponent, seed, seat)")
    print("games -- the quantity the ladder rating actually responds to.")


if __name__ == "__main__":
    main()
