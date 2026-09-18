"""Finite transparent Stackelberg value for productive capital.

This module joins three quantities which earlier experiments valued in
isolation:

* the exact daily cash/labour certificate for standing plus new capital;
* one executable post-output crop reinvestment option funded by realised cash;
* a finite opponent best-response set whose assets, feed and daily hires are
  paid by the opponent before their output can affect the shared market.

The response set is generated from public state.  For each legal crop/animal
direction it enumerates every currently affordable quantity on currently
unlocked empty tiles, proves the combined standing/new workload, and retains
the quantity with the greatest exact standalone incremental profit.  The
leader then chooses the endpoint/reinvestment branch whose worst exact market
margin over those named responses is largest.  There is no probability,
identity, replay statistic, fitted coefficient, target count or hidden state.
"""

import copy
from collections import Counter, defaultdict
from dataclasses import dataclass
from types import SimpleNamespace

from whitebox import cashflow, econ, paths


@dataclass(frozen=True)
class Response:
    """One certified public-state opponent response direction."""

    name: str
    item: str = ""
    quantity: int = 0
    cost: float = 0.0
    outputs: tuple = ()

    def schedule(self):
        return {
            int(day): {str(item): int(qty) for item, qty in products}
            for day, products in self.outputs
        }


@dataclass(frozen=True)
class Reinvestment:
    """One feasible next-stage crop purchase funded after first output."""

    name: str
    cost: float = 0.0
    outputs: tuple = ()
    purchase_day: int = -1
    order: tuple = ()
    positions_by_item: tuple = ()
    routes_by_day: tuple = ()
    hire_phases_by_day: tuple = ()
    activates_land: bool = False

    def schedule(self):
        return {
            int(day): {str(item): int(qty) for item, qty in products}
            for day, products in self.outputs
        }

    def positions(self):
        return {
            str(item): tuple(tuple(pos) for pos in positions)
            for item, positions in self.positions_by_item
        }

    def routes(self):
        return {
            int(day): tuple(
                tuple((tuple(pos), int(ops)) for pos, ops in route)
                for route in routes
            )
            for day, routes in self.routes_by_day
        }

    def hire_phases(self):
        return {
            int(day): tuple(int(qty) for qty in phases)
            for day, phases in self.hire_phases_by_day
        }


def _freeze_schedule(outputs_by_day):
    return tuple(
        (int(day), tuple(sorted(
            (str(item), max(0, int(qty or 0)))
            for item, qty in products.items() if int(qty or 0) > 0
        )))
        for day, products in sorted(outputs_by_day.items())
        if any(int(qty or 0) > 0 for qty in products.values())
    )


def _merge_schedules(*schedules):
    out = defaultdict(Counter)
    for schedule in schedules:
        for day, products in (schedule or {}).items():
            for item, qty in products.items():
                if item in econ.SELLABLE and int(qty or 0) > 0:
                    out[int(day)][str(item)] += int(qty)
    return {day: dict(products) for day, products in out.items()}


def _public_actor_snapshot(snap, farm, other):
    """Public-only planning snapshot for one player.

    Private shed/seeds are deliberately empty.  Consequently every retained
    response is feasible from public money without assuming hidden resources;
    hidden inventory can only make the real opponent stronger.
    """
    actor = SimpleNamespace(
        step=int(snap.step), day=int(snap.day), hour=int(snap.hour),
        days_left=int(getattr(snap, "days_left", max(0, 29 - snap.day))),
        me=farm, opp=other, shed={}, seeds={},
        inventories=[{} for _ in range(max(1, int(farm.workers)))],
        market_inv=dict(snap.market_inv), board=int(snap.board),
        shed_used=0, shops=tuple(getattr(snap, "shops", ())),
        config=getattr(snap, "config", None),
    )
    actor.allow_productive_shed_tiles = bool(getattr(
        snap, "allow_productive_shed_tiles", False,
    ))
    actor.carried = lambda: {}
    return actor


def _first_output_horizon(snap, counts, phase_aligned=False):
    start = int(snap.day) if phase_aligned else int(snap.day) + 1
    horizons = []
    for item, qty in counts.items():
        if int(qty or 0) <= 0:
            continue
        events = (cashflow._crop_event_days(item, start)
                  if item in econ.CROPS
                  else cashflow._animal_event_days(item, start))
        if not events:
            return None
        horizons.append(int(events[0]) + 1)
    return max(horizons) if horizons else start


def _deferred_first_output_horizon(snap):
    """Common MPC horizon for every legal tomorrow-capital direction."""
    purchase_day = int(snap.day) + 1
    start_day = purchase_day + 1
    horizons = []
    for item in sorted(tuple(econ.CROPS) + tuple(econ.ANIMALS)):
        deadline = (econ.SEED_DEADLINE[item] if item in econ.CROPS
                    else econ.ANIMAL_DEADLINE[item])
        if purchase_day * econ.TURNS_PER_DAY > int(deadline):
            continue
        events = (cashflow._crop_event_days(item, start_day)
                  if item in econ.CROPS
                  else cashflow._animal_event_days(item, start_day))
        if events:
            horizons.append(int(events[0]) + 1)
    return min(cashflow.LAST_DAY, max(horizons)) if horizons else None


def _incremental_operating_cost(combined, baseline):
    return float(combined.operating_cost) - float(baseline.operating_cost)


def _response_margin(snap, own_outputs, own_cost, response,
                     opponent_baseline=None, drains=None):
    """Exact incremental terminal margin for one certified response.

    At each dated phase the actual book processes our sale and the opponent's
    standing-plus-response sale in per-unit lockstep.  A second book processes
    only the opponent's standing counterfactual.  Therefore

    ``own revenue - joint opponent revenue + baseline opponent revenue``

    is the exact revenue-margin increment.  We subtract our certified cost and
    add the opponent response cost because that cash leaves their final bank.
    """
    baseline = (opponent_baseline if opponent_baseline is not None else
                cashflow._visible_output_schedule(snap, snap.opp))
    response_outputs = response.schedule()
    own = _merge_schedules(own_outputs)
    joint_book = {
        item: int(snap.market_inv.get(item, econ.MARKET_I0)
                  or econ.MARKET_I0)
        for item in econ.SELLABLE
    }
    baseline_book = dict(joint_book)
    drains = (drains if drains is not None else
              cashflow._guaranteed_town_drain_by_day(snap))
    margin = -float(own_cost) + float(response.cost)
    days = sorted(set(own) | set(baseline) | set(response_outputs))
    for day in days:
        for item in econ.SELLABLE:
            drain = max(0, int(drains.get(day, {}).get(item, 0) or 0))
            joint_book[item] = max(0, joint_book[item] - drain)
            baseline_book[item] = max(0, baseline_book[item] - drain)
        base_day = Counter(baseline.get(day, {}))
        response_day = Counter(response_outputs.get(day, {}))
        own_day = Counter(own.get(day, {}))
        for item in sorted(set(base_day) | set(response_day) | set(own_day)):
            ours = max(0, int(own_day.get(item, 0)))
            base_qty = max(0, int(base_day.get(item, 0)))
            theirs = base_qty + max(0, int(response_day.get(item, 0)))
            own_revenue, opponent_revenue, joint_book[item] = (
                cashflow._lockstep_sale_result(
                    item, ours, theirs, joint_book[item],
                )
            )
            baseline_revenue, baseline_book[item] = cashflow._sale_result(
                item, base_qty, baseline_book[item],
            )
            margin += own_revenue - opponent_revenue + baseline_revenue
    return float(margin)


