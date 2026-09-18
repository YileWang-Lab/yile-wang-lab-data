"""Bounded multi-day cash/labour/shed certificate for new capital.

This is an incremental certificate, re-solved from the current observation.
It keeps the strategy's baseline cash reserve untouched and proves that the
newly proposed assets can fund their own exact seed/animal/land bill, daily
full-service feed, deterministic Fibonacci crew bill, shed occupancy and sale
orders through the remaining actionable days.

Future sale uncertainty uses one named conservative book: all rule-derived
remaining output on both currently visible farms is reserved ahead of the new
portfolio, and town drain is ignored.  No hidden future purchase or policy is
predicted.  This is not yet the simultaneous opponent interval solver; it is a
transparent nominal lower book for inventing a route-trimmable proposal.
"""
import copy
from collections import Counter, defaultdict
from functools import lru_cache

from whitebox import econ, paths, value as objective


LAST_DAY = 29
# Every future worker is hired at hour 0 and begins at hour 1.  Reserving the
# last action for one aggregate DROP leaves 22 turns for independent round trips.
ROUTE_TURNS = econ.TURNS_PER_DAY - 2
# A shared route includes its DROP explicitly.  A hand hired by the hour-0
# market phase first acts at hour 1, hence the complete closed route has 23
# engine actions.  Using this budget for every segment does not borrow the
# incumbent farmer's extra hour-0 action.
SHARED_ROUTE_TURNS = econ.TURNS_PER_DAY - 1


class Certificate:
    __slots__ = ("feasible", "reason", "counts", "land_cost",
                 "upfront_spend", "cash_path", "final_cash",
                 "minimum_cash", "cash_by_day",
                 "workers_by_day", "feed_by_day", "outputs_by_day",
                 "routes_by_day", "hire_phases_by_day",
                 "positions_by_item", "paired_value", "evaluations",
                 "exchange_evaluations", "operating_cost",
                 "operating_cost_by_day", "selected_reinvestment",
                 "selected_worst_response", "selected_own_cost",
                 "selected_full_endpoint", "selected_reinvestment_order",
                 "selected_reinvestment_positions_by_item",
                 "selected_execution_routes_by_day",
                 "selected_execution_hire_phases_by_day")

    def __init__(self, counts, land_cost=0.0):
        self.feasible = True
        self.reason = "ok"
        self.counts = dict(counts)
        self.land_cost = float(land_cost)
        self.upfront_spend = 0.0
        self.cash_path = []
        self.final_cash = 0.0
        self.minimum_cash = float("inf")
        self.cash_by_day = {}
        self.workers_by_day = {}
        self.feed_by_day = {}
        self.outputs_by_day = {}
        self.routes_by_day = {}
        self.hire_phases_by_day = {}
        self.positions_by_item = {}
        self.paired_value = 0.0
        self.evaluations = 0
        self.exchange_evaluations = 0
        self.operating_cost = 0.0
        self.operating_cost_by_day = {}
        self.selected_reinvestment = ""
        self.selected_worst_response = ""
        self.selected_own_cost = 0.0
        self.selected_full_endpoint = False
        # A continuation value is an admissible policy action only when its
        # physical witness survives the value calculation.  These public audit
        # fields bind the selected future purchase, placement, routes and hire
        # phases to the certificate; empty values mean no future action was
        # selected.  Historical callers ignore them and keep identical policy
        # behaviour.
        self.selected_reinvestment_order = ()
        self.selected_reinvestment_positions_by_item = {}
        self.selected_execution_routes_by_day = {}
        self.selected_execution_hire_phases_by_day = {}

    def reject(self, reason, cash=0.0):
        self.feasible = False
        self.reason = reason
        self.final_cash = float(cash)
        self.minimum_cash = min(self.minimum_cash, float(cash))
        return self


def _sell_outputs(book, outputs):
    """Sell each day's same-item output once at the exact marginal curve."""
    after = dict(book)
    revenue = 0.0
    for item in sorted(outputs):
        qty = max(0, int(outputs[item]))
        inv = int(after.get(item, econ.MARKET_I0) or econ.MARKET_I0)
        revenue += econ.sell_revenue(item, qty, inv)
        for _ in range(qty):
            price = econ.price(item, inv)
            if price > econ.PRICE_FLOOR:
                inv += 1
        after[item] = inv
    return float(revenue), after


@lru_cache(maxsize=16384)
def _sale_result(item, qty, inventory):
    """Exact marginal sale and closing inventory, memoized by public state."""
    inv = int(inventory)
    revenue = 0.0
    for _ in range(max(0, int(qty))):
        price = econ.price(item, inv)
        revenue += price
        if price > econ.PRICE_FLOOR:
            inv += 1
    return float(revenue), inv


@lru_cache(maxsize=4096)
def _cached_buy_cost(item, qty, inventory):
    """Exact engine marginal buy curve, memoized for certificate trials."""
    return float(econ.buy_cost(item, int(qty), int(inventory)))


def _sell_outputs_cached(book, outputs):
    """Shared-certificate equivalent of `_sell_outputs` with exact memoization."""
    after = dict(book)
    revenue = 0.0
    for item in sorted(outputs):
        qty = max(0, int(outputs[item]))
        inv = int(after.get(item, econ.MARKET_I0) or econ.MARKET_I0)
        gained, inv = _sale_result(item, qty, inv)
        revenue += gained
        after[item] = inv
    return float(revenue), after


def _remaining_visible_units(snap, farm, include_fertilizer=False):
    """Rule upper bound on remaining output of currently standing assets.

    Fertilizer is optional so historical variants remain byte-for-byte
    behavior compatible.  When enabled, it counts a currently collectable
    unit plus one nightly refresh through the last actionable day for every
    visible animal.  That is the public full-service upper, not a fitted yield.
    """
    out = Counter()
    for tile in getattr(farm, "crops", {}).values():
        crop = tile.get("crop")
        if crop not in econ.CROPS:
            continue
        held = max(0, int(tile.get("yield_units", 0) or 0))
        events = objective._crop_event_days(tile, crop, snap.day)
        if econ.CROPS[crop]["ongoing"]:
            units = held + len(events)
        else:
            units = (max(held, int(econ.CROPS[crop]["max_yield"]))
                     if events else held)
        out[crop] += units
    for tile in getattr(farm, "animals", {}).values():
        kind = tile.get("animal")
        spec = econ.ANIMALS.get(kind)
        if spec is None:
            continue
        held = max(0, int(tile.get("yield_units", 0) or 0))
        events = objective._animal_event_days(
            tile, kind, snap.day, include_start=True,
        )
        # Full service is the maximum public standing stream: one base unit at
        # every event and one banked CARE bonus after the first event.
        out[spec["product"]] += held + len(events) + max(0, len(events) - 1)
        if include_fertilizer:
            out["FERTILIZER"] += int(bool(
                tile.get("fertilizer_available", False)
            ))
            out["FERTILIZER"] += max(0, LAST_DAY - int(snap.day))
    return out


def _visible_output_schedule(snap, farm, include_fertilizer=False):
    """Daily upper schedule from public standing assets under full service."""
    out = defaultdict(Counter)
    first_day = min(LAST_DAY, int(snap.day) + 1)
    for tile in getattr(farm, "crops", {}).values():
        crop = tile.get("crop")
        if crop not in econ.CROPS:
            continue
        held = max(0, int(tile.get("yield_units", 0) or 0))
        if held:
            out[first_day][crop] += held
        events = objective._crop_event_days(tile, crop, snap.day)
        if econ.CROPS[crop]["ongoing"]:
            for refresh in events:
                out[refresh + 1][crop] += 1
        elif events:
            remaining = max(0, int(econ.CROPS[crop]["max_yield"]) - held)
            out[events[0] + 1][crop] += remaining

    for tile in getattr(farm, "animals", {}).values():
        kind = tile.get("animal")
        spec = econ.ANIMALS.get(kind)
        if spec is None:
            continue
        product = spec["product"]
        held = max(0, int(tile.get("yield_units", 0) or 0))
        if held:
            out[first_day][product] += held
        events = objective._animal_event_days(
            tile, kind, snap.day, include_start=True,
        )
        for rank, refresh in enumerate(events):
            out[refresh + 1][product] += 1 if rank == 0 else 2
        if include_fertilizer:
            if tile.get("fertilizer_available", False):
                out[first_day]["FERTILIZER"] += 1
            # End-of-day refresh on day d is collectable on day d+1.  The
            # refresh after day 29 is outside the actionable horizon.
            for output_day in range(int(snap.day) + 1, LAST_DAY + 1):
                out[output_day]["FERTILIZER"] += 1
    return out


def _own_reserved_book(snap, include_fertilizer=False):
    """Current public book after all visible own standing output sells first."""
    book = {item: int(snap.market_inv.get(item, econ.MARKET_I0)
                      or econ.MARKET_I0)
            for item in econ.SELLABLE}
    for item, qty in _remaining_visible_units(
            snap, snap.me, include_fertilizer=include_fertilizer).items():
        book[item] += max(0, int(qty))
    return book


def _guaranteed_town_drain_by_day(snap):
    """Analytic lower town drain between consecutive modelled sale days."""
    from whitebox import market_model
    out = {}
    prior = int(snap.step)
    for day in range(int(snap.day) + 1, LAST_DAY + 1):
        sale_step = min(718, max(prior, day * econ.TURNS_PER_DAY))
        out[day] = {
            item: market_model.town_take_bounds(
                snap, item, start_step=prior, end_step=sale_step,
            )[0]
            for item in econ.SELLABLE
        }
        prior = sale_step
    return out


@lru_cache(maxsize=32768)
def _paired_sale_value(item, qty, inventory, opponent_upper):
    """Worst exact same-slot margin over a public opponent quantity interval.

    The engine clears matching market-order slots one unit at a time.  Both
    players receive the price quoted from the same pre-commit inventory in a
    joint round, so neither whole batch is first.  Every integer quantity in
    the public feasible interval is enumerated; no opponent distribution or
    seat-order average enters this lower value.
    """
    qty = max(0, int(qty))
    inventory = max(0, int(inventory))
    upper = max(0, int(opponent_upper))
    if qty <= 0:
        return 0.0
    worst = None
    for opp_qty in range(upper + 1):
        paired = _paired_sale_exact(item, qty, inventory, opp_qty)
        worst = paired if worst is None else min(worst, paired)
    return float(worst or 0.0)


@lru_cache(maxsize=65536)
def _lockstep_sale_result(item, qty, opponent_qty, inventory):
    """Exact engine result when both sides SELL in the same order slot.

    Each joint unit is quoted before either commit mutates the market.  Once
    one order is exhausted, the other side's tail follows the ordinary
    marginal curve.  The result is ``(our_revenue, opponent_revenue, book)``.
    """
    qty = max(0, int(qty))
    inventory = max(0, int(inventory))
    opponent_qty = max(0, int(opponent_qty))
    joint = min(qty, opponent_qty)
    own_revenue = 0.0
    opponent_revenue = 0.0
    book = inventory
    for _ in range(joint):
        quoted = econ.price(item, book)
        own_revenue += quoted
        opponent_revenue += quoted
        if quoted > econ.PRICE_FLOOR:
            book += 2
    own_tail, book = _sale_result(item, qty - joint, book)
    opponent_tail, book = _sale_result(
        item, opponent_qty - joint, book,
    )
    return (float(own_revenue + own_tail),
            float(opponent_revenue + opponent_tail), int(book))


@lru_cache(maxsize=65536)
def _paired_sale_exact(item, qty, inventory, opponent_qty):
    """Exact same-slot zero-sum margin increment for one opponent sale.

    The counterfactual is the opponent making the same sale without us.  The
    value therefore includes our realised cash plus revenue denied to the
    opponent.  This is a transparent game margin, not a probability estimate.
    """
    qty = max(0, int(qty))
    inventory = max(0, int(inventory))
    opponent_qty = max(0, int(opponent_qty))
    if qty <= 0:
        return 0.0
    own_revenue, opponent_revenue, _book = _lockstep_sale_result(
        item, qty, opponent_qty, inventory,
    )
    opponent_alone, _after = _sale_result(
        item, opponent_qty, inventory,
    )
    return float(own_revenue + opponent_alone - opponent_revenue)


