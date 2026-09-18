# Kaggriculture: white-box optimisation architecture

## Contract

The production agent may use only:

- the current observation and its own state carried across turns;
- transition, price, production and legality rules derived from the engine;
- deterministic optimisation algorithms over those rules;
- uncertainty sets derived from what is currently observable.

It may not load, replay, imitate, splice, classify, or choose another player's
action trace. Replay-mining files in this repository are historical diagnostics,
not legal production dependencies. `whitebox/agent.py::_whitebox_entry` is the
production entry and no longer contains a tape or replay-opening path.

Current published wrapper: `whitebox/versions/v204_retained_land_commitment.py`,
packaged as `submission/whitebox_v204.py`. V204 keeps the V103/V102 constructive
terminal route and adds a state-derived retained-land obligation: a deferred
land action is reopened only when the live observation again satisfies the
positioned route, cash, service-displacement, order-slot and robust-value
certificates. The online integer frontier is bounded by public endpoint
feasibility, and V214/V215 capacity-reserve variants remain research-only.
V204 is a transparent white-box research release, not a claim of promotion or
guaranteed win rate. Its capital, task and market layers share one post-unit
`decision_snap`; the market layer applies deterministic day-boundary shed
capacity protection. The selected wrapper imports no tape, replay, opponent
file, fitted weight, seed schedule, or filesystem data. Historical V103/V102
qualification results remain below as provenance; they predate the current
shared-market-equation correction and are not silently reused as a current
promotion claim.

The linked public-state-router reference was audited separately. Its compressed
action arrays and route-label selection are replay/tape mechanisms and are not
reachable from the production bundle. Only the rule-level lessons (state-based
repair, capacity protection, route feasibility and terminal clearing) are
eligible for white-box translation. Run
`scripts/audit_whitebox_runtime.py` to audit the exact package closure before
shipping a new wrapper.

## Runtime contract

Runtime failure is game failure. The installed runner grants 1 second per call
and only 60 seconds of overage for the full episode; exhausted overage yields
`TIMEOUT` and `reward=None`. Every online optimiser therefore shares one
monotonic soft deadline created at action entry. A valid incumbent is always
available, and no exponential subproblem may start near the deadline.

Current policy: 180ms local solve budget; reuse a same-day incumbent route on a
late crew event, otherwise use the feasible value-first assigner; stop local
search anytime; substitute NN+2-opt for Held-Karp with less than 50ms remaining.
Runtime promotion gates use P95, maximum, cutoff count and true-engine status,
not mean latency alone.

## Objective

The game is a finite-horizon simultaneous stochastic game. The production
objective is expected win probability, with final-money difference as the
continuous tie-breaker used during search:

```
J(s) = P(M_us(T) > M_opp(T) | s)
       + epsilon * E[M_us(T) - M_opp(T) | s]
```

Farm profit alone is not the objective because our sales change the opponent's
realised prices. Opponent private stock is represented by a feasible interval,
not a guessed style label.

## Layer 1: finite-horizon economy MPC

Re-solve once per day and after a material market shock. The decision variables
are daily crop cohorts, animal purchases, land, crew, feed, fertiliser and sale
quantities. State transitions come directly from the engine.

The optimiser must enforce all of these jointly:

- cash is non-negative at every purchase point, not merely at season end;
- an animal purchase includes feed and servicing until its first cash return;
- a crop purchase includes planting, survival watering and harvest task demand;
- shed occupancy includes carried production that auto-drops at day rollover;
- market revenue uses unit-by-unit inventory repricing;
- land has value only for tiles the task layer can actually service;
- opponent supply is bounded from visible crops/animals and inferred holdings;
- opponent purchases are excluded until their public cash can afford them;
  affordability is necessary, not a claim that they will choose the purchase.

Market revenue is nonlinear but discrete. For each product, precompute the exact
engine lookup `R[item, inventory, quantity]`; this turns revenue into table
lookup rather than approximation. The remaining problem can be solved with
dynamic programming or branch-and-bound over daily bundles.

Current implementation notes: `market_model.expected_town_take` conditions
known drain on the observed shop multiset and integrates still-hidden uniform
with-replacement shop unlocks analytically. V58 aggregates repeated optional
capital output by product before the exact `sell_revenue` call, and V59
recertifies the quantities that actually survive route trim. V60-V64 implement
constructive multi-day cash/labour/shed/order-slot portfolios and robust
both-seat quantity values, but their attempted production policies did not
pass the paired-win gate; they remain equation/test assets and tombstones, not
selected action paths.

The required output is not a fixed portfolio. It is a vector of shadow prices
and feasible targets for the current state:

