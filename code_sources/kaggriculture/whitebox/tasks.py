"""Module 3 of 6 -- TASK PLANNER. What work exists today, and who does it.

Two stages, deliberately separate:

  enumerate(snap, plan) -> [Task]      what the farm needs done, with a value
  assign(snap, tasks)   -> {unit: tour} who does which, in what order

ENUMERATION IS WHERE THE ENGINE RULES LIVE, and they are unforgiving:

  * A crop must be WATERED THE DAY IT IS PLANTED. `_new_plant` starts at
    `consecutive_unwatered = 1`, and two unwatered nights turn it into a weed.
    PLANT and WATER therefore ride in the same tile visit, always.
  * FEED and CARE every animal every day. CARE banks a multiplier that is only
    consumed on the next FED production day, so an uncared animal is not just
    slower, it permanently loses that cycle's bonus.
  * Animals produce FERTILIZER unconditionally, fed or not, and nobody in town
    consumes it. It still has to be collected and sold, because the shed holds
    100 items and a full shed freezes all commerce (measured: bank $62).
  * PLANT validation is ATOMIC per crop per turn -- if the turn's PLANT requests
    for one crop exceed seeds held, ALL of them are dropped. So seed accounting
    happens here, at enumeration, not hopefully at execution.

ASSIGNMENT DELEGATES TO `route/router.py`: one joint prize-collecting solver
selects tasks, assigns workers under global input constraints, and orders each
open Manhattan route. Task value and path cost therefore meet in the same
decision instead of being optimised in sequence.
"""
import sys, os
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from route import router                      # noqa: E402  the day-VRP solver
from route.router import Task, Unit           # noqa: E402
from whitebox import econ, paths, value as objective  # noqa: E402
try:
    from whitebox import market_model as _MM
except Exception:
    _MM = None

import os as _os
# 1 = water only a tile that would weed tonight, directly from the two-night
# death rule. 0 is the fully-watered control.
_WATER_SLACK = int(_os.environ.get("WB_WATER_SLACK", "1"))
_STRICT_FERT_ENABLED = None


# Execution variants are deliberately opt-in.  Historical agents keep the
# coordinate-only cache and its measured behaviour.  ``manifest_routes`` keeps
# the router's complete per-worker certificate (aggregate pickup manifest plus
# exact planned mutations), while ``parallel_opening_manifest`` additionally
# enables the opening completion-balancing rule.
_MANIFEST_EXECUTION = frozenset((
    "manifest_routes",
    "parallel_opening_manifest",
    "positioned_capital_manifest",
    "incremental_hire_manifest",
    "bounded_commitment_manifest",
    "production_aligned_crop_manifest",
    "paid_production_fertilizer_manifest",
    "paid_fertilizer_productive_shed_relocation_manifest",
    "exact_zero_day_manifest",
    "paid_weed_reinvestment_manifest",
    "paid_weed_reinvestment_incremental_hire_manifest",
    "paid_weed_reinvestment_bounded_hire_manifest",
))
_COMPLETION_BALANCE = frozenset((
    "parallel_opening",
    "parallel_opening_manifest",
))
_STRICT_UNIT_INVENTORY = frozenset((
    "unit_inventory",
    "parallel_opening",
    "manifest_routes",
    "parallel_opening_manifest",
    "positioned_capital_manifest",
    "incremental_hire_manifest",
    "bounded_commitment_manifest",
    "production_aligned_crop_manifest",
    "paid_production_fertilizer_manifest",
    "paid_fertilizer_productive_shed_relocation_manifest",
    "exact_zero_day_manifest",
    "paid_weed_reinvestment_manifest",
    "paid_weed_reinvestment_incremental_hire_manifest",
    "paid_weed_reinvestment_bounded_hire_manifest",
))

# Per-seat, current-day capital commitments emitted by the white-box capital
# master. This is not an inferred policy state: every entry is the exact
# (item, tile) decision just paid for in our own market action. The next
# observation contains the purchased fungible inventory but not its intended
# tile, so retaining this action certificate makes execution solve the same
# physical problem that selected the crew.
_CAPITAL_POSITIONS = {}

# Multi-day suffix of a paid turnover action certificate.  Each entry is an
# item/position pair we ourselves bought and routed; live tile state remains
# the validity guard and removes stale records after harvest or failure.
_PAID_TURNOVER_CROPS = {}

# Per-seat finite service covenant emitted by the selected multi-day
# certificate.  Unlike a target portfolio, this contains only dated public
# tile coordinates from a route that was actually costed.  It expires at the
# last certified day and is active only in the isolated execution variant.
_SERVICE_COMMITMENTS = {}


def _execution_variant():
    plan = _last_plan[0]
    return getattr(plan, "execution_variant", None) if plan is not None else None


def _uses_manifest_execution():
    return _execution_variant() in _MANIFEST_EXECUTION


def paid_turnover_item(snap, pos):
    """Crop named by the current-day manifest after DIG on ``pos``.

    This reads only our retained action certificate.  Returning ``None`` when
    the route/day/capability does not match prevents an unrelated DIG from
    opening the intraday seed-purchase master.
    """
    cache = _PLAN.get(int(snap.seat))
    if (cache is None or int(cache.get("day", -1)) != int(snap.day)
            or not bool(cache.get("paid_weed_turnover", False))):
        return None
    target = tuple(pos)
    for manifest in (cache.get("manifests") or {}).values():
        for stop, ops in (manifest or {}).get("stops", ()):
            if tuple(stop) != target:
                continue
            names = {op[0] for op in (ops or ()) if op}
            plant = next((op for op in (ops or ())
                          if op and op[0] == "PLANT" and len(op) >= 2), None)
            if "DIG" in names and plant is not None:
                return str(plant[1])
    return None


def paid_turnover_arrival_is_preplanned(snap, before, current):
    """Whether every newly visible asset is a named turnover seed.

    A successful seed order normally invalidates the daily route so the new
    inventory can be assigned.  Paid turnover is the exception: its existing
    manifest already contains DIG+PLANT+WATER on the exact committed tile.
    Re-solving after the seed arrives would discard that certificate and the
    incumbent service path it protects.
    """
    cache = _PLAN.get(int(snap.seat))
    commitment = _CAPITAL_POSITIONS.get(int(snap.seat))
    if (cache is None or commitment is None
            or int(cache.get("day", -1)) != int(snap.day)
            or int(commitment.get("day", -1)) != int(snap.day)
            or not bool(cache.get("paid_weed_turnover", False))):
        return False
    increases = {
        str(item): int(qty) - int(before.get(item, 0) or 0)
        for item, qty in current
        if int(qty) > int(before.get(item, 0) or 0)
    }
    if not increases or any(item not in econ.CROPS for item in increases):
        return False
    positioned = commitment.get("positions_by_item", {})
    for crop, quantity in increases.items():
        pending = 0
        for raw_pos in positioned.get(crop, ()):
            pos = tuple(raw_pos)
            x, y = pos
            if (0 <= x < snap.board and 0 <= y < snap.board
                    and snap.me.tiles[y][x] is None
                    and paid_turnover_item(snap, pos) == crop):
                pending += 1
        if quantity > pending:
            return False
    return True


def paid_turnover_hires(snap, plan, max_orders, cash_available,
                        bank_outputs=False, allowed_kinds=()):
    """Exact incremental crew choice for named turnover work.

    Existing workers and their manifests are sunk and immutable.  The caller
    supplies the finite task kinds opened by our own turnover certificate;
    each candidate hand starts on the engine's public spawn tile next hour,
    pays the exact Fibonacci wage, and must complete a closed route whose task
    value strictly exceeds that wage.
    """
    cache = _PLAN.get(int(snap.seat))
    if (cache is None or int(cache.get("day", -1)) != int(snap.day)
            or int(snap.hour) + 1 >= econ.TURNS_PER_DAY
            or int(cache.get("units", 0) or 0) <= 1
            or int(cache.get("units", 0) or 0)
            != 1 + len(snap.me.hands)
            or not bool(cache.get("paid_weed_turnover", False))):
        return 0
    allowed = frozenset(str(kind) for kind in allowed_kinds)
    if not allowed:
        allowed = frozenset(("PAID_TURNOVER_SERVICE",))
    pending = [
        task for task in (cache.get("undone") or ())
        if str(task.kind) in allowed and float(task.value) > 0
    ]
    from whitebox import hiring as _hiring
    room = min(
        len(pending), max(0, int(max_orders)),
        max(0, int(_hiring.MAX_HANDS) - len(snap.me.hands)),
    )
    if not pending or room <= 0:
        return 0

    best = (0.0, 0)
    for quantity in range(1, room + 1):
        wage = float(econ.hire_block_cost(snap.me.hires_today, quantity))
        if wage > float(cash_available) + 1e-9:
            break
        first_idx = 1 + len(snap.me.hands)
        units = [
            Unit(first_idx + index, tuple(pos), int(snap.hour) + 1)
            for index, pos in enumerate(
                _hiring.spawn_positions(snap, quantity, None)
            )
        ]
        tours, _left = router.plan_day(
            units, pending,
            objective.planned_shed_stock(snap, plan),
            deadline=None, bank_outputs=bank_outputs,
            deterministic_primal=True,
        )
        selected = {
            id(task)
            for tour in tours.values()
            for task in (tour or {}).get("tasks", ())
        }
        value = sum(float(task.value) for task in pending
                    if id(task) in selected)
        net = value - wage
        key = (float(net), -quantity)
        if key > (best[0], -best[1]):
            best = (float(net), int(quantity))
    return int(best[1]) if best[0] > 1e-9 else 0


def paid_turnover_service_hires(snap, plan, max_orders, cash_available,
                                bank_outputs=False):
    """Compatibility entry for the named WATER/HARVEST suffix only."""
    return paid_turnover_hires(
        snap, plan, max_orders, cash_available, bank_outputs,
        allowed_kinds=("PAID_TURNOVER_SERVICE",),
    )


def commit_paid_turnover_incremental_hire(snap, allowed_kinds):
    """Retain the exact task universe bought by this turn's HIRE order."""
    cache = _PLAN.get(int(snap.seat))
    kinds = tuple(sorted(set(str(kind) for kind in allowed_kinds)))
    if (cache is None or int(cache.get("day", -1)) != int(snap.day)
            or not bool(cache.get("paid_weed_turnover", False))
            or not kinds):
        return False
    cache["paid_turnover_incremental_kinds"] = kinds
    return True


def commit_capital_positions(seat, day, positions_by_item):
    """Retain one day's selected capital layout for exact live execution."""
    positions = {}
    for item, raw_positions in sorted((positions_by_item or {}).items()):
        clean = []
        seen = set()
        for raw in raw_positions or ():
            pos = tuple(raw)
            if len(pos) != 2 or pos in seen:
                continue
            seen.add(pos)
            clean.append(pos)
        if clean:
            positions[str(item)] = tuple(clean)
    _CAPITAL_POSITIONS[int(seat)] = {
        "day": int(day), "positions_by_item": positions,
    }
    cache = _PLAN.get(int(seat))
    if (cache is not None and int(cache.get("day", -1)) == int(day)
            and bool(cache.get("paid_weed_turnover", False))):
        records = _PAID_TURNOVER_CROPS.setdefault(int(seat), {})
        for item, item_positions in positions.items():
            if item not in econ.CROPS:
                continue
            for pos in item_positions:
                if any(
                        tuple(stop) == tuple(pos)
                        and any(op and op[0] == "DIG" for op in ops)
                        and any(op and op[0] == "PLANT" and len(op) >= 2
                                and str(op[1]) == item for op in ops)
                        for manifest in (cache.get("manifests") or {}).values()
                        for stop, ops in (manifest or {}).get("stops", ())):
                    records[tuple(pos)] = {
                        "crop": str(item), "created_day": int(day),
                    }


def commit_service_schedule(seat, created_day, positions_by_day):
    """Retain the dated tile set of one selected finite route witness."""
    schedule = {}
    for raw_day, raw_positions in sorted((positions_by_day or {}).items()):
        day = int(raw_day)
        if day <= int(created_day):
            continue
        clean = []
        seen = set()
        for raw in raw_positions or ():
            pos = tuple(raw)
            if len(pos) != 2 or pos in seen:
                continue
            seen.add(pos)
            clean.append(pos)
        if clean:
            schedule[day] = tuple(sorted(clean))
    if schedule:
        _SERVICE_COMMITMENTS[int(seat)] = {
            "created_day": int(created_day),
            "end_day": max(schedule),
            "positions_by_day": schedule,
        }
    else:
        _SERVICE_COMMITMENTS.pop(int(seat), None)