def _allocation_dp(item_costs, capacity):
    """Exact minimum over one conserved integer allocation budget.

    ``item_costs[i][h]`` is the worst value for item ``i`` when at most ``h``
    hidden units of the shared stock budget are assigned to that item.  The
    adversary may leave capacity unused, matching the physical inequality
    ``sum(h_i) <= shedCapacity``.
    """
    capacity = max(0, int(capacity))
    dp = [float("inf")] * (capacity + 1)
    dp[0] = 0.0
    for costs in item_costs:
        nxt = [float("inf")] * (capacity + 1)
        for used, prior in enumerate(dp):
            if prior == float("inf"):
                continue
            for hidden, cost in enumerate(costs[:capacity - used + 1]):
                total = used + hidden
                nxt[total] = min(nxt[total], prior + float(cost))
        dp = nxt
    return float(min(dp) if dp else 0.0)


def _paired_bundle_value(outputs, inventories, opponent_visible,
                         hidden_capacity):
    """Robust bundle value with one physical hidden-shed capacity budget.

    Visible future output remains a per-product interval.  Hidden stock is not
    independently duplicated across those intervals: integer allocations
    ``h_i`` share the exact engine shed capacity.  Repeated own output is
    already aggregated in ``outputs`` before entering this dynamic program.
    """
    item_costs = []
    for item in sorted(outputs):
        qty = max(0, int(outputs.get(item, 0) or 0))
        if item not in econ.SELLABLE or qty <= 0:
            continue
        inv = int(inventories.get(item, econ.MARKET_I0) or econ.MARKET_I0)
        visible = max(0, int(opponent_visible.get(item, 0) or 0))
        costs = []
        for hidden in range(max(0, int(hidden_capacity)) + 1):
            costs.append(min(
                _paired_sale_exact(item, qty, inv, opponent_qty)
                for opponent_qty in range(visible + hidden + 1)
            ))
        item_costs.append(costs)
    return _allocation_dp(item_costs, hidden_capacity)


def _paired_bundle_difference(candidate_outputs, baseline_outputs,
                              inventories, opponent_visible,
                              hidden_capacity):
    """Worst same-scenario candidate-minus-baseline bundle value.

    Both policies face the same exact opponent quantity and the same conserved
    hidden allocation.  This is stronger than comparing two independently
    minimised absolute values: a positive result proves candidate dominance
    throughout the named uncertainty set.
    """
    item_costs = []
    for item in sorted(set(candidate_outputs) | set(baseline_outputs)):
        if item not in econ.SELLABLE:
            continue
        candidate_qty = max(0, int(candidate_outputs.get(item, 0) or 0))
        baseline_qty = max(0, int(baseline_outputs.get(item, 0) or 0))
        inv = int(inventories.get(item, econ.MARKET_I0) or econ.MARKET_I0)
        visible = max(0, int(opponent_visible.get(item, 0) or 0))
        costs = []
        for hidden in range(max(0, int(hidden_capacity)) + 1):
            costs.append(min(
                (_paired_sale_exact(
                    item, candidate_qty, inv, opponent_qty,
                ) - _paired_sale_exact(
                    item, baseline_qty, inv, opponent_qty,
                ))
                for opponent_qty in range(visible + hidden + 1)
            ))
        item_costs.append(costs)
    return _allocation_dp(item_costs, hidden_capacity)


def _reserved_book(snap):
    book = {item: int(snap.market_inv.get(item, econ.MARKET_I0)
                      or econ.MARKET_I0)
            for item in econ.SELLABLE}
    reserve = _remaining_visible_units(snap, snap.me)
    reserve.update(_remaining_visible_units(snap, snap.opp))
    for item, qty in reserve.items():
        book[item] = book.get(item, econ.MARKET_I0) + max(0, int(qty))
    return book


def _crop_event_days(crop, planted_day):
    spec = econ.CROPS[crop]
    first_refresh = planted_day + int(spec["first_yield_day"]) - 1
    if first_refresh > LAST_DAY - 1:
        return []
    if not spec["ongoing"]:
        return [first_refresh]
    out = []
    for refresh in range(first_refresh, LAST_DAY):
        age = refresh + 1 - planted_day - int(spec["first_yield_day"])
        if age < 0 or age % int(spec["interval"]):
            continue
        production = age // int(spec["interval"]) + 1
        if production <= int(spec["max_yield"]):
            out.append(refresh)
    return out


def _animal_event_days(kind, placed_day):
    spec = econ.ANIMALS[kind]
    out = []
    for refresh in range(placed_day, LAST_DAY):
        age = refresh + 1 - placed_day - int(spec["first_yield_day"])
        if age >= 0 and age % int(spec["interval"]) == 0:
            out.append(refresh)
    return out


def _profiles(snap, counts, max_distance):
    """Return constructive daily round trips, feed and banked output."""
    trips = defaultdict(list)
    feed = Counter()
    outputs = defaultdict(Counter)
    start = int(snap.day) + 1
    travel = 2 * max(0, int(max_distance))

    for crop in sorted(econ.CROPS):
        n = max(0, int(counts.get(crop, 0) or 0))
        if n <= 0:
            continue
        events = _crop_event_days(crop, start)
        if not events:
            return None, None, None, "no_terminal_output"
        last_refresh = events[-1]
        harvests = Counter(refresh + 1 for refresh in events)
        for day in range(start, last_refresh + 2):
            ops = 0
            if day == start:
                ops += 2                         # PLANT + survival WATER
            elif day <= last_refresh:
                ops += 1                         # WATER
            if harvests.get(day):
                ops += 1                         # HARVEST
                per = (1 if econ.CROPS[crop]["ongoing"]
                       else int(econ.CROPS[crop]["max_yield"]))
                outputs[day][crop] += n * per * harvests[day]
            if ops:
                trips[day].extend([travel + ops] * n)

    for kind in sorted(econ.ANIMALS):
        n = max(0, int(counts.get(kind, 0) or 0))
        if n <= 0:
            continue
        events = _animal_event_days(kind, start)
        if not events:
            return None, None, None, "no_terminal_output"
        last_refresh = events[-1]
        harvests = Counter(refresh + 1 for refresh in events)
        event_rank = {refresh + 1: i for i, refresh in enumerate(events)}
        for day in range(start, last_refresh + 2):
            ops = 0
            if day == start:
                ops += 2                         # BUILD + PLACE
            if day <= last_refresh:
                ops += 2                         # FEED + CARE
                feed[day] += n
            if harvests.get(day):
                ops += 1                         # HARVEST
                units = 1 if event_rank[day] == 0 else 2
                product = econ.ANIMALS[kind]["product"]
                outputs[day][product] += n * units
            if ops:
                trips[day].extend([travel + ops] * n)
    return trips, feed, outputs, None


def _pack_workers(costs):
    """Construct first-fit independent round trips in 22-turn worker bins."""
    remaining = []
    for cost in sorted((int(c) for c in costs), reverse=True):
        if cost > ROUTE_TURNS:
            return None
        for i, room in enumerate(remaining):
            if cost <= room:
                remaining[i] -= cost
                break
        else:
            remaining.append(ROUTE_TURNS - cost)
    return len(remaining)


def _shared_route_cost(route):
    """Exact action count for one shed-start, shed-return service sweep.

    ``route`` is an ordered sequence of ``(position, operations)``.  The start
    charge is the worst of the four legal shed spawn tiles, every inter-tile
    Manhattan move and unit operation is counted once, and the route returns
    to the closest shed tile for one explicit aggregate DROP.
    """
    route = list(route)
    if not route:
        return 0
    first = route[0][0]
    cost = max(paths.dist(shed, first) for shed in paths.SHED_TILES)
    cost += sum(max(0, int(ops)) for _pos, ops in route)
    cost += sum(paths.dist(a[0], b[0]) for a, b in zip(route, route[1:]))
    cost += paths.dist_to_shed(route[-1][0]) + 1
    return int(cost)


@lru_cache(maxsize=4096)
def _shared_position_order(positions):
    """Memoized geometry-only nearest-next order for a position set."""
    remaining = list(positions)
    order = []
    cur = paths.SPAWN
    while remaining:
        nxt = min(remaining, key=lambda pos: (paths.dist(cur, pos), pos))
        remaining.remove(nxt)
        order.append(nxt)
        cur = nxt
    return tuple(order)


def _shared_sweep_order(stops):
    """Deterministic nearest-next open sweep from the public shed geometry."""
    by_position = {tuple(pos): int(ops) for pos, ops in stops}
    positions = tuple(sorted(by_position))
    return [(pos, by_position[pos])
            for pos in _shared_position_order(positions)]


@lru_cache(maxsize=8192)
def _pack_shared_routes_cached(stops):
    """Immutable exact memo for one normalized positioned daily profile."""
    order = _shared_sweep_order(stops)
    routes = []
    current = []
    current_cost = 0
    for stop in order:
        pos, ops = stop
        if current:
            prior = current[-1][0]
            trial_cost = (current_cost - paths.dist_to_shed(prior)
                          + paths.dist(prior, pos) + max(0, int(ops))
                          + paths.dist_to_shed(pos))
        else:
            trial_cost = _shared_route_cost([stop])
        if trial_cost <= SHARED_ROUTE_TURNS:
            current.append(stop)
            current_cost = trial_cost
            continue
        if not current or _shared_route_cost([stop]) > SHARED_ROUTE_TURNS:
            return None
        routes.append(tuple(current))
        current = [stop]
        current_cost = _shared_route_cost(current)
    if current:
        routes.append(tuple(current))
    return tuple(routes)


def _pack_shared_routes(stops):
    """Split one explicit sweep into worker-feasible closed route segments."""
    # `_profiles_shared` emits a canonical type/slot order.  The cached solver
    # itself reorders geometrically, so preserving that canonical tuple avoids
    # thousands of redundant sorts and route copies without changing a route.
    normalized = tuple((tuple(pos), int(ops)) for pos, ops in stops)
    return _pack_shared_routes_cached(normalized)


@lru_cache(maxsize=8192)
def _pack_shared_routes_with_pickups_cached(stops):
    """Pack a sweep while charging every distinct shed PICKUP per route.

    ``stops`` contains ``(position, operations, pickup_items)`` triples.  A
    PICKUP action may take any quantity of one item, exactly matching the
    engine and route master; a route carrying several animal kinds therefore
    pays once for each kind, while any number of FEED stops pays once for
    WHEAT.  The returned public route shape deliberately omits the metadata.
    """
    by_position = {
        tuple(pos): (int(ops), frozenset(items))
        for pos, ops, items in stops
    }
    ordered_positions = _shared_position_order(tuple(sorted(by_position)))
    routes = []
    current = []
    current_base_cost = 0
    current_items = frozenset()
    for pos in ordered_positions:
        ops, items = by_position[pos]
        trial_items = current_items | items
        if current:
            prior = current[-1][0]
            trial_base_cost = (
                current_base_cost - paths.dist_to_shed(prior)
                + paths.dist(prior, pos) + max(0, int(ops))
                + paths.dist_to_shed(pos)
            )
        else:
            trial_base_cost = _shared_route_cost([(pos, ops)])
        trial_cost = trial_base_cost + len(trial_items)
        if trial_cost <= SHARED_ROUTE_TURNS:
            current.append((pos, ops))
            current_base_cost = trial_base_cost
            current_items = trial_items
            continue
        singleton_cost = _shared_route_cost([(pos, ops)]) + len(items)
        if not current or singleton_cost > SHARED_ROUTE_TURNS:
            return None
        routes.append(tuple(current))
        current = [(pos, ops)]
        current_base_cost = _shared_route_cost(current)
        current_items = items
    if current:
        routes.append(tuple(current))
    return tuple(routes)


