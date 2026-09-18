"""Build a large sparring pool from the top of the ladder.

Six reference agents is too small a pool -- it overfits, and today it showed:
we beat the kawa school reliably while going 50/50 against the 8c4s school.

The chain is: leaderboard teamId -> that team's submissions -> that submission's
episodes -> replay -> 719-step tape -> a runnable agent. Episode *metadata*
already carries `team_id`, `submission_id`, `reward` and `index` (the seat), so
the whole ladder can be mapped without downloading anything; only the episodes
actually chosen for extraction need the ~30MB replay.
"""
import argparse, json, os, sys, time
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
CACHE = os.path.join(ROOT, "pbt", "ladder_cache.json")
REPLAYS = os.path.join(ROOT, "replays")
POOL = os.path.join(ROOT, "pool")
os.makedirs(REPLAYS, exist_ok=True)
os.makedirs(POOL, exist_ok=True)


def _api():
    from kaggle.api.kaggle_api_extended import KaggleApi
    a = KaggleApi(); a.authenticate(); return a


def leaderboard(api, n=30):
    rows = api.competition_leaderboard_view("kaggriculture")
    out = []
    for r in rows[:n]:
        out.append({"team_id": int(getattr(r, "team_id", 0) or 0),
                    "team": getattr(r, "team_name", "?"),
                    "score": float(getattr(r, "score", 0) or 0)})
    return out


def crawl(api, teams, sleep=0.3):
    """Metadata only. Returns {episode_id: [{team,reward,seat,submission}, ...]}."""
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {"episodes": {}, "teams": {}}
    for t in teams:
        tid = str(t["team_id"])
        if tid in cache["teams"]:
            continue
        try:
            subs = api.competition_team_submissions(t["team_id"])
        except Exception as e:
            print(f"  {t['team']}: submissions failed {repr(e)[:60]}"); continue
        if not subs:
            continue
        best = max(subs, key=lambda s: float(getattr(s, "public_score", 0) or 0))
        sid = int(getattr(best, "id"))
        try:
            eps = api.competition_list_episodes(sid)
        except Exception as e:
            print(f"  {t['team']}: episodes failed {repr(e)[:60]}"); continue
        for e in eps:
            rec = []
            for a in (getattr(e, "agents", None) or []):
                rec.append({"team": getattr(a, "team_name", "?"),
                            "team_id": int(getattr(a, "team_id", 0) or 0),
                            "submission": int(getattr(a, "submission_id", 0) or 0),
                            "reward": float(getattr(a, "reward", 0) or 0),
                            "seat": int(getattr(a, "index", 0) or 0)})
            if len(rec) == 2:
                cache["episodes"][str(getattr(e, "id"))] = rec
        cache["teams"][tid] = {"team": t["team"], "score": t["score"],
                               "submission": sid, "n_episodes": len(eps)}
        print(f"  {t['team']:<22} score {t['score']:>7.1f}  sub {sid}  {len(eps)} episodes",
              flush=True)
        json.dump(cache, open(CACHE, "w"))
        time.sleep(sleep)
    return cache


def matrix(cache):
    """Real ladder head-to-head from metadata alone."""
    wl = defaultdict(lambda: [0, 0])
    margins = defaultdict(list)
    for eid, rec in cache["episodes"].items():
        a, b = rec
        if a["reward"] == b["reward"]:
            continue
        w, l = (a, b) if a["reward"] > b["reward"] else (b, a)
        wl[w["team"]][0] += 1
        wl[l["team"]][1] += 1
        margins[w["team"]].append(w["reward"] - l["reward"])
    return wl, margins


def pick_episodes(cache, team, k=2):
    """Episodes this team won, most decisive first."""
    got = []
    for eid, rec in cache["episodes"].items():
        for i, a in enumerate(rec):
            if a["team"] == team and a["reward"] > rec[1 - i]["reward"]:
                got.append((a["reward"] - rec[1 - i]["reward"], int(eid), a["seat"]))
    got.sort(reverse=True)
    return got[:k]


