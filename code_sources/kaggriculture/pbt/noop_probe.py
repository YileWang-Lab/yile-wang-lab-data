"""Does the tape actually 'blindly execute into states it did not expect'?

The behavioural-cloning critique says a replayed tape must misfire whenever the
world drifts from the recording. That is testable: every tile op has a
precondition, so an action can be checked against live state *before* it is
submitted. This counts how many of the tape's own actions land on a state where
they do nothing, and whether that rate predicts losing.
"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

ANIMALS = {"GOOSE": "COOP", "COW": "PASTURE", "SHEEP": "PASTURE"}


def op_valid(op, tile, inv, seeds):
    """Mirrors the engine's preconditions in _apply_unit_action."""
    if not op:
        return True
    n = op[0]
    isd = isinstance(tile, dict)
    if n in ("NORTH", "SOUTH", "EAST", "WEST", "PASS"):
        return True
    if n == "FEED":
        return isd and "animal" in tile and not tile.get("fed_today") and inv.get("WHEAT", 0) > 0
    if n == "CARE":
        return isd and "animal" in tile and not tile.get("cared_today")
    if n == "COLLECT_FERTILIZER":
        return isd and "animal" in tile and tile.get("fertilizer_available")
    if n == "HARVEST":
        return isd and tile.get("yield_units", 0) > 0
    if n == "WATER":
        return isd and tile.get("kind") == "PLANT" and not tile.get("watered_today")
    if n == "FERTILIZE":
        return isd and tile.get("kind") == "PLANT" and inv.get("FERTILIZER", 0) > 0
    if n == "PLANT":
        return tile is None and seeds.get(op[1], 0) > 0
    if n in ("BUILD_COOP", "BUILD_PASTURE"):
        return tile is None
    if n == "PLACE":
        return (inv.get(op[1], 0) > 0 and isd
                and tile.get("kind") == ANIMALS.get(op[1]) and "animal" not in tile)
    if n == "DIG":
        return tile is not None and not (isd and "animal" in tile)
    if n == "PICKUP":
        return True
    return True


def probe(action, obs, seat):
    """-> (issued_tile_ops, wasted_tile_ops)."""
    o = obs if isinstance(obs, dict) else dict(obs)
    farms = o.get("farms") or []
    if seat >= len(farms):
        return 0, 0
    farm = farms[seat]
    priv = o.get("private") or {}
    seeds = priv.get("seeds") or {}
    invs = priv.get("inventories") or [{}]
    tiles = farm["tiles"]
    units = [farm.get("farmer")] + list(farm.get("hands") or [])
    acts = [action.get("farmer") or ["PASS"]] + list(action.get("hands") or [])
    issued = wasted = 0
    for i, (pos, act) in enumerate(zip(units, acts)):
        if not act or act[0] in ("PASS", "NORTH", "SOUTH", "EAST", "WEST", "PICKUP"):
            continue
        if pos is None:
            continue
        try:
            tile = tiles[pos[1]][pos[0]]
        except Exception:
            continue
        inv = invs[i] if i < len(invs) else {}
        issued += 1
        if not op_valid(act, tile, inv, seeds):
            wasted += 1
    return issued, wasted