def _pack_shared_routes_with_pickups(stops, pickups_by_position):
    """Pickup-aware counterpart used by the constructive prefix proof."""
    normalized = tuple(
        (tuple(pos), int(ops), tuple(sorted(pickups_by_position.get(pos, ()))))
        for pos, ops in stops
    )
    return _pack_shared_routes_with_pickups_cached(normalized)


def _two_phase_hire_schedule(routes, pickups_by_position, feed_qty=0):
    """Construct an hour-0/hour-1 hire schedule for closed future routes.

    The farmer and hands hired after hour 0 have 23 actions through hour 23.
    One aggregated WHEAT purchase, when needed, shares the hour-0 ten-order
    queue, leaving nine HIRE slots; hour 1 has ten further HIRE slots and those
    hands retain 22 actions. Routes are freely assignable, so matching sorted
    route costs to sorted capacities is an exact finite feasibility test.
    """
    routes = tuple(routes or ())
    workers = len(routes)
    if workers <= 0:
        return ()
    costs = []
    for route in routes:
        items = set()
        for pos, _ops in route:
            items.update(pickups_by_position.get(tuple(pos), ()))
        costs.append(_shared_route_cost(route) + len(items))
    first_hires = min(
        max(0, workers - 1),
        max(0, econ.MAX_ORDERS - int(bool(feed_qty))),
    )
    remaining = max(0, workers - 1 - first_hires)
    second_hires = min(remaining, econ.MAX_ORDERS)
    if second_hires < remaining:
        return None
    capacities = ([SHARED_ROUTE_TURNS] * (1 + first_hires)
                  + [SHARED_ROUTE_TURNS - 1] * second_hires)
    if any(cost > capacity for cost, capacity in zip(
            sorted(costs, reverse=True), sorted(capacities, reverse=True))):
        return None
    return (int(first_hires), int(second_hires))


def _assign_positions(counts, slots):
    """Mirror the default capital-column placement order on concrete slots."""
    remaining = list(slots)
    assigned = defaultdict(list)
    asset_order = sorted(
        (item for item in counts if item in econ.ANIMALS),
        key=lambda item: (econ.ANIMALS[item]["cost"], item),
    )
    asset_order += sorted(item for item in counts if item in econ.CROPS)
    for item in asset_order:
        qty = max(0, int(counts.get(item, 0) or 0))
        if qty > len(remaining):
            return None
        assigned[item].extend(remaining[:qty])
        del remaining[:qty]
    return assigned


def _profiles_positioned(snap, assigned, start_day=None,
                         defer_first_animal_service=False,
                         credit_fertilizer=False):
    """Return daily service stops for one exact item-to-tile assignment.

    The legacy certificate purchases at an abstract next-day boundary.  A
    phase-aligned purchase instead plants/builds/places after hour 0 of the
    current day.  Newly placed animals survive that first un-fed night by the
    exact two-night starvation rule, so their first FEED+CARE is next day.
    """
    stops = defaultdict(list)
    feed = Counter()
    outputs = defaultdict(Counter)
    start = (int(snap.day) + 1 if start_day is None else int(start_day))

    for crop in sorted(econ.CROPS):
        positions = assigned.get(crop, ())
        if not positions:
            continue
        events = _crop_event_days(crop, start)
        if not events:
            return None, None, None, "no_terminal_output"
        last_refresh = events[-1]
        harvests = Counter(refresh + 1 for refresh in events)
        for day in range(start, last_refresh + 2):
            ops = 0
            if day == start:
                ops += 2
            elif day <= last_refresh:
                ops += 1
            if harvests.get(day):
                ops += 1
                per = (1 if econ.CROPS[crop]["ongoing"]
                       else int(econ.CROPS[crop]["max_yield"]))
                outputs[day][crop] += len(positions) * per * harvests[day]
            if ops:
                stops[day].extend((pos, ops) for pos in positions)

    for kind in sorted(econ.ANIMALS):
        positions = assigned.get(kind, ())
        if not positions:
            continue
        events = _animal_event_days(kind, start)
        if not events:
            return None, None, None, "no_terminal_output"
        last_refresh = events[-1]
        harvests = Counter(refresh + 1 for refresh in events)
        event_rank = {refresh + 1: i for i, refresh in enumerate(events)}
        for day in range(start, last_refresh + 2):
            ops = 0
            if day == start:
                ops += 2
            if (day <= last_refresh
                    and not (defer_first_animal_service and day == start)):
                ops += 2
                feed[day] += len(positions)
            if harvests.get(day):
                ops += 1
                units = 1 if event_rank[day] == 0 else 2
                outputs[day][econ.ANIMALS[kind]["product"]] += (
                    len(positions) * units
                )
            # A surviving animal sets ``fertilizer_available`` at every
            # nightly refresh, independent of its product clock.  It becomes
            # collectable the following day.  This opt-in certificate charges
            # one exact COLLECT_FERTILIZER operation per positioned animal;
            # the shared closed route already charges its aggregate DROP.
            if credit_fertilizer and day > start:
                ops += 1
                outputs[day]["FERTILIZER"] += len(positions)
            if ops:
                stops[day].extend((pos, ops) for pos in positions)
    return stops, feed, outputs, None


def _profiles_first_output_positioned(snap, assigned, start_day=None):
    """Minimal constructive service prefix through each asset's first sale.

    A planted crop is watered immediately, then every other day: the engine
    tolerates one unwatered night but converts it to a weed after the second.
    A newly placed animal is analogously fed on the following day and every
    other day thereafter; CARE cannot affect the first base yield and is
    omitted.  Each asset leaves this certificate after its first HARVEST, so no
    speculative obligation beyond the next public replans is charged.
    """
    stops = defaultdict(list)
    pickups = defaultdict(lambda: defaultdict(set))
    feed = Counter()
    outputs = defaultdict(Counter)
    start = (int(snap.day) + 1 if start_day is None else int(start_day))

    for crop in sorted(econ.CROPS):
        positions = assigned.get(crop, ())
        if not positions:
            continue
        events = _crop_event_days(crop, start)
        if not events:
            return None, None, None, None, "no_prefix_output"
        refresh = int(events[0])
        # PLANT+WATER is atomic in the capital column. Thereafter one WATER on
        # every second day is the exact minimum survival schedule.
        stops[start].extend((pos, 2) for pos in positions)
        for day in range(start + 2, refresh + 1, 2):
            stops[day].extend((pos, 1) for pos in positions)
        sale_day = refresh + 1
        stops[sale_day].extend((pos, 1) for pos in positions)
        units = (1 if econ.CROPS[crop]["ongoing"]
                 else int(econ.CROPS[crop]["max_yield"]))
        outputs[sale_day][crop] += len(positions) * units

    for kind in sorted(econ.ANIMALS):
        positions = assigned.get(kind, ())
        if not positions:
            continue
        events = _animal_event_days(kind, start)
        if not events:
            return None, None, None, None, "no_prefix_output"
        refresh = int(events[0])
        stops[start].extend((pos, 2) for pos in positions)  # BUILD + PLACE
        for pos in positions:
            pickups[start][pos].add(kind)
        # Placement day may end unfed once. FEED the following day and every
        # second day through the first refresh; no CARE can change first yield.
        for day in range(start + 1, refresh + 1, 2):
            stops[day].extend((pos, 1) for pos in positions)
            feed[day] += len(positions)
            for pos in positions:
                pickups[day][pos].add("WHEAT")
        sale_day = refresh + 1
        stops[sale_day].extend((pos, 1) for pos in positions)
        outputs[sale_day][econ.ANIMALS[kind]["product"]] += len(positions)
    return stops, feed, outputs, pickups, None


def _profiles_exact_first_output_positioned(snap, assigned, start_day=None):
    """Earliest first-output prefix with exact one-time crop accumulation.

    The legacy V98 prefix incorrectly assigned every one-time crop its rule
    ``max_yield`` at first maturity. The engine instead creates the plant with
    one held unit and adds one only when WATER executes inside
    ``[(max_yield_day + 1)//2, max_yield_day]``. This profile executes the
    same minimum alternating survival schedule, then WATER+HARVEST on the
    earliest legal sale day and counts only the increments actually earned.
    Ongoing crops and animals still have exactly one base unit then.
    """
    stops = defaultdict(list)
    pickups = defaultdict(lambda: defaultdict(set))
    feed = Counter()
    outputs = defaultdict(Counter)
    start = (int(snap.day) + 1 if start_day is None else int(start_day))

    for crop in sorted(econ.CROPS):
        positions = assigned.get(crop, ())
        if not positions:
            continue
        spec = econ.CROPS[crop]
        events = _crop_event_days(crop, start)
        if not events:
            return None, None, None, None, "no_prefix_output"
        sale_day = int(events[0]) + 1
        stops[start].extend((pos, 2) for pos in positions)
        water_days = list(range(start + 2, sale_day, 2))
        for day in water_days:
            stops[day].extend((pos, 1) for pos in positions)
        if spec["ongoing"]:
            harvest_ops = 1
            units = 1
        else:
            # WATER before HARVEST on the maturity visit earns the final exact
            # growth-window increment. Initial held yield is one.
            harvest_ops = 2
            growth_start = (int(spec["max_yield_day"]) + 1) // 2
            productive_waters = sum(
                growth_start <= day - start <= int(spec["max_yield_day"])
                for day in water_days + [sale_day]
            )
            units = min(int(spec["max_yield"]), 1 + productive_waters)
        stops[sale_day].extend((pos, harvest_ops) for pos in positions)
        outputs[sale_day][crop] += len(positions) * units

    for kind in sorted(econ.ANIMALS):
        positions = assigned.get(kind, ())
        if not positions:
            continue
        events = _animal_event_days(kind, start)
        if not events:
            return None, None, None, None, "no_prefix_output"
        refresh = int(events[0])
        stops[start].extend((pos, 2) for pos in positions)
        for pos in positions:
            pickups[start][pos].add(kind)
        for day in range(start + 1, refresh + 1, 2):
            stops[day].extend((pos, 1) for pos in positions)
            feed[day] += len(positions)
            for pos in positions:
                pickups[day][pos].add("WHEAT")
        sale_day = refresh + 1
        stops[sale_day].extend((pos, 1) for pos in positions)
        outputs[sale_day][econ.ANIMALS[kind]["product"]] += len(positions)
    return stops, feed, outputs, pickups, None


