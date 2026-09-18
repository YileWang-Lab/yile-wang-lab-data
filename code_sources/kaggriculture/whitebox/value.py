"""Engine-derived relaxed terminal-dollar values for task bundles.

This is the common objective used by task selection, worker assignment, route
ordering, and hiring.  It deliberately returns dollars, not priority points.
The relaxation assumes that output which can mature before the last actionable
day is eventually sold, while pricing it after all currently visible opponent
output of the same item.  That is a transparent robust lower book, not a style
prediction or replay statistic.
"""
import math
from collections import Counter
from functools import lru_cache

from whitebox import econ


LAST_ACTION_DAY = 29
_EXACT_ZERO_DAY_AGE = False


def set_exact_zero_day_age(enabled):
    """Select whether public day zero is a date or a legacy missing value."""
    global _EXACT_ZERO_DAY_AGE
    _EXACT_ZERO_DAY_AGE = bool(enabled)


def _dated_field(tile, key, default):
    raw = tile.get(key, default)
    if _EXACT_ZERO_DAY_AGE:
        return int(default if raw is None else raw)
    return int(raw or default)


def _visible_opp_units(snap, item):
    units = 0
    for tile in snap.opp.animals.values():
        kind = tile.get("animal")
        if kind in econ.ANIMALS and econ.ANIMALS[kind]["product"] == item:
            units += int(tile.get("yield_units", 0) or 0)
    for tile in snap.opp.crops.values():
        if tile.get("crop") == item:
            units += int(tile.get("yield_units", 0) or 0)
    return max(0, units)


def sale_value(snap, item, qty):
    """Robust current-book value after visible opponent standing supply."""
    qty = max(0, int(qty))
    if qty <= 0 or item not in econ.SELLABLE:
        return 0.0
    inv = int(snap.market_inv.get(item, econ.MARKET_I0) or econ.MARKET_I0)
    inv += _visible_opp_units(snap, item)
    return float(econ.sell_revenue(item, qty, inv))


def paired_phase_sale_value(snap, item, qty):
    """Worst same-slot margin over currently visible opponent stock.

    The engine quotes both players from the same pre-commit inventory for each
    joint unit.  We enumerate the public interval ``0..visible`` rather than
    assume an opponent quantity distribution.  Hidden stock remains the job
    of bundle objectives, where one conserved shed-capacity budget can be
    shared across items.
    """
    qty = max(0, int(qty))
    if qty <= 0 or item not in econ.SELLABLE:
        return 0.0
    inv = int(snap.market_inv.get(item, econ.MARKET_I0) or econ.MARKET_I0)
    from whitebox.cashflow import _paired_sale_value
    return float(_paired_sale_value(
        item, qty, inv, _visible_opp_units(snap, item),
    ))


@lru_cache(maxsize=32768)
def _temporal_rule_price(item, inventory):
    """Exact engine price memo local to the multi-phase objective."""
    return int(econ.price(item, int(inventory)))


@lru_cache(maxsize=65536)
def _temporal_sale_result(item, qty, inventory):
    """Exact sale transition using the memoized pure rule price equation."""
    inv = int(inventory)
    revenue = 0.0
    for _ in range(max(0, int(qty))):
        unit_price = _temporal_rule_price(item, inv)
        revenue += unit_price
        if unit_price > econ.PRICE_FLOOR:
            inv += 1
    return float(revenue), int(inv)


@lru_cache(maxsize=65536)
def _temporal_paired_value_cached(item, schedule, initial_book,
                                  initial_stock, phase_drains):
    """Pure conserved-stock DP shared by ordinary/capital objective instances."""
    states = {(int(initial_book), int(initial_stock)): 0.0}
    for (_day, our_qty), drain in zip(schedule, phase_drains):
        next_states = {}
        for (raw_book, stock), prior_value in states.items():
            book = max(0, int(raw_book) - int(drain))
            for opponent_qty in range(int(stock) + 1):
                from whitebox.cashflow import _paired_sale_exact
                candidate_value = (
                    float(prior_value)
                    + _paired_sale_exact(
                        item, our_qty, book, opponent_qty,
                    )
                )
                _combined, after = _temporal_sale_result(
                    item, our_qty + opponent_qty, book,
                )
                state = (int(after), int(stock) - opponent_qty)
                if (state not in next_states
                        or candidate_value < next_states[state]):
                    next_states[state] = candidate_value
        states = next_states
    return float(min(states.values()) if states else float("-inf"))


def unit_value(snap, item):
    return sale_value(snap, item, 1)


def input_value(snap, item, qty=1):
    """Opportunity cost of consuming stock which could otherwise be sold."""
    return sale_value(snap, item, qty)