```
Plan = {
  crop_cohorts,
  animal_targets,
  land_target,
  cash_reserve,
  labour_shadow_price,
  shed_shadow_price,
  product_shadow_prices,
}
```

The current `whitebox/capital.py` is the first one-step relaxation of this
layer. Computed acquisition orders are proposal ceilings, not commitments.
Each proposed seed/animal unit becomes an optional executable task column with
per-unit cash, one shared product-order key and (when needed) a shared fixed
BUY_LAND activation. The route master chooses the column or drops the purchase.
This closes the immediate asset-without-labour failure, but it is not yet the
multi-day cash-flow DP described above.

## Layer 2: task DAG

Every candidate is an engine-valid task bundle with prerequisites, deadline and
terminal marginal value. Examples:

```
animal service: PICKUP WHEAT -> FEED -> CARE -> HARVEST
crop start:      PLANT -> WATER
fertilised crop: PICKUP FERTILIZER -> FERTILIZE -> WATER -> HARVEST
animal start:    BUILD -> PICKUP animal -> PLACE
```

Hard survival conditions are constraints, not large arbitrary weights:

- an animal at `consecutive_unfed == 1` must be fed or explicitly abandoned;
- a crop at `consecutive_unwatered == 1` must be watered or explicitly abandoned;
- atomic same-crop planting cannot exceed seed stock;
- prerequisites must occur before their dependent operation;
- a unit cannot spend more turns than remain in the day.

Optional-task value is the change in the relaxed terminal objective:

```
value(task) = V_relaxed(apply(task, state)) - V_relaxed(state)
```

This replaces fixed numbers such as `FEED=900` and `HARVEST=240`. The value of
HARVEST depends on product, quantity, book depth, future production blocked by
`max_held`, shed pressure and remaining selling opportunities.

## Layer 3: prize-collecting multi-worker routing

The correct daily route is an **open** prize-collecting multi-vehicle route.
Harvested goods do not require an immediate return trip: the engine auto-drops
all unit inventories at day rollover, subject to shed capacity. Therefore the
old `WB_EXACT_TOUR` split that prices every HARVEST/COLLECT as an independent
shed round trip solves the wrong problem and must remain disabled.

For a fixed worker route, exact cost is:

```
one PICKUP per required input product
+ Manhattan length of the open tile path
+ number of tile operations
+ optional early DROP cost when same-day sale/overflow makes it valuable
```

The proposed solver is a decomposition:

1. Mandatory survival bundles are inserted first.
2. Stable spatial zones provide small candidate sets and prevent turn-to-turn
   route oscillation.
3. Each worker's pricing subproblem is an exact orienteering DP over its zone.
4. A master auction/Lagrangian loop moves tasks between workers according to
   marginal route cost until no improving transfer remains.
5. Replan only at day start or a material event (hire, new animal/structure,
   destroyed crop); preserve already-committed route prefixes otherwise.

### Hiring is part of the routing master problem

A hired hand is not an abstract increment to labour capacity. For every
candidate hire count `k` at hour `h`, solve the complete route allocation again
for the old workers and the `k` new workers:

```
F(k, h) = max total terminal task value over all worker routes
score(k) = F(k, h) - F(0, h)
           - sum(fib(hires_today + j), j=0..k-1)
```

The candidate workers start at `h+1`, have `23-h` turns, and spawn on the
least-occupied shed-access tile after the current units have acted, with the
engine's NW/NE/SW/SE tie break. Each hire also consumes one market-order slot.
The optimiser selects `argmax score(k)` subject to cash, slot, deadline and
end-of-day constraints. It reassigns all tasks; it does not value a hand as a
fixed fraction of the previous plan's undone operations.

Hire Fibonacci counters are per farm. An opponent HIRE never changes our hire
price. Simultaneity still matters through the opponent's newly available task
capacity and the resulting future product-supply interval, which feeds Layers
1 and 4 rather than contaminating the exact hire-cost equation.

The current implementation now has a first deterministic primal solver for this
master problem. It inserts survival/positive-dollar tasks by complete marginal
route cost, enforces global carried-input stock, relocates tasks across workers,
exchanges higher-value leftovers for lower-value assigned work, and refills the
released capacity. Final open routes of at most ten unique stops are exact
Held-Karp paths; larger routes use deterministic nearest-neighbour + 2-opt.

A crew-size event preserves each incumbent's first still-live target as a
forced route prefix, then jointly reoptimises every uncommitted task and every
new worker. This prevents a hire from making the old crew reverse direction.
It is still a primal heuristic, not the exact route-column/master-auction
decomposition described above. The experimental `whitebox/capital.py` now makes
proposed seed, animal and land acquisitions optional columns in this same solve;
each legal hire count adds actual spawned workers at `h+1`, and cash/order/input
activations are shared across routes. This is the correct coupling, but it is
default OFF because its n=18 margin gain is statistically underpowered.