def _standing_response_margin(snap, own_outputs, own_cost, response,
                              opponent_baseline=None, drains=None,
                              own_baseline=None):
    """Absolute game margin with existing and new output in one book.

    ``_response_margin`` is the historical incremental-capital equation: it
    puts only the candidate output into our side of the shared book.  That is
    exact on an empty farm, but it makes a ninth COW look like a first COW once
    the farm already owns eight.  This opt-in counterpart starts from the
    public full-service output schedule of our standing assets, merges the
    candidate schedule, and prices both players in the same dated lockstep.

    Response and leader costs retain their real signs.  No target herd, replay
    statistic or fitted saturation coefficient enters the calculation.
    """
    standing = own_baseline if own_baseline is not None else {}
    own = _merge_schedules(standing, own_outputs)
    baseline = (opponent_baseline if opponent_baseline is not None else
                cashflow._visible_output_schedule(snap, snap.opp))
    response_outputs = response.schedule()
    book = {
        item: int(snap.market_inv.get(item, econ.MARKET_I0)
                  or econ.MARKET_I0)
        for item in econ.SELLABLE
    }
    drains = (drains if drains is not None else
              cashflow._guaranteed_town_drain_by_day(snap))
    margin = -float(own_cost) + float(response.cost)
    days = sorted(set(own) | set(baseline) | set(response_outputs))
    for day in days:
        for item in econ.SELLABLE:
            drain = max(0, int(drains.get(day, {}).get(item, 0) or 0))
            book[item] = max(0, book[item] - drain)
        theirs = Counter(baseline.get(day, {}))
        theirs.update(response_outputs.get(day, {}))
        ours = Counter(own.get(day, {}))
        for item in sorted(set(ours) | set(theirs)):
            own_revenue, opponent_revenue, book[item] = (
                cashflow._lockstep_sale_result(
                    item,
                    max(0, int(ours.get(item, 0))),
                    max(0, int(theirs.get(item, 0))),
                    book[item],
                )
            )
            margin += own_revenue - opponent_revenue
    return float(margin)


def _context_response_margin(snap, own_outputs, own_cost, response, context):
    """Dispatch one named response through the context's explicit equation."""
    if context.get("include_own_standing_book", False):
        return _standing_response_margin(
            snap, own_outputs, own_cost, response,
            context.get("opponent_baseline", {}), context.get("drains"),
            context.get("own_baseline", {}),
        )
    return _response_margin(
        snap, own_outputs, own_cost, response,
        context.get("opponent_baseline", {}), context.get("drains"),
    )


