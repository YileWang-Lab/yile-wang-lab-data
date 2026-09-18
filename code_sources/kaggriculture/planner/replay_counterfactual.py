"""Would the new agent have won the games the live one lost?

For each real ladder loss, replay the OPPONENT's exact recorded action sequence
at the episode's real seed and swap only our side for a candidate agent. The
opponent's actions are fixed input, so this isolates our own change.

IMPORTANT LIMITATION, stated up front because it bounds every number below:
a recorded episode is a TRACE, not a policy (HANDOFF section 10). Against an
adaptive opponent, changing our play would have changed theirs, so this is a
counterfactual against "the opponent behaving exactly as they did", not against
the opponent. It is a legitimate directional signal and a good regression check;
it is NOT a prediction of the rematch. Fully valid only for tape opponents.

Sanity gate: the candidate is first run as the ORIGINAL agent (submission
55600561's config) and must reproduce the replay's recorded final banks. If the
reproduction is off, the opponent was reacting to something the trace cannot
capture and that episode is reported as unusable rather than scored.

Usage:
    /home/yilewang/kagg-env/bin/python -m planner.replay_counterfactual
"""
import importlib.util
import json
import multiprocessing
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from planner.simulate import Simulator, _agent_caller  # noqa: E402
from route.bake import bake  # noqa: E402

LOG_DIR = os.path.join(ROOT, "logs", "planner")
EPISODES = "/tmp/claude-1818200050/-home-yilewang/12e9e33c-6cb5-4a53-939b-9c2b0d0b6776/scratchpad/v3_episodes2.json"

SHIPPED = {"_PREEMPT_MIN_FUTURE_QUANTITY": 0, "_PREEMPT_MAX_BATCH": 30,
           "INTERVENE": 1, "IV_DUMP_FRAC": 0.8, "IV_LEAD": 3, "IV_FERT": 1}
NEW = {**SHIPPED, "IV_STRUCT": 1, "IV_DUMP_FRAC": 0.7, "IV_MIN_PRICE": 0.20}

_n = [0]


