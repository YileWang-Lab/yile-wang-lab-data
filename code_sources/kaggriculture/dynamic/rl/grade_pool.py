"""Grade every available agent by how often our RL start point beats it.

The training pool is all reference agents we beat 0.7% of the time. That is 40%
of the compute spent on episodes whose sign term is a constant, so they teach
nothing -- the same zero-variance failure that made the reward useless earlier,
surviving in the half of the mix that was not fixed. Self-play win rate has
climbed to 54-100% against a frozen snapshot while pool win rate has never left
0.0%, which is what "improving, but with no rung within reach" looks like.

A curriculum needs opponents that lose sometimes. This measures every candidate
in agents/, opponents/ and pool/ against the RL identity policy and sorts them,
so a ladder can be built from the ones that sit in the informative band rather
than guessed at. Nothing is downloaded: 376 baked variants from previous
experiments are already on disk, spanning early GA generations to the shipped
build, and their strength was never catalogued.

    python dynamic/rl/grade_pool.py [seeds] [workers] [max_agents]

Writes logs/rl/ladder.json, ordered easiest first.
"""
import json
import multiprocessing as mp
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _HERE]
sys.path.insert(0, ROOT)

OUT = os.path.join(ROOT, "logs", "rl", "ladder.json")
_n = [0]
_W = {}


def candidates(limit=None):
    seen, out = set(), []
    for sub in ("opponents", "opponents/external", "opponents/rungs",
                "agents", "pool"):
        d = os.path.join(ROOT, sub)
        if not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for f in sorted(files):
                if not f.endswith(".py") or f.startswith("_"):
                    continue
                p = os.path.join(root, f)
                try:
                    size = os.path.getsize(p)
                except OSError:
                    continue
                if size < 2000:            # extractor stubs, not agents
                    continue
                key = (f, size)
                if key in seen:            # the same build baked twice
                    continue
                seen.add(key)
                out.append(p)
    random.Random(7).shuffle(out)
    return out[:limit] if limit else out


def _init(genome):
    _W["genome"] = genome


def _mk_identity():
    import importlib.util
    _n[0] += 1
    path = os.path.join(ROOT, "dynamic", "rl", "agent_rl.py")
    spec = importlib.util.spec_from_file_location(f"g_{os.getpid()}_{_n[0]}", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    from dynamic.rl.net import DailyNet, SellNet, NumpyPolicy, to_numpy_weights
    m.configure(_W["genome"])
    m.set_policy(NumpyPolicy(to_numpy_weights(DailyNet().eval(), SellNet().eval()),
                             explore=False))
    return m.agent


def _mk_file(path):
    import importlib.util
    _n[0] += 1
    spec = importlib.util.spec_from_file_location(f"o_{os.getpid()}_{_n[0]}", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    fn = getattr(m, "_submission_entry", None)
    if fn is None:
        fn = getattr(m, "agent", None)
    return fn


def play(job):
    path, seed, seat = job
    try:
        from planner.simulate import Simulator
        me = _mk_identity()
        op = _mk_file(path)
        if op is None:
            return (path, seed, seat, None, "no agent callable")
        pair = [me, op] if seat == 0 else [op, me]
        sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
        m0, m1 = sim.run_episode(pair[0], pair[1])
        us, them = (m0, m1) if seat == 0 else (m1, m0)
        return (path, seed, seat, us - them, None)
    except Exception as e:
        return (path, seed, seat, None, str(e)[:90])


def main():
    n_seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 120

    from route.search import to_params
    g = json.load(open(os.path.join(ROOT, "dynamic", "best_genome3.json")))["genome"]
    genome = to_params(dict(g))
    genome["OPP_MODEL"] = 1
    genome["SHED_PANIC_FRACTION"] = 0.40

    cands = candidates(limit)
    rng = random.Random(4242)
    seeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(n_seeds)]
    jobs = [(p, s, st) for p in cands for s in seeds for st in (0, 1)]
    print(f"{len(cands)} candidate agents x {n_seeds} seeds x 2 seats "
          f"= {len(jobs):,} games, {workers} workers", flush=True)
    t0 = time.time()
    with mp.get_context("forkserver").Pool(workers, initializer=_init,
                                           initargs=(genome,)) as pool:
        res = pool.map(play, jobs, chunksize=2)
    print(f"{time.time() - t0:.0f}s", flush=True)

    per = {}
    bad = {}
    for path, seed, seat, margin, err in res:
        if err:
            bad[path] = err
            continue
        per.setdefault(path, {}).setdefault(seed, []).append(margin)
    rows = []
    for path, byseed in per.items():
        paired = [sum(v) for v in byseed.values() if len(v) == 2]
        if not paired:
            continue
        wins = sum(1 for x in paired if x > 0)
        rows.append({"path": os.path.relpath(path, ROOT),
                     "win_pct": 100.0 * wins / len(paired),
                     "mean_paired": sum(paired) / len(paired),
                     "n": len(paired)})
    rows.sort(key=lambda r: -r["win_pct"])
    json.dump(rows, open(OUT, "w"), indent=1)

    print(f"\n{len(rows)} graded, {len(bad)} unusable")
    print(f"{'win% vs our start':>18}  {'mean paired':>12}  agent")
    band = [r for r in rows if 20.0 <= r["win_pct"] <= 80.0]
    for r in rows[:8] + [None] + band[:1] + [None] + rows[-6:]:
        if r is None:
            print("  ...")
            continue
        print(f"{r['win_pct']:>17.0f}%  {r['mean_paired']:>+12,.0f}  {r['path']}")
    print(f"\nIN THE INFORMATIVE BAND (we win 20-80%): {len(band)} agents")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
