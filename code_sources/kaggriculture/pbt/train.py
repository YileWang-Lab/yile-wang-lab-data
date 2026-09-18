"""Population-based training loop.

The engine is strictly 2-player (`"agents": [2]`), so a variant cannot share a
board with three opponents. Equivalent formulation: the variant plays each of
its three sampled opponents head-to-head, and its group rank is
`1 + (opponents that beat it)`, giving the same 1..4 scale the protocol asks for.
"""
import argparse, csv, itertools, json, multiprocessing, os, random, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pbt import pool as P                                    # noqa: E402
from pbt.variants import make_variants                       # noqa: E402
from route.bake import bake                                  # noqa: E402

AGENTS = os.path.join(ROOT, "agents")
SCORES = os.path.join(ROOT, "scores")
LOGS = os.path.join(ROOT, "logs")
for d in (AGENTS, SCORES, LOGS):
    os.makedirs(d, exist_ok=True)


def _agent_for(spec):
    """spec: {'ref': name} for a reference, or {'path': file} for a baked agent."""
    from search.evaluate import load_ref_agent
    if spec.get("ref"):
        return load_ref_agent(spec["ref"])
    import importlib.util
    global _c
    _c[0] += 1
    s = importlib.util.spec_from_file_location(f"pbt_{_c[0]}_{os.getpid()}", spec["path"])
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m.agent


_c = [0]


def play(job):
    from kaggle_environments import make
    vid, vspec, oid, ospec, seed, seat = job
    try:
        me, other = _agent_for(vspec), _agent_for(ospec)
        pair = [me, other] if seat == 0 else [other, me]
        env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": seed},
                   debug=False)
        env.run(pair)
        f = env.steps[-1]
        return (vid, oid, float(f[seat].observation["farms"][seat]["money"]),
                float(f[1 - seat].observation["farms"][1 - seat]["money"]), None)
    except Exception as exc:
        return (vid, oid, 0.0, 0.0, repr(exc)[:160])


