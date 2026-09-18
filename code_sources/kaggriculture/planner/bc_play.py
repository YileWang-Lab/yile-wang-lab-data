"""The decisive gate: can a policy made ONLY of the cloned network play a game?

92.8% action accuracy is not evidence of anything on its own. Errors compound
over 720 steps x up to 15 units, and the failure modes are asymmetric: a wrong
move direction costs one turn, but a missed WATER kills the crop (two
consecutive unwatered days makes a weed) and a missed FEED loses the animal.
The only honest test is to hand the network the farm and see what it banks.

The network predicts the base op. Item arguments are resolved by rule rather
than learned, for the reason given in bc_data.py -- there is one sensible crop
for a tile whose role is known, so a 30-way joint vocabulary would only add
sparsity. Market orders are not cloned at all here; a deliberately plain rule
runs them, so that what is being measured is the cloned FARM policy rather than
a mixture of two things.

Baselines to beat, same opponent and seeds:
  the tape itself   ~$96k
  route/agent.py    ~$84k
A number near either means cloning transfers. A number near zero means the
compounding argument above won, and the prior is not usable for search either.
"""
import argparse
import importlib.util
import json
import math
import multiprocessing
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from planner.simulate import Simulator  # noqa: E402
from planner.bc_data import features, OPS, CROPS, ANIMALS  # noqa: E402

BC_DIR = os.path.join(ROOT, "planner", "bc")
SHED_ACCESS = {(4, 4), (5, 4), (4, 5), (5, 5)}
_n = [0]


def _load(name):
    _n[0] += 1
    p = os.path.join(ROOT, "opponents", f"{name}.py")
    s = importlib.util.spec_from_file_location(f"bp_{os.getpid()}_{_n[0]}", p)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return getattr(m, "_submission_entry", None) or m.agent


class Net:
    """Plain-Python forward pass -- the same arithmetic the submission would
    ship, so there is no train/inference mismatch to debug later."""

    def __init__(self, path):
        d = json.load(open(path))
        self.ops = d["ops"]; self.mu = d["mu"]; self.sd = d["sd"]
        self.W = d["W"]; self.B = d["B"]

    def __call__(self, feat):
        x = [(v - m) / s for v, m, s in zip(feat, self.mu, self.sd)]
        for li, (W, B) in enumerate(zip(self.W, self.B)):
            out = list(B)
            for i, xi in enumerate(x):
                if xi == 0.0:
                    continue
                row = W[i]
                for j in range(len(out)):
                    out[j] += xi * row[j]
            if li < len(self.W) - 1:
                out = [v if v > 0 else 0.0 for v in out]
            x = out
        return x


def _needs_work(t, day):
    """Is this tile worth standing on right now?"""
    if t is None or t == "LOCKED":
        return 0
    if not isinstance(t, dict):
        return 0
    if "animal" in t:
        return 3 if (not t.get("fed_today") or t.get("yield_units", 0) > 0
                     or not t.get("cared_today") or t.get("fertilizer_available")) else 0
    if t.get("kind") == "PLANT":
        if not t.get("watered_today"):
            return 3
        return 2 if t.get("yield_units", 0) > 0 else 0
    if t.get("kind") == "WEED":
        return 1
    return 0


def _route_step(x, y, tiles, day, claimed):
    """Greedy navigation: step toward the nearest unclaimed tile that needs work.

    This exists to test the load-bearing claim in bc_play's failure analysis --
    that cloning fails on NAVIGATION rather than on tile operations. The network
    reproduces WATER/FEED/HARVEST at 97-99% but 47% of a tape's actions are
    moves, and where a tape moves at step t depends on where it is going, which
    is a property of the whole day's route and simply is not present in local
    features. If replacing only the movement decision rescues the agent, that
    diagnosis is right; if it does not, the problem is elsewhere.
    """
    best, bestd = None, 99
    for ty in range(10):
        for tx in range(10):
            if (tx, ty) in claimed:
                continue
            w = _needs_work(tiles[ty][tx], day)
            if not w:
                continue
            d = abs(tx - x) + abs(ty - y) - w
            if d < bestd:
                bestd, best = d, (tx, ty)
    if best is None:
        return None
    tx, ty = best
    if (tx, ty) == (x, y):
        return None
    claimed.add(best)
    if ty < y:
        return "NORTH"
    if ty > y:
        return "SOUTH"
    if tx > x:
        return "EAST"
    return "WEST"