def _profiles_minimal_full_output_positioned(snap, assigned, start_day=None):
    """Minimum-service path through every reachable base output.

    This is the executable continuation endpoint paired with V99's immediate
    post-first-output abandonment endpoint.  Crops WATER only often enough to
    avoid the second missed night.  Animals FEED on the same alternating
    cadence and never CARE, so every production event contributes exactly its
    unconditional base unit.  One-time crop accumulation uses the same exact
    productive-WATER equation as V99.  No fertilizer or care bonus is valued.
    """
    stops = defaultdict(list)
    pickups = defaultdict(lambda: defaultdict(set))
    feed = Counter()
    outputs = defaultdict(Counter)
    start = (int(snap.day) + 1 if start_day is None else int(start_day))

    for crop in sorted(econ.CROPS):
        positions = assigned.get(crop, ())
        if not positions:
            continue
        spec = econ.CROPS[crop]
        events = _crop_event_days(crop, start)
        if not events:
            return None, None, None, None, "no_continuation_output"
        sale_days = [int(refresh) + 1 for refresh in events]
        last_sale = sale_days[-1]
        stops[start].extend((pos, 2) for pos in positions)
        water_days = list(range(start + 2, last_sale + 1, 2))
        for day in water_days:
            stops[day].extend((pos, 1) for pos in positions)
        if spec["ongoing"]:
            for day in sale_days:
                stops[day].extend((pos, 1) for pos in positions)
                outputs[day][crop] += len(positions)
        else:
            sale_day = sale_days[0]
            # The maturity WATER is productive and precedes HARVEST. If it is
            # already on the alternating cadence, add only HARVEST here.
            extra_ops = 1 if sale_day in water_days else 2
            stops[sale_day].extend((pos, extra_ops) for pos in positions)
            growth_start = (int(spec["max_yield_day"]) + 1) // 2
            productive_waters = sum(
                growth_start <= day - start <= int(spec["max_yield_day"])
                for day in sorted(set(water_days + [sale_day]))
            )
            units = min(int(spec["max_yield"]), 1 + productive_waters)
            outputs[sale_day][crop] += len(positions) * units

    for kind in sorted(econ.ANIMALS):
        positions = assigned.get(kind, ())
        if not positions:
            continue
        events = _animal_event_days(kind, start)
        if not events:
            return None, None, None, None, "no_continuation_output"
        sale_days = [int(refresh) + 1 for refresh in events]
        last_sale = sale_days[-1]
        stops[start].extend((pos, 2) for pos in positions)
        for pos in positions:
            pickups[start][pos].add(kind)
        for day in range(start + 1, last_sale + 1, 2):
            stops[day].extend((pos, 1) for pos in positions)
            feed[day] += len(positions)
            for pos in positions:
                pickups[day][pos].add("WHEAT")
        product = econ.ANIMALS[kind]["product"]
        for day in sale_days:
            stops[day].extend((pos, 1) for pos in positions)
            outputs[day][product] += len(positions)
    return stops, feed, outputs, pickups, None


def _visible_survival_profile(snap, horizon_day, start_day=None):
    """Rule-minimum service reserve for public standing productive capital.

    This is deliberately a workload baseline, not a forecast of the ordinary
    policy.  From the next replan day through ``horizon_day`` every visible
    ongoing crop is WATERed and every visible animal is FEEDed on alternating
    days.  One missed night is legal; service every second day is therefore
    the exact minimum periodic cadence that prevents the second miss.  The
    first service is reserved unconditionally because today's already-chosen
    unit phase is outside this future certificate.

    Visible one-time crops are assigned the explicit feasible abandonment
    alternative at zero residual.  Crediting or routing their harvest would
    introduce a separate sale/retention decision; watering them after their
    public finite life would instead create phantom work.  No CARE, harvest or
    future output is assumed for the standing baseline.
    """
    stops = defaultdict(list)
    pickups = defaultdict(lambda: defaultdict(set))
    feed = Counter()
    start = (int(snap.day) + 1 if start_day is None else int(start_day))
    horizon = min(LAST_DAY, int(horizon_day))
    if horizon < start:
        return stops, feed, pickups

    ongoing = [
        tuple(pos) for pos, tile in sorted(snap.me.crops.items())
        if econ.CROPS.get(tile.get("crop"), {}).get("ongoing")
    ]
    animals = [tuple(pos) for pos in sorted(snap.me.animals)]
    for day in range(start, horizon + 1, 2):
        stops[day].extend((pos, 1) for pos in ongoing)
        stops[day].extend((pos, 1) for pos in animals)
        feed[day] += len(animals)
        for pos in animals:
            pickups[day][pos].add("WHEAT")
    return stops, feed, pickups


def _visible_full_service_profile(snap, horizon_day, start_day=None):
    """Rule-derived full-service workload of the public standing farm.

    This profile is used only by an explicit continuation endpoint. Ongoing
    crops are watered daily and harvested on public production dates. Animals
    are fed, cared and checked for fertilizer daily, with harvest added on
    product dates. Output itself belongs to the identical standing baseline
    and is deliberately omitted; only its route workload interacts with new
    capital. The start is after today's already-projected unit phase.
    """
    stops = defaultdict(list)
    pickups = defaultdict(lambda: defaultdict(set))
    feed = Counter()
    start = (int(snap.day) + 1 if start_day is None
             else max(int(snap.day) + 1, int(start_day)))
    horizon = min(LAST_DAY, int(horizon_day))
    if horizon < start:
        return stops, feed, pickups

    for pos, tile in sorted(snap.me.crops.items()):
        crop = tile.get("crop")
        spec = econ.CROPS.get(crop)
        if spec is None:
            continue
        sale_days = {
            int(refresh) + 1
            for refresh in objective._crop_event_days(tile, crop, snap.day)
        }
        if spec["ongoing"]:
            end = horizon
        elif sale_days:
            end = min(horizon, min(sale_days))
        else:
            continue
        for day in range(start, end + 1):
            ops = 1 + int(day in sale_days)  # WATER + optional HARVEST
            stops[day].append((tuple(pos), ops))

    for pos, tile in sorted(snap.me.animals.items()):
        kind = tile.get("animal")
        if kind not in econ.ANIMALS:
            continue
        sale_days = {
            int(refresh) + 1
            for refresh in objective._animal_event_days(
                tile, kind, snap.day, include_start=True,
            )
        }
        for day in range(start, horizon + 1):
            # FEED + CARE + COLLECT_FERTILIZER + optional HARVEST.
            stops[day].append((tuple(pos), 3 + int(day in sale_days)))
            feed[day] += 1
            pickups[day][tuple(pos)].add("WHEAT")
    return stops, feed, pickups


def _merge_positioned_work(stops, feed, pickups, extra_stops, extra_feed,
                           extra_pickups):
    """Merge two dated public-equation workloads without losing pickups."""
    for day, day_stops in extra_stops.items():
        stops[day].extend(day_stops)
    feed.update(extra_feed)
    for day, by_position in extra_pickups.items():
        for pos, items in by_position.items():
            day_pickups = pickups.setdefault(day, defaultdict(set))
            day_pickups.setdefault(pos, set()).update(items)


def _profiles_shared(snap, counts, slots):
    """Return daily positioned service stops, feed and grouped output."""
    assigned = _assign_positions(counts, slots)
    if assigned is None:
        return None, None, None, "physical_slots"
    return _profiles_positioned(snap, assigned)


def _fixed_commitment(snap, fixed_orders):
    cash = 0.0
    shed = int(getattr(snap, "shed_used", sum(snap.shed.values())) or 0)
    book = {item: int(snap.market_inv.get(item, econ.MARKET_I0)
                      or econ.MARKET_I0)
            for item in econ.SELLABLE}
    for order in fixed_orders or ():
        if len(order) < 3 or order[0] != "BUY_PRODUCT":
            continue
        item, qty = order[1], max(0, int(order[2] or 0))
        if item not in econ.BUYABLE:
            continue
        inv = book[item]
        cash += econ.buy_cost(item, qty, inv)
        book[item] = inv - qty
        shed += qty
    return cash, shed


def certify(snap, counts, reserve=0.0, max_distance=0, land_cost=0.0,
            fixed_orders=None):
    """Prove an incremental portfolio's daily resource trajectory."""
    counts = {item: max(0, int(qty or 0))
              for item, qty in counts.items() if int(qty or 0) > 0}
    cert = Certificate(counts, land_cost)
    asset_cost = sum(econ.CROPS[item]["seed"] * qty
                     for item, qty in counts.items() if item in econ.CROPS)
    asset_cost += sum(econ.ANIMALS[item]["cost"] * qty
                      for item, qty in counts.items() if item in econ.ANIMALS)
    fixed_spend, initial_shed = _fixed_commitment(snap, fixed_orders)
    animal_units = sum(qty for item, qty in counts.items()
                       if item in econ.ANIMALS)
    cert.upfront_spend = float(asset_cost + land_cost)
    cash = float(snap.me.money) - fixed_spend - cert.upfront_spend
    if cash < float(reserve) - 1e-9:
        return cert.reject("upfront_cash", cash)
    if initial_shed + animal_units > econ.SHED_CAPACITY:
        return cert.reject("shed_capacity", cash)

    trips, feed, outputs, error = _profiles(snap, counts, max_distance)
    if error:
        return cert.reject(error, cash)
    book = _reserved_book(snap)
    cert.cash_path.append(cash)
    days = sorted(set(trips) | set(feed) | set(outputs))
    for day in days:
        workers = _pack_workers(trips.get(day, ()))
        if workers is None:
            return cert.reject("daily_labour", cash)
        hires = max(0, workers - 1)
        feed_qty = max(0, int(feed.get(day, 0)))
        # Hires and the one aggregated WHEAT order execute at hour 0.
        if hires + (1 if feed_qty else 0) > econ.MAX_ORDERS:
            return cert.reject("market_order_slots", cash)
        if feed_qty > econ.SHED_CAPACITY:
            return cert.reject("shed_capacity", cash)
        day_cost = float(econ.hire_block_cost(0, hires))
        if feed_qty:
            inv = int(book.get("WHEAT", econ.MARKET_I0))
            day_cost += econ.buy_cost("WHEAT", feed_qty, inv)
            book["WHEAT"] = inv - feed_qty
        cash -= day_cost
        if cash < float(reserve) - 1e-9:
            return cert.reject("bridge_cash", cash)
        day_output = Counter(outputs.get(day, {}))
        if sum(day_output.values()) > econ.SHED_CAPACITY:
            return cert.reject("shed_capacity", cash)
        if len([q for q in day_output.values() if q > 0]) > econ.MAX_ORDERS:
            return cert.reject("market_order_slots", cash)
        revenue, book = _sell_outputs(book, day_output)
        cash += revenue
        cert.cash_path.append(cash)
        cert.workers_by_day[day] = workers
        cert.feed_by_day[day] = feed_qty
        cert.outputs_by_day[day] = dict(day_output)
    cert.final_cash = cash
    return cert


