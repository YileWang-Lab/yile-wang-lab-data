"""Find a configuration that specifically beats our current submission.

Two purposes: it gives the pool a genuine adversary tuned against our style
rather than a generic strong agent, and it measures how exploitable the
submission actually is. If some config beats sub_v12 well above 50%, a ladder
opponent could find it too.
"""
import itertools, json, multiprocessing, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TARGET = {"_PREEMPT_MIN_FUTURE_QUANTITY": 0, "_PREEMPT_MAX_BATCH": 30}
SEEDS = list(range(1, 21))          # 20 seeds x 2 seats = 40 games per candidate

GRID = []
for frac in (0.0, 1.0, 2.0, 3.5):
    for batch in (8, 30, 60):
        for clone in (6, 40):
            for start in (0, 120):
                GRID.append({"_PREEMPT_FRACTION": frac, "_PREEMPT_MAX_BATCH": batch,
                             "_PREEMPT_MAX_CLONE_DISTANCE": clone,
                             "_PREEMPT_START": start,
                             "_PREEMPT_MIN_FUTURE_QUANTITY": 0})
GRID.append({"_PREEMPT_ENABLED": False})
GRID.append({})


def play(job):
    from kaggle_environments import make
    from route.batch import load_base
    idx, seed, seat = job
    try:
        me = load_base(GRID[idx]).agent
        other = load_base(TARGET).agent
        pair = [me, other] if seat == 0 else [other, me]
        env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": seed},
                   debug=False)
        env.run(pair)
        f = env.steps[-1]
        return (idx, float(f[seat].observation["farms"][seat]["money"]),
                float(f[1 - seat].observation["farms"][1 - seat]["money"]))
    except Exception:
        return (idx, 0.0, 0.0)


def main():
    jobs = [(i, s, seat) for i in range(len(GRID)) for s in SEEDS for seat in (0, 1)]
    ctx = multiprocessing.get_context("forkserver")
    with ctx.Pool(26) as p:
        res = p.map(play, jobs)
    rows = []
    for i, cfg in enumerate(GRID):
        r = [x for x in res if x[0] == i]
        w = sum(1 for x in r if x[1] > x[2]); n = len(r)
        rows.append((w / max(n, 1), w, n, cfg))
    rows.sort(key=lambda t: -t[0])
    print(f"{'对 sub_v12 胜率':>14}{'胜/局':>9}   配置")
    for wr, w, n, cfg in rows[:8]:
        print(f"{wr:>13.0%}{str(w)+'/'+str(n):>9}   {cfg}")
    print("...")
    for wr, w, n, cfg in rows[-3:]:
        print(f"{wr:>13.0%}{str(w)+'/'+str(n):>9}   {cfg}")
    json.dump({"best": rows[0][3], "win_rate": rows[0][0]},
              open(os.path.join(ROOT, "models", "adversary.json"), "w"), indent=1)
    print(f"\n最强反制 -> models/adversary.json  ({rows[0][0]:.0%})")


if __name__ == "__main__":
    main()
