"""Turn top-ladder replays into (named features -> decision) rows.

WHY REPLAYS FROM THE TOP AND NOT THE TAPE. HANDOFF section 32 measured tape
distillation at 89-100% held-out agreement and -46,972 in play. The cause was
covariate shift, and the mechanism is specific: kawa's tape is a FIXED 719-step
trajectory, so cloning it clones a path, and our scheduler never walks that path.

The top ladder is different in a way that matters. Section 10 measured their
self-agreement across their own games at 37-65% -- they RESPOND to state rather
than replaying a script. Cloning them clones a function, and a function can
generalise off its training path in a way a trajectory cannot. That is the whole
bet here, and it is a bet, not a certainty: the acceptance test is play, never
agreement.

WHAT IS EXTRACTED. One row per day per top player:

    x   36 board statistics + 86 market/economy scalars, all named
    y   that day's decisions -- crops planted, hires, land bought, animal
        placed, and per product the fraction of holdings offered

The board is already flat: `encode.extract_board_features` reduces a 10x10xC
plane to 36 counts, means and fractions, so a 22 MB replay collapses to 30 rows
of 122 floats. Memory is not a constraint after that, and each feature keeps a
name so any tree fitted on them is readable.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _HERE]
sys.path.insert(0, ROOT)

from dynamic.opp_state import OppState          # noqa: E402
from dynamic.rl import encode as E              # noqa: E402
from dynamic.rl import policy_api as PA         # noqa: E402
from route.opponent import OpponentModel        # noqa: E402

REPLAYS = os.path.join(ROOT, "replays")
OUT = os.path.join(ROOT, "logs", "tree", "rows.json")

# The eleven strongest teams we hold replays for, by mean final bank.
TOP = ["VanKoha", "我的AI是GPT", "ReCurSiON", "HKmgikao", "peikopon",
       "tetsuya", "mandgeee", "Thomas Tschinkel", "Galaxantic",
       "カワシギ", "Eddy Despradel"]


def _nearest(v, opts):
    return min(range(len(opts)), key=lambda i: abs(opts[i] - v))


def rows_from(path, teams_wanted):
    """Every day-row for whichever seat a wanted team held."""
    try:
        d = json.load(open(path))
    except Exception:
        return []
    names = (d.get("info") or {}).get("TeamNames") or []
    seats = [i for i, t in enumerate(names[:2]) if t in teams_wanted]
    if not seats:
        return []
    steps = d["steps"]
    out = []
    for seat in seats:
        st, om = OppState(), OpponentModel()
        pend = None
        day_plant, day_hire, day_land, day_animal, day_sold = {}, 0, 0, None, {}
        my_prev = {}
        for i in range(1, len(steps)):
            entry = steps[i][seat]
            obs = entry.get("observation") or {}
            if "farms" not in obs or "private" not in obs:
                continue
            day, hour = int(obs.get("day", 0)), int(obs.get("hour", 0))
            farms = obs["farms"]
            if len(farms) < 2:
                continue
            me, opp = farms[seat], farms[1 - seat]
            priv = obs["private"]
            shops = tuple((obs.get("town") or {}).get("unlocked_shops") or ())
            inv = (obs.get("market") or {}).get("inventory") or {}
            om.observe(dict(inv), int(obs.get("step", i)), shops, my_prev)
            if om.recent and om.recent[-1][0] == int(obs.get("step", i)):
                st.record_sales(om.recent[-1][1])
            st.observe(opp, day, hour)
            st.reconcile((obs.get("market") or {}).get("prices") or {},
                         len(opp.get("hands") or []))

            if hour == 0:
                pend = (E.encode_whitebox(obs, me, priv, opp, st, day, hour),
                        E.encode_scalars(obs, me, priv, opp, st, day, hour),
                        dict(priv.get("shed") or {}),
                        len(me.get("hands") or []), day,
                        float(me.get("money", 0)))
                day_plant, day_hire, day_land, day_animal, day_sold = {}, 0, 0, None, {}

            act = entry.get("action") or {}
            my_prev = {}
            if isinstance(act, dict):
                for u in [act.get("farmer")] + list(act.get("hands") or []):
                    if u and u[0] == "PLANT" and len(u) > 1:
                        day_plant[u[1]] = day_plant.get(u[1], 0) + 1
                    if u and u[0] == "PLACE" and len(u) > 1:
                        day_animal = u[1]
                for m in act.get("market") or []:
                    if not m:
                        continue
                    if m[0] == "HIRE":
                        day_hire += 1
                    elif m[0] == "BUY_LAND":
                        day_land = 1
                    elif m[0] == "SELL":
                        day_sold[m[1]] = day_sold.get(m[1], 0) + int(m[2])
                        my_prev[m[1]] = my_prev.get(m[1], 0) + int(m[2])

            if hour == 23 and pend:
                x, scal, shed0, n_hands, d0, cash = pend
                tot = sum(day_plant.values())
                crop = (max(day_plant, key=day_plant.get) if tot else None)
                sell, mask = [], []
                for it in PA.PRODUCTS:
                    held = float(shed0.get(it, 0))
                    if held <= 0:
                        sell.append(0)
                        mask.append(0)
                        continue
                    sell.append(_nearest(min(1.0, day_sold.get(it, 0) / held),
                                         PA.SELL_LEVELS))
                    mask.append(1)
                out.append({"x": x, "s": scal, "day": d0, "cash": cash,
                            "team": names[seat],
                            "crop": PA.CROPS.index(crop) if crop in PA.CROPS else -1,
                            "hire": min(6, day_hire), "land": int(bool(day_land)),
                            "animal": PA.ANIMAL_CHOICES.index(day_animal)
                                      if day_animal in PA.ANIMAL_CHOICES else 0,
                            "sell": sell, "sell_mask": mask})
                pend = None
        del st, om
    del d
    return out


def main():
    import gc
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    files = sorted(os.listdir(REPLAYS))
    files = [os.path.join(REPLAYS, f) for f in files if f.endswith(".json")]
    want = set(TOP)
    rows, seen = [], {}
    for i, f in enumerate(files):
        r = rows_from(f, want)
        if r:
            for x in r:
                seen[x["team"]] = seen.get(x["team"], 0) + 1
            rows.extend(r)
            print(f"  [{i + 1}/{len(files)}] {os.path.basename(f)[:34]} "
                  f"+{len(r)} rows (total {len(rows):,})", flush=True)
        gc.collect()
        if limit and len(rows) >= limit:
            break
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({"rows": rows, "names": E.whitebox_names(),
               "scalar_names": E.scalar_names()}, open(OUT, "w"))
    print(f"\n{len(rows):,} day-rows from {len(seen)} teams -> {OUT}")
    for t, n in sorted(seen.items(), key=lambda kv: -kv[1]):
        print(f"  {t[:28]:<30}{n:>6}")


if __name__ == "__main__":
    main()