def clear_service_commitment(seat):
    _SERVICE_COMMITMENTS.pop(int(seat), None)


def _committed_service_positions(snap):
    if _execution_variant() != "bounded_commitment_manifest":
        return frozenset()
    record = _SERVICE_COMMITMENTS.get(int(snap.seat))
    if not record:
        return frozenset()
    if int(snap.day) > int(record.get("end_day", -1)):
        clear_service_commitment(snap.seat)
        return frozenset()
    return frozenset(
        tuple(pos) for pos in record.get("positions_by_day", {}).get(
            int(snap.day), (),
        )
    )


def _apply_service_commitment(snap, work):
    """Make only live tasks on the selected dated route non-droppable."""
    positions = _committed_service_positions(snap)
    if not positions:
        return work
    for task in work:
        if (tuple(task.pos) in positions
                and task.kind in ("ANIMAL_SERVICE", "CROP_SERVICE",
                                  "PLANT_CROP", "BUILD_ANIMAL_HOME",
                                  "PLACE_ANIMAL")):
            task.mandatory = True
    return work


def _apply_paid_turnover_commitment(snap, work):
    """Name a turnover crop's suffix for additive route insertion.

    The new crop is optional capital, so sunk cost must not make its later
    WATER/HARVEST task mandatory ahead of pre-existing farm work.  Giving it a
    separate kind lets ``assign`` add it only to capacity left by V199's exact
    ordinary route.
    """
    records = _PAID_TURNOVER_CROPS.get(int(snap.seat))
    if not records:
        return work
    by_position = {tuple(task.pos): task for task in work}
    stale = []
    for pos, record in records.items():
        crop = str(record.get("crop", ""))
        x, y = tuple(pos)
        raw = (snap.me.tiles[y][x]
               if 0 <= x < snap.board and 0 <= y < snap.board else None)
        if (isinstance(raw, dict) and raw.get("kind") == "PLANT"
                and str(raw.get("crop", "")) == crop):
            task = by_position.get(tuple(pos))
            if task is not None and task.kind in ("CROP_SERVICE", "PLANT_CROP"):
                task.kind = "PAID_TURNOVER_SERVICE"
                task.mandatory = False
            continue
        # During the purchase turn the just-DIGged tile is still empty until
        # the next unit phase. Preserve it for that same-day suffix only.
        if raw is None and int(snap.day) == int(record.get("created_day", -1)):
            task = by_position.get(tuple(pos))
            if task is not None and task.kind == "PLANT_CROP":
                task.kind = "PAID_TURNOVER_SERVICE"
                task.mandatory = False
            continue
        stale.append(tuple(pos))
    for pos in stale:
        records.pop(pos, None)
    if not records:
        _PAID_TURNOVER_CROPS.pop(int(snap.seat), None)
    return work


def _capital_item(task):
    for op in task.ops or ():
        if op and op[0] in ("PLANT", "PLACE") and len(op) >= 2:
            return str(op[1])
    return None


def _position_accepts_item(snap, pos, item):
    """Live engine predicate for one committed placement destination."""
    x, y = tuple(pos)
    if not (0 <= x < snap.board and 0 <= y < snap.board):
        return False
    relocation_manifest = (
        _execution_variant()
        == "paid_fertilizer_productive_shed_relocation_manifest"
    )
    if (not paths.productive_tile_allowed(snap, pos)
            and not (relocation_manifest and tuple(pos) in paths.SHED_SET)):
        return False
    raw = snap.me.tiles[y][x]
    if item in econ.CROPS:
        return raw is None
    spec = econ.ANIMALS.get(item)
    if spec is None:
        return False
    return (raw is None or (
        isinstance(raw, dict) and "animal" not in raw
        and raw.get("kind") == spec["structure"]
    ))


def _apply_capital_positions(snap, work):
    """Permute fungible live tasks onto the capital certificate's tiles.

    Ordinary enumeration knows the purchased item counts exactly, but its
    scan-order locations need not be the locations used by the crew/route
    proof. A sequence of swaps preserves every task and every unique tile
    while restoring as many selected item/tile pairs as live inventory and
    engine state still permit. Failed purchases or externally-invalidated
    tiles are skipped and remain governed by the ordinary live plan.
    """
    plan = _last_plan[0]
    if getattr(plan, "execution_variant", None) not in (
            "positioned_capital_manifest", "bounded_commitment_manifest",
            "production_aligned_crop_manifest", "exact_zero_day_manifest",
            "paid_production_fertilizer_manifest",
            "paid_fertilizer_productive_shed_relocation_manifest",
            "paid_weed_reinvestment_manifest",
            "paid_weed_reinvestment_incremental_hire_manifest",
            "paid_weed_reinvestment_bounded_hire_manifest"):
        return work
    commitment = _CAPITAL_POSITIONS.get(int(snap.seat))
    if not commitment or int(commitment.get("day", -1)) != int(snap.day):
        return work

    eligible = [task for task in work if _capital_item(task) is not None]
    by_position = {tuple(task.pos): task for task in work}
    committed_ids = set()
    for item, positions in commitment["positions_by_item"].items():
        for target in positions:
            target = tuple(target)
            if not _position_accepts_item(snap, target, item):
                continue
            present = by_position.get(target)
            if (present is not None and _capital_item(present) == item
                    and id(present) not in committed_ids):
                committed_ids.add(id(present))
                continue
            candidate = next((
                task for task in eligible
                if id(task) not in committed_ids
                and _capital_item(task) == item
            ), None)
            if candidate is None:
                break
            source = tuple(candidate.pos)
            occupant = by_position.get(target)
            if occupant is not None and _capital_item(occupant) is None:
                # The capital certificate blocked current work tiles. Preserve
                # a later unmodelled live mutation instead of a collision.
                continue
            if occupant is not None and occupant is not candidate:
                occupant.pos = source
                by_position[source] = occupant
            else:
                by_position.pop(source, None)
            candidate.pos = target
            by_position[target] = candidate
            committed_ids.add(id(candidate))
    return work


def _needs_water(tile):
    """Water only when skipping would actually cost the tile.

    THE ENGINE RULE. `_daily_refresh_plants` weeds a tile at
    `consecutive_unwatered >= 2`, and a watered day resets the counter to 0. So
    a tile at 0 survives being skipped today (it goes to 1); a tile at 1 must be
    watered tonight or it is a weed by morning. `_new_plant` starts at 1, so a
    tile planted today is always watered today.

    Production does not require watering -- only survival does, plus the
    fertilizer bonus, which applies on watered days only. Watering at state 0
    therefore consumes a turn without changing the feasible survival set.
    """
    if tile.get("watered_today"):
        return False
    return int(tile.get("consecutive_unwatered", 0) or 0) >= _WATER_SLACK


def _production_aligned_crop_service():
    return _execution_variant() in (
        "production_aligned_crop_manifest",
        "paid_production_fertilizer_manifest",
        "paid_fertilizer_productive_shed_relocation_manifest",
    )


def _paid_weed_reinvestment():
    plan = _last_plan[0]
    return bool(getattr(plan, "paid_weed_turnover", False)) or (
        _execution_variant() in (
            "paid_weed_reinvestment_manifest",
            "paid_weed_reinvestment_incremental_hire_manifest",
            "paid_weed_reinvestment_bounded_hire_manifest",
        )
    )


def _produces_tonight(snap, tile):
    crop = tile.get("crop")
    if crop not in ONGOING:
        return False
    spec = econ.CROPS[crop]
    raw_planted = tile.get("planted_day", snap.day)
    planted = int(snap.day if raw_planted is None else raw_planted)
    age = int(snap.day) + 1 - planted - int(spec["first_yield_day"])
    if age < 0 or age % int(spec["interval"]):
        return False
    return age // int(spec["interval"]) + 1 <= int(spec["max_yield"])


def _crop_water_needed(snap, tile, fertilizing=False):
    """Survival water plus optional production-day fertilizer activation."""
    # A manifest retains the names of operations selected at day opening.
    # After FERTILIZE and WATER succeed, that historical name is not a reason
    # to issue WATER again on the already-watered live tile.
    if tile.get("watered_today"):
        return False
    return (_needs_water(tile)
            or (_production_aligned_crop_service()
                and _produces_tonight(snap, tile)
                and (bool(fertilizing)
                     or int(tile.get("fertilized_until_day", -1) or -1)
                     >= int(snap.day))))


def _crop_ready(tile, day):
    cd = econ.CROPS.get(tile.get("crop"))
    if not cd:
        return False
    if cd["ongoing"]:
        return int(tile.get("yield_units", 0) or 0) > 0
    return (day - int(tile.get("planted_day", 0) or 0)) >= cd["first_yield_day"]


def _survival_feed_hard_core():
    """Whether this version separates urgent FEED from optional tile work."""
    return bool(getattr(
        _last_plan[0], "survival_feed_hard_core", False,
    ))


# Isolated research switch.  The historical V206 arm only split FEED when an
# animal had already missed one night.  A daily-feed arm may ask the same
# operation-level core for every currently unfed animal; this is still a
# public-state rule (the engine's live ``fed_today`` flag and event calendar),
# never a fixed herd target or replay schedule.  Version wrappers pin the
# value explicitly so it cannot leak between bundled episodes.
DAILY_FEED_HARD_CORE = False


def _animal_has_future_output(snap, tile):
    """Return whether a live animal still has a public production event."""
    kind = tile.get("animal") if isinstance(tile, dict) else None
    if kind not in econ.ANIMALS:
        return False
    return bool(objective._animal_event_days(
        tile, kind, int(snap.day), include_start=True,
    ))


def _survival_feed_projection(snap, work):
    """Split urgent service into a mandatory FEED core and an optional suffix.

    FEED is a survival constraint, while CARE/HARVEST/COLLECT_FERTILIZER are
    useful but not survival-critical.  Keeping the suffix as a second task at
    the same coordinate lets the route master cover FEED even when the full
    bundle does not fit, without throwing away profitable service.  The full
    task remains an upgrade witness for historical callers; the router skips
    that upgrade whenever a suffix is present so operations cannot duplicate.
    """
    routed = []
    upgrades = {}
    for task in work:
        names = {op[0] for op in (task.ops or ()) if op}
        tile = snap.me.animals.get(tuple(task.pos))
        if (task.kind != "ANIMAL_SERVICE" or "FEED" not in names
                or tile is None
                or tile.get("fed_today")
                or (not DAILY_FEED_HARD_CORE
                    and int(tile.get("consecutive_unfed", 0) or 0) < 1)):
            routed.append(task)
            continue
        feed_ops = [["FEED"]]
        feed_value, mandatory = objective.animal_task_value(
            snap, tile, feed_ops,
        )
        if (DAILY_FEED_HARD_CORE and not mandatory
                and _animal_has_future_output(snap, tile)):
            # In the isolated daily-feed arm, survival itself is the witness:
            # the animal has a future engine production event, so skipping the
            # one-WHEAT FEED would create a known two-night death risk even if
            # the optional CARE/HARVEST suffix has a higher route value.
            mandatory = True
        if not mandatory:
            routed.append(task)
            continue
        core = Task(
            tuple(task.pos), feed_ops, {"WHEAT": 1},
            float(feed_value), True, "ANIMAL_SERVICE",
        )
        routed.append(core)

        # Preserve non-survival work as an independent same-tile suffix.  Its
        # value is the exact public-state increment from the original bundle
        # after removing the FEED core; no fitted distance or schedule weight
        # is introduced.  A non-positive suffix is omitted, but the mandatory
        # FEED core is always retained.
        residual_ops = [list(op) for op in (task.ops or ())
                        if op and op[0] != "FEED"]
        if residual_ops:
            residual_value = float(task.value) - float(feed_value)
            if residual_value > 1e-9:
                routed.append(Task(
                    tuple(task.pos), residual_ops, {}, residual_value, False,
                    "ANIMAL_SERVICE",
                ))
        upgrades[id(core)] = task
    return routed, upgrades


