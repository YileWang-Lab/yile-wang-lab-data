# Kaggriculture public-code audit (2026-09-12)

This is an offline audit of public Kaggle notebooks, not a claim about their
private agents or leaderboard strength.  The snapshots were obtained with the
Kaggle CLI on 2026-09-12 and inspected as source/markdown only.  No external
notebook was run as our production policy and no public action table was copied
into the runtime.

## 1. White-box boundary

The production policy may use only the current observation, public engine rules,
our own state carried between callbacks, and deterministic calculations over
those inputs.  In particular, these are not legal runtime inputs:

- replay IDs, episode IDs, seeds, team/opponent identity, ladder rank, or source
  file names;
- compressed or literal action tapes, route IDs, schedule tables, or future
  actions recovered from a replay;
- fitted action frequencies, hidden inventory estimates, or assumed future
  prices/shops;
- fixed leader dates, coordinates, asset counts, or compositions unless they
  are derived from the live state and engine constants.

The current production baseline remains
`whitebox/versions/v204_retained_land_commitment.py`.  V206, V208, V209,
V210, and the newly present V211 daily-feed wrapper are research variants and
are not promoted by this audit.  The static closure audit passes for both V204
and V211; this is a dependency check, not a strength result:

```text
python scripts/audit_whitebox_runtime.py \
  --entry whitebox.versions.v204_retained_land_commitment \
  --callable whitebox_v204_retained_land_commitment
```

## 2. Public snapshot inventory

The following are the most relevant public sources in the current competition
listing.  “Tape” means that the executable policy is ultimately driven by a
precomputed route/action archive, even when a small public-state wrapper is
present.

