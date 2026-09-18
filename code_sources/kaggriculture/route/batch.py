"""Batch variant evaluator: score N agent variants on one fixed matchup set.

Every variant plays the identical seeds and seats, so the scores are directly
comparable and a difference is a signal rather than seed noise. A variant is
(params -> base module globals) plus an optional overlay hook.
"""
import importlib.util, json, multiprocessing, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
BASE_PATH = os.path.join(ROOT, "opponents", "kaggriculture-multi-route-farming-agent.py")
_n = [0]

SEEDS = [11, 47, 101, 2029, 3137, 7717]
FIELD = ["BASE", "kaggriculture-3000-socre", "kaggriculture-rank-your-agent",
         "v111-8c4s-economic-core-premium-lead"]


def load_base(params=None):
    _n[0] += 1
    spec = importlib.util.spec_from_file_location(f"bv{_n[0]}_{os.getpid()}", BASE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for k, v in (params or {}).items():
        if k.startswith("_"):
            setattr(mod, k, v)
    return mod


def matchups():
    out = []
    for i, s in enumerate(SEEDS):
        for opp in FIELD:
            out.append((opp, s, i % 2))
    return out


def play(job):
    from kaggle_environments import make
    from search.evaluate import load_ref_agent
    vid, params, (opp, seed, seat) = job
    try:
        me = load_base(params).agent
        other = load_base(None).agent if opp == "BASE" else load_ref_agent(opp)
        pair = [me, other] if seat == 0 else [other, me]
        env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": seed},
                   debug=False)
        env.run(pair)
        f = env.steps[-1]
        return (vid, opp, float(f[seat].observation["farms"][seat]["money"]),
                float(f[1 - seat].observation["farms"][1 - seat]["money"]), None)
    except Exception as exc:
        return (vid, opp, 0.0, 0.0, repr(exc)[:160])


def run(variants, workers=26):
    """variants: {vid: params}. Returns {vid: (mean_money, wins, games, beat_base)}"""
    jobs = [(vid, p, m) for vid, p in variants.items() for m in matchups()]
    ctx = multiprocessing.get_context("forkserver")
    with ctx.Pool(processes=workers) as pool:
        res = pool.map(play, jobs)
    agg = {}
    for vid in variants:
        rows = [r for r in res if r[0] == vid and r[4] is None]
        if not rows:
            agg[vid] = (0.0, 0, 0, 0.0); continue
        money = sum(r[2] for r in rows) / len(rows)
        wins = sum(1 for r in rows if r[2] > r[3])
        vb = [r for r in rows if r[1] == "BASE"]
        beat = sum(1 for r in vb if r[2] > r[3]) / max(len(vb), 1)
        agg[vid] = (money, wins, len(rows), beat)
    return agg
