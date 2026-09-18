"""In-place waste recovery.

Measured: 2.0% of the tape's tile ops fire into a state where they do nothing,
and losses carry twice the waste rate of wins (3.5% vs 1.7%, r = -0.32 against
margin). So the behavioural-cloning critique has a real kernel — just a much
smaller one than "zero generalisation".

The fix has one hard constraint. Substituting an action that *moves* a unit
desynchronises every later scripted action for it (measured: 62% -> 0-5%). So
recovery only ever swaps in an op valid on the tile the unit is already standing
on. Position is untouched, the tape stays in sync, and only turns the tape was
going to waste anyway are affected.

Deliberately excluded: FEED and FERTILIZE. Both consume carried stock the tape
budgeted for a later step, so recovering with them robs a scheduled action.
"""

_TEMPLATE = '''

# ============ in-place waste recovery (pbt/recover.py) ============
_WR_ENABLED = __ENABLED__
_WR_ANIMAL_STRUCT = {"GOOSE": "COOP", "COW": "PASTURE", "SHEEP": "PASTURE"}
# Ordered by value; none of these consume carried stock or move the unit.
_WR_TRY = ("HARVEST", "CARE", "WATER", "COLLECT_FERTILIZER")
_WR_BASE_AGENT = agent


def _wr_ok(op, tile, inv, seeds):
    if not op:
        return True
    n = op[0]
    isd = isinstance(tile, dict)
    if n in ("NORTH", "SOUTH", "EAST", "WEST", "PASS", "PICKUP", "DROP"):
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
                and tile.get("kind") == _WR_ANIMAL_STRUCT.get(op[1]) and "animal" not in tile)
    if n == "DIG":
        return tile is not None and not (isd and "animal" in tile)
    return True


def agent(obs):
    action = _WR_BASE_AGENT(obs)
    if not _WR_ENABLED:
        return action
    try:
        o = obs if isinstance(obs, dict) else dict(obs)
        seat = int(o.get("player", 0) or 0)
        farms = o.get("farms") or []
        if seat >= len(farms):
            return action
        farm = farms[seat]
        priv = o.get("private") or {}
        seeds = priv.get("seeds") or {}
        invs = priv.get("inventories") or [{}]
        tiles = farm["tiles"]
        units = [farm.get("farmer")] + list(farm.get("hands") or [])
        acts = [list(action.get("farmer") or ["PASS"])] + \\
               [list(h or ["PASS"]) for h in (action.get("hands") or [])]
        changed = False
        for i in range(min(len(units), len(acts))):
            op, pos = acts[i], units[i]
            if pos is None or not op:
                continue
            # movement and shed work are never touched -- position must not change
            if op[0] in ("PASS", "NORTH", "SOUTH", "EAST", "WEST", "PICKUP", "DROP"):
                continue
            try:
                tile = tiles[pos[1]][pos[0]]
            except Exception:
                continue
            inv = invs[i] if i < len(invs) else {}
            if _wr_ok(op, tile, inv, seeds):
                continue
            for cand in _WR_TRY:
                if _wr_ok([cand], tile, inv, seeds):
                    acts[i] = [cand]
                    changed = True
                    break
        if changed:
            action["farmer"] = acts[0]
            action["hands"] = acts[1:]
    except Exception:
        return action
    return action
'''


def recover_src(enabled=1):
    return _TEMPLATE.replace("__ENABLED__", str(bool(enabled)))