| Public source | Observed focus | Runtime class |
| --- | --- | --- |
| [Thomas 95.5% replay routing](https://www.kaggle.com/code/thomastschinkel/kaggriculture-95-5-win-rate-via-replay-routing) | Six-day opening, step-144 market regime, prefix-compatible tail splice; 5 embedded schedules | Tape; mechanism reference only |
| [Thomas 93.8% public-state router](https://www.kaggle.com/code/thomastschinkel/kaggriculture-93-8-win-rate-public-state-router) | YARN/milk demand and carrot-price checkpoints, low-frequency route switching | Tape; mechanism reference only |
| [Thomas 74.5% public-state router](https://www.kaggle.com/code/thomastschinkel/kaggriculture-public-state-router-74-5-win-rate) | Three public triggers plus weed-dig, dead-stock and sell-clamp repairs | Tape; mechanism reference only |
| [Lynn Farming Score](https://www.kaggle.com/code/lynnsakurai/farming-score-a-mathematical-approach) and [V4](https://www.kaggle.com/code/lynnsakurai/farming-score-v4-a-better-shop) | Route programs, projected shed, terminal settlement, opening-liquidity and survival guards | Tape; rule-level pieces transferable |
| [Yusuke Shop Router 0909](https://www.kaggle.com/code/yhay81/shop-router-0909) | Shop-pair route mode, weed repair, projected shed, bounded sale advancement | Tape; rule-level pieces transferable |
| [Tetsutani Market Smart Farming](https://www.kaggle.com/code/tetsutani/market-smart-farming-kaggriculture) | Four/five-own-action sale reservation, block boundary and exact debt ledger | Frozen parent tape plus narrow timing layer |
| [Dmitrii Herd-Safe Sale Window](https://www.kaggle.com/code/dmitriigluzdov/kaggriculture-herd-safe-sale-window-lb-2700) | Two-turn sale reservation, stock-consumer barriers, debt repayment and abstention | Tape-derived future sales; rule-level pieces transferable |
| [Dmitrii Seven-Turn Rescue](https://www.kaggle.com/code/dmitriigluzdov/kaggriculture-7-turn-rescue-historical-lb-2800) | Terminal physical planner, bundle proposals, dominance and mismatch abandonment | Parent tape; terminal certificates transferable |
| [Prvsiyan Soil Remembers Rain](https://www.kaggle.com/code/prvsiyan/kaggriculture-frontier-the-soil-remembers-rain) | Late cattle substitution and day-12 six-sheep stress/admission experiment | Tape parent; stress model is not a runtime forecast |
| [Pilkwang Structured Economic Policy](https://www.kaggle.com/code/pilkwang/kaggriculture-structured-economic-policy) | Explicit two-scenario six-sheep admission; marked unverified and submission-disallowed | Tape parent; admission form is research only |
| [Ahmed More Yield, Smarter Labor](https://www.kaggle.com/code/ahmedberatozer/more-yield-smarter-labor) | V37 finite fertilization, warehouse guard and tomato labor assignment | Tape parent; candidate reported mixed elite-field evidence |
| [Adaptive Farming Strategy](https://www.kaggle.com/code/tetsutani/adaptive-farming-strategy-for-kaggriculture) | Five coherent routes selected by first shops plus local execution guards | Tape; route selector abstraction transferable |
| [Flexonafft Most Powerfull Route](https://www.kaggle.com/code/flexonafft/kaggriculture-most-powerfull-route) | Reactive sheep expansion, sale/room/weed guards, finite crop and labor overlays | Tape; no independent white-box backbone |
| [Georgy What 2600+ Farms Do Differently](https://www.kaggle.com/code/georgymamarin/kaggriculture-what-2600-farms-do-differently) | Live replay/ladder fingerprints and market diagnostics | Offline data analysis; no policy runtime |
| [Rayk Rank Your Agent](https://www.kaggle.com/code/raykkretzschmar/kaggriculture-rank-your-agent) | Engine-pin fixture, seat-swapped round robin, Bradley–Terry ladder and held-out tests | Evaluation harness; no policy runtime |

## 3. What the leading public routers actually do

### Thomas: low-frequency regime selection, not online planning

The 95.5% and 93.8% notebooks share a fixed opening and inspect public town and
market state at a few checkpoints.  Tail switching is permitted only when the
opening prefix is exactly compatible.  The public vector includes shop demand,
market inventory/price, farm tile population, cash and unlocked quadrants.  The
93.8% variant then uses another carrot-price checkpoint late in the season.

The 74.5% public version reports the same pattern: a baseline route, three
public-state checkpoints, and small repairs.  Its reported rejected changes are
also useful evidence: “sell before buys”, “hire last”, unaffordable-buy deferral,
and feeding/caring on idle turns were not universally helpful.

Transferable white-box form:

1. Build a small, named set of route *modes* from the current public regime.
2. Commit to a mode for a bounded block; do not oscillate each callback.
3. Switch only when the current state satisfies a feasibility certificate, not
   because a replay reached a particular step.
4. Keep local repairs (weed, capacity, sale fill) conservative and failure-closed.

The schedules, route labels, compressed trees, fixed checkpoint numbers and all
future actions are excluded.  They are the performance backbone of those
notebooks and violate our runtime contract.

### Lynn and Yhay: physical inventory accounting

The strongest portable implementation detail is `projected_shed`: apply the
current worker PICKUP/DROP/PLACE (and known production) in order, then reason
about the stock available to SELL.  Their terminal layers preserve existing
orders, deduplicate SELLs, add only physically fillable positive inventory and
respect the ten-order cap.

Yhay's `repair_weeds` turns a blocked PLANT/BUILD or an idle worker standing on a
WEED into DIG, delaying only that worker's same-day queue.  Its sale advancement
is bounded by already planned own SELL quantities and stops at PICKUP, same-item
BUY, ambiguous animal return, or the next 72-turn shop block.  These are useful
state barriers; the source's `actions.json` and route-plan indices are not.

Lynn V4's opening-liquidity guard is a readable budget certificate: reduce only
fixed-price WHEAT seed orders when the live day-0 cash would otherwise fail to
retain the named day-1 hire liquidity.  Its survival guard identifies an animal
with `consecutive_unfed >= 1`, finds a WHEAT carrier and routes a FEED repair.
That repair is best effort, not a proof that every animal is covered; V204 still
needs a hard coverage certificate.

### Sale reservation and terminal rescue

Dmitrii and Tetsutani independently converge on a useful separation:

- reserve only stock already available after current worker actions;
- do not reserve product needed by a future PICKUP or same-item BUY;
- stop at a shop/block boundary and at ambiguous animal-depot returns;
- record an exact debt and subtract it from the corresponding future sale;
- if any precondition is unknown, preserve the parent action;
- near the deadline, solve physical reachability and shed capacity before
  liquidation.

The missing white-box abstraction in our code is a generic committed-work ledger
that can hold future WHEAT consumption, FEED obligations, PICKUP reservations,
planned sales, and capital purchase obligations without reading a tape.

### Livestock and crop investment experiments

Prvsiyan's public sheep experiment makes the trade-off explicit: land, six
sheep, feed and two workers are paid up front, while wool revenue is reduced by
an explicit delivery haircut and rival-adoption/feed-stress scenarios.  The
notebook itself warns that future service and prices are assumptions and that
the first sheep controller lost money despite producing more wool.  Pilkwang's
decoded `sheep_admission.py` is even clearer: it returns `UNKNOWN` and preserves
the parent if the public schema or scenario inputs are unsupported, and its
configuration says `strength_status=UNVERIFIED` and `submission_allowed=false`.

Ahmed V37 adds three inspectable ideas: finite fertilizer projects, a final-hour
warehouse overflow check, and cooperative tomato-worker assignment chosen by
physical path length and remaining callbacks.  Its own report says the
independent 136-game elite field had the same 81–55 record as V36; the large
reacting-policy gain is a separate, less demanding cohort.  It is therefore an
engineering reference, not promotion evidence.  Every V37 project still runs
on a compressed route parent and forecasts future route work, so only the
state-derived accounting pattern can be transferred.

## 4. First-quadrant animal question

The public evidence does **not** justify a universal rule “do not buy animals in
the first quadrant”.  Thomas's public opening is animal-heavy; Prvsiyan's
livestock branch waits for a very specific observed regime; Rayk's controlled
composition experiment found all-cow better than mixed cow/sheep on tuned seeds,
then worse on held-out seeds; Georgy's live meta notebook does not even publish
animal-purchase features, only crops, crew and first-land day.  These facts are
not contradictory: the value of an animal depends on feed coverage, worker
reachability, shed room, shop demand, and the remaining horizon.

As a concrete but non-general example, the decoded opening of Thomas's 95.5%
public schedule places `BUY_ANIMAL COW 2` and `BUY_ANIMAL SHEEP 2` in its step-1
market queue, before any paid land expansion.  The same schedule buys more cows
at later early steps.  This proves that at least one strong *public tape* uses
animals in the initial quadrant; it does not prove that this is the leader's
private policy, that the composition is optimal, or that the same purchase is
safe for our live state.  It is therefore evidence against a blanket gate, not
a rule to copy.

The correct white-box rule is therefore an admission certificate:

```text
allow animal purchase only if
  current cash/order slots pay the purchase,
  every animal has a reachable FEED carrier and WHEAT reserve,
  placement and service fit the remaining daily horizon,
  shed capacity and market slots remain feasible, and
  the worst declared *current-state* stress case does not destroy the
  parent plan's certified margin.
otherwise preserve the parent action (UNKNOWN => no purchase).
```

This supports investigating V211's FEED core and a future failure-closed animal
admission layer, but it does not promote V208–V210's broad first-quadrant gates.

## 5. Gap matrix against V204

| Public lesson | White-box translation | V204 status | Remaining gap |
| --- | --- | --- | --- |
| Low-frequency public regime routing | Named modes selected from shops/market/farm state | Partial: capital planner re-solves state | No explicit bounded mode/commit interface |
| Prefix compatibility | State certificate before changing a committed plan | Retained land obligation does this for one land ray | General committed-work identity is missing |
| Projected shed | Ordered PICKUP/DROP/PLACE projection before SELL | Present in task/capital layers | Not exposed as one reusable service |
| Bounded sale advance | Advance only safe, already committed stock | Partial room/clamp/dead-stock guards | Generic tape-free debt ledger |
| Weed repair | Local DIG and same-day queue repair | Task layer sees WEED | Need worker-local queue contract |
| Terminal physical planner | Reachability + positive deposit gain + liquidation | Present in terminal rescue | Make mismatch/dominance certificate explicit |
| Feed survival | FEED is a hard prerequisite | V206/V211 research switches | Multi-animal carrier/WHEAT hard cover |
| Capital admission | Pay purchase + service + shed + labor before commit | Capital certificates exist | Failure-closed animal admission and stress audit |
| Cooperative labor assignment | Enumerate finite assignments by physical time | Route planner has multi-worker assignment | Reusable bounded assignment certificate |
| Evaluation discipline | Pin engine, swap seats, hold out seeds, BT ranking | Existing arena tests | Consolidate into one low-token harness |

## 6. Recommended next experiments (all white-box)

1. **Committed-work ledger.** Define a small immutable record of future
   obligations created by our own accepted actions.  It must be updated only by
   observed confirmations and must never be populated from a route/tape.
2. **FEED hard-cover certificate.** For every animal with a future production
   event, prove a carrier, WHEAT quantity, reachable tile and FEED callback
   before accepting optional crop/land/animal work.  If any animal is uncovered,
   abstain from the optional work.
3. **Failure-closed animal admission.** Enumerate only the finite current-state
   purchase/service bundle; include Fibonacci hire cost, placement distance,
   feed reserve, shed/order slots and a conservative delivery haircut.  Unknown
   state returns the parent action.
4. **Tape-free bounded sale ledger.** Reuse the `SaleLedger` shape audited in
   Pilkwang's public source, but feed it only our own confirmed committed sales;
   no future action lookup is allowed.
5. **Service-route/shed Pareto certificate.** Accept new land or animals only
   when the finite route assignment preserves both service coverage and terminal
   shed capacity, rather than comparing standalone task scores.
6. **Reusable evaluation command.** One script should pin engine 1.32.7,
   run both seats over fixed holdout seeds, check `DONE/DONE`, conservation,
   timeout and source/package identity, and report paired wins/margins.  The
   replay corpus remains an offline diagnostic input to this script only.

No item above authorizes copying a public schedule.  Each candidate must pass
the static runtime audit and the paired holdout gate before promotion.

## 7. Audit artefacts and reproducibility

Downloaded snapshots used for this audit are in `/tmp/kaggle-audit-*` and are
not imported by `whitebox/agent.py`.  The public-list query was:

```text
/home/yilewang/kagg-env/bin/kaggle kernels list \
  --competition kaggriculture --sort-by voteCount --page-size 30 --csv
```

The audit intentionally keeps intermediate research variants and historical
opponent files as offline evidence.  They may be archived separately, but must
not be deleted or made reachable from the production package merely to reduce
file count.  The package closure, not the repository's total file count, is the
white-box boundary.