def certify_shared(snap, counts, slots, reserve=0.0, land_cost=0.0,
                   fixed_orders=None, _context=None, paired_objective=False,
                   _paired_context=None, positions_by_item=None,
                   phase_aligned=False, post_market_cash=0.0,
                   cash_credit_by_day=None, persistent_shed_by_day=None,
                   sale_products_by_day=None, credit_output_cash=True,
                   enforce_bridge_cash=True, first_output_only=False,
                   exact_first_output=False, visible_survival_horizon=None,
                   visible_full_service_horizon=None,
                   minimal_full_output=False, credit_fertilizer=False,
                   two_phase_future_hires=False):
    """Prove the same trajectory with positioned, shared closed routes."""
    counts = {item: max(0, int(qty or 0))
              for item, qty in counts.items() if int(qty or 0) > 0}
    cert = Certificate(counts, land_cost)
    asset_cost = sum(econ.CROPS[item]["seed"] * qty
                     for item, qty in counts.items() if item in econ.CROPS)
    asset_cost += sum(econ.ANIMALS[item]["cost"] * qty
                      for item, qty in counts.items() if item in econ.ANIMALS)
    if _context is None:
        fixed_spend, initial_shed = _fixed_commitment(snap, fixed_orders)
        initial_book = _reserved_book(snap)
    else:
        fixed_spend, initial_shed, initial_book = _context
    animal_units = sum(qty for item, qty in counts.items()
                       if item in econ.ANIMALS)
    cert.upfront_spend = float(asset_cost + land_cost)
    cert.paired_value = -cert.upfront_spend if paired_objective else 0.0
    cash = float(snap.me.money) - fixed_spend - cert.upfront_spend
    cert.minimum_cash = min(cert.minimum_cash, cash)
    if cash < float(reserve) - 1e-9:
        return cert.reject("upfront_cash", cash)
    if initial_shed + animal_units > econ.SHED_CAPACITY:
        return cert.reject("shed_capacity", cash)

    # Assets and current hires execute before V89's ordinary SELL orders.  A
    # certified current sale may therefore fund later service, but never the
    # purchase that precedes it.  Preserve both points on the cash path.
    if float(post_market_cash) > 0.0:
        cert.cash_path.append(cash)
        cash += float(post_market_cash)

    if positions_by_item is None:
        assigned = _assign_positions(counts, slots)
    else:
        assigned = {
            item: [tuple(pos) for pos in positions_by_item.get(item, ())]
            for item in counts
        }
        assigned_positions = [pos for positions in assigned.values()
                              for pos in positions]
        if (any(len(assigned.get(item, ())) != qty
                for item, qty in counts.items())
                or len(assigned_positions) != len(set(assigned_positions))
                or not set(assigned_positions).issubset(
                    {tuple(pos) for pos in slots}
                )):
            assigned = None
    if assigned is None:
        return cert.reject("physical_slots", cash)
    cert.positions_by_item = {
        item: tuple(positions) for item, positions in assigned.items()
    }
    start_day = int(snap.day) if phase_aligned else None
    if minimal_full_output:
        stops, feed, outputs, pickups, error = (
            _profiles_minimal_full_output_positioned(
                snap, assigned, start_day=start_day,
            )
        )
    elif exact_first_output:
        stops, feed, outputs, pickups, error = (
            _profiles_exact_first_output_positioned(
                snap, assigned, start_day=start_day,
            )
        )
    elif first_output_only:
        stops, feed, outputs, pickups, error = _profiles_first_output_positioned(
            snap, assigned, start_day=start_day,
        )
    else:
        stops, feed, outputs, error = _profiles_positioned(
            snap, assigned, start_day=start_day,
            defer_first_animal_service=phase_aligned,
            credit_fertilizer=credit_fertilizer,
        )
        pickups = {}
    if error:
        return cert.reject(error, cash)
    if visible_survival_horizon is not None:
        background = _visible_survival_profile(
            snap, visible_survival_horizon, start_day=start_day,
        )
        _merge_positioned_work(stops, feed, pickups, *background)
    if visible_full_service_horizon is not None:
        background = _visible_full_service_profile(
            snap, visible_full_service_horizon, start_day=start_day,
        )
        _merge_positioned_work(stops, feed, pickups, *background)
    if phase_aligned:
        # The post-market route master proves today's positioned PLANT+WATER or
        # BUILD+PLACE operations and charges the actual current hires.  Keep
        # their earlier production calendar here, but do not double-charge the
        # same current-day route in this future cash/service certificate.
        stops.pop(int(snap.day), None)
    book = dict(initial_book)
    if paired_objective:
        if _paired_context is None:
            paired_book = _own_reserved_book(snap)
            opponent_outputs = _visible_output_schedule(snap, snap.opp)
            guaranteed_drain = _guaranteed_town_drain_by_day(snap)
        else:
            paired_book, opponent_outputs, guaranteed_drain = _paired_context
            paired_book = dict(paired_book)
        paired_step = int(snap.step)
    else:
        paired_book, opponent_outputs = {}, {}
        guaranteed_drain = {}
        paired_step = int(snap.step)
    cert.cash_path.append(cash)
    cash_credit_by_day = dict(cash_credit_by_day or {})
    persistent_shed_by_day = dict(persistent_shed_by_day or {})
    sale_products_by_day = {
        int(day): set(items) for day, items in
        (sale_products_by_day or {}).items()
    }
    opponent_days = set(opponent_outputs) if paired_objective else set()
    if visible_survival_horizon is not None:
        opponent_days = {
            day for day in opponent_days
            if day <= int(visible_survival_horizon)
        }
    elif visible_full_service_horizon is not None:
        opponent_days = {
            day for day in opponent_days
            if day <= int(visible_full_service_horizon)
        }
    elif (first_output_only or exact_first_output) and outputs:
        opponent_days = {day for day in opponent_days
                         if day <= max(outputs)}
    days = sorted(set(stops) | set(feed) | set(outputs) | opponent_days)
    for day in days:
        if first_output_only or exact_first_output or minimal_full_output:
            routes = _pack_shared_routes_with_pickups(
                stops.get(day, ()), pickups.get(day, {}),
            )
        else:
            routes = _pack_shared_routes(stops.get(day, ()))
        if routes is None:
            return cert.reject("daily_labour", cash)
        workers = len(routes)
        hires = max(0, workers - 1)
        feed_qty = max(0, int(feed.get(day, 0)))
        if two_phase_future_hires:
            phases = _two_phase_hire_schedule(
                routes, pickups.get(day, {}), feed_qty,
            )
            if phases is None:
                return cert.reject("staged_hire_horizon", cash)
            cert.hire_phases_by_day[day] = phases
        elif hires + (1 if feed_qty else 0) > econ.MAX_ORDERS:
            return cert.reject("market_order_slots", cash)
        if feed_qty > econ.SHED_CAPACITY:
            return cert.reject("shed_capacity", cash)
        day_cost = float(econ.hire_block_cost(0, hires))
        if feed_qty:
            inv = int(book.get("WHEAT", econ.MARKET_I0))
            day_cost += _cached_buy_cost("WHEAT", feed_qty, inv)
            book["WHEAT"] = inv - feed_qty
        cash -= day_cost
        cert.minimum_cash = min(cert.minimum_cash, cash)
        cert.operating_cost += day_cost
        cert.operating_cost_by_day[day] = day_cost
        if paired_objective:
            cert.paired_value -= day_cost
        if enforce_bridge_cash and cash < float(reserve) - 1e-9:
            return cert.reject("bridge_cash", cash)
        day_output = Counter(outputs.get(day, {}))
        persistent = max(0, int(persistent_shed_by_day.get(day, 0) or 0))
        if persistent + sum(day_output.values()) > econ.SHED_CAPACITY:
            return cert.reject("shed_capacity", cash)
        sale_products = ({item for item, qty in day_output.items() if qty > 0}
                         | sale_products_by_day.get(day, set()))
        if len(sale_products) > econ.MAX_ORDERS:
            return cert.reject("market_order_slots", cash)
        revenue, book = _sell_outputs_cached(book, day_output)
        if credit_output_cash:
            cash += revenue
        cash += max(0.0, float(cash_credit_by_day.get(day, 0.0) or 0.0))
        if paired_objective:
            sale_step = min(718, max(paired_step, int(day) * econ.TURNS_PER_DAY))
            for item in econ.SELLABLE:
                paired_book[item] = max(
                    0, int(paired_book.get(item, econ.MARKET_I0))
                    - int(guaranteed_drain.get(day, {}).get(item, 0))
                )
            opponent_day = Counter(opponent_outputs.get(day, {}))
            for item in sorted(set(day_output) | set(opponent_day)):
                qty = max(0, int(day_output.get(item, 0)))
                opp_upper = max(0, int(opponent_day.get(item, 0)))
                inv = int(paired_book.get(item, econ.MARKET_I0))
                cert.paired_value += _paired_sale_value(
                    item, qty, inv, opp_upper,
                )
                _combined_revenue, paired_book[item] = _sale_result(
                    item, qty + opp_upper, inv,
                )
            paired_step = sale_step
        cert.cash_path.append(cash)
        cert.workers_by_day[day] = workers
        cert.feed_by_day[day] = feed_qty
        cert.outputs_by_day[day] = dict(day_output)
        cert.routes_by_day[day] = routes
        cert.cash_by_day[day] = float(cash)
    cert.final_cash = cash
    return cert


def certify_optional_continuation(snap, counts, slots, reserve=0.0,
                                  land_cost=0.0, fixed_orders=None,
                                  _context=None, paired_objective=True,
                                  _paired_context=None,
                                  positions_by_item=None):
    """Better feasible endpoint: exact first output or all base outputs.

    The first endpoint abandons immediately after V99's exact first sale. The
    continuation endpoint funds only rule-minimum survival and collects every
    reachable unconditional base output.  Taking the better feasible endpoint
    makes later service an option rather than V90/V91's imposed obligation.
    """
    common = dict(
        reserve=reserve, land_cost=land_cost, fixed_orders=fixed_orders,
        _context=_context, paired_objective=paired_objective,
        _paired_context=_paired_context, positions_by_item=positions_by_item,
    )
    first = certify_shared(
        snap, counts, slots, exact_first_output=True, **common,
    )
    full = certify_shared(
        snap, counts, slots, minimal_full_output=True, **common,
    )
    feasible = [cert for cert in (first, full) if cert.feasible]
    if not feasible:
        return first
    return max(feasible, key=lambda cert: (
        cert.paired_value, cert.final_cash, -cert.operating_cost,
        repr(sorted(cert.outputs_by_day.items())),
    ))


def certify_joint_farm_prefix(snap, counts, slots, reserve=0.0,
                              land_cost=0.0, fixed_orders=None,
                              _context=None, paired_objective=True,
                              _paired_context=None, positions_by_item=None):
    """V100 combined visible-farm and exact-new-capital prefix certificate.

    Physical feasibility and bridge cash use the combined dated workload.
    Economic value subtracts the identical visible-farm counterfactual over
    the candidate's endogenous first-output horizon.  Thus background service
    is neither rewarded nor charged to capital in isolation, while nonlinear
    route hires, feed purchases and the exact public market book remain joint.
    All standing assets have an explicit zero residual after the horizon.
    """
    clean = {item: max(0, int(qty or 0))
             for item, qty in counts.items() if int(qty or 0) > 0}
    if not clean:
        return certify_shared(
            snap, {}, slots, reserve=reserve, land_cost=land_cost,
            fixed_orders=fixed_orders, _context=_context,
            paired_objective=paired_objective,
            _paired_context=_paired_context,
        )
    start = int(snap.day) + 1
    horizon = max(
        start + int((econ.CROPS[item] if item in econ.CROPS
                     else econ.ANIMALS[item])["first_yield_day"])
        for item in clean
    )
    combined = certify_shared(
        snap, clean, slots, reserve=reserve, land_cost=land_cost,
        fixed_orders=fixed_orders, _context=_context,
        paired_objective=paired_objective,
        _paired_context=_paired_context, positions_by_item=positions_by_item,
        exact_first_output=True, visible_survival_horizon=horizon,
    )
    if not combined.feasible or not paired_objective:
        return combined
    baseline = certify_shared(
        snap, {}, (), reserve=0.0, land_cost=0.0,
        fixed_orders=fixed_orders, _context=_context,
        paired_objective=True, _paired_context=_paired_context,
        exact_first_output=True, visible_survival_horizon=horizon,
        enforce_bridge_cash=False,
    )
    if not baseline.feasible:
        return combined.reject("visible_baseline_" + baseline.reason,
                               combined.final_cash)
    combined.paired_value -= baseline.paired_value
    return combined