def planned_shed_stock(snap, plan=None):
    """Inputs available to a day route after certified input purchases.

    Unit actions precede this turn's market, so a worker may wait one turn at
    the shed before the purchase arrives; the cached day route can then execute
    it.  Counting only the pre-market snapshot incorrectly deletes most FEED
    work from the entire day. WHEAT is the survival commitment. The optional
    fertilizer target is set only by :func:`paid_fertilizer_target`;
    historical plans leave it at zero.
    """
    stock = dict(snap.shed)
    if plan is None:
        return stock
    have = int(stock.get("WHEAT", 0) or 0)
    target = max(have, int(getattr(plan, "wheat_needed", have) or have))
    carried_fn = getattr(snap, "carried", None)
    carried_stock = (carried_fn() if callable(carried_fn) else {
        item: sum(int(inv.get(item, 0) or 0)
                  for inv in getattr(snap, "inventories", ()))
        for item in econ.SELLABLE
    })
    fertilizer_have = int(stock.get("FERTILIZER", 0) or 0)
    carried = int(carried_stock.get("FERTILIZER", 0) or 0)
    fertilizer_target = max(
        0, int(getattr(plan, "fertilizer_target", 0) or 0),
    )
    if target <= have and fertilizer_target <= fertilizer_have + carried:
        return stock
    room = max(0, int(getattr(
        snap, "shed_room", econ.SHED_CAPACITY - sum(stock.values()),
    )))
    # The daily plan treats survival feed as a commitment. Cash may arrive from
    # an earlier sale in the same day, while the route remains cached; checking
    # only cash at the route-construction instant permanently deleted those
    # later-feasible FEED tasks. Market.feed_orders has first priority and is
    # the executor of this commitment. The economy MPC will eventually provide
    # the full intraday cash-flow certificate here.
    incoming = min(max(0, target - have), room, 20)
    if incoming:
        stock["WHEAT"] = have + incoming
        room -= incoming

    fertilizer_incoming = min(
        max(0, fertilizer_target - fertilizer_have - carried), room,
    )
    if fertilizer_incoming:
        stock["FERTILIZER"] = fertilizer_have + fertilizer_incoming
    return stock


def _animal_event_days(tile, kind, start_day, include_start=True):
    spec = econ.ANIMALS[kind]
    placed = _dated_field(tile, "placed_day", start_day)
    out = []
    first_refresh = start_day if include_start else start_day + 1
    # Refresh at the end of day d produces for next_day=d+1. Output from the
    # day-29 refresh cannot be acted on, so d=28 is the last useful refresh.
    for d in range(first_refresh, LAST_ACTION_DAY):
        next_day = d + 1
        age = next_day - placed - spec["first_yield_day"]
        if age >= 0 and age % spec["interval"] == 0:
            out.append(d)
    return out


def animal_retention_value(snap, tile, kind, after_today=True):
    """Conservative future stream net of the minimum survival feed bill."""
    events = _animal_event_days(tile, kind, snap.day,
                                include_start=not after_today)
    if not events:
        return 0.0
    product = econ.ANIMALS[kind]["product"]
    gross = sale_value(snap, product, len(events))
    last_day = events[-1]
    survival_days = max(0, last_day - snap.day)
    # Feeding every other day is the cheapest schedule that prevents escape.
    min_feed = int(math.ceil(survival_days / 2.0))
    feed_cost = input_value(snap, "WHEAT", min_feed)
    return max(0.0, gross - feed_cost)


def animal_task_value(snap, tile, ops):
    """Dollar value and survival flag for this tile's complete task bundle."""
    kind = tile.get("animal")
    if kind not in econ.ANIMALS:
        return 0.0, False
    spec = econ.ANIMALS[kind]
    product = spec["product"]
    names = {op[0] for op in ops if op}
    held = int(tile.get("yield_units", 0) or 0)
    value = sale_value(snap, product, held) if "HARVEST" in names else 0.0
    if "COLLECT_FERTILIZER" in names:
        value += unit_value(snap, "FERTILIZER")

    feed = "FEED" in names
    care = "CARE" in names
    urgent = feed and int(tile.get("consecutive_unfed", 0) or 0) >= 1
    if feed:
        value -= input_value(snap, "WHEAT", 1)
        events_today = _animal_event_days(tile, kind, snap.day, include_start=True)
        produces_tonight = bool(events_today and events_today[0] == snap.day)
        if produces_tonight:
            room = max(0, spec["max_held"] - (0 if "HARVEST" in names else held))
            pending = int(tile.get("pending_care_bonus", 0) or 0)
            value += sale_value(snap, product, min(room, 1 + pending))
        if urgent:
            value += animal_retention_value(snap, tile, kind, after_today=True)

    # CARE today adds exactly one pending bonus after tonight's production. It
    # has value only if FEED also succeeds and another useful event remains.
    if care and (feed or tile.get("fed_today")):
        future = _animal_event_days(tile, kind, snap.day, include_start=False)
        if future:
            value += unit_value(snap, product)
    return value, bool(urgent and value > 0)


def _crop_event_days(tile, crop, start_day):
    spec = econ.CROPS[crop]
    planted = _dated_field(tile, "planted_day", start_day)
    if not spec["ongoing"]:
        ready = planted + spec["first_yield_day"]
        return [ready - 1] if start_day <= ready - 1 < LAST_ACTION_DAY else []
    out = []
    for d in range(start_day, LAST_ACTION_DAY):
        next_day = d + 1
        age = next_day - planted - spec["first_yield_day"]
        if age < 0 or age % spec["interval"]:
            continue
        production_count = age // spec["interval"] + 1
        if production_count <= spec["max_yield"]:
            out.append(d)
    return out


