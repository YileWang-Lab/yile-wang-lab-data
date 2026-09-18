"""Read the *schedule* out of a reference agent's precomputed action tape.

These agents don't plan at runtime -- they replay a route that was optimised
offline, which is why they land 52% useful actions where our runtime planner
lands 25%. We can't reuse their tape (it's their route), but the SHAPE of the
schedule is strategy we can copy into our own planner: how many hands per day,
when each purchase happens, and how the day's turns are budgeted.
"""
import importlib.util
import sys
from collections import Counter, defaultdict

REF = sys.argv[1] if len(sys.argv) > 1 else "v111-8c4s-economic-core-premium-lead"
path = f"/home/yilewang/kaggriculture/opponents/{REF}.py"
spec = importlib.util.spec_from_file_location("ref_sched", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

tape = getattr(mod, "_ACTIONS", None) or getattr(mod, "_TRACE", None)
if tape is None:
    for name in dir(mod):
        v = getattr(mod, name)
        if isinstance(v, list) and len(v) > 600 and isinstance(v[0], dict) and "farmer" in v[0]:
            tape = v
            break
if tape is None:
    print(f"{REF}: no action tape found (runtime planner, not a replay)")
    sys.exit()

print(f"=== {REF} — {len(tape)} steps ===\n")

USEFUL = {"PLANT", "WATER", "HARVEST", "FEED", "CARE", "FERTILIZE",
          "COLLECT_FERTILIZER", "BUILD_COOP", "BUILD_PASTURE", "PLACE", "DIG", "PICKUP", "DROP"}
MOVE = {"NORTH", "SOUTH", "EAST", "WEST"}

per_day = defaultdict(lambda: {"useful": 0, "move": 0, "idle": 0,
                               "hands": 0, "hire": 0, "buys": Counter(), "sells": Counter()})
for step, a in enumerate(tape):
    d = step // 24
    rec = per_day[d]
    ops = [(a.get("farmer") or ["PASS"])[0]] + [(h or ["PASS"])[0] for h in (a.get("hands") or [])]
    rec["hands"] = max(rec["hands"], len(a.get("hands") or []))
    for op in ops:
        rec["useful" if op in USEFUL else ("move" if op in MOVE else "idle")] += 1
    for o in (a.get("market") or []):
        if not o:
            continue
        if o[0] == "HIRE":
            rec["hire"] += 1
        elif o[0] in ("BUY_ANIMAL", "BUY_SEED", "BUY_PRODUCT"):
            rec["buys"][f"{o[0][4:]}:{o[1]}"] += int(o[2]) if len(o) > 2 else 1
        elif o[0] == "BUY_LAND":
            rec["buys"]["LAND"] += 1
        elif o[0] == "SELL":
            rec["sells"][o[1]] += int(o[2]) if len(o) > 2 else 1

print(f"{'day':>3} {'hands':>5} {'hire':>4} {'useful':>7} {'move':>5} {'idle':>5} {'use%':>5}  purchases")
tot = Counter()
for d in sorted(per_day):
    r = per_day[d]
    t = r["useful"] + r["move"] + r["idle"]
    tot["useful"] += r["useful"]; tot["move"] += r["move"]; tot["idle"] += r["idle"]
    buys = ", ".join(f"{k}x{v}" for k, v in r["buys"].most_common(4))
    print(f"{d:>3} {r['hands']:>5} {r['hire']:>4} {r['useful']:>7} {r['move']:>5} {r['idle']:>5} "
          f"{r['useful']/max(t,1):>4.0%}  {buys}")

t = sum(tot.values())
print(f"\nSEASON: useful={tot['useful']:,} ({tot['useful']/t:.0%})  "
      f"move={tot['move']:,} ({tot['move']/t:.0%})  idle={tot['idle']:,} ({tot['idle']/t:.0%})")

print("\ntotal sells by product:")
allsell = Counter()
for d in per_day:
    allsell.update(per_day[d]["sells"])
for k, v in allsell.most_common():
    print(f"  {k:<12} {v:,}")