### Qualified terminal route column

V69 replaces a fixed last-eight-step collector with a current-state proof after
the final possible production refresh. A constructively closed partial terminal
route aggregates all repeated products before exact nonlinear both-seat
clearing. It may replace the live general route only when

```
terminal_paired_value > optimistic_general_route_paired_value_upper_bound
```

where the general bound follows its live stop order, charges every remaining
movement/operation/return/DROP action, credits complete HARVEST plus
COLLECT_FERTILIZER output, and optimistically omits missing-input economic cost.
Exact ties preserve the general route. Current carried stock is rescued only
when the general suffix plus DROP cannot fit the remaining action count but a
direct shed leg plus DROP can. This formulation has no takeover step, fitted
tolerance, memory, opponent style label, or target count.

V69 passed valid 108- and 288-cell standard simulator gates and a six-seed,
both-seat real-engine standard gate against immutable V59; see `HANDOFF.md` for
absolute margins, paired deltas, controls, status counts, runtimes and logs. It
was the selected white-box baseline and is now V76's immutable comparison
baseline.

Two later audits constrain the next implementation. First, a conserved
100-item hidden-shed allocation is exactly inert for one terminal market phase
under paired seats: averaging both commit orders cancels opponent quantity and
leaves our standalone nonlinear revenue. Hidden supply can matter only through
book state across distinct sale times, not as an independently duplicated
terminal allowance. Second, market purchases and hires arrive after current
unit actions. V71 proved that shifting only route time/position while retaining
pre-action tiles, tasks and private stock is inconsistent and strongly
regressive; V72's all-PASS partial switch was timing-nondeterministic. A future
phase-correct master must first construct one complete deterministic post-unit
snapshot, then regenerate ordinary and capital columns from it. Partial
runtime switches are not promotable. Exact negative evidence is in
`HANDOFF.md` sections V70-V72.

V73 implements that missing transition as an isolated arm. It copies the exact
farmer-then-hands engine equations for movement, DROP/PICKUP/PLACE, every tile
operation, inventories, seeds and yield removal, including the phase-level
atomic rule that rejects all same-crop PLANT requests when aggregate demand
exceeds starting seeds. It deliberately does not advance the clock, market,
town, decay or daily refresh: those occur after market orders. Market orders,
strategy state, ordinary tasks and capital columns are regenerated from the
projected snapshot; routes start at `hour+1`, and hiring spawn occupancy reads
the projected positions without replaying unit movement. Its valid quick
paired gate was strongly negative, so it is retained only as an engine-fidelity
tombstone and V69 remains selected; exact margins and controls are in
`HANDOFF.md`.

The target online one-day master, of which the current capital solver is a
one-step relaxation without the full robust externality term, is:

```
max_x,z,k  sum(route_terminal_value[r] * x[r])
           - hire_cost(k) - robust_market_externality(x, opponent_set)
s.t.       one route per live/candidate worker
           task, worker-turn, carried-input and shed-capacity constraints
           asset/hire activation => exact cash and market-order consumption
           new workers spawn after current unit actions and act from h+1
           solve_time <= shared anytime deadline
```

Objective values generate tasks; tasks exist only inside executable routes;
routes determine the marginal value of hiring and assets. None of these three
objects is optimised independently and then treated as fixed by the next layer.

V74 isolates the remaining ordinary-task pricing defect. For every production
task with an unambiguous rule-derived product, it freezes the non-sale and
option-floor residual and aggregates proposal output by product before calling
the exact nonlinear revenue equation. Each task receives its physical-unit
share of the complete bundle revenue. Since marginal sale revenue is
non-increasing, the complete-proposal average is a conservative value for any
routed subset. Input opportunity costs remain standalone (also conservative),
and ambiguous BUILD/CLEAR tasks are not assigned a guessed product. V74 is not
selected pending paired qualification; exact evidence is in `HANDOFF.md`.

### Qualified selected-quantity route objective

V76 closes V74's linear-relaxation gap. Each identifiable task `i` is split
into its non-sale residual `b[i]` and exact rule-derived product output
`q[i,p]`. For a selected route/capital set `S`, the master uses

```
V(S) = sum_(i in S) b[i] + sum_p R[p](sum_(i in S) q[i,p])
Delta(i | S) = V(S union {i}) - V(S).
```