def productive_inventory_terms(snap, outputs_by_day, sale_bundle, sell_now,
                               opponent_capacity=econ.SHED_CAPACITY):
    """Robust two-sale value/cash terms for a productive certificate.

    The executable choice is binary at bundle level: execute V89's complete
    current sale vector, or retain that same vector until the selected capital
    portfolio's first certified output day.  Repeated quantities are aggregated
    once per product.  Every remaining unit derivable from either public farm
    is reserved ahead of the new output; guaranteed public town drain applies
    only before that reserve arrives.  This is conservative over every timing
    of visible future supply.

    One hidden opponent shed is allocated across products by `_allocation_dp`.
    With no positive town drain after the reserve, moving hidden supply earlier
    weakly lowers every later marginal price, so reserving it immediately before
    the certified sale is the exact worst timing in this lower-bound model.
    """
    bundle = {item: max(0, int(qty or 0))
              for item, qty in sale_bundle.items()
              if item in econ.SELLABLE and int(qty or 0) > 0}
    output_days = sorted(
        int(day) for day, outputs in outputs_by_day.items()
        if any(int(qty or 0) > 0 for qty in outputs.values())
    )
    anchor = output_days[0] if output_days else None
    if anchor is None and not sell_now:
        return None

    first_output = Counter(outputs_by_day.get(anchor, {}) if anchor is not None
                           else {})
    current = bundle if sell_now else {}
    retained = {} if sell_now else bundle
    current_value = 0.0
    after_current = {}
    for item in econ.SELLABLE:
        inv = int(snap.market_inv.get(item, econ.MARKET_I0)
                  or econ.MARKET_I0)
        qty = max(0, int(current.get(item, 0) or 0))
        gained, closing = _sale_result(item, qty, inv)
        current_value += gained
        after_current[item] = closing

    current_orders = [["SELL", item, qty]
                      for item, qty in sorted(current.items()) if qty > 0]
    if current_orders:
        from whitebox import market as _market
        current_cash = _market.robust_sale_cash(
            snap, current_orders, opponent_capacity,
        )
    else:
        current_cash = 0.0

    if anchor is None:
        return {
            "anchor_day": None,
            "paired_revenue": float(current_value),
            "current_cash": float(current_cash),
            "future_cash": 0.0,
            "future_products": set(),
        }

    from whitebox import market_model
    sale_step = min(718, max(int(snap.step), anchor * econ.TURNS_PER_DAY))
    visible = _remaining_visible_units(snap, snap.me)
    visible.update(_remaining_visible_units(snap, snap.opp))
    capacity = max(0, int(opponent_capacity))
    item_costs = []
    future_products = set()
    for item in sorted(set(first_output) | set(retained)):
        qty = (max(0, int(first_output.get(item, 0) or 0))
               + max(0, int(retained.get(item, 0) or 0)))
        if item not in econ.SELLABLE or qty <= 0:
            continue
        future_products.add(item)
        drain = market_model.town_take_bounds(
            snap, item, start_step=int(snap.step), end_step=sale_step,
        )[0]
        base = max(0, int(after_current[item]) - max(0, int(drain)))
        # All rule-derived visible remaining supply is placed after guaranteed
        # drain. This cannot overstate the future sale value.
        base += max(0, int(visible.get(item, 0) or 0))
        costs = []
        for hidden in range(capacity + 1):
            _hidden_value, after_hidden = _sale_result(item, hidden, base)
            costs.append(_sale_result(item, qty, after_hidden)[0])
        item_costs.append(costs)
    future_cash = (_allocation_dp(item_costs, capacity)
                   if item_costs else 0.0)
    return {
        "anchor_day": anchor,
        "paired_revenue": float(current_value + future_cash),
        "current_cash": float(current_cash),
        "future_cash": float(future_cash),
        "future_products": future_products,
    }


def productive_inventory_path_terms(snap, outputs_by_day, sale_bundle,
                                    sell_now,
                                    opponent_capacity=econ.SHED_CAPACITY,
                                    include_paired_value=True):
    """All-output extension of `productive_inventory_terms` for V91.

    With ``include_paired_value=True`` (V91), the objective uses one exact
    shared hidden allocation for the complete multi-day revenue path. Daily
    bridge cash uses a cheaper but valid lower bound: give every product its
    individual worst `shedCapacity` allocation. A physical shared allocation
    is a subset of those per-product bounds, so summing the individual minima
    cannot overstate cash at any prefix. V92 consumes only those feasibility
    prefixes and explicitly skips the unused terminal allocation DP. No
    revenue coefficient or opponent timing policy is introduced.
    """
    bundle = {item: max(0, int(qty or 0))
              for item, qty in sale_bundle.items()
              if item in econ.SELLABLE and int(qty or 0) > 0}
    days = sorted(
        int(day) for day, outputs in outputs_by_day.items()
        if any(int(qty or 0) > 0 for qty in outputs.values())
    )
    anchor = days[0] if days else None
    if anchor is None and not sell_now:
        return None
    current = bundle if sell_now else {}
    retained = {} if sell_now else bundle
    current_value = 0.0
    after_current = {}
    for item in econ.SELLABLE:
        inv = int(snap.market_inv.get(item, econ.MARKET_I0)
                  or econ.MARKET_I0)
        qty = max(0, int(current.get(item, 0) or 0))
        gained, closing = _sale_result(item, qty, inv)
        current_value += gained
        after_current[item] = closing
    current_orders = [["SELL", item, qty]
                      for item, qty in sorted(current.items()) if qty > 0]
    if current_orders:
        from whitebox import market as _market
        current_cash = _market.robust_sale_cash(
            snap, current_orders, opponent_capacity,
        )
    else:
        current_cash = 0.0
    if anchor is None:
        return {
            "anchor_day": None, "paired_revenue": float(current_value),
            "current_cash": float(current_cash), "prefix_cash": {},
            "future_products_by_day": {},
        }

    from whitebox import market_model
    sale_step = min(718, max(int(snap.step), anchor * econ.TURNS_PER_DAY))
    visible = _remaining_visible_units(snap, snap.me)
    visible.update(_remaining_visible_units(snap, snap.opp))
    capacity = max(0, int(opponent_capacity))
    items = sorted(
        set(retained)
        | {item for outputs in outputs_by_day.values() for item in outputs}
    )
    final_costs = []
    individual_prefix = {day: 0.0 for day in days}
    products_by_day = {}
    for item in items:
        if item not in econ.SELLABLE:
            continue
        drain = market_model.town_take_bounds(
            snap, item, start_step=int(snap.step), end_step=sale_step,
        )[0]
        base = max(0, int(after_current[item]) - max(0, int(drain)))
        base += max(0, int(visible.get(item, 0) or 0))
        curves = []
        worst_prefix = None
        hidden_values = (range(capacity + 1)
                         if include_paired_value else (capacity,))
        for hidden in hidden_values:
            _hidden_value, book = _sale_result(item, hidden, base)
            cumulative = 0.0
            prefix = {}
            for day in days:
                qty = max(0, int(outputs_by_day.get(day, {}).get(item, 0)
                                 or 0))
                if day == anchor:
                    qty += max(0, int(retained.get(item, 0) or 0))
                gained, book = _sale_result(item, qty, book)
                cumulative += gained
                prefix[day] = cumulative
                if qty > 0:
                    products_by_day.setdefault(day, set()).add(item)
            curves.append(cumulative)
            if hidden == capacity:
                worst_prefix = prefix
        if include_paired_value:
            final_costs.append(curves)
        for day in days:
            individual_prefix[day] += float(worst_prefix.get(day, 0.0))
    if include_paired_value:
        robust_future = (_allocation_dp(final_costs, capacity)
                         if final_costs else 0.0)
    else:
        robust_future = (individual_prefix[days[-1]] if days else 0.0)
    return {
        "anchor_day": anchor,
        "paired_revenue": float(current_value + robust_future),
        "current_cash": float(current_cash),
        "prefix_cash": individual_prefix,
        "future_products_by_day": products_by_day,
    }


def _available_slots(snap, include_next_land=False, reserve_inventory=False,
                     blocked_positions=()):
    unlocked = set(snap.me.unlocked)
    if include_next_land and econ.can_buy_land(len(snap.me.unlocked)):
        owned_extra = len(snap.me.unlocked) - 1
        unlocked.add(econ.LAND_ORDER[owned_extra])
    blocked = {tuple(pos) for pos in blocked_positions}
    slots = []
    for y, row in enumerate(snap.me.tiles):
        for x, tile in enumerate(row):
            pos = (x, y)
            if (not paths.productive_tile_allowed(snap, pos)
                    or pos in blocked):
                continue
            quadrant = paths.quadrant_of(x, y, snap.board)
            if quadrant not in unlocked:
                continue
            if tile is None or (tile == "LOCKED" and include_next_land):
                slots.append(pos)
    slots.sort(key=lambda pos: (paths.dist_to_shed(pos), pos))
    if reserve_inventory:
        committed = sum(max(0, int(qty or 0))
                        for qty in getattr(snap, "seeds", {}).values())
        committed += sum(max(0, int(snap.shed.get(kind, 0) or 0))
                         for kind in econ.ANIMALS)
        carried = (snap.carried() if hasattr(snap, "carried") else {})
        committed += sum(max(0, int(carried.get(kind, 0) or 0))
                         for kind in econ.ANIMALS)
        # Existing inventory will be placed on the nearest available slots by
        # the same deterministic task layer. New purchases may use only what
        # remains, so their distance bound is the suffix of this ordering.
        slots = slots[min(len(slots), committed):]
    return slots


def _greedy_branch(snap, fixed_orders, reserve, include_land,
                   reserve_inventory=False, shared_routes=False):
    slots = _available_slots(snap, include_land, reserve_inventory)
    shared_context = None
    if shared_routes:
        fixed_spend, initial_shed = _fixed_commitment(snap, fixed_orders)
        shared_context = (fixed_spend, initial_shed, _reserved_book(snap))
    if not slots:
        empty_cert = (certify_shared(
            snap, {}, slots, reserve=reserve, fixed_orders=fixed_orders,
            _context=shared_context,
        ) if shared_routes else certify(
            snap, {}, reserve, fixed_orders=fixed_orders,
        ))
        return [], empty_cert
    distance = max(paths.dist_to_shed(pos) for pos in slots)
    owned_extra = len(snap.me.unlocked) - 1
    land_cost = (float(econ.LAND_PRICES[owned_extra])
                 if include_land and econ.can_buy_land(
                     len(snap.me.unlocked))
                 else 0.0)
    counts = {}
    current = (certify_shared(
        snap, counts, slots, reserve, land_cost, fixed_orders, shared_context,
    ) if shared_routes else certify(
        snap, counts, reserve, distance, land_cost, fixed_orders,
    ))
    if not current.feasible:
        return [], current
    candidates = sorted(tuple(econ.CROPS) + tuple(econ.ANIMALS))
    while sum(counts.values()) < len(slots):
        best = None
        for item in candidates:
            if item in econ.CROPS and snap.step > econ.SEED_DEADLINE[item]:
                continue
            if item in econ.ANIMALS and snap.step > econ.ANIMAL_DEADLINE[item]:
                continue
            trial = dict(counts)
            trial[item] = trial.get(item, 0) + 1
            distinct = len(trial) + (1 if include_land else 0)
            if len(fixed_orders or ()) + distinct > econ.MAX_ORDERS:
                continue
            cert = (certify_shared(
                snap, trial, slots, reserve, land_cost, fixed_orders,
                shared_context,
            ) if shared_routes else certify(
                snap, trial, reserve, distance, land_cost, fixed_orders,
            ))
            if not cert.feasible:
                continue
            gain = cert.final_cash - current.final_cash
            key = (gain, cert.final_cash, -cert.upfront_spend, item)
            if best is None or key > best[0]:
                best = (key, trial, cert)
        if best is None or best[0][0] <= 1e-9:
            break
        _key, counts, current = best
    orders = []
    for kind in sorted(econ.ANIMALS):
        if counts.get(kind, 0):
            orders.append(["BUY_ANIMAL", kind, counts[kind]])
    for crop in sorted(econ.CROPS):
        if counts.get(crop, 0):
            orders.append(["BUY_SEED", crop, counts[crop]])
    if include_land and counts:
        orders.append(["BUY_LAND"])
    return orders, current


def invent_proposal(snap, fixed_orders=None, reserve=0.0,
                    reserve_inventory=False, shared_routes=False):
    """Invent the best of current-land and exact next-land greedy bundles."""
    arms = [_greedy_branch(snap, fixed_orders or [], reserve, False,
                           reserve_inventory, shared_routes)]
    owned_extra = len(snap.me.unlocked) - 1
    if econ.can_buy_land(len(snap.me.unlocked)):
        arms.append(_greedy_branch(snap, fixed_orders or [], reserve, True,
                                   reserve_inventory, shared_routes))
    feasible = [arm for arm in arms if arm[1].feasible]
    if not feasible:
        return [], arms[0][1]
    return max(feasible, key=lambda arm: (
        arm[1].final_cash, -arm[1].upfront_spend, -len(arm[0]), repr(arm[0])
    ))