def run_round(state, rng, workers, seeds):
    rnd = state["round"] + 1
    genes = state["gene_pool"]
    weights = [max(g.get("win_rate", 0.5), 0.05) ** 3 for g in genes]
    base = dict(rng.choices(genes, weights=weights, k=1)[0]["genome"])
    base.pop("FORCE_ROUTE", None)

    variants = make_variants(base, rng)
    specs = {}
    for i, (note, genome) in enumerate(variants, start=1):
        path = os.path.join(AGENTS, f"round{rnd}_v{i}.py")
        bake(genome, out=path, note=f"round {rnd} variant v{i} -- {note}")
        specs[f"v{i}"] = {"path": path, "genome": genome, "note": note}

    pool = state["opponent_pool"]
    jobs, sampled = [], {}
    for vid, spec in specs.items():
        opps = rng.sample(pool, min(3, len(pool)))
        sampled[vid] = [o["id"] for o in opps]
        for j, o in enumerate(opps):
            for k, sd in enumerate(seeds):
                jobs.append((vid, {"path": spec["path"]}, o["id"], o, sd, (j + k) % 2))

    ctx = multiprocessing.get_context("forkserver")
    with ctx.Pool(processes=workers) as pl:
        res = pl.map(play, jobs)

    rows, summary = [], {}
    for vid in specs:
        mine = [r for r in res if r[0] == vid and r[4] is None]
        beaten_by = 0
        income = sum(r[2] for r in mine) / max(len(mine), 1)
        for oid in sampled[vid]:
            g = [r for r in mine if r[1] == oid]
            if g and sum(r[2] for r in g) < sum(r[3] for r in g):
                beaten_by += 1
        rank = 1 + beaten_by
        summary[vid] = {"rank": rank, "income": income,
                        "opponents": sampled[vid], "note": specs[vid]["note"],
                        "wins": sum(1 for r in mine if r[2] > r[3]), "games": len(mine)}
        rows.append([vid, "|".join(sampled[vid]), rank, round(income)])

    with open(os.path.join(SCORES, f"round{rnd}.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["variant_id", "opponents", "rank", "income"])
        w.writerows(rows)

    def _key(v):
        s_ = summary[v]
        return (s_["rank"], -s_["wins"] / max(s_["games"], 1))

    champ = min(summary, key=_key)
    c = summary[champ]

    # Streak is judged against the ENTIRE pool, not the three opponents the
    # champion happened to draw. Sampling three from a pool that contains a 0%
    # agent makes rank==1 nearly free, and the protocol's stop condition fired
    # in five rounds on that technicality.
    gauntlet = [(champ, {"path": specs[champ]["path"]}, o["id"], o, sd, k % 2)
                for o in pool for k, sd in enumerate(seeds)]
    with ctx.Pool(processes=workers) as pl:
        gres = pl.map(play, gauntlet)
    beaten = []
    for o in pool:
        rows_o = [r for r in gres if r[1] == o["id"] and r[4] is None]
        if rows_o and sum(r[2] for r in rows_o) <= sum(r[3] for r in rows_o):
            beaten.append(o["id"])
    swept = not beaten
    c["gauntlet_losses"] = beaten
    state["streak"] = state["streak"] + 1 if swept else 0
    state["round"] = rnd

    champ_path = os.path.join(AGENTS, f"champion_round{rnd}.py")
    bake(specs[champ]["genome"], out=champ_path,
         note=f"round {rnd} CHAMPION -- {c['note']}")
    # Store the win rate as the gene's fitness: rank has only four levels and
    # ties constantly, so it cannot order the gene pool.
    state["gene_pool"].append({"id": f"r{rnd}_{champ}", "genome": specs[champ]["genome"],
                               "rank": c["rank"],
                               "win_rate": c["wins"] / max(c["games"], 1),
                               "generation": rnd})
    state["opponent_pool"].append({"id": f"r{rnd}_{champ}", "ref": None,
                                   "path": champ_path, "score_history": [c["income"]],
                                   "generation": rnd})
    P.prune(state)
    state["history"].append({"round": rnd, "champion": champ, "rank": c["rank"],
                             "income": c["income"], "note": c["note"],
                             "streak": state["streak"]})
    return rnd, summary, champ, champ_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--workers", type=int, default=26)
    ap.add_argument("--seeds", type=int, nargs="*", default=[11, 47])
    ap.add_argument("--stop-streak", type=int, default=5)
    a = ap.parse_args()

    state = P.load()
    rng = random.Random(1000 + state["round"])
    for _ in range(a.rounds):
        t0 = time.time()
        rnd, summary, champ, cpath = run_round(state, rng, a.workers, a.seeds)
        P.save(state)
        print(f"\n=== ROUND {rnd} ({time.time()-t0:.0f}s) ===")
        print(f"{'变体':<5}{'平均排名':>9}{'胜/局':>9}{'收入':>11}  改动")
        for vid in sorted(summary, key=lambda v: (summary[v]['rank'],
                                                   -summary[v]['wins'] / max(summary[v]['games'], 1))):
            s = summary[vid]
            print(f"{vid:<5}{s['rank']:>9}{str(s['wins'])+'/'+str(s['games']):>9}"
                  f"{s['income']:>11,.0f}  {s['note']}")
        lost = summary[champ].get("gauntlet_losses") or []
        print(f"冠军 {champ} rank={summary[champ]['rank']} "
              f"({'优秀' if summary[champ]['rank'] <= 2 else '普通'})  "
              f"全池横扫={'是' if not lost else '否 输给 ' + ','.join(lost)}  "
              f"连胜={state['streak']}/{a.stop_streak}")
        print(f"对手池={len(state['opponent_pool'])} 基因池={len(state['gene_pool'])} -> {cpath}")
        if state["streak"] >= a.stop_streak:
            print(f"\n*** 终止条件达成：连续 {state['streak']} 轮横扫全部对手 ***")
            break


if __name__ == "__main__":
    main()