`R` is `econ.sell_revenue` on the current observed market after visible public
standing supply. Ordinary and capital output share the same quantity book;
asset/input costs remain explicit residuals and fixed land activation is paid
once. A lazy heap is exact for greedy marginal order because engine marginal
sale revenue is non-increasing. The online route primal is structurally bounded
and uses deterministic NN+2-opt emission, with no `perf_counter`-dependent
candidate path. The selected wrapper pins all inherited reachable `WB_*`
settings to the qualified constants rather than accepting environment-driven
policy switches.

Against immutable V69, V76 passed valid independent 108- and 288-cell standard
simulator gates (+$6,802.45, W-L 74-34; +$6,129.77, W-L 181-107) and a
six-seed both-seat real-engine standard gate (+$5,341.22, W-L 23-13). Mirrors
are exact, all real statuses are `DONE/DONE`, and two full runtime repeats stay
below 170 ms. Direct self-play mean margin is negative/uncertain in the larger
and real gates despite positive win counts; that residual risk is preserved in
`HANDOFF.md`. V76 is the selected strict-white-box baseline as of 2026-08-28.

V77 tested the next certificate/route seam without changing V76: the multi-day
certificate exposed an exact item-to-position assignment, routing received
those exact columns, and the actual retained assignment was recertified. This
closed the prior surrogate-position defect, remained deterministic, and stayed
inside the runtime soft target. Its valid 108-cell standard gate was neutral
(+$8,888 mean but only 55-53 paired improvements, with multi-route negative),
so it is a tombstone and did not advance to 288/real. The remaining equation
gap is inside the trim itself: route insertion uses the current-horizon bundle
marginal, then final branch selection uses the multi-day certificate. A future
arm must provide one exact selected-set multi-day marginal oracle to both steps
under a structural evaluation bound; item-specific tuning is not a substitute.

V78 implemented that exact cached selected-set marginal, and V79 repaired the
market-phase timing by projecting committed unit actions and starting all
capital-supported routes at hour+1. The equations and determinism tests pass,
but neither policy survived the quick external gate: V78 was -$6,651 with W-L
6-12; V79 was nominally +$893 but W-L 7-11 and therefore a regression. V79 also
showed 187-198 ms tails. These are tombstones. The remaining certificate defect
is calendar consistency: the proof begins at the next modelled day while live
inventory execution begins at hour1 of the purchase day. Do not tune asset
counts around this mismatch; either prove the same-day cash/labour/feed segment
exactly or work a different architecture layer.

V80 proved that remaining segment exactly. It advances crop/animal event
calendars to the purchase day, delegates today's asset operations to the
post-market hour+1 master, defers first animal feed according to the two-night
starvation rule, invalidates the route once on an observable capital increase,
and enforces `min cash >= reserve + current hire cost`. Physical certificates
are shared across crew arms without sharing their cash verdicts. The result is
mechanically coherent but decisively worse externally (-$23,935, t=-3.24,
W-L 5-13, all three rows negative). V77-V80 therefore close this integration
line as tombstones. Further work must select another architecture gap rather
than tune the certified portfolio's item counts.

V81 tested the independent gap between V76's greedy route primal and the
router's finite relocation/exchange/refill equations. It used the same exact
selected-set nonlinear objective with no deadline or fallback, and historical
paths remained disabled by default. The candidate was exactly deterministic,
but a full trace reached 335 ms with 22/719 calls above the 180 ms soft target.
Its quick hard-pool delta against V76 was -$7,534 (W-L 10-8), with negative
self-play and two negative opponent rows. It is a runtime-invalid neutral
tombstone. A future refinement must first derive a smaller finite work bound;
introducing a clock cutoff would violate the production contract.

V82 and V83 tested coefficient-free replacements for the remaining steady-sale
heuristics. V82 capped hour-zero sales by the exact lower town drain conditioned
on current shops and sold intraday only to prevent provable 100-item shed
overflow. It was deterministic and fast but starved bridge cash, regressing
-$190,538 with W-L 0-18. V83 instead liquidated all non-feed stock at the exact
day-boundary inventory cadence. It was baseline-like in runtime and behavior,
but its nominal +$609 quick mean came from only 13 firing cells with W-L 4-9,
so it is also a regression. The two extremes show that absorption value and
cash option value must be optimized together in a multi-day market/capital
objective; neither a fixed-seed pace nor coefficient-free endpoint policy is
sufficient. V76 remains selected.

V84/V85 then isolated same-phase sale financing. For live sale vector `q` and
one conserved hidden opponent shed allocation `h`, the exact safe cash is

```
min_(sum h[p] <= 100) sum_p sell_revenue(q[p], book_after(h[p])).
```