def _positive_animal_liquidation(snap, tile, ops, value, mandatory):
    """Drop an uneconomic FEED without losing profitable same-tile output.

    An animal with no remaining production can cost more to feed than its
    already-held product and fertilizer are worth.  The old all-or-nothing
    bundle then had non-positive value, so the router discarded HARVEST and
    COLLECT together with FEED.  Enumerate the at-most-three non-feed
    operations and return a single same-coordinate task only when its exact
    public-state value is positive and strictly dominates the rejected full
    bundle.  No survival task is weakened: positive urgent bundles remain
    mandatory and never enter this rule.
    """
    if mandatory or float(value) > 0:
        return None
    residual = [list(op) for op in (ops or ()) if op and op[0] != "FEED"]
    if len(residual) == len(ops or ()) or not residual:
        return None
    candidates = []
    for mask in range(1, 1 << len(residual)):
        candidate_ops = [
            op for index, op in enumerate(residual) if mask & (1 << index)
        ]
        candidate_value, candidate_mandatory = objective.animal_task_value(
            snap, tile, candidate_ops,
        )
        if candidate_mandatory or float(candidate_value) <= 0:
            continue
        candidates.append((
            float(candidate_value), -len(candidate_ops),
            tuple(op[0] for op in candidate_ops), candidate_ops,
        ))
    if not candidates:
        return None
    candidate_value, _negative_ops, _names, candidate_ops = max(candidates)
    if candidate_value <= float(value) + 1e-9:
        return None
    return candidate_ops, {}, float(candidate_value), False


def enumerate_tasks(snap, plan):
    """Everything worth doing on a tile today, one Task per tile."""
    tasks = []
    me = snap.me

    # --- animals: feed, care, collect. One visit does all three.
    for pos, tile in me.animals.items():
        ops, carry = [], {}
        if not tile.get("fed_today"):
            ops.append(["FEED"])
            carry["WHEAT"] = carry.get("WHEAT", 0) + 1
        if not tile.get("cared_today"):
            ops.append(["CARE"])
        held = int(tile.get("yield_units", 0) or 0)
        if held > 0:
            # HARVEST, not PICKUP. `_apply_unit_action`'s HARVEST branch covers
            # crops AND animals; PICKUP is a shed WITHDRAWAL that returns
            # immediately unless the unit is shed-adjacent. Emitting PICKUP at
            # an animal tile is a silent no-op, and it was the whole reason this
            # farm never had anything to sell: 311 PICKUPs in the mid-game, a
            # shed holding nothing but bought WHEAT, and no revenue at all.
            ops.append(["HARVEST"])
        if tile.get("fertilizer_available"):
            ops.append(["COLLECT_FERTILIZER"])
        if ops:
            value, mandatory = objective.animal_task_value(snap, tile, ops)
            liquidation = _positive_animal_liquidation(
                snap, tile, ops, value, mandatory,
            )
            if liquidation is not None:
                ops, carry, value, mandatory = liquidation
            tasks.append(Task(pos, ops, carry, value, mandatory,
                              "ANIMAL_SERVICE"))

    # --- crops: water always, harvest when ready.
    for pos, tile in me.crops.items():
        ops, carry = [], {}
        if _crop_ready(tile, snap.day):
            ops.append(["HARVEST"])
        fertilizing = _should_fertilize(snap, tile)
        if fertilizing:
            # CARRY IS REQUIRED. `_apply_unit_action`'s FERTILIZE branch does
            # `_inv_take(inv, "FERTILIZER", 1)` -- the unit's OWN pocket, not the
            # shed. Without the carry the unit walks to the tile holding nothing
            # and the op is a silent no-op, which is exactly what happened: the
            # whole FERTILIZE change measured as zero either way.
            carry["FERTILIZER"] = carry.get("FERTILIZER", 0) + 1
            # 235 of his 243 fertilise ops are on STRAWBERRY, always on a tile
            # not yet watered that day: the engine's bonus applies only on a
            # WATERED day, so fertilising first and watering after doubles the
            # next production. Only ongoing crops repay it, because a one-shot
            # crop has a single production left to double.
            ops.append(["FERTILIZE"])
        if _crop_water_needed(snap, tile, fertilizing=fertilizing):
            # WATER after HARVEST: HARVEST clears the yield, WATER checks the
            # fertilizer flag, and an unwatered night is a weed by morning.
            ops.append(["WATER"])
        if ops:
            value, mandatory = objective.crop_task_value(snap, tile, ops)
            # Legacy value treated ``planted_day == 0`` as missing and moved
            # its event calendar forward to the current day.  Keep every
            # historical capital/retention term unchanged in this isolated
            # arm, but credit the one current output unit whose fertilizer
            # bonus is physically activated by the additional WATER proved
            # above.  Fertilizer input cost is already subtracted by
            # ``crop_task_value`` when FERTILIZE is in this same task.
            if (_production_aligned_crop_service()
                    and int(tile.get("planted_day", -1)) == 0
                    and _produces_tonight(snap, tile)
                    and any(op[0] == "WATER" for op in ops)):
                value += objective.unit_value(snap, tile.get("crop"))
            tasks.append(Task(pos, ops, carry, value, mandatory,
                              "CROP_SERVICE"))

    # --- animals waiting in the shed need a structure to stand on, and the
    # --- structure has to exist before the PLACE. BUILD is free and instant.
    shed_animals = {k: int(snap.shed.get(k, 0) or 0) for k in econ.ANIMALS}
    pending = sum(shed_animals.values())
    reserved_build = set()
    build_pool = iter(_buildable(snap))
    if pending:
        free_struct = {}
        for y, row in enumerate(me.tiles):
            for x, t in enumerate(row):
                if isinstance(t, dict) and "animal" not in t and t.get("kind") in ("PASTURE", "COOP"):
                    free_struct.setdefault(t["kind"], []).append((x, y))
        for kind, n in shed_animals.items():
            if n <= 0:
                continue
            want = econ.ANIMALS[kind]["structure"]
            animal_value = objective.animal_placement_value(snap, kind)
            slots = free_struct.get(want, [])
            for pos in slots[:n]:
                tasks.append(Task(pos, [["PLACE", kind]], {kind: 1},
                                  animal_value, False, "PLACE_ANIMAL"))
            free_struct[want] = slots[n:]
            short = n - len(slots)
            # build what is missing, on tiles inside an unlocked quadrant
            for _ in range(max(0, short)):
                try:
                    pos = next(build_pool)
                except StopIteration:
                    break
                reserved_build.add(pos)
                op = "BUILD_PASTURE" if want == "PASTURE" else "BUILD_COOP"
                # The coordinate-only executor historically scheduled BUILD
                # and discovered PLACE only after the structure appeared.  Its
                # route cost therefore certified one operation while execution
                # needed BUILD + a shed round-trip + PLACE.  The manifest arm
                # makes that dependency one atomic planning column: one animal
                # is reserved to this worker, picked up in the route's batch,
                # and PLACE is charged before the day-boundary test.
                combined = _uses_manifest_execution()
                ops = [[op], ["PLACE", kind]] if combined else [[op]]
                carry = {kind: 1} if combined else {}
                tasks.append(Task(pos, ops, carry, animal_value, False,
                                  "BUILD_ANIMAL_HOME"))

    # --- empty tiles: plant, respecting seeds actually held (atomic validation).
    seeds = dict(snap.seeds)
    wave = _wave_state(snap, plan)
    plantable = [p for p in me.empty
                 if paths.quadrant_of(*p) in me.unlocked
                 and paths.productive_tile_allowed(snap, p)
                 and p not in reserved_build]
    for pos in plantable:
        crop = _pick_crop(seeds, plan, snap, wave)
        if crop is None:
            break
        seeds[crop] -= 1
        if crop in ONGOING:
            wave[crop] = (wave[crop][0] + 1, wave[crop][1])
        tasks.append(Task(pos, [["PLANT", crop], ["WATER"]], {},
                          objective.plant_value(snap, crop), False,
                          "PLANT_CROP"))

    # --- weeds: only worth clearing if there is time to use the tile again.
    # The paid arm has its own exact crop calendar and can prove the final
    # day-27 -> day-29 cohort; historical zero-seed clearing keeps V199's
    # stricter three-whole-days boundary byte-for-byte.
    paid_weed = _paid_weed_reinvestment()
    if snap.days_left >= (2 if paid_weed else 3):
        if paid_weed:
            turnover_crop, option_values = (
                objective.paid_weed_reinvestment_choice(
                snap, plan, len(me.weeds),
                )
            )
            weed_positions = sorted(
                me.weeds, key=lambda pos: (paths.dist_to_shed(pos), pos),
            )
            if turnover_crop is None or not option_values:
                # Closed option means exact V199 enumeration, including its
                # zero-value DIG columns.  Removing even rejected columns can
                # change deterministic solver/cache ordering downstream.
                for pos in me.weeds:
                    tasks.append(Task(
                        pos, [["DIG"]], {},
                        objective.weed_value(snap, plan), False, "CLEAR_WEED",
                    ))
            else:
                for pos, option_value in zip(weed_positions, option_values):
                    # One atomic route column reserves all three physical turns.
                    # The seed itself arrives after DIG in that turn's market
                    # phase; the manifest retains the named crop so the same unit
                    # PLANTs and WATERs without a destructive mid-day re-route.
                    tasks.append(Task(
                        pos,
                        [["DIG"], ["PLANT", turnover_crop], ["WATER"]],
                        {}, option_value, False, "CLEAR_WEED",
                    ))
        else:
            for pos in me.weeds:
                tasks.append(Task(pos, [["DIG"]], {},
                                  objective.weed_value(snap, plan), False,
                                  "CLEAR_WEED"))

    return _apply_paid_turnover_commitment(
        snap, _apply_service_commitment(
            snap, _apply_capital_positions(snap, tasks),
        ),
    )


ONGOING = ("STRAWBERRY", "TOMATO")


def _should_fertilize(snap, tile):
    enabled = (_os.environ.get("WB_FERT", "1") != "0"
               if _STRICT_FERT_ENABLED is None
               else bool(_STRICT_FERT_ENABLED))
    if not enabled:
        return False
    if tile.get("crop") not in ONGOING:
        return False
    if (_production_aligned_crop_service()
            and not _produces_tonight(snap, tile)):
        return False
    if tile.get("watered_today"):
        return False
    stock = snap.shed
    if _execution_variant() in (
            "paid_production_fertilizer_manifest",
            "paid_fertilizer_productive_shed_relocation_manifest"):
        stock = objective.planned_shed_stock(snap, _last_plan[0])
    if int(stock.get("FERTILIZER", 0) or 0) <= 0:
        return False
    return int(tile.get("fertilized_until_day", -1) or -1) < snap.day


def _buildable(snap):
    """Empty, unlocked, non-shed tiles -- ALWAYS in the same order.

    The order is part of the contract, not a detail. `enumerate_tasks` schedules
    BUILD on the first N of this list while `_build_here` designates the N
    nearest the shed; when the two disagreed they named different tiles, so the
    routed tile answered PLANT and the designated tile was never visited. Four
    animals then sat in the shed from step 1 to step 719 with a standing
    shortfall of four pastures and not one of them ever built.
    """
    return sorted((p for p in snap.me.empty
                   if paths.quadrant_of(*p) in snap.me.unlocked
                   and paths.productive_tile_allowed(snap, p)),
                  key=lambda p: (paths.dist_to_shed(p), p))


# A block of ongoing crop planted in one day matures together and rots into
# weeds together, because `_daily_refresh_plants` counts production off
# `planted_day`, so every tile in the block crosses `max_yield` on the same
# refresh. Two independent public sources implement the same fix under the
# same name ("wave"/"cohort") -- `sota1111/kaggriculture-gpt`'s public-prose
# note on the reactive-optimal-task candidate, and a collaborator's
# `barnyard_economist_v5` (which loses 0/96 against the pool overall, but its
# `build_roles` wave-staggering is the one piece of it that measured correct
# in isolation). WAVE_SIZE tiles per cohort, WAVE_GAP days before the next
# cohort starts -- both read off the LIVE tiles, never a fixed day schedule,
# so it works whichever day planting actually happens on.
WAVE_SIZE = int(_os.environ.get("WB_WAVE_SIZE", "12"))
WAVE_GAP = int(_os.environ.get("WB_WAVE_GAP", "3"))
WAVE_GATE = _os.environ.get("WB_WAVE_GATE", "1") != "0"


def _wave_state(snap, plan):
    """{crop: (tiles already queued this call, age of the newest live cohort)}."""
    newest = {}
    for t in snap.me.crops.values():
        c = t.get("crop")
        if c not in ONGOING:
            continue
        pd = int(t.get("planted_day", -999) or -999)
        if pd > newest.get(c, -999):
            newest[c] = pd
    return {c: (0, snap.day - newest.get(c, -999)) for c in ONGOING}


