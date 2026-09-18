"""Extract a player's 720-step action tape from a downloaded replay.

The tape alone is not an agent: replayed at a different seed it desynchronises,
because weeds and shop unlocks are drawn from a stream shared between both
farms. The reference agents solve this with `_weed_repair_action` (DIG a weed
blocking a scheduled PLANT/BUILD, then replay the delayed action) and
`_align_hands` (trim/pad the hand list to whatever the engine actually granted).

So the tape is transplanted into that existing scaffolding rather than replayed
raw: take the strongest reference's runtime layer, swap `_ACTIONS*` for the
extracted tape, and pin the route label so tape selection cannot override it.
"""
import base64, json, sys, zlib


def extract(replay_path, seat):
    d = json.load(open(replay_path))
    # steps[0] is the initial state and carries no action; the actions that
    # drive the episode live at steps[1:], which is why the reference tapes are
    # 719 long rather than 720. Taking steps[0] shifts the whole tape by one and
    # silently discards the opening turn -- the single most important step.
    steps = (d.get("steps") or [])[1:]
    tape = []
    for frame in steps:
        if seat >= len(frame):
            tape.append({"farmer": ["PASS"], "hands": [], "market": []}); continue
        a = frame[seat].get("action")
        if not isinstance(a, dict):
            tape.append({"farmer": ["PASS"], "hands": [], "market": []}); continue
        tape.append({
            "farmer": list(a.get("farmer") or ["PASS"]),
            "hands": [list(h or ["PASS"]) for h in (a.get("hands") or [])],
            "market": [list(o) for o in (a.get("market") or [])],
        })
    return tape, d


def payload(tape):
    raw = json.dumps(tape, separators=(",", ":")).encode()
    return base64.b85encode(zlib.compress(raw, 9)).decode()


def build_agent(tape, base_src_path, out_path, note=""):
    """kawa's runtime layer + this tape."""
    src = open(base_src_path).read()
    blob = payload(tape)
    with open(out_path, "w") as f:
        f.write(src)
        f.write(f'\n\n# ==== transplanted tape ({note}) ====\n')
        f.write("_XT = json.loads(zlib.decompress(base64.b85decode(\n")
        f.write(f"    '{blob}'\n")
        f.write(")).decode('utf-8'))\n")
        f.write("for _n in ('_ACTIONS_10C4S_3Q','_ACTIONS_8C6S_3Q','_ACTIONS_6C8S_3Q',\n"
                "          '_ACTIONS_6C12S_4Q_FIRST_YARN','_ACTIONS_6C12S_4Q_SECOND_YARN',\n"
                "          '_LEGACY_ACTIONS_10C4S_3Q','_LEGACY_ACTIONS_8C6S_3Q',\n"
                "          '_LEGACY_ACTIONS_6C8S_3Q','_LEGACY_ACTIONS_6C12S_4Q_FIRST_YARN',\n"
                "          '_LEGACY_ACTIONS_6C12S_4Q_SECOND_YARN','_ACTIONS'):\n"
                "    if _n in globals(): globals()[_n] = _XT\n")
        f.write("\n\ndef _xt_entry(obs):\n    return agent(obs)\n")
    return out_path


if __name__ == "__main__":
    path, seat, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    tape, d = extract(path, seat)
    names = (d.get("info") or {}).get("TeamNames") or []
    print(f"extracted seat {seat} ({names[seat] if seat < len(names) else '?'}) "
          f"-- {len(tape)} steps")
    hands = max(len(s["hands"]) for s in tape)
    mkt = sum(len(s["market"]) for s in tape)
    useful = sum(1 for s in tape for u in [s["farmer"]] + s["hands"]
                 if u and u[0] not in ("PASS", "NORTH", "SOUTH", "EAST", "WEST"))
    print(f"max hands {hands}, market orders {mkt}, useful unit actions {useful}")
    print("day 0 market:", tape[0]["market"])
    build_agent(tape, "/home/yilewang/kaggriculture/opponents/"
                "kaggriculture-multi-route-farming-agent.py", out, note=path)
    import os
    print(f"wrote {out} ({os.path.getsize(out):,} bytes)")
