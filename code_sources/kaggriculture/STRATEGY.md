# Kaggriculture — strategy notes (derived from source, not the write-up)

Source read: `kaggle_environments/envs/kaggriculture/kaggriculture.py` (1086 lines, v1.32.7).
Everything below is verified against code, not the competition description.

## 1. The game is MARKET-limited, not production-limited

`analysis/market_capacity.py` computes the revenue ceiling per product. Selling N units
evenly over days 10-29 (the shed cap forces spreading):

| product | 100u | 200u | 400u | 800u | ceiling |
|---|---|---|---|---|---|
| EGG | $54 | $51 | $43 | **$41** | **none — log decay** |
| WHEAT | $39 | $37 | $33 | $22 | none, but low value |
| MILK | $251 | $230 | $91 | $29 | ~$46k @ 200u |
| WOOL | $235 | $225 | $70 | $30 | ~$45k @ 200u |
| STRAWBERRY | $225 | $208 | $149 | $31 | ~$60k @ 400u |
| MELON | $238 | $163 | $78 | $38 | ~$33k @ 150u |
| FERTILIZER | $90 | $80 | $60 | $32 | ~$24k @ 400u |
| CARROT | $44 | $40 | $29 | $19 | ~$15k |
| TOMATO | $68 | $62 | $39 | $21 | ~$16k |

**Consequence:** produce each premium good only up to its saturation point, then convert
every remaining tile to geese. Eggs absorb unlimited volume at ~$40.

## 2. Findings that are not in the write-up

1. **Animals produce fertilizer unconditionally.** `_daily_refresh_animals` sets
   `fertilizer_available = True` for every surviving animal every day regardless of
   fed/cared status (line 831). Fertilizer is consumed by *nobody* in town
   (`TOWN_CENTER_PRODUCTS` excludes it, no shop demands it), so its price only ever
   falls — but 400 units is still ~$24k for one COLLECT action each. Free money.

2. **Animals survive on half rations.** `consecutive_unfed >= 2` kills. Feeding on
   alternating days keeps the counter at 0/1 forever. An unfed-but-alive animal
   *still produces its base 1 unit* — only the CARE bonus is lost.

3. **CARE is a large multiplier, and it banks.** `pending_care_bonus` accrues +1 per
   fed+cared day and is paid in full on the next scheduled production.
   - Goose (interval 1): 1 -> **2 eggs/day**
   - Cow (interval 2): 1 -> **3 milk / 2 days** (1.5/day, 3x)
   - Sheep (interval 3): 1 -> **4 wool / 3 days** (1.33/day, 4x)
   A production day where the animal is unfed *wipes the bank* (line 826-828).

4. **Optimal sale timing is "as late as possible".** Town drain is monotonically
   increasing, so market inventory is lowest — and price highest — at season end.
   The only thing preventing a single end-of-season dump is `shedCapacity = 100`.
   Corollary: hold premium goods as long as the shed allows; never dump early.

5. **Selling at the $1 floor does not add to market inventory** (line 659). Dumping
   worthless surplus is free and does not deepen the crash.

6. **`BUY_PRODUCT` quotes at `inventory - 1`** (post-buy), so a buy/sell round trip
   against an unchanged market nets exactly zero. No arbitrage there.

7. **Atomic PLANT validation is a trap.** If the total PLANT requests for one crop in
   a single turn exceed seeds held, *every* PLANT for that crop is dropped
   (lines 920-933). Must cap plant assignments per crop per turn.

8. **Labour is almost free early.** Hire cost is `fib(n)` for the n-th hire that day,
   cumulative `F(n+2)-1`: 10 hands = $143/day for 264 actions. 15 hands = $1,596.
   Marginal cost per action: ~$10 at 12 hands, ~$41 at 15, ~$167 at 20.
   Sweet spot ~12-16 hands, rising as the bank grows.

9. **Locked tiles are passable** and the shed is reachable from all four centre tiles
   even while three of them are locked. Hands spawn on (5,4) — locked until NE is
   bought — and must walk back.

10. **Seeds never enter the shed** and do not count against `shedCapacity`.
    Animals bought *do* sit in the shed and count against it.

## 3. Per-tile economics (verified against the growth code)

Watering bonus window is `(max_yield_day+1)//2 <= age <= max_yield_day`, +1/day
watered, +2/day if also fertilized, capped at `max_yield`.

| line | occupancy | output | actions | $/tile/day |
|---|---|---|---|---|
| Cow (fed+cared) | permanent | 1.5 milk/day | ~4/day | **$345** (capped ~200u) |
| Sheep (fed+cared) | permanent | 1.33 wool/day | ~4/day | **$287** (capped ~200u) |
| Melon | 10 days | 6 units | 8 | $110 (capped ~150u) |
| Strawberry (fert) | 17 days | 8 units | ~20 | $100 (capped ~400u) |
| Goose (fed+cared) | permanent | 2 egg + 1 fert/day | ~3.5/day | **$80, uncapped** |
| Wheat (unfert) | 5 days | 4 units | 7 | $16 (feed, not revenue) |

## 4. Animal feeding: full feed beats rationing (verified, `analysis/animal_economics.py`)