def _pick_crop(seeds, plan, snap, wave=None):
    """The crop furthest BELOW its target tile count, not the highest share.

    Planting by share alone has no stopping condition, and it showed: against
    the leader's structure we ran 57 STRAWBERRY beds where he holds 33, and
    grew ZERO wheat where he holds 27. Overshooting one crop is not free -- the
    tiles come out of the crop that is short, and the short one was the feed.

    So the rule is a deficit rule: of the crops we hold seed for and can still
    harvest in time, plant whichever is furthest below what the target structure
    says the farm should have. When nothing is short, fall back to value so
    spare tiles still earn.

    ONGOING crops additionally respect the wave gate: once a live cohort is
    both under `WAVE_GAP` days old and already holds `WAVE_SIZE` tiles, no more
    of that crop is planted until the cohort ages past the gap -- deliberately
    even if the deficit rule above says it is still short, because the
    alternative is exactly the failure mode this exists to avoid.
    """
    have = {}
    for t in snap.me.crops.values():
        c = t.get("crop")
        if c:
            have[c] = have.get(c, 0) + 1
    target = getattr(plan, "crop_targets", None) or {}
    wave = wave or {}
    best, best_gap, fallback, fb_v = None, 0.0, None, 0.0
    for crop, share in plan.crop_mix.items():
        if seeds.get(crop, 0) <= 0:
            continue
        if snap.step > econ.SEED_DEADLINE.get(crop, 719):
            continue
        if WAVE_GATE and crop in ONGOING:
            queued, age = wave.get(crop, (0, 999))
            if age < WAVE_GAP and queued >= WAVE_SIZE:
                continue
        target_n = float(target.get(crop, 0))
        gap = ((target_n - have.get(crop, 0)) / max(1.0, target_n)
               if target else 0.0)
        if gap > best_gap:
            best, best_gap = crop, gap
        v = share * econ.MARKET_PARAMS[crop]["base"]
        if v > fb_v:
            fallback, fb_v = crop, v
    return best or fallback


# Per-seat plan cache. Keyed by seat because the two players share this module
# inside one process and, like the tape's own guards, a shared dict would carry
# one seat's plan into the other's turn.
# ---------------------------------------------------------------------------
# EXACT TASK SELECTION AS A KNAPSACK, NOT A TOUR (2026-08-24 directive).
#
# The first version modelled a unit's day as an Orienteering Problem -- choose
# the SUBSET and ORDER of tasks to visit, `dp[mask][last]`, O(2^K * K^2), which
# needed K truncated to ~8-12 for tractability. That was the wrong shape for
# this game's task structure, and fixing the shape rather than the truncation
# is what actually made it exact.
#
# EVERY TASK IS A ROUND TRIP. FEED and FERTILIZE need their carry fetched from
# the shed before the op; HARVEST, PICKUP and COLLECT_FERTILIZER produce
# something that only banks on a DROP at the shed; PLACE needs the shed's
# animal stock. WATER, CARE, DIG and PLANT do not strictly need the shed, but
# costing them as a round trip too loses nothing but a little slack -- they are
# still selected whenever the travel is worth it.
#
# Because every trip both starts and ends at the SAME anchor (a shed-access
# tile -- `_spawn_hand` and the farmer's day-reset both place units there), no
# two trips share any travel. The problem is no longer "which order" -- there
# is no order to optimise, only "which subset fits the budget" -- which is a
# 0/1 KNAPSACK: item i costs `dist(start, pos_i) + len(ops_i) + dist(pos_i,
# nearest shed)` turns and is worth `value_i`. `O(N * budget)`, so the FULL
# daily candidate set (all ~50-75 tasks a partition can hold) is solved whole,
# no K truncation needed anywhere.
#
# `route/router.py::partition` still does the CROSS-UNIT split, unchanged: the
# spatial angular sweep is simultaneous for every unit and unbiased by
# processing order, which is what a first, sequential-per-unit version of this
# lacked -- the farmer, solved first, took the best of everything and every
# later hand inherited a steadily worse pool (measured: -5.8% against the
# greedy baseline). Partition first, then an exact knapsack per partition.
_EXACT_TOUR = _os.environ.get("WB_EXACT_TOUR", "0") != "0"


_SHED_OPS = frozenset(("FEED", "FERTILIZE", "HARVEST", "PICKUP", "PLACE",
                      "COLLECT_FERTILIZER"))


def _is_shed_dependent(task):
    """True if this tile-visit needs the shed BEFORE or AFTER the ops.

    FEED/FERTILIZE consume carry fetched from the shed; HARVEST/PICKUP/PLACE/
    COLLECT_FERTILIZER produce or place something that only banks on a shed
    DROP or draws from shed stock. WATER/CARE/DIG/PLANT touch neither: PLANT's
    seed comes straight out of `private["seeds"]`, never through a hand or the
    shed, so a tile whose only ops are these needs no shed trip at all.
    """
    if task.carry:
        return True
    return any(op and op[0] in _SHED_OPS for op in task.ops)


def _wb_dp_tour(start, budget, cands):
    """Exact best-value TOUR over `cands` -- for the shed-FREE category only.

    These tasks (WATER/CARE/DIG/PLANT) can be chained without a shed detour
    between them, so unlike the knapsack above, visiting order matters and the
    round-trip-per-task model would be wrong here. `dp[mask][last]` = fewest
    turns to have visited exactly `mask`, ending at `last` -- the same
    Orienteering solve validated in `pbt/endgame.py::_eg_solve_unit`, over the
    (typically small, tens not hundreds) shed-free candidate set for one unit.
    """
    k = len(cands)
    if k == 0 or budget <= 0:
        return 0.0, []
    INF = float("inf")
    size = 1 << k
    dp = [[INF] * k for _ in range(size)]
    par = [[-1] * k for _ in range(size)]
    for i, (pos, ops, _carry, _value) in enumerate(cands):
        dp[1 << i][i] = paths.dist(start, pos) + len(ops)
    for mask in range(size):
        row = dp[mask]
        for last in range(k):
            t = row[last]
            if t == INF:
                continue
            lp = cands[last][0]
            for nxt in range(k):
                if mask & (1 << nxt):
                    continue
                nt = t + paths.dist(lp, cands[nxt][0]) + len(cands[nxt][1])
                nm = mask | (1 << nxt)
                if nt < dp[nm][nxt]:
                    dp[nm][nxt] = nt
                    par[nm][nxt] = last
    best_v, best = -1.0, None
    for mask in range(1, size):
        val = sum(cands[i][3] for i in range(k) if mask & (1 << i))
        if val <= best_v:
            continue
        for last in range(k):
            t = dp[mask][last]
            if t != INF and t <= budget:
                best_v, best = val, (mask, last)
                break
    if best is None:
        return 0.0, []
    mask, last = best
    order = []
    while last >= 0:
        order.append(last)
        p = par[mask][last]
        mask ^= (1 << last)
        last = p
    order.reverse()
    return best_v, [cands[i] for i in order]


