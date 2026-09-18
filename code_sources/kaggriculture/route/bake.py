"""Bake a single self-contained submission/main.py.

The base agent is stdlib-only (base64/copy/json/zlib) and already exposes a
top-level `agent(obs)`, so baking is: copy it verbatim, then append an override
block that rebinds its hand-set runtime constants to searched values. Module
globals are read inside the functions at call time, so appending after all the
definitions is enough -- no editing of their source, nothing to keep in sync.
"""
import argparse
import json
import os
import shutil

from pbt.intervene import intervene_src
from route.overlay import overlay_src

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, "opponents", "kaggriculture-multi-route-farming-agent.py")
OUT = os.path.join(ROOT, "submission", "main.py")

TUNABLES = ("_PREEMPT_ENABLED", "_PREEMPT_FRACTION", "_PREEMPT_MAX_BATCH",
            "_PREEMPT_MAX_CLONE_DISTANCE", "_PREEMPT_MIN_PRICE_RATIO",
            "_PREEMPT_MIN_FUTURE_QUANTITY", "_PREEMPT_START", "_PREEMPT_STOP",
            "_WEED_REPLAY_STEPS", "_DEMAND_ALPHA")


def bake(params=None, out=OUT, note=None):
    """`BASE_OVERRIDE` swaps the underlying agent file, so the same appended
    layers can be measured on top of a different school's tape."""
    """Write a standalone agent file. Constants are rebound by appending after
    all definitions -- module globals are read inside the functions at call
    time, so nothing in their source needs editing."""
    params = params or {}
    shutil.copyfile((params or {}).get("BASE_OVERRIDE") or BASE, out)
    overrides = {k: v for k, v in params.items() if k in TUNABLES}
    force = params.get("FORCE_ROUTE")
    with open(out, "a") as f:
        if note:
            f.write(f"\n\n# {note}\n")
        if overrides:
            f.write("\n# --- runtime constant overrides ---\n")
            for k in TUNABLES:
                if k in overrides:
                    f.write(f"{k} = {overrides[k]!r}\n")
        if params.get("OVERLAY"):
            f.write(overlay_src(min_hands=params.get("OV_MIN_HANDS", 4),
                                fill_idle=params.get("OV_FILL_IDLE", 1),
                                cash_floor=params.get("OV_CASH_FLOOR", 2),
                                day1_only=params.get("OV_DAY1_ONLY", 0)))
        if params.get("INTERVENE"):
            from pbt.intervene import PREMIUM, PREMIUM_FERT
            _items = params.get("IV_ITEMS")
            f.write(intervene_src(enabled=1,
                                  dump_frac=params.get("IV_DUMP_FRAC", 0.8),
                                  lead=params.get("IV_LEAD", 1),
                                  squeeze=params.get("IV_SQUEEZE", 0),
                                  repay=params.get("IV_REPAY", 0),
                                  mirror=params.get("IV_MIRROR", 0),
                                  items=(tuple(_items) if _items else
                                         (PREMIUM_FERT if params.get("IV_FERT") else PREMIUM)),
                                  struct=params.get("IV_STRUCT", 0),
                                  staged=params.get("IV_STAGED", 0),
                                  min_price=params.get("IV_MIN_PRICE", 0.0),
                                  slot_first=params.get("IV_SLOT_FIRST", 0),
                                  seat0_dump=params.get("IV_SEAT0_DUMP"),
                                  seat0_min_price=params.get("IV_SEAT0_MINPRICE"),
                                  hold_ratio=params.get("IV_HOLD_RATIO", 0.0),
                                  hold_shed_max=params.get("IV_HOLD_SHED_MAX", 70),
                                  hold_stop_step=params.get("IV_HOLD_STOP_STEP", 600),
                                  stop_day=params.get("IV_STOP_DAY", 0),
                                  late_dump=params.get("IV_LATE_DUMP", 0.0),
                                  adapt=params.get("IV_ADAPT", 0),
                                  marginal_floor=params.get("IV_MARGINAL_FLOOR", 0.25),
                                  vol_mult=params.get("IV_VOL_MULT", 1.0),
                                  max_qty=params.get("IV_MAX_QTY", 60),
                                  pred_mode=params.get("IV_PRED_MODE", 0)))
        if force:
            # Pin the tape instead of letting the shop draw choose it.
            f.write("\n# --- tape selection override ---\n")
            f.write(f"def _kawa_route_label(obs):\n    return {force!r}\n")
        if params.get("DAY0_MARKET"):
            from pbt.tape_edit import day0_src
            f.write(day0_src(params["DAY0_MARKET"]))
        if params.get("RECOVER"):
            from pbt.recover import recover_src
            f.write(recover_src())
        if params.get("TAPE_MAP"):
            from pbt.tapesel import tapesel_src
            f.write(tapesel_src(params["TAPE_MAP"]))
        if params.get("TREE_ROUTE"):
            # Score-neutral by construction: the CART is a perfect fit to the
            # route table, verified at the table, action and play levels. It is
            # the substrate for per-step edits (`_TR_EDITS`), not a gain. Safe
            # to append after tapesel because `_kawa_route_label` is resolved at
            # call time, so whichever definition lands last still wins.
            from pbt.treeroute import treeroute_src
            f.write(treeroute_src(
                (params or {}).get("BASE_OVERRIDE") or BASE))
        # Kaggle resolves a file agent with get_last_callable, which walks the
        # module namespace in INSERTION order. Rebinding `agent` does not move
        # it -- the name was inserted by the base file -- so the last *new*
        # callable wins. Without this stub that was `_iv_predict`, and the
        # engine would have called it as agent(observation, configuration).
        # Must stay the final definition in the file.
        f.write("\n\ndef _submission_entry(obs):\n    return agent(obs)\n")
    return out, overrides


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--genome", default=None, help="best_*.json to bake in")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()
    params = {}
    if args.genome and os.path.exists(args.genome):
        params = json.load(open(args.genome)).get("params") or {}
    path, ov = bake(params, args.out)
    size = os.path.getsize(path)
    print(f"wrote {path}  ({size:,} bytes)")
    print(f"overrides baked: {ov if ov else 'none (verbatim base)'}")


if __name__ == "__main__":
    main()