A bounded min-plus DP enforces the shared 100-item capacity and exact $1-floor
book semantics; the executable queue places certified sales before every
dependent spend. V84 attached this proof to day-boundary sell-all and degraded
all three external rows (-$7,493/cell aggregate). V85 attached it only to
V76's already-selected sale vector and again degraded all rows (-$5,595,
W-L 7-11), with repeat soft-target misses above 182 ms. Both changes fired in
18/18 cells. The feasibility theorem survives; the one-step capital objective
does not. Reuse requires a joint multi-day objective whose state includes cash,
retained inventory, shed room and opponent-relative terminal value.

V87 isolated the retained-stock side without changing V86's selected capital.
For current sale bundle `q`, public book `I`, exact one-step town drain `d`, and
one conserved hidden opponent shed allocation `h`, it computes

```
min_(sum h[p] <= 100) sum_p (
    R(q[p], book_after(I[p] - d[p], h[p]))
  - R(q[p], book_after(I[p], h[p])))
```

with exact floor-book semantics and one shared capacity DP. The queue is
post-processed only after capital selection and only if it contains sales
alone; current DROP, cash below the computed service reserve, daily rollover,
or crossing into endgame vetoes the delay. Because town drain can only lower
book inventory, waiting is never worse for any allocation; it is selected only
when the zero-hidden allocation is strictly better. V86 re-evaluates next turn,
so no memory or hidden-state commitment is introduced.

This theorem produced only a neutral policy effect: standard108 versus selected
V86 was -$3.82/cell (SE $7.91, t=-0.48), 14/108 firing, conditional W-L 8-6;
self-play was -$248 total. The hardest multi-route row was -$57.89/cell while
two easier rows were positive. V87 is not promoted and did not earn 288/real.
The missing mechanism is not another one-step timing gate but a structurally
bounded multi-day selected-set objective coupling retained stock, cash/service
feasibility, shed room, order slots and opponent-relative terminal value.

V88 solves the exact terminal boundary case of that objective. Once the
state-derived closed terminal route strictly dominates the general-route upper
bound, no newly purchased capital or service work can produce before the last
action. For certified total output `Q[p]`, current sale `q[p]`, current book
`I[p]`, and guaranteed public drain `d[p]`, its separable product term is

```
R(q[p], I[p])
+ R(Q[p] - q[p], inventory_after_sale(I[p], q[p]) - d[p]).
```

Paired-seat market-order cancellation applies phase by phase because each
phase closes at the same combined book in both seat orders; opponent quantities
therefore cancel without a policy model. A quantity/slot DP combines the exact
product terms, requires `sum(Q)-sum(q) <= shedCapacity`, includes non-sellable
shed occupants in that capacity, and uses at most ten orders. Exact ties retain
more stock. The final action is `episodeSteps-2` from public configuration.

The equation is valid but insufficient as a policy improvement. Standard108
against V86 was -$2.43/cell (SE $41.61, t=-0.06), 82/108 firing and conditional
W-L 41-41; self-play was -$1,103 and three of six pool rows were negative. A
maximum-shape solve measured 21.3 ms mean, adding tail risk to inherited route
tails. V88 is not promoted and did not reach 288/real. General-horizon value
must couple sale cash with productive service and capacity before terminal
closure rather than rely on terminal retention alone.

V89 closes the independent runtime prerequisite without changing the economic
model. In one immutable-V86 profile, capital selection made 2,365,329 calls to
the pure route-cost function; lazy nonlinear repricing repeatedly requested the
same singleton and selected-set costs. Within one `joint_assign` solve, route
cost depends only on

```
(worker, multiset(selected task identities), committed prefix, bank-output mode).
```

V89 memoizes that exact mapping for the duration of the solve and discards it
immediately afterward. Task identities are cache keys only and never enter an
ordering, score or emitted action. Worker geometry and bank-output mode are
constant within the solve; the prefix is explicit in the key. Thus memoization
removes duplicate evaluation of the same NN+2-opt equation but cannot change a
feasible set, marginal, tie-break or route.

The optimization is action-identical to V86 on a 719-step deterministic trace,
18 hard-pool cells, 108 standard-pool cells and 36 both-seat real-engine cells.
It reduces seed26800 mean/P95/P99/max latency by
25.0%/27.2%/27.7%/30.7%, from a V86 maximum of 182.87 ms to repeat maxima of
126.76 and 127.57 ms. V89 is selected for runtime safety only; all unresolved
productive-horizon inventory/cash/service equations remain unchanged.