def _wb_knapsack(start, budget, cands):
    """Exact subset of independent round trips: shed -> task -> shed.

    Conservative by construction: real execution (`next_op`/`live_ops`) can
    chain two carry-free tasks (say, two adjacent WATER tiles) without
    detouring through the shed between them, so this can under-select what a
    perfect multi-stop tour could fit. It never over-selects -- every chosen
    trip's cost is a genuine upper bound on what executing it will take -- so
    the schedule this returns is always achievable, only not always the
    absolute maximum achievable. That trade is the whole point: it is what
    makes the subset choice EXACT and CHEAP instead of approximate and
    expensive.
    """
    items = []
    for pos, ops, carry, value in cands:
        home = min(paths.dist(pos, t) for t in paths.SHED_TILES)
        cost = paths.dist(start, pos) + len(ops) + home
        if 0 < cost <= budget:
            items.append((cost, value, pos, ops, carry))
    n = len(items)
    B = int(budget)
    if n == 0 or B <= 0:
        return 0.0, []
    dp = [[0.0] * (B + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        cost, value = items[i - 1][0], items[i - 1][1]
        row, prev = dp[i], dp[i - 1]
        for b in range(B + 1):
            best = prev[b]
            if cost <= b:
                alt = prev[b - cost] + value
                if alt > best:
                    best = alt
            row[b] = best
    b = B
    chosen = []
    for i in range(n, 0, -1):
        if dp[i][b] != dp[i - 1][b]:
            cost, value, pos, ops, carry = items[i - 1]
            chosen.append((pos, ops, carry, value))
            b -= cost
    return dp[n][B], chosen, B - b


def _assign_exact(snap, task_list):
    """Spatial partition (proven, unbiased), TWO exact solvers within each.

    `route/router.py::partition` assigns tasks to units, unchanged. Within one
    unit's assignment, tasks split into the two categories `_is_shed_dependent`
    tells apart, each solved by the algorithm that is actually exact FOR IT:

      shed-dependent (FEED/FERTILIZE/HARVEST/PICKUP/PLACE/COLLECT_FERTILIZER)
          independent round trips -- `_wb_knapsack`, O(N * budget), no
          ordering to solve because every trip returns to the same anchor.
      shed-free (WATER/CARE/DIG/PLANT)
          chainable without a shed detour, so order matters -- `_wb_dp_tour`,
          the Orienteering solve, over what is typically a few dozen
          candidates per unit (small enough that the un-truncated set is
          still fast).

    BUDGET SPLIT: the knapsack runs first, on the unit's FULL remaining
    budget, and reports how many turns it actually used -- knapsack only
    spends turns that are profitable, so it does not need to be told to leave
    room for anything else. The tour DP then gets whatever is left. This is
    not the jointly optimal split (that would need the value curve of both
    solvers over every possible split point), but it is a well-motivated one:
    shed-dependent tasks are typically few and high-value (a starving animal,
    a ready harvest), so they claim their turns first and rarely crowd out
    the much larger shed-free sweep.

    The two chosen lists are then run as ONE tour DP together for ORDERING
    ONLY -- not to change which tasks are kept, but because a route that
    interleaves a harvest stop with nearby water stops walks less than doing
    all the shed-dependent stops first and all the shed-free stops second.
    """
    units = [Unit(0, tuple(snap.me.farmer), snap.hour)]
    for i, pos in enumerate(snap.me.hands):
        units.append(Unit(i + 1, tuple(pos), snap.hour))
    assignment, leftover = router.partition(task_list, units)
    routes = {}
    undone = list(leftover)
    for u in units:
        pos = u.start
        budget = u.budget
        my_tasks = assignment.get(u.idx, [])
        if not my_tasks or budget <= 0:
            routes[u.idx] = []
            undone.extend(my_tasks)
            continue

        dependent = [t for t in my_tasks if _is_shed_dependent(t)]
        free = [t for t in my_tasks if not _is_shed_dependent(t)]

        dep_cands = [(t.pos, t.ops, t.carry, t.value) for t in dependent]
        _dv, dep_chosen, dep_turns = _wb_knapsack(pos, budget, dep_cands)

        # After any shed-dependent trips the unit is effectively back at the
        # shed (every trip both starts and ends there); the shed-free sweep
        # starts from there too, except when nothing shed-dependent was taken,
        # in which case the unit never left its actual position.
        free_start = paths.nearest_shed_tile(pos) if dep_chosen else pos
        free_budget = max(0, budget - dep_turns)
        free_cands = [(t.pos, t.ops, t.carry, t.value) for t in free]
        _fv, free_chosen = _wb_dp_tour(free_start, free_budget, free_cands)

        taken_pos = {c[0] for c in dep_chosen} | {c[0] for c in free_chosen}
        # Dependent stops first (each is its own round trip from `pos`, ending
        # back at the shed), free stops after (the tour DP already ordered
        # them starting from the shed). NOT re-optimised as one combined tour:
        # a first attempt at that re-solved the union with all values set to
        # 1.0 so it would only decide ORDER, not selection -- but with value
        # information erased, "best" collapsed to "most stops", and the DP
        # correctly-per-its-objective dropped FEED in favour of squeezing in
        # more WATER stops. Measured: bank $14. The concatenation below is not
        # travel-optimal across the seam between the two groups, but it is
        # correct, and correctness lost more here than travel-optimality ever
        # could.
        routes[u.idx] = [c[0] for c in dep_chosen] + [c[0] for c in free_chosen]
        undone.extend(t for t in my_tasks if t.pos not in taken_pos)
    return routes, undone


_PLAN = {}
_MANIFEST_INPUT_WAITS = set()


def reset(seat=None):
    if seat is None:
        _PLAN.clear()
        _MANIFEST_INPUT_WAITS.clear()
        _CAPITAL_POSITIONS.clear()
        _PAID_TURNOVER_CROPS.clear()
        _SERVICE_COMMITMENTS.clear()
    else:
        # Asset arrival invalidates only today's route assignment.  The
        # capital-position/service certificates are precisely what the fresh
        # route must now execute, so clearing them here would erase the cause
        # of this local replan.  A new episode calls the global branch above.
        _PLAN.pop(seat, None)
        _MANIFEST_INPUT_WAITS.difference_update(
            key for key in tuple(_MANIFEST_INPUT_WAITS)
            if key[0] == int(seat)
        )


def assign(snap, tasks, deadline=None, bank_outputs=False,
           deterministic_primal=False, bundle_master=False,
           deterministic_refine=False, paired_phase_bundle=False,
           temporal_paired_bundle=False, spatial_multistart=False):
    """Partition today's tiles across today's units, ONCE A DAY.

    THE BUG THIS FIXES WAS WORTH THE WHOLE GAME. Re-solving the day-VRP every
    turn re-partitions the board every turn, so a unit two steps into a walk
    toward a cow gets reassigned to a melon on the far side and never arrives.
    Measured: animals fed on 0 of 24 turns a day, so every animal starved out
    after two nights, the farm re-bought them, and the bank sat at $275 for four
    hundred steps. `route/router.py` says this in its own docstring -- one day is
    an independent multi-vehicle routing problem -- and calling it per turn
    quietly turns it into a different, unsolvable one.

    Historical variants cache only the tile order.  The opt-in manifest route
    also retains the router's planned operations and aggregate carry allocation,
    while still returning the same coordinate lists to every other subsystem.
    Live state remains the validity guard, so completed work falls away without
    a mid-day re-plan; the manifest only prevents execution from inventing a
    different crop, animal or series of one-item shed trips.
    """
    seat = snap.seat
    cache = _PLAN.get(seat)
    n_units = 1 + len(snap.me.hands)
    execution_variant = _execution_variant()
    paid_weed_turnover = _paid_weed_reinvestment()
    manifest_execution = execution_variant in _MANIFEST_EXECUTION
    if snap.step == 0:
        cache = None
    paid_incremental_kinds = tuple(
        str(kind)
        for kind in ((cache or {}).get(
            "paid_turnover_incremental_kinds", (),
        ) or ())
    )
    paid_turnover_incremental = bool(
        cache is not None
        and paid_weed_turnover
        and bool(cache.get("paid_weed_turnover", False))
        and int(cache.get("units", 0) or 0) > 1
        and paid_incremental_kinds
    )
    incremental_hire = bool(
        cache is not None
        and (execution_variant in (
                "incremental_hire_manifest",
                "paid_weed_reinvestment_incremental_hire_manifest",
                "paid_weed_reinvestment_bounded_hire_manifest",
            ) or paid_turnover_incremental)
        and cache.get("day") == snap.day
        and n_units > int(cache.get("units", 0) or 0)
        and bool(cache.get("bank_outputs", False)) == bool(bank_outputs)
        and bool(cache.get("deterministic_primal", False))
        == bool(deterministic_primal)
        and bool(cache.get("bundle_master", False)) == bool(bundle_master)
        and bool(cache.get("paired_phase_bundle", False))
        == bool(paired_phase_bundle)
        and bool(cache.get("temporal_paired_bundle", False))
        == bool(temporal_paired_bundle)
        and bool(cache.get("deterministic_refine", False))
        == bool(deterministic_refine)
        and bool(cache.get("spatial_multistart", False))
        == bool(spatial_multistart)
        and bool(cache.get("paid_weed_turnover", False))
        == bool(paid_weed_turnover)
    )
    if incremental_hire:
        # Incumbents keep every carried pickup and planned mutation from the
        # route already proved at the day opening. Only newly spawned hands
        # receive the explicit leftover set. Re-solving the union would lose
        # BUILD+PLACE tasks as soon as an incumbent had picked the animal out
        # of the shed, because that animal is then absent from live enumeration.
        old_units = int(cache["units"])
        cached_undone = list(cache.get("undone") or ())
        pending = (
            [task for task in cached_undone
             if str(task.kind) in paid_incremental_kinds]
            if paid_turnover_incremental else cached_undone
        )
        new_units = [
            Unit(idx, tuple(snap.me.hands[idx - 1]), snap.hour)
            for idx in range(old_units, n_units)
        ]
        bundle_model = (
            objective.TemporalPairedTaskBundleObjective(snap, pending)
            if temporal_paired_bundle else
            (objective.TaskBundleObjective(
                snap, pending, paired_phase=paired_phase_bundle,
            ) if bundle_master else None)
        )
        new_tours, new_undone = router.plan_day(
            new_units, pending, objective.planned_shed_stock(snap, _last_plan[0]),
            deadline=deadline, bank_outputs=bank_outputs,
            deterministic_primal=deterministic_primal,
            bundle_model=bundle_model,
            deterministic_refine=deterministic_refine,
            spatial_multistart=spatial_multistart,
        )
        routes = {uid: list(cache["routes"].get(uid, []))
                  for uid in range(old_units)}
        manifests = dict(cache.get("manifests") or {})
        for unit in new_units:
            tour = new_tours.get(unit.idx) or {
                "carry": {}, "stops": [], "tasks": [],
                "turn_cost": 0, "completion_hour": snap.hour,
            }
            routes[unit.idx] = [pos for pos, _ops in tour["stops"]]
            manifests[unit.idx] = tour
        cache = dict(cache)
        still_undone = (
            [task for task in cached_undone
             if str(task.kind) not in paid_incremental_kinds]
            + list(new_undone)
            if paid_turnover_incremental else list(new_undone)
        )
        cache.update({
            "units": n_units, "routes": routes, "manifests": manifests,
            "undone": still_undone,
            "incremental_first_unit": old_units,
            "paid_turnover_incremental_first_unit": (
                old_units if paid_turnover_incremental else None
            ),
            "paid_turnover_incremental_kinds": (),
        })
        _PLAN[seat] = cache
        return routes, cache["undone"]
    if (cache is None or cache["day"] != snap.day or cache["units"] != n_units
            or bool(cache.get("bank_outputs", False)) != bool(bank_outputs)
            or bool(cache.get("deterministic_primal", False))
            != bool(deterministic_primal)
            or bool(cache.get("bundle_master", False))
            != bool(bundle_master)
            or bool(cache.get("paired_phase_bundle", False))
            != bool(paired_phase_bundle)
            or bool(cache.get("temporal_paired_bundle", False))
            != bool(temporal_paired_bundle)
            or bool(cache.get("deterministic_refine", False))
            != bool(deterministic_refine)
            or bool(cache.get("spatial_multistart", False))
            != bool(spatial_multistart)
            or cache.get("execution_variant") != execution_variant
            or bool(cache.get("paid_weed_turnover", False))
            != bool(paid_weed_turnover)):
        # A same-day crew event normally triggers a joint re-plan. If another
        # layer already spent the act budget, keep every incumbent route and
        # leave only the new hands idle for this turn. This is an engine-valid
        # incumbent and is preferable to replacing a productive live plan with
        # a rushed one. A day change cannot reuse yesterday's route and falls
        # through to the fast feasible planner below.
        if (cache is not None and cache["day"] == snap.day and
                router.deadline_expired(deadline)
                and cache.get("execution_variant") == execution_variant
                and bool(cache.get("paid_weed_turnover", False))
                == bool(paid_weed_turnover)):
            routes = {uid: list(cache["routes"].get(uid, []))
                      for uid in range(n_units)}
            routed = {tuple(pos) for route in routes.values() for pos in route}
            undone = [task for task in tasks if tuple(task.pos) not in routed]
            # Do not write the temporary unit count back: on the next turn the
            # mismatch remains visible and triggers the full joint re-plan.
            return routes, undone
        fixed_owner = {}
        if cache is not None and cache["day"] == snap.day:
            live_positions = {tuple(task.pos) for task in tasks}
            for uid in range(min(cache["units"], n_units)):
                for pos in cache["routes"].get(uid, []):
                    pos = tuple(pos)
                    if pos in live_positions:
                        fixed_owner[pos] = uid
                        break
        turnover_removed = 0
        if _EXACT_TOUR:
            routes, undone = _assign_exact(snap, tasks)
            manifests = {}
        else:
            units = [Unit(0, snap.me.farmer, snap.hour)]
            for i, pos in enumerate(snap.me.hands):
                units.append(Unit(i + 1, pos, snap.hour))
            shed_stock = objective.planned_shed_stock(snap, _last_plan[0])
            # The isolated deterministic bundle master is a structurally
            # bounded greedy primal.  It must not choose a different feasible
            # incumbent merely because another arena worker consumed CPU.
            # Historical deterministic-route wrappers do not enable
            # ``bundle_master``; V75 does not enable ``deterministic_primal``.
            route_deadline = (None if bundle_master and deterministic_primal
                              else deadline)

            def solve(work):
                routed_work, hard_upgrades = (
                    _survival_feed_projection(snap, work)
                    if _survival_feed_hard_core() else
                    (list(work), {})
                )
                model_work = list(routed_work) + list(
                    hard_upgrades.values()
                )
                bundle_model = (
                    objective.TemporalPairedTaskBundleObjective(
                        snap, model_work,
                    )
                    if temporal_paired_bundle else
                    (objective.TaskBundleObjective(
                        snap, model_work,
                        paired_phase=paired_phase_bundle,
                    ) if bundle_master else None)
                )
                tours, _routed_undone = router.plan_day(
                    units, routed_work, shed_stock, fixed_owner=fixed_owner,
                    deadline=route_deadline, bank_outputs=bank_outputs,
                    deterministic_primal=deterministic_primal,
                    bundle_model=bundle_model,
                    deterministic_refine=deterministic_refine,
                    completion_balance=(
                        snap.day == 0
                        and execution_variant in _COMPLETION_BALANCE
                    ),
                    spatial_multistart=spatial_multistart,
                    hard_upgrades=hard_upgrades,
                )
                if not hard_upgrades:
                    return tours, _routed_undone

                # Translate the projected core universe back to live full
                # tasks for same-day incremental-hire bookkeeping. A core-only
                # route has completed survival FEED but may still offer the
                # original CARE/HARVEST/COLLECT bundle to a later new hand;
                # live manifest guards naturally remove the FEED already done.
                selected = {
                    id(task)
                    for tour in tours.values()
                    for task in (tour or {}).get("tasks", ())
                }
                routed_undone_ids = {id(item) for item in _routed_undone}
                core_for_full = {
                    id(full): core_id
                    for core_id, full in hard_upgrades.items()
                }
                undone_live = []
                for task in work:
                    if id(task) in selected:
                        continue
                    core_id = core_for_full.get(id(task))
                    if core_id is not None and core_id in selected:
                        undone_live.append(task)
                        continue
                    if core_id is not None or id(task) in routed_undone_ids:
                        undone_live.append(task)
                return tours, undone_live

            turnover = [
                task for task in tasks
                if (paid_weed_turnover and (
                    (task.kind == "CLEAR_WEED"
                     and any(op and op[0] == "PLANT" for op in task.ops))
                    or task.kind == "PAID_TURNOVER_SERVICE"
                ))
            ]
            if not turnover:
                tours, undone_r = solve(tasks)
            else:
                # First solve V199's exact ordinary task universe. Turnover is
                # then an additive option over *unused* route capacity: each
                # insertion must retain every task in that executable baseline
                # and still fit the same worker's physical day budget. This is
                # the constructive form of its labour opportunity cost; no
                # harvest, fertilizer collection or animal service may be
                # exchanged for a superficially profitable cleared tile.
                turnover_ids = {id(task) for task in turnover}
                ordinary = [
                    task for task in tasks if id(task) not in turnover_ids
                ]
                tours, _ordinary_undone = solve(ordinary)
                pending = [task for task in turnover if float(task.value) > 0]
                inserted = []
                while pending:
                    best = None
                    for task in pending:
                        for unit in units:
                            old_tour = tours.get(unit.idx) or {}
                            new_tour = router.append_unbanked_suffix(
                                unit, old_tour, task,
                                bank_outputs=bank_outputs,
                            )
                            if new_tour is None:
                                continue
                            old_cost = int(old_tour.get("turn_cost", 0) or 0)
                            new_cost = int(new_tour["turn_cost"])
                            delta = max(0, new_cost - old_cost)
                            key = (
                                float(task.value) / max(1.0, float(delta)),
                                float(task.value), -int(delta),
                                -paths.dist_to_shed(tuple(task.pos)),
                                tuple(-axis for axis in task.pos), -unit.idx,
                            )
                            if best is None or key > best[0]:
                                best = (key, task, unit, new_tour)
                    if best is None:
                        break
                    _key, task, unit, new_tour = best
                    tours[unit.idx] = new_tour
                    inserted.append(task)
                    pending.remove(task)

                selected = {
                    id(task)
                    for tour in tours.values()
                    for task in (tour or {}).get("tasks", ())
                }
                undone_r = [task for task in tasks if id(task) not in selected]
                turnover_removed = len(turnover) - len(inserted)
            routes = {u: [t for t, _ops in (tours.get(u) or {}).get("stops", [])]
                     for u in range(n_units)}
            manifests = dict(tours) if manifest_execution else {}
            undone = undone_r
        cache = {"day": snap.day, "units": n_units,
                 "routes": routes, "undone": undone,
                 "manifests": manifests,
                 "execution_variant": execution_variant,
                 "paid_weed_turnover": bool(paid_weed_turnover),
                 "paid_weed_turnover_removed": int(turnover_removed),
                 "bank_outputs": bool(bank_outputs),
                 "deterministic_primal": bool(deterministic_primal),
                 "bundle_master": bool(bundle_master),
                 "paired_phase_bundle": bool(paired_phase_bundle),
                 "temporal_paired_bundle": bool(temporal_paired_bundle),
                 "deterministic_refine": bool(deterministic_refine),
                 "spatial_multistart": bool(spatial_multistart)}
        _PLAN[seat] = cache
    return cache["routes"], cache["undone"]


def selected_input_requirement(snap, item):
    """Count an input only when it occurs in today's selected manifests."""
    cache = _PLAN.get(int(snap.seat))
    if cache is None or int(cache.get("day", -1)) != int(snap.day):
        return 0
    operation = "FERTILIZE" if str(item) == "FERTILIZER" else "FEED"
    return sum(
        1
        for manifest in (cache.get("manifests") or {}).values()
        for task in (manifest or {}).get("tasks", ())
        if any(op and op[0] == operation
               for op in (getattr(task, "ops", ()) or ()))
    )


def live_ops(snap, pos, inv=None):
    """What this tile needs RIGHT NOW, from live state. The cached route holds
    tile order only; every operation is re-derived here, so a tile that someone
    else already watered simply stops asking for work."""
    me = snap.me
    tile = me.animals.get(pos) or me.crops.get(pos)
    if pos in me.animals:
        ops, carry = [], {}
        if not tile.get("fed_today"):
            ops.append(["FEED"]); carry["WHEAT"] = 1
        if not tile.get("cared_today"):
            ops.append(["CARE"])
        held = int(tile.get("yield_units", 0) or 0)
        if held > 0:
            ops.append(["HARVEST"])          # see enumerate_tasks: never PICKUP
        if tile.get("fertilizer_available"):
            ops.append(["COLLECT_FERTILIZER"])
        return ops, carry
    if pos in me.crops:
        # Leader order within a crop tile: WATER before HARVEST (1676-494),
        # FERTILIZE before WATER so the bonus lands on the watered day.
        ops, carry = [], {}
        fertilizing = _should_fertilize(snap, tile)
        if fertilizing:
            ops.append(["FERTILIZE"])
            carry["FERTILIZER"] = 1
        if _crop_water_needed(snap, tile, fertilizing=fertilizing):
            ops.append(["WATER"])
        if _crop_ready(tile, snap.day):
            ops.append(["HARVEST"])
        return ops, carry
    raw = me.tiles[pos[1]][pos[0]] if 0 <= pos[1] < len(me.tiles) else None
    if isinstance(raw, dict) and raw.get("kind") in ("PASTURE", "COOP") and "animal" not in raw:
        # An empty structure wants an animal that is in the shed OR already in
        # somebody's hands. Checking the shed alone is self-cancelling: the
        # instant a unit PICKUPs the cow the shed count hits zero, the tile stops
        # asking for a PLACE, the unit is re-routed elsewhere and carries that
        # cow for the rest of the game. Measured: ONE `PLACE` op issued in 719
        # steps, peak herd of one, on a farm that had bought a dozen animals.
        # Judged against the SHED plus THIS unit's own pockets -- never against
        # every unit's. `snap.carried()` aggregates the whole crew, so unit A
        # would see the sheep in unit B's hands, decide the pasture wants one,
        # walk to an empty shed and try to PICKUP it, forever. Measured as a
        # livelock: the farmer repeated `PICKUP SHEEP 1` from step 47 to the end
        # of the game against a shed holding nothing.
        # The legacy branch used aggregate crew inventory here even though the
        # action is emitted for one specific unit.  If unit A carried the only
        # cow, every other worker then walked to the shed and repeated a failed
        # PICKUP forever.  The isolated correction reads this unit's own pocket;
        # the shed remains shared and is still constrained by the joint master.
        strict_unit = _execution_variant() in _STRICT_UNIT_INVENTORY
        carried = (dict(inv or {}) if strict_unit else snap.carried())
        for kind, spec in econ.ANIMALS.items():
            if spec["structure"] != raw["kind"]:
                continue
            if int(snap.shed.get(kind, 0) or 0) > 0 or int(carried.get(kind, 0) or 0) > 0:
                return [["PLACE", kind]], {kind: 1}
        return [], {}
    if isinstance(raw, dict) and raw.get("kind") == "WEED":
        return [["DIG"]], {}
    if raw is None:
        # An empty tile is a choice, not a default. Before the day cache was
        # introduced this branch always returned PLANT, which silently overrode
        # every BUILD_PASTURE the task planner had scheduled: structures were
        # never built, so animals could never be PLACEd, so the herd sat in the
        # shed and in hands' pockets for the whole game and `animals = 0` at
        # step 719 in every single ablation arm. A structure is worth more than
        # a crop tile whenever there is an animal with nowhere to stand.
        kind = _build_here(snap, pos)
        if kind:
            return [["BUILD_PASTURE" if kind == "PASTURE" else "BUILD_COOP"]], {}
        # Wave state is recomputed here (not cached) because this branch is
        # the low-volume opportunistic path -- it only runs when a unit's
        # cached route is exhausted -- so the O(crop tiles) cost of computing
        # it is paid rarely, and paying it wrongly would let exactly the
        # opportunistic path re-open a wave the main planting loop just closed.
        crop = (_pick_crop(dict(snap.seeds), _last_plan[0], snap,
                           _wave_state(snap, _last_plan[0]))
               if _last_plan[0] else None)
        if crop:
            # PLANT and WATER ride the same visit: `_new_plant` starts at
            # consecutive_unwatered = 1 and two unwatered nights is a weed.
            return [["PLANT", crop], ["WATER"]], {}
    return [], {}


_BUILD_PLAN = {}


def _build_here(snap, pos):
    """Structure to build on `pos`, or None. Bounded by the actual shortfall.

    `live_ops` is asked about one tile at a time and has no memory, so a naive
    "build if any animal is homeless" answers YES for every empty tile on the
    board and paves the farm: measured, that turned $12,786 into $934 because
    nothing was left to plant. The designation is therefore computed once per
    turn -- the N buildable tiles nearest the shed, N being the shortfall -- and
    every other tile falls through to planting.
    """
    key = (snap.seat, snap.step)
    plan = _BUILD_PLAN.get(key)
    if plan is None:
        _BUILD_PLAN.clear()
        need = _structure_shortfall(snap)
        spots = sorted(_buildable(snap), key=lambda p: paths.dist_to_shed(p))
        plan, i = {}, 0
        for kind in ("PASTURE", "COOP"):
            for _ in range(max(0, need.get(kind, 0))):
                if i >= len(spots):
                    break
                plan[spots[i]] = kind
                i += 1
        _BUILD_PLAN[key] = plan
    return plan.get(tuple(pos))


def _structure_shortfall(snap):
    """{structure: how many more we need} for animals with nowhere to stand.

    Counts animals held in the shed AND carried in unit inventories -- a unit
    that picked one up and found no free pasture is still holding it, and that
    animal is just as homeless as one in the shed.
    """
    free = {"PASTURE": 0, "COOP": 0}
    for row in snap.me.tiles:
        for t in row:
            if isinstance(t, dict) and "animal" not in t and t.get("kind") in free:
                free[t["kind"]] += 1
    carried = snap.carried()
    need = {"PASTURE": 0, "COOP": 0}
    for kind, spec in econ.ANIMALS.items():
        homeless = int(snap.shed.get(kind, 0) or 0) + int(carried.get(kind, 0) or 0)
        need[spec["structure"]] += homeless
    return {k: need[k] - free[k] for k in need}


_last_plan = [None]


# Same-day banking knobs; 0 disables, which is the pre-2026-08-25 behaviour.
DELIVER_MIN = int(_os.environ.get("WB_DELIVER_MIN", "0"))
DELIVER_HOUR = int(_os.environ.get("WB_DELIVER_HOUR", "18"))


def _opponent_standing_units(snap, item):
    total = 0
    for tile in snap.opp.animals.values():
        kind = tile.get("animal")
        if kind in econ.ANIMALS and econ.ANIMALS[kind]["product"] == item:
            total += max(0, int(tile.get("yield_units", 0) or 0))
    for tile in snap.opp.crops.values():
        if tile.get("crop") == item:
            total += max(0, int(tile.get("yield_units", 0) or 0))
    return total


def _robust_bank_now(snap, pos, inv, route):
    """Whether a shed detour beats continuing the current route.

    The uncertainty set contains every unit the opponent visibly has standing
    on a tile: they can legally harvest, DROP and sell it before our overnight
    auto-deposit. We price that adversarial sale unit-by-unit on the exact book,
    then compare the resulting loss on our carried goods with the value density
    of the next still-live route task times the incremental detour turns. This
    is a local robust best response over public state, not a sale schedule.
    """
    carried = {item: max(0, int(qty or 0)) for item, qty in (inv or {}).items()
               if item in econ.SELLABLE and item != "WHEAT" and int(qty or 0) > 0}
    if not carried:
        return False
    shed = paths.nearest_shed_tile(pos)
    to_bank = paths.dist(pos, shed) + 1
    if to_bank > max(0, econ.TURNS_PER_DAY - snap.hour):
        return False

    exposure = 0.0
    for item, qty in carried.items():
        rival = _opponent_standing_units(snap, item)
        if rival <= 0:
            continue
        inv0 = int(snap.market_inv.get(item, econ.MARKET_I0) or econ.MARKET_I0)
        now = econ.sell_revenue(item, qty, inv0)
        later = econ.sell_revenue(item, qty, inv0 + rival)
        exposure += max(0.0, float(now - later))
    if exposure <= 0:
        return False

    next_tile = None
    next_value = 0.0
    next_turns = 1
    for raw in route or ():
        tile = tuple(raw)
        ops, _carry = live_ops(snap, tile, inv)
        if not ops:
            continue
        next_tile = tile
        next_value = max(0.0, float(_live_task_value(snap, tile, ops)))
        next_turns = max(1, paths.dist(pos, tile) + len(ops))
        break
    if next_tile is None:
        return True
    direct = paths.dist(pos, next_tile)
    via_shed = paths.dist(pos, shed) + 1 + paths.dist(shed, next_tile)
    detour = max(1, via_shed - direct)
    opportunity = detour * (next_value / float(next_turns))
    return exposure > opportunity


def _cached_manifest(snap, unit_idx):
    """The router certificate for this worker, only in the isolated arm."""
    cache = _PLAN.get(snap.seat)
    if (cache is None or cache.get("day") != snap.day
            or cache.get("execution_variant") not in _MANIFEST_EXECUTION
            or bool(cache.get("paid_weed_turnover", False))
            != bool(_paid_weed_reinvestment())):
        return None
    return (cache.get("manifests") or {}).get(unit_idx)


def _manifest_specs(manifest):
    """Return ``pos -> (planned ops, task kinds)`` from one route certificate."""
    planned = {
        tuple(pos): [list(op) for op in ops]
        for pos, ops in (manifest or {}).get("stops", ())
    }
    kinds = {}
    for task in (manifest or {}).get("tasks", ()):
        kinds.setdefault(tuple(task.pos), set()).add(task.kind)
    return {pos: (ops, kinds.get(pos, set())) for pos, ops in planned.items()}


def _planned_live_ops(snap, pos, inv, planned_ops, kinds=()):
    """Live remainder of one *specific* planned stop.

    The ordinary live planner answers "what could be useful on this coordinate
    now".  A route certificate needs the narrower question "what remains of the
    mutation that was costed for this coordinate".  In particular, a completed
    one-shot harvest must not turn into an uncosted PLANT, and a newly placed
    animal must not add uncosted FEED/CARE operations to a BUILD+PLACE column.
    """
    pos = tuple(pos)
    planned_ops = [list(op) for op in (planned_ops or ()) if op]
    names = [op[0] for op in planned_ops]
    raw = (snap.me.tiles[pos[1]][pos[0]]
           if 0 <= pos[1] < len(snap.me.tiles)
           and 0 <= pos[0] < len(snap.me.tiles[pos[1]]) else None)

    build = next((op for op in planned_ops
                  if op[0] in ("BUILD_PASTURE", "BUILD_COOP")), None)
    place = next((op for op in planned_ops
                  if op[0] == "PLACE" and len(op) > 1), None)
    plant = next((op for op in planned_ops
                  if op[0] == "PLANT" and len(op) > 1), None)

    # BUILD+PLACE is one physical column.  Carry the animal before leaving the
    # shed, build on one turn, then place on the next without an extra round trip.
    if build is not None:
        carry = {place[1]: 1} if place is not None else {}
        if raw is None:
            return [list(build)], carry
        expected = "PASTURE" if build[0] == "BUILD_PASTURE" else "COOP"
        if (place is not None and isinstance(raw, dict)
                and raw.get("kind") == expected and "animal" not in raw):
            return [list(place)], carry
        return [], {}

    if place is not None:
        kind = place[1]
        spec = econ.ANIMALS.get(kind) or {}
        if (isinstance(raw, dict) and "animal" not in raw
                and raw.get("kind") == spec.get("structure")):
            return [list(place)], {kind: 1}
        return [], {}

    # A selected crop column owns its crop identity.  Once PLANT succeeds only
    # its paired WATER remains; generic live work on that coordinate is not part
    # of this certificate.
    if plant is not None and "DIG" in names:
        crop = plant[1]
        if isinstance(raw, dict) and raw.get("kind") == "WEED":
            return [["DIG"]], {}
        if raw is None:
            if int(snap.seeds.get(crop, 0) or 0) <= 0:
                # The route already paid for this exact DIG+seed+PLANT chain.
                # Stay on its released tile while the market phase clears the
                # retained seed order. Falling through to the next stop lets
                # one fungible seed satisfy a different DIG and destroys the
                # position certificate.
                return [["PASS"]], {}
            return [list(plant)], {}
        if (isinstance(raw, dict) and raw.get("kind") == "PLANT"
                and raw.get("crop") == crop and not raw.get("watered_today")):
            return [["WATER"]], {}
        return [], {}

    if plant is not None:
        crop = plant[1]
        if raw is None:
            if int(snap.seeds.get(crop, 0) or 0) <= 0:
                return [], {}
            return [list(plant)], {}
        if (isinstance(raw, dict) and raw.get("kind") == "PLANT"
                and raw.get("crop") == crop and not raw.get("watered_today")):
            return [["WATER"]], {}
        return [], {}

    if "DIG" in names or "CLEAR_WEED" in kinds:
        if isinstance(raw, dict) and raw.get("kind") == "WEED":
            return [["DIG"]], {}
        return [], {}

    # Service bundles are state-derived, but only while the original asset type
    # still occupies the tile.  This preserves legal op ordering and naturally
    # removes actions already completed by another worker.
    animal_service = ("ANIMAL_SERVICE" in kinds or
                      any(name in ("FEED", "CARE", "COLLECT_FERTILIZER")
                          for name in names))
    crop_service = ("CROP_SERVICE" in kinds or
                    any(name in ("FERTILIZE", "WATER") for name in names))
    if animal_service:
        tile = snap.me.animals.get(pos)
        if tile is None:
            return [], {}
        ops, carry = [], {}
        if "FEED" in names and not tile.get("fed_today"):
            ops.append(["FEED"])
            carry["WHEAT"] = 1
        if "CARE" in names and not tile.get("cared_today"):
            ops.append(["CARE"])
        if ("HARVEST" in names
                and int(tile.get("yield_units", 0) or 0) > 0):
            ops.append(["HARVEST"])
        if ("COLLECT_FERTILIZER" in names
                and tile.get("fertilizer_available")):
            ops.append(["COLLECT_FERTILIZER"])
        return ops, carry
    if crop_service:
        tile = snap.me.crops.get(pos)
        if tile is None:
            return [], {}
        ops, carry = [], {}
        # Do not ask `_should_fertilize`: after the route's batch PICKUP the
        # shared shed may correctly be empty while this worker holds every
        # reserved unit in its own pocket.
        if ("FERTILIZE" in names and not tile.get("watered_today")
                and int(tile.get("fertilized_until_day", -1) or -1) < snap.day):
            ops.append(["FERTILIZE"])
            carry["FERTILIZER"] = 1
        if "WATER" in names and _crop_water_needed(
                snap, tile, fertilizing="FERTILIZE" in names):
            ops.append(["WATER"])
        if "HARVEST" in names and _crop_ready(tile, snap.day):
            ops.append(["HARVEST"])
        return ops, carry
    if "HARVEST" in names:
        if pos in snap.me.animals or pos in snap.me.crops:
            return live_ops(snap, pos, inv)
        return [], {}
    return [], {}


def _manifest_requirements(snap, manifest, inv):
    """Aggregate inputs still required by this worker's unfinished stops.

    Quantities are capped by the router's per-worker allocation.  Since every
    worker receives a disjoint slice of the shared shed stock during
    ``build_tour``, simultaneous pickup requests cannot intentionally steal one
    another's inputs.
    """
    specs = _manifest_specs(manifest)
    needed = {}
    for pos, (planned_ops, kinds) in specs.items():
        ops, carry = _planned_live_ops(snap, pos, inv, planned_ops, kinds)
        if not ops:
            continue
        for item, qty in carry.items():
            needed[item] = needed.get(item, 0) + max(0, int(qty or 0))
    reserved = dict((manifest or {}).get("carry", {}) or {})
    return {item: min(qty, max(0, int(reserved.get(item, 0) or 0)))
            for item, qty in needed.items()
            if qty > 0 and int(reserved.get(item, 0) or 0) > 0}


def _wait_for_certified_input(snap, unit_idx, item, required, inv):
    """Spend only an already-certified pickup credit waiting for an input.

    A same-day crew re-plan can inherit one manifest input in this worker's
    pocket while another input is scheduled to arrive in the market phase.
    The route model conservatively charged one PICKUP for *both* item types.
    Leaving the shed and returning after the purchase wastes two moves and can
    make a survival FEED miss the day boundary.  Waiting once consumes the
    pickup turn made unnecessary by the inherited item, so the original route
    turn certificate remains valid.  If the purchase does not arrive, the
    retained wait certificate prevents another uncharged wait next turn.
    """
    plan = _last_plan[0]
    target_name = (
        "wheat_needed" if str(item) == "WHEAT" else
        "fertilizer_target" if str(item) == "FERTILIZER" else None
    )
    if plan is None or target_name is None:
        return False
    carried_fn = getattr(snap, "carried", None)
    carried = (carried_fn() if callable(carried_fn) else {
        name: sum(int(stock.get(name, 0) or 0)
                  for stock in getattr(snap, "inventories", ()))
        for name in required
    })
    owned = (int(snap.shed.get(item, 0) or 0)
             + int(carried.get(item, 0) or 0))
    target = max(0, int(getattr(plan, target_name, 0) or 0))
    if target <= owned:
        return False

    # Each distinct already-satisfied input removes exactly one PICKUP action
    # which route_cost charged. Never wait more times than those saved turns.
    credits = sum(
        1 for name, qty in required.items()
        if int(qty) > 0 and int(inv.get(name, 0) or 0) >= int(qty)
    )
    prefix = (int(snap.seat), int(snap.day), int(unit_idx))
    used = sum(1 for key in _MANIFEST_INPUT_WAITS if key[:3] == prefix)
    key = prefix + (str(item),)
    if credits <= used or key in _MANIFEST_INPUT_WAITS:
        return False
    _MANIFEST_INPUT_WAITS.add(key)
    return True


def next_op(snap, unit_idx, route, robust_banking=False,
            bank_after_route=False, auto_bank_after_route=False,
            bank_detour_after_route=False):
    """This turn's single action for one unit, re-derived from where it IS."""
    pos = snap.me.farmer if unit_idx == 0 else (
        snap.me.hands[unit_idx - 1] if unit_idx - 1 < len(snap.me.hands) else None)
    if pos is None:
        return ["PASS"]
    pos = tuple(pos)
    inv = snap.inventories[unit_idx] if unit_idx < len(snap.inventories) else {}

    if robust_banking and _robust_bank_now(snap, pos, inv, route):
        return _deliver(pos, inv)

    manifest = _cached_manifest(snap, unit_idx)
    manifest_specs = _manifest_specs(manifest) if manifest is not None else {}
    if manifest is not None:
        # The route solver charged one PICKUP per distinct item, with the whole
        # quantity in that action.  Recreate exactly that batch for the live
        # unfinished suffix.  The old coordinate-only executor fetched one unit
        # for the current tile, consumed it, and walked back to the shed before
        # every later FEED/PLACE -- work the hiring model never charged.
        required = _manifest_requirements(snap, manifest, inv)
        missing = {
            item: max(0, int(qty) - int(inv.get(item, 0) or 0))
            for item, qty in required.items()
            if int(inv.get(item, 0) or 0) < int(qty)
        }
        available = [(item, min(qty, int(snap.shed.get(item, 0) or 0)))
                     for item, qty in sorted(missing.items())
                     if int(snap.shed.get(item, 0) or 0) > 0]
        if available:
            if pos in paths.SHED_SET:
                item, qty = available[0]
                return ["PICKUP", item, int(qty)]
            mv = paths.step_toward(pos, paths.nearest_shed_tile(pos))
            return [mv] if mv else ["PASS"]
        if pos in paths.SHED_SET:
            incoming = next((
                item for item in sorted(missing)
                if _wait_for_certified_input(
                    snap, unit_idx, item, required, inv,
                )
            ), None)
            if incoming is not None:
                return ["PASS"]

    for tile in (route or []):
        tile = tuple(tile)
        if manifest is None:
            ops, carry = live_ops(snap, tile, inv)
        else:
            planned_ops, kinds = manifest_specs.get(tile, ((), ()))
            ops, carry = _planned_live_ops(
                snap, tile, inv, planned_ops, kinds,
            )
        if not ops:
            continue
        missing = {k: v for k, v in carry.items() if int(inv.get(k, 0) or 0) < v}
        if missing:
            # A predicted purchase can arrive only in the market phase.  If it
            # has not arrived, skip this dependent stop for now instead of
            # issuing a failed PICKUP forever; the cached route retries it on
            # the next observation.
            if manifest is not None and not any(
                    int(snap.shed.get(k, 0) or 0) > 0 for k in missing):
                continue
            if pos in paths.SHED_SET:
                item, n = sorted(missing.items())[0]
                available_n = int(snap.shed.get(item, 0) or 0)
                return ["PICKUP", item, int(min(n, available_n) if manifest is not None
                                             else n)]
            mv = paths.step_toward(pos, paths.nearest_shed_tile(pos))
            return [mv] if mv else ["PASS"]
        if pos == tile:
            return list(ops[0])
        mv = paths.step_toward(pos, tile)
        return [mv] if mv else ["PASS"]

    # A paid incremental crew certificate is not permission to alter the
    # incumbent service allocation.  V181 correctly preserved old route
    # manifests, but after clearing its named weeds a fresh hand fell through
    # to global opportunistic work and could take an animal operation before
    # its original owner arrived.  The bounded arm closes that execution set:
    # only workers added by the current day's incremental certificate stop
    # here; incumbents retain the historical opportunistic path.
    cache = _PLAN.get(snap.seat) or {}
    paid_incremental_first = cache.get(
        "paid_turnover_incremental_first_unit",
    )
    bounded_first = (
        paid_incremental_first
        if paid_incremental_first is not None
        else cache.get("incremental_first_unit", 10 ** 9)
    )
    bounded_incremental = bool(
        (_execution_variant()
         == "paid_weed_reinvestment_bounded_hire_manifest"
         or (bool(cache.get("paid_weed_turnover", False))
             and paid_incremental_first is not None))
        and cache.get("day") == snap.day
        and unit_idx >= int(bounded_first)
    )
    if bounded_incremental:
        carrying = sum(int(v or 0) for item, v in inv.items()
                       if item in econ.SELLABLE and int(v or 0) > 0)
        return _deliver(pos, inv) if carrying > 0 else ["PASS"]

    # The V55 route master already charged the selected output-bearing route
    # for its return leg and DROP. Honour that certificate before searching
    # for opportunistic work, otherwise emission would spend the reserved tail
    # on a new tile and recreate the overnight-only banking bug.
    if bank_after_route and not auto_bank_after_route:
        carrying = sum(int(v or 0) for k, v in inv.items()
                       if k in econ.SELLABLE and int(v or 0) > 0)
        if carrying > 0:
            if bank_detour_after_route:
                detour = _certified_bank_detour(snap, pos, inv)
                if detour is not None:
                    return detour
            return _deliver(pos, inv)

    # SAME-DAY BANKING (2026-08-25). Read off ReCurSiON's replays, not invented.
    #
    # The engine banks every hand inventory automatically at `_end_of_day`, so a
    # unit NEVER has to walk to the shed -- which is why this agent emitted 0
    # DROPs in 5,515 mid-game unit-actions. But automatic banking lands the
    # goods AFTER the last turn of the day, so they are not sellable until the
    # next day, and anything past shedCapacity at that moment is DISCARDED.
    #
    # The ladder's strongest distinct agent does not accept that. Across three
    # replays ReCurSiON plays 58 DROPs, 37 of them mid-game, piled into hours
    # 19-23 -- and 30 of those 37 are followed by a SELL THE SAME DAY. A DROP
    # banks immediately; the free deposit costs a day of price. (Most other
    # strong seats do exactly what we do: 9-11 DROPs, none mid-game. And
    # ReCurSiON's DROP schedule is byte-identical across seats and across
    # rewards of 44k and 167k, so it is a fixed tape, not a reactive rule.)
    #
    # This is the cheap version of that: once a unit is carrying enough to be
    # worth a trip and the day is nearly over, bank it instead of looking for
    # one more chore.
    if DELIVER_MIN > 0 and snap.hour >= DELIVER_HOUR:
        carrying = sum(int(v or 0) for k, v in inv.items() if k in econ.SELLABLE)
        if carrying >= DELIVER_MIN:
            return _deliver(pos, inv)

    # Route exhausted. Before idling, look for work that did not exist when the
    # day was planned.
    #
    # The day cache is built at hour 0, so anything created later -- a structure
    # raised at hour 6, an animal bought at hour 9 -- is in NO unit's route and
    # stays untouched until tomorrow. That is why a farm that bought a dozen
    # animals issued exactly ONE `PLACE` in 719 steps. Rather than re-solving the
    # VRP mid-day (which is the thrash this cache exists to prevent), an idle
    # unit just walks to the nearest tile that still wants something.
    op = _opportunistic(snap, pos, inv)
    if op is not None:
        return op

    # When the caller has proved that the complete day's shed plus every
    # carried/harvestable unit fits, the engine's end-of-day refresh performs
    # this deposit for free.  Do not spend an unreserved tail walking home.
    # Unsafe-capacity states never set this flag and retain the physical DROP.
    if auto_bank_after_route:
        return ["PASS"]

    # Anything the unit is still CARRYING is unsellable until it reaches the
    # shed: `SELL` draws from `private["shed"]` and only a `DROP` on a
    # shed-access tile moves it there (HANDOFF rule 5). Omitting this step is
    # what made the first working build bank $3,000 with eight producing animals
    # -- every unit of milk it ever picked up was still in a hand's pocket at
    # step 719.
    return _deliver(pos, inv)


def _opportunistic(snap, pos, inv):
    """Nearest tile with live work, weighted by value over distance."""
    best, best_score = None, 0.0
    for tile in _candidate_tiles(snap):
        if tile == pos:
            continue
        raw = snap.me.tiles[tile[1]][tile[0]]
        if (_paid_weed_reinvestment()
                and isinstance(raw, dict) and raw.get("kind") == "WEED"
                and paid_turnover_item(snap, tile) is None):
            # A bare opportunistic DIG has no reserved seed, PLANT/WATER turns
            # or retained crop identity. Leave it untouched; only the named
            # atomic turnover columns may exercise this option.
            continue
        ops, carry = live_ops(snap, tile, inv)
        if not ops:
            continue
        if any(int(inv.get(k, 0) or 0) < v for k, v in carry.items()):
            # would need a shed trip first; only worth it for placing an animal
            if ops[0][0] != "PLACE":
                continue
        value = _live_task_value(snap, tile, ops)
        score = value / (paths.dist(pos, tile) + len(ops) + 1.0)
        if score > best_score:
            best, best_score = (tile, ops, carry), score
    if best is None:
        return None
    tile, ops, carry = best
    missing = {k: v for k, v in carry.items() if int(inv.get(k, 0) or 0) < v}
    if missing:
        if pos in paths.SHED_SET:
            item, n = sorted(missing.items())[0]
            return ["PICKUP", item, int(n)]
        mv = paths.step_toward(pos, paths.nearest_shed_tile(pos))
        return [mv] if mv else ["PASS"]
    if pos == tile:
        return list(ops[0])
    mv = paths.step_toward(pos, tile)
    return [mv] if mv else None


def _certified_bank_detour(snap, pos, inv):
    """Best live task whose complete detour still ends in today's DROP.

    The incumbent V149 route has already exhausted its selected stops and has
    reserved a direct return.  A live task may precede that return only when
    movement to the tile, every currently required operation, movement from
    the tile to the nearest shed and one DROP all fit in the exact remaining
    public action budget.  Inputs must already be in this worker's inventory;
    no unpriced market or shed action is assumed.
    """
    remaining = max(0, econ.TURNS_PER_DAY - int(snap.hour))
    best = None
    for raw in _candidate_tiles(snap):
        tile = tuple(raw)
        ops, carry = live_ops(snap, tile, inv)
        if not ops:
            continue
        if any(int(inv.get(item, 0) or 0) < int(qty or 0)
               for item, qty in carry.items()):
            continue
        shed = paths.nearest_shed_tile(tile)
        turns = (
            paths.dist(pos, tile) + len(ops)
            + paths.dist(tile, shed) + 1
        )
        if turns > remaining:
            continue
        value = max(0.0, float(_live_task_value(snap, tile, ops)))
        if value <= 0.0:
            continue
        rank = (value / max(1.0, float(turns)), value, -turns)
        if (best is None or rank > best[0]
                or (rank == best[0] and tile < best[1])):
            best = (rank, tile, ops)
    if best is None:
        return None
    _rank, tile, ops = best
    if pos == tile:
        return list(ops[0])
    move = paths.step_toward(pos, tile)
    return [move] if move else None


def _live_task_value(snap, pos, ops):
    """Value an unplanned live bundle with the same objective as day planning."""
    tile = snap.me.animals.get(pos)
    if tile is not None:
        return objective.animal_task_value(snap, tile, ops)[0]
    tile = snap.me.crops.get(pos)
    if tile is not None:
        return objective.crop_task_value(snap, tile, ops)[0]
    first = ops[0] if ops else ["PASS"]
    op = first[0]
    if op == "PLACE" and len(first) > 1:
        return objective.animal_placement_value(snap, first[1])
    if op == "PLANT" and len(first) > 1:
        return objective.plant_value(snap, first[1])
    if op == "DIG":
        return objective.weed_value(snap, _last_plan[0])
    if op.startswith("BUILD_"):
        structure = "COOP" if op == "BUILD_COOP" else "PASTURE"
        kinds = [k for k, spec in econ.ANIMALS.items()
                 if spec["structure"] == structure
                 and int(snap.shed.get(k, 0) or 0) > 0]
        return max((objective.animal_placement_value(snap, k) for k in kinds),
                   default=0.0)
    return 0.0


_CAND_CACHE = {}


def _candidate_tiles(snap):
    """Tiles worth considering for opportunistic work. Cached per turn.

    `_opportunistic` runs for every idle unit, and rebuilding this list inside
    each of them scanned the 100-tile board up to twelve times a turn, 719 times
    a game. The board cannot change between two units' calls within one turn --
    actions are applied after every unit has been polled -- so one scan is
    correct as well as cheaper.
    """
    key = (snap.seat, snap.step)
    hit = _CAND_CACHE.get(key)
    if hit is not None:
        return hit
    _CAND_CACHE.clear()
    out = list(snap.me.animals) + list(snap.me.crops)
    for y, row in enumerate(snap.me.tiles):
        for x, t in enumerate(row):
            if t is None or (isinstance(t, dict) and t.get("kind") in ("PASTURE", "COOP", "WEED")):
                if paths.quadrant_of(x, y) in snap.me.unlocked:
                    out.append((x, y))
    _CAND_CACHE[key] = out
    return out


def _deliver(pos, inv):
    """Walk to the shed and DROP, if this unit is holding anything sellable."""
    carrying = sum(int(v or 0) for k, v in (inv or {}).items()
                   if k in econ.SELLABLE and int(v or 0) > 0)
    if carrying <= 0:
        return ["PASS"]
    if tuple(pos) in paths.SHED_SET:
        return ["DROP"]
    mv = paths.step_toward(pos, paths.nearest_shed_tile(pos))
    return [mv] if mv else ["DROP"]


# ------------------------------------------------------- endgame collector

ENDGAME_TAKEOVER = 8          # measured optimum; see HANDOFF section 38


def endgame_collect(snap, unit_idx):
    """The validated last-8-step liquidation, ported from `submission/v5_tk8.py`.

    Why EIGHT and not fifty. Inside ~8 steps nothing planted can still grow, so
    every remaining turn is worth exactly what it converts into shed stock and a
    dedicated collect-and-deliver planner beats a general one. Past ~12 the
    window starts eating production the farm is still doing, and section 36's
    fidelity cost takes over. Measured against the same baseline: 8 steps
    +303 sim / +302 real at 85.8%/90.3% win, 12 steps -70, 25 steps -6,345,
    50 steps -13,601. The window is not a parameter to push -- it is the width
    of the region where the objective has genuinely changed.

    HARVEST, never PICKUP: `_apply_unit_action`'s HARVEST branch covers crops
    AND animals, while PICKUP is a shed withdrawal that no-ops anywhere else.
    """
    pos = snap.me.farmer if unit_idx == 0 else (
        snap.me.hands[unit_idx - 1] if unit_idx - 1 < len(snap.me.hands) else None)
    if pos is None:
        return ["PASS"]
    pos = tuple(pos)
    inv = snap.inventories[unit_idx] if unit_idx < len(snap.inventories) else {}
    carrying = sum(int(v or 0) for k, v in (inv or {}).items()
                   if k in econ.SELLABLE and int(v or 0) > 0)
    room = snap.shed_room
    if carrying > 0:
        if pos in paths.SHED_SET:
            # Never drop into a shed that cannot take it: DROP deletes the
            # surplus rather than leaving it in hand. On the last step holding
            # is worth nothing either, so drop regardless.
            return ["DROP"] if (room >= carrying or snap.step >= 718) else ["PASS"]
        mv = paths.step_toward(pos, paths.nearest_shed_tile(pos))
        return [mv] if mv else ["DROP"]
    best, best_d = None, None
    for tile, t in list(snap.me.animals.items()) + list(snap.me.crops.items()):
        units = int(t.get("yield_units", 0) or 0)
        if units <= 0 or units > room:
            continue
        d = paths.dist(pos, tile)
        if snap.step + d + 2 > 718:
            continue
        if best_d is None or d < best_d:
            best, best_d = tile, d
    if best is None:
        mv = paths.step_toward(pos, paths.nearest_shed_tile(pos))
        return [mv] if mv else ["PASS"]
    if pos == best:
        return ["HARVEST"]
    mv = paths.step_toward(pos, best)
    return [mv] if mv else ["PASS"]