def finite_public_responses(snap, opponent_baseline=None, drains=None,
                            full_continuation=False,
                            mixed_continuation=False,
                            complete_products=(),
                            staged_reinvestment=False,
                            staged_response_cache=None,
                            staged_land_reinvestment=False,
                            staged_mixed_reinvestment=False):
    """Return a finite paid response set from public engine constraints.

    The default historical arm closes each response at first output.  The
    opt-in full-continuation arm also prices the minimum-service path through
    every remaining base output, then retains the more profitable paid
    endpoint for that quantity.  This prevents a COW response from being
    represented by one MILK unit when it can legally produce all season.  By
    default one standalone-best quantity is retained per asset direction; for
    a product named in ``complete_products`` every feasible endpoint/quantity
    is retained so the follower quantity can depend on the leader candidate.
    """
    no_response = Response("NO_RESPONSE")
    farm = getattr(snap, "opp", None)
    if (farm is None or not hasattr(farm, "tiles")
            or not hasattr(farm, "unlocked") or not hasattr(farm, "workers")):
        return (no_response,)
    actor = _public_actor_snapshot(snap, farm, snap.me)
    slots = cashflow._available_slots(actor, reserve_inventory=False)
    if not slots or float(farm.money) <= 0.0:
        return (no_response,)

    baseline_outputs = (opponent_baseline if opponent_baseline is not None else
                        cashflow._visible_output_schedule(snap, snap.opp))
    drains = (drains if drains is not None else
              cashflow._guaranteed_town_drain_by_day(snap))
    baseline_cache = {}
    complete_products = frozenset(str(item) for item in complete_products)
    chosen = []
    staged_best = {}
    staged_cache_key = (
        "responses", bool(staged_land_reinvestment),
        bool(staged_mixed_reinvestment),
    )
    cached_staged = (
        staged_response_cache.get(staged_cache_key)
        if staged_reinvestment and staged_response_cache is not None
        else None
    )
    generate_staged = bool(
        staged_reinvestment and cached_staged is None
    )
    for item in sorted(tuple(econ.CROPS) + tuple(econ.ANIMALS)):
        deadline = (econ.SEED_DEADLINE[item] if item in econ.CROPS
                    else econ.ANIMAL_DEADLINE[item])
        if int(snap.step) > int(deadline):
            continue
        unit_cost = float(econ.CROPS[item]["seed"] if item in econ.CROPS
                          else econ.ANIMALS[item]["cost"])
        if unit_cost <= 0.0:
            continue
        cap = min(len(slots), int(float(farm.money) // unit_cost))
        best = None
        best_first = None
        direction = []
        for quantity in range(1, cap + 1):
            counts = {item: quantity}
            horizon = _first_output_horizon(actor, counts)
            if horizon is None:
                break
            positions = {item: slots[:quantity]}
            endpoints = []
            combined = cashflow.certify_shared(
                actor, counts, slots[:quantity], reserve=0.0,
                positions_by_item=positions, exact_first_output=True,
                visible_survival_horizon=horizon,
            )
            if combined.feasible:
                endpoints.append(("", horizon, combined, True))
            if full_continuation:
                full = cashflow.certify_shared(
                    actor, counts, slots[:quantity], reserve=0.0,
                    positions_by_item=positions, minimal_full_output=True,
                    visible_survival_horizon=cashflow.LAST_DAY,
                )
                if full.feasible:
                    endpoints.append((
                        "_FULL", cashflow.LAST_DAY, full, False,
                    ))
            for suffix, endpoint_horizon, endpoint, first_only in endpoints:
                cache_key = (int(endpoint_horizon), bool(first_only))
                baseline = baseline_cache.get(cache_key)
                if baseline is None:
                    baseline = cashflow.certify_shared(
                        actor, {}, (), reserve=0.0,
                        exact_first_output=first_only,
                        minimal_full_output=not first_only,
                        visible_survival_horizon=endpoint_horizon,
                        enforce_bridge_cash=False,
                    )
                    baseline_cache[cache_key] = baseline
                operating = (
                    _incremental_operating_cost(endpoint, baseline)
                    if baseline.feasible else endpoint.operating_cost
                )
                cost = float(endpoint.upfront_spend) + float(operating)
                response = Response(
                    name=f"BUY_{item}_{quantity}{suffix}", item=item,
                    quantity=quantity, cost=cost,
                    outputs=_freeze_schedule(endpoint.outputs_by_day),
                )
                direction.append(response)
                # With no own action, the negative margin is exactly the
                # opponent's incremental profit over their standing baseline.
                payoff = _response_margin(
                    snap, {}, 0.0, response, baseline_outputs, drains,
                )
                key = (-payoff, -cost, -quantity, response.name)
                if best is None or key > best[0]:
                    best = (key, response)
                if first_only and (best_first is None
                                   or key > best_first[0]):
                    best_first = (key, response, endpoint)
        if (generate_staged and item in econ.CROPS
                and not bool(econ.CROPS[item]["ongoing"])
                and best_first is not None):
            # The online finite response uses an explicit two-level policy:
            # first choose this crop direction's exact standalone maximizer,
            # then enumerate every feasible paid animal continuation from its
            # realised cash.  Restricting the bridge to one-shot crops closes
            # the first workload and releases only harvested public positions;
            # no unpriced standing crop service survives into stage two.
            _first_key, first_response, first_endpoint = best_first
            for continuation in feasible_output_funded_capital(
                    actor, first_endpoint, reserve=0.0,
                    full_continuation=True,
                    target_items=tuple(econ.ANIMALS),
                    include_land=staged_land_reinvestment):
                if not continuation.order:
                    continue
                target = str(continuation.order[1])
                staged_outputs = _merge_schedules(
                    first_endpoint.outputs_by_day,
                    continuation.schedule(),
                )
                staged = Response(
                    name=(f"{first_response.name}_THEN_"
                          f"{continuation.name}"),
                    item=f"{item}->{target}",
                    quantity=(int(first_response.quantity)
                              + int(continuation.order[2])),
                    cost=(float(first_response.cost)
                          + float(continuation.cost)),
                    outputs=_freeze_schedule(staged_outputs),
                )
                staged_payoff = _response_margin(
                    snap, {}, 0.0, staged,
                    baseline_outputs, drains,
                )
                staged_key = (
                    -staged_payoff, -float(staged.cost),
                    -int(staged.quantity), staged.name,
                )
                direction_key = (str(item), target)
                incumbent = staged_best.get(direction_key)
                if incumbent is None or staged_key > incumbent[0]:
                    staged_best[direction_key] = (
                        staged_key, staged,
                    )
            if staged_mixed_reinvestment:
                for continuation in feasible_output_funded_mixed(
                        actor, first_endpoint, reserve=0.0):
                    if not continuation.order:
                        continue
                    crop = str(continuation.order[1])
                    animal = str(continuation.order[3])
                    quantity = (int(continuation.order[2])
                                + int(continuation.order[4]))
                    staged_outputs = _merge_schedules(
                        first_endpoint.outputs_by_day,
                        continuation.schedule(),
                    )
                    staged = Response(
                        name=(f"{first_response.name}_THEN_"
                              f"{continuation.name}"),
                        item=f"{item}->{crop}+{animal}",
                        quantity=(int(first_response.quantity) + quantity),
                        cost=(float(first_response.cost)
                              + float(continuation.cost)),
                        outputs=_freeze_schedule(staged_outputs),
                    )
                    staged_payoff = _response_margin(
                        snap, {}, 0.0, staged,
                        baseline_outputs, drains,
                    )
                    staged_key = (
                        -staged_payoff, -float(staged.cost),
                        -int(staged.quantity), staged.name,
                    )
                    direction_key = (str(item), crop, animal)
                    incumbent = staged_best.get(direction_key)
                    if incumbent is None or staged_key > incumbent[0]:
                        staged_best[direction_key] = (
                            staged_key, staged,
                        )
        product = (str(item) if item in econ.CROPS else
                   str(econ.ANIMALS[item]["product"]))
        if product in complete_products:
            chosen.extend(direction)
        elif best is not None:
            chosen.append(best[1])

    if full_continuation and mixed_continuation:
        # A pure-direction set cannot express an opponent who spends one
        # current public budget on both the most profitable crop book and a
        # contested animal book. For every engine-derived unordered pair,
        # enumerate every affordable quantity of the first item and the
        # maximum affordable remainder of the second, in both deterministic
        # nearest-slot layouts. Retain the exact standalone-profit maximizer.
        # This is a finite paid action set, not a fitted opponent mixture.
        items = sorted(tuple(econ.CROPS) + tuple(econ.ANIMALS))
        baseline_key = (int(cashflow.LAST_DAY), False)
        full_baseline = baseline_cache.get(baseline_key)
        if full_baseline is None:
            full_baseline = cashflow.certify_shared(
                actor, {}, (), reserve=0.0, minimal_full_output=True,
                visible_survival_horizon=cashflow.LAST_DAY,
                enforce_bridge_cash=False,
            )
            baseline_cache[baseline_key] = full_baseline
        for left_index, left in enumerate(items):
            for right in items[left_index + 1:]:
                unit = {
                    left: float(econ.CROPS[left]["seed"]
                                if left in econ.CROPS
                                else econ.ANIMALS[left]["cost"]),
                    right: float(econ.CROPS[right]["seed"]
                                 if right in econ.CROPS
                                 else econ.ANIMALS[right]["cost"]),
                }
                for first, second in ((left, right), (right, left)):
                    best = None
                    first_cap = min(
                        len(slots) - 1,
                        int(float(farm.money) // unit[first]),
                    )
                    for first_qty in range(1, first_cap + 1):
                        remaining_cash = (
                            float(farm.money) - first_qty * unit[first]
                        )
                        second_qty = min(
                            len(slots) - first_qty,
                            max(0, int(remaining_cash // unit[second])),
                        )
                        if second_qty <= 0:
                            continue
                        counts = {first: first_qty, second: second_qty}
                        positions = {
                            first: slots[:first_qty],
                            second: slots[
                                first_qty:first_qty + second_qty
                            ],
                        }
                        endpoint = cashflow.certify_shared(
                            actor, counts,
                            slots[:first_qty + second_qty], reserve=0.0,
                            positions_by_item=positions,
                            minimal_full_output=True,
                            visible_survival_horizon=cashflow.LAST_DAY,
                        )
                        if not endpoint.feasible:
                            continue
                        operating = (
                            _incremental_operating_cost(
                                endpoint, full_baseline,
                            )
                            if full_baseline.feasible
                            else endpoint.operating_cost
                        )
                        cost = (float(endpoint.upfront_spend)
                                + float(operating))
                        response = Response(
                            name=(f"BUY_MIX_{first}_{first_qty}_"
                                  f"{second}_{second_qty}_FULL"),
                            item=f"{left}+{right}",
                            quantity=first_qty + second_qty,
                            cost=cost,
                            outputs=_freeze_schedule(
                                endpoint.outputs_by_day,
                            ),
                        )
                        payoff = _response_margin(
                            snap, {}, 0.0, response,
                            baseline_outputs, drains,
                        )
                        key = (
                            -payoff, -cost,
                            -(first_qty + second_qty), response.name,
                        )
                        if best is None or key > best[0]:
                            best = (key, response)
                    if best is not None:
                        chosen.append(best[1])
    if generate_staged:
        cached_staged = tuple(
            staged_best[key][1] for key in sorted(staged_best)
        )
        if staged_response_cache is not None:
            staged_response_cache[staged_cache_key] = cached_staged
    chosen.extend(cached_staged or ())
    return tuple([no_response] + chosen)


def make_context(snap, full_response_continuation=False,
                 mixed_response_continuation=False,
                 include_own_standing_book=False,
                 candidate_response_products=(),
                 staged_response_reinvestment=False,
                 staged_response_cache=None,
                 robust_own_standing_realisation=False,
                 staged_response_land_reinvestment=False,
                 staged_response_mixed_reinvestment=False):
    """Solve-local public response context shared by every candidate arm."""
    opponent_baseline = cashflow._visible_output_schedule(snap, snap.opp)
    own_baseline = (
        cashflow._visible_output_schedule(snap, snap.me)
        if (include_own_standing_book
            or robust_own_standing_realisation) else {}
    )
    drains = cashflow._guaranteed_town_drain_by_day(snap)
    responses = finite_public_responses(
        snap, opponent_baseline, drains,
        full_continuation=full_response_continuation,
        mixed_continuation=mixed_response_continuation,
        complete_products=candidate_response_products,
        staged_reinvestment=staged_response_reinvestment,
        staged_response_cache=staged_response_cache,
        staged_land_reinvestment=staged_response_land_reinvestment,
        staged_mixed_reinvestment=staged_response_mixed_reinvestment,
    )
    context = {
        "responses": responses,
        "opponent_baseline": opponent_baseline,
        "own_baseline": own_baseline,
        "drains": drains,
        "include_own_standing_book": bool(include_own_standing_book),
        "candidate_response_products": tuple(sorted(
            str(item) for item in candidate_response_products
        )),
        "staged_response_reinvestment": bool(
            staged_response_reinvestment
        ),
        "robust_own_standing_realisation": bool(
            robust_own_standing_realisation
        ),
        "staged_response_land_reinvestment": bool(
            staged_response_land_reinvestment
        ),
        "staged_response_mixed_reinvestment": bool(
            staged_response_mixed_reinvestment
        ),
    }
    context["baseline_robust"] = float(min(
        _context_response_margin(snap, {}, 0.0, response, context)
        for response in responses
    ))
    if robust_own_standing_realisation:
        incremental = [
            (_response_margin(
                snap, {}, 0.0, response,
                opponent_baseline, drains,
            ), response.name)
            for response in responses
        ]
        standing = [
            (_standing_response_margin(
                snap, {}, 0.0, response,
                opponent_baseline, drains, own_baseline,
            ), response.name)
            for response in responses
        ]
        context["baseline_robust_modes"] = {
            "incremental": float(min(incremental)[0]),
            "standing": float(min(standing)[0]),
        }
    return context


def _cash_at(cert, day):
    eligible = [d for d in cert.cash_by_day if int(d) <= int(day)]
    if eligible:
        return float(cert.cash_by_day[max(eligible)])
    if cert.cash_path:
        return float(cert.cash_path[0])
    return float("-inf")


def _incremental_revenue_by_day(snap, base_outputs, extra_outputs):
    base_book = cashflow._reserved_book(snap)
    combined_book = dict(base_book)
    out = {}
    for day in sorted(set(base_outputs) | set(extra_outputs)):
        base_day = Counter(base_outputs.get(day, {}))
        extra_day = Counter(extra_outputs.get(day, {}))
        base_revenue, base_book = cashflow._sell_outputs_cached(
            base_book, base_day,
        )
        combined_revenue, combined_book = cashflow._sell_outputs_cached(
            combined_book, base_day + extra_day,
        )
        out[int(day)] = float(combined_revenue - base_revenue)
    return out


def _standalone_schedule_revenue(snap, schedule):
    """Exact dated own revenue on the conservative public reserved book."""
    book = cashflow._reserved_book(snap)
    revenue = 0.0
    for day in sorted(schedule):
        gained, book = cashflow._sell_outputs_cached(
            book, Counter(schedule.get(day, {})),
        )
        revenue += float(gained)
    return revenue


def _standing_cash_terms(snap, horizon):
    """Conservative dated cash/slot credits for own public standing output."""
    schedule = cashflow._visible_output_schedule(
        snap, snap.me, include_fertilizer=True,
    )
    schedule = {day: Counter(products) for day, products in schedule.items()
                if int(day) <= int(horizon)}
    book = cashflow._reserved_book(snap)
    # `_reserved_book` historically omits fertilizer. Reserve the difference
    # before pricing the background sale so this cash credit cannot overstate
    # what the same public animals make available.
    ordinary = cashflow._remaining_visible_units(snap, snap.me)
    with_fertilizer = cashflow._remaining_visible_units(
        snap, snap.me, include_fertilizer=True,
    )
    book["FERTILIZER"] = int(book.get("FERTILIZER", econ.MARKET_I0)) + max(
        0, int(with_fertilizer.get("FERTILIZER", 0))
        - int(ordinary.get("FERTILIZER", 0)),
    )
    credits = {}
    products_by_day = {}
    for day in sorted(schedule):
        gained, book = cashflow._sell_outputs_cached(book, schedule[day])
        credits[int(day)] = float(gained)
        products_by_day[int(day)] = {
            item for item, qty in schedule[day].items() if int(qty) > 0
        }
    return credits, products_by_day


def feasible_reinvestments(snap, cert, reserve=0.0,
                           include_land_option=False,
                           include_activated_land=False,
                           all_output_anchors=False,
                           anchor_day=None,
                           release_harvested_land=False):
    """Enumerate one executable crop continuation funded by realised output.

    Every continuation uses one still-empty current-land tile, buys after the
    first certified output has reached cash, starts work the following day,
    and follows an independently closed exact first-output route.  Combining
    closed route counts is conservative but constructive: it cannot borrow
    labour from the standing/new-capital certificate.
    """
    none = Reinvestment("NO_REINVESTMENT")
    output_days = sorted(
        day for day, products in cert.outputs_by_day.items()
        if any(int(qty or 0) > 0 for qty in products.values())
    )
    if not output_days:
        return (none,)
    if all_output_anchors and anchor_day is None:
        options = [none]
        seen = {none.name}
        for candidate_day in output_days:
            for option in feasible_reinvestments(
                    snap, cert, reserve,
                    include_land_option=include_land_option,
                    include_activated_land=include_activated_land,
                    all_output_anchors=False,
                    anchor_day=int(candidate_day),
                    release_harvested_land=release_harvested_land):
                if option.name not in seen:
                    seen.add(option.name)
                    options.append(option)
        return tuple(options)
    anchor = int(output_days[0] if anchor_day is None else anchor_day)
    if anchor not in output_days:
        return (none,)
    purchase_day = anchor + 1
    start_day = purchase_day + 1
    if start_day > cashflow.LAST_DAY:
        return (none,)
    used = {
        tuple(pos) for positions in cert.positions_by_item.values()
        for pos in positions
    }
    # A harvested one-time crop releases both its tile and its realised cash.
    # The earlier certificate blocked every initial capital position forever,
    # erasing the most important economic option of an early WHEAT/CARROT
    # rotation.  Release only positions whose named crop output is already in
    # the certified schedule at or before this anchor; ongoing crops, animals
    # and not-yet-harvested crops remain hard blocked.
    released = set()
    if release_harvested_land:
        for crop, positions in cert.positions_by_item.items():
            if crop not in econ.CROPS or bool(econ.CROPS[crop]["ongoing"]):
                continue
            harvested = any(
                int(day) <= anchor
                and int(products.get(crop, 0) or 0) > 0
                for day, products in cert.outputs_by_day.items()
            )
            if harvested:
                released.update(tuple(pos) for pos in positions)
    blocked = used - released
    current_slots = cashflow._available_slots(
        snap, reserve_inventory=False, blocked_positions=blocked,
    )
    options = [none]

    def add_option(crop, positions, purchase_cost, purchase_orders, name,
                   repeat_rotation=False):
        if purchase_day * econ.TURNS_PER_DAY > econ.SEED_DEADLINE[crop]:
            return
        assigned = {crop: list(positions)}
        stops = defaultdict(list)
        pickups = defaultdict(lambda: defaultdict(set))
        outputs = defaultdict(Counter)
        purchase_costs = {int(purchase_day): float(purchase_cost)}
        cycle_start = int(start_day)
        while True:
            (cycle_stops, cycle_feed, cycle_outputs, cycle_pickups,
             error) = cashflow._profiles_exact_first_output_positioned(
                snap, assigned, start_day=cycle_start,
            )
            if error or any(int(qty or 0)
                            for qty in cycle_feed.values()):
                return
            for day, day_stops in cycle_stops.items():
                stops[int(day)].extend(day_stops)
            for day, products in cycle_outputs.items():
                outputs[int(day)].update(products)
            for day, by_position in cycle_pickups.items():
                for position, items in by_position.items():
                    pickups[int(day)][tuple(position)].update(items)
            if (not repeat_rotation
                    or bool(econ.CROPS[crop]["ongoing"])):
                break
            sale_days = [
                int(day) for day, products in cycle_outputs.items()
                if int(products.get(crop, 0) or 0) > 0
            ]
            if not sale_days:
                break
            next_purchase = max(sale_days) + 1
            next_start = next_purchase + 1
            if (next_purchase * econ.TURNS_PER_DAY
                    > econ.SEED_DEADLINE[crop]):
                break
            purchase_costs[next_purchase] = (
                len(positions) * float(econ.CROPS[crop]["seed"])
            )
            cycle_start = next_start
        feasible = True
        incremental_hire_cost = {}
        days = sorted(set(stops) | set(outputs) | set(purchase_costs))
        for day in days:
            routes = cashflow._pack_shared_routes_with_pickups(
                stops.get(day, ()), pickups.get(day, {}),
            )
            if routes is None:
                feasible = False
                break
            base_workers = int(cert.workers_by_day.get(day, 0) or 0)
            total_workers = base_workers + len(routes)
            base_hires = max(0, base_workers - 1)
            total_hires = max(0, total_workers - 1)
            sale_items = {
                item for item, qty in cert.outputs_by_day.get(day, {}).items()
                if int(qty or 0) > 0
            } | {
                item for item, qty in outputs.get(day, {}).items()
                if int(qty or 0) > 0
            }
            slots_used = total_hires
            slots_used += int(bool(cert.feed_by_day.get(day, 0)))
            slots_used += len(sale_items)
            slots_used += (int(purchase_orders)
                           if day in purchase_costs else 0)
            if slots_used > econ.MAX_ORDERS:
                feasible = False
                break
            incremental_hire_cost[day] = (
                float(econ.hire_block_cost(0, total_hires))
                - float(econ.hire_block_cost(0, base_hires))
            )
        if not feasible:
            return
        extra_outputs = {day: dict(products)
                         for day, products in outputs.items()}
        incremental_revenue = _incremental_revenue_by_day(
            snap, cert.outputs_by_day, extra_outputs,
        )
        delta = 0.0
        minimum = float("inf")
        for day in sorted(set(days) | set(incremental_revenue)):
            delta -= float(purchase_costs.get(day, 0.0))
            delta -= float(incremental_hire_cost.get(day, 0.0))
            minimum = min(minimum, _cash_at(cert, day) + delta)
            delta += float(incremental_revenue.get(day, 0.0))
            minimum = min(minimum, _cash_at(cert, day) + delta)
        if minimum < float(reserve) - 1e-9:
            return
        cost = (sum(purchase_costs.values())
                + sum(incremental_hire_cost.values()))
        options.append(Reinvestment(
            name=name, cost=float(cost),
            outputs=_freeze_schedule(extra_outputs),
        ))

    if current_slots and not release_harvested_land:
        position = current_slots[0]
        for crop in sorted(econ.CROPS):
            add_option(
                crop, [position], float(econ.CROPS[crop]["seed"]), 1,
                f"AFTER_DAY_{anchor}_BUY_{crop}",
            )
    elif current_slots:
        available_cash = _cash_at(cert, purchase_day) - float(reserve)
        for crop in sorted(econ.CROPS):
            seed_cost = float(econ.CROPS[crop]["seed"])
            cap = min(
                len(current_slots),
                max(0, int(available_cash // seed_cost)),
            )
            start_index = len(options)
            for quantity in range(1, cap + 1):
                add_option(
                    crop, current_slots[:quantity], quantity * seed_cost, 1,
                    f"AFTER_DAY_{anchor}_ROTATE_{crop}_{quantity}",
                    repeat_rotation=True,
                )
            generated = options[start_index:]
            del options[start_index:]
            if generated:
                options.append(max(
                    generated,
                    key=lambda option: (
                        _standalone_schedule_revenue(
                            snap, option.schedule(),
                        ) - float(option.cost),
                        -float(option.cost), option.name,
                    ),
                ))

    if include_activated_land:
        activated_quadrants = sorted({
            paths.quadrant_of(pos[0], pos[1], snap.board)
            for pos in used
            if paths.quadrant_of(pos[0], pos[1], snap.board)
            not in set(snap.me.unlocked)
        })
        expanded = cashflow._available_slots(
            snap, include_next_land=True, reserve_inventory=False,
            blocked_positions=used,
        )
        for quadrant in activated_quadrants:
            fill_slots = [
                pos for pos in expanded
                if paths.quadrant_of(pos[0], pos[1], snap.board) == quadrant
                and pos not in used
            ]
            available_cash = _cash_at(cert, purchase_day) - float(reserve)
            for crop in sorted(econ.CROPS):
                seed_cost = float(econ.CROPS[crop]["seed"])
                cap = min(
                    len(fill_slots),
                    max(0, int(available_cash // seed_cost)),
                )
                start_index = len(options)
                for quantity in range(1, cap + 1):
                    add_option(
                        crop, fill_slots[:quantity], quantity * seed_cost, 1,
                        (f"AFTER_DAY_{anchor}_FILL_ACTIVATED_{quadrant}_"
                         f"{crop}_{quantity}"),
                    )
                # The leader's second-stage action set retains one quantity
                # per product direction: the exact standalone-profit maximizer
                # among every cash/labour-feasible integer quantity. The outer
                # Stackelberg solve still chooses the worst paid opponent
                # response against that direction. This finite reduction is
                # equation-derived and avoids evaluating identical response
                # games for every prefix quantity inside every crew arm.
                generated = options[start_index:]
                del options[start_index:]
                if generated:
                    options.append(max(
                        generated,
                        key=lambda option: (
                            _standalone_schedule_revenue(
                                snap, option.schedule(),
                            ) - float(option.cost),
                            -float(option.cost), option.name,
                        ),
                    ))

    if include_land_option:
        owned_extra = len(snap.me.unlocked) - 1
        if econ.can_buy_land(len(snap.me.unlocked)):
            quadrant = econ.LAND_ORDER[owned_extra]
            expanded = cashflow._available_slots(
                snap, include_next_land=True, reserve_inventory=False,
                blocked_positions=used,
            )
            land_slots = [
                pos for pos in expanded
                if paths.quadrant_of(pos[0], pos[1], snap.board) == quadrant
                and pos not in current_slots
            ]
            land_cost = float(econ.LAND_PRICES[owned_extra])
            available_cash = _cash_at(cert, purchase_day) - float(reserve)
            for crop in sorted(econ.CROPS):
                seed_cost = float(econ.CROPS[crop]["seed"])
                cap = min(
                    len(land_slots),
                    max(0, int((available_cash - land_cost) // seed_cost)),
                )
                start_index = len(options)
                for quantity in range(1, cap + 1):
                    add_option(
                        crop, land_slots[:quantity],
                        land_cost + quantity * seed_cost, 2,
                        (f"AFTER_DAY_{anchor}_BUY_LAND_{quadrant}_"
                         f"{crop}_{quantity}"),
                    )
                if release_harvested_land:
                    generated = options[start_index:]
                    del options[start_index:]
                    if generated:
                        options.append(max(
                            generated,
                            key=lambda option: (
                                _standalone_schedule_revenue(
                                    snap, option.schedule(),
                                ) - float(option.cost),
                                -float(option.cost), option.name,
                            ),
                        ))
    return tuple(options)


def feasible_deferred_capital(snap, cert, reserve=0.0,
                              full_continuation=False,
                              blocked_positions=(), purchase_day=None,
                              release_harvested_land=False,
                              target_items=None, name_stem=None,
                              purchase_order_keys=1):
    """One-day hold-cash/empty-tile option over every legal asset.

    A cheap current crop does not consume only seed cash and today's route: it
    also occupies a tile that tomorrow's replan could use for a durable asset.
    This finite continuation preserves that option explicitly.  It buys on the
    next day, starts the independently closed route one day later, and charges
    the incremental Fibonacci crew, animal feed, market keys and capital before
    crediting output.  The optional full-continuation arm pays that service
    through every remaining base output as a second named endpoint; the first-
    output abandonment endpoint remains available.  Every quantity comes from
    live cash and live empty positions; no preferred asset or target
    composition enters the set.

    Route counts are added rather than jointly repacked with ``cert``.  This is
    conservative: a returned option is executable even without assuming that a
    future optimiser discovers route sharing.  WHEAT feed is priced on paired
    no-refill books for the baseline and combined workloads, which likewise
    cannot understate the incremental purchase bill.
    """
    none = Reinvestment("NO_DEFERRED_CAPITAL")
    purchase_day = (int(snap.day) + 1 if purchase_day is None
                    else int(purchase_day))
    start_day = purchase_day + 1
    if start_day > cashflow.LAST_DAY:
        return (none,)
    used = {
        tuple(pos) for positions in cert.positions_by_item.values()
        for pos in positions
    }
    if release_harvested_land:
        realised_by = int(purchase_day) - 1
        for item, positions in cert.positions_by_item.items():
            if item not in econ.CROPS or bool(econ.CROPS[item]["ongoing"]):
                continue
            if any(
                    int(day) <= realised_by
                    and int(products.get(item, 0) or 0) > 0
                    for day, products in cert.outputs_by_day.items()):
                used.difference_update(tuple(pos) for pos in positions)
    used.update(tuple(pos) for pos in (blocked_positions or ()))
    slots = cashflow._available_slots(
        snap, reserve_inventory=False, blocked_positions=used,
    )
    available_cash = _cash_at(cert, purchase_day) - float(reserve)
    if not slots or available_cash <= 0.0:
        return (none,)

    drains = cashflow._guaranteed_town_drain_by_day(snap)
    options = [none]
    legal_targets = (tuple(econ.CROPS) + tuple(econ.ANIMALS)
                     if target_items is None else tuple(target_items))
    for item in sorted(legal_targets):
        if item not in econ.CROPS and item not in econ.ANIMALS:
            continue
        deadline = (econ.SEED_DEADLINE[item] if item in econ.CROPS
                    else econ.ANIMAL_DEADLINE[item])
        if purchase_day * econ.TURNS_PER_DAY > int(deadline):
            continue
        unit_cost = float(econ.CROPS[item]["seed"] if item in econ.CROPS
                          else econ.ANIMALS[item]["cost"])
        cap = min(len(slots), max(0, int(available_cash // unit_cost)))
        for quantity in range(1, cap + 1):
            positions = slots[:quantity]
            assigned = {item: positions}
            profiles = [(
                "",
                cashflow._profiles_exact_first_output_positioned(
                    snap, assigned, start_day=start_day,
                ),
            )]
            if full_continuation:
                profiles.append((
                    "_FULL",
                    cashflow._profiles_minimal_full_output_positioned(
                        snap, assigned, start_day=start_day,
                    ),
                ))
            for suffix, profile in profiles:
                stops, feed, outputs, pickups, error = profile
                if error:
                    continue
                incremental_hire = {}
                extra_routes_by_day = {}
                combined_hire_phases_by_day = {}
                feasible = True
                days = sorted(
                    set(stops) | set(feed) | set(outputs) | {purchase_day}
                )
                for day in days:
                    routes = cashflow._pack_shared_routes_with_pickups(
                        stops.get(day, ()), pickups.get(day, {}),
                    )
                    if routes is None:
                        feasible = False
                        break
                    extra_routes_by_day[int(day)] = tuple(routes)
                    base_workers = int(cert.workers_by_day.get(day, 0) or 0)
                    total_workers = base_workers + len(routes)
                    base_hires = max(0, base_workers - 1)
                    total_hires = max(0, total_workers - 1)
                    feed_qty = (int(cert.feed_by_day.get(day, 0) or 0)
                                + int(feed.get(day, 0) or 0))
                    sale_items = {
                        product for product, amount
                        in cert.outputs_by_day.get(day, {}).items()
                        if int(amount or 0) > 0
                    } | {
                        product for product, amount
                        in outputs.get(day, {}).items()
                        if int(amount or 0) > 0
                    }
                    slots_used = total_hires + int(bool(feed_qty))
                    slots_used += len(sale_items)
                    slots_used += (
                        int(purchase_order_keys)
                        if day == purchase_day else 0
                    )
                    if slots_used > econ.MAX_ORDERS:
                        feasible = False
                        break
                    # This deferred option deliberately closes every required
                    # hire in the hour-0 queue.  The slot inequality above
                    # includes feed, dated output sales and the purchase key,
                    # so all of these workers retain the full 23-action route
                    # horizon.  The witness is stronger than merely assuming
                    # a future optimiser will rediscover a two-wave split.
                    combined_hire_phases_by_day[int(day)] = (
                        int(total_hires), 0,
                    )
                    incremental_hire[day] = (
                        float(econ.hire_block_cost(0, total_hires))
                        - float(econ.hire_block_cost(0, base_hires))
                    )
                if not feasible:
                    continue

                # Price the extra animal ration against the exact baseline
                # ration on two deterministic conservative books. Guaranteed
                # town drain occurs between dated purchases; omitting our
                # possible WHEAT output cannot understate the extra-feed bill.
                base_book = int(
                    snap.market_inv.get("WHEAT", econ.MARKET_I0)
                    or econ.MARKET_I0
                )
                combined_book = base_book
                incremental_feed = {}
                prior_day = int(snap.day)
                for day in days:
                    drain = sum(
                        max(0, int(
                            drains.get(d, {}).get("WHEAT", 0) or 0,
                        ))
                        for d in range(prior_day + 1, int(day) + 1)
                    )
                    base_book = max(0, base_book - drain)
                    combined_book = max(0, combined_book - drain)
                    base_qty = int(cert.feed_by_day.get(day, 0) or 0)
                    extra_qty = int(feed.get(day, 0) or 0)
                    base_cost = float(econ.buy_cost(
                        "WHEAT", base_qty, base_book,
                    ))
                    combined_cost = float(econ.buy_cost(
                        "WHEAT", base_qty + extra_qty, combined_book,
                    ))
                    incremental_feed[day] = combined_cost - base_cost
                    base_book -= base_qty
                    combined_book -= base_qty + extra_qty
                    prior_day = int(day)

                extra_outputs = {
                    int(day): dict(products)
                    for day, products in outputs.items()
                }
                incremental_revenue = _incremental_revenue_by_day(
                    snap, cert.outputs_by_day, extra_outputs,
                )
                purchase_cost = quantity * unit_cost
                delta = 0.0
                minimum = float("inf")
                for day in sorted(set(days) | set(incremental_revenue)):
                    if day == purchase_day:
                        delta -= purchase_cost
                    delta -= float(incremental_hire.get(day, 0.0))
                    delta -= float(incremental_feed.get(day, 0.0))
                    minimum = min(minimum, _cash_at(cert, day) + delta)
                    delta += float(incremental_revenue.get(day, 0.0))
                    minimum = min(minimum, _cash_at(cert, day) + delta)
                if minimum < float(reserve) - 1e-9:
                    continue
                cost = (purchase_cost + sum(incremental_hire.values())
                        + sum(incremental_feed.values()))
                prefix = (str(name_stem) if name_stem is not None
                          else f"DEFER_DAY_{purchase_day}")
                options.append(Reinvestment(
                    name=(f"{prefix}_BUY_{item}_{quantity}{suffix}"),
                    cost=float(cost),
                    outputs=_freeze_schedule(extra_outputs),
                    purchase_day=int(purchase_day),
                    order=(("BUY_SEED" if item in econ.CROPS
                            else "BUY_ANIMAL"), item, int(quantity)),
                    positions_by_item=((
                        str(item), tuple(tuple(pos) for pos in positions),
                    ),),
                    routes_by_day=tuple(
                        (int(day), tuple(routes))
                        for day, routes in sorted(
                            extra_routes_by_day.items()
                        )
                    ),
                    hire_phases_by_day=tuple(
                        (int(day), tuple(phases))
                        for day, phases in sorted(
                            combined_hire_phases_by_day.items()
                        )
                    ),
                ))
    return tuple(options)


def feasible_output_funded_capital(snap, cert, reserve=0.0,
                                   full_continuation=True,
                                   target_items=None,
                                   include_land=False):
    """Capital bought only after a certified output has become cash.

    The first positive output day is the public funding event.  The purchase
    occurs on the following day, work begins one day later, and a harvested
    one-shot crop may release only its own named positions.  This is a finite
    two-stage reachability certificate, not a forecast that grants the actor
    free future money or land.
    """
    none = Reinvestment("NO_OUTPUT_FUNDED_CAPITAL")
    output_days = sorted(
        int(day) for day, products in cert.outputs_by_day.items()
        if any(int(qty or 0) > 0 for qty in products.values())
    )
    if not output_days:
        return (none,)
    anchor = int(output_days[0])
    options = feasible_deferred_capital(
        snap, cert, reserve=reserve,
        full_continuation=full_continuation,
        purchase_day=anchor + 1,
        release_harvested_land=True,
        target_items=(tuple(econ.ANIMALS)
                      if target_items is None else tuple(target_items)),
        name_stem=f"REINVEST_AFTER_DAY_{anchor}",
    )
    converted = [none]
    converted.extend(
        option for option in options
        if option.name != "NO_DEFERRED_CAPITAL"
    )
    if include_land:
        owned_extra = len(snap.me.unlocked) - 1
        if econ.can_buy_land(len(snap.me.unlocked)):
            land_cost = float(econ.LAND_PRICES[owned_extra])
            next_quadrant = str(econ.LAND_ORDER[owned_extra])
            expanded = copy.copy(snap)
            expanded.me = copy.copy(snap.me)
            expanded.me.unlocked = list(snap.me.unlocked) + [next_quadrant]
            expanded.me.tiles = [list(row) for row in snap.me.tiles]
            next_positions = []
            for y, row in enumerate(expanded.me.tiles):
                for x, tile in enumerate(row):
                    if (paths.quadrant_of(x, y, snap.board) == next_quadrant
                            and tile == "LOCKED"):
                        expanded.me.tiles[y][x] = None
                        next_positions.append((x, y))
            expanded.me.empty = (
                list(getattr(snap.me, "empty", ())) + next_positions
            )
            current_positions = cashflow._available_slots(
                snap, reserve_inventory=False,
            )
            land_options = feasible_deferred_capital(
                expanded, cert, reserve=float(reserve) + land_cost,
                full_continuation=full_continuation,
                blocked_positions=current_positions,
                purchase_day=anchor + 1,
                release_harvested_land=False,
                target_items=(tuple(econ.ANIMALS)
                              if target_items is None
                              else tuple(target_items)),
                name_stem=(f"REINVEST_AFTER_DAY_{anchor}_BUY_LAND_"
                           f"{next_quadrant}_THEN"),
                purchase_order_keys=2,
            )
            for option in land_options:
                if option.name == "NO_DEFERRED_CAPITAL":
                    continue
                converted.append(Reinvestment(
                    name=option.name,
                    cost=float(option.cost) + land_cost,
                    outputs=option.outputs,
                    purchase_day=option.purchase_day,
                    order=option.order,
                    positions_by_item=option.positions_by_item,
                    routes_by_day=option.routes_by_day,
                    hire_phases_by_day=option.hire_phases_by_day,
                    activates_land=True,
                ))
    return tuple(converted)


def feasible_output_funded_mixed(snap, cert, reserve=0.0):
    """Paid crop-plus-animal frontiers after the first realised sale.

    This is the missing mixed second stage between a one-shot cash crop and a
    durable herd.  The crop sale is first applied to the same conservative
    reserved market book used by ``cert``.  On the following day the actor may
    spend only the resulting certified cash.  For every public crop/animal
    pair and every positive crop quantity, the response tries the greatest
    animal quantity allowed by the remaining cash and physical slots.  An
    infeasible point is reduced until the exact full-output cash/labour/feed
    certificate closes.  The best exact incremental-profit point on each such
    engine-derived frontier is retained.

    Thus the finite reduction expresses the economically meaningful tendency
    to cover usable land without encoding a target coverage, herd, crop mix,
    replay statistic or opponent identity.  Both nearest-slot orderings are
    proved because heterogeneous route cost depends on placement.
    """
    none = Reinvestment("NO_OUTPUT_FUNDED_MIXED")
    output_days = sorted(
        int(day) for day, products in cert.outputs_by_day.items()
        if any(int(qty or 0) > 0 for qty in products.values())
    )
    if not output_days:
        return (none,)
    anchor = int(output_days[0])
    purchase_day = anchor + 1
    if purchase_day + 1 > cashflow.LAST_DAY:
        return (none,)

    available_cash = _cash_at(cert, purchase_day) - float(reserve)
    if available_cash <= 0.0:
        return (none,)

    # Reproduce the first certificate's own conservative sale book exactly.
    # Supplying it as `_context` prevents `_reserved_book` from reserving the
    # same standing public output a second time in the continuation.
    closing_book = cashflow._reserved_book(snap)
    for day in sorted(cert.outputs_by_day):
        if int(day) > anchor:
            break
        _revenue, closing_book = cashflow._sell_outputs_cached(
            closing_book, Counter(cert.outputs_by_day.get(day, {})),
        )

    future = copy.copy(snap)
    future.me = copy.copy(snap.me)
    future.me.money = float(available_cash)
    future.step = int(purchase_day) * econ.TURNS_PER_DAY
    future.day = int(purchase_day)
    future.hour = 0
    future.days_left = max(0, cashflow.LAST_DAY - int(purchase_day))

    used = {
        tuple(pos) for positions in cert.positions_by_item.values()
        for pos in positions
    }
    for item, positions in cert.positions_by_item.items():
        if item not in econ.CROPS or bool(econ.CROPS[item]["ongoing"]):
            continue
        if any(
                int(day) <= anchor
                and int(products.get(item, 0) or 0) > 0
                for day, products in cert.outputs_by_day.items()):
            used.difference_update(tuple(pos) for pos in positions)
    slots = cashflow._available_slots(
        future, reserve_inventory=False, blocked_positions=used,
    )
    if len(slots) < 2:
        return (none,)

    cash_context = (0.0, 0, dict(closing_book))
    baseline = cashflow.certify_shared(
        future, {}, (), reserve=0.0, _context=cash_context,
        minimal_full_output=True,
        visible_survival_horizon=cashflow.LAST_DAY,
        enforce_bridge_cash=False,
    )
    options = [none]
    endpoint_cache = {}

    def endpoint_for(crop, crop_qty, animal, animal_qty, reverse):
        key = (crop, int(crop_qty), animal, int(animal_qty), bool(reverse))
        if key in endpoint_cache:
            return endpoint_cache[key]
        crop_qty = int(crop_qty)
        animal_qty = int(animal_qty)
        if reverse:
            positions = {
                animal: slots[:animal_qty],
                crop: slots[animal_qty:animal_qty + crop_qty],
            }
        else:
            positions = {
                crop: slots[:crop_qty],
                animal: slots[crop_qty:crop_qty + animal_qty],
            }
        endpoint = cashflow.certify_shared(
            future, {crop: crop_qty, animal: animal_qty},
            slots[:crop_qty + animal_qty], reserve=0.0,
            _context=cash_context, positions_by_item=positions,
            minimal_full_output=True,
            visible_survival_horizon=cashflow.LAST_DAY,
        )
        endpoint_cache[key] = (endpoint, positions)
        return endpoint, positions

    for crop in sorted(econ.CROPS):
        if purchase_day * econ.TURNS_PER_DAY > econ.SEED_DEADLINE[crop]:
            continue
        crop_cost = float(econ.CROPS[crop]["seed"])
        for animal in sorted(econ.ANIMALS):
            if (purchase_day * econ.TURNS_PER_DAY
                    > econ.ANIMAL_DEADLINE[animal]):
                continue
            animal_cost = float(econ.ANIMALS[animal]["cost"])
            best = None
            crop_cap = min(
                len(slots) - 1,
                max(0, int((available_cash - animal_cost) // crop_cost)),
            )
            for crop_qty in range(1, crop_cap + 1):
                animal_cap = min(
                    len(slots) - crop_qty,
                    max(0, int(
                        (available_cash - crop_qty * crop_cost)
                        // animal_cost
                    )),
                )
                for reverse in (False, True):
                    animal_qty = int(animal_cap)
                    while animal_qty > 0:
                        endpoint, positions = endpoint_for(
                            crop, crop_qty, animal, animal_qty, reverse,
                        )
                        if endpoint.feasible:
                            break
                        animal_qty -= 1
                    if animal_qty <= 0:
                        continue
                    operating = (
                        _incremental_operating_cost(endpoint, baseline)
                        if baseline.feasible else endpoint.operating_cost
                    )
                    cost = float(endpoint.upfront_spend) + float(operating)
                    profit = (
                        float(endpoint.final_cash) - float(baseline.final_cash)
                        if baseline.feasible else
                        _standalone_schedule_revenue(
                            future, endpoint.outputs_by_day,
                        ) - cost
                    )
                    key = (
                        profit, -cost, crop_qty + animal_qty,
                        -crop_qty, -animal_qty, not reverse,
                    )
                    if best is None or key > best[0]:
                        best = (
                            key, crop_qty, animal_qty, endpoint, positions,
                        )
            if best is None:
                continue
            (_key, crop_qty, animal_qty, endpoint, positions) = best
            options.append(Reinvestment(
                name=(f"REINVEST_AFTER_DAY_{anchor}_BUY_MIX_"
                      f"{crop}_{crop_qty}_{animal}_{animal_qty}_FULL"),
                cost=(float(endpoint.upfront_spend)
                      + float(_incremental_operating_cost(endpoint, baseline)
                              if baseline.feasible
                              else endpoint.operating_cost)),
                outputs=_freeze_schedule(endpoint.outputs_by_day),
                purchase_day=int(purchase_day),
                order=("BUY_MIX", crop, int(crop_qty),
                       animal, int(animal_qty)),
                positions_by_item=tuple(
                    (str(item), tuple(tuple(pos) for pos in item_positions))
                    for item, item_positions in sorted(positions.items())
                ),
                routes_by_day=tuple(
                    (int(day), tuple(routes))
                    for day, routes in sorted(endpoint.routes_by_day.items())
                ),
                hire_phases_by_day=tuple(
                    (int(day), (max(0, int(workers) - 1), 0))
                    for day, workers in sorted(endpoint.workers_by_day.items())
                ),
            ))
    return tuple(options)


def _endpoint(snap, counts, slots, reserve, land_cost, fixed_orders,
              cash_context, positions_by_item, full,
              full_service_continuation=False,
              standing_service_horizon=None,
              service_fertilizer_credit=True,
              two_phase_future_hires=False):
    horizon = (cashflow.LAST_DAY if full else
               _first_output_horizon(snap, counts, phase_aligned=True))
    if horizon is None:
        return None
    common = dict(
        reserve=reserve, land_cost=land_cost, fixed_orders=fixed_orders,
        _context=cash_context, positions_by_item=positions_by_item,
        paired_objective=False, phase_aligned=True,
        two_phase_future_hires=two_phase_future_hires,
    )
    productive_standing = standing_service_horizon is not None
    service_horizon = (
        max(int(horizon), int(standing_service_horizon))
        if productive_standing else int(horizon)
    )
    if productive_standing:
        cash_credit, sale_products = _standing_cash_terms(
            snap, service_horizon,
        )
        combined = cashflow.certify_shared(
            snap, counts, slots,
            credit_fertilizer=service_fertilizer_credit,
            minimal_full_output=full,
            exact_first_output=not full,
            visible_full_service_horizon=service_horizon,
            cash_credit_by_day=cash_credit,
            sale_products_by_day=sale_products, **common,
        )
    elif full and full_service_continuation:
        cash_credit, sale_products = _standing_cash_terms(snap, horizon)
        combined = cashflow.certify_shared(
            snap, counts, slots,
            credit_fertilizer=service_fertilizer_credit,
            visible_full_service_horizon=horizon,
            cash_credit_by_day=cash_credit,
            sale_products_by_day=sale_products, **common,
        )
    else:
        combined = cashflow.certify_shared(
            snap, counts, slots, minimal_full_output=full,
            exact_first_output=not full,
            visible_survival_horizon=horizon, **common,
        )
    if not combined.feasible:
        return None
    baseline_kwargs = dict(
        reserve=0.0, land_cost=0.0, fixed_orders=fixed_orders,
        _context=cash_context, paired_objective=False, phase_aligned=True,
        enforce_bridge_cash=False,
        two_phase_future_hires=two_phase_future_hires,
    )
    if productive_standing:
        baseline = cashflow.certify_shared(
            snap, {}, (), visible_full_service_horizon=service_horizon,
            minimal_full_output=full,
            exact_first_output=not full,
            cash_credit_by_day=cash_credit,
            sale_products_by_day=sale_products,
            **baseline_kwargs,
        )
    elif full and full_service_continuation:
        baseline = cashflow.certify_shared(
            snap, {}, (), visible_full_service_horizon=horizon,
            cash_credit_by_day=cash_credit,
            sale_products_by_day=sale_products,
            **baseline_kwargs,
        )
    else:
        baseline = cashflow.certify_shared(
            snap, {}, (), minimal_full_output=full,
            exact_first_output=not full,
            visible_survival_horizon=horizon, **baseline_kwargs,
        )
    operating = (_incremental_operating_cost(combined, baseline)
                 if baseline.feasible else combined.operating_cost)
    own_cost = float(combined.upfront_spend) + float(operating)
    return combined, own_cost


def certify_unified(snap, counts, slots, reserve=0.0, land_cost=0.0,
                    fixed_orders=None, cash_context=None,
                    positions_by_item=None, context=None,
                    land_reinvestment=False,
                    activated_land_reinvestment=False,
                    full_service_continuation=False,
                    all_reinvestment_anchors=False,
                    rotation_reinvestment=False,
                    deferred_capital_reinvestment=False,
                    deferred_capital_full_continuation=False,
                    close_empty_deferred_baseline=False,
                    deferred_standing_service_horizon=False,
                    bounded_first_output_only=False,
                    deferred_blocked_positions=(),
                    service_fertilizer_credit=True,
                    service_fertilizer_value=True,
                    two_phase_future_hires=False):
    """Max endpoint/reinvestment, then min over paid public responses."""
    clean = {item: max(0, int(qty or 0))
             for item, qty in counts.items() if int(qty or 0) > 0}
    if cash_context is None:
        fixed_spend, initial_shed = cashflow._fixed_commitment(
            snap, fixed_orders,
        )
        cash_context = (
            fixed_spend, initial_shed, cashflow._reserved_book(snap),
        )
    if not clean and not close_empty_deferred_baseline:
        cert = cashflow.certify_shared(
            snap, {}, (), reserve=reserve, fixed_orders=fixed_orders,
            _context=cash_context,
            two_phase_future_hires=two_phase_future_hires,
        )
        cert.paired_value = 0.0
        return cert
    context = context if context is not None else make_context(snap)
    responses = tuple(
        context.get("responses") or (Response("NO_RESPONSE"),)
    )
    baseline = context.get("opponent_baseline", {})
    drains = context.get("drains")
    if "baseline_robust" in context:
        baseline_robust = float(context["baseline_robust"])
    else:
        baseline_robust = float(min(
            _response_margin(snap, {}, 0.0, response, baseline, drains)
            for response in responses
        ))
    endpoints = []
    standing_service_horizon = (
        _deferred_first_output_horizon(snap)
        if deferred_standing_service_horizon else None
    )
    for full in ((False,) if bounded_first_output_only else (False, True)):
        endpoint = _endpoint(
            snap, clean, slots, reserve, land_cost, fixed_orders,
            cash_context, positions_by_item, full,
            full_service_continuation=full_service_continuation,
            standing_service_horizon=standing_service_horizon,
            service_fertilizer_credit=service_fertilizer_credit,
            two_phase_future_hires=two_phase_future_hires,
        )
        if endpoint is None:
            continue
        cert, base_cost = endpoint
        reinvestments = list(feasible_reinvestments(
                snap, cert, reserve,
                include_land_option=land_reinvestment,
                include_activated_land=activated_land_reinvestment,
                all_output_anchors=all_reinvestment_anchors,
                release_harvested_land=rotation_reinvestment))
        if deferred_capital_reinvestment:
            reinvestments.extend(
                feasible_deferred_capital(
                    snap, cert, reserve,
                    full_continuation=(
                        deferred_capital_full_continuation
                    ),
                    blocked_positions=deferred_blocked_positions,
                )[1:]
            )
        for reinvestment in reinvestments:
            own_outputs = _merge_schedules(
                cert.outputs_by_day, reinvestment.schedule(),
            )
            if not service_fertilizer_value:
                own_outputs = {
                    int(day): {
                        item: int(qty) for item, qty in products.items()
                        if item != "FERTILIZER" and int(qty or 0) > 0
                    }
                    for day, products in own_outputs.items()
                }
            own_cost = float(base_cost) + float(reinvestment.cost)
            if context.get("robust_own_standing_realisation", False):
                mode_baselines = context["baseline_robust_modes"]
                mode_rows = []
                for mode in ("incremental", "standing"):
                    if mode == "standing":
                        values = [
                            (_standing_response_margin(
                                snap, own_outputs, own_cost, response,
                                baseline, drains,
                                context.get("own_baseline", {}),
                            ), response)
                            for response in responses
                        ]
                    else:
                        values = [
                            (_response_margin(
                                snap, own_outputs, own_cost, response,
                                baseline, drains,
                            ), response)
                            for response in responses
                        ]
                    mode_worst, mode_response = min(
                        values, key=lambda row: (row[0], row[1].name),
                    )
                    mode_rows.append((
                        float(mode_worst) - float(mode_baselines[mode]),
                        mode, mode_response,
                    ))
                relative_value, worst_mode, worst_response = min(
                    mode_rows,
                    key=lambda row: (row[0], row[1], row[2].name),
                )
                worst_response_name = (
                    f"{worst_mode}:{worst_response.name}"
                )
            else:
                response_values = [
                    (_context_response_margin(
                        snap, own_outputs, own_cost, response, context,
                    ), response)
                    for response in responses
                ]
                worst_value, worst_response = min(
                    response_values,
                    key=lambda row: (row[0], row[1].name),
                )
                relative_value = float(worst_value) - baseline_robust
                worst_response_name = worst_response.name
            key = (
                relative_value, float(cert.final_cash),
                -float(own_cost), -int(full), reinvestment.name,
                worst_response_name,
            )
            endpoints.append((
                key, cert, reinvestment, worst_response_name,
                own_cost, bool(full),
            ))
    if not endpoints:
        failed = cashflow.Certificate(clean, land_cost)
        return failed.reject("no_stackelberg_endpoint", float(snap.me.money))
    (key, cert, selected_reinvestment, selected_worst_response,
     selected_own_cost, selected_full) = max(
        endpoints, key=lambda row: row[0],
    )
    cert.paired_value = float(key[0])
    cert.selected_reinvestment = str(selected_reinvestment.name)
    cert.selected_worst_response = str(selected_worst_response)
    cert.selected_own_cost = float(selected_own_cost)
    cert.selected_full_endpoint = bool(selected_full)
    cert.selected_reinvestment_order = tuple(selected_reinvestment.order)
    cert.selected_reinvestment_positions_by_item = (
        selected_reinvestment.positions()
    )
    execution_routes = {
        int(day): tuple(routes)
        for day, routes in cert.routes_by_day.items()
    }
    for day, routes in selected_reinvestment.routes().items():
        execution_routes[int(day)] = (
            tuple(execution_routes.get(int(day), ())) + tuple(routes)
        )
    execution_phases = {
        int(day): tuple(int(qty) for qty in phases)
        for day, phases in cert.hire_phases_by_day.items()
    }
    execution_phases.update(selected_reinvestment.hire_phases())
    cert.selected_execution_routes_by_day = execution_routes
    cert.selected_execution_hire_phases_by_day = execution_phases
    return cert