def _orders_from_counts(counts, include_land):
    orders = []
    for kind in sorted(econ.ANIMALS):
        if counts.get(kind, 0):
            orders.append(["BUY_ANIMAL", kind, counts[kind]])
    for crop in sorted(econ.CROPS):
        if counts.get(crop, 0):
            orders.append(["BUY_SEED", crop, counts[crop]])
    if include_land and counts:
        orders.append(["BUY_LAND"])
    return orders


def _bounded_paired_branch(snap, fixed_orders, reserve, include_land,
                           reserve_inventory=True, blocked_positions=(),
                           phase_aligned=False, first_output_only=False,
                           exact_first_output=False,
                           joint_farm_prefix=False,
                           optional_continuation=False,
                           fertilizer_bridge=False,
                           exchange_repair=False,
                           adaptive_marginal=False,
                           stackelberg=False,
                           certificate_cache=None,
                           paired_context=None,
                           stackelberg_context=None,
                           allowed_items=None,
                           new_land_only=False):
    """One fixed singleton ranking followed by bounded exact marginal rays.

    This is a deterministic primal construction, not an exact portfolio
    optimiser.  It evaluates each legal asset singleton once, fixes that
    equation-derived order, then extends each asset ray only while the exact
    paired objective improves.  At most ``items + slots + items`` nonempty
    certificates are solved, independent of wall-clock time.
    """
    slots = _available_slots(
        snap, include_land, reserve_inventory, blocked_positions,
    )
    if new_land_only:
        # A land challenger must pay for and physically use the new quadrant.
        # Without this restriction an ``include_land`` arm can place its whole
        # portfolio on residual current land while still appending BUY_LAND,
        # which is feasible cash accounting but not a meaningful land action.
        unlocked = set(snap.me.unlocked)
        slots = [
            pos for pos in slots
            if paths.quadrant_of(pos[0], pos[1], snap.board) not in unlocked
        ]
    fixed_spend, initial_shed = _fixed_commitment(snap, fixed_orders)
    cash_context = (fixed_spend, initial_shed, _reserved_book(snap))
    paired_context = (paired_context if paired_context is not None else (
        _own_reserved_book(snap),
        _visible_output_schedule(snap, snap.opp),
        _guaranteed_town_drain_by_day(snap),
    ))
    owned_extra = len(snap.me.unlocked) - 1
    land_cost = (float(econ.LAND_PRICES[owned_extra])
                 if include_land and econ.can_buy_land(
                     len(snap.me.unlocked))
                 else 0.0)
    evaluations = 1
    def evaluate(candidate_counts):
        if stackelberg and candidate_counts:
            from whitebox import stackelberg as _stackelberg
            return _stackelberg.certify_unified(
                snap, candidate_counts, slots, reserve, land_cost,
                fixed_orders, cash_context,
                positions_by_item=None, context=stackelberg_context,
            )
        if optional_continuation and candidate_counts:
            return certify_optional_continuation(
                snap, candidate_counts, slots, reserve, land_cost,
                fixed_orders, cash_context, paired_objective=True,
                _paired_context=paired_context,
            )
        if joint_farm_prefix and candidate_counts:
            if certificate_cache is None:
                return certify_joint_farm_prefix(
                    snap, candidate_counts, slots, reserve, land_cost,
                    fixed_orders, cash_context, paired_objective=True,
                    _paired_context=paired_context,
                )
            key = (
                "joint_farm_prefix",
                tuple(sorted((item, int(qty))
                             for item, qty in candidate_counts.items()
                             if int(qty) > 0)),
                tuple(slots), float(land_cost), bool(phase_aligned),
                bool(fertilizer_bridge),
            )
            base = certificate_cache.get(key)
            if base is None:
                base = certify_joint_farm_prefix(
                    snap, candidate_counts, slots, 0.0, land_cost,
                    fixed_orders, cash_context, paired_objective=True,
                    _paired_context=paired_context,
                )
                certificate_cache[key] = base
            cert = copy.copy(base)
            if not cert.feasible:
                return cert
            upfront_cash = (float(snap.me.money) - float(cash_context[0])
                            - float(cert.upfront_spend))
            if upfront_cash < float(reserve) - 1e-9:
                return cert.reject("upfront_cash", upfront_cash)
            if cert.minimum_cash < float(reserve) - 1e-9:
                return cert.reject("bridge_cash", cert.minimum_cash)
            return cert
        if certificate_cache is None:
            return certify_shared(
                snap, candidate_counts, slots, reserve, land_cost,
                fixed_orders, cash_context, paired_objective=True,
                _paired_context=paired_context, phase_aligned=phase_aligned,
                first_output_only=first_output_only,
                exact_first_output=exact_first_output,
                credit_fertilizer=fertilizer_bridge,
            )
        # HIRE orders have no inventory/cash effect inside the future
        # certificate; their exact Fibonacci bill is represented by ``reserve``.
        # Across crew arms, a positioned portfolio's physical route, output and
        # cash trajectory is therefore identical.  Solve it once at reserve 0,
        # then apply each arm's reserve inequality to the recorded exact
        # pre-output minimum cash.  The cache is solve-local and the key is the
        # full positioned universe, never a seed/opponent identity.
        key = (
            tuple(sorted((item, int(qty))
                         for item, qty in candidate_counts.items()
                         if int(qty) > 0)),
            tuple(slots), float(land_cost), bool(phase_aligned),
            bool(fertilizer_bridge),
        )
        base = certificate_cache.get(key)
        if base is None:
            base = certify_shared(
                snap, candidate_counts, slots, 0.0, land_cost,
                fixed_orders, cash_context, paired_objective=True,
                _paired_context=paired_context, phase_aligned=phase_aligned,
                first_output_only=first_output_only,
                exact_first_output=exact_first_output,
                credit_fertilizer=fertilizer_bridge,
            )
            certificate_cache[key] = base
        cert = copy.copy(base)
        if not cert.feasible:
            return cert
        upfront_cash = (float(snap.me.money) - float(cash_context[0])
                        - float(cert.upfront_spend))
        if upfront_cash < float(reserve) - 1e-9:
            return cert.reject("upfront_cash", upfront_cash)
        if cert.minimum_cash < float(reserve) - 1e-9:
            return cert.reject("bridge_cash", cert.minimum_cash)
        return cert

    current = evaluate({})
    if not current.feasible or not slots:
        current.evaluations = evaluations
        return [], current

    universe = (tuple(econ.CROPS) + tuple(econ.ANIMALS)
                if allowed_items is None else tuple(allowed_items))
    legal = []
    for item in sorted(universe):
        if item in econ.CROPS and snap.step > econ.SEED_DEADLINE[item]:
            continue
        if item in econ.ANIMALS and snap.step > econ.ANIMAL_DEADLINE[item]:
            continue
        distinct = 1 + (1 if include_land else 0)
        if len(fixed_orders or ()) + distinct > econ.MAX_ORDERS:
            continue
        cert = evaluate({item: 1})
        evaluations += 1
        if cert.feasible:
            gain = cert.paired_value - current.paired_value
            if gain > 1e-9:
                legal.append((gain, cert.paired_value,
                              -cert.upfront_spend, item))
    legal.sort(reverse=True)

    counts = {}
    if adaptive_marginal:
        legal_items = [row[-1] for row in legal]
        while sum(counts.values()) < len(slots):
            best = None
            for item in legal_items:
                trial = dict(counts)
                trial[item] = trial.get(item, 0) + 1
                distinct = len(trial) + (1 if include_land else 0)
                if len(fixed_orders or ()) + distinct > econ.MAX_ORDERS:
                    continue
                cert = evaluate(trial)
                evaluations += 1
                if not cert.feasible:
                    continue
                key = (cert.paired_value - current.paired_value,
                       cert.paired_value, cert.final_cash,
                       -cert.upfront_spend, item)
                if best is None or key > best[0]:
                    best = (key, trial, cert)
            if best is None or best[0][0] <= 1e-9:
                break
            _key, counts, current = best
    else:
        for _singleton_gain, _value, _spend, item in legal:
            while sum(counts.values()) < len(slots):
                trial = dict(counts)
                trial[item] = trial.get(item, 0) + 1
                distinct = len(trial) + (1 if include_land else 0)
                if len(fixed_orders or ()) + distinct > econ.MAX_ORDERS:
                    break
                cert = evaluate(trial)
                evaluations += 1
                if (not cert.feasible
                        or cert.paired_value <= current.paired_value + 1e-9):
                    break
                counts, current = trial, cert

    if exchange_repair and counts:
        # The ray constructor above is deliberately cheap, but its first
        # singleton ranking can lock an entire farm into one asset: "the first
        # COW beats the first SHEEP" does not imply that the twentieth COW
        # beats the first SHEEP after nonlinear market saturation.  Search
        # every one-unit replacement once, select the steepest exact direction,
        # then evaluate the complete finite integer line along that direction.
        # The work bound is items^2 + physical slots and contains no wall clock,
        # replay label, target mix or fitted coefficient.
        legal_items = [
            item for item in sorted(universe)
            if not (item in econ.CROPS
                    and snap.step > econ.SEED_DEADLINE[item])
            and not (item in econ.ANIMALS
                     and snap.step > econ.ANIMAL_DEADLINE[item])
        ]
        direction = None
        best_one = current
        best_one_counts = dict(counts)
        for remove in sorted(counts):
            if counts.get(remove, 0) <= 0:
                continue
            for add in legal_items:
                if add == remove:
                    continue
                trial = dict(counts)
                trial[remove] -= 1
                if trial[remove] <= 0:
                    trial.pop(remove, None)
                trial[add] = trial.get(add, 0) + 1
                distinct = len(trial) + (1 if include_land else 0)
                if len(fixed_orders or ()) + distinct > econ.MAX_ORDERS:
                    continue
                cert = evaluate(trial)
                evaluations += 1
                key = (cert.paired_value, cert.final_cash,
                       -cert.upfront_spend, remove, add)
                incumbent = (best_one.paired_value, best_one.final_cash,
                             -best_one.upfront_spend,
                             direction[0] if direction else "",
                             direction[1] if direction else "")
                if cert.feasible and key > incumbent:
                    direction = (remove, add)
                    best_one, best_one_counts = cert, trial

        if (direction is not None
                and best_one.paired_value > current.paired_value + 1e-9):
            remove, add = direction
            line_best = best_one
            line_counts = best_one_counts
            for quantity in range(2, int(counts.get(remove, 0)) + 1):
                trial = dict(counts)
                trial[remove] -= quantity
                if trial[remove] <= 0:
                    trial.pop(remove, None)
                trial[add] = trial.get(add, 0) + quantity
                cert = evaluate(trial)
                evaluations += 1
                if (cert.feasible
                        and (cert.paired_value, cert.final_cash,
                             -cert.upfront_spend, repr(sorted(trial.items())))
                        > (line_best.paired_value, line_best.final_cash,
                           -line_best.upfront_spend,
                           repr(sorted(line_counts.items())))):
                    line_best, line_counts = cert, trial
            counts, current = line_counts, line_best
    current.evaluations = evaluations
    return _orders_from_counts(counts, include_land), current