V90 and V91 test the first general productive inventory coupling while keeping
V89's proposal fixed. Both compare V89's current sale bundle with retaining it
to the selected portfolio's first certified output, and both prove positioned
routes, daily feed/hire cash, shed peaks, slots and fixed land activation. V90
credits only the first robust output and regresses -$154,656.83/cell, W-L 0-18.
V91 credits every robust output under one conserved hidden allocation and still
regresses -$125,091.78/cell, W-L 0-18. Both are deterministic and below 103 ms.
The failure is therefore not omitted later revenue: substituting a standalone
full-season capital objective for V89's joint selected-set score suppresses the
coupled route/hire/capital trajectory. V92 preserves V89's score exactly and
uses the proof only as a feasibility oracle, yet still regresses
-$36,580.33/cell with W-L 1-17. Thus a hard full-season worst-case certificate
also over-restricts an agent that replans daily. Future production arms should
certify only obligations unavoidable before the next public replan, or repair
actual current quantities after routing; V92 remains an audit oracle.

V93 tests the latter repair seam while leaving V89 route selection and value
unchanged. It recertifies actual routed quantities and iteratively removes the
capital column with least exact V89 score loss. The hard-pool result is still
-$37,996.67/cell (W-L 6-12): multi-route is neutral, while frontier and v111
each lose about $56k-$59k/cell. Thus both in-marginal and post-route enforcement
are rejected. Full-season certificates remain audit assets, not production
constraints; do not tune their uncertainty set around opponent rows.

V94 narrows enforcement to the exact last productive placement day. It
projects the current unit phase (capital is bought afterward), validates target
tile preconditions, and asks whether the remaining crew can complete only the
new asset's initial operations before day end. This is a necessary relaxation:
ordinary work is not charged and no later-day service is assumed. The quick
hard-pool gate is exactly action-identical to V89 in all 18 cells, so the
constraint is empirically inert on that sample. Keep it as an explicit timing
equation and do not promote it or spend a larger gate without firing evidence.

V95 moves to a different gap: the route objective was still an own-bank lower
bound because it reserved visible opponent stock ahead of our selected output.
For a simultaneous phase, both seat orders cancel every opponent quantity and
leave our standalone nonlinear revenue. V95 substitutes exactly that output
term after removing the old one; every non-sale residual and V89 physical
constraint remains explicit. Its standard108 evidence is -$275/cell, W-L
51-57, with five negative opponent rows and full firing. Do not promote it or
extend it to 288/real. A future opponent-relative productive objective must
preserve sale time and persistent book state instead of collapsing the whole
stream into one simultaneous phase.

V96 implements that dated state exactly: rule-derived output days, one
persistent public book, guaranteed current-shop drain, and one conserved stock
of currently visible opponent yield across phases. Its full selected-set
marginal remains runtime-invalid after structural memoization (315-318 ms
maxima and 20 calls above 180 ms per repeat). V97 therefore routes with V89 and
recertifies only each complete branch's actual quantity on the dated equation.
That bounded seam is runtime-safe, yet standard108 regresses -$2,638.82/cell
(t=-2.47), W-L 48-60, with five negative rows. Both are tombstones. Do not add
a fitted phase weight, opponent reserve, row switch or clock fallback.

V98 tests the complementary finite-horizon construction. Proposed assets are
certified only through first output with minimum engine survival: alternating
WATER/FEED, no first-yield CARE, pickup-aware closed routes, exact daily hires,
feed/cash/shed/slots, grouped nonlinear sale and fixed activation. Pending
private capital consumes physical tiles, and the bounded no-land/land inventor
has a structural certificate-count limit rather than a clock cutoff.

The mechanism is executable and runtime-safe but decisively wrong as a
production objective: quick18 is -$145,463/cell (t=-9.15), W-L 0-18. Its
standalone new-capital routes do not share future labour with the existing
farm's ordinary service stops, and the horizon gives standing capital no
post-first-output residual. The next MPC must merge both stop sets inside one
dated resource system and derive a terminal feasibility/abandonment interval.
Do not repair V98 with fitted tail weights, fixed counts, or V90's rejected
full-season obligation.

V99 repairs the one-time-crop production equation before that joint model is
built. Under the exact minimum survival path, WATER-before-HARVEST produces
WHEAT=2, CARROT=2 and MELON=4 at earliest maturity; `max_yield` is not present
unless enough growth-window WATER actions actually occurred. V99 remains a
decisive -$98,403/cell, W-L 0-18 tombstone; its seed block differs from V98,
so the headline losses are not a causal A/B. The joint-farm prefix must inherit these
quantities, combine current-visible and proposed stops before daily route
packing, and use a rule-feasible zero abandonment residual rather than a
learned tail or full-season obligation.