def make_agent(net, safety=True, routed=False):
    """`safety` adds the precondition/maintenance layer described in bc_play's
    failure analysis. Pure cloning banks $40: the policy leaves the tape's state
    distribution, stops issuing PICKUP, therefore carries no wheat, therefore
    never FEEDs (3 times in a whole game against the tape's ~4.6% of actions),
    and every animal escapes after two unfed days. DAgger is the textbook fix
    and is unavailable here -- the expert is a TAPE, so it cannot be queried for
    "what would you do in THIS state"; it only knows step t of its own
    trajectory. So the recovery has to be rules, not more data.

    The layer does two things and deliberately nothing else:
      - masks ops whose engine preconditions cannot hold, so a confident but
        impossible prediction cannot waste the turn
      - overrides the net when the state is about to lose an asset irreversibly
        (an animal one day from escaping, a crop one day from becoming a weed)
    """
    def agent(obs):
        seat = int(obs.get("player", 0))
        farm = obs["farms"][seat]
        priv = obs.get("private") or {}
        shed = priv.get("shed") or {}
        seeds = priv.get("seeds") or {}
        invs = priv.get("inventories") or [{}]
        tiles = farm["tiles"]
        day, hour = int(obs["day"]), int(obs["hour"])

        n_animals = sum(1 for row in tiles for t in row
                        if isinstance(t, dict) and "animal" in t)

        def unit_action(ui, pos):
            logits = net(features(obs, seat, ui, pos))
            order = sorted(range(len(logits)), key=lambda i: -logits[i])
            inv = invs[ui] if ui < len(invs) else {}
            x, y = int(pos[0]), int(pos[1])
            tile = tiles[y][x]
            d = tile if isinstance(tile, dict) else {}

            if safety:
                # 1. irreversible-loss overrides, on the tile we already occupy
                if isinstance(d, dict) and "animal" in d:
                    if not d.get("fed_today") and inv.get("WHEAT", 0):
                        return ["FEED"]
                    if d.get("yield_units", 0) > 0:
                        return ["HARVEST"]
                if isinstance(d, dict) and d.get("kind") == "PLANT" \
                        and not d.get("watered_today"):
                    return ["WATER"]
                # 2. stock up at the shed rather than walking away empty
                if (x, y) in SHED_ACCESS and not inv:
                    for a in ANIMALS:
                        if shed.get(a, 0) > 0:
                            return ["PICKUP", a, 1]
                    if n_animals and shed.get("WHEAT", 0) > 0:
                        return ["PICKUP", "WHEAT", min(8, shed["WHEAT"])]
                if (x, y) in SHED_ACCESS and inv and not any(
                        inv.get(k, 0) for k in ("WHEAT", "FERTILIZER", *ANIMALS)):
                    return ["DROP"]

            for i in order[:4]:
                op = OPS[i]
                if op == "PLANT":
                    have = [c for c in CROPS if seeds.get(c, 0) > 0]
                    if have and tile is None:
                        return ["PLANT", max(have, key=lambda c: seeds.get(c, 0))]
                    continue
                if op == "PICKUP":
                    if (x, y) not in SHED_ACCESS:
                        continue
                    for a in ANIMALS:
                        if shed.get(a, 0) > 0:
                            return ["PICKUP", a, 1]
                    if n_animals and shed.get("WHEAT", 0) > 0:
                        return ["PICKUP", "WHEAT", min(6, shed["WHEAT"])]
                    if shed.get("FERTILIZER", 0) > 0:
                        return ["PICKUP", "FERTILIZER", min(3, shed["FERTILIZER"])]
                    continue
                if op == "PLACE":
                    for a in ANIMALS:
                        if inv.get(a, 0) and isinstance(tile, dict) \
                                and tile.get("kind") in ("COOP", "PASTURE") \
                                and "animal" not in tile:
                            return ["PLACE", a]
                    continue
                if op == "DROP":
                    if (x, y) in SHED_ACCESS and inv:
                        return ["DROP"]
                    continue
                if op == "FEED" and not (inv.get("WHEAT", 0)
                                         and isinstance(d, dict) and "animal" in d
                                         and not d.get("fed_today")):
                    continue
                if op == "FERTILIZE" and not (inv.get("FERTILIZER", 0)
                                              and isinstance(d, dict)
                                              and d.get("kind") == "PLANT"):
                    continue
                if safety:
                    if op == "WATER" and not (isinstance(d, dict)
                                              and d.get("kind") == "PLANT"
                                              and not d.get("watered_today")):
                        continue
                    if op == "HARVEST" and not (isinstance(d, dict)
                                                and d.get("yield_units", 0) > 0):
                        continue
                    if op == "CARE" and not (isinstance(d, dict) and "animal" in d
                                             and not d.get("cared_today")):
                        continue
                    if op == "COLLECT_FERTILIZER" and not (
                            isinstance(d, dict) and d.get("fertilizer_available")):
                        continue
                    if op in ("BUILD_COOP", "BUILD_PASTURE") and tile is not None:
                        continue
                    if op == "DIG" and not (isinstance(d, dict)
                                            and d.get("kind") == "WEED"):
                        continue
                    if op in ("NORTH", "SOUTH", "EAST", "WEST"):
                        dx, dy = {"NORTH": (0, -1), "SOUTH": (0, 1),
                                  "EAST": (1, 0), "WEST": (-1, 0)}[op]
                        if not (0 <= x + dx < 10 and 0 <= y + dy < 10):
                            continue
                return [op]
            return ["PASS"]

        claimed = set()

        def unit_final(ui, pos):
            act = unit_action(ui, pos)
            if routed and act and act[0] in ("NORTH", "SOUTH", "EAST", "WEST", "PASS"):
                x, y = int(pos[0]), int(pos[1])
                if _needs_work(tiles[y][x], day):
                    return act
                mv = _route_step(x, y, tiles, day, claimed)
                if mv:
                    return [mv]
            return act

        farmer = unit_final(0, farm["farmer"])
        hands = [unit_final(i + 1, hp) for i, hp in enumerate(farm.get("hands") or [])]

        # --- rule-based market, deliberately not cloned ---
        # The first version of this starved the farm and made the whole BC
        # measurement meaningless: it spent all 3,000 on day 0 animals and seeds,
        # then `money - cost < 40` broke the hire loop on every later day, so the
        # season ran on the farmer alone and both BC variants banked exactly $40.
        # Hiring is the highest-return purchase there is -- a hand costs fib(n)
        # (the 5th of the day is $5) and returns a whole 24-turn workday -- so it
        # is funded first and a reserve is kept to guarantee it.
        orders = []
        money = farm["money"]
        HIRE_RESERVE = 400

        if hour <= 1:
            k = 0
            while len(farm.get("hands") or []) + k < 12 and len(orders) < 10:
                cost = _fib(farm.get("hires_today", 0) + k)
                if money - cost < 20:
                    break
                orders.append(["HIRE"]); money -= cost; k += 1

        prices = (obs.get("market") or {}).get("prices") or {}
        shed_used = sum(shed.values())
        spendable = max(0.0, money - HIRE_RESERVE)

        # feed stock first: a starved animal escapes and takes its capital with it
        if n_animals and len(orders) < 10:
            want = min(n_animals * 2, max(0, 100 - shed_used), 40)
            have = shed.get("WHEAT", 0)
            px = max(1, prices.get("WHEAT", 25))
            n = int(min(want - have, spendable // px))
            if n > 0:
                orders.append(["BUY_PRODUCT", "WHEAT", n])
                money -= n * px; spendable -= n * px

        # animals, throttled to 1/turn so day 0 cannot consume the whole bank
        if day <= 14 and len(orders) < 10 and shed_used < 90:
            for a, cnt, cost in (("COW", 6, 400), ("SHEEP", 8, 500)):
                placed = sum(1 for row in tiles for t in row
                             if isinstance(t, dict) and t.get("animal") == a)
                need = cnt - placed - shed.get(a, 0)
                if need > 0 and spendable >= cost:
                    orders.append(["BUY_ANIMAL", a, 1])
                    money -= cost; spendable -= cost
                    break

        if day <= 20 and len(orders) < 10:
            for c, cnt, px in (("WHEAT", 8, 10), ("STRAWBERRY", 4, 100), ("MELON", 3, 80)):
                if seeds.get(c, 0) < cnt:
                    nb = int(min(cnt - seeds.get(c, 0), spendable // px, 6))
                    if nb > 0:
                        orders.append(["BUY_SEED", c, nb])
                        money -= nb * px; spendable -= nb * px

        n_extra = len(farm.get("unlocked_quadrants") or ["NW"]) - 1
        if n_extra < 3 and len(orders) < 10:
            price = [1000, 2000, 4000][n_extra]
            if spendable >= price * 1.6:
                orders.append(["BUY_LAND"]); money -= price; spendable -= price

        terminal = day * 24 + hour >= 680
        RES = {"MELON": 70, "WOOL": 60, "MILK": 55, "STRAWBERRY": 45,
               "EGG": 20, "FERTILIZER": 25, "WHEAT": 12, "CARROT": 15, "TOMATO": 20}
        for item in ["MELON", "WOOL", "MILK", "STRAWBERRY", "TOMATO", "CARROT",
                     "EGG", "FERTILIZER", "WHEAT"]:
            if len(orders) >= 10:
                break
            have = int(shed.get(item, 0))
            if have <= 0:
                continue
            if item == "WHEAT" and n_animals and not terminal:
                have -= n_animals * 2
                if have <= 0:
                    continue
            if terminal or prices.get(item, 0) >= RES.get(item, 20) or shed_used > 70:
                orders.append(["SELL", item, have])

        return {"farmer": farmer, "hands": hands, "market": orders[:10]}
    return agent


def _fib(n):
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def play(job):
    kind, seed, opp_name = job
    try:
        opp = _load(opp_name)
        if kind == "bc":
            me = make_agent(Net(os.path.join(BC_DIR, "bc_model.json")), safety=False)
        elif kind == "bc_safe":
            me = make_agent(Net(os.path.join(BC_DIR, "bc_model.json")), safety=True)
        elif kind == "bc_routed":
            me = make_agent(Net(os.path.join(BC_DIR, "bc_model.json")),
                            safety=True, routed=True)
        elif kind == "tape":
            me = _load("kaggriculture-multi-route-farming-agent")
        else:
            from route.search import to_params
            g = json.load(open(os.path.join(ROOT, "planner", "checkpoints",
                                            "best_genome1.json")))["genome"]
            s = importlib.util.spec_from_file_location(
                f"rt_{os.getpid()}_{time.time_ns()}", os.path.join(ROOT, "route", "agent.py"))
            m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
            m.configure(to_params(g)); me = m.agent
        sim = Simulator.new_episode(configuration={"episodeSteps": 720}, seed=seed)
        m0, m1 = sim.run_episode(me, opp)
        return (kind, seed, m0, m1, None)
    except Exception:
        import traceback
        return (kind, seed, 0.0, 0.0, traceback.format_exc()[-300:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=24)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--opponent", default="v111-8c4s-economic-core-premium-lead")
    args = ap.parse_args()
    import random
    rng = random.Random(555)
    seeds = [rng.randrange(10 ** 6, 2 ** 31 - 1) for _ in range(args.games)]
    jobs = [(k, s, args.opponent) for k in
            ("bc", "bc_safe", "bc_routed", "route", "tape") for s in seeds]
    t0 = time.time()
    with multiprocessing.get_context("forkserver").Pool(args.workers) as pool:
        res = pool.map(play, jobs, chunksize=1)
    print(f"elapsed {time.time()-t0:.0f}s")
    errs = [r[4] for r in res if r[4]]
    if errs:
        print(f"{len(errs)} errors; first:\n{errs[0]}")
    print()
    print(f"vs {args.opponent}, {args.games} seeds")
    print(f"{'agent':<8} {'own bank':>12} {'opp bank':>12} {'margin':>12} {'wins':>7}")
    for k in ("tape", "route", "bc_routed", "bc_safe", "bc"):
        rows = [r for r in res if r[0] == k and not r[4]]
        if not rows:
            continue
        print(f"{k:<8} {statistics.mean(r[2] for r in rows):>12,.0f} "
              f"{statistics.mean(r[3] for r in rows):>12,.0f} "
              f"{statistics.mean(r[2]-r[3] for r in rows):>12,.0f} "
              f"{sum(1 for r in rows if r[2]>r[3]):>4}/{len(rows)}")


if __name__ == "__main__":
    main()

# ---------------------------------------------------------------------------
# RESULT (2026-08-19). Behavioural cloning from tapes does not work here, and
# the control experiment shows why it cannot be fixed with more data or a
# better policy head.
#
#   vs v111, 12 seeds, own bank:
#     tape          $89,116
#     route/agent    $71,506
#     bc             $    62     pure network
#     bc_safe        $   129     + precondition masking + irreversible-loss overrides
#     bc_routed      $   288     + rule-based navigation to the nearest task
#
#   CONTROL -- let the TAPE drive so the state stays on the expert's own
#   trajectory, and merely ask the network what it would do:
#     agreement 92.6% overall, 98.2% on non-move ops
#     (WATER 98.0, FEED 99.4, HARVEST 98.2, PASS 97.9)
#
# So the network is correct: features, training and the plain-Python forward
# pass all reproduce the tape almost exactly WHERE THE TAPE HAS BEEN. It
# collapses only when it drives. That is textbook covariate shift, and the
# control rules out an implementation bug.
#
# Why it cannot be repaired here specifically:
#
#   1. No DAgger. The standard fix is to run the learner, then have the EXPERT
#      label the off-trajectory states it reaches. Our expert is a TAPE -- a
#      fixed 719-step action list. It cannot be queried for "what would you do
#      in this state"; it only knows step t of its own trajectory. The
#      supervision signal required to fix covariate shift does not exist.
#
#   2. Navigation is not a function of local state. 47% of a tape's actions are
#      moves, and where it moves at step t encodes where it is going -- a
#      property of the whole day's route, absent from any local feature vector.
#      Adding rule-based navigation (bc_routed) confirmed this is not the whole
#      story either: it moved the number from $129 to $288, not to $70k.
#
#   3. A perfect clone of kawa is kawa. Even total success caps at the tape we
#      already run, so the upside was never above the current agent -- the
#      hoped-for gain was a board-relative policy that could then be improved,
#      and that is exactly the part that fails.
#
# What survives and is worth keeping: bc_data.features() and the collection
# pipeline (2.7M samples in 8 seconds), plus the finding that the TILE-OPERATION
# decision is highly learnable (98.2%) while PLANNING is not. If a strong
# QUERYABLE policy ever exists, cloning it is ready to run. route/agent.py is
# queryable but weaker than the tape, so cloning it gains nothing over calling it.
# ---------------------------------------------------------------------------