def invent_paired_proposal(snap, fixed_orders=None, reserve=0.0,
                           reserve_inventory=True, blocked_positions=(),
                           phase_aligned=False, fertilizer_bridge=False,
                           exchange_repair=False,
                           adaptive_marginal=False,
                           joint_farm_prefix=False,
                           stackelberg=False,
                           recertify_stackelberg_arms=False,
                           activated_land_reinvestment=False,
                           full_service_continuation=False,
                           crop_only_land_arm=False,
                           robust_crop_land_gate=False,
                           certificate_cache=None, paired_context=None,
                           stackelberg_context=None, allowed_items=None,
                           allow_land=True):
    """Best exact no-land/next-land arm under bounded paired construction."""
    fixed = fixed_orders or []
    arms = [_bounded_paired_branch(
        snap, fixed, reserve, False, reserve_inventory, blocked_positions,
        phase_aligned, fertilizer_bridge=fertilizer_bridge,
        exchange_repair=exchange_repair,
        adaptive_marginal=adaptive_marginal,
        joint_farm_prefix=joint_farm_prefix,
        stackelberg=stackelberg,
        certificate_cache=certificate_cache,
        paired_context=paired_context,
        stackelberg_context=stackelberg_context,
        allowed_items=allowed_items,
    )]
    owned_extra = len(snap.me.unlocked) - 1
    if allow_land and econ.can_buy_land(len(snap.me.unlocked)):
        arms.append(_bounded_paired_branch(
            snap, fixed, reserve, True, reserve_inventory, blocked_positions,
            phase_aligned, fertilizer_bridge=fertilizer_bridge,
            exchange_repair=exchange_repair,
            adaptive_marginal=adaptive_marginal,
            joint_farm_prefix=joint_farm_prefix,
            stackelberg=stackelberg,
            certificate_cache=certificate_cache,
            paired_context=paired_context,
            stackelberg_context=stackelberg_context,
            allowed_items=allowed_items,
        ))
        crop_land_arms = []
        if crop_only_land_arm and owned_extra >= 1:
            # Crops have a finite first-output abandonment/rotation endpoint;
            # animals create a durable FEED+CARE obligation.  Keep this as a
            # separate action class so an otherwise valuable crop expansion
            # is not hidden by the ordinary land ray's animal maximizer.  The
            # first expansion remains under the already validated ordinary
            # arm; this challenger isolates the missing third/fourth-quadrant
            # decision without changing the opening action universe.
            for crop in sorted(econ.CROPS):
                crop_land_arms.append(_bounded_paired_branch(
                    snap, fixed, reserve, True, reserve_inventory,
                    blocked_positions, phase_aligned,
                    fertilizer_bridge=fertilizer_bridge,
                    exchange_repair=exchange_repair,
                    adaptive_marginal=adaptive_marginal,
                    joint_farm_prefix=joint_farm_prefix,
                    stackelberg=stackelberg,
                    certificate_cache=certificate_cache,
                    paired_context=paired_context,
                    stackelberg_context=stackelberg_context,
                    allowed_items=(crop,),
                    new_land_only=True,
                ))
            arms.extend(crop_land_arms)
            if robust_crop_land_gate:
                # Compare the incumbent current-land universe directly with
                # each crop-specific new-land ray.  The ordinary all-asset
                # land ray is deliberately outside this isolated gate because
                # its durable animal service was V119's confounder.
                arms = [arms[0]] + crop_land_arms
    if recertify_stackelberg_arms or (
            robust_crop_land_gate and crop_land_arms):
        from whitebox import stackelberg as _stackelberg
        fixed_spend, initial_shed = _fixed_commitment(snap, fixed)
        cash_context = (fixed_spend, initial_shed, _reserved_book(snap))
        recertified = []
        for orders, proposal_cert in arms:
            counts = {}
            for order in orders:
                if (len(order) >= 3
                        and order[0] in ("BUY_SEED", "BUY_ANIMAL")):
                    counts[str(order[1])] = max(0, int(order[2] or 0))
            if not counts:
                recertified.append((orders, proposal_cert))
                continue
            robust = _stackelberg.certify_unified(
                snap, counts,
                sorted(
                    {tuple(pos) for positions in
                     proposal_cert.positions_by_item.values()
                     for pos in positions},
                    key=lambda pos: (paths.dist_to_shed(pos), pos),
                ),
                reserve=reserve, land_cost=proposal_cert.land_cost,
                fixed_orders=fixed, cash_context=cash_context,
                positions_by_item=proposal_cert.positions_by_item,
                context=stackelberg_context,
                activated_land_reinvestment=activated_land_reinvestment,
                full_service_continuation=full_service_continuation,
            )
            robust.evaluations = proposal_cert.evaluations
            recertified.append((orders, robust))
        arms = recertified
    feasible = [arm for arm in arms if arm[1].feasible]
    if not feasible:
        return [], arms[0][1]
    return max(feasible, key=lambda arm: (
        arm[1].paired_value, arm[1].final_cash,
        -arm[1].upfront_spend, -len(arm[0]), repr(arm[0]),
    ))


def invent_first_output_proposal(snap, fixed_orders=None, reserve=0.0,
                                 blocked_positions=()):
    """Best bounded portfolio whose cash path is proved to first outputs."""
    fixed = fixed_orders or []
    arms = [_bounded_paired_branch(
        snap, fixed, reserve, False, True, blocked_positions,
        first_output_only=True,
    )]
    owned_extra = len(snap.me.unlocked) - 1
    if econ.can_buy_land(len(snap.me.unlocked)):
        arms.append(_bounded_paired_branch(
            snap, fixed, reserve, True, True, blocked_positions,
            first_output_only=True,
        ))
    feasible = [arm for arm in arms if arm[1].feasible]
    if not feasible:
        return [], arms[0][1]
    return max(feasible, key=lambda arm: (
        arm[1].paired_value, arm[1].final_cash,
        -arm[1].upfront_spend, -len(arm[0]), repr(arm[0]),
    ))


def invent_exact_first_output_proposal(snap, fixed_orders=None, reserve=0.0,
                                       blocked_positions=()):
    """Bounded V99 portfolio under exact earliest harvestable quantities."""
    fixed = fixed_orders or []
    arms = [_bounded_paired_branch(
        snap, fixed, reserve, False, True, blocked_positions,
        exact_first_output=True,
    )]
    owned_extra = len(snap.me.unlocked) - 1
    if econ.can_buy_land(len(snap.me.unlocked)):
        arms.append(_bounded_paired_branch(
            snap, fixed, reserve, True, True, blocked_positions,
            exact_first_output=True,
        ))
    feasible = [arm for arm in arms if arm[1].feasible]
    if not feasible:
        return [], arms[0][1]
    return max(feasible, key=lambda arm: (
        arm[1].paired_value, arm[1].final_cash,
        -arm[1].upfront_spend, -len(arm[0]), repr(arm[0]),
    ))


def invent_joint_farm_prefix_proposal(snap, fixed_orders=None, reserve=0.0,
                                      blocked_positions=()):
    """V100 bounded exact prefix sharing dated visible-farm service routes."""
    fixed = fixed_orders or []
    arms = [_bounded_paired_branch(
        snap, fixed, reserve, False, True, blocked_positions,
        joint_farm_prefix=True,
    )]
    owned_extra = len(snap.me.unlocked) - 1
    if econ.can_buy_land(len(snap.me.unlocked)):
        arms.append(_bounded_paired_branch(
            snap, fixed, reserve, True, True, blocked_positions,
            joint_farm_prefix=True,
        ))
    feasible = [arm for arm in arms if arm[1].feasible]
    if not feasible:
        return [], arms[0][1]
    return max(feasible, key=lambda arm: (
        arm[1].paired_value, arm[1].final_cash,
        -arm[1].upfront_spend, -len(arm[0]), repr(arm[0]),
    ))


def invent_optional_continuation_proposal(snap, fixed_orders=None,
                                          reserve=0.0,
                                          blocked_positions=()):
    """V101 bounded portfolio under the two exact continuation endpoints."""
    fixed = fixed_orders or []
    arms = [_bounded_paired_branch(
        snap, fixed, reserve, False, True, blocked_positions,
        optional_continuation=True,
    )]
    owned_extra = len(snap.me.unlocked) - 1
    if econ.can_buy_land(len(snap.me.unlocked)):
        arms.append(_bounded_paired_branch(
            snap, fixed, reserve, True, True, blocked_positions,
            optional_continuation=True,
        ))
    feasible = [arm for arm in arms if arm[1].feasible]
    if not feasible:
        return [], arms[0][1]
    return max(feasible, key=lambda arm: (
        arm[1].paired_value, arm[1].final_cash,
        -arm[1].upfront_spend, -len(arm[0]), repr(arm[0]),
    ))


def invent_exchange_proposal(snap, fixed_orders=None, reserve=0.0,
                             reserve_inventory=True):
    """Correct one fixed-ray lock-in by an exact steepest exchange line.

    Every one-unit remove/add direction is evaluated once.  If any direction
    improves the paired certificate, all integer quantities along only that
    steepest direction are evaluated and the best feasible point is returned.
    The work bound is ``item_types^2 + physical_slots`` and is independent of
    machine speed; this is a one-neighbourhood primal correction, not a claim
    of global portfolio optimality.
    """
    fixed = fixed_orders or []
    proposal, current = invent_paired_proposal(
        snap, fixed, reserve, reserve_inventory,
    )
    counts = Counter()
    include_land = False
    for order in proposal:
        if not order:
            continue
        if order[0] == "BUY_LAND":
            include_land = True
        elif len(order) >= 3 and order[0] in ("BUY_SEED", "BUY_ANIMAL"):
            counts[order[1]] += max(0, int(order[2] or 0))
    if not counts:
        return proposal, current

    slots = _available_slots(snap, include_land, reserve_inventory)
    fixed_spend, initial_shed = _fixed_commitment(snap, fixed)
    cash_context = (fixed_spend, initial_shed, _reserved_book(snap))
    paired_context = (
        _own_reserved_book(snap),
        _visible_output_schedule(snap, snap.opp),
        _guaranteed_town_drain_by_day(snap),
    )
    owned_extra = len(snap.me.unlocked) - 1
    land_cost = (float(econ.LAND_PRICES[owned_extra])
                 if include_land and econ.can_buy_land(
                     len(snap.me.unlocked))
                 else 0.0)
    legal = []
    for item in sorted(tuple(econ.CROPS) + tuple(econ.ANIMALS)):
        if item in econ.CROPS and snap.step > econ.SEED_DEADLINE[item]:
            continue
        if item in econ.ANIMALS and snap.step > econ.ANIMAL_DEADLINE[item]:
            continue
        legal.append(item)

    evaluations = 0
    best_direction = None
    for remove in sorted(counts):
        if counts[remove] <= 0:
            continue
        for add in legal:
            if add == remove:
                continue
            trial = dict(counts)
            trial[remove] -= 1
            if trial[remove] <= 0:
                del trial[remove]
            trial[add] = trial.get(add, 0) + 1
            distinct = len(trial) + (1 if include_land else 0)
            if len(fixed) + distinct > econ.MAX_ORDERS:
                continue
            cert = certify_shared(
                snap, trial, slots, reserve, land_cost, fixed,
                cash_context, paired_objective=True,
                _paired_context=paired_context,
            )
            evaluations += 1
            if not cert.feasible:
                continue
            gain = cert.paired_value - current.paired_value
            key = (gain, cert.paired_value, -cert.upfront_spend,
                   add, remove)
            if best_direction is None or key > best_direction[0]:
                best_direction = (key, remove, add, trial, cert)

    if best_direction is None or best_direction[0][0] <= 1e-9:
        current.exchange_evaluations = evaluations
        return proposal, current

    _key, remove, add, best_counts, best_cert = best_direction
    for quantity in range(2, counts[remove] + 1):
        trial = dict(counts)
        trial[remove] -= quantity
        if trial[remove] <= 0:
            del trial[remove]
        trial[add] = trial.get(add, 0) + quantity
        distinct = len(trial) + (1 if include_land else 0)
        if len(fixed) + distinct > econ.MAX_ORDERS:
            continue
        cert = certify_shared(
            snap, trial, slots, reserve, land_cost, fixed,
            cash_context, paired_objective=True,
            _paired_context=paired_context,
        )
        evaluations += 1
        if not cert.feasible:
            continue
        key = (cert.paired_value, cert.final_cash,
               -cert.upfront_spend, repr(sorted(trial.items())))
        best_key = (best_cert.paired_value, best_cert.final_cash,
                    -best_cert.upfront_spend,
                    repr(sorted(best_counts.items())))
        if key > best_key:
            best_counts, best_cert = trial, cert

    best_cert.exchange_evaluations = evaluations
    return _orders_from_counts(best_counts, include_land), best_cert