## Layer 4: simultaneous market control

For each product and feasible opponent sale interval, evaluate our legal sale
quantities under both seat orders using the exact market commit rule. Select the
robust best response:

```
q* = argmax_q min_{q_opp in feasible(state)}
     [terminal_value_after(q, q_opp)]
```

The feasible interval comes from visible standing production, travel-to-shed
bounds, inferred holdings, the 100-item shed constraint and public opponent
cash. `Horizon.cash/can_afford/affordability_gap` supplies the exact finance
bound; hidden intent remains an uncertainty set. No opponent tape or behavioural
class is needed.

### Audit of the current DUSK/HORIZON code

The historical names do not imply that their current implementations satisfy
this architecture:

- `opp_clear_round = 719-(ceil(animals/workers)+1)` is not a physical bound. It
  omits worker/animal positions, harvest eligibility, return travel, DROP and
  private stock. Replace it with lower/upper feasible liquidation times from a
  terminal routing problem.
- The white-box endgame collector is called independently per unit, so workers
  do not share target claims or shed-capacity reservations. Its reachability
  test also omits tile-to-shed return distance. Terminal unit actions and market
  orders must be solved jointly so a same-turn DROP can generate a SELL.
- `earliest_sellable` receives a day rather than the live step, can return a
  time earlier than the current hour, and charges only one tile's round trip
  after accumulating volume across several tiles. It also assumes one future
  unit per producer rather than a rule-derived yield interval.
- `OpponentTracker` holdings are estimates, not exact observations. Invisible
  $1 sales, crop/animal loss and shed overflow require lower/upper bounds.
- `horizon.sense()` is currently invoked, but market code still reads the raw
  opponent model/tracker directly. HORIZON must become the single interval API
  before its cache and semantics can be trusted by several consumers.

The replacement is a small robust terminal solver over the final horizon:

```
max min_opponent  final_money_difference
variables: unit routes, harvests, drops, sell quantities, market slots
constraints: exact remaining turns, worker start positions, shed capacity,
             unit inventories, market commit order, feasible opponent stock
```

Unlike a fixed eight-step takeover, this solver switches objectives when the
state-dependent value of production work falls below liquidation work.

## Implementation order

1. Keep the anytime incumbent and true-engine timeout gate on every solver edit.
2. Extend the one-step optional capital columns into a multi-day cash-flow
   bundle generator which can invent portfolios rather than only trim proposals.
3. Convert HORIZON point estimates into lower/upper feasible stock, route-time
   and purchase intervals, using public cash as a hard feasibility boundary.
4. Add the robust simultaneous-sale optimiser over both seat commit orders.
5. Replace the primal route heuristic only if its residual 42.8% relaxation is
   still binding after the value/cash/market master is qualified.

## Promotion gates

A change is promoted only when it passes all gates:

- identity/control path is exact;
- no import or runtime reference to tape/replay action modules;
- no illegal actions in engine traces;
- cash-feasibility, crop-survival and animal-survival invariants pass;
- common-random-number holdout improves paired win rate and margin; own bank is
  diagnostic only and cannot promote a change;
- at least 100 independent paired games and enough firing games for a mechanism;
  major default-path changes require at least 288 paired simulator cells;
- simulator sign is confirmed on multiple seeds and both seats in the real
  engine before default promotion or submission;
- no real-engine timeout, and latency headroom survives a slower-machine stress
  factor. Current-engine and historical-replay simulator fidelity are separate
  versioned tests.

## V100 boundary result: existing-load marginal is insufficient

V100 implements the finite joint-farm relaxation

```
candidate value = combined exact-prefix value
                - identical dated visible-farm baseline
```

The baseline reserves rule-minimum alternate-day WATER for visible ongoing
crops and FEED plus WHEAT pickup for visible animals. It shares routes, hires,
feed-price clearing, order slots and bridge cash with proposed capital. Visible
one-time crops and every post-horizon asset have an explicit zero abandonment
residual. This satisfies the white-box boundary and isolates the intended
shared-congestion term.

It is nevertheless structurally inadequate and empirically rejected
(-$112,877/cell, W-L 0-18 on quick18). The first day-0 capital decision has no
visible standing farm, so subtracting an existing-load baseline adds no
opportunity cost exactly when the irreversible oversized portfolio is bought.
A successor must value the proposed asset's own finite-horizon continuation or
abandonment opportunity at purchase time without imposing V90's full-season
tail. V100 also repeats a 234 ms call and therefore fails runtime safety even
apart from margin. It is an architecture tombstone, not a fallback or switch.