def extract_pool(api, cache, targets, per_team=2):
    """Download each target's most decisive wins and bake their tape into an agent.

    Every pool member is transplanted into the same runtime scaffolding (kawa's
    weed repair + hand alignment), so pool members differ only in their 719-step
    tape. That makes the pool a controlled comparison of *schedules*, which is
    what we want to spar against -- not an exact clone of each opponent's
    private runtime logic, which the replay does not expose anyway.
    """
    from pbt.extract_tape import extract, build_agent
    BASE = os.path.join(ROOT, "opponents",
                        "kaggriculture-multi-route-farming-agent.py")
    made = []
    for team in targets:
        picks = pick_episodes(cache, team, k=per_team)
        if not picks:
            print(f"  {team}: no wins cached"); continue
        margin, eid, seat = picks[0]
        path = os.path.join(REPLAYS, f"episode-{eid}-replay.json")
        if not os.path.exists(path):
            try:
                api.competition_episode_replay(eid, path=REPLAYS, quiet=True)
            except Exception as e:
                print(f"  {team}: download failed {repr(e)[:60]}"); continue
        if not os.path.exists(path):
            cand = [f for f in os.listdir(REPLAYS) if str(eid) in f]
            if not cand:
                print(f"  {team}: replay missing"); continue
            path = os.path.join(REPLAYS, cand[0])
        try:
            tape, d = extract(path, seat)
        except Exception as e:
            print(f"  {team}: extract failed {repr(e)[:60]}"); continue
        safe = "".join(c if c.isalnum() else "_" for c in team)[:24]
        out = os.path.join(POOL, f"pool_{safe}.py")
        build_agent(tape, BASE, out, note=f"{team} ep{eid} seat{seat}")
        mh = max(len(s2["hands"]) for s2 in tape)
        d0 = tape[0]["market"]
        cows = next((o[2] for o in d0 if o[0] == "BUY_ANIMAL" and o[1] == "COW"), 0)
        sheep = next((o[2] for o in d0 if o[0] == "BUY_ANIMAL" and o[1] == "SHEEP"), 0)
        melon = next((o[2] for o in d0 if o[0] == "BUY_SEED" and o[1] == "MELON"), 0)
        hires = sum(1 for o in d0 if o[0] == "HIRE")
        print(f"  {team:<22} ep{eid} seat{seat} margin{margin:>+9,.0f}  "
              f"{cows}C/{sheep}S melon{melon} hire{hires} hands{mh}  -> {os.path.basename(out)}")
        made.append(out)
    return made


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--crawl", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--min-games", type=int, default=20)
    ap.add_argument("--extract", type=int, default=0,
                    help="extract tapes for the N strongest teams by real win rate")
    a = ap.parse_args()
    api = _api()
    if a.crawl:
        lb = leaderboard(api, a.top)
        print(f"crawling {len(lb)} teams (metadata only)")
        cache = crawl(api, lb)
    else:
        cache = json.load(open(CACHE))
    print(f"\ncached: {len(cache['teams'])} teams, {len(cache['episodes'])} episodes")
    if a.report:
        wl, mg = matrix(cache)
        known = {v["team"]: v["score"] for v in cache["teams"].values()}
        rows = [(n, w, l) for n, (w, l) in wl.items() if w + l >= a.min_games]
        rows.sort(key=lambda t: -(t[1] / max(t[1] + t[2], 1)))
        print(f"\n真实天梯战绩（>= {a.min_games} 局）")
        print(f"{'team':<26}{'榜分':>8}{'W':>5}{'L':>5}{'win%':>7}{'胜时均分差':>12}")
        for name, w, l in rows[:30]:
            m = sum(mg[name]) / len(mg[name]) if mg[name] else 0
            sc = known.get(name)
            print(f"{name[:24]:<26}{(f'{sc:.0f}' if sc else '-'):>8}{w:>5}{l:>5}"
                  f"{w/max(w+l,1):>7.0%}{m:>+12,.0f}")


    if a.extract:
        wl, mg = matrix(cache)
        known = {v["team"] for v in cache["teams"].values()}
        rank = [(w / max(w + l, 1), n) for n, (w, l) in wl.items()
                if n in known and w + l >= 25]
        rank.sort(reverse=True)
        targets = [n for _, n in rank[:a.extract]]
        print(f"\nextracting tapes for {len(targets)} teams")
        extract_pool(api, cache, targets)


if __name__ == "__main__":
    main()
