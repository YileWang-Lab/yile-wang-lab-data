"""Extract the tape's SEASON PLAN: what it builds, where, and when.

Not a script. The tape's 719 actions have already been shown unusable as a
policy -- planner/bc_play.py cloned them at 92.6% per-step agreement and banked
$288 against the tape's $89k, because the tape cannot supervise the states a
learner actually reaches. And planner/schedule_diff.py extracted only its
per-day HIRE/LAND/BUY counts, one number a day with no spatial content; forcing
those onto our crew measured -56,572.

What has never been extracted is the plan's SHAPE: which tile ends up holding
which role, in what order those tiles come online, and what has to be bought by
when to make that order feasible. That is a declarative target -- "by day 6 own
these tiles and have 4 pastures standing" -- which a dynamic scheduler can chase
and repair, rather than a frame it must reproduce exactly.

This matters because of what tonight measured. The planner earns MORE per
work-turn than the tape ($35.34 vs $35.98 is a wash) but has 81% of its
work-turns, and six separate ways of adding scale all made it poorer, each
failing through cash: capital and labour compete for the same money and labour
is what converts capital into product. The tape's plan is a cash-flow sequence
that is known to be feasible from $3,000. Its layout is the part of that
sequence we have never copied.
"""
import collections
import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from planner.simulate import Simulator  # noqa: E402

OUT = os.path.join(ROOT, "dynamic", "season_plan.json")
_n = [0]


def _load(p):
    _n[0] += 1
    s = importlib.util.spec_from_file_location(f"sp_{os.getpid()}_{_n[0]}", p)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return getattr(m, "_submission_entry", None) or m.agent


def extract(tape_path, opp_path, seed):
    """Watch a tape play and record the plan its board reveals."""
    tape = _load(tape_path); opp = _load(opp_path)
    # tile -> first day we saw each role there, and the role sequence
    first_seen = {}
    role_hist = collections.defaultdict(list)
    daily = {}
    quad_day = {}

    def probe(obs):
        a = tape(obs)
        seat = int(obs.get("player", 0))
        farm = obs["farms"][seat]
        day = int(obs["day"])
        tiles = farm["tiles"]
        for y in range(10):
            for x in range(10):
                t = tiles[y][x]
                if not isinstance(t, dict):
                    continue
                role = (t.get("animal") or
                        (t.get("crop") if t.get("kind") == "PLANT" else None) or
                        (t.get("kind") if t.get("kind") in ("COOP", "PASTURE") else None))
                if not role:
                    continue
                key = (x, y)
                if key not in first_seen:
                    first_seen[key] = (day, role)
                if not role_hist[key] or role_hist[key][-1][1] != role:
                    role_hist[key].append((day, role))
        nq = len(farm.get("unlocked_quadrants") or ["NW"])
        if nq not in quad_day:
            quad_day[nq] = day
        if day not in daily:
            daily[day] = {"money": farm["money"], "hands": len(farm.get("hands") or [])}
        return a

    sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
    m0, _ = sim.run_episode(probe, opp)
    return first_seen, role_hist, daily, quad_day, m0


def main():
    tape = os.path.join(ROOT, "opponents",
                        "kaggriculture-multi-route-farming-agent.py")
    opp = os.path.join(ROOT, "opponents",
                       "v111-8c4s-economic-core-premium-lead.py")
    seeds = [1009, 88301, 271829, 481123]
    # a tile's role must agree across seeds to be part of the PLAN rather than
    # a reaction to one board
    votes = collections.defaultdict(collections.Counter)
    day_votes = collections.defaultdict(list)
    quads = collections.defaultdict(list)
    banks = []
    for sd in seeds:
        fs, hist, daily, qd, bank = extract(tape, opp, sd)
        banks.append(bank)
        for key, (day, role) in fs.items():
            votes[key][role] += 1
            day_votes[key].append(day)
        for nq, day in qd.items():
            quads[nq].append(day)

    plan = {}
    for key, c in votes.items():
        role, n = c.most_common(1)[0]
        if n < len(seeds):          # not stable across seeds -> not a plan tile
            continue
        days = sorted(day_votes[key])
        plan[f"{key[0]},{key[1]}"] = {"role": role,
                                      "day": days[len(days) // 2]}
    import statistics
    print(f"tape banks ${statistics.mean(banks):,.0f}")
    print(f"stable plan tiles: {len(plan)} of {len(votes)} ever occupied")
    print()
    by_role = collections.Counter(v["role"] for v in plan.values())
    print("PLAN portfolio:", dict(by_role.most_common()))
    print()
    print("quadrant unlock day (median):",
          {k: int(statistics.median(v)) for k, v in sorted(quads.items())})
    print()
    print("tiles coming online per day:")
    per_day = collections.Counter(v["day"] for v in plan.values())
    for d in sorted(per_day):
        roles = collections.Counter(v["role"] for v in plan.values() if v["day"] == d)
        print(f"  day {d:>2}: {per_day[d]:>3} tiles  {dict(roles.most_common())}")
    json.dump({"plan": plan,
               "quad_day": {k: int(statistics.median(v)) for k, v in quads.items()},
               "portfolio": dict(by_role)},
              open(OUT, "w"), indent=1)
    print(f"\nsaved {OUT}")


if __name__ == "__main__":
    main()