## V101 boundary result: terminal endpoints do not couple future replans

V101 tests a coefficient-free continuation envelope: exact first-output
abandonment versus exact minimum-service continuation through all reachable
base outputs. Both endpoints separately prove routes, feed, cash and clearing;
continuation is never imposed when abandonment has higher feasible value. The
arm changes 24 MELON into a recurring/diversified 24-slot bundle and remains
runtime-safe, so the terminal endpoint is economically active.

The quick gate is still -$93,637/cell with W-L 0-18. A standalone program can
be internally feasible while the observation-by-observation production policy
does not commit to executing that program. Maximizing any positive standalone
capital endpoint therefore fills physical capacity and changes the whole
trajectory. Further endpoint scalars, service-cadence variants and item-count
repairs are closed by V98-V101. Continue with the distinct terminal
route/liquidation interval gap; do not install V101 as a fallback.

## V102 terminal trip-structure closure

The ordinary-route upper bound already chained live stops before one final
return and DROP, but the terminal primal paid a return/DROP after every target.
The strict opportunity comparison was therefore physically asymmetric. V102
uses, for each worker,

```
distance(start, first) + operations(first)
+ sum(distance(previous, next) + operations(next))
+ distance(last, nearest_shed) + DROP
```

and treats current carried goods as the chain's initial load. Unique claims,
exact crop-decay offsets, complete tile output, aggregate nonlinear clearing,
production closure and strict terminal dominance remain unchanged. The sum of
current carried and selected output cannot exceed the shared 100-item final
shed capacity, so simultaneous final drops are constructive. This contains no
fixed takeover step, fitted route coefficient, opponent identity or hidden
schedule.

The unchanged wrapper is qualified against immutable V89: quick18 +$526/cell
(17-1), standard108 +$795/cell (90-14 plus four inert ties), independent
standard288 +$759/cell (259-25 plus four inert ties), and installed real36
+$863/cell (34-2). All qualification rows are positive, mirrors are exact,
all real games complete `DONE/DONE`, and repeated seed31000 decisions remain
below 142 ms. V102 was the selected strict-white-box wrapper and remains V103's
immutable comparison baseline; V89 remains an earlier immutable baseline.

## V103 terminal insertion closure

V102's exact-marginal primal could only append a target after the current
worker endpoint. V103 tests that target at every insertion position of every
worker chain. Each trial recomputes the complete closed route and every
HARVEST offset, so an insertion that causes an already selected crop to decay
is infeasible. The economic ordering is unchanged; complete and incremental
closed length break only exact-gain ties. No route-value coefficient, fixed
count, clock branch or remembered commitment is introduced.

Against immutable V102, standard108 is +$85/cell (57-46, five inert),
independent standard288 is +$60/cell (171-104, 13 inert), and enlarged
installed real108 is +$42/cell (66-33, nine inert). Every simulator288 and
real108 row mean is positive, mirrors are exact and all 540 enlarged real games
finish `DONE/DONE`. Direct enlarged real self-play is -$2,596 (7-11), retained
as contrary evidence. V103 is selected; V102 remains immutable.

## V104 terminal one-exchange experiment

V104 starts from V103's certified inserted route set. For each selected and
rejected target pair, it removes the selected target, forces the rejected one
at its shortest exact insertion, then refills with the unchanged exact bundle
marginal. A candidate is actionable only when every closed route, crop-decay
offset, complete output bundle, and shared final shed capacity remains feasible;
it replaces V103 only under a strict increase in the same paired value. The
single exchange neighborhood is a mathematical neighborhood definition, not a
fitted iteration count. V104 is deterministic and runtime-safe, and its
standard108 aggregate is +$36/cell with conditional W-L 36-17. However, only
53/108 cells fire, confidence crosses zero, and v111/strong-barnyard row means
are negative. It receives no 288/real gate and is retained as an unpromoted
positive/neutral tombstone. V103 remains selected.

## V105 complete shared-slot capital alternatives

V105 removes proposal-order tile reservation from the current daily capital
master. Every proposed asset type receives every tile in the finite frontier
needed to place the proposal; exact item quantity limits and a per-tile
exclusive key preserve physical feasibility. The existing bundle objective,
cash, order-slot, hire, route and fixed-land equations choose among these
columns. No proposal quantity or value equation changes. V105 is experimental
pending runtime and CRN evidence; V103 remains selected.
Runtime and closure pass, but quick18 is -$7,056/cell (SE $3,445), W-L
5-13, with every hard-opponent row and direct self-play negative. V105 is a
rejected tombstone and receives no larger gate. Its physical alternative-set
equation remains an audit primitive; V103 stays selected.