Base production fires on schedule REGARDLESS of feed status (only the CARE bonus
depends on it), and an animal only dies after 2 *consecutive* unfed days. So
every-other-day feeding is survivable and looks tempting as a wheat-saving move.
It is not worth it — steady-state net $ over 200 days:

| animal | full feed (net $) | every-other (net $) |
|---|---|---|
| GOOSE | $9,960 | $5,000 |
| COW | $62,770 | $20,000 |
| SHEEP | $53,175 | $19,275 |

Full feed wins for all three because the CARE-bonus multiplier is worth far more
than the wheat saved. **Feed and care every animal every day, no exceptions**, down
to the day it would starve if you skip. Marginal value per wheat spent: goose $80,
cow $344, sheep $296 — cow/sheep convert wheat into product far more efficiently
than goose does.

## 5. Portfolio optimizer (verified, `analysis/portfolio_optimizer.py`)

Greedy marginal-$-per-tile allocator, walking a shared market ledger so later
picks correctly see the price impact of earlier ones (both on the product they
sell AND on wheat, which cow/sheep/goose all compete for). Land assumed available
from day 8. Result for 100 tiles:

| activity | tiles | why |
|---|---|---|
| COW | 13 | milk crashes fast (linear glut, above_target 1.60) — diminishing returns hit hard past ~13 |
| SHEEP | 10 | wool crashes even faster (sq glut, above_target 3.20) |
| STRAWBERRY | ~50 | absorbs huge volume before crashing (sqrt below / linear above) |
| MELON | ~12 | thin town demand (no shop wants it) but big margin per unit up to ~150u |
| WHEAT | ~14 | NOT just feed — wheat's own sell curve (sqrt/log) is so forgiving that growing and selling it raw nets ~$55-60/tile/day, on par with strawberry |
| GOOSE | 0 in the greedy optimum | see below |

**Non-obvious finding: geese are marginal, not the free money they look like in
isolation.** In isolation (cheap wheat, $25) a goose tile nets ~$1,156 over the
season. But once 13 cows + 10 sheep are drawing ~23 wheat/day, the market wheat
price climbs past $60-75, and goose's margin-per-wheat ($80) is thin enough that
its net collapses to $126-$324/tile — worse than the alternatives above. Geese are
only clearly correct if: (a) wheat is grown on-site near-free rather than bought,
or (b) all higher-value land uses are already saturated and geese are strictly
better than an empty tile (they are — use them as filler, not a strategy).

This directly overturns the original STRATEGY.md guess of "convert everything
left over to geese" — that was true only under naive per-product isolation, not
once wheat is treated as a shared, price-elastic resource. **Open question for the
simulator search:** does growing MORE wheat (rather than buying it) to subsidize a
larger goose flock beat the current allocation? The optimizer above always buys
feed wheat at market price; it doesn't yet credit self-grown wheat as a cheaper
feed source shared with the animals. Worth testing directly in the fast simulator.

## 6. Target portfolio (100 tiles) — v2, feeds the rule-based agent

- 13 cows (fed/cared daily)
- 10 sheep (fed/cared daily)
- 50 strawberry (fertilized + watered daily)
- 12 melon (fertilized + watered daily)
- 14 wheat (feeds animals first, surplus sold raw)
- remainder -> geese as filler (small positive value, never worse than empty)
- fertilizer: collected from every animal daily; use on crops in their bonus
  window first, sell surplus (uncapped town demand for it: zero, but glut curve
  is gentle — linear/linear — so it absorbs volume fine at falling but positive prices)

Plausible target: **$200k+**, refined by the large-scale simulator search.

## 7. Labor estimate

Rough daily task-action count at the v2 portfolio (water/feed/care/harvest/
fertilize/collect, excluding movement): ~206 actions/day. At 24 actions/hand/day
that is a hard floor of ~9 hands with zero movement overhead; realistic zone
layouts will need more like 15-20. Hire cost is cumulative fib: 15 hands/day =
$1,596, 20 hands/day = $17,710. Exact optimal hand count is a job for the
simulator search (Task 5), not hand analysis.

## 8. Open questions for the optimiser

- Does self-grown (near-free) wheat make geese worth adding back, and how many?
- Hand count schedule over the season (ramps with money and tile count).
- Land purchase timing ($1k/$2k/$4k) vs. buying animals/seeds earlier.
- Per-product reserve prices and sell cadence (shed cap forces continuous
  selling — this doc's "sell late" instinct from section 1 has to be reconciled
  with the shedCapacity=100 hard limit across ~99 producing tiles).
- Zone/patrol layout efficiency (movement overhead per tending action).

## 9. Search infrastructure notes

- `kaggle_environments`'s per-turn overhead (deepcopy + structify + JSON
  schema validation of the whole state) scales with how much is built on the
  farm, not just turn count. A fully-built ~90-tile agent is 3-4x slower per
  episode than the sparse `starter` baseline used for the original 1.69s/720
  turn benchmark. Budget accordingly when estimating search throughput.
- This machine has 26 physical cores behind 52 logical (2-way hyperthreading).
  For this CPU-bound, single-threaded-per-process workload, oversubscribing
  to 48 workers caused generations to take 6+ minutes; capping workers at the
  physical core count (26) brought the same generation down to ~15s. Always
  size multiprocessing.Pool to physical, not logical, cores for this kind of
  job.
