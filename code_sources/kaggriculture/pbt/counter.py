"""Counter-parameter matrix: which runtime constants beat which opponent.

The field is heterogeneous -- one fixed constant set cannot be optimal against
both the strongest reference and the weakest. This measures a full
config x opponent grid and, alongside it, records each opponent's public
feature vector early in the game, so the winning config can be selected at
runtime from what the opponent's farm actually looks like.
"""
import csv, itertools, json, multiprocessing, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

FEATURE_STEP = 96          # day 4: builds are committed, tapes have diverged
MODELS = os.path.join(ROOT, "models")
os.makedirs(MODELS, exist_ok=True)

CONFIGS = {
    "base":    {},
    "sub_v12": {"_PREEMPT_MIN_FUTURE_QUANTITY": 0, "_PREEMPT_MAX_BATCH": 30},
    "aggro":   {"_PREEMPT_FRACTION": 3.0, "_PREEMPT_MAX_BATCH": 40,
                "_PREEMPT_MAX_CLONE_DISTANCE": 40, "_PREEMPT_START": 0},
    "early":   {"_PREEMPT_MIN_FUTURE_QUANTITY": 0, "_PREEMPT_MAX_BATCH": 30,
                "_PREEMPT_START": 0, "_PREEMPT_STOP": 716},
    "clone40": {"_PREEMPT_MIN_FUTURE_QUANTITY": 0, "_PREEMPT_MAX_BATCH": 30,
                "_PREEMPT_MAX_CLONE_DISTANCE": 40},
    "off":     {"_PREEMPT_ENABLED": False},
}
OPPONENTS = {
    "ref_A": "kaggriculture-multi-route-farming-agent",
    "ref_B": "kaggriculture-3000-socre",
    "ref_C": "kaggriculture-rank-your-agent",
    "ref_D": "kaggriculture-ttv1",
    "ref_E": "v111-8c4s-economic-core-premium-lead",
    "ref_F": "ref-pipeline-highscore",
}
SEEDS = [11, 47, 101, 2029, 3137, 7717, 5, 19]

FEATURE_KEYS = ("hands", "quadrants", "money", "COW", "SHEEP", "GOOSE",
                "WHEAT", "MELON", "STRAWBERRY", "PASTURE", "COOP", "WEED")


def features(farm):
    c = {k: 0 for k in FEATURE_KEYS}
    c["hands"] = len(farm.get("hands") or [])
    c["quadrants"] = len(farm.get("unlocked_quadrants") or [])
    c["money"] = float(farm.get("money", 0) or 0)
    for row in farm.get("tiles") or []:
        for t in row:
            if not isinstance(t, dict):
                continue
            for f in ("crop", "animal", "kind"):
                v = str(t.get(f, "")).upper()
                if v in c:
                    c[v] += 1
                    break
    return c


def play(job):
    from kaggle_environments import make
    from route.batch import load_base
    from search.evaluate import load_ref_agent
    cfg, oid, seed, seat = job
    grabbed = {}

    def spy(obs):
        o = obs if isinstance(obs, dict) else dict(obs)
        st = int(o.get("day", 0)) * 24 + int(o.get("hour", 0))
        if st == FEATURE_STEP and not grabbed:
            fs = (o.get("farms") or [])
            if len(fs) > 1:
                grabbed.update(features(fs[1 - seat]))
        return me(obs)
    try:
        me = load_base(CONFIGS[cfg]).agent
        other = load_ref_agent(OPPONENTS[oid])
        pair = [spy, other] if seat == 0 else [other, spy]
        env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": seed},
                   debug=False)
        env.run(pair)
        f = env.steps[-1]
        return (cfg, oid, seed, float(f[seat].observation["farms"][seat]["money"]),
                float(f[1 - seat].observation["farms"][1 - seat]["money"]), grabbed)
    except Exception:
        return (cfg, oid, seed, 0.0, 0.0, {})


def main():
    jobs = [(c, o, s, i % 2) for c in CONFIGS for o in OPPONENTS
            for i, s in enumerate(SEEDS)]
    ctx = multiprocessing.get_context("forkserver")
    with ctx.Pool(26) as p:
        res = p.map(play, jobs)

    with open(os.path.join(ROOT, "opponent_features.csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["opponent", "seed"] + list(FEATURE_KEYS))
        seen = set()
        for cfg, oid, seed, _, _, feat in res:
            if feat and (oid, seed) not in seen:
                seen.add((oid, seed))
                w.writerow([oid, seed] + [feat.get(k, 0) for k in FEATURE_KEYS])

    grid, best = {}, {}
    print(f"{'config':<10}" + "".join(f"{o:>9}" for o in OPPONENTS) + f"{'总胜率':>9}")
    for cfg in CONFIGS:
        row, tw, tg = [], 0, 0
        for oid in OPPONENTS:
            rows = [r for r in res if r[0] == cfg and r[1] == oid]
            w_ = sum(1 for r in rows if r[3] > r[4]); n = len(rows)
            grid[(cfg, oid)] = w_ / max(n, 1); row.append(w_ / max(n, 1))
            tw += w_; tg += n
        print(f"{cfg:<10}" + "".join(f"{v:>8.0%} " for v in row) + f"{tw/max(tg,1):>8.0%}")
    for oid in OPPONENTS:
        best[oid] = max(CONFIGS, key=lambda c: grid[(c, oid)])
    print("\n每个对手的克星配置:", json.dumps(best, ensure_ascii=False))
    centroids = {}
    for oid in OPPONENTS:
        fs = [r[5] for r in res if r[1] == oid and r[5]]
        if fs:
            centroids[oid] = {k: sum(f.get(k, 0) for f in fs) / len(fs)
                              for k in FEATURE_KEYS}
    json.dump({"best_config": best, "configs": CONFIGS, "centroids": centroids,
               "feature_keys": list(FEATURE_KEYS), "feature_step": FEATURE_STEP},
              open(os.path.join(MODELS, "counter_params.json"), "w"), indent=1)
    print("saved -> models/counter_params.json, opponent_features.csv")


if __name__ == "__main__":
    main()