def _load(path):
    _n[0] += 1
    spec = importlib.util.spec_from_file_location(f"cf_{os.getpid()}_{_n[0]}", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return getattr(m, "_submission_entry", None) or m.agent


def make_trace_agent(steps, seat):
    """An agent that emits the recorded action for `seat` at each step."""
    acts = [steps[i][seat].get("action") for i in range(len(steps))]

    def agent(obs):
        i = int(obs.get("day", 0)) * 24 + int(obs.get("hour", 0)) + 1
        if i < len(acts) and isinstance(acts[i], dict):
            return acts[i]
        return {"farmer": ["PASS"], "hands": [], "market": []}
    return agent


def run_one(job):
    ep, our_seat, agent_path, label = job
    path = os.path.join(ROOT, "replays", f"episode-{ep}-replay.json")
    try:
        d = json.load(open(path))
        seed = d["info"]["seed"]
        cfg = d.get("configuration", {})
        steps = d["steps"]
        opp_seat = 1 - our_seat

        me = _load(agent_path)
        opp = make_trace_agent(steps, opp_seat)

        sim = Simulator.new_episode(
            configuration={k: v for k, v in cfg.items() if k in
                           ("boardSize", "startingMoney", "maxMarketOrdersPerTurn", "turnsPerDay",
                            "shedCapacity", "weedSpawnChance", "townShopUnlockInterval",
                            "townShopSellInterval", "townCenterSellInterval",
                            "farmHandCostMult", "episodeSteps", "marketParams")},
            seed=seed)
        pair = [me, opp] if our_seat == 0 else [opp, me]
        m0, m1 = sim.run_episode(pair[0], pair[1])
        us, them = (m0, m1) if our_seat == 0 else (m1, m0)
        return (ep, label, us, them, us - them, None)
    except Exception:
        import traceback
        return (ep, label, 0, 0, 0, traceback.format_exc()[-250:])


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true",
                    help="score every ladder game, not just the losses. The losses are a "
                         "SELECTED-HARDEST subset, so a delta measured on them alone "
                         "understates the ladder-wide effect.")
    a = ap.parse_args()

    rows = json.load(open(EPISODES))
    losses = [r for r in rows if (a.all or not r["win"])]
    losses = [r for r in losses
              if os.path.exists(os.path.join(ROOT, "replays", f"episode-{r['episode']}-replay.json"))]
    print(f"{len(losses)} real ladder games with replays available "
          f"({'ALL games' if a.all else 'losses only'})")

    old_path = os.path.join(ROOT, "agents", "cf_old.py")
    new_path = os.path.join(ROOT, "agents", "cf_new.py")
    bake(SHIPPED, out=old_path, note="counterfactual: live 55600561 config")
    bake(NEW, out=new_path, note="counterfactual: new 55612771 config")

    jobs = []
    for r in losses:
        jobs.append((r["episode"], r["us_seat"], old_path, "old"))
        jobs.append((r["episode"], r["us_seat"], new_path, "new"))

    t0 = time.time()
    with multiprocessing.get_context("forkserver").Pool(12) as pool:
        res = pool.map(run_one, jobs)
    print(f"elapsed {time.time()-t0:.0f}s")

    by_ep = {}
    for ep, label, us, them, margin, err in res:
        if err:
            print(f"ep {ep} {label}: ERROR {err[-150:]}")
            continue
        by_ep.setdefault(ep, {})[label] = (us, them, margin)

    truth = {r["episode"]: r for r in losses}
    print()
    verbose = len(truth) <= 25
    if verbose:
        print(f"{'episode':>10} {'opponent':<20} {'st':>3} {'REAL margin':>12} "
              f"{'repro(old)':>11} {'fidelity':>9} {'new margin':>11} {'delta':>9} {'flips?':>7}")
    flips = 0
    usable = 0
    deltas = []
    for ep, t in sorted(truth.items(), key=lambda kv: kv[1]["margin"]):
        d = by_ep.get(ep, {})
        if "old" not in d or "new" not in d:
            continue
        old_m = d["old"][2]
        new_m = d["new"][2]
        real_m = t["margin"]
        # fidelity: does replaying the opponent's trace vs our ORIGINAL agent
        # reproduce the real result? if not, the trace is not a faithful stand-in.
        err = abs(old_m - real_m)
        ok = err < max(500, 0.05 * abs(real_m))
        if ok:
            usable += 1
            deltas.append(new_m - old_m)
            if new_m > 0:
                flips += 1
        if verbose:
            print(f"{ep:>10} {t['opp_team'][:20]:<20} {t['us_seat']:>3} {real_m:>12,.0f} "
                  f"{old_m:>11,.0f} {'OK' if ok else 'DRIFT':>9} {new_m:>11,.0f} "
                  f"{new_m-old_m:>+9,.0f} {('YES' if new_m > 0 else 'no') if ok else '-':>7}")

    print()
    print(f"usable episodes (trace reproduces the real result): {usable}/{len(truth)}")
    if deltas:
        md = statistics.mean(deltas)
        sd = statistics.pstdev(deltas) if len(deltas) > 1 else 0.0
        se = sd / (len(deltas) ** 0.5)
        old_w = sum(1 for ep, t in truth.items()
                    if ep in by_ep and "old" in by_ep[ep] and by_ep[ep]["old"][2] > 0)
        new_w = sum(1 for ep, t in truth.items()
                    if ep in by_ep and "new" in by_ep[ep] and by_ep[ep]["new"][2] > 0)
        print(f"mean delta from the new agent: {md:+,.0f}  (se {se:,.0f}, t={md/se if se else 0:.1f})")
        print(f"record under the replayed traces: old {old_w}/{usable}  ->  new {new_w}/{usable}")
        real_losses = [ep for ep, t in truth.items() if t["margin"] < 0]
        flipped = [ep for ep in real_losses
                   if ep in by_ep and by_ep[ep].get("new", (0, 0, 0))[2] > 0]
        lost = [ep for ep, t in truth.items() if t["margin"] > 0
                and ep in by_ep and by_ep[ep].get("new", (0, 0, 1))[2] < 0]
        print(f"real losses that flip to wins: {len(flipped)}/{len(real_losses)}")
        print(f"real wins that flip to losses: {len(lost)}")
    print()
    print("CAVEAT: opponents are replayed traces. Against an adaptive opponent they")
    print("would have reacted to our change, so this bounds the direction, not the rematch.")

    out = os.path.join(LOG_DIR, f"counterfactual_{time.strftime('%Y%m%d_%H%M%S')}.json")
    json.dump({str(k): v for k, v in by_ep.items()}, open(out, "w"), indent=1, default=str)
    print(f"raw: {out}")


if __name__ == "__main__":
    main()