def _exact_crop_event_days(tile, crop, start_day):
    """V189 event calendar where public day zero remains the integer zero."""
    spec = econ.CROPS[crop]
    raw = tile.get("planted_day", start_day)
    planted = int(start_day if raw is None else raw)
    if not spec["ongoing"]:
        ready = planted + spec["first_yield_day"]
        return [ready - 1] if start_day <= ready - 1 < LAST_ACTION_DAY else []
    out = []
    for day in range(int(start_day), LAST_ACTION_DAY):
        age = day + 1 - planted - int(spec["first_yield_day"])
        if age < 0 or age % int(spec["interval"]):
            continue
        if age // int(spec["interval"]) + 1 <= int(spec["max_yield"]):
            out.append(day)
    return out


def paid_fertilizer_target(snap, plan):
    """Return the finite robust-optimal fertilizer units for today's route.

    A candidate must be an observable, unfertilized ongoing crop that produces
    tonight. Every feasible tomato/strawberry count is valued at its worst
    exact simultaneous-sale margin. Existing input pays its foregone sale
    value; extra input pays the exact nonlinear post-buy quote. Survival feed,
    the plan cash floor and shed capacity remain hard constraints.
    """
    if plan is None or getattr(plan, "phase", None) == "endgame":
        return 0
    candidates = {"STRAWBERRY": [], "TOMATO": []}
    for tile in getattr(snap.me, "crops", {}).values():
        crop = tile.get("crop")
        if crop not in candidates or tile.get("watered_today"):
            continue
        if int(tile.get("fertilized_until_day", -1) or -1) >= int(snap.day):
            continue
        events = _exact_crop_event_days(tile, crop, int(snap.day))
        if not events or events[0] != int(snap.day):
            continue
        bonus = sum(1 for day in events if day <= int(snap.day) + 2)
        if bonus:
            candidates[crop].append(int(bonus))
    for crop in candidates:
        candidates[crop].sort(reverse=True)
    if not any(candidates.values()):
        return 0

    carried_fn = getattr(snap, "carried", None)
    carried_stock = (carried_fn() if callable(carried_fn) else {
        item: sum(int(inv.get(item, 0) or 0)
                  for inv in getattr(snap, "inventories", ()))
        for item in econ.SELLABLE
    })
    carried = int(carried_stock.get("FERTILIZER", 0) or 0)
    held = int(snap.shed.get("FERTILIZER", 0) or 0) + carried
    room = max(0, int(getattr(snap, "shed_room", 0) or 0))

    # Feed owns the first market slots and its protected service cash.
    wheat_have = int(snap.shed.get("WHEAT", 0) or 0)
    wheat_gap = min(
        max(0, int(getattr(plan, "wheat_needed", 0) or 0) - wheat_have),
        room, 20,
    )
    protected = max(
        0.0,
        float(getattr(plan, "cash_floor", 0.0) or 0.0),
        float(getattr(plan, "service_cash_floor", 0.0) or 0.0),
    )
    money = float(getattr(snap.me, "money", 0.0) or 0.0)
    wheat_book = int(
        snap.market_inv.get("WHEAT", econ.MARKET_I0) or econ.MARKET_I0
    )
    wheat_price = max(1, econ.price("WHEAT", wheat_book))
    wheat_qty = min(
        wheat_gap, int(max(0.0, money - protected) // wheat_price),
    )
    wheat_cost = econ.buy_cost("WHEAT", wheat_qty, wheat_book)
    cash = max(0.0, money - protected - float(wheat_cost))
    buy_room = max(0, room - wheat_qty)
    fertilizer_book = int(
        snap.market_inv.get("FERTILIZER", econ.MARKET_I0) or econ.MARKET_I0
    )

    prefix = {}
    for crop, units in candidates.items():
        totals = [0]
        for unit_count in units:
            totals.append(totals[-1] + unit_count)
        prefix[crop] = totals

    choices = []
    for strawberry_n in range(len(candidates["STRAWBERRY"]) + 1):
        for tomato_n in range(len(candidates["TOMATO"]) + 1):
            total = strawberry_n + tomato_n
            bought = max(0, total - held)
            if bought > buy_room:
                continue
            buy_cost = econ.buy_cost("FERTILIZER", bought, fertilizer_book)
            if float(buy_cost) > cash + 1e-9:
                continue
            bonus_value = (
                paired_phase_sale_value(
                    snap, "STRAWBERRY", prefix["STRAWBERRY"][strawberry_n],
                )
                + paired_phase_sale_value(
                    snap, "TOMATO", prefix["TOMATO"][tomato_n],
                )
            )
            held_used = min(total, held)
            opportunity = sale_value(snap, "FERTILIZER", held_used)
            net = float(bonus_value) - float(opportunity) - float(buy_cost)
            # Prefer lower bought/total quantity on exact value ties.
            choices.append((net, -bought, -total, total, bought))
    if not choices:
        return 0
    return int(max(choices)[3])


def crop_remaining_value(snap, tile):
    crop = tile.get("crop")
    if crop not in econ.CROPS:
        return 0.0
    spec = econ.CROPS[crop]
    events = _crop_event_days(tile, crop, snap.day)
    if spec["ongoing"]:
        units = len(events)
    else:
        units = max(0, spec["max_yield"] - int(tile.get("yield_units", 0) or 0)) if events else 0
    return sale_value(snap, crop, units)


def crop_task_value(snap, tile, ops):
    crop = tile.get("crop")
    if crop not in econ.CROPS:
        return 0.0, False
    names = {op[0] for op in ops if op}
    held = int(tile.get("yield_units", 0) or 0)
    value = sale_value(snap, crop, held) if "HARVEST" in names else 0.0
    urgent = ("WATER" in names
              and int(tile.get("consecutive_unwatered", 0) or 0) >= 1)
    if urgent:
        value += crop_remaining_value(snap, tile)

    events = _crop_event_days(tile, crop, snap.day)
    produces_tonight = bool(events and events[0] == snap.day)
    if "WATER" in names and produces_tonight and econ.CROPS[crop]["ongoing"]:
        value += unit_value(snap, crop)
    if "FERTILIZE" in names:
        bonus_events = sum(1 for d in events if d <= snap.day + 2)
        value += sale_value(snap, crop, bonus_events)
        value -= input_value(snap, "FERTILIZER", 1)
    return value, bool(urgent and value > 0)


def plant_value(snap, crop):
    units = plant_output_units(snap, crop)
    return sale_value(snap, crop, units)


def plant_output_units(snap, crop):
    """Rule-derived terminal units from one newly planted crop tile."""
    if crop not in econ.CROPS:
        return 0
    spec = econ.CROPS[crop]
    first_ready = snap.day + spec["first_yield_day"]
    if first_ready > LAST_ACTION_DAY:
        return 0
    if spec["ongoing"]:
        units = 1 + max(0, (LAST_ACTION_DAY - first_ready) // spec["interval"])
        units = min(units, spec["max_yield"])
    else:
        units = spec["max_yield"]
    return int(units)


def paid_turnover_output_units(snap, crop):
    """Unfertilized units available at a turnover crop's first legal harvest.

    ``plant_output_units`` is a terminal upper for a fully serviced crop.  A
    paid weed option does not own those future route turns.  For one-shot
    crops the engine starts with one unit and WATER on the first harvest day
    adds one unit when that day is inside the public yield window.  Ongoing
    crops produce one unit at their first refresh.  Crediting anything beyond
    this earliest endpoint would be free future labour.
    """
    if crop not in econ.CROPS:
        return 0
    spec = econ.CROPS[crop]
    first_ready = int(snap.day) + int(spec["first_yield_day"])
    if first_ready > LAST_ACTION_DAY:
        return 0
    if spec["ongoing"]:
        return 1
    window_start = (int(spec["max_yield_day"]) + 1) // 2
    bonus = int(window_start <= int(spec["first_yield_day"])
                <= int(spec["max_yield_day"]))
    return min(int(spec["max_yield"]), 1 + bonus)


def animal_placement_value(snap, kind):
    if kind not in econ.ANIMALS:
        return 0.0
    fake = {"animal": kind, "placed_day": snap.day}
    return animal_retention_value(snap, fake, kind, after_today=False)


def animal_placement_units(snap, kind):
    """Base product units used by ``animal_placement_value`` for one animal."""
    if kind not in econ.ANIMALS:
        return 0
    fake = {"animal": kind, "placed_day": snap.day}
    return len(_animal_event_days(fake, kind, snap.day, include_start=True))


def animal_full_service_value(snap, kind):
    """Future product stream when FEED+CARE is funded through last output.

    The engine produces one base unit at every event whether fed or not. CARE
    adds one pending unit, but only a fed future event can cash it; the first
    event therefore has no bonus and every later event has one. This is the
    appropriate capital-column value because the same master is also buying
    the labour and feed needed to service the asset. Fertilizer is deliberately
    excluded: it is a shared, crashable by-product, so ignoring it is a robust
    lower bound rather than counting one full-price unit per animal-day.
    """
    if kind not in econ.ANIMALS:
        return 0.0
    product_units, feed_days = animal_full_service_units(snap, kind)
    if product_units <= 0:
        return 0.0
    product = econ.ANIMALS[kind]["product"]
    gross = sale_value(snap, product, product_units)
    return max(0.0, gross - input_value(snap, "WHEAT", feed_days))


def animal_full_service_units(snap, kind):
    """``(product units, feed days)`` for one newly placed serviced animal."""
    if kind not in econ.ANIMALS:
        return 0, 0
    fake = {"animal": kind, "placed_day": snap.day}
    events = _animal_event_days(fake, kind, snap.day, include_start=True)
    if not events:
        return 0, 0
    return (len(events) + max(0, len(events) - 1),
            max(0, events[-1] - snap.day + 1))


def task_sale_outputs(snap, task):
    """Rule-derived sale quantities credited inside one ordinary task value.

    This is a decomposition of the positive sale terms already present in
    ``animal_task_value``, ``crop_task_value``, ``plant_value`` and
    ``animal_placement_value``.  Feed/fertilizer opportunity costs and the
    per-animal ``max(0, gross-feed)`` option floor remain in the residual when
    the terms are repriced.  BUILD/CLEAR tasks intentionally return no output:
    their eventual product identity is not encoded in the task column, so
    assigning one here would be a guess rather than an equation.
    """
    outputs = Counter()
    kind = getattr(task, "kind", None)
    names = {op[0] for op in (getattr(task, "ops", ()) or ()) if op}
    x, y = tuple(task.pos)
    tile = snap.me.tiles[y][x]

    if kind == "ANIMAL_SERVICE" and isinstance(tile, dict):
        animal = tile.get("animal")
        if animal not in econ.ANIMALS:
            return outputs
        spec = econ.ANIMALS[animal]
        product = spec["product"]
        held = int(tile.get("yield_units", 0) or 0)
        if "HARVEST" in names:
            outputs[product] += held
        if "COLLECT_FERTILIZER" in names:
            outputs["FERTILIZER"] += 1
        if "FEED" in names:
            events = _animal_event_days(
                tile, animal, snap.day, include_start=True,
            )
            if events and events[0] == snap.day:
                room = max(0, spec["max_held"]
                           - (0 if "HARVEST" in names else held))
                pending = int(tile.get("pending_care_bonus", 0) or 0)
                outputs[product] += min(room, 1 + pending)
            if int(tile.get("consecutive_unfed", 0) or 0) >= 1:
                outputs[product] += len(_animal_event_days(
                    tile, animal, snap.day, include_start=False,
                ))
        if ("CARE" in names
                and ("FEED" in names or tile.get("fed_today"))
                and _animal_event_days(
                    tile, animal, snap.day, include_start=False,
                )):
            outputs[product] += 1
        return outputs

    if kind == "CROP_SERVICE" and isinstance(tile, dict):
        crop = tile.get("crop")
        if crop not in econ.CROPS:
            return outputs
        held = int(tile.get("yield_units", 0) or 0)
        if "HARVEST" in names:
            outputs[crop] += held
        events = _crop_event_days(tile, crop, snap.day)
        urgent = ("WATER" in names
                  and int(tile.get("consecutive_unwatered", 0) or 0) >= 1)
        if urgent:
            if econ.CROPS[crop]["ongoing"]:
                outputs[crop] += len(events)
            elif events:
                outputs[crop] += max(0, econ.CROPS[crop]["max_yield"] - held)
        if ("WATER" in names and events and events[0] == snap.day
                and econ.CROPS[crop]["ongoing"]):
            outputs[crop] += 1
        if "FERTILIZE" in names:
            outputs[crop] += sum(1 for day in events if day <= snap.day + 2)
        return outputs

    if kind == "PLANT_CROP":
        crop = next((op[1] for op in task.ops
                     if op and op[0] == "PLANT" and len(op) > 1), None)
        if crop in econ.CROPS:
            outputs[crop] += plant_output_units(snap, crop)
        return outputs

    if kind == "PLACE_ANIMAL":
        animal = next((op[1] for op in task.ops
                       if op and op[0] == "PLACE" and len(op) > 1), None)
        if animal in econ.ANIMALS:
            outputs[econ.ANIMALS[animal]["product"]] += animal_placement_units(
                snap, animal,
            )
        return outputs

    if kind == "CAPITAL_CROP":
        crop = next((op[1] for op in task.ops
                     if op and op[0] == "PLANT" and len(op) > 1), None)
        if crop in econ.CROPS:
            outputs[crop] += plant_output_units(snap, crop)
        return outputs

    if kind == "CAPITAL_ANIMAL":
        animal = next((op[1] for op in task.ops
                       if op and op[0] == "PLACE" and len(op) > 1), None)
        if animal in econ.ANIMALS:
            outputs[econ.ANIMALS[animal]["product"]] += animal_placement_units(
                snap, animal,
            )
    return outputs


def task_sale_schedule(snap, task):
    """Rule-derived ``(item, availability_day) -> units`` for one task.

    This is the dated form of :func:`task_sale_outputs`. ``day`` is when an
    output is first public-physically available after the corresponding engine
    refresh; already-held harvests and collected fertilizer use the current
    day. The routine changes no quantity or non-sale term.
    """
    schedule = Counter()
    kind = getattr(task, "kind", None)
    names = {op[0] for op in (getattr(task, "ops", ()) or ()) if op}
    x, y = tuple(task.pos)
    tile = snap.me.tiles[y][x]

    def add(item, day, qty=1):
        qty = max(0, int(qty))
        if item in econ.SELLABLE and qty:
            schedule[(item, max(int(snap.day), int(day)))] += qty

    if kind == "ANIMAL_SERVICE" and isinstance(tile, dict):
        animal = tile.get("animal")
        spec = econ.ANIMALS.get(animal)
        if spec is None:
            return schedule
        product = spec["product"]
        held = int(tile.get("yield_units", 0) or 0)
        if "HARVEST" in names:
            add(product, snap.day, held)
        if "COLLECT_FERTILIZER" in names:
            add("FERTILIZER", snap.day)
        if "FEED" in names:
            events = _animal_event_days(
                tile, animal, snap.day, include_start=True,
            )
            if events and events[0] == snap.day:
                room = max(0, spec["max_held"]
                           - (0 if "HARVEST" in names else held))
                pending = int(tile.get("pending_care_bonus", 0) or 0)
                add(product, events[0] + 1, min(room, 1 + pending))
            if int(tile.get("consecutive_unfed", 0) or 0) >= 1:
                for refresh in _animal_event_days(
                        tile, animal, snap.day, include_start=False):
                    add(product, refresh + 1)
        if ("CARE" in names
                and ("FEED" in names or tile.get("fed_today"))):
            future = _animal_event_days(
                tile, animal, snap.day, include_start=False,
            )
            if future:
                add(product, future[0] + 1)
        return schedule

    if kind == "CROP_SERVICE" and isinstance(tile, dict):
        crop = tile.get("crop")
        if crop not in econ.CROPS:
            return schedule
        held = int(tile.get("yield_units", 0) or 0)
        if "HARVEST" in names:
            add(crop, snap.day, held)
        events = _crop_event_days(tile, crop, snap.day)
        urgent = ("WATER" in names
                  and int(tile.get("consecutive_unwatered", 0) or 0) >= 1)
        if urgent:
            if econ.CROPS[crop]["ongoing"]:
                for refresh in events:
                    add(crop, refresh + 1)
            elif events:
                add(crop, events[0] + 1,
                    max(0, econ.CROPS[crop]["max_yield"] - held))
        if ("WATER" in names and events and events[0] == snap.day
                and econ.CROPS[crop]["ongoing"]):
            add(crop, events[0] + 1)
        if "FERTILIZE" in names:
            for refresh in events:
                if refresh <= snap.day + 2:
                    add(crop, refresh + 1)
        return schedule

    if kind in ("PLANT_CROP", "CAPITAL_CROP"):
        crop = next((op[1] for op in task.ops
                     if op and op[0] == "PLANT" and len(op) > 1), None)
        if crop not in econ.CROPS:
            return schedule
        fake = {"crop": crop, "planted_day": snap.day, "yield_units": 0}
        events = _crop_event_days(fake, crop, snap.day)
        if econ.CROPS[crop]["ongoing"]:
            for refresh in events:
                add(crop, refresh + 1)
        elif events:
            add(crop, events[0] + 1, econ.CROPS[crop]["max_yield"])
        return schedule

    if kind in ("PLACE_ANIMAL", "CAPITAL_ANIMAL"):
        animal = next((op[1] for op in task.ops
                       if op and op[0] == "PLACE" and len(op) > 1), None)
        spec = econ.ANIMALS.get(animal)
        if spec is None:
            return schedule
        fake = {"animal": animal, "placed_day": snap.day}
        for refresh in _animal_event_days(
                fake, animal, snap.day, include_start=True):
            add(spec["product"], refresh + 1)
    return schedule


class TaskBundleObjective:
    """Exact nonlinear value oracle for a selected set of route tasks.

    Each task is decomposed into a rule-derived sale quantity and a residual
    containing its input opportunity costs, capital cost and option-floor
    terms. ``add_gain`` is the exact grouped-value change when the route master
    adds that task. The oracle is state-local and has no fitted parameter.
    """

    def __init__(self, snap, tasks, paired_phase=False):
        self.snap = snap
        self.paired_phase = bool(paired_phase)
        self.terms = {}
        self._revenue = {}
        for task in tasks:
            outputs = Counter({
                item: int(qty)
                for item, qty in task_sale_outputs(snap, task).items()
                if item in econ.SELLABLE and int(qty) > 0
            })
            # Task construction uses the historical own-revenue lower book.
            # Remove that exact output term before substituting a different
            # selected-bundle market objective. This preserves every non-sale
            # input, survival, option-floor and capital residual unchanged.
            residual = float(task.value) - sum(
                sale_value(snap, item, qty)
                for item, qty in outputs.items()
            )
            self.terms[id(task)] = (outputs, residual)

    def revenue(self, item, qty):
        key = (item, max(0, int(qty)))
        if key not in self._revenue:
            valuation = (paired_phase_sale_value
                         if self.paired_phase else sale_value)
            self._revenue[key] = valuation(self.snap, key[0], key[1])
        return self._revenue[key]

    def outputs(self, task):
        return self.terms.get(id(task), (Counter(), float(task.value)))[0]

    def residual(self, task):
        return self.terms.get(id(task), (Counter(), float(task.value)))[1]

    def counts(self, selected=()):
        out = Counter()
        for task in selected:
            out.update(self.outputs(task))
        return out

    def update_counts(self, counts, task, sign=1):
        for item, qty in self.outputs(task).items():
            counts[item] += int(sign) * int(qty)
            if counts[item] <= 0:
                counts.pop(item, None)

    def signature(self, task, counts):
        return tuple((item, int(counts.get(item, 0)))
                     for item in sorted(self.outputs(task)))

    def add_gain(self, task, counts):
        gain = self.residual(task)
        for item, qty in self.outputs(task).items():
            before = int(counts.get(item, 0))
            gain += self.revenue(item, before + qty) - self.revenue(item, before)
        return gain

    def swap_gain(self, incoming, outgoing, counts):
        gain = self.residual(incoming) - self.residual(outgoing)
        affected = set(self.outputs(incoming)) | set(self.outputs(outgoing))
        for item in affected:
            before = int(counts.get(item, 0))
            after = (before - int(self.outputs(outgoing).get(item, 0))
                     + int(self.outputs(incoming).get(item, 0)))
            gain += self.revenue(item, after) - self.revenue(item, before)
        return gain

    def score(self, selected):
        selected = list(selected)
        counts = self.counts(selected)
        return (sum(self.residual(task) for task in selected)
                + sum(self.revenue(item, qty)
                      for item, qty in counts.items()))


class TemporalPairedTaskBundleObjective:
    """Selected-output value over dated phases and one persistent public book.

    Output quantities and dates come from :func:`task_sale_schedule`. At every
    selected sale day, an adversary may sell any amount of one conserved stock
    already standing as public yield on the opponent farm. Unsold stock carries
    to later phases and never exceeds the engine's shed capacity. Each phase
    uses the engine's exact per-unit lockstep margin and enumerates the feasible
    opponent quantity; guaranteed town drain is applied between phases. This is
    a current-observation uncertainty set, not an opponent policy, service
    assumption or future-capital prediction.
    """

    def __init__(self, snap, tasks):
        from whitebox import cashflow as _cashflow
        self.snap = snap
        self.terms = {}
        self._value_cache = {}
        # Only units already standing on the public opponent farm enter this
        # uncertainty set. Future service/output is not guaranteed and adding
        # its full-service upper was both a different hypothesis and needless
        # state growth. Every currently visible unit may be sold at any one of
        # our dated phases or retained; the same unit is never reused.
        self.initial_opponent = {
            item: _visible_opp_units(snap, item) for item in econ.SELLABLE
        }
        self.drain = _cashflow._guaranteed_town_drain_by_day(snap)
        for task in tasks:
            totals = Counter({
                item: int(qty) for item, qty in task_sale_outputs(
                    snap, task,
                ).items() if item in econ.SELLABLE and int(qty) > 0
            })
            schedule = Counter({
                (item, int(day)): int(qty)
                for (item, day), qty in task_sale_schedule(snap, task).items()
                if item in econ.SELLABLE and int(qty) > 0
            })
            dated_totals = Counter()
            for (item, _day), qty in schedule.items():
                dated_totals[item] += qty
            if dated_totals != totals:
                raise ValueError("dated task output does not conserve quantity")
            residual = float(task.value) - sum(
                sale_value(snap, item, qty) for item, qty in totals.items()
            )
            self.terms[id(task)] = (schedule, residual,
                                    frozenset(totals))

    def schedule(self, task):
        return self.terms.get(id(task), (Counter(), 0.0, frozenset()))[0]

    def residual(self, task):
        return self.terms.get(
            id(task), (Counter(), float(task.value), frozenset()),
        )[1]

    def items(self, task):
        return self.terms.get(id(task), (None, None, frozenset()))[2]

    def counts(self, selected=()):
        out = Counter()
        for task in selected:
            out.update(self.schedule(task))
        return out

    def update_counts(self, counts, task, sign=1):
        for key, qty in self.schedule(task).items():
            counts[key] += int(sign) * int(qty)
            if counts[key] <= 0:
                counts.pop(key, None)

    def _item_schedule(self, counts, item):
        return tuple(sorted(
            (int(day), int(qty))
            for (scheduled_item, day), qty in counts.items()
            if scheduled_item == item and int(qty) > 0
        ))

    def signature(self, task, counts):
        return tuple((item, self._item_schedule(counts, item))
                     for item in sorted(self.items(task)))

    def _item_value(self, item, schedule):
        key = (item, tuple(schedule))
        if key in self._value_cache:
            return self._value_cache[key]
        if not schedule:
            return 0.0
        prior_day = int(self.snap.day)
        phase_drains = []
        for day, our_qty in schedule:
            phase_drains.append(sum(
                int(self.drain.get(d, {}).get(item, 0) or 0)
                for d in range(prior_day + 1, int(day) + 1)
            ))
            prior_day = int(day)
        value = _temporal_paired_value_cached(
            item, tuple(schedule),
            int(self.snap.market_inv.get(item, econ.MARKET_I0)
                or econ.MARKET_I0),
            min(econ.SHED_CAPACITY,
                int(self.initial_opponent.get(item, 0) or 0)),
            tuple(phase_drains),
        )
        self._value_cache[key] = float(value)
        return float(value)

    def _affected_value(self, counts, items):
        return sum(self._item_value(item, self._item_schedule(counts, item))
                   for item in items)

    def add_gain(self, task, counts):
        items = self.items(task)
        before = self._affected_value(counts, items)
        trial = Counter(counts)
        self.update_counts(trial, task)
        return self.residual(task) + self._affected_value(trial, items) - before

    def swap_gain(self, incoming, outgoing, counts):
        items = self.items(incoming) | self.items(outgoing)
        before = self._affected_value(counts, items)
        trial = Counter(counts)
        self.update_counts(trial, outgoing, -1)
        self.update_counts(trial, incoming, 1)
        return (self.residual(incoming) - self.residual(outgoing)
                + self._affected_value(trial, items) - before)

    def score(self, selected):
        selected = list(selected)
        counts = self.counts(selected)
        items = {item for item, _day in counts}
        return (sum(self.residual(task) for task in selected)
                + self._affected_value(counts, items))


def reprice_task_sale_bundles(snap, tasks):
    """Clear all ordinary selected-proposal output once per product.

    Let task ``i`` contain rule-derived output ``q[i,p]`` and original value
    ``v[i]``.  Freeze its non-sale/floor residual as

      ``b[i] = v[i] - sum_p sale_value(q[i,p])``.

    For proposal quantity ``Q[p] = sum_i q[i,p]``, replace standalone revenue
    by the exact nonlinear bundle revenue and share it per physical unit:

      ``v_bundle[i] = b[i] + sum_p q[i,p]/Q[p] * sale_value(Q[p])``.

    The market curve has non-increasing marginal revenue, so using the full
    proposal's average for any routed subset is conservative.  Input
    opportunity costs are deliberately left standalone in ``b``; aggregating
    them would lower their average and could overstate a small subset.
    """
    tasks = list(tasks)
    terms = {}
    totals = Counter()
    for task in tasks:
        outputs = task_sale_outputs(snap, task)
        outputs = Counter({item: int(qty) for item, qty in outputs.items()
                           if item in econ.SELLABLE and int(qty) > 0})
        if not outputs:
            continue
        residual = float(task.value) - sum(
            sale_value(snap, item, qty) for item, qty in outputs.items()
        )
        terms[id(task)] = (outputs, residual)
        totals.update(outputs)
    bundle_revenue = {
        item: sale_value(snap, item, qty) for item, qty in totals.items()
    }
    for task in tasks:
        term = terms.get(id(task))
        if term is None:
            continue
        outputs, residual = term
        task.value = residual + sum(
            bundle_revenue[item] * qty / float(totals[item])
            for item, qty in outputs.items()
        )
    return tasks


def weed_value(snap, plan):
    candidates = [plant_value(snap, crop) for crop, n in snap.seeds.items()
                  if int(n or 0) > 0 and crop in econ.CROPS]
    return max(candidates) if candidates else 0.0


def paid_weed_reinvestment_choice(snap, plan, max_tiles):
    """Best homogeneous weed-clear exercise arm and its crop identity.

    DIG exposes an empty tile before the current market phase.  The capital
    master can therefore buy seed against that projected state, but the old
    task layer assigned DIG zero whenever no seed was already owned.  That is
    a circular action-set deletion: no DIG means no empty tile, and no empty
    tile means no seed purchase.

    For each public crop and each feasible quantity, this routine values the
    exact terminal output bundle on the visible shared book and subtracts the
    real seed bill not already sunk in inventory.  Current cash must cover the
    purchase after the plan's named standing-service reserve.  The best
    positive arm yields one equal value column per cleared tile; route capacity
    then selects an executable subset, and the projected capital master still
    has to certify the actual purchase.  No crop target, date schedule, replay
    statistic or learned coefficient enters the option.
    """
    limit = max(0, int(max_tiles))
    if limit <= 0:
        return None, ()
    # A small crop action can change the next replan's land/herd branch even
    # when its own route uses only spare turns.  Until those durable action
    # sets are closed, their counterfactual displacement is not certified.
    # This gate is derived only from public ownership and engine deadlines.
    if (econ.can_buy_land(len(snap.me.unlocked))
            or int(snap.step) <= max(int(deadline)
                                     for deadline in econ.ANIMAL_DEADLINE.values())):
        return None, ()
    reserve = max(0.0, float(getattr(
        plan, "service_cash_floor", getattr(plan, "cash_floor", 0.0),
    ) or 0.0))
    spendable = max(0.0, float(snap.me.money) - reserve)
    eligible = [
        crop for crop in sorted(econ.CROPS)
        if int(snap.step) <= int(econ.SEED_DEADLINE[crop])
        # Open only the final realizable first-yield cohort.  An earlier
        # turnover changes several later daily route problems; without a
        # retained multi-day route that displacement is not certified.
        and int(snap.day) + int(econ.CROPS[crop]["first_yield_day"])
        == LAST_ACTION_DAY
        and paid_turnover_output_units(snap, crop) > 0
    ]
    if not eligible:
        return None, ()
    # Until a future daily route is retained, minimize the number of exposed
    # WATER days.  This is a public-rule minimization, not a crop-name or date
    # target; longer-lived crops are absent rather than receiving free service.
    shortest_service = min(
        int(econ.CROPS[crop]["first_yield_day"]) for crop in eligible
    )
    best = None
    for crop in eligible:
        if int(econ.CROPS[crop]["first_yield_day"]) != shortest_service:
            continue
        units = paid_turnover_output_units(snap, crop)
        if units <= 0:
            continue
        owned = max(0, int(snap.seeds.get(crop, 0) or 0))
        seed_cost = float(econ.CROPS[crop]["seed"])
        cap = min(limit, owned + int(spendable // seed_cost))
        for quantity in range(1, cap + 1):
            bought = max(0, quantity - owned)
            cost = float(bought) * seed_cost
            if cost > spendable + 1e-9:
                continue
            total = (sale_value(snap, crop, quantity * units) - cost)
            if total <= 1e-9:
                continue
            key = (float(total), -float(cost), -quantity, crop)
            if best is None or key > best[0]:
                best = (key, quantity, float(total))
    if best is None:
        return None, ()
    key, quantity, total = best
    crop = str(key[-1])
    return crop, tuple(
        float(total) / float(quantity) for _ in range(quantity)
    )


def paid_weed_reinvestment_frontier(snap, plan, max_tiles):
    """Per-tile values for the best paid weed-turnover arm.

    The compatibility wrapper keeps the original public return type.  The task
    planner uses :func:`paid_weed_reinvestment_choice` as well, because a route
    that budgets DIG+PLANT+WATER must retain the crop identity whose seed bill
    was subtracted from the value.
    """
    _crop, values = paid_weed_reinvestment_choice(
        snap, plan, max_tiles,
    )
    return values
