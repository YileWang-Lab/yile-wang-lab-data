# Kaggriculture — handoff

**Goal:** gold in the Kaggle *Kaggriculture* simulation competition (2-player,
720 turns, most money wins). Submission deadline 2026-09-30.

---

## 0. READ THIS FIRST — state as of 2026-08-27

**There is currently no contract-legal submission to ship.** The production
development entry is `whitebox/agent.py::_whitebox_entry`. It recomputes every
action from current public/private state and engine rules; another player's
tape, a replayed opening, mined target schedules and learned action imitation
are forbidden. Section 46 defines this reset and overrides every earlier
"ship" instruction in this file.

Current status:

| component | legal status | production status |
|---|---|---|
| **NOON** | white-box objective + tasks + open multi-worker routes + route-coupled hiring | active development path; still losing the standard field |
| optional capital master (§48) | white-box and semantically joint | **experimental, default OFF**; n=18 own-bank gain is strong but paired margin evidence is underpowered |
| **HORIZON** | public-state signals are legal | point estimates are not promoted; opponent cash is now exposed as an exact affordability constraint for the future robust solver |
| **DUSK / replay opening / v3 tape** | **illegal under the current contract** | historical evidence only; never import or submit |

Runtime is a correctness constraint, not a benchmark nicety. The engine grants
`actTimeout=1s` and only `remainingOverageTime=60s` for the whole game; an
exhausted overage produces `TIMEOUT`, `reward=None`, and a forfeit. The current
agent gives the expensive joint layers a 180ms soft deadline, falls back to a
feasible greedy route or the same-day incumbent plan, and skips Held-Karp near
the cutoff. Capital ON seed 9100 now measures 38.6ms mean / 180.1ms P95 /
182.9ms max (0 turns above 350ms); default OFF is 20.0ms / 105.1ms / 182.0ms.
See §49 before changing route complexity or the budget.

Promotion is by paired **final-money margin/win rate**, never own bank alone.
The current capital result is not default-qualified: +$2,880 margin over 18
cells is about 0.9 SE at the measured $13k-$15k per-cell margin SD. Require at
least 288 paired simulator cells plus a multi-seed, both-seat real-engine gate.

### Historical tape-era snapshot below — reference only, do not rebuild/ship

`submission/dusk.py` was the v3 tape plus DUSK and measured 85.4% against its
historical standard pool. That score remains useful evidence about game
mechanics, not a legal component of the white-box architecture.

Historical rebuild command:
```bash
cd /home/yilewang/kaggriculture && /home/yilewang/kagg-env/bin/python -c "
import sys; sys.path.insert(0,'.')
from route.bake import bake
print(bake({'_PREEMPT_MIN_FUTURE_QUANTITY':0,'_PREEMPT_MAX_BATCH':30,
            'INTERVENE':1,'IV_DUMP_FRAC':0.7,'IV_LEAD':3,'IV_FERT':1,
            'IV_STRUCT':1,'IV_MIN_PRICE':0.20,
            'TAPE_MAP':['6c12s_4q_second_yarn','6c12s_4q_second_yarn',
                        '6c8s_3q','10c4s_3q','8c6s_3q']}))"
```

### Submissions (Kaggle keeps only the latest 2 active)

| id | what | real-engine gain | ladder |
|---|---|---|---|
| **55614625** | + bucket-0 tape swap | **+858** vs 55612771 | active, converging |
| **55612771** | + IV_STRUCT, dump .70, price gate .20 | +670 vs 55600561 | active, 24/27 (89%) |
| 55600561 | kawa + intervene (2026-08-18) | — | inactive, peaked 2630.9, 65/84 (77%) |

### Three rules that override everything else

1. **Never score same-tape matchups by win rate.** An agent against a
   byte-identical copy of itself wins seat 0 only **15%** of the time, on a mean
   margin of **-$66**. Use **paired margin**: play both seat orders per seed and
   sum them. A true mirror then scores exactly 0. Section 5.
2. **The tape can now be edited, and you still mostly should not.** As of
   2026-08-21 the route table is a **flat array over an explicit state space**
   (section 4b), so a single state is overridable via `_FR_REMAP` (re-point) or
   `_FR_EDITS` (novel action), coherently at all three read sites. Only **2,205
   of the 7,190 states are reachable** — six of the ten tables are never
   selected — so search the mask, not the space, and report the mask size with
   any result. What has NOT changed is the measurement: every probe so far
   collapsed the run —
   single-step PASS at steps 0-20 costs -6k to -299k, day-0 market edits -7k to
   -138k. Treat an edit as damage until a paired run says otherwise. Market
   orders ARE freely editable; that is what the whole intervention layer is.
   Selecting a different tape also still works (section 16).
3. **Validate a submission by file path** (`env.run([path, opponent])`), never by
   import. Kaggle resolves a file agent with `get_last_callable`, which walks the
   namespace in **insertion order** — rebinding `agent` in an appended layer does
   *not* move it, so the last *newly defined* callable wins. Section 5.

### What changed on 2026-08-21

The route table is now **addressable** and the tape is editable per state —
section 4b. Four derived builds exist, all from `submission/v3_base.py`, and all
four verify equivalent at every level including the real engine.
**`submission/v3_flat.py` supersedes `submission/v3_tree.py`**:

| build | bytes | what it adds | wall | use it for |
|---|---|---|---|---|
| `v3_base.py` | 155,305 | — the shipped v3, 12 blobs | — | the reference |
| `v3_tree.py` | 196,410 | 41,105 B base64 CART, ~13 compares | +0.3% | nothing; kept for comparison |
| `v3_flat.py` | 158,663 | **3,358 B** flat array, one index | **+0.1%** | **ship this** |
| `v3_expanded.py` | 1,463,844 | all 12 blobs as literals | +7.6% | reading a blob |
| `v3_flat_expanded.py` | 1,467,202 | both | +7.4% | **read and edit this** |

The two transformations are independent — expansion appends nothing, so
`v3_expanded.py` still picks `_submission_entry` while both flat builds pick
`_flatroute_entry` — and were verified separately as well as together.

The CART was structure for its own sake — its leaves were already `(table, step)`
references, so nothing depended on the branch structure. Its only real product
was the substrate, and a flat array over `s1 = (legacy*5 + label)*719 + step` is
a strictly better one: key space and reference space are the same integer space,
so `_FR_REMAP[i] = j` means "state i plays state j's action" in one int.

**All twelve blobs are also expandable now** (`pbt/expand.py`): the ten route
tables and — the half nobody had read — the two market tapes `_V17_R5_MARKETS`
and `_V17_MD_MARKETS`. `submission/v3_flat_expanded.py` has no compressed data
in it at all. It costs 8x cold import and +7.6% episode wall, so **ship
`v3_flat.py`, read and edit `v3_flat_expanded.py`**.

All of these are **worth exactly zero extra points on their own** — substrates
for a search, not candidates. Side-by-side copies and full write-up in
`v3_compare/`; numpy tooling in `dynamic/tape/route_array.py`. There is
deliberately **no opponent axis** — the opponent enters the eleven guards, not
the route; see `pbt/flatroute.py`'s docstring for why adding one now makes the
search harder before it makes the agent better.

### What changed on 2026-08-23

Two things, and neither is a new submission. The shipped agent is still 55614625.

**`arena.py` is now the standard A/B harness — use it instead of writing another
one.** One file, self-play plus the opponent pool, every rule in this section
enforced by construction rather than by remembering: identity control, paired
margin for same-tape arms, paired win rate as well as margin, common random
numbers across the two arms, firing rate and the conditional distribution, file-
path loading through `get_last_callable`, 26 workers, and a `sim | real | both`
engine switch that cross-checks the two. Section 5.

```bash
/home/yilewang/kagg-env/bin/python arena.py <candidate.py> \
    --baseline submission/main.py --seeds 24 --pool standard --engine both
```

**The endgame is closed.** A full endgame proposal was graded against the engine
source and against live games — half of it is already shipped, a quarter of it is
impossible, and the buildable remainder measured +2 a seed. Section 38. The
by-product is four engine facts that were not written down anywhere: animals
cannot be sold, goods sit in hand inventories until a `DROP`, `shedCapacity` caps
any market position at 100 items, and wheat's ceiling is $125 rather than the
$45 that gets quoted.

**`incoming/submission8.18.v3 (1).py` is graded** (section 37 asked). Against
`submission/main.py`: **+26,517 self-play** over 24 paired seeds (18-6) but
**-2,051 a seed against the pool** (t -3.94, n=144), real engine agreeing in sign
at -445. It beats us head to head and loses to everyone else, which is the shape
of the 2630.9-vs-1828.3 contradiction rather than an explanation of it. Its
twelve blobs are byte-identical to `submission/v3_base.py`, so whatever differs
is in the code around them, not in the tape.

Nothing was submitted to Kaggle on 2026-08-21 or 2026-08-23. The shipped agent
is still 55614625. Kaggle's API and the open web were both unreachable from this machine
that day (`api.kaggle.com` SSL EOF; web fetches 403 through the configured
relay), so the ladder standings below are a **2026-08-19 snapshot**, not live.

The self-play / opponent-pool RL run (`dynamic/rl/train.py`) was **stopped** on
2026-08-21 after ~21h. It had been flapping rung 6↔7 for hours — 536 promotions
against 535 demotions, every rung-7 iteration at 0.0% poolwr with 26-41 errors,
`best.npz` unchanged since 09:05. It produced nothing.

### Rule 4, learned 2026-08-19 and now the most expensive one

**For a concentrated effect, sample size means FIRING games, not games played.**
The bucket-0 tape swap changes behaviour in only ~13% of games. Its first
real-engine gate ran 180 paired games — comfortably past section 5's "≥100
games" bar — but only ~28 of them fired, and it returned **-18** for something
worth **+858** at 630 paired. Nothing was broken: the simulator reproduces that
same -18 on that same sample. Always report how often a change actually fires
and its CONDITIONAL distribution, not just the mean.

Corollary: two "independent replications" that share an opponent set are not
independent. +1,889 and +1,966 on disjoint seeds looked conclusive and were both
drawing the same region; real independence came from changing distribution
entirely (the 80 real ladder traces).

### Rule 5, learned 2026-08-23

**A market-only change cannot sell what the hands are still carrying.** `SELL`
draws from `private["shed"]`; a `HARVEST` or `PICKUP` puts the unit in that
unit's own inventory, and only `DROP` — a hand action, on a shed-access tile —
moves it to the shed. From step 708 of a measured game we hold 24 MILK, 4 WOOL
and 4 STRAWBERRY in hand inventories and **nothing** in the shed until the
tape's `DROP` at 717. Every market-layer idea that wants to sell earlier than
the tape does is therefore not a market edit at all; it is a route edit wearing
a market edit's clothes, and it has to clear section 36's budget.

The general form: before designing an overlay, check WHERE THE STATE IT NEEDS
ACTUALLY LIVES. Three of the four endgame modules in section 38 were inert, and
two of them were inert for this reason.

### What was actually worth anything

| change | measured on | gain |
|---|---|---|
| ~10 generations of constant search, PBT, tape-selection search | — | **~0** |
| market intervention (lead 3, dump 80%, +FERTILIZER) | vs plain kawa | +1,611 |
| IV_STRUCT + dump .70 + price gate .20 | real engine | **+670** |
| bucket-0 tape swap | real engine | **+858** |
| ...the same, across our 80 real ladder games | ladder traces | +429, record 62/80 → 66/80 |

### The two lines, as of 2026-08-20

Both are at local optima and the reason is now measured, not guessed.

- **tape+market (SHIPPED, ladder 2183.9)**: 600 mutants cleared nothing;
  five market-layer ideas refuted with controls. Section 20.
- **from-scratch planner (-57,830)**: its economy already MATCHES the tape's
  (own bank 86,386 vs 86,119). The entire gap is that the opponent banks ~$51k
  more against us, and the cause is price, not stolen volume -- they sell 1,446
  units against us and 1,447 against the tape, at $114.2 and $78.7 respectively.
  Ten levers refuted. Section 19.

### Corrections to earlier sections of this document

- **Section 0's old "12 vs 14 hand slots" gap is NOT our deficit.** Measured
  from 23 replays (`planner/analyze_top.py`): we run 277 hires, 12 hands, 2,858
  useful ops — at or above every ladder leader, and the most ops of anyone. Only
  ReCurSiON runs 14 hands. The gap is price realisation, not labour.
- **Section 11's "tape-selection mapping already searched, default wins" is
  wrong for bucket 0.** Section 16.
- **Section 12's "IV_STRUCT is ambiguous" was under-sampling.** It is +420 at
  n=1,440 paired (t=16.3), and shipped.
- **Section 14's "the market layer is at a local optimum" is now true and
  proven** — but it was true of the *parameters*, not of structural changes.
  Section 17.

---

## 1. Environment

| what | where |
|---|---|
| project root | `/home/yilewang/kaggriculture` |
| python | `/home/yilewang/kagg-env/bin/python` (venv, py3.14) |
| engine source (READ IT) | `/home/yilewang/kagg-env/lib/python3.14/site-packages/kaggle_environments/envs/kaggriculture/kaggriculture.py` |
| Kaggle CLI | `/home/yilewang/kagg-env/bin/kaggle`, token at `~/.kaggle/access_token` |

Machine: **26 physical cores** (52 logical), 187 GB RAM. GPUs unused — the
workload is single-threaded CPU-bound Python. **Always size pools to 26**;
48 workers on 26 cores took 6+ minutes to not finish what 26 do in 30s.

Rebuild the submission: see section 0 (the parameters changed 2026-08-19).

## 2. File map

```
STRATEGY.md                   game economics derived from engine source (still valid)
submission/main.py            THE FILE TO SUBMIT
opponents/                    6 loadable public reference agents + extractor
replays/                      downloaded ladder replays (~30MB each)

pbt/intervene.py              the market-intervention layer = the entire real edge
pbt/extract_tape.py           replay -> 719-step tape -> transplant into kawa
route/bake.py                 assembles submission/main.py (base tape + layers)
route/opponent.py             EXACT opponent-sales inference (used by the agent)
route/tournament.py           round-robin harness
route/batch.py                fixed-matchup batch scorer

route/geom.py|router.py|agent.py   own-plan architecture — still far behind, section 13
pbt/tapesel.py                tape-selection rule — bucket 0 IS mis-assigned, section 16

planner/simulate.py           FAST pure-Python engine port, ~1,200 steps/s (~9x env.step)
planner/tests/                test_sim_fidelity (56 replays) + test_agent_fidelity (live play)
planner/intervene_sweep.py    market-layer sweeps, rounds 1-6, paired margin with CRN
planner/tape_sweep.py         per-bucket tape argmax  |  tape_map_test.py  fresh-seed check
planner/ladder_sweep.py       tune against the 80 REAL ladder opponents, not the pool
planner/replay_counterfactual.py  "would the new agent have won the games we lost?"
planner/analyze_top.py        realised per-unit prices from replays, us vs the leaders
planner/decompile.py|spec_extract.py  tape -> explicit schedule spec, and the gap to it
planner/day_pipeline.py       gated submission (real-engine + file-path gates)
pbt/tape_edit.py              day-0 market editor (proved the tape is not editable)
pbt/features.py|cluster.py    6-dim opponent features + K-Means (no signal found)
pbt/adaptive.py|adversary.py  per-family counter params (tied with plain best)
pbt/pool.py|variants.py|train.py   population-based training (random walk, section 5)
agents/                       every baked variant from every experiment

--- v3 representation work, 2026-08-21 (section 4b) -----------------------
submission/v3_base.py         the shipped v3, unmodified. 12 blobs, opaque
submission/v3_tree.py         + CART blob          SUPERSEDED, kept for comparison
submission/v3_flat.py         + flat state array   SHIP THIS ONE  (+0.1% wall)
submission/v3_expanded.py     all 12 blobs as literal source
submission/v3_flat_expanded.py  both               READ AND EDIT THIS ONE (+7.4%)

pbt/flatroute.py|flatify.py   emit + append the flat array layer (_FR_*)
pbt/expand.py                 expand every blob to literals; finds them by AST
pbt/treeroute.py|treeify.py   the superseded CART layer (_TR_*)
dynamic/tape/route_array.py   numpy view of the flat table: keys, diff,
                              reachability, patch. NEVER imported by an agent
dynamic/tape/v3_bench.py      equivalence sweep, V3_LAYER=tree|flat|expanded|
                              flat_expanded. planner.simulate, 26 workers
dynamic/tape/v3_submit_check.py  the same by FILE PATH under kaggle_environments
                              (needs ~/kagg-env). Local only, never contacts Kaggle
v3_compare/                   all five builds side by side + README + market_tapes.py

--- evaluation + endgame, 2026-08-23 (sections 5, 38) ---------------------
arena.py                      THE A/B HARNESS. self-play + pool, one file,
                              sim|real|both. Use this, do not write another
pbt/endgame.py                emit + append the endgame market layer (_EG_*)
submission/v4_endgame.py      expanded v3 + the endgame layer. deadline mask on,
                              front-run on, squeeze OFF, early-DROP on. +2/seed
submission/v4_squeeze.py      the white paper's wheat squeeze, kept as evidence:
                              -3,068 a seed, 0 wins in 144. Do not ship
submission/v4_deadline_only.py|v4_frontrun_only.py   inert controls, section 38
logs/arena/                   every arena run as JSON, newest last
```

## 3. Engine mechanics that matter

All verified against source, not the write-up.

- **Market-limited, not production-limited.** Price = f(inventory) around a
  10,000 baseline, per-product curves. MELON and WOOL are **quadratic** above
  baseline (crash hardest), MILK and STRAWBERRY linear, EGG/WHEAT log (never
  really crash). Selling at the $1 floor does **not** add to market inventory.
- **Hands are cleared every night** and must be re-hired daily. Cost is
  `fib(hires_today)` for that farm. Extra overlay hires before the same farm's
  later orders reprice those later orders (4 extra hires move its following 5
  from $7 to $81). The counters are private: the opponent's HIRE never changes
  our price.
- **A crop must be watered the day it is planted.** `_new_plant` starts at
  `consecutive_unwatered = 1`; unwatered at the nightly refresh it is a weed by
  morning. PLANT and WATER must ride in the same tile visit.
- **CARE banks a multiplier** consumed on the next fed production day: goose
  1→2 eggs/day, cow 1→3 milk/2 days, sheep 1→4 wool/3 days. Feed and care every
  animal every day.
- **Animals produce fertilizer unconditionally**, fed or not. Nobody in town
  consumes it, so its price only falls — but it must still be sold, because the
  shed holds only 100 items and hoarding it freezes all commerce (measured:
  bank $62).
- **Atomic PLANT validation:** if PLANT requests for one crop in a turn exceed
  seeds held, *all* of them are dropped.
- **`max_lifespan_step` is an absolute step index, not a duration.** MELON
  planted day 0 gets 312 = decay starts **day 13**; it first yields **day 10**.
  Reading it as "312 steps of locked capital" is wrong and has misled analyses.
- **Within a step the engine runs `_process_market` before `_town_consume`.** A
  sale placed on a step the town drains enters an undrained market; the same
  sale one step later enters after the tick lifted the price. This is what the
  front-run/dump timing exploits.

## 4. The tape is immutable

Day 0 is the most isolated possible edit — a market line that moves no unit.
Paired margins after editing it:

| day-0 change | vs kawa | vs v111 | overall |
|---|---|---|---|
| none (baseline) | +1,579 | +16,708 | **+12,101** |
| feed 6 → 14 | +1,579 | +16,708 | +12,101 (**no effect** — no cash to fill it) |
| melon 12 → 6 | -11,211 | -6,213 | -7,467 |
| hire 4 + feed 14 | -63,945 | -50,846 | -54,541 |
| 1 COW / 4 SHEEP | -111,355 | -106,791 | **-107,714** |
| v111's whole day-0 line | -99,442 | -158,985 | **-138,558** |

Every downstream PLACE/PLANT assumes exactly the shed the tape bought. Grafting
another agent's opening onto this tape destroys it — its parameters only work
with its own 720-step continuation.

The same rigidity killed the day-1 fix. **All five tapes leave day 1 empty** —
0 hand slots, 0 actions, 0 HIRE, so the farm runs that day on the farmer alone
despite four hires costing $7 against $23 on hand. Overlay results, 40 games vs
kawa each: baseline 62%, hire-only-day-1 62% (bodies idle — the tape has no work
for them), hire every day **0%**, hire + assign work **0-5%**. A tape `PASS` is a
hand *holding station*; moving it desynchronises the rest of its schedule.

## 5. Measurement rules paid for the hard way

- **Seat asymmetry decides same-tape games.** `_end_of_day` rolls player 0's
  weeds first and `_process_market` commits both players against the shared
  product market in player order. HIRE and BUY_LAND themselves use private
  farm state and do not reprice the opponent. Identical agent vs itself: seat
  0 wins 6/40, mean margin -$66. Use
  paired margin; a byte-identical mirror then scores +0/+0, 0 wins, 0 losses.
- **A screening panel ranks against a *field*; only pairwise ranks against an
  *opponent*.** Three times a panel rated variants equal-or-better while the
  direct 100-game pairing showed one clearly worse (once 26% vs the config it
  had "beaten"). Screen broadly, decide pairwise.
- **A variant needs ≥100 games before its rank means anything.** Real
  differences here are 1-3 points; PBT scored variants on 12 games, so noise
  dominated, `v8 random noise` kept "winning", and 10 rounds of optimisation
  moved *backwards* (its champion then lost 22-78 to the earlier build).
- **Never attribute engine callbacks using objects from `obs`.**
  `kaggle_environments` structifies the observation, so `farm is obs["farms"][0]`
  inside a patched `_commit_unit` is always false and every commit lands on one
  player. Hook `_process_market(state, env)` — it gets the live state — and
  identify players by `private` identity.
- **A validation whose ground truth shares the broken step with the thing being
  validated proves nothing.** The opponent-sales inference first "validated" at
  near-zero error only because both sides were computing *combined* sales.
- **Cross-opponent comparisons are confounded.** Weeds roll only on empty tiles,
  so our tile count shifts the RNG before `rng.choice(SHOPS)` — the town's shop
  mix changes with the opponent, and "agent X scores more against Y than Z"
  supports no strategy claim.
- **Seed range is *not* a confound** (hypothesis tested and rejected). Ladder
  seeds are 32-bit; local work used 1-50. Over 40 of each: ours vs naru +11,374
  / +8,860; kawa vs v111 +13,862 / +12,232; ours vs kawa +1,428 / +1,611. The
  populations agree.
- **`pkill -f <pattern>` matches your own shell.** Use `pkill -f '[g]a_search'`,
  and beware that regex `.` matches `/` — `route.search` also matched the literal
  text `route/search.py` in a heredoc and killed the shell running it.

### All of the above is now `arena.py`, and you should use it

Every rule in this section was re-implemented by hand for most of the sweeps in
this repo, and the expensive mistakes were omissions rather than errors —
`metric_test.py` has the identity control, `v3_bench.py` has the paired mirror,
`intervene_sweep.py` has CRN, and no one file had all three until now.

```bash
python arena.py <candidate.py> --baseline <base.py> --seeds 24 --pool standard
python arena.py <candidate.py> --engine both --real-seeds 20   # + real gate
python arena.py <candidate.py> --quick                         # iteration only
```

What it enforces, so you cannot forget it:

- **`base_vs_base` must return +0** or the run ABORTS. The v3 lineage keeps
  `_WEED_STATE`, `_SHIFT_STATE`, `_KAWA_LAYOUT_FALLBACK` and `_IV` at module
  level keyed by seat, so a reused module carries the last episode into the next
  one and every number downstream is fiction.
- **`cand_vs_cand`** catches a nondeterministic candidate before it poisons the
  paired arithmetic.
- Same-tape arms are scored by **paired margin only**; the pool is scored by
  **both** margin and paired win rate (section 29).
- Both arms play each (opponent, seed, seat) **in the same worker**, so a
  difference is the change and not the draw.
- **Firing rate and the conditional distribution** are printed whether you asked
  or not (rule 4), and the verdict is gated on n >= 100 paired and >= 30 fired.
- Agents are resolved with **`get_last_callable`** semantics (rule 3), and the
  pool is preflighted in the parent so a broken opponent is one dropped line
  rather than a wall of tracebacks.

**The two engines are not interchangeable.** `planner.simulate` runs an episode
in ~0.31s against the real engine's ~4.8s. It is not bit-identical in absolute
bank — v3_base vs kawa on seed 9000 is (87,332 / 86,890) real and
(87,519 / 87,077) sim, **both off by the same +187**, so the margin is identical
and paired work is unaffected. Screen on `sim`, gate on `real`, and
`--engine both` reports whether the two agree in sign.

## 6. Opponent modelling — the one thing that paid

**Their sales are exactly recoverable, not guessed.** Within a step the engine
settles both players' orders and then the town's consumption, so

    inv[t+1] = inv[t] + my_sales[t] + their_sales[t] - town_take[t]

and every term but theirs is known: inventory is public, `town_take` is
computable from the unlocked shop list, and our own sales are what we issued.
Validated against engine ground truth over a full season: **zero error** on
STRAWBERRY, MELON, MILK, WOOL and EGG; total absolute error 9, confined to
WHEAT and FERTILIZER — the only products whose price reaches the $1 floor, where
the engine deliberately does not record the sale.

`pbt/intervene.py` measures each product's sale cadence from that inference and
pushes stock into the book ahead of the predicted sale. Tuning by paired margin:

| dump fraction (lead 3, +FERTILIZER) | vs kawa | mirror vs dump-40% |
|---|---|---|
| 40% | +1,221 | — |
| 60% | +1,358 | +297 (37/3) |
| **80%** | **+1,428** | **+467 (39/1)** |
| 100% | +1,209 | +29 (29/11) |

**Cost of running it:** observation must happen every turn (a running inventory
delta — a skipped turn breaks the arithmetic), but the *action* fires only
**9% of turns**, never before day 6 (needs ≥3 observations to fit a period),
concentrated in days 23-27. FERTILIZER alone is half of all firings.

**Ideas tested and rejected**, all from the published Market Relay write-up:
exact repayment / volume conservation (**-3 to -5 points**: our dump is an
aggressive extra sale, not a retimed one, so repaying hands the advantage back),
near-mirror gating (**-2**, it only reduces how often we act), and buying wheat
to squeeze an animal-heavy opponent (**2% win rate** — it spends cash the tape
needs downstream).

**We were exploitable and this is how it was found.** kawa does not model us —
its `_future_sells(obs, step)` reads its *own* tape. But `_clone_distance` does
read our farm, and ours is **0** against kawa (same tape), so its preemption is
fully armed; denying it is worth +$784, and unreachable, because raising the
distance past 6 needs 7 extra hands, 7 changed tiles, or a different tape.
Turning our own layer around — equipping opponents with it — produced three
predators that beat us, which is exactly how the dump fraction was found to be
set too low.

## 7. Reference agents and the ladder

`opponents/` holds 6 loadable public agents, all stdlib-only and audited.
Round-robin by paired margin (3,120 games): our build +9,016, kawa +8,103,
ref_B/ref_D +1,608, v111 -13,338, rank-your-agent -13,624, pipeline -43,120.

- **V16-RC5 is v111**, byte-identical (`sha256 f029fa0c…`, 18,946 bytes). Its
  notebook's "60/60" is against its own reconstructed baselines, never against
  kawa. Do not submit it.
- **The ladder meta has converged on 8c4s.** Three different opponents
  (Naru041104, Igor V, StopPlantingStartGameTheorying) open identically —
  4-5 HIRE, **1 COW / 4 SHEEP**, 5 wheat seed, 5 melon seed, 5-14 wheat product —
  and all reach 14 hands. We beat that family ~70% of paired seeds; the three
  losses that prompted this investigation were a bad draw, not a systematic
  defeat.

### Submissions

`publicScore` is a **skill rating, not money**, and converges with games played —
two copies of the same agent can sit hundreds of points apart on match history
alone.

| id | file | score | what it actually is |
|---|---|---|---|
| 55594505 | submission.py | **2326.3** | **unmodified kawa** |
| 55597426 | submission8.18.v2.py | 1898.5 | **unmodified kawa** |
| 55576209 | Kaggriculture.py | 1848.1 | earlier user agent |
| 55587826 | main.py | 482.6 | our GA route agent (all-crop) |

Only the latest 2 are active; 5/day. **Nothing built on 2026-08-18 has been
submitted** — every gain since is unvalidated on the ladder.

### Replays are the only honest feedback

```bash
/home/yilewang/kagg-env/bin/kaggle competitions submissions kaggriculture
/home/yilewang/kagg-env/bin/kaggle competitions episodes <SUBMISSION_ID>
/home/yilewang/kagg-env/bin/kaggle competitions replay <EPISODE_ID> -p replays/
/home/yilewang/kagg-env/bin/python -m pbt.extract_tape replays/<f>.json <seat> out.py
```

The real seed is at `info.seed` (32-bit) — any ladder game reproduces locally
with it. **Off-by-one:** replay `steps[0]` is the initial state and carries no
action; actions live at `steps[1:]`, which is why tapes are 719 long. Taking
`steps[0]` silently discards the opening turn.

Transplant fidelity is verified: replaying both extracted tapes at the episode's
real seed reproduced 107,064 v 135,395 against an actual 108,217 v 135,557.

## 8. Ground rules with the user

The competition permits reusing published notebooks; the user has confirmed they
want that. The shipped agent is a public tape plus our own market layer, and
that is understood and intended.

## 9. Next (superseded by sections 16-18; see section 0)

1. **Submit and get a real score.** Every local avenue is exhausted; the one
   number we do not have is what the intervention layer is worth on the ladder.
2. **The 12→14 hand-slot gap** is the only quantified structural deficit left,
   and it needs a different tape, not a tuned one. Extraction tooling is ready.
3. Do not re-run constant searches. They were run to exhaustion and measured
   zero once paired margin replaced win rate.

## 10. The sparring pool cannot be grown by copying the ladder

Six reference agents is a small pool and the overfitting risk is real. Copying
the top of the ladder does **not** fix it.

Access is not the problem — it is fully solved. `pbt/build_pool.py` walks
leaderboard `teamId` -> that team's submissions -> that submission's episodes,
and episode *metadata* already carries `team_id`, `submission_id`, `reward` and
seat index. **2,616 real ladder games were mapped without downloading a byte.**
Real head-to-head records for the top 20 (>=25 games):

| team | ladder score | W-L | win% |
|---|---|---|---|
| tetsuya | 3048 | 83-11 | **88%** |
| mandgeee | 2910 | 82-17 | 83% |
| VanKoha | 2888 | 58-13 | 82% |
| カワシギ | **3196** | 143-34 | 81% |
| 我的AI是GPT | 2899 | 69-21 | 77% |
| Utkarsh #2 | 2904 | 137-134 | 51% |

Note score and strength disagree: tetsuya wins 88% but ranks 3rd on rating.

**The blocker is that these agents are adaptive, not tape-replay.**
`pbt/agreement.py` compares three of an agent's own games step by step:

| team | farmer agreement | hands | market |
|---|---|---|---|
| tetsuya | 49.1% | 19.1% | 76.5% |
| カワシギ | 37.4% | 26.1% | 43.4% |
| 我的AI是GPT | 39.9% | 27.7% | 45.1% |
| mandgeee | 65.2% | 33.0% | 52.6% |

V16-RC5 reconstructed Nikita's submission at **99.91%** market agreement — that
one was a tape. The current top of the ladder is not. A single episode is a
*trace*, not a policy; replayed blindly it degrades badly (the extracted files
lost to our submission by up to -106,857, implausible for a 77%-win opponent).
They are quarantined in `pool_invalid/`.

**Always run `pbt/agreement.py` before trusting an extracted opponent.**

This also reframes the ladder: the "two schools" split by day-0 opening is only
an opening similarity. The continuations are adaptive and diverge.

## 11. The behavioural-cloning critique, tested point by point

A review argued the agent is brittle behavioural cloning and proposed
parameterising quantities, adding a fallback policy, auto-selecting sequences,
and training a network. Measured against this codebase:

| proposal | verdict |
|---|---|
| parameterise absolute quantities into formulas | **refuted** — day-0 quantity edits cost -107k to -138k (section 4) |
| auto-select the sequence from opponent features | **already present and already optimal** — `_kawa_route_label`; the whole 5-bucket mapping was searched, default wins (section 23 of the archive) |
| submission size near a 20MB limit | **wrong** — the file is 155KB |
| weed/exception recovery | **already present** — `_weed_repair_action`, `_align_hands` |
| market intervention | **already shipped** — and confirmed firing on the ladder |
| "zero generalisation, catastrophic drift" | **overstated but has a kernel** — see below |
| add a fallback policy for drifted states | **refuted, decisively** — see below |

### How much does the tape actually misfire?

`pbt/noop_probe.py` checks every tile op against the engine's own preconditions
before submission, over 96 games:

- wasted tile ops: **2.0% mean** (median 1.5%, worst 15.3%)
- wins 1.7% vs losses **3.5%**; correlation with margin **r = -0.32**

So drift is real and does correlate with losing, but at 2% it is not
"catastrophic", and it explains ~10% of variance.

### Why no fallback can exploit it

`pbt/recover.py` substitutes a valid op **on the tile the unit already occupies**
whenever the tape's op would no-op — never moving, so position stays in sync,
and only touching turns the tape was wasting anyway. It looks free. It is not:

| opponent | recovery off | recovery on |
|---|---|---|
| kawa | +1,168 | **-140,858** |
| v111 | +11,560 | -130,748 |
| 3000-socre | +11,845 | -150,193 |
| rank-your-agent | +13,504 | -127,066 |

Head to head: **0 paired wins in 32**.

Position invariance is not enough — the tape needs **state** invariance, and
there is no useful action that leaves state unchanged. HARVEST takes the yield
and, on a non-ongoing crop, *deletes the plant*; WATER sets `watered_today` and
changes yield accrual; CARE and COLLECT_FERTILIZER consume their flags.

**Even the wasted 2% of turns cannot be reclaimed.** This is the third
independent confirmation that the tape admits no edits, and the strongest.

## 12. Structural yield forecast and staged dumping — tested, both marginal

A review proposed replacing the dump trigger's observed-cadence predictor with
one that reads the opponent's *visible board* (animal `placed_day + first_yield
+ k*interval`, crop growth tables), and splitting the dump into tranches.

The first idea was a genuine gap: `route/opponent.py::forecast_supply` had been
built and validated but was never wired into the intervention trigger, which
used only the median observed sale interval. Both were implemented
(`IV_STRUCT`, `IV_STAGED`) and measured over 32 paired 32-bit seeds:

| variant | kawa | v111 | 3000 | rank | field mean | direct vs base |
|---|---|---|---|---|---|---|
| base | +1,149 | +15,354 | +10,942 | +17,478 | +11,231 | — |
| **struct** | **+1,469** | +15,556 | +11,754 | +17,175 | **+11,489** | -29 (8/32) |
| staged | +1,124 | +15,539 | +11,056 | +17,583 | +11,325 | **-386 (1/32)** |
| both | +1,417 | +15,629 | +11,769 | +17,250 | +11,516 | **-824 (2/32)** |

- **Staged dumping is refuted** (-386, 1 paired win in 32). Splitting the block
  gives the opponent a turn to sell into the gap.
- **The structural forecast is ambiguous**: +258 on the field mean (+320 against
  kawa specifically, a 28% relative gain on that matchup) but -29 and 8/32 in
  the direct mirror. A -29 mean on a ~$90k bank is 0.03% — the mirror is
  effectively a tie decided by noise.

Not shipped. The effect is inside the band where today's measurements have
repeatedly inverted, and a live submission was already performing on the ladder;
swapping it for a ~2% local signal is not justified. Kept behind `IV_STRUCT` for
a future run with a larger sample.

### Proposals refuted before implementation, from measurements already on file
micro-task/transaction restructuring of the trace, A* pathfinding with a
reservation table, worker-driven early shed clearing (discards measured at
**0** — the problem does not exist), per-shop-combination dedicated traces
(we cannot author tapes; the ladder top is adaptive), and offline GA
perturbation of the trace. All require editing the tape. See sections 4 and 11.

## 13. Self-built planner: restarted 2026-08-18 evening

The tape is a hard ceiling and the ladder offers no better one to copy — every
strong agent is either running kawa's public tape already (HKmgikao matches
`_ACTIONS_6C12S_4Q_FIRST_YARN` at 100% farmer / 94.9% market) or is adaptive and
cannot be extracted (VanKoha 56.7%, Galaxantic 50.1%, Eddy Despradel 64.5%,
Michael Timbs 59.0%, plus the four in section 10). So the only way past it is to
author a schedule, which means `route/`.

### Honest baseline, paired margin, 32-bit seeds

| genome | vs kawa | vs v111 | vs 3000 | own bank |
|---|---|---|---|---|
| best_route2 | **-101,239** | -83,164 | -109,886 | $68,655 |
| best_route6 | -104,431 | -106,251 | -111,069 | $62,879 |
| defaults | -137,842 | -144,963 | -149,372 | $48,571 |

We bank ~$68k where kawa banks ~$170k in the same game. **The gap is 2.5x**, not
the 1.3x an earlier note implied — that note compared numbers measured under
different matchups and was wrong.

### Three fitness defects fixed before restarting

The earlier searches optimised the wrong thing:

1. **`starter` was in the matchup set.** Pitfall #3 exactly — a champion tuned
   with it won every local game and scored 485 on the ladder. Removed.
2. **Fitness was mean *own bank*.** That rewards a genome for drawing a rich
   seed, not for beating the opponent. Now mean **paired margin**.
3. **One seat only, and seeds from 1..10^6.** Now every reference is played from
   **both seats on the same seed**, with seeds drawn from the ladder's own 32-bit
   range.

### Result: 124 generations, stopped 2026-08-18

| | gen 0 | best (gen 116) |
|---|---|---|
| paired margin vs the reference pool | -34,720 | **-8,192** |
| win rate | 0.00 | 0.17-0.33 (noisy) |

The gap closed **76%** and then flattened. Best genome: 5 COW / 6 SHEEP /
6 MELON / 24 STRAWBERRY / 4 WHEAT, `MAX_HANDS=16`, `HIRE_BUDGET_FRACTION=0.61`
— and the search turned **`FRONT_RUN` and `OPP_MODEL` off**, which is the
opposite of what helps the tape build.

Still negative: it does not beat kawa. The line is kept because it is the only
one that depends on nobody else's tape, but on this evidence a parameter search
over the existing planner will not close the remaining gap — the shortfall is in
the economy (revenue per unit and product mix), not the routing, which already
runs 31% movement against kawa's 43%.

**Do not edit `route/agent.py` or `route/router.py` while a search runs** —
workers re-exec the agent per episode and the fitness signal is silently
corrupted.

## 15. Evaluation pool, expanded 2026-08-18

Six agents was too small a pool. Twelve high-vote public notebooks were pulled
with `kaggle kernels pull`; after dedup **five were genuinely new and usable**,
taking the pool to **nine**. Measured against our build (paired margin, 20 seeds,
both seats):

| pool member | paired margin | paired wins |
|---|---|---|
| kawa (multi-route) | **+1,176** | 19/20 |
| frontier-the-soil-remembers-rain | +13,311 | **13/20** |
| v111 / V16-RC5 | +14,798 | 15/20 |
| breaking-the-tie-2883 | +17,284 | 15/20 |
| Kaito Fukami v25 | +27,512 | 20/20 |
| strong-barnyard-economist | +33,887 | 20/20 |
| pure-architecture-2600-elo | +39,589 | 20/20 |

**No public notebook is worth copying** — every one is weaker than what we
already run, including the public v25 of the player who was ranked #1 (3220) at
the time. Public notebooks lag well behind what the top players actually submit.
They are useful only as sparring partners, and `frontier` is the valuable
addition: it takes 7 of 20 seeds off us, so it exercises the agent differently
from the kawa family.

Dedup saved three redundant matchups: `rank-top10-read-the-market` =
`3000-socre` = `ttv1`, and **boatlee's "V20-Adaptive-R1" is kawa itself**.

Four notebooks (adaptive-farming-strategy, findings-from-zero-to-top-meta,
structured-economic-policy, ultimate-mega-ensemble-3000) extract to analysis
code rather than a standalone agent and are not usable.

## 14. v3 ladder losses: no bug, and the market layer is at a local optimum

37 games, **32-5 (86%)**. All five losses are narrow — the worst is -5,341 on a
$121k bank (4.4%) and the smallest is -139. There is no collapse to fix.

**Four of the five are at seat 0**: seat 0 goes 17/21 (81%), seat 1 goes 15/16
(94%). That is the structural asymmetry from section 5 showing up on the ladder,
and it is not fixable from the agent side.

The largest loss did suggest a real mechanism. We sold **2,738 FERTILIZER to the
opponent's 1,697** while its price ran 43 -> 26 -> 10 -> **1**, and the game
turned in exactly that window (d22 +414 -> d24 -5,097). Front-running only pays
while there is a price to win; at the floor both players clear at the same few
dollars. kawa ships this idea as `_PREEMPT_MIN_PRICE_RATIO` but leaves it at 0.0.

Implemented as `IV_MIN_PRICE` and measured over 24 paired seeds:

| gate | field mean | direct vs gate-off |
|---|---|---|
| off | +8,137 | — |
| 0.05 | +8,186 | +65 (9/24) |
| **0.10** | **+8,280** | **+100 (12/24)** |
| 0.20 | +8,320 | -12 (8/24) |
| 0.35 | +8,277 | -178 (7/24) |

**Not shipped.** The best variant wins its direct matchup 12 of 24 — exactly
chance — and +100 on an +8,137 margin is 1.5%.

That is the third refinement of the market layer to land in the noise
(structural forecast, staged dumping, price gate). **The layer is at a local
optimum; stop tuning it.** Remaining gains have to come from the schedule, which
is what `route/` is for.

---

## 16. The tape-selection rule: bucket 0 IS mis-assigned (2026-08-19)

Section 11 recorded the 5-bucket mapping as "already present and already
optimal — the whole 5-bucket mapping was searched, default wins". That is right
for four of the five buckets and **wrong for bucket 0**.

`_kawa_route_label` maps the town's shop draw onto one of five tapes. The space
is 5^5 = 3,125 mappings, which is the wrong way to attack it. Buckets are
mutually exclusive, so force each tape, record which bucket each game fell into,
and take the argmax **per bucket** — 5 measurements, not 3,125
(`planner/tape_sweep.py`).

That naive answer proposed changing three buckets and was wrong on two counts:

1. The argmax is selected on the data it is scored on.
2. **The bucketing is post-hoc.** `_kawa_route_label` reads the shops unlocked
   *so far*, so the bucket starts at 4 and moves as shops unlock — the agent
   switches tapes mid-episode. The tell was in the data: the default agent's
   bucket-1 mean (21,379) did not equal the mean of the tape the default map
   assigns to bucket 1 (15,847), which it would have to if the map were static.

Tested properly, as real `TAPE_MAP` variants on seeds disjoint from the
derivation (`planner/tape_map_test.py`):

| change | vs live | t |
|---|---|---|
| **bucket 0 only** | **+1,841** | **13.7** |
| all three buckets | +1,041 | 3.2 |
| bucket 1 only | -111 | -0.8 |
| bucket 2 only | -814 | -6.1 |

Bucket 0 fires when YARN_STORE is the first shop unlocked. The default sends it
to `6c12s_4q_first_yarn`; `6c12s_4q_second_yarn` is much better there.

**The conditional distribution is the part that matters**, because a tape swap
replaces the whole 30-day schedule — it either does nothing or changes
everything:

```
fires on 12.6% of games (452 of 3,600 paired)
conditional mean +14,662 (se 853, t=17.2), positive in 365/452 = 81%
conditional sd 18,145   min -33,940   median +12,618   max +72,456
```

Confirmed on the distribution that actually matters — replayed against the 80
real ladder opponents we have faced: **+429, record 62/80 → 66/80**.

Shipped as 55614625. Real-engine gate +858 (se 242) over 630 paired games.

**The remaining four buckets have now been checked properly and the default is
right for them. Do not re-search this.**

---

## 17. The market layer is exhausted — proven, not assumed (2026-08-19)

Section 14 concluded "the layer is at a local optimum; stop tuning it" from
three refinements landing in noise at n=24-32. That conclusion was correct for
*parameters* and wrong for *structural* changes — `IV_STRUCT` was structural and
worth +670 on the real engine.

With `planner/simulate.py` the parameter question is now settled at ~1,300
paired games per variant, with common random numbers:

| round | what | verdict |
|---|---|---|
| 1-2 | IV_STRUCT / dump / price gate / lead / slot | **+490 shipped**; slot_first -327 (t=-10.8); lead 2 and 4 both worse than 3 |
| 3 | dump ITEM SET (drop STRAWBERRY, MILK, etc.) | refuted: no_strawberry +496 vs unchanged +495 |
| 4 | base tape `_PREEMPT_*` constants | **all noise** |
| 5 | seat-conditional play | refuted, and backwards from the hypothesis |
| 6 | sell SUPPRESSION (hold stock for price) | **catastrophic**, -7,905 to -14,731 |
| — | tuned against the 80 real ladder opponents | live config already optimal (best +23) |

Two findings inside those negatives are worth keeping:

- **kawa's own preempt layer is inert under our configuration.**
  `_PREEMPT_MAX_BATCH` 30→40, `_PREEMPT_FRACTION` 1.0→2.0 and `_PREEMPT_START`
  120→0 each produce an **exact 0.0** paired delta. Our layer has taken over its
  role entirely. This retroactively explains section 5's note that PBT "moved
  backwards" over 10 rounds on these constants — it was optimising dead
  parameters.
- **Our high-volume/low-price selling is structural, not a defect.**
  `planner/analyze_top.py` shows us selling the most units (1,813) at the lowest
  price ($80.4) against ReCurSiON's 1,404 at $129.6, which looks like an obvious
  target. It is not: withholding sales at ANY threshold is catastrophic, because
  the tape's economy depends on continuous liquidation — held stock fills the
  100-item shed, stalls production and starves downstream purchases.

**Also corrected:** section 0's old "12 vs 14 hand slots, ~22% less labour" gap
is not real. Measured over 23 replays we run 277 hires / 12 hands / 2,858 useful
ops — the most ops of anyone on the ladder. Only ReCurSiON runs 14 hands.

---

## 18. The from-scratch planner, 2026-08-19: still far behind

`route/agent.py` under the current best genome is **~-34,000 paired margin vs
the 9-agent pool at ~0% win rate**. Note the honest baseline: gen116's recorded
fitness of -8,192 was measured on a much easier matchup mix (kawa + one rotating
reference + self-play); under the full uniform pool the same genome is -47,787.

Tried and refuted today:

- 10 hand-picked portfolio variants (more GOOSE/EGG, less STRAWBERRY, 8c4s-style
  mix): **all worse than baseline**, some much worse.
- `MIN_CREW` floor in `_size_crew` (`planner/route_v2.py`): **-13k to -52k**.
  The idea was that sizing the crew to *today's* tasks is circular — tasks come
  from planted tiles, which come from yesterday's crew — so a floor should
  bootstrap it. Instead it burns fib-priced cash on idle hands, matching section
  4's finding for the tape. The identity check (MIN_CREW=0 reproduces the
  unmodified agent at exactly +0) confirms the measurement was sound.

`planner/spec_extract.py` turns the tape into an explicit target list. The gap
is **scale, not efficiency**: our realised price per unit is BETTER than the
tape's ($89.7 vs $79.6) and our useful-op rate is higher (44.5% vs 40.1%), but
we hire 188 to its 277 and land 67 PLANT / 13 PLACE to its 186 / 53. We run a
farm about two thirds the size, well.

**Do not edit `route/agent.py` while a search runs** — workers re-exec it per
episode. Copy it (as `planner/route_v2.py`) and edit the copy.

---

## 19. The planner's deficit is PRICE SUPPRESSION, and ten levers were refuted (2026-08-20)

### The measurement that reframes everything

Every diagnostic before tonight measured OUR side -- revenue per work-turn,
$/unit, work fraction, build count, idle rate -- and all of them showed the
planner at or above the tape at 50 tiles. That is why nine experiments chased
the wrong quantity. **`paired margin` is us MINUS them, and the second term was
never measured on its own.**

Over 4 opponents x 3 seeds x both seats:

| we play | own bank | opponent bank | paired |
|---|---|---|---|
| dynamic, 50 tiles | 86,386 | **131,522** | -45,136 |
| the tape | 86,119 | **80,601** | **+5,518** |

**Our economy is already tape-equivalent -- 0.3% apart.** The whole gap is that
the opponent banks ~$51k more against us than against the tape.

### It is price, not volume. The opponent sells exactly as much either way.

| we play | opp units | opp $/unit | opp bank | our units | our $/unit |
|---|---|---|---|---|---|
| dynamic | **1,446** | **114.2** | 131,522 | 1,110 | 104.6 |
| tape | **1,447** | **78.7** | 80,601 | 1,603 | 80.5 |

The opponent sells 1,446 units against us and 1,447 against the tape -- the tape
takes not one unit from them. It wins by selling 1,603 units to our 1,110, which
drags the shared price level down 31% for everyone. **The tape suffers the low
prices too ($80.5/unit); it wins because at that price level the larger producer
comes out ahead.** Our high $/unit is a symptom of being small, not a strength.

So the requirement is precise: **produce profitably above ~50 tiles.**

### Ten levers, all refuted

| lever | result |
|---|---|
| proportional portfolio scale-up | -87,245 |
| crew floor (MIN_CREW) | -52,000 |
| crew + tiles together (schedule-driven) | -62,285 |
| cycling-crop portfolios (wheat-heavy) | -150,176 |
| geese (the uncapped book) | -183,427 |
| front-loaded purchases | -42,897 |
| SeasonPlan layout transplant | -86,211 |
| whole-tile triage scheduler | +/-2,700, i.e. noise |
| wheat flooding | -95,916, **and it makes the opponent RICHER** |
| capped-book flooding | -81,980, **opponent's volume does not move at all** |

Two of these are worth keeping as facts rather than scores:

- **Flooding wheat subsidises the opponent.** The engine allows `BUY_PRODUCT`
  only for WHEAT and FERTILIZER, so wheat is what they buy for feed. Pushing our
  wheat sales 285 -> 536 raised their bank 106,957 -> 112,248.
- **There is no headroom to steal.** Across every capped-book variant the
  opponent sold 753-755 units regardless of whether we sold 540 or 638. Town
  drain replenishes fast enough that both players sell what they produce. An
  earlier note in this document reasoned that capped products cannot be denied
  because both clear at $1; the real reason is simpler -- volume is not
  contested at all, only price is.

### Why buying to dump cannot work

`_commit_unit` quotes `BUY_PRODUCT` at `market_price(inv - 1)`, i.e. post-buy,
with the engine's own comment: "so a buy/sell round-trip against an unchanged
market nets zero". Price suppression has to be PRODUCED, never purchased.

### Status

Mechanism fully characterised, no usable lever found. This is not a parameter
problem: it needs a day scheduler that stays profitable past 50 tiles, and the
triage rewrite (`dynamic/router2.py`) did not deliver that. Do not re-run
portfolio or cash-flow searches -- `planner/role_gradient.py` measured all 24
single-role perturbations of the 50-tile optimum negative, and a 19-generation
cash-flow GA peaked at generation 1 (-57,830 from -78,027) and then went 17
generations without improvement.

---

## 20. The tape+market line is exhausted too (2026-08-20)

`evolution/` ran 600 mutants over 3 rounds -- tape-map recombination, cross-family
window splices, and jitter on the base tape's constants -- with **zero clearing a
+200 screen**, and stopped on its own plateau rule.

Market-layer ideas tested and refuted tonight, each with controls:

| idea | result |
|---|---|
| adaptive dump sizing from the exact price curve | 12 variants, all negative; best -34 |
| ...against fixed-fraction controls | no adaptive setting beat its fixed control |
| depth concentration (dump only MELON+FERTILIZER) | 8 variants, all negative, best -127 |
| day gate on late-game dumping | +22 (pool), +10 (ladder replays) |
| weighted / most-recent cadence predictor | 5 variants, -126..-181; median stands |

**The front-run audit is the useful artefact.** Over 144 games, tracking every
firing against the opponent's exactly recovered sales: we clear ahead on
**94-99%** of firings and same-step collisions are rare (the engine quotes both
players against the same pre-commit inventory, so a same-step sale is priced
identically for both -- beating them requires a strictly earlier step). Position
is not the problem. Realised price sorts by market DEPTH instead:

```
FERTILIZER  493 units to floor   +1.1 per unit
MELON       158                 +24.3
MILK         76                  -2.8
STRAWBERRY   62                  -2.1
WOOL         59                  -2.2
```

On three of five products we sell first and realise LESS: dumping into a shallow
book walks our own later units down, the town drains, and the opponent sells into
the recovery above our average. But the A/B refuted acting on it -- concentrating
on the deep books scored -127 -- so the audit signal is correlational, and does
not separate our dump's causal effect from the price path it shares with theirs.

---

## 21. Measurement rules added tonight

**Identical rows across variants means a parameter is inert, not that the idea
is neutral.** This cost three separate measurements:

- `TERMINAL_STEP` belongs to `route/agent.py` and does not exist in the tape
  build; nine terminal-timing variants returned byte-identical numbers.
- `PLAN_GATE_DAYS >= 0` is true for 0, so a SeasonPlan "off" control silently ran
  the tape's 73-tile layout with 50-tile parameters and scored -164,312 against
  its real -78,101.
- A sell-policy sweep produced seven identical rows because the reserve was
  never binding; a follow-up probe then mislabelled the cause as the reserve
  price when the actual hold is the FEED buffer.

`dynamic/agent2.py::configure()` now reports unknown keys and raises under
`STRICT_PARAMS`. **Apply the same guard before trusting any sweep.**

**Do not select games by outcome and then read their trajectory.** A per-day
margin trace of 7 losses against 7 wins appeared to show "endgame collapse" --
losses led at day 15 and bled out. That is circular: a loss is by definition a
game whose margin ends negative. Two interventions built on it (day gate,
adaptive sizing) found nothing, because the pattern was an artefact of the
selection. Compare at a FIXED point instead: of all games led at day 15, what
fraction converted?

**Behavioural cloning from a tape cannot work, and the control proves it.**
`planner/bc_data.py` + `bc_train.py` reach 92.8% action accuracy (96.2% on
non-move ops) from 2.7M samples. The resulting agent banks **$288** against the
tape's $89k. Letting the TAPE drive and merely asking the network what it would
do gives 92.6% agreement -- so the model is correct and the failure is covariate
shift. It is unfixable here: DAgger needs the expert to label the states the
learner reaches, and a fixed 719-step action list cannot be queried off its own
trajectory. Adding data does not help; more on-distribution samples say nothing
about off-distribution states.

---

## 22. The suppression math, and why neither half of the architecture can use it (2026-08-20)

Built to the plan of pricing every decision through the real market: an exact
market model, an opponent inventory tracker, and both wired into the market
controller and the day scheduler. **The math is right, both wiring points are
measured inert, and the reasons are structural rather than parametric.**

### The marginal value of a sale is not its price

`dynamic/market_model.py` reproduces the engine's `market_price` bit for bit
(0 mismatches over 9 products x 4,001 inventories) and adds the analytic slope.
Market inventory is a pure accumulator -- `_town_consume` subtracts the same
amount whatever we do -- so an extra unit sold now clears every LATER sale by
BOTH players one slope lower, for the rest of the season. Differentiating the
margin gives

    MV = P(inv) + alpha * |P'(inv)| * (N_them - N_us)

The suppression term is **signed on the difference of the two remaining
supplies**. That single fact retro-explains three earlier negatives: flooding a
book we ourselves still have to sell into is self-harm, which is exactly what
wheat flooding (-95,916) and capped-book flooding (-81,980) were measuring.

**Section 20's front-run audit was reading the wrong cause.** It sorted
realised-price edge by market DEPTH; the real variable is NON-RECOVERY, and
depth only correlates with it. Season town demand against units-to-floor:

    MELON       30 demand / 158 to floor   ratio 0.19   audit +24.3
    FERTILIZER   0        / 493            ratio 0.00   audit  +1.1
    WOOL       246        /  59            ratio 4.2    audit  -2.2
    MILK       331        /  76            ratio 4.4    audit  -2.8
    STRAWBERRY 422        /  62            ratio 6.8    audit  -2.1

MELON is in **no shop's product list** -- only the town centre's 1-per-24-steps
touches it -- and FERTILIZER has no buyer at all. Those two are the only books
where being first is worth anything, and they are exactly the two the audit
scored positive. The three it scored negative are the three the town refills
4-7x over. Perfect ordering, and it is derivable without playing a game.

### The opponent's holdings are recoverable, and they are always small

`dynamic/opp_state.py`. Their tiles are fully public, including `yield_units`,
`pending_care_bonus` and `money`. Within a day `yield_units` can only fall, and
only HARVEST lowers it, so summing intra-day drops measures their harvests
**exactly** -- validated in `dynamic/opp_state_test.py`, where the residual
mirrors the sales side unit for unit.

Two corrections tame the sales side, which is blind only at the $1 floor:
floor reconciliation (a floored book cannot be suppressed anyway -- `slope()` is
0 there) and the shed cap. `_drop_inventories_to_shed` keeps **100 items TOTAL
across all products and discards the overflow**, so no estimate above ~100 is
physically possible; that alone cut MILK's drift from 267 units to 24.

The useful finding is what survives: **the opponent can never be sitting on a
hoard**, so `N_them` is dominated by what their tiles will still produce, not by
what they hold.

- The structural forecast under-reads the truth ~2.5x (72.8 strawberry against
  an actual 192.7) but has RANK: correlation 0.66-0.82 on the five products
  that matter. A scalar gain fixes a bias, so the bias was left to calibration.
- **Extrapolating their exact observed harvest rate instead is worse.** It
  halves the bias and takes strawberry's correlation from 0.66 to -0.00 and
  melon's from 0.80 to -0.04. Kept behind `blend`, defaulted off.

### Why the market controller cannot use any of it

Attributing every unit we offer to the branch that offered it (3 seeds, vs kawa):

    shed-panic dump 79%     terminal dump 19%     the price gate 2-3%

The reserve price, the front-run hold and the opponent's reserve scale together
govern **one sale in forty**. The agent's real sell policy is "the shed passed
20% -> dump everything", and that is also, by accident, why our realised $/unit
is HIGHER than the tape's: dumping in small frequent batches meters the book.

This is the true cause of the "identical rows" symptom in section 21. The gate
is not merely unbinding on some parameter settings; it is nearly dead code.
Every MV variant lands in noise -- MV ordering of the panic dump -34 (t=-0.0),
alpha 0/0.5/1/2 all within 200, `SHED_PANIC_FRACTION` 0.10 exactly +0.

Metering is worse than inert: -32,749 (t=-12.7). Holding stock fills the shed
and stalls production, the same mechanism section 17 round 6 measured.

### Why the scheduler cannot use it either

`dynamic/task_value.py` prices every task through the live market -- a melon
harvest and a wheat harvest score 900 apiece under `OP_VALUE`, though one is six
units at $250 and the other six at $25. It is correct and it is **exactly +0
over 144 paired games**, because:

| day | tiles with work | op-turns wanted | crew turn cap | utilisation |
|---|---|---|---|---|
| 12 | 63 | 102 | 288 | 35% |
| 18 | 63 | 92 | 264 | 35% |
| 24 | 57 | 110 | 264 | 42% |

**Mean 35%, max 43%, and demand exceeds capacity on 0 days of 30.** Task value
only decides which work gets DROPPED, and nothing is ever dropped. `partition`
assigns by angular sweep; value reaches `build_tour` only on over-subscription.

So the whole objective `J = sum V_task - lambda*C_move` optimises an allocation
problem with 65% slack, and every coefficient in it (lambda, alpha, K, gamma,
beta) is unidentifiable by construction. This also explains `MIN_CREW` at -13k
to -52k: we already hire hands with nothing to do.

### What the audit says the gap actually is

`dynamic/revenue_audit.py` prices both players' sales through the commit hook.
Against kawa, 3 seeds:

| | our units | our $ | their units | their $ |
|---|---|---|---|---|
| dynamic scheduler | 1,132 | 89,008 | 1,521 | **137,382** |
| the tape | 1,704 | 91,889 | 1,704 | **91,734** |

**Our own economy is fine -- our bank is 77,614 against the tape's 71,544 in the
same matchup.** The entire gap is the second column. MILK is the clearest case:

    against us      we sell 156 @ $138, they sell 265 @ $141   margin  -15,789
    against the tape   248 @ $40,          249 @ $40           margin      -28

**The tape does not win milk. It neutralises it**, and that is worth +15,761
because the deficit it erases is larger than the revenue it gives up. Same shape
on strawberry (-23,625, crushable to about -6,480).

That is the mechanism, stated exactly, and it needs volume we do not have --
1,132 units against 1,704. Suppression cannot be bought (`BUY_PRODUCT` quotes
post-buy, so a round trip nets zero) and cannot be timed (we already dump
continuously). **It has to be PRODUCED.**

### Refuted tonight, with controls

| lever | result |
|---|---|
| MV ordering of the shed-panic dump | -34 (t=-0.0) |
| MV metering when we out-supply them | -32,749 (t=-12.7) |
| MV re-pricing the sell gate, alpha 0..2 | all exactly +0 (gate not binding) |
| economic task value in the scheduler | exactly +0 (capacity not binding) |
| economic task value + triage | -869 (t=-1.1) |
| WHEAT priority 0.014 -> 0.85 | **-75,378** (displaces melon/strawberry) |
| ...with 12 / 18 wheat tiles | -123,861 / -91,455 |
| 12 wheat tiles at current priority | -4,161 |
| 6 geese (EGG trades $89, nobody produces it) | -49,999 |
| feed buffer 1.0 -> 2.5 | -30,343 |

Also measured and NOT a defect: **shed-overflow discards are 15 units a game
against the tape's 21.** The nightly 100-item cap is not eating our output.

### Status

The suppression theory is sound and now has exact tooling behind it. Neither
the market controller nor the day scheduler is the place it can act, and both
were shown so by measurement rather than argument. The binding constraint is
unchanged from section 19 and is now quantified from a second direction:
**produce more units profitably.** Until that moves, this line stays at -90,650
paired against the 9-agent pool while the shipped tape+market build is +9,016.

### 22a. One thing that did work: refill dead tiles with wheat

`_last_plant_day` is 19 for STRAWBERRY and 17 for MELON, but **25 for WHEAT**.
After day 17 any tile that dies is dead for the season, because its own role can
no longer return anything before the buzzer -- and our board loses 10 tiles over
the last third (49 -> 39) where the tape holds ~70 flat. Replanting those with
wheat costs $10 and displaces nothing.

`NURSE_LATE=1, NURSE_CROP="WHEAT"`, paired margin against the 6-agent pool:

| seed set | n paired | vs base | se | t | paired wins |
|---|---|---|---|---|---|
| 90210 | 144 | **+1,768** | 373 | 4.7 | 96/144 (67%) |
| 4242 | 240 | **+1,893** | 286 | 6.6 | 166/240 (69%) |
| 777001 | 360 | **+2,049** | 221 | 9.3 | 259/360 (72%) |

Controls: `NURSE_LATE` with no `NURSE_CROP` is exactly +0, and
`NURSE_CROP="MELON"` is exactly +0 -- melon can never be the refill because its
own last plant day is 17. `SEED_BATCH_PER_TURN=16` on top adds ~+600 but its own
control is only +822 (t=1.6), so it is not established on its own.

**Mechanism confirmed, not assumed.** The two agents are byte-identical through
day 19 and then diverge exactly as predicted:

    day          15    17    19    21    23    25    27
    baseline     47    48    47    43    43    42    37
    late wheat   47    48    47    47    46    46    42     wheat 245 -> 282

Now on by default in `dynamic/agent2.py`. Note for future sweeps: the baseline
has moved, so an identity control has to set `NURSE_LATE=0`, not leave it unset.

### The same idea at the other end of the season does NOT work

Deferring expensive seed to follow the tape's cash-flow order is worse, and
consistently: STRAWBERRY held to day 8 is -10,029, day 11 -14,860, day 14
-32,276. Strawberry is an ongoing crop with a **4-yield lifetime cap**
(`production_count > max_yield` stops it, engine line 796), so every day it is
held back is a yield it never takes. Nursing wheat through the gap recovers
+4,000 to +6,000 of that but never the whole cost.

Also refuted with controls tonight, all on the opening ramp:

| lever | result |
|---|---|
| `BUY_ANIMALS_FIRST=0` (cheap seed before $400-500 animals) | **-17,719** |
| ...with batch 16 | -18,558 |
| `PLANT_MISS_TOLERANCE` 16 -> 0 / 2 / 4 | -1,214 / +1,311 / +183, all noise |
| the 73-tile season plan (85 tiles realised) | -62,148 |

The opening-order hypothesis was wrong in the direction it was proposed: animals
first is right. They produce fertilizer unconditionally from day 1 and milk/wool
for twenty-plus days, where a $100 strawberry seed returns nothing until day 12.

### Why the 85-tile plan still fails, measured

Crew capacity is NOT the reason, and the earlier reading of this was wrong on a
subtlety: `_size_crew` sizes the crew TO the task list, so utilisation is pinned
by construction at ~32% whatever the portfolio (50 tiles 35%, 85 tiles 32%,
0 days over 100% in either). It measures the crew-sizing ratio, not slack.

The real breakdown of where unit-turns go, against the tape on the same seed:

    us, 50 tiles   move 43%  enable 33%  idle 13%  produce 5%  build 2%   5,485 turns
    us, 85 tiles   move 47%  enable 30%  idle 12%  produce 4%  build 3%   5,330 turns
    the tape       move 52%  enable 28%  idle  8%  produce 6%  build 4%   6,914 turns

**Movement is not our problem -- we are better at it than the tape (43% vs 52%)
and it still banks twice as much.** It simply does 26% more unit-turns and 2.5x
more build ops. And under the 85-tile plan our cash sits at $0.3k from day 3 to
day 15 while the tape is at $10.3k by day 12, so the extra tiles are planted and
then die unwatered (19 tiles on day 3 down to 9 on day 6). More tiles without
the cash to crew them is strictly worse, which is the sixth independent
confirmation of that.

---

## 23. Opportunity cost as a module, so the windows find themselves (2026-08-20)

Section 22a's late-wheat refill was found by hand. It is one instance of a rule:

    V_task = V_self + V_suppress - V_opportunity
    V_opportunity(tile, t) = max over feasible c of E[Profit(c, tile, t)]

After day 19 nothing but WHEAT and CARROT can still be planted, so the feasible
set collapses to one useful element, `V_opportunity` goes to 0, and any
positive-profit crop should be planted automatically. `dynamic/opportunity.py`
computes the feasible set and each member's profit, so windows of that shape
fall out of the arithmetic instead of being noticed.

### E[Profit] is exact, and the two yield rules are different

Both had been misread earlier in this project, so they are now written down:

- **NON-ONGOING (WHEAT, CARROT, MELON).** `_new_plant` seeds `yield_units = 1`
  and the nightly refresh SKIPS them entirely. Yield comes from WATER, and only
  inside `[(max_yield_day+1)//2, max_yield_day]` (engine line 438-443). WHEAT
  therefore makes 1 + 3 = **4 units for 6 unit-turns**; MELON makes 6 by age 10.
  HARVEST then DELETES the plant, which is what lets it cycle a tile.
- **ONGOING (STRAWBERRY, TOMATO).** `production_count > max_yield` stops accrual
  permanently (engine line 796), so `max_yield` is a **LIFETIME cap**.
  STRAWBERRY produces exactly 4 units, at ages 10/12/14/16. That is the
  arithmetic behind deferral measuring -10,029 to -32,276 in section 22a: every
  day held back is a yield never taken, not a yield delayed.

### It reproduces the hand-found window and beats it

`ALLOC_MODE=1` keeps a tile's searched role while that role is feasible and
profitable, and otherwise plants the best thing that still is. Paired margin
against the 6-agent pool, four disjoint seed sets, all against the same static
base (`NURSE_LATE=0, ALLOC_MODE=0`):

| seeds | n | hand-coded late wheat | alloc1 L13 | alloc1 L15 |
|---|---|---|---|---|
| 31337 | 240 | +2,311 (t=8.9) | — | **+2,938** (t=8.4) |
| 606060 | 288 | +2,363 (t=8.7) | **+3,020** (t=10.7) | +2,872 (t=10.5) |
| 818181 | 288 | +1,863 (t=7.6) | — | **+2,545** (t=7.6) |
| 246810 | 288 | +2,229 (t=9.4) | **+2,631** (t=8.7) | +2,449 (t=8.0) |

The allocator beats the hand-written rule by +500 to +680 on every set, at
82% paired wins on the largest. `ALLOC_LABOR` is a **plateau over 13-17**, not a
spike, with a cliff at 20 (-11,684) where strawberry's profit turns negative and
the fallback abandons it everywhere. Shipped at 13.

**`ALLOC_MODE=2` (always plant the argmax) is -53,163.** The searched static
layout carries real information about WHERE a role belongs that a per-tile
profit comparison does not have; the allocator is only allowed to act where the
static answer has expired.

### What it found on its own

Instrumented over 3 seeds, substitutions of (searched role -> chosen crop):

    MELON      -> WHEAT   days 20-27      the hand-found window
    STRAWBERRY -> WHEAT   days 20-25      the same window, other tiles
    STRAWBERRY -> MELON   days 18-19      NEW -- nobody had looked here
    anything   -> None    days 28-29      correctly stops planting

### A candidate the formula proposed and the engine rejected

`_last_plant_day` keys on `max_yield_day`, but HARVEST is gated on
`first_yield_day` (engine line 457) -- `max_yield_day` only bounds accrual. The
true bound is later: **MELON 17 -> 19** (still its full 6 units, since the
accrual window shuts at age 10 anyway) and **WHEAT 25 -> 27** (2 units, ~$100,
on a $10 seed). Both have positive gross profit, and the STRAWBERRY -> MELON
window above needs them.

Measured: **-1,546 (t=-7.0) on its own, -1,656 with the allocator, -2,085 with
the hand-coded refill.** So the flat $/unit-turn labour price understates a LATE
planting: it waters every day until harvest against a crew that is winding down,
and it finishes inside the terminal liquidation window where the turns are
wanted for selling. Kept reachable as `TRUE_LAST_PLANT_DAY`, defaulted off.

This is the formula-and-experiment loop behaving correctly. The module proposed
three windows; the engine kept one, and the one it kept is worth more than the
hand-written version of it.

### Shipped defaults in `dynamic/agent2.py`

    ALLOC_MODE = 1        ALLOC_LABOR = 13.0        TRUE_LAST_PLANT_DAY = 0
    NURSE_LATE = 1        NURSE_CROP = "WHEAT"      (both bypassed while ALLOC_MODE is on,
                                                     and worth +2,229 if it is turned off)

`ECON_VALUE` remains exactly inert alongside all of this (+2,449 with and
without), as section 22 predicted: nothing is ever dropped, so the thing that
decides what to drop cannot matter.

---

## 24. Global resource valuation: the veto works, the replacement does not (2026-08-20)

`dynamic/enpv.py` implements the full framework -- ENPV per asset with an
endogenous price, dynamic feed costing, a multi-dimensional knapsack, the labour
shadow price, bundle ROI and a burn-rate cash reserve. Two wirings of the same
correct valuation, and they differ by 95,000 paired margin.

### The endogenous price is the piece a fixed-count portfolio cannot have

`market_model.realized_price(item, inv, n, shops, days, opp_units)` returns the
AVERAGE $/unit for selling n units over `days`, against the town's drain and the
opponent's expected supply. A marginal quote prices one more unit; an asset
produces many, and each lowers the price of the next:

    n units sold over 18 days, opponent selling the same
    item          n=20   n=50  n=100  n=200  n=400      drain/day
    MELON          248    228    148     73     38          1
    STRAWBERRY     228    219    203    151     11         25
    EGG             55     54     51     43     41         13

A genome storing TC_COW=5 prices all five cows identically. With the feedback
in, the marginal animal is valued against the book the existing herd has already
filled, and the numbers are decisive: at 6 sheep owned the seventh is worth
**-118**, and the searched genome buys seven.

### Wholesale replacement: -90,059

`ENPV_BUY` replaces the searched purchase throttle with the knapsack. It starts
BETTER -- 20 producing tiles by day 3 against the base's 8, which is the ramp
this project has been chasing since section 19 -- and then collapses to 8 tiles
by day 9 with cash pinned at $0.00. It spends every dollar on seed and cannot
afford a single hand to water it.

Two bugs found and fixed on the way, both worth keeping:

- **The reserve must be sized to the crew the farm WILL need**, not the one it
  has. Crew is sized to the current task list, so on day 0 it is 1 and a burn-
  rate reserve built from it is about $2. (-115,067 -> -90,059 when fixed.)
- **It needs a floor at SPEND_RESERVE.** The rest of the agent refuses to hire
  while `money - cost < SPEND_RESERVE`, so a reserve below that number does not
  under-save, it silently disables hiring.

Even fixed it is -90,059, and insensitive to every parameter (L8 -88,718,
L20 -115,359, dry-days 1/2/4 all within 600). That is a behavioural break, not
a mis-valuation.

### Subtractive: +4,208 mean over three seed sets

`ENPV_VETO` keeps the searched purchase order exactly and only DECLINES a
purchase whose ENPV has gone negative. It can remove spending, never redirect it.

| ENPV_LABOR | 135791 (n=240) | 515151 (n=288) | 929292 (n=288) |
|---|---|---|---|
| **8** | **+3,626** (t=3.4) | **+4,619** (t=5.1) | **+4,378** (t=4.6) |
| 10 | — | +4,876 (t=4.8) | +2,126 (t=2.0) |
| 13 | +1,598 (t=1.4) | +4,681 (t=4.5) | +2,946 (t=2.8) |
| 20 | -3,279 | — | — |
| 30 | -27,650 | — | — |

Shipped at 8, the stable point. Above ~20 the veto starts refusing purchases
that pay.

**The veto is inert while ALLOC_MODE=0** -- it needs `S["econ"]`, which is only
built when the allocator or ECON_VALUE is on. Measured as two byte-identical
rows, which is exactly section 21's symptom.

### THE PATTERN, now established across five attempts

| change | shape | result |
|---|---|---|
| opportunity allocator (ALLOC_MODE=1) | **additive** -- acts only where the static role has expired | **+2,865** |
| ENPV veto | **subtractive** -- only removes negative-ENPV spending | **+4,208** |
| ALLOC_MODE=2, free argmax layout | replacement | -53,163 |
| ENPV_BUY, knapsack purchasing | replacement | -90,059 |
| MV metering in the market layer | replacement | -32,749 |

**The searched genome's parameters are co-adapted.** A principled subsystem
dropped in on top of them breaks that co-adaptation faster than its own
correctness repays. Every gain this session came from a change that acts only
where the existing policy does nothing, or that only declines. Design new work
to that shape.

### Cumulative, one fresh seed set (n=336 paired)

| build | paired margin | vs session start | t |
|---|---|---|---|
| session start | -80,909 | — | — |
| + late wheat (hand-coded) | -78,605 | +2,304 | 9.3 |
| + opportunity allocator | -78,044 | +2,865 | 10.7 |
| **+ ENPV veto (SHIPPED)** | **-73,390** | **+7,519** | **8.5** |

---

## 25. `MODEL.md` — the mathematics, in one place

The derivations scattered through sections 22-24 are collected in
[`MODEL.md`](MODEL.md), written as GitHub-rendered LaTeX so the formulas stay
readable and reviewable rather than living in docstrings.

It covers: the engine's price curve and its exact reproduction; the depth and
recovery ratio that decide which books can be suppressed at all; the marginal
value of a sale and the sign of its suppression term; the endogenous realized
price; exact opponent sales and harvest recovery with the shed-cap and floor
corrections; both yield rules; asset ENPV; the multi-dimensional knapsack, the
labour shadow price, bundle ROI and the burn-rate reserve; and the opportunity
cost that makes the "no-displacement window" fall out of arithmetic.

Section 10 is the calibration table -- every coefficient names the data that
fixed it. Section 11 is the refuted list, with the pattern that now governs how
work here should be shaped: **additive or subtractive changes hold, wholesale
replacements break.**

---

## 26. The target, quantified — and three more refutations (2026-08-20)

### What "beat our best model" actually means

Measured on the SAME pool and the SAME seeds, paired margin, both seats
(n = 336 paired games):

| agent | paired margin |
|---|---|
| **shipped `submission/main.py` (tape+market)** | **+12,160** |
| unmodified kawa tape | +11,628 |
| dynamic scheduler, this session's best | **−73,390** |

**The gap is 85,550, and the shipped agent wins 329 of 336 paired seeds (98%).**
Note also that the whole market-intervention layer is worth only +532 over the
raw tape on this pool — the tape is essentially all of it.

### The tape's own season plan, read off its issued orders

```
day 0   MELON x12, WHEAT x7, buy_WHEAT x9, HIRE x5, COW x2, SHEEP x2
        -> 23 producing tiles by day 1, on $3,094 of a $3,000 opening
day 1-10   cash never rises above $1,534; it runs the entire ramp at ~zero
day 11  cash jumps to $14,794 as the melon lands, and it buys 23 STRAWBERRY
day 12  68 producing tiles
```

Twelve melon on day 0, against our `TC_MELON` of 8 for the entire season — and
melon is the one book that never recovers (30 units of season demand against 158
to the floor), so it is the one place quota preemption is real.

### Three more refutations, and a sharper form of the pattern

| lever | shape | result |
|---|---|---|
| mean-variance risk adjustment | subtractive | **inert** |
| ENPV purchase ORDER (same budget, same caps) | re-ordering | **−12,542** |
| melon-forward opening, TC_MELON 12 / 16 | portfolio | −21,056 / −25,428 |
| ...with RP_MELON raised to 0.97 | portfolio | −34,036 |

The risk adjustment is inert for a structural reason worth keeping: `ENPV_VETO`
is a binary `ENPV > 0` test, so a variance penalty small enough not to refuse
everything is too small to flip a sign. λ=1e-5 fires on 0% of games, 1e-4 on 2%
(+11), 1e-3 on 31% (+228, t=0.5). Kept, defaulted off; it is the right object if
ENPV is ever used for RANKING instead of a sign test.

**`ENPV_ORDER` sharpens the pattern.** It changes nothing about how much is
bought — batch sizes, per-turn caps and the reserve are untouched, and the same
total is spent. Only the SEQUENCE changes, and only where cash binds. It costs
−12,542. So the boundary is not "replacement vs addition" in any loose sense:

$$\text{touching a co-adapted decision AT ALL} \Rightarrow \text{breaks}$$
$$\text{acting only where the policy does nothing, or only declining} \Rightarrow \text{holds}$$

### What this implies for the remaining gap

Closing 85,550 by hand is not on the evidence available. Roughly 25 distinct
levers have now been refuted across two sessions, spanning the market layer, the
day scheduler, the portfolio, cash flow, opening order and global resource
allocation. The three that worked total +7,519 and all three are additive or
subtractive.

The one honest lever left is not an insight, it is COMPUTE: `best_genome.json`
was searched against `dynamic/agent.py` before any of the market model, the
allocator or the veto existed, and it peaked at generation 1 and then went 17
generations without improving. **It is an optimum of a different agent.** A
search does not suffer the co-adaptation problem that every hand-written
subsystem hit this session, because it re-adapts every parameter at once.

`dynamic/search2.py` seeds from the current shipped configuration, puts the two
new labour prices and the two new switches in the genome, and keeps the fitness
unchanged (paired margin, common random numbers, both seats, ladder-range
seeds). `ALLOC_MODE=2` and `ENPV_BUY` are deliberately NOT in the search space —
both are measured strongly negative.

---

## 27. Three modules built alongside the GA (2026-08-20, search running)

`dynamic/search2.py` is running, so `dynamic/agent2.py` and everything in its
import graph are FROZEN — workers re-exec it per evaluation. All wiring went
into `dynamic/agent3.py`, a copy with the new switches defaulted off, so
agent3 with no parameters is agent2 exactly.

### 27.1 Fitted opponent supply — the strongest result of the three

`dynamic/opp_predict.py`. Ridge least squares on eight public features
(structural forecast, tracked holdings, exact harvest rate, exact sales rate,
days left, their tiles of this item, their herd size). Held out **by GAME**, not
by row — rows from one game share its board, shop draw and opponent, so a row
split would report a fit that does not exist.

| item | model bias / \|err\| / corr | structural bias / \|err\| / corr |
|---|---|---|
| STRAWBERRY | −0.9 / 11.3 / **0.99** | −136.4 / 136.4 / 0.54 |
| MELON | −0.9 / 9.0 / **0.96** | −24.3 / 24.3 / 0.75 |
| MILK | 1.3 / 11.6 / **0.97** | −75.7 / 75.7 / 0.65 |
| WOOL | 0.5 / 12.5 / **0.92** | −47.7 / 48.0 / 0.80 |
| WHEAT | 16.1 / 75.1 / **0.75** | −308.1 / 308.1 / **−0.48** |
| FERTILIZER | 3.7 / 7.8 / **0.99** | 26.0 / 50.2 / 0.67 |

The 2.5x bias is gone and correlation goes 0.54–0.80 → 0.92–0.99. Caveat: the
held-out games share the same 6-opponent pool, so this is not evidence of
transfer to an unseen opponent. Degrades gracefully — no theta means the
structural forecast, i.e. agent2's behaviour.

### 27.2 Market timing — one derived correction to a hardcoded list

`dynamic/market_timing.py`. `_process_market` runs before `_town_consume` in
the same step, so holding a sale across a town tick is quoted after the drain
rather than before it, worth exactly

$$\text{gain per unit} = |P'(q)| \cdot d_{\text{tick}}(i)$$

| item | \|P'\| | tick drain | $/unit held | in `FRONT_RUN_ITEMS`? |
|---|---|---|---|---|
| MILK | 2.098 | 3 | 6.30 | yes |
| WOOL | 2.322 | 2 | 4.64 | yes |
| STRAWBERRY | 0.343 | 4 | 1.37 | yes |
| **MELON** | 1.200 | **0** | **0.00** | **yes — and worth nothing** |

**No shop sells MELON**, so its tick drain is zero and holding it gains $0 while
donating a step to the opponent. Note this ranks the books the OPPOSITE way from
suppression: suppression wants the books the town cannot refill, timing wants
the ones it refills hardest.

### 27.3 The spatial/VRP model — built, and it refutes its own premise

`dynamic/spatial.py` implements the graph model, Manhattan `D(u,v)`,
`TravelTime` over the solved tour, and the hard constraint
$\sum L_{req} + \text{TravelTime} \le L_{max}$, using the real `partition` and
`build_tour` rather than a formula.

**At the crew the agent actually runs, nothing is dropped:**

```
73 tiles with 12 workers:  served 73, dropped 0
50 tiles with 12 workers:  served 50, dropped 0
```

| workers | crop tiles servable | animal tiles servable |
|---|---|---|
| 8 | 65 | 37 |
| 12 | 80 | 52 |
| 16 | 100 | 67 |

So the 73-tile collapse is **not** a routing failure and the hard constraint has
nothing to bite on. It is the cash chain, as section 26 measured: more tiles →
more crew → crew costs cash → no cash on days 3–15 → tiles die unwatered.

The one genuinely useful number that fell out: **crew sizing that counts travel
is roughly double what op-turn sizing says** (73 tiles needs 10 workers, op-turn
sizing says 4). That is the same correction `enpv.crew_needed` already applies
via TILES_PER_HAND, and it is now derivable instead of fitted.

### 27.4 On bitmaps, space-filling curves, APSP and Hungarian assignment

Assessed against this codebase rather than in general:

- **Precomputed APSP / "never run BFS or A\* in the engine"** — already
  satisfied by construction. `grep -rn "bfs|dijkstra|astar|A\*"` over
  `route/ dynamic/ planner/` returns **nothing**: movement is unrestricted and
  LOCKED tiles are passable, so `route/geom.dist` is plain Manhattan and already
  O(1). There is no path search to remove.
- **Space-filling curve for routing** — `partition` already sorts by an angular
  sweep around the shed, which has the locality property a Z-order or Hilbert
  index would provide. Same role, already present.
- **Bitboards** — would speed up set operations, but speed is not binding: a
  full game is 0.4s, the agent runs 85 tiles without incident, and nothing times
  out. There is no crash to prevent.
- **Hungarian / LAP instead of the greedy sweep** — the only one with real
  algorithmic upside, and it has no slack to recover: at 12 workers the current
  partition already drops zero tasks at 73 tiles. It is also a wholesale
  replacement of a co-adapted component, which is the shape that has failed six
  times here.

### 27.5 A strictly better opponent estimate makes a strictly worse agent

The fitted predictor is better on every metric that describes an estimator, and
it measures **-18,502** in play. Two explanations were proposed and both were
tested and refuted:

| hypothesis | test | result |
|---|---|---|
| co-adaptation via `ENPV_LABOR` (calibrated against the biased forecast) | re-calibrate it | L8 -18,611, L6 -19,866, L4 -20,575, L2 -20,084, **L0 -20,400** — monotonically worse |
| covariate shift (fit on games where the TAPE held our seat) | re-fit on OUR games, same held-out quality | **-18,502**, i.e. unchanged |

Damage channels, isolated: `ENPV_VETO=0` recovers most of it (-18,502 ->
-5,488) and the remaining -5,488 is the opportunity allocator, whose
`price_of` is `ctx.unit_price` and therefore also carries `N_them`.

**So the BIAS was doing useful work.** Both consumers -- the veto by hand, the
allocator by hand, and the portfolio by an earlier GA -- were tuned against a
forecast that under-reads the opponent by 2.5x. Under-reading their supply makes
the agent behave as though the books are emptier than they are, which makes it
produce and sell more aggressively, and aggression is exactly what it lacks.
Correcting the estimate makes it correctly timid.

This is the sharpest statement of the session's pattern: **it is not that
replacements are wrong and additions are right. It is that every hand-written
component here is calibrated against the errors of the ones around it.** A
component cannot be improved in isolation, however correct the improvement.

The implication is a search, not another hand fix: put the predictor in the
GENOME and let the search re-adapt its consumers around it. That is what
`dynamic/search3.py` does.

**Discipline note:** the `MV off` variant in that sweep returned a row
byte-identical to its sibling because `MV_MARKET` was already 0. Section 21's
rule applies to my own sweeps too — confirm a parameter is live before spending
games on it.

---

## 28. GA methodology: selection is sound, the recorded champion is not

`dynamic/search2.py` and `search3.py` score each genome on 5 seeds x 6 opponents
= 30 games, 15 paired. Section 5's rule says a variant needs >=100 games before
its rank means anything, so that number deserved a second look. It splits into
two questions with different answers.

**Selection is fine.** The seed list is drawn once per generation and every
genome in that generation plays the same seeds, so within-generation ranking is
paired with common random numbers — the low-variance comparison. That is the
only comparison selection pressure actually uses.

**The recorded champion is biased upward.** `best_fit` is a running max across
generations, and generation 6's best was scored on generation 6's seeds while
generation 7's was scored on different ones. Taking a max over noisy draws from
different distributions selects partly for a lucky seed draw, and the checkpoint
saves whatever won that draw. So a headline like "-48,821 at generation 6" is
not comparable to a hand-tuned number measured at n=336.

**Consequence for anyone reading a `best_genome*.json`: re-measure it before
believing it.** The fitness field records what won a 15-paired-game draw, not
the genome's standing. `dynamic/mt_sweep.py` will load and re-evaluate any
checkpoint at a real sample size.

**Also: do not edit `dynamic/search3.py` while it runs**, not just the agent.
The pool is recreated every generation with the forkserver context, so newly
spawned workers re-import the main module and would pick up a mid-run edit.

---

## 29. Paired win rate beats paired margin as an evaluation metric (2026-08-20)

Measured head to head on variants of KNOWN effect size
(`dynamic/metric_test.py`, 40 seeds x 6 opponents x both seats, n=240 paired):

| variant | margin | t | win rate | t |
|---|---|---|---|---|
| exact null (identity) | +0 | **0.00** | 50.0% | **0.00** |
| late wheat off | -8,172 | -8.23 | 22.5% | **-8.52** |
| veto off | -4,931 | -4.79 | 32.7% | **-4.93** |
| alloc off | -5,620 | -5.60 | 26.7% | **-7.23** (+29%) |
| ENPV_LABOR=20 (known bad) | -4,154 | -2.73 | 37.1% | **-3.96** (+45%) |

The win rate is more sensitive on every real effect and still returns exactly
zero on the null. **The advantage grows with how noisy the margin is**, because
margin variance is carried by a few blow-out games while a win rate caps each
seed at +-1. Small-perturbation changes gain only 4%; noisy ones gain 29-45%.

**Genome-level comparisons are the noisiest case there is** (sd ~32,500 per
paired game against ~4,200 for a small additive change), so this is worth most
exactly where the GA operates. `dynamic/search3.py` now scores in percentage
points above 50.

**HANDOFF rule 1 still stands and is not violated by this.** Raw win rate is
invalid -- seat asymmetry gives a byte-identical mirror 15% at seat 0. What is
used here is a PAIRED win rate against a reference on the same seed, and a true
mirror scores margin exactly 0 on every seed, so it TIES rather than losing.
Ties are excluded from the rate (standard sign test) and reported, and the smoke
test confirms the reference against itself returns +0.0pp at 0-0.

## 30. Zero-drag cash: refuted three times, and the idle cash is not a defect

From day 12 the agent holds a mean of $22,900 idle, ends at $49,562, and leaves
FIFTY TILES LOCKED. The land guard is circular -- `wanted` needs a role in a
quadrant we have not bought, and no role is assigned to a quadrant we do not
own -- so the third quadrant is never purchased however much cash accumulates.

Three independent implementations of the zero-drag policy, all negative:

| version | fix attempted | result |
|---|---|---|
| v1 | as specified | -37,683 |
| v2 | price each new tile against the ones just added | -36,592 |
| v3 | gate on the DAY (d14 / d17 / d20) | -27,835 / -19,387 / **-18,143** |
| any | **land purchase disabled** | **+25 to +1,423 (t~0)** |

The separation variant is the whole story: **buying the quadrant is the
negative, not the extra tiles.** Three hypotheses tested and refuted along the
way -- it is not distance (the shed is central, all four quadrants average 4.00
and 12 workers serve all 75 tiles with 0 dropped), not endogenous pricing (fixed
in v2, no change), and not ramp timing (d20 still -18,143).

The mechanism, from a direct trace: the expansion WORKS mechanically -- live
tiles go 43 -> 69 -- and nothing dies unwatered (`consecutive_unwatered` stays
0). But both banks fall, ours 49,562 -> 32,129 and theirs 75,249 -> 58,743. The
new tiles are planted around day 20 and mostly cannot yield before the buzzer
(`yield_plan` gives melon 0 units from day 20), so they crash the shared price
level and consume crew turns while returning almost nothing.

**And the land cost is never charged.** `enpv.enpv_land` exists and was never
wired into the expansion: it buys a $2,000-4,000 quadrant to gain 25 tiles worth
about $112 each at day 20. That is the arithmetic, and it is negative.

**Conclusion: the $22,900 of idle cash is a correct valuation, not a defect.**
There is nothing left worth buying with it. Do not re-attempt land expansion
without first passing `enpv_land`.

### 30.1 The agent's OWN land purchase is ENPV-justified (a valid null)

`LAND_ENPV_VETO` prices the quadrant the agent already buys and declines it if
the tiles cannot repay the land. It measures **exactly +0 at every
`LAND_USABLE_FRAC`** — and this is a valid null, not the inert-parameter
symptom, which was checked rather than assumed:

```
enpv_land evaluated 708 times, negative 233 times
  day  quad   $/tile  tiles   ENPV_land
    0     0    1,274     15     +18,110
   14     1      594     15      +6,909
   29     1        0     15      -2,000
```

It is strongly positive at every moment the agent actually buys (day 0 and
day 14) and only negative at day 29, when no crop can yield before the buzzer
and the agent would not buy anyway. So the framework confirms the existing
behaviour: the first quadrant is worth +$18,110 and the second +$6,909.

That also cross-checks section 30 from the other side — land is worth buying
EARLY and not late, which is exactly why the zero-drag expansion (buying a third
quadrant around day 20) measured -18,143.

### 30.2 The GA finds no improvement over the hand-tuned reference

Four generations under the win-rate fitness, every generation's winner
re-confirmed on disjoint seeds:

| gen | in-generation | confirmed | W-L |
|---|---|---|---|
| 0 | +5.6pp | **-5.6pp** | 96-120 |
| 1 | +9.7pp | **-6.0pp** | 95-121 |
| 2 | +0.0pp | +0.0pp | 0-0 (the winner WAS the reference) |
| 3 | +11.1pp | **-11.9pp** | 82-133 |

`best` remains +0.0pp: **nothing has beaten the seeded reference.** Every
apparent winner is in-generation noise, and the confirmation pass catches each
one. Generation 2 is the cleanest evidence — the reference itself won its own
generation.

This is the same conclusion the margin-based run reached, now with a metric that
is 29-45% more sensitive and a confirmation gate that cannot bank noise. The
hand-tuned configuration this session produced is at a local optimum that random
mutation is not escaping.

---

## 31. The sell threshold: the largest confirmed effect of the session (2026-08-20)

`SHED_PANIC_FRACTION` governs the branch that offers **79% of all units we
sell** ("shed passed X% -> dump everything"). Moving it off the searched value
of 0.25 wins overwhelmingly on WIN RATE while leaving mean margin at zero.

Baseline `best_genome3.json`, three disjoint seed sets:

| value | margin | margin t | win rate | win rate t | W-L |
|---|---|---|---|---|---|
| 0.25 (baseline) | +0 | — | 50.0% | — | — |
| **0.35** | -45 | -0.24 | **88.6%** | **10.98** | 179-23 |
| **0.40** | +28 | 0.09 | **83.6%** | **12.11** | 271-53 |
| **0.45** | +182 | 0.57 | **77.6%** | **10.02** | 256-74 |
| 0.60 | +146 | 0.44 | 61.3% | 4.15 | 206-130 |
| 0.75 | -352 | -0.99 | 48.8% | -0.44 | 164-172 |
| 0.90 | -1,701 | -4.10 | 40.5% | -3.49 | 136-200 |

**Margin is zero throughout and win rate is t=10-12.** Under the project's
standard metric this effect is invisible; it exists only because the evaluation
moved to a paired win rate. Since `publicScore` is a skill rating driven by
match outcomes (section 7), win rate is the metric aligned with the objective.

**Consequence: every margin-scored sweep in this document may have missed
effects of this shape.** Re-scoring the important ones under win rate is worth
doing before trusting any of their nulls.

### A methodology failure that nearly buried it

The first confirmation run reported all four coordinate-descent candidates as
refuted, `SHED_PANIC=0.40` at t=-1.27. That run loaded `best_genome.json` as its
baseline while the run it was confirming had loaded `best_genome3.json`. Same
parameter values, two different references, so neither direction meant anything.
`dynamic/cd_confirm.py` now takes `BASE_CKPT` from the environment and PRINTS
it. **A confirmation must state which checkpoint it is confirming against.**

## 32. RL on the scheduler: interface built, identity control passes

The policy sits on top of the scheduler and answers four decisions rather than
emitting raw ops, which collapses the action space, keeps the model shippable
(1-5M params, not 200M), and preserves the scheduler as a fallback.

`dynamic/rl/encode.py` -- 10x10x21 spatial per farm + 86 scalars = 4,286 floats,
0.29 ms. Opponent holdings are an INTERVAL, not a point estimate: the tracker's
ledger gives the lower bound, floor-sale invisibility gives the upper, and the
100-item shed caps the vector. Width is fed in as an explicit confidence signal.

`dynamic/rl/policy_api.py` -- two cadences, because encoding is not free at 720
steps a game: a strategic head once a DAY on the full observation (30 calls),
and a sell head every turn on the market scalars only (86 floats, ~25x cheaper).

`dynamic/rl/agent_rl.py` -- agent4 with the four hooks. **With a ScriptedPolicy
it reproduces agent4 byte for byte on 4 seeds** (47,669 / 55,035 / 67,210 /
91,945). That identity is the control for the entire RL line.

Section 31 is the evidence that the sell head is where the value is: one
CONSTANT in that branch is worth 88.6% win rate. A state-dependent policy with
the price slope, the drain rate and the opponent belief interval in front of it
has strictly more to say there.

---

## 32. Tape distillation fails the same way action cloning did (2026-08-20)

Section 21 recorded behavioural cloning from the tape reaching 92.8% action
accuracy and banking $288, the failure being covariate shift. The obvious
response is to clone something lower-dimensional, and that was tried properly:
`dynamic/rl/distill.py` clones DECISION CONDITIONS at the scheduler's own
decision points -- which crop to plant, how many hands, whether to buy land,
which animal, what fraction of holdings to sell -- 30 decisions a day over 122
NAMED features, with our scheduler still executing every unit move.

The fit is good. Held out BY GAME, lift over the majority class:

| head | model | majority | lift |
|---|---|---|---|
| animal | 100.0% | 75.9% | **+24.1** |
| sell | 91.1% | 76.6% | **+14.5** |
| crop_pref | 89.7% | 79.3% | **+10.3** |
| buy_land | 99.1% | 93.1% | +6.0 |
| crew_delta | 100.0% | 96.6% | +3.4 |

**And it plays 46,972 worse than the scheduler it replaces** (t=-12.97, 14 wins
to 130 losses over 288 paired games).

The argument for why this would differ from section 21 -- low-dimensional,
condition-level, executed by our own scheduler so the learner cannot leave the
expert's trajectory -- is WRONG, and the reason is worth stating exactly. The
tape plants wheat on day 3 because ITS board has 23 producing tiles by then;
ours has 8. The rule learned is "plant wheat when our.WHEAT=0.4 and cash=0.1",
and our scheduler never visits that state. Cloning conditions instead of actions
lowers the dimension of the map but does nothing about the domain it is fitted
on:

    P_tape(x) != P_scheduler(x)  =>  argmax_a pi_tape(a|x) is meaningless on
                                     the x we actually visit

**Do not re-attempt tape initialisation** without first solving the
distribution mismatch, and note that DAgger cannot: a fixed 719-step action list
cannot be asked "what would you do with only 8 tiles".

### What this does NOT refute

The white-box linear policy itself is unaffected and is kept. Both heads are now
linear softmax over named features -- 2,337 + 3,922 = 6,259 coefficients against
the MLP's 2,524,600, 0.01 MB against 5.0 MB -- with the exact identity
initialisation preserved, numpy inference matching torch term for term, and
`explain()` / `rules()` printing the policy as text. The board is compressed to
36 named statistics (`encode.extract_board_features`), which was the only reason
the daily head could not be read.

The correct path is that architecture initialised at the SCHEDULER identity
(-71,384) rather than at the tape (-118,356), with PPO from there.

---

## 33. Five ways of asking "is it the decisions?" — all say no (2026-08-20)

A full day spent on the hypothesis that the scheduler picks the wrong actions.
Five independent attacks, five negatives, and together they locate the problem
somewhere else entirely.

### 1. Decision trees from the top of the ladder: -116,035, 0 wins in 24

`dynamic/tree/` extracts 1,479 day-rows from 193 replays covering the ELEVEN
strongest teams we hold games for (VanKoha 126k mean bank, 我的AI是GPT 119k,
ReCurSiON 118k, HKmgikao 117k, peikopon 116k, tetsuya 113k, mandgeee 112k,
Thomas Tschinkel 112k, Galaxantic 109k, カワシギ 109k, Eddy Despradel 105k), and
fits a hand-written depth-3 CART per decision head.

**The fit is genuinely good, and held out BY TEAM** -- rules from ten players
predicting the eleventh:

| head | leave-one-team-out | majority | lift |
|---|---|---|---|
| crop | 86.8% | 62.2% | **+24.6** |
| hire | 95.1% | 81.2% | **+13.9** |
| animal | 85.0% | 77.5% | +7.5 |
| land | 96.8% | 92.0% | +4.8 |

In play it is **-55,671 against the scheduler baseline** (t=-19.5) and **head to
head against every build we have submitted, -116,035 with 0 wins in 24**. Adding
the tree takes us from -65,896 to -116,035 against the shipped agent.

This was supposed to differ from section 32, and the argument was explicit: the
top ladder is ADAPTIVE (section 10 measured 37-65% self-agreement), so cloning
them clones a function, not a trajectory. **The leave-one-team-out result proves
the function generalises ACROSS THEM and it still does not transfer to us**,
which is the sharper form of the lesson:

    P_top(x) overlapping each other  does NOT imply  P_ours(x) in supp P_top

### 2. The distribution distance, measured

Profiling our own states against theirs on producing tiles, strawberry tiles,
readiness, cash and shed fill:

| | producing | strawberry | cash |
|---|---|---|---|
| **us** | **0.384** | **0.378** | **0.350** |
| nearest (peikopon) | 0.716 | 0.761 | 0.574 |
| furthest (HKmgikao) | 0.751 | 0.937 | 0.672 |

All eleven cluster together at distance 0.58-0.75 from us while sitting 0.17
apart from each other. **There is no in-distribution strong player on this
ladder, because being strong IS being big.** The tree's largest leaf (n=850,
95% pure) requires `our.STRAWBERRY > 0.700`; our mean is 0.378, so we never
reach the branch that carries the rule.

### 3. More data cannot fix it — the learning curve is flat

| rows | crop | hire | animal | land |
|---|---|---|---|---|
| 134 | 73.3% | 86.4% | 76.5% | 92.0% |
| 672 | 85.0% | 95.1% | 85.3% | 91.4% |
| 1,344 | 86.8% | 95.1% | 85.0% | 96.8% |

Saturated from 50% of the data onward: doubling it buys +1.8pp on crop and
nothing anywhere else, and the failure happens at 86.8%. **Do not download more
replays for this purpose.** Section 21 already said it -- more on-distribution
samples say nothing about off-distribution states -- and this is the measurement.

### 4. The shipped MARKET layer does not transfer either: +290 +- 3,900

The shipped build is tape PLUS market overlay, and every experiment before today
touched only the farming half. `pbt/intervene.py` is a pure wrapper -- it edits
market orders and never a tile -- so it bolts onto our scheduler unchanged
(`dynamic/tree/bake_overlay.py`). It is worth +1,611 on the tape.

On our scheduler it is **+290 on a standard error of 3,900**, against every
rival. The mechanism explains it: the overlay pushes stock into the book ahead
of the opponent's predicted sale, and it needs stock to push. Section 22
measured 79% of our units leaving through the shed-panic dump, so by the time
the overlay wants to act we are empty. **The market layer is an amplifier of the
tape's production, not a portable gain.**

### 5. The endgame is already optimal, and worth +-600 total

Rollout search on OUR OWN states, branching at day 22 and playing 12 terminal
policies to the buzzer, 768 rollouts (`dynamic/endgame.py`). Cheap where a
day-3 rollout is not: 0.1s from day 25 against 0.59s from day 3.

**Nothing beats the current setting.** The best two variants are +0; the whole
searchable range is ±600, which is 0.9% of the 67,928 deficit. `TERMINAL_STEP`
700-712 costs -299 (stock unsold), `SHED_PANIC_FRACTION` 0.70 costs -554
(hoarding hits the 100-item shed cap) -- two independent reproductions of
section 17's "holding stock for price is catastrophic".

And the premise that the endgame would be in-distribution is **backwards**: the
distance to the top ladder is 0.40 over days 6-11 and **1.33 over days 18-23**,
where they work ~74 producing tiles and we work ~40. The endgame is where we
differ MOST.

### What all five have in common

Not one is a decision-quality problem. Every road ends at the same place, now
measured from five directions plus the shadow price of section 34: **our farm is
half the size of theirs, and the difference is set in the first ten days.**

    day 12 producing tiles     us 37        the tape 68
    cash on hand, days 2-8     us $171-360  the tape $10,300 by day 12
    lambda(0-9)                2.00 +- 0.19 -- a dollar then is worth two later
    lambda(>=10)               1.00 +- 0.00 -- and after, worth exactly itself

**The only unrefuted direction with a quantified target is early capital.**

### 4b. The route table is now addressable — v3, 2026-08-21

Four derived builds off `submission/v3_base.py`, all verified equivalent. Three
are that file byte-for-byte plus one appended block; the fourth (`v3_expanded.py`)
appends nothing and only rewrites the blobs in place. **The flat array supersedes
the tree.**

| build | tool | bytes | block | lookup |
|---|---|---|---|---|
| `submission/v3_tree.py` | `pbt/treeify.py` → `treeroute.py` | 196,410 | 41,105 B base64 CART | ~13 compares + decode |
| **`submission/v3_flat.py`** | `pbt/flatify.py` → `flatroute.py` | 158,663 | **3,358 B** plain source | one index |
| `submission/v3_expanded.py` | `pbt/expand.py` | 1,463,844 | all 12 blobs as literals | unchanged |
| **`submission/v3_flat_expanded.py`** | both | 1,467,202 | flat array + no blobs at all | one index |

Ship `v3_flat.py`; read and edit `v3_flat_expanded.py`. All four are equivalent.

The CART was structure for its own sake: its leaves were already `(table, step)`
references, so nothing ever depended on the branch structure, and its only real
product was the substrate. A flat array is a strictly better one.

**The state space, written down.** A route decision is a function of exactly
three things and the tape always knew it:

```
legacy in {0,1}   _kawa_use_legacy_layout(obs)   per-seat latch, stateful
label  in {0..4}  _kawa_route_label(obs)         pure
step   in {0..718}
s1 = (legacy * 5 + label) * 719 + step            |s1| = 7,190
```

**Key space and reference space are the same integer space** — `s1` decomposes
as `table * 719 + step` because the table index *is* `legacy * 5 + label`. So
identity is `_FR_CODES[i] == i` and there are two edit primitives:
`_FR_REMAP[i] = j` (state i plays state j's action; one int, always legal) and
`_FR_EDITS[i] = act` (novel action). The 7,190 identity ints are NOT written out
— that costs 42,028 bytes of source to say nothing, more than the blob it
replaces — so the array is `list(range(7190))` plus sparse deviations, still a
real mutable list at runtime.

Both builds rebind `_kawa_actions` to return a proxy (`__len__` + `__getitem__`)
so ALL THREE readers resolve together — the base lookup, `_trace_actor_action`
(current step, weed replay) and `_future_sells` (step + 1, pre-empt borrow). An
edit is coherent everywhere by construction rather than by remembering to patch.

**No numpy in the agent, numpy in the tooling.** The lookup runs 2,160×/episode
where boxed numpy scalar indexing is *slower* than list indexing, and stdlib-only
imports are worth keeping in someone else's sandbox. Vectorised work lives in
`dynamic/tape/route_array.py` (`RouteArray.load/key/unkey/keys/action/
fingerprints/diff/measure_reach/patch`).

**No opponent axis, deliberately.** The opponent enters the eleven guards, not
the route. `(opp, legacy, label, step)` is a one-multiply change if ever
justified, but it multiplies parameters by |s2| against a fixed-size pool —
harder search before better agent. Condition in the guards, where it is free.

**Do not re-bake this one.** v3's market layer came from an older
`pbt/intervene.py` (no `_IV_STRUCT` / `_IV_MIN_PRICE` / `_IV_STAGED`), so
`route/bake.py` would silently swap it for today's. Both tools copy and append.

**All twelve blobs are now expandable** — `pbt/expand.py` rewrites every
`json.loads(zlib.decompress(base64.b85decode(...)))` as literal source, one row
per line with its step number: the ten route tables AND the two market tapes
`_V17_R5_MARKETS` (720 rows) / `_V17_MD_MARKETS` (719). Blobs are found by
**AST** — any module-level assign whose value contains a b85/b64 decode call —
not by name, because a regex on `_ACTIONS_` skips the market pair, which is the
half nobody had ever read. Values come from *executing the file*, so what is
written is what that file produced. Both market guards are live: over 20 pool
episodes `_v17_r5_counter` changed the action on 16 turns, `_v17_md_counter` on
140, so the gameplay runs do exercise them.

That gives a THIRD editing surface — edit `_ACTIONS_8C6S_3Q[30]` in place, in
readable source — alongside `_FR_REMAP` (re-point) and `_FR_EDITS` (novel
action). Reach for the in-place edit when you know what you want the step to do;
the dicts are for programmatic search.

**Expansion costs 8x cold import** — 0.047s → 0.387s, file 155 KB → 1.46 MB,
episode wall +7.6% under the real engine. Nothing is near a timeout, so this is
a preference: ship `v3_flat.py` (+0.1%), read and edit `v3_flat_expanded.py`.
**Warm `__pycache__` reports expansion as 73% FASTER and that number is a lie** —
the 1.5 MB parse caches to .pyc while the compact file's zlib decode reruns
every import. Kaggle writes the file and imports it, so the parse is paid.
`expand.py --check` measures in a fresh temp dir for exactly this reason.

Side-by-side copies and the full write-up live in `v3_compare/`, including
`market_tapes.py` — the two market tapes alone, expanded, for reading.

| check | tool | tree | flat | expanded | flat_expanded |
|---|---|---|---|---|---|
| route keys | — | 7,190/7,190 | 7,190/7,190 | — | 7,190/7,190 |
| blob values after expansion | `expand.py --check` | — | — | **12/12** | 12/12 |
| pool games, per-seed final banks | `dynamic/tape/v3_bench.py` | 120/120 | 72/72 | 72/72 | 72/72 |
| self-play `*_vs_base` paired margin | `v3_bench.py` | **+0**, 0/16 | **+0**, 0/12 | **+0**, 0/12 | **+0**, 0/12 |
| self-play `base_vs_base` (identity control, §21) | `v3_bench.py` | **+0**, 0/16 | **+0**, 0/12 | **+0**, 0/12 | **+0**, 0/12 |
| real engine, by file path (rule 3) | `v3_submit_check.py` | 30/30 | 30/30 | 30/30 | 30/30 |
| episode wall time | `v3_submit_check.py` | +0.3% | +0.1% | +7.6% | +7.4% |
| Kaggle entry point | `--check` | `_treeroute_entry` | `_flatroute_entry` | `_submission_entry` | `_flatroute_entry` |

`V3_LAYER=tree|flat|expanded|flat_expanded` selects the build on both harnesses.
`v3_submit_check.py` needs `~/kagg-env` — `kaggle_environments` is not in the
default interpreter, and it is a LOCAL check that never contacts Kaggle.

**Both edit surfaces were proven load-bearing by sabotage**, at reachable state
749 = `(0, '8c6s_3q', 30)`, seed 9000 vs `strong-barnyard-economist`: baseline
76,829 → `_FR_EDITS[749] = PASS` gives 55,293 → `_FR_REMAP[749] = key(0,'10c4s_3q',0)`
gives 77,557. A *first* remap attempt returned 76,829, unchanged, and that was
not dead code — `_ACTIONS_10C4S_3Q[30]` is byte-identical to `_ACTIONS_8C6S_3Q[30]`,
so it asked for nothing. §21 again: an identical row can mean **inert**, not
neutral. Check which before concluding.

**Reachability, measured with every read instrumented** (both flat readers plus
the weed replay and the step+1 peek), five-opponent pool × 3 seeds × both seats:

```
reachable 2,205 / 7,190 states (30.7%)
  legacy=0  10c4s_3q   647 states, steps  72..718
  legacy=0  8c6s_3q    719 states, steps   0..718   <- the workhorse
  legacy=1  10c4s_3q   647 states, steps  72..718
  legacy=1  8c6s_3q    192 states, steps  24..215
  never selected: 6c8s_3q, 6c12s_4q_first_yarn, 6c12s_4q_second_yarn (both legacies)
```

Six of the ten tables are never selected against this pool — 4,985 dead states.
Search the mask, not the space, and always report the mask size with the result:
"no improvement in 7,190 states" and "no improvement in 2,205 states" are
different claims. `RouteArray.measure_reach()` recomputes it for another pool.

Two drivers on purpose: `planner.simulate` is ours and fast, but only
`kaggle_environments` scores the competition. Status matters as much as the bank
— an agent that raises is marked INVALID and forfeits, and a forfeit still
produces a plausible-looking number.

**The load-bearing test is the one that matters.** Identical output also has an
innocent explanation — the block being dead code — which would make every row
above vacuous. Both edit surfaces were sabotaged at a reachable state
(`(0,'8c6s_3q',30)` = 749), seed 9000 vs strong-barnyard-economist:

```
flat                                   76,829
+ _FR_EDITS[749] = PASS                55,293
+ _FR_REMAP[749] = key(0,'10c4s',0)    77,557
```

The first remap attempt pointed at `10c4s_3q` step **30** and returned 76,829,
unchanged — and that was **not** dead code: `_ACTIONS_10C4S_3Q[30]` is
byte-identical to `_ACTIONS_8C6S_3Q[30]`, so it asked for nothing. §21 again: an
identical row can mean **inert**, not neutral. Check which before concluding.

Equivalence is a property of a BUILD, not of the generator. The tree template
briefly carried verification numbers in a comment and they were *kawa's*, in a
v3 file. Rerun both checks after regenerating.

**Reachability, measured** (every read instrumented incl. replay and step+1 peek,
5 opponents × 3 seeds × both seats) — supersedes the earlier 2,133/29.7% figure:

```
reachable 2,205 / 7,190 (30.7%)
  legacy=0 10c4s_3q   647 states, steps  72..718
  legacy=0 8c6s_3q    719 states, steps   0..718    <- the workhorse
  legacy=1 10c4s_3q   647 states, steps  72..718
  legacy=1 8c6s_3q    192 states, steps  24..215
  never selected: 6c8s_3q, 6c12s_4q_{first,second}_yarn, both legacies
```

**Six of the ten tables are never selected at all.** Search the mask, not the
space, and report the mask size with any result: "no improvement in 7,190
states" and "no improvement in 2,205 states" are different claims.

So section 4 is now narrower than it was. The *table* is editable — per state,
coherently at all three read sites. What section 4 measured and what still
stands is that edits are mostly CATASTROPHIC: single-step PASS at steps 0-20
costs -6k to -299k (`dynamic/tape/leaf_scan.py`). Steps > 100 are untested and
are the only place a soft state is likely. **Editability is a substrate, not a
gain — this ships at v3's score, to the dollar.**

Pool numbers for v3 itself, 100 games (**not** evidence about the tree):

| opponent | games | win | mean margin |
|---|---|---|---|
| strong-barnyard-economist | 20 | 100% | +14,119 |
| kaggriculture-3000-socre | 20 | 100% | +5,983 |
| kaggriculture-rank-your-agent | 20 | 80% | +7,768 |
| v111-8c4s-economic-core-premium-lead | 20 | 80% | +7,111 |
| kaggriculture-multi-route-farming-agent | 20 | 85% | +680 |
| **total (deduped)** | **100** | **89.0%** | **+7,132** |

`opponents/kaggriculture-ttv1.py` and `opponents/kaggriculture-3000-socre.py`
are BYTE-IDENTICAL (md5 `694c736a…`). Any round-robin listing both
double-weights that agent; the row above is deduped, the raw run said 90.8%.
**Check the pool for duplicates before reading a total.**

**`submission/v3_base.py` arrived truncated** and was repaired. Pasted through
the terminal, all ten table lines were cut at exactly 4,095 chars. The file
still looked complete — every `def` and every blob start is at column 0 and
survived — which is why a grep-level check passed it; that check was wrong. All
five other builds of this lineage carry those ten lines byte-identically and
each is a strict extension of the truncated prefix, so restoration was
unambiguous (verified: 719-step tables, both market blobs, `__version__`,
`dump=0.8 lead=3` with no `_IV_STRUCT`, `PMB=30 PMFQ=0`). Truncated original at
`submission/v3_base.py.truncated.bak`. **Check line lengths, not just symbol
presence, on any agent file that arrives by paste.**

---

## 36. What a route edit costs: the fidelity curve (2026-08-21)

Section 4b proved the edit surfaces are load-bearing by sabotage — one state set
to PASS moved a game 76,829 → 55,293. This is the same question asked as a
curve: blend the route table with a fitted decision tree at a controlled rate
`p` and sweep it (`dynamic/tape/fidelity.py`, 768 games, 3 opponents × 16 seeds
× both seats, paired).

| deviation | paired margin | win rate |
|---|---|---|
| **0%** | **+7,099** | 67% |
| **1%** | **−73,448** | 8% |
| 2% | −179,626 | 0% |
| 5% | −281,257 | 0% |
| 100% | −302,365 | 0% |

**About −80,000 per 1% of deviated unit-orders**, and by 5% it is already at 93%
of the loss from replacing the route entirely. The two measurements agree:
section 4b's single-state PASS is 1 of 2,205 reachable states, and it cost
−21,536 on one seed — steeper than this curve's average, which is what a
load-bearing state looks like.

**Use this as the budget for any edit.** A change that improves one state has to
beat roughly 80,000 × (deviated fraction) to break even, and `_FR_EDITS` at a
single reachable state is ~0.05% of the mask. That is why section 4b's remap
(+728) is a real result and why blanket rewrites are not.

### The corollary: a state-conditional tree cannot replace the route

Asked directly, and worth recording so it is not re-attempted. A depth-9 CART
over 30 named per-unit features (position, tile state, neighbourhood, day, cash,
crew, opponent aggregates — no step index), trained on 82,968 unit-turns from
the tape, held out by game:

    stage 1, op        61.6%      stage 2, movement direction   49.3%

Dropped into the pipeline in place of the route, guards intact:
**−305,485 paired, 0 wins in 144.** Adding the market overlay changed nothing
(identical to the digit) because the agent never accumulated stock to sell.

The ceilings behind that, all measured:

| representation | reproduction |
|---|---|
| `(label, step, unit)` — the route's OWN index | 83.1% |
| ...plus weed count | 91.5% |
| state-conditional, no step | 61.6% / 49.3% |

Even keyed on the route's own index the ceiling is 83.1%, because
`_weed_repair_action` carries cross-turn state and `_align_hands` depends on
where hands spawned — neither is in the observation. And 83.1% fidelity sits far
below −281,257 on the curve above. **The route is not a function of the
observable state, so no state-conditional representation is equivalent to it.**
`step` is the only feature that makes a tree equivalent, and a tree keyed on
`step` is the flat array of section 4b with extra nodes.

### The eleven guards are now separable — `dynamic/tape/pipeline.py`

The route is one of twelve things the agent does. The other eleven are reactive
guards applied in a fixed order (kawa source 990–1002), three of them stateful.
`Pipeline` exposes them as named, individually switchable stages delegating to
the original functions, so fidelity is by construction rather than by
transcription:

```python
p = Pipeline()                       # verified 12,942/12,942 fields = 100.00%
p.disable("r5_counter")              # drop one guard, measure the cost
p.replace("preempt_shift", ours)     # swap in market_model logic
```

Measured on one game: the guards leave the farmer order untouched 100% of the
time, hands 99.9%, market 96.8% — **96.7% of turns are the route verbatim.**
Order is load-bearing (feed guard before room evacuation; terminal liquidation
last), and each stateful guard keeps seat-keyed module state, so `_fresh_kawa()`
gives every Pipeline its own module copy and `reset()` clears it between
episodes.

**This is the editable surface that is not the route.** `r5_counter` and
`md_counter` are opponent-specific counters and have never been costed; that
measurement is not done.

## 37. Files handed over from the desktop — `incoming/` (2026-08-21)

Uploaded, not yet graded. Nothing is imported by any agent.

```
incoming/8.21kaggriculture.py                    1,442 KB
incoming/submission8.18.v3 (1).py                  153 KB   possibly 55600561
incoming/kaggriculture-precomputed-schedule-policy.ipynb  1,772 KB
incoming/kaggriculture-conomic-cut.md                4 KB
incoming/终局卖出策略.md                            12 KB
incoming/终局雇佣和移动规划.txt                       0 KB   <- transfer failed, re-send
incoming/参考代码/                                        13 public notebooks
```

**Grade before promoting to `opponents/`.** Section 33 graded 117 agents already
on disk and found exactly two in the band we win 20–80% of; an ungraded file
silently changes the pool every result is measured against.

`submission8.18.v3 (1).py` — **graded 2026-08-23, and it did not resolve the
contradiction.** Against `submission/main.py` it is **+26,517 self-play** over 24
paired seeds (18-6) and **-2,051 a seed against the standard pool** (t -3.94,
n=144), with the real engine agreeing in sign at -445 a seed. So it beats us head
to head and loses harder to everyone else. If this is 55600561 then its 2630.9
was not earned by being a better agent against the field, and the next question
is what the ladder's opponent distribution looks like, not what the file does.
Its twelve blobs are byte-identical to `submission/v3_base.py`, so whatever
differs lives in the code around the tape, not in the tape.

It is also the file that was expanded: `incoming/submission8.18.v3_expanded.py`
(1,463,841 bytes, 12/12 blobs verified identical, 12/12 real-engine episodes
DONE/DONE and bank-identical to the compact original).

Two of the endgame notes overlap a measurement already on file: twelve terminal
policies were swept by rollout and the entire searchable range was ±600, with
`SHED_PANIC_FRACTION=0.70` costing −554. If the notes propose something outside
that range, that is the experiment worth running.

## 38. The endgame is closed (2026-08-23)

A complete endgame proposal was handed over: a deadline table, WHCA\* hand
routing under a three-quadrant assumption, an optimal liquidation model, a
front-running protocol, and a quantified wheat squeeze. Every claim was checked
against the engine source and against live games **before** anything was built.
Three claims were right, three were wrong, and the buildable remainder is worth
**+2 a seed**.

### Graded against the engine source

| claim | verdict |
|---|---|
| the deadline table | **RIGHT, one step tight.** Derived: `_daily_refresh_plants` produces when `next_day - planted_day - first_yield_day >= 0`, the last actionable step is 718, so the deadline is `(30 - first_yield_day) * 24 - 1`. WHEAT/CARROT **671**, TOMATO/COW 527, STRAWBERRY/MELON **479**, SHEEP 575, GOOSE 623. The note says 670/526/478 — conservative by one on the crops, exact on the animals. |
| base prices; `BUY_PRODUCT` only WHEAT and FERTILIZER; $1 sales add no supply | **RIGHT**, all three verified in `MARKET_PARAMS` and `_commit_unit`. |
| the front-run mechanism | **RIGHT.** MILK's `above_target` is 1.60 over `T=122`, so ~100 units of glut takes it from $160 to the $1 floor, and pool opponents sell **74-119** premium units at step >= 670. It is a real zero-sum race. |
| animals can be liquidated for residual value | **WRONG.** `_process_market` quotes `SELL` only for `item in PRODUCTS`, and PRODUCTS has no GOOSE/COW/SHEEP. |
| the wheat squeeze | **WRONG in this window.** It needs the opponent to still need feed. Measured, 3 seeds x 6 pool opponents: they buy **189-522** wheat across a game and **0-7** of it at step >= 670. |
| terminal liquidation needs building | **WRONG, it is already perfect.** 9 games, 3 opponents: the shed holds `{}` at step 719 every time. `_terminal_liquidation` leaves $0 behind. |

### Four engine facts that were not written down before

- **Animals are not sellable at all.** An animal in the shed is worth exactly $0.
  "PICKUP the animal, then SELL it" spends hand actions for nothing and costs the
  HARVESTs it displaces. The tape is right to leave 10 COW and 4 SHEEP standing.
- **Goods sit in hand inventories until a `DROP`.** This is rule 5 in section 0
  and it is the reason a market-only endgame layer cannot fire.
- **`maxMarketOrdersPerTurn` is 10 and `shedCapacity` is 100** — total, not per
  item, and `BUY_PRODUCT` checks it. No market position can exceed ~100 units, so
  the squeeze's own worked example (200-400 wheat) is unreachable.
- **Wheat's ceiling is $125, not $45.** $45 is the price after removing exactly
  `T=400` units; the curve keeps climbing to $125 at zero inventory. Any model
  that hard-caps at 45 mis-sizes both sides of the trade.

### Measured, all four modules, vs `incoming/submission8.18.v3_expanded.py`

`arena.py`, 24 seeds x 6 standard-pool opponents x both seats, n=144 paired. The
all-flags-off build is the layer's own identity control and returned +0 on 144.

| module | fires | result |
|---|---|---|
| deadline mask | **0%** | inert — the tape never crosses a deadline. It buys WHEAT seed at 670 and 671 and stops, which is the derived value exactly. |
| front-run, market-only | **0%** | cannot fire; the stock is in hand inventories. Rule 5. |
| **wheat squeeze** | 100% | **-3,068 a seed, t -25.49, 0 wins in 144.** Self-play -68,189. |
| front-run + early `DROP` | 6% | **+32 conditional, 9-0.** |

Only the last one is positive, and it is positive because it stops being a market
edit: it makes a hand that is **already standing on a shed-access tile** DROP
early so the sale can happen at all. Nobody is moved and no scheduled work is
displaced beyond that one action. Real-engine gate, 40 sim seeds and 20 real
seeds on the hard pool:

```
sim   +1/seed  t 2.36   fired 5%   conditional +27  6-0
real  +2/seed  t 1.89   fired 7%   conditional +28  4-0     engines agree in sign
```

10 firing games across both engines, 0 losses — the direction is not in doubt.
The magnitude is: **+28 per firing game on a $70k-130k board**, and `arena.py`
calls it NEUTRAL. `submission/v4_endgame.py` is that build; it is not worth a
submission on its own.

### What this closes, and what it does not

**Closed.** The endgame liquidation window is exhausted for the same reason the
market layer was (section 17): the tape already does the profitable thing. The
white paper's Module 3 and Module 4 are descriptions of shipped behaviour. Do not
rebuild them.

**Not attempted, and here is why.** The proposal's decision tree over
`(S_me, S_opp)` is section 36's refutation restated — a depth-9 CART over 30
named state features scores **-305,485 paired, 0 wins in 144**, and the ceiling
keyed on the route's OWN index is 83.1% because `_weed_repair_action` carries
cross-turn state and `_align_hands` depends on where hands spawned. The route is
not a function of the observable state. WHCA\* hand routing in the last 50 steps
is a ~7% route deviation against section 36's -80,000-per-1% budget, and the
measurement above shows there is nothing to buy with it: the shed is already
empty at 719.

**Still open.** The squeeze premise is false *in the endgame window* — but
opponents do buy 189-522 wheat across a full game, so the arbitrage exists
somewhere earlier. `_IV_SQUEEZE` in the shipped intervention layer is ungated by
step and holds the position for hundreds of turns against a 100-item shed; a
step-windowed version aimed at where the demand actually is has never been
measured. Section 22's suppression math is the place to start.

### Endgame route takeover: the last EIGHT steps are worth taking (2026-08-23)

Section 38 closed the endgame as a MARKET problem. It is not closed as a ROUTE
problem. Replacing the tape's hands and farmer with a liquidation planner for
the final N steps, `pbt/endgame.py --takeover N`, against `v4_endgame`:

| N | sim delta/seed | sim win | real delta/seed | real win |
|---|---|---|---|---|
| 4 | +0 | inert | — | — |
| 6 | +5 | 69.8% | — | — |
| **8** | **+281** (t 13.68) | **85.8%** (206-34) | **+302** (t 9.36) | **90.3%** (65-7) |
| **10** | **+336** (t 9.63) | 75.8% (182-58) | **+338** (t 6.71) | 80.6% (58-14) |
| 12 | -70 | 35.0% | — | — |
| 15 | -263 | 28.5% | — | — |
| 20 | -3,789 | 0.0% | — | — |
| 25 | -6,345 | 0.0% | — | — |
| 50 | -13,601 | 0.0% | — | — |

n=240 paired at N=8/10, both engines agreeing in sign. **Ship `--takeover 8`**
(`submission/v4_endgame_tk8.py`): highest win rate on both engines, and section
29 prefers the win rate. N=10 carries a bigger mean if margin is what is wanted.

**The cliff between 10 and 12 is the whole result.** Inside ~10 steps nothing
planted can still grow, so every remaining turn is worth exactly what it
converts into shed stock, and a dedicated collect-deliver planner beats the
tape's generic route. Past ~12 the window starts eating real production the tape
was still doing -- harvests, watering, feeding -- and section 36's fidelity cost
takes over. This is the first route edit in this project that is worth anything,
and it works precisely because the objective genuinely changes there.

### The transition model was wrong: HARVEST collects animals, PICKUP does not

Found by checking the DP's transitions against `_apply_unit_action` line by
line, after the exact solver lost to the greedy one and that was taken as
evidence of a model defect rather than of a bad idea. It was:

**`HARVEST` handles BOTH crops and animals. `PICKUP` is a shed WITHDRAWAL** --
it returns immediately unless the unit is shed-adjacent, and it pulls from
`private["shed"]`. Both takeover planners emitted `["PICKUP", product, n]` at
animal tiles, so every animal collection in the window was a **silent no-op**:
the unit walked to the cow, issued an order that did nothing, and walked home
empty. Fixing it is worth +22 to +42 a seed on the greedy arms.

Final, both engines, vs `v4_endgame`, n=240 sim / 72 real:

| build | sim delta | sim win | real delta | real win |
|---|---|---|---|---|
| `v5_tk8` | +303 (t 13.48) | **85.8%** | +302 (t 9.36) | **90.3%** (65-7) |
| `v5_tk10` | **+378** (t 10.21) | 78.3% | **+338** (t 6.71) | 80.6% (58-14) |

**Ship `submission/v5_tk8.py`** on win rate (section 29), or `v5_tk10.py` if
margin is the target. Both are real, both engines agree.

### The exact solver still loses, and the remaining gap is unmodelled ENGINE RULES

`--exact 1` (subset DP, `dp[mask][last]` = fewest turns to collect `mask` ending
at `last`, valued on the real marginal price curve, O(2^K K^2) at K=12) scores
**-1,332 a seed against the greedy planner**. The HARVEST fix moved it by ~0, so
that was not the cause.

Measured against v111, the loss is **our own revenue, not opponent denial**:
-1,747 to our bank against +117 to theirs. And in the last 10 steps the exact
arm issues **69.8 DROP operations against the greedy arm's 7.2, while selling 40
units against 60**. It is dumping over and over and banking less.

The DP is exact for a model that is still missing at least three engine rules,
all of them in the DROP/shed path and all of them exactly modellable:

- **`shedCapacity` is 100 items TOTAL** and the DP has no capacity constraint,
  so it plans collections that cannot fit.
- **DROP DESTROYS THE OVERFLOW.** `_apply_unit_action`'s DROP branch computes
  `take = min(n, room)` and then `del inv[item]` UNCONDITIONALLY -- what does not
  fit is gone, not left in hand. A planner that ignores capacity therefore does
  not merely waste a turn, it deletes the cargo.
- **Sale timing and the 10-order cap.** Goods only become money if a SELL slot
  is available the same turn or later, and `maxMarketOrdersPerTurn` is 10.

So the correct conclusion is not "DP loses to greedy". It is that **this DP
encodes a collection problem the engine does not have**, and the greedy planner
accidentally respects the capacity rule because it shuttles one tile at a time.
Adding capacity to the state -- `dp[mask][last][room]`, or simply pruning masks
whose total exceeds current shed room -- is the next thing to try, and it is the
first version of this that would deserve the word exact.

**A standing caveat on "DP is optimal".** It is optimal for the model it
encodes. This is a two-player zero-sum game and **the opponent's shed is not in
the observation** -- only their public tiles, money and hands are. Their
liquidation schedule is therefore estimable (section 38's
`T = 719 - (ceil(A/W) + 1)` is built from public state) but never exactly
known, so no single-agent DP over our own state can be optimal against an
arbitrary opponent. Model everything that IS observable; the rest is estimation.

### The layered endgame engine: implemented as specified, worse at every window

The 50-step takeover was re-attempted properly. The first version was a
collector only -- it never fed, watered or cared -- so it deleted the 52
HARVESTs, 50 WATERs and 9 FEEDs the tape still runs across steps 670-718. The
rewrite implements the white paper's section III as written:

- `R > R_clear`: FEED anything whose remaining production beats one wheat, CARE
  it, WATER anything still harvestable, HARVEST what is ready, deliver.
- `R <= R_clear` with `R_clear = ceil(A_me / W_me) + 1`: husbandry stops, every
  unit collects and delivers.
- Values are marginal revenue at current market depth, so FEED/HARVEST/WATER
  compare directly. `_eg_future_events` counts remaining yields against the
  engine's own refresh rule rather than approximating.

| window | layered planner | collector-only |
|---|---|---|
| 50 | **-4,760** (1.4%) | -7,868 (0.0%) |
| 25 | -3,609 (0.0%) | -6,345 (0.0%) |
| 12 | -2,514 (2.1%) | -70 (35.0%) |
| **8** | **-1,655** (9.0%) | **+314 (85.4%)** |

The layered version beats the collector at 50 and 25 -- husbandry really is
worth something there -- but it is worse at 8 and 12, and **nothing beats the
8-step collector**. Adding our own husbandry scoring on top of the tape's
schedule is a net loss at every window we can measure.

**Why, and it is section 36 again.** The only thing this project's planners do
better than the tape is the terminal collect-and-deliver, and that is worth
something only in the last handful of steps where nothing planted can still
grow. Everywhere else the tape's husbandry is already better than a hand-scored
substitute, so every extra step of takeover buys a worse decision. The window is
not a parameter to push; it is the width of the region where the objective has
genuinely changed.

**Shipping stays `submission/v5_tk8.py`** -- collector-only, 8 steps, sim +303 /
real +302, real win rate 90.3% (65-7), both engines agreeing in sign.


## 39. Market structure decides the portfolio, and it kills price suppression (2026-08-24)

`whitebox/market_model.py` computes three quantities from the engine at import
and nothing in the planting or selling rules is hand-chosen any more.

**Shop coverage, confirmed against `SHOPS`** (a public write-up claimed this and
it is right): MILK is stocked by 3 shops, WOOL by 1, MELON by **none**. But a
single-product shop consumes DOUBLE, so YARN_STORE alone drains 12.4 WOOL a day.

| item | shops | town/day | halves at | floor at | recovery | front-run loss | policy |
|---|---|---|---|---|---|---|---|
| MELON | 0 | 1.0 | 112 | 158 | never | -30% | timed |
| WOOL | 1 | 12.4 | 42 | 59 | 3.4 d | **-99%** | spread |
| MILK | 3 | 20.5 | 38 | 76 | 1.9 d | **-94%** | spread |
| STRAWBERRY | 4 | 26.4 | 31 | 62 | 1.2 d | -98% | spread |
| EGG | 2 | 13.9 | never | never | never | -5% | free |
| WHEAT | 5 | 32.8 | never | never | never | -6% | free |

**Crash depth is set by `T`, not by `above_target`.** MELON has the harshest
`above_target` in the game at 3.60 and is the most crash-RESISTANT premium
product, because T=300 against WOOL's 105. A widely quoted formula that puts I0
where the engine puts T gives MILK a 260-unit crash point; the real one is 76.

### Diversification is the higher-revenue allocation, not a hedge

60 units of output, opponent holding the same basket and front-running:

| allocation | alone | front-run | loss |
|---|---|---|---|
| all MILK | $5,886 | $339 | -94% |
| all WOOL | $7,929 | $60 | -99% |
| **diversified** | **$9,228** | **$8,179** | **-11%** |

The basket wins with NO opponent present, because marginal price falls steeply
within a product and not at all across products. `market_model.crop_mix()` is
now the strategy's target: fill each product to the larger of its trickle
ceiling (town/day x 22 selling days) and its one-shot ceiling (units before the
price halves), in descending base price.

### Price suppression against the opponent is physically impossible

The idea -- trickle WOOL/MILK to hold the price under their break-even -- fails
on the town's clock, which the shop-count argument omits:

| item | town drains/day | our output/day at the winners' herd | verdict |
|---|---|---|---|
| WOOL | 12.4 | 4 SHEEP x 0.67 = **2.7** | town eats 4.6x what we make |
| MILK | 20.5 | 8 COW x 1.00 = **8.0** | town eats 2.6x what we make |

Sustaining even a FLAT price -- before any glut -- would need **19 SHEEP or
20 COW**, against the 4 and 8 the strongest replay seats actually run, and those
animals would displace the crop tiles that pay for them. **WOOL is the worst
suppression target, not the best**, precisely because its one shop is a
single-product shop drawing double.

What survives: trickling is the right SELLING rule for our own sake. Selling 3
MILK realises 99% of base and 3 WOOL realises 100%, where dumping 40 realises
74% and 85%. It protects our price; it does not touch theirs.

**The only place suppression works is the last 8 steps**, because MILK needs 1.9
days to recover and WOOL 3.4, and neither fits in the turns that remain. That is
exactly what `submission/v5_tk8.py` exploits.

## 40. The fixed-opening curve: the white-box mid-game is negative everywhere

`whitebox/mine_full_opening.py` extracts the complete action -- farmer, hands
AND market. Mining only the market line was a real defect: the farm bought two
cows, two sheep and nineteen seeds with nobody to work them and banked $20.

**How long is the opening?** Distinct sequences among the top 40 seats: 9 at 100
steps (modal **18/40**), 23 at 150 (8/40), 37 at 300 (2/40). Consensus collapses
past ~100 steps, so 100 is the real opening.

**But longer is monotonically better**, with the source episode held FIXED so
only length varies:

| fixed opening | 100 | 200 | 300 | 400 | 500 | 600 | 670 |
|---|---|---|---|---|---|---|---|
| mean bank | 8,666 | 11,191 | 18,891 | 21,869 | 45,015 | 74,614 | **86,010** |

Strictly monotone. **Every step handed back to the white-box mid-game costs
money**, and at 670 the number reaches the shipped tape because at 670 it IS a
tape. The phased architecture, optimised honestly, converges on the thing it was
built to replace.

**Use this curve as the bar.** A mid-game worth having must beat the replay it
displaces at the same step count. None of the current one does: against the
standard pool the phased white-box wins **0.0% of 96 games** at -229,971 a seed.

Three real bugs were fixed getting there, all worth knowing:
- `schedule.cash_floor` is what WINNERS HELD ($13,112 by day 13), and using it
  as a spending floor on a farm holding $70 makes every purchase impossible
  forever. The floor must be sized from our own obligations.
- `whitebox/tasks.py` collected animals with `PICKUP` -- the same no-op fixed in
  the endgame layer, never fixed here. The shed held nothing but bought WHEAT
  for the whole game. Fixing it took step-400 state from 1 animal / 0 crops to
  15 animals / 52 crops.
- The opening must carry hands, not just market orders.

## 41. `kaggle/strategy_tree.pkl` -- read, not adopted

zlib-compressed sklearn tree; `kaggle/tree_rules.py` is its exported if-else.
Its 840 features are one-hots over `[my_t-10, opp_t-10, ... my_t-1, opp_t-1]`:
**action history only, no board state**. It is section 36's refuted design with
strictly less information (that one had 30 named state features and scored
-305,485, 0 wins in 144), it is section 32's behaviour-cloning failure mode
($288 against $89k at 92.8% action accuracy), and its leaves emit fixed-length
`hands` lists unrelated to the crew actually hired. For the opening -- the use
proposed for it -- mining the replays directly is strictly better: same source,
no lossy intermediary, and it yields the 18/40 consensus that locates where the
opening ends.

## 42. DUSK — the endgame policy, named, shipped and measured (2026-08-24)

**DUSK is the name of the last-50-step policy from now on.** Built by
`pbt/endgame.py`, shipped as **`submission/dusk.py`** (195,661 bytes, compact
tape, entry `_endgame_entry`).

| steps | what DUSK does |
|---|---|
| 670-710 | **market only.** Deadline masking plus policy-sized selling. The route is NOT touched. |
| `T_opp-1` | **front-run.** `T = 719 - (ceil(A_opp / W_opp) + 1)`, from public state, into order slot 0. |
| 711-718 | **route takeover, 8 steps, collector only.** carry -> shed -> DROP, HARVEST what is reachable and bankable. |
| 716-718 | terminal liquidation. |

Deliberately absent, each refuted with a number: the wheat squeeze (-3,068, 0
wins in 144), selling animals (impossible -- `SELL` quotes only `item in
PRODUCTS`), sustained price suppression (would need 19 SHEEP or 20 COW just to
match the town's drain, section 39), and the exact subset DP (ties the collector
on win rate and loses the head-to-head 42.9%).

### Measured, on the v3 tape

Against the unmodified v3 tape, real engine unless stated:

```
identity control base_vs_base    +0        (12/12 and 32/32)
candidate mirror cand_vs_cand    +0        (32/32)
HEAD TO HEAD vs the tape     +6,668 / 12 seeds   12-0-0    (real)
                            +17,361 / 32 seeds   32-0-0    (sim)
POOL, real, n=144            WIN 85.4%   wt 8.50   margin +316
POOL, sim,  n=192            WIN 82.3%   wt 8.95   margin +295
```

Per opponent on the real engine: kawa **100.0%**, strong-barnyard 95.8%,
3000-socre 91.7%, frontier / v111 / rank-your-agent 75.0% each. It beats the
tape it is built on in **every paired seed of both engines**.

### DUSK IS NOT PORTABLE BETWEEN TAPES

Applied to a different tape it is a **regression: 2.1% win rate, -2,899 a seed**
(`submission/apex_dusk.py` on `submission/apex_tape.py`, n=144). DUSK works on
v3 because v3 spends its last eight steps walking hands that are still carrying;
another tape ends differently and the takeover destroys rather than completes
it. This is section 4 again -- a tape's parameters only work with its own
720-step continuation. **Re-measure DUSK on every new base. Never assume it
transfers.**

### Replay bank is NOT playing strength

`submission/apex_tape.py` is the highest-banking seat of all 386 in `replays/`
(episode-92777801 seat 1, **166,656**). Replayed against kawa it banks
**41,065**, against the v3 tape's 87,519 on the same seed.

A replay tape's recorded bank was earned against **the opponent it actually
faced**; the market path, and therefore every price it realised, was a joint
product of both seats. Ranking candidate tapes by their replay bank picks the
agent that met the weakest opponent, not the strongest agent. Rank by paired
play in `arena.py` or not at all.

### A build hazard that cost an hour, and would have shipped the wrong agent

`v5_tk8` was built from `pbt/endgame.py` when `_eg_takeover_units` was the
collector. That function was later REPLACED IN PLACE by the layered husbandry
planner, which measures -1,655 at the same window. Rebuilding from the same
command afterwards therefore produced a **different policy under the same
flags**, and it was caught only because the compact and expanded builds failed a
bank-identity check (0/6).

The collector is now `_eg_takeover_collect` and is the DEFAULT; the layered
planner is `--layered 1` and must be asked for. `submission/dusk.py` is verified
**6/6 bank-identical to `v5_tk8`**.

Generalise it: **a builder that is edited between experiments is a silent
version skew**. Same flags, same source, different agent. Always re-verify a
rebuild against the artifact it is supposed to reproduce.

## 43. Exact-DP mid-game path planning — three attempts, three distinct bugs, none shipped (2026-08-24)

Directive: mid-game task assignment must be exact, never greedy. Three
increasingly-informed attempts, each fixing the previous one's diagnosed
defect, and each still net negative. `WB_EXACT_TOUR` defaults to **0** (the
proven `route/router.py` greedy path) until this is resolved -- flipping it to
1 currently reproduces a bank-collapsing bug.

**Attempt 1 — sequential per-unit Orienteering DP.** `dp[mask][last]`, same
algorithm validated for the endgame (`pbt/endgame.py::_eg_solve_unit`), run
unit-by-unit (farmer first) each claiming its exact-best subset from whatever
remained. **-5.8%** (56,653 -> 53,386). Cause: the farmer, solved first, took
the locally-best candidates and every later hand inherited a steadily worse
pool -- an order-dependent artefact, the same class of bug exactness is
supposed to remove.

**Attempt 2 — partition first, exact tour within each partition.**
`route/router.py::partition` (angular sweep, simultaneous for all units,
unbiased by processing order) kept unchanged for the cross-unit split; the
per-unit tour construction (NN + 2-opt + greedy-drop) replaced with the exact
DP. Fixed the ordering bias (K=8 and K=12 gave IDENTICAL results, confirming
no truncation was biting) but still **-5.3%** (58,343 -> 55,264). The
survival-neglect hypothesis was checked and REFUTED by direct measurement: fed
rate 97% vs 96%, watered rate 92% vs 91%, both engines almost identical.
Root cause not fully diagnosed before the next attempt superseded it.

**Attempt 3 — round trips as an independent-item knapsack** (user's
structural insight: every task fundamentally returns to the shed to drop or
fetch, so trips share no travel and the problem is a 0/1 knapsack,
`O(N x budget)`, not a tour, `O(2^K x K^2)` — removes K-truncation entirely).
Correct for the six SHED-DEPENDENT ops (FEED, FERTILIZE, HARVEST, PICKUP,
PLACE, COLLECT_FERTILIZER) but applied to ALL ops including the four
SHED-FREE ones (WATER, CARE, DIG, PLANT), which do not need a shed round trip
and can be chained. Costing them at 2x their real travel collapsed watered
rate from 92% to 63%, weeds went to 37, and margin fell **-35.2%**
(57,270 -> 37,125).

**Attempt 3b — split by shed-dependency, per the same user directive.**
`_is_shed_dependent(task)` (true if `carry` is non-empty or any op is in the
six shed ops) routes each task to the right solver: knapsack for dependent,
the Orienteering DP for free. A first version then re-solved the UNION of both
solvers' picks through one more tour DP for ordering, with every item's value
set to 1.0 so it would only decide order, not selection -- but with value
information erased, "best" collapsed to "most stops visited," and the DP
correctly-per-that-objective dropped FEED tasks to fit more WATER stops.
**Bank $14.** Removed; the two solvers' outputs are now simply concatenated
(dependent stops, then free stops) rather than re-ordered as one tour.

**Attempt 3b still fails, differently: an infinite movement oscillation.**
Traced per-turn: the farmer alternates NORTH/SOUTH between (2,4) and (2,3) for
20+ consecutive turns starting mid-mid-game (~step 124), `tasks._PLAN`'s
cached route for that unit reads `None` for the whole oscillating window then
suddenly populates at step 144. Final bank $14-15. NOT ROOT-CAUSED before this
session's time ran out -- the next place to look is whether `free_start`
(`nearest_shed_tile(pos)` when any dependent trip was taken) disagrees with
where `next_op` actually re-derives the unit's position from turn to turn, or
whether the concatenated dependent+free route contains a position `next_op`
cannot make progress toward from where the unit actually ends up after the
dependent leg.

**Net status.** The user's round-trip / shed-dependency framing is correct and
should be kept as the target design -- attempt 2's tour-DP-only approach
plateaued at -5%, and the knapsack reformation for the dependent half is a
real structural improvement (O(N·budget), no K-truncation, provably exact for
what it covers). What remains broken is specifically the SEAM between the two
solvers' outputs. `WB_EXACT_TOUR=0` (greedy, proven, ~60,000 on the standard
smoke test) is the shipped default; `WB_EXACT_TOUR=1` is left in the code,
switched off, for whoever picks this back up.

## 44. NOON — the mid-game strategy, named (2026-08-24)

**NOON is the name of the mid-game (steps 123-670) strategy from now on**, the
counterpart to DUSK (section 42, steps 670-718) and the fixed opening (steps
0-122, section 42's Ryo-derived sequence). The day-cycle naming is deliberate:
opening = dawn, NOON = the full working day, DUSK = the wind-down.

Lives in `whitebox/`, driven by `whitebox/agent.py`. Composes:

| component | what it does |
|---|---|
| `state.py` | `obs` -> immutable `Snapshot` + `OpponentTracker` (holdings inference) |
| `strategy.py` | day-by-day targets from `ryo_targets.py`, cash-floor/animal-budget by day |
| `tasks.py` | `enumerate_tasks` (what needs doing) + `assign` (greedy, `route/router.py`) |
| `hiring.py` | how many hands, against a MEASURED operation-capacity ceiling |
| `market.py` | sell policy (`market_model.py`) + front-run trigger (`opponent_model.py`) |
| `opponent_model.py` | `earliest_available(farm, item, day)` -- the only opponent signal used |
| `market_model.py` | per-product crash depth, town absorption, sell policy, portfolio ceilings |
| `paths.py` | plain Manhattan; no path search needed (LOCKED passable, no collisions) |

### Path planning stays greedy, by measurement, not by default

Section 43 records three attempts to make path planning exact (Orienteering
DP, then a knapsack reformation, then a shed-dependency split) -- each fixed a
real bug in the one before it, and the third is currently broken (an
unresolved movement oscillation, bank collapsing to $14-15). `WB_EXACT_TOUR`
defaults to **0**: `route/router.py`'s proven angular-sweep partition plus
nearest-neighbour-plus-2-opt tour construction. NOON's task LAYER is exact
where it matters (the value/priority decisions); the WALKING layer is not, and
that is now a settled, measured choice rather than an open question.

### The 547-step budget, measured

With path planning fixed as greedy, the only remaining decision surface is the
TASK layer -- what to do, including hiring. Measured directly (our own agent,
4 seeds, steps 123-669, 24,325 unit-turns):

```
movement   56%
operations 44%
```

This is what "the executable space, net of movement" concretely is: of
roughly 6,017 unit-turns available per unit across the 547-step mid-game, only
~44% converts to an actual FEED/WATER/HARVEST/CARE/etc call. `hiring.py`'s
`marginal_value` used to guess this per task (Manhattan distance from the shed,
which is a fair estimate for a day's FIRST task and a systematic under-count
for every task after it). It now caps a candidate hand's task-fitting purely by
`n_ops`, against a capacity ceiling `budget * OP_FRACTION`.

**The calibration constant is NOT the raw measurement.** Swept against the
standard pool, 16 seeds:

| OP_FRACTION | mean bank |
|---|---|
| 0.3 | 57,236 |
| **0.44 (the raw measured ratio)** | **55,214 -- worse than no discount at all** |
| **0.6 (shipped)** | **58,943** |
| 0.8 | 58,367 |
| 1.0 (no discount) | 56,162 |

0.44 answers "what fraction of a FULL DAY, at an already-tuned 11-hand crew,
ends up as operations" -- a different question from "what should ONE
CANDIDATE hand's own task-fitting subroutine assume it can reach", which has
no explicit travel term at all (only `n_ops`) and needed its own calibration.
Conflating the two was tried and measured worse. Verified afterward that this
does not trade away survival: fed rate 97%, watered rate 92%, unchanged from
before the change.

### Opponent modelling stays minimal, by directive

`opponent_model.py::earliest_available(farm, item, day)` is the only signal:
the earliest AGENT DAY a farm's VISIBLE tiles could put `item` on the market,
from planted/placed tiles alone (never from inferred holdings, never a style
or pressure classification -- both were built, measured, and explicitly
rejected in favour of this simpler signal). Feeds two decisions, both gated on
`FRONTRUN_LEAD_DAYS` (default 3):

- `market.py::_sell_batch` -- if the opponent's earliest availability for an
  item we hold is within the lead window, sell up to `oneshot_capacity`
  now rather than the item's normal spread/timed/free policy.
- `strategy.py::opponent_adjusted_targets` -- if their earliest availability
  for a crop we are about to plant is within the lead window, trim that
  crop's target tile count to 70% (floored, never zeroed -- section 42's
  "trim, do not replace" finding).

### Land is hard-capped at 3 quadrants, not merely defaulted

`market.py::acquisition_orders` clamps `min(plan.target_quadrants, 3)`
regardless of what a portfolio or package config asks for -- the 4th quadrant
(the SE purchase, $4,000) cannot be reopened by picking a different
`WB_PKG_EXPAND`. $4,000 buys 25 tiles that still need crew and water to be
worth anything; the same money is 10 COW or 40 STRAWBERRY seed batches, either
of which returns a stream. Section 40 already measured labour, not land, as
this farm's binding constraint.

### Where NOON stands

Real-engine-equivalent (`planner.simulate`) win rate against the standard
pool, 16 seeds x 6 opponents = 96 games, all of them against the v3 tape
(unrelated agents, all built on the same mature 719-step base):

```
WIN 0.0%   margin -141,275/game   n=96, fired 96/96
```

Still 0-96. But the absolute numbers moved a lot over this session: mean bank
against kawa alone went from ~$35k (session start, phased architecture just
wired) to ~$120k (now) -- roughly 3x -- while the deficit against the pool
shrank from -229,971 to -141,275 (-38%). Section 40's fixed-opening curve is
still the right frame for reading this: a white-box mid-game that is worth
anything has to beat the replay it displaces at the same step count, and NOON
has closed a large fraction of that gap without yet closing all of it.

**NOON is not shipped.** `submission/dusk.py` (the v3 tape + DUSK) remains the
one submittable build, real-engine 85.4% against the standard pool. NOON is
the from-scratch line of work, kept in `whitebox/` and measured on its own
terms.

## 45. HORIZON — the opponent-signal system, named (2026-08-24)

**HORIZON** is the name of the opponent-modelling signal from now on: not a
fourth time-phase like NOON or DUSK, but the cross-cutting system that watches
the opponent's public state and tells NOON's market layer how far off their
next sale is. Lives in `whitebox/opponent_model.py`, used by `market.py`.

### What was missing, precisely

Asked directly whether the opponent-modelling ask (money changes -> purchases,
plantings, sales -> inventory; planted tiles -> minimum-volume maturity date;
steps back to shed -> earliest SELL time; impact on our own selling) had
actually been built. Checked the code rather than the earlier write-up, and
three gaps were real:

| asked for | status found |
|---|---|
| what they planted | done -- direct observation, public tiles, no inference needed |
| what they sold (inventory) | **built but orphaned** -- `state.py::OpponentTracker` ran `observe()` every turn, `tracker` was threaded all the way to `_sell_batch`, and never read inside it |
| money changes -> purchases | not built, and not needed -- `BUY_SEED`/`BUY_ANIMAL` do not move market inventory (the only channel the tracker reads) but their RESULT is directly visible on tiles anyway; only `BUY_PRODUCT` needs money-adjacent inference and the tracker already gets that from the market-inventory delta, not from money |
| precise maturity ("minimum tiles to harvest") | **`earliest_available` answered a narrower question** -- first single tile ripe, not a threshold volume. A lone stray tile fired the same as a real batch |
| steps back to shed -> earliest sell | **not built at all** -- `earliest_available` returned a DAY based on ripening rules only, conflating "ripe" with "sellable." `SELL` draws from the shed only; ripe produce sits in a worker's pocket until a `DROP` |

### What HORIZON adds: `opponent_model.py::earliest_sellable`

```python
earliest_sellable(farm, item, day, min_units) -> step | None
```

Two corrections over the old `earliest_available`, both requested directly:

- **Volume threshold.** Walks producing tiles in ripening order, accumulates
  units, returns the day the running total first clears `min_units` -- not
  the first tile's day. Verified by direct measurement (one game, sampled
  every 12 steps from step 123): the old any-single-unit trigger fired on
  WOOL **42** times; the volume-gated one (`min_units=6`) fired **10** times.
  MELON was unchanged (11 -> 11) because it ripens as a whole tile at once --
  there was no single-tile noise to filter there in the first place.
- **Shed round-trip.** The triggering tile's Manhattan distance to the
  nearest shed tile, charged as a round trip (there, harvest, back, drop) --
  `2 * home + 2` turns -- added to the ripening day converted to a step. This
  is the same shed-anchored assumption `opp_clear_round` and DUSK's collector
  already use for timing OURSELVES, applied to them.

`market.py::_sell_batch` now fires the front-run on EITHER of two signals,
not one: `earliest_sellable` within `FRONTRUN_LEAD_DAYS` (future ripening,
volume- and travel-corrected), OR `tracker.holdings(item) >=
FRONTRUN_MIN_UNITS` for the reliable half of `OpponentTracker`'s inference
(MELON/EGG/CARROT/TOMATO/STRAWBERRY -- what they are already sitting on,
which no tile-reading can see because it may no longer be on any tile).

### Measured

16 seeds, single opponent (kawa), mean bank:

```
market timing OFF entirely                    58,338
market timing ON  (min_units=1, ~= old)       58,966
market timing ON  (min_units=6, shipped)      58,966
```

Having SOME timing signal is worth **+628** over none. The volume-threshold
choice (1 vs 6) did not separate at this sample size -- section 5's own rule
applies here as much as anywhere else, >=100 games before a rank means
anything, and n=16 is well short. `min_units=6` (default,
`WB_FRONTRUN_MIN_UNITS`) is kept on MECHANISM, not on this measurement: it
cannot fire on a single stray tile the way the unfiltered version can, and the
measurement did not show it doing any WORSE. Revisit at higher n if the
question matters later.

### The three names, current state

| name | window | what it is | status |
|---|---|---|---|
| **DUSK** | steps 670-718 | historical tape overlay: deadline mask, `opp_clear_round-1`, fixed 8-step collector, terminal liquidation | **not legal under the white-box-only contract**. The 85.4% result belongs to `submission/dusk.py` plus its v3 tape and is historical evidence only; every rule must be re-derived and re-tested on the computed state. |
| **NOON** | computed mid-game | current white-box line: live task DAG, open routes, route-coupled hiring, provisional `theory_v0` targets | legal production path, not shipped. Ryo targets and calibrated undone-task hiring were removed. Current 18-game screen: $35,453 own, -$88,853 margin, 0 wins. |
| **HORIZON** | cross-cutting | public-state opponent timing and inferred holdings | input source is legal, but the current point-estimate model is not exact and the wrapper is not yet the single downstream interface. Treat as experimental until converted to feasibility intervals and tested through an actual decision consumer. |

The fixed opening (steps 0-122, Ryo's replayed sequence) remains unnamed --
it is not a decision system, it is a literal replayed trace, and naming it
would suggest there is a policy there to reason about when there is not.

## 46. White-box-only reset (2026-08-27)

Project constraint changed: another player's tape, replayed opening, mined
target schedule, and learned action imitation are not legal components of the
final architecture. `whitebox/agent.py::_whitebox_entry` is now the production
line: its tape loader, seam substitution and replay-opening branch were removed,
and `whitebox/strategy.py` defaults to `computed` rather than `leader`.

The honest pure-computed baseline is weak: 18 simulator games against three
standard opponents, seeds 9100-9105, mean own bank **$30,086**, mean margin
**-$101,972**, 0 wins. A traced game spends the opening $3,000 down to $4 on
four COW plus slow-return MELON/STRAWBERRY assets and does not reach material
cash generation until about day 19. The first binding defect is therefore the
separate animal-first / seed-second purchase architecture: asset purchase,
future task demand and time-to-first-cash are not jointly constrained.

An experimental animal bridge reserve was added behind `WB_ANIMAL_BRIDGE=1`.
It reserves live-price wheat until first animal yield. On the same 18 games it
improved mean margin to -$93,621 but reduced own bank to $28,667 and remained
0 wins. It is correctly **default OFF**: the solvency mechanism is real, but a
reserve inside the still-wrong animal-first loop is not the joint optimiser.

One old task premise is also formally retired. `WB_EXACT_TOUR` assumes every
HARVEST/COLLECT is an independent shed round trip. The engine auto-drops all
unit inventories at rollover, so the correct daily problem is an OPEN
prize-collecting multi-worker route with bulk input pickup and an optional
end-of-day DROP, not a round-trip knapsack. Keep `WB_EXACT_TOUR=0`.

The target design and implementation order are in
`WHITEBOX_ARCHITECTURE.md`: finite-horizon economy MPC -> engine-derived task
DAG and shadow values -> open prize-collecting routing -> robust simultaneous
market best response. No external action trace is part of that design.

### Joint hiring-route implementation (2026-08-27)

`whitebox/hiring.py` no longer values a hand as `OP_FRACTION` times the old
plan's undone operations. For every feasible `k`, it now rebuilds the complete
route allocation for all existing workers plus `k` hypothetical new hands and
maximises:

```
scheduled_value(k) - scheduled_value(0)
- hire_block_cost(hires_today, k)
```

The hypothetical hands use the exact engine timing and spawn rule: unit actions
resolve first, HIRE resolves in the market phase, the new hand begins at
`hour+1`, and its spawn is the least-occupied shed tile after current movement
with NW/NE/SW/SE tie-breaking. Every hire consumes a market slot. A crew-size
change then invalidates `tasks.assign`'s cache on the next turn, so those hands
receive and execute real routes rather than remaining abstract capacity.

The production import graph was also sealed. `_whitebox_entry` no longer has a
runtime portfolio selector, and `agent/strategy/tasks/hiring/market` import no
behavior, opening, weights, package, schedule or target module. A fresh-process
audit reports `FORBIDDEN_IMPORTED []`. Historical files remain in the repo but
cannot enter the production path.

Four rule tests in `whitebox/test_hiring.py` pass: post-action spawn occupancy,
new-hand route value, own-farm Fibonacci counter, and hour-23 rejection. A full
seed-9100 trace shows hired hands receiving non-PASS routes; agent decision time
was 1.62 ms mean, 4.77 ms max. The modular agent also needed a real-engine
loader fix because raw Python is executed without `__file__`; after the fix,
seed 9100 versus kawa finishes `DONE/DONE` at $59,610 / $123,014 (our bank is
identical to the simulator's $59,610).

Do not overclaim the score. First replacing only the old hiring heuristic gave
$38,016 own / -$86,590 margin on the same 18-game screen, but correcting the
partition bug that could strand an oversized first task produced the final
$35,453 own / -$88,853 margin, 0 wins. Against the provisional `theory_v0`
control ($36,218 / -$88,608), that is -$765 own, -$245 margin, with 9 better
and 9 worse cells (paired-own t=-0.16). The mechanism is required for semantic
correctness, not promoted as a measured strength gain. The immediate blocker
is that it optimises fixed task constants (`FEED=900`, etc.); until Layer 2
replaces them with terminal-money shadow values, the correct hire-route coupling
is still solving the wrong value function.

## 47. Joint objective / task / route solver (2026-08-27)

The fixed task constants named at the end of section 46 are gone from the live
enumerator. `whitebox/value.py` is now the common engine-derived relaxed-dollar
objective used by task enumeration, opportunistic work and hiring. It prices
harvested units down the exact marginal sell curve after visible opponent
standing supply; values future crop/animal production only when it can mature
before the last actionable day; charges consumed WHEAT/FERTILIZER at opportunity
cost; and turns imminent crop/animal loss into a hard mandatory task rather than
an arbitrary large weight.

`route/router.py::joint_assign` replaced angular partitioning in the live path.
It solves task selection and worker assignment together under each worker's
remaining-turn budget and the farm-wide carried-input constraint. Insertions are
priced by their change to the complete open route, followed by cross-worker
relocations, prize exchanges and refill. Routes with at most ten unique stops
use exact Held-Karp; larger routes retain deterministic NN+2-opt. A carry route
is now costed and emitted as current position -> nearest shed -> bulk PICKUP ->
open task route, fixing the old impossible assumption that a remote worker
already held its inputs.

The first joint implementation regressed seed 9100 from $59,610 to $58,227
because every same-day hire invalidated the cache and made the whole incumbent
crew change targets. Event replanning now locks each old worker's first still-
live stop as a forced prefix, then jointly allocates all uncommitted work and the
new workers. The same seed finishes at **$63,334 / $147,181**, with 178 hires,
166 FEED, 166 CARE and 287 HARVEST. Ten rule tests pass across
`whitebox/test_joint_planner.py` and `whitebox/test_hiring.py`.

Four common-random-number seeds (9100-9103) versus kawa compare the new joint
solver with the old angular partition while holding the new dollar objective
fixed:

| solver | mean own bank | mean opponent bank | mean margin |
|---|---:|---:|---:|
| joint + prefix commitment | **$48,204** | $119,157 | -$70,953 |
| angular partition | $25,655 | **$94,978** | **-$69,323** |

This is strong evidence that the joint solver creates much more productive
farms, but not yet evidence that it improves the true simultaneous-game
objective: own bank rises $22,549 while opponent bank rises $24,179, leaving
margin $1,630 worse at n=4. NOON remains a development line, not a submission.
The next objective correction is opponent-relative market value, not another
route-only heuristic.

Two tempting coupling patches were explicitly rejected. Charging all existing
workers from `hour+1` improved one low seed but regressed the paired result; more
importantly, the current task object had not yet projected the already-executed
unit operation, so it was not a consistent post-action state. Projecting this
turn's planned seed/animal purchases into future tasks fixed the seed-9101
under-hiring symptom ($8,239 -> $49,288), but over four seeds reduced mean own
bank to $46,564 and margin to -$72,827. Reserving those purchases before hiring
was worse again. All three experiment paths were removed from production.

The correct next master problem must make capital commitments **optional**, not
precommitted. A route column may depend on BUY_SEED / BUY_ANIMAL / BUY_LAND;
selecting that column activates both its cash/order prerequisite and its future
PLANT or BUILD->PLACE task chain. Hire columns then compete with asset columns
for the same cash and ten market slots. This is the minimal formulation in which
objective, task allocation, path planning and hired-worker behaviour are truly
joint rather than sequentially patched together.

Real-engine gate for the promoted development build, seed 9100 versus kawa:
`DONE/DONE`, **$63,332 / $146,946**. The fast simulator returned
$63,334 / $147,181, so this dynamic white-box matchup is not bit-exact (ours
-2, opponent -235); use the simulator for paired screening and the real engine
for every promotion decision.

## 48. Optional capital columns enter the joint master (2026-08-27)

Section 47's next formulation is now implemented as a one-step white-box
relaxation in `whitebox/capital.py`. The old flow committed BUY_ANIMAL /
BUY_SEED / BUY_LAND first and asked the labour planner to cope afterwards. The
new flow treats the computed acquisition orders only as upper bounds. Every
individual proposed asset becomes an optional route column:

```
seed unit    = cash(seed) + shared BUY_SEED slot -> PLANT -> WATER
animal unit  = cash(animal) + shared BUY_ANIMAL slot
               -> [BUILD] -> PICKUP animal -> PLACE
locked tile  = one shared fixed BUY_LAND cash/slot activation
hire k       = exact Fibonacci block + k slots + k real spawned workers
```

`route.router.Task` therefore carries `cash_cost`, `order_key` and shared
`activations`. `joint_assign` enforces their farm-wide cash and distinct-order
limits alongside WHEAT/FERTILIZER/animal carry stock and every worker's route
budget. Only selected capital columns are converted back into market orders;
two selected WHEAT columns emit one `BUY_SEED WHEAT 2`, and several tasks in a
locked quadrant pay/emit BUY_LAND once. Feed remains a prerequisite order,
while HIRE and capital compete for the same remaining cash and ten slots.

This directly includes hired-worker behaviour: for each legal `k`, the master
adds workers at the engine's post-action spawn tiles with first action at
`hour+1`, reruns all task selection/assignment, subtracts the exact Fibonacci
bill, and emits only the asset quantities actually carried by the winning
routes. No other player's tape, opening or learned target enters the module.

### Evaluation

Seed 9100 versus kawa improved from section 47's $63,334 / $147,181 to
**$72,188 / $142,399** in the fast simulator (margin +$13,636 relative to the
previous joint build). The real Kaggle engine finishes `DONE/DONE` at
**$72,188 / $142,364**.

Disjoint evaluation, seeds 9200-9205 x three standard opponents, 18 paired
cells:

| capital master | mean own bank | mean margin |
|---|---:|---:|
| OFF (section 47 joint route) | $34,547 | -$64,995 |
| ON | **$56,113** | **-$62,115** |
| paired ON - OFF | **+$21,566** | **+$2,880** |

Own-bank cells are 17-1, but the true game objective is margin and those cells
are only 13-5. With the measured per-cell margin SD around $13,000-$15,000,
+$2,880 at n=18 is about **0.9 standard errors**. This screen is useful enough
to retain the implementation, not to promote it. `WB_CAPITAL_MASTER` is
therefore **default OFF** pending at least 288 paired simulator cells and a
multi-seed, both-seat real-engine gate. The only true-engine result above is
one seed, which proves executability, not rank.

The original runtime was 48.5ms mean / 228ms P95 / 658ms max. After the §49
anytime guard, the same capital-ON seed measures 38.6ms / 180.1ms / 182.9ms;
no turn exceeded 350ms or 1s. Default OFF measures 20.0ms / 105.1ms / 182.0ms.
Twenty white-box rule tests pass.

### Remaining relaxation

The master sees only acquisition quantities proposed by the current computed
Plan, so it can reject or resize that portfolio but cannot yet invent a crop or
animal outside the proposal. Asset value is a relaxed terminal-dollar stream,
not a full multi-day cash-flow state, and existing-worker capacity is still
priced from the pre-action task snapshot. Most importantly, opponent effects
enter through conservative sale prices but not yet through the full
`money_us - money_opp` market externality. The next step is a multi-day bundle
DP/column generator plus the Layer-4 robust simultaneous-sale objective, not
more fixed portfolio tuning.

## 49. Runtime, engine facts and experiment tombstones (2026-08-27)

### Runtime is a hard game constraint

The installed environment defines `actTimeout=1` second and gives each agent
`remainingOverageTime=60` seconds for the **whole episode**. The runner charges
only the part of a call above 1s against that pool, but once a call exceeds the
remaining pool `agent.py` returns `DeadlineExceeded`; `core.py` turns
`ERROR/INVALID/TIMEOUT` into `reward=None`. One runtime failure is a forfeit.

The production entry now creates one monotonic 180ms soft deadline at the top
of every action and threads it through task assignment, hiring, the optional
capital master and route emission. The solver is anytime:

- use the same-day cached route when a crew-event replan arrives after budget;
- otherwise return a deterministic feasible value-first assignment that still
  enforces worker turns, carried stock, capital cash and market-order keys;
- stop insertion/relocation/exchange/refill at the deadline;
- do not start candidate-wide scoring with less than 10ms left;
- do not start exact Held-Karp with less than 50ms left; use NN+2-opt.

The cutoff is deliberately far below 1s because judging hardware may be slower
and because task generation/action emission still need headroom. Performance
must be gated on maximum and timeout count, not mean alone.

Default-OFF production execution gate after the change: seeds 9100 and 9101,
both seat orders, four real-engine games, **4/4 `DONE/DONE`**, no TIMEOUT or
INVALID. White-box banks by `(seed, seat)` were $63,856, $71,624, $8,239 and
$8,239. This validates execution only; it is not an A/B strength result and
does not qualify the optional capital master.

### Engine facts now part of the architecture

| fact | verified consequence |
|---|---|
| day rollover auto-drops every unit inventory, then deletes any amount above the 100-item shed capacity | old four-day/60 feed buffer destroyed 61.9 units / $1,629 per game; 2-day/16 reduced measured loss to 0.4. Capacity must be a Layer-1 state constraint. |
| `whitebox.econ.price` versus the current installed engine | zero error on 8,100 price points and 540 sequential trade updates. `whitebox/value.py` may use it as exact arithmetic. |
| historical ladder replays use an older CARROT/TOMATO/EGG low-inventory curve | replay fidelity and current-engine fidelity are separate gates. `planner.simulate` now defaults to current engine constants; the replay test injects its historical parameters explicitly. |
| opponent farm money is public and every purchase is cash constrained | at observed purchase time, cash was median 1.23x the price and 68% of buys occurred within two steps of first becoming affordable. Cash is a free necessary-condition signal for future purchases, not a reconstruction of past buys. `Horizon.cash/can_afford/affordability_gap` exposes it without claiming intent. |
| mid-game unit inventories auto-drop at night | 0 mid-game DROP actions is correct unless a same-day sale or overflow shadow price pays for the trip. |
| greedy open route versus Held-Karp | measured relaxation was 42.8%; exact routes remain useful when time permits, never at the cost of a timeout. |

The opponent-cash correction supersedes §45's narrower conclusion that
"money -> purchases is not needed." It is indeed not needed to infer a purchase
which already happened and became visible on a tile. It **is** needed to bound
whether a future purchase is feasible. Cash alone is not a behaviour model:
market slots, shed/tile capacity and objective value still bound the action.

### Retired or unreachable experiment switches

| old switch | evidence | production status |
|---|---:|---|
| `WB_PACED` | -$143 to -$3,290 | falsified; hard `PACED=False`, env cannot reopen it |
| `WB_FLUSH` | approximately $0 | not promoted; hard `FLUSH=False`. Overflow physics remains in the capacity model. |
| `WB_DEADLINE_TRIM` | -$7,409 | falsified; hard zero. State-dependent economics belongs in value, not a global deadline shift. |
| `WB_CROP_PLAN` | -$10,395 | falsified; `_cplan=None`, `CROP_PLAN=""`, unreachable from production |
| `WB_OPEN_HERD` | replay-opening selector | retired by the white-box contract; `opening_sequence.py` is not in the production import/action path |
| `WB_HORIZON_TARGETS` | no qualified margin result | historical leader-only function, unreachable from `_decide_computed`; switch is hard disabled. Keep the sensor API, not its unqualified point-estimate target trim. |

Do not rerun the four falsified arms unless the underlying formulation changes.
A larger sample of the same switch is not a new formulation.

## 50. V55 joint banking routes: recovered after the interrupted session (2026-08-28)

The last implementation completed before the desktop conversation was
interrupted is `whitebox/versions/v55_joint_bank_routes.py`.  It keeps V48's
optional capital master and makes productive route outputs part of that same
solve: a selected HARVEST/COLLECT route reserves its shed-return tail and DROP,
the emitted unit action can bank that inventory on the same turn, and the
market layer merges the corresponding SELL.  Hiring, asset columns, routes,
DROP and SELL therefore compete under one executable turn budget instead of
assuming that output reaches the shed for free.

The recovered validation state is clean:

- 25 rule tests pass across joint planning, hiring, capital, market and HORIZON;
- all changed white-box modules compile;
- every recorded arena run has zero errors and zero unfinished games.

Common-random-number comparison against V48:

| screen | paired cells | mean margin delta | W-L | interpretation |
|---|---:|---:|---:|---|
| quick simulator, seeds 14000-14005 x hard 3 | 18 | +$7,916 | 12-6 | encouraging, underpowered |
| current simulator, seeds 15000-15002 x hard 3 | 9 | -$5,129 | 2-7 | negative small screen |
| real engine, same seeds/opponents | 9 | -$5,129 | 2-7 | exact sign confirmation of the negative screen |
| standard simulator, seeds 16000-16017 x six opponents | 108 | +$2,442 | 62-46 | +1.14 SE, not separable |

On the standard screen V55's paired absolute margin is -$120,441 versus
V48's -$122,883.  Self-play favours V55 by +$9,260 per seed (15-3), but the
external pool remains 0 absolute wins in 108 paired cells.  This is useful
mechanism evidence, not a promotion result: the real-engine screen has the
opposite sign and the architecture's 288-cell gate is unmet.  Keep V55 behind
its explicit variant (`bank_sales="joint_routes"`); do not make it the
production default and do not submit it.

The next implementation item remains `WHITEBOX_ARCHITECTURE.md` step 2: extend
the one-step optional capital columns into a multi-day cash-flow bundle
generator that can invent portfolios.  V55 closes one same-day
route-to-bank-to-sale relaxation but does not solve the multi-day cash state or
the robust opponent-relative market objective.

## 51. Strict-white-box audit, V56 fixed land charge, and persistent handoff (2026-08-28)

All 43 Markdown records in the repository were reread after the interrupted
desktop session, including the endgame selling notes.  The historical endgame
proposal is not an admissible production rule: animals cannot be sold, PICKUP
is not harvest, opponent inventory is not exactly observable, and the proposed
terminal squeeze is not a proved market invariant.  Its useful remainder is a
requirement to derive terminal feasibility from current state, not a fixed
round or fixed liquidation window.

The production import closure is data-clean: it contains only white-box state,
economics, market, horizon, task, capital, strategy and route modules, with no
replay, learned-weight, schedule, opening or opponent-tape import and no runtime
file I/O.  That is necessary but not sufficient for the user's strict contract.
The remaining non-white-box relaxations are explicit: the fixed 6-COW/4-SHEEP/
3-quadrant proposal ceiling, a fixed-seed 64-sample synthetic shop average,
additive per-task values despite nonlinear same-item market clearing, fixed
selling/recovery/front-run constants, no multi-day cash/feed/labour/shed
certificate, and an own-dollar objective that is not yet a robust simultaneous
margin objective.  These are development hypotheses, not economically proved
production parameters.

`whitebox/versions/v56_fixed_land.py` fixes one concrete objective error.  V48-
V55 constrained BUY_LAND cash but did not subtract its shared fixed charge from
the master objective.  `whitebox/capital.py` now enumerates enabled activation
sets (exactly through four keys), solves each hire/activation branch, and
subtracts each selected fixed charge once.  Feasibility and objective therefore
use the same land cost.  Historical V48-V55 wrappers explicitly set
`charge_activation_cost=False` so their recorded baselines do not silently
change when the shared core changes.  Four focused tests prove shared versus
distinct activation accounting and the $800/$1,200 value decisions behind a
$1,000 land charge.  The white-box suite now passes 29 tests and all changed
modules compile.

Formal common-random-number quick screen, V56 versus immutable V55, seed0
17000:

| screen | paired cells | result | firing | interpretation |
|---|---:|---:|---:|---|
| self-play | 6 | -$2,405 total; -$401/seed; 1-2-3 | n/a | neutral |
| hard opponent pool | 18 | +$1,111 mean delta; 6-4 on firing cells | 10/18 | neutral, underpowered |

The exact log is `logs/arena/v56_vs_v55_quick_17000.json`; there were no errors
or unfinished games.  The earlier
`logs/arena/v55_fixed_cost_vs_v48_quick.json` is only a preliminary screen and
must not be used to isolate the charge because both variants imported a mutable
shared core at that time.  V56 is retained as a corrected development variant,
not promoted as stronger.

The next work order is: observable-current-shop conditional value; nonlinear
bundle sale value; multi-day cash/feed/labour/shed certificate that can invent
the portfolio; route trim plus recertification; then interval/robust
opponent-relative and state-driven terminal value.  Do not return to fixed
portfolio tuning.

This worktree is already on the persistent 3090 host
`jll-3090.server.thuiiif` (`10.144.51.6`), so shutting down the desktop does not
remove it.  The unattended campaign is launched in tmux session
`kagg-whitebox`; logs and the Codex session ID live in
`logs/remote_campaign/`.  The exact autonomous contract is in
`docs/REMOTE_CAMPAIGN_PROMPT.md`, and the watchdog is
`scripts/whitebox_remote_campaign.sh`.  Recovery commands:

```
ssh yilewang@10.144.51.6
cd /home/yilewang/kaggriculture
tmux attach -t kagg-whitebox
```

Detach with `Ctrl-b d`.  To request a clean stop after the current Codex run,
create `logs/remote_campaign/STOP`; to terminate immediately, kill the tmux
session.  The watchdog resumes the same non-interactive Codex session every 30
seconds after a completed turn, using `gpt-5.6-sol`, high reasoning, approval
policy `never`, and `danger-full-access` as explicitly requested by the user.

## 52. V57 observable-shop analytical valuation (2026-08-28)

`whitebox/versions/v57_shop_conditioned.py` is the first isolated candidate
after V56. It removes the fixed-seed 64-draw shop assumption from the crop-mix
valuation used by this arm. The engine reveals the current shop multiset and
draws each future instance uniformly with replacement at deterministic
three-day boundaries. `whitebox.market_model.expected_town_take` therefore
computes, over live steps `[now, 719)`,

```
known drain = exact multiplicity-weighted contribution of snap.shops
future drain = future unlocked slots * mean contribution over the 8 shop names
centre drain = exact non-FERTILIZER ticks
```

The future term is a finite sum over the engine's eight equally likely shop
names, not Monte Carlo and not a fitted coefficient. Duplicate observed shops
count independently, and an unlock enters on its first usable step. The stated
relaxation is narrow: linearity makes expected absorption exact, but nonlinear
sale revenue at expected inventory is not claimed to equal expected nonlinear
revenue. That remains for the bundle/robust-market steps.

V56 remains an immutable control: callers without a live snapshot retain the
old sampled `TOWN_DAY` path, while only `plan_variant="shop_conditioned"` asks
for the conditional mix. Six new equation-level tests cover duplicate shops,
the closed-form future expectation, disappearance of uncertainty after all
eight unlocks, exact unlock timing, replacement of prior by observed shop, and
a crop-mix response to two public shop states. The full white-box suite is now
35/35 passing and the changed modules compile. No gameplay result has yet been
recorded for V57; do not infer improvement from the semantic correction.

Quick CRN screen versus immutable V56, seed0 18000, is recorded at
`logs/arena/v57_vs_v56_quick_18000.json` (simulator, 1.8 minutes, no engine
errors or unfinished games):

| screen | paired cells | result | firing | interpretation |
|---|---:|---:|---:|---|
| self-play | 6 | -$13,779 total; -$2,296/seed; 1-5 | 6/6 | invalid for ranking: candidate mirror was nonzero on 1/6 seeds |
| hard opponent pool | 18 | +$1,011 mean delta; 9-9 | 18/18 | neutral and inherits candidate nondeterminism |

The V56 identity control was exact, but V57's own mirror returned +$5,419 on
one of six seeds. This is a failed determinism gate, most plausibly an anytime
deadline branch exposed by the changed crop mix; the pool delta must not be
used as strength evidence. Diagnose and eliminate that source before any
larger screen. Import closure itself passed: `FORBIDDEN_IMPORTED []`.

The first implementation of the expectation was exact but looped across every
remaining step for every product on every action. It has been replaced by the
algebraically identical closed form: count shop/centre tick multiples in a
half-open interval, then add at most eight future-unlock progressions. A new
test compares that form to the stepwise equation at six season positions for
WOOL, MILK and FERTILIZER. The suite is now 37/37; 10,000 conditioned
`crop_mix` evaluations take 156 ms total on this host (~0.016 ms each). The
same-seed determinism screen still must be rerun; this optimisation does not by
itself prove the mirror failure is gone.

The exact-seed rerun is
`logs/arena/v57_vs_v56_quick_18000_closedform.json` (simulator, 1.8 minutes).
This time V57's mirror was exact, but V56's identity control was nonzero by
$639 on 1/6 seeds, so `arena.py` correctly aborted the run. The hard-pool rows
happened to reproduce the first run to the dollar (+$1,011 mean, 9-9, firing
18/18), but an aborted identity control means they are still not evidence.
The failure moving from candidate mirror to baseline mirror across identical
seed reruns strongly points to wall-clock anytime cutoff jitter under the
26-worker load, not stateful shop mathematics. Runtime/cutoff frequency must be
measured directly before another strength screen.

Isolated same-seed latency trace (seed 18000, seat 0 versus kawa) found no
actual cutoff in either arm: V56 bank $46,898, 18.45 ms mean / 73.94 ms P95 /
130.73 ms max; V57 bank $46,692, 20.12 / 75.13 / 130.91 ms; both had 0 turns
at or above 170 ms. V57 adds about 1.7 ms mean but essentially no P95/max cost.
The mirror failures therefore arise only under the saturated arena process
load. Keep the 180 ms production limit; obtain a clean identity-controlled
screen rather than raising the budget and evaluating a different policy.

## 53. V58 nonlinear same-product capital bundle value (2026-08-28)

`whitebox/versions/v58_bundle_values.py` is an independent V56-based arm; it
does not stack the nondeterministic V57 portfolio response. V56 values every
optional crop/animal column against the same current book, so three new
STRAWBERRY tiles, COWs or SHEEP each receive the revenue of being first. V58
derives each column's terminal units from the crop/animal production rules,
groups columns by sale product, removes each standalone sale term, and applies
`objective.sale_value`/`econ.sell_revenue` once to the aggregate quantity:

```
bundle_value[item] = sell_revenue(item, sum(column_units), live_book)
column_value = non_sale_terms + bundle_value * column_units / total_units
```

The proportional allocation prevents identical assets on different tiles from
receiving arbitrary first/last prices merely due to coordinate order. Its
explicit relaxation is conservative: a selected subset retains the full
proposal bundle's average price rather than being repriced upward; the planned
route-trim/recertification stage is where selected quantities must be repriced
exactly. Seed/animal cash and feed opportunity costs remain separate and are
not lost in the sale aggregation.

Three new tests prove that three repeated STRAWBERRY columns sum to exactly one
12-unit nonlinear sale, a singleton is unchanged including seed cost, and two
COW columns share one MILK curve while retaining their non-sale terms. Together
with the shop equations, the full white-box suite is 40/40 passing and changed
modules compile. V56 behavior is isolated because repricing runs only for
`capital_variant="bundle_values"`. No gameplay result is yet recorded.

Valid quick screen versus immutable V56 is
`logs/arena/v58_vs_v56_quick_18200.json` (seed0 18200, simulator, 1.7 minutes,
both mirrors exact, zero errors/not-done):

| screen | paired cells | absolute candidate result | paired V58-V56 | firing |
|---|---:|---:|---:|---:|
| self-play | 6 seeds | -$21,104 total head-to-head; 1-2-3 | -$3,517/seed | 3/6 nonzero |
| hard pool | 18 | mean paired margin -$126,962; 0 absolute wins | +$3,022 mean; 6-7 on firing cells | 13/18 |

The conditional pool delta is +$4,184 (SE $4,050, t=1.03), while paired win
rate on firing cells is 46.2%. This is mixed and underpowered, not an obvious
margin collapse; advance only to the existing 108-cell standard screen. Import
closure passed (`FORBIDDEN_IMPORTED []`).

The required 108-cell standard rejection gate is
`logs/arena/v58_vs_v56_standard108_18300.json` (seed0 18300, simulator,
5.4 minutes, both 18-seed mirrors exact, zero errors/not-done):

| screen | cells | V58 absolute paired margin | V56 absolute paired margin | V58-V56 | firing |
|---|---:|---:|---:|---:|---:|
| self-play | 18 seeds | head-to-head -$62,814 total; 2-7-9 | n/a | -$3,490/seed, SE $1,618, t=-2.16 | 9/18 nonzero |
| standard external pool | 108 | -$118,569 mean; 0 absolute wins | -$119,434 mean; 0 absolute wins | +$865 mean | 42/108 |

Conditional on firing, the pool delta is +$2,224 (SE $1,885, t=1.18) with
23-19 firing-cell wins (54.8%). Per-opponent mean deltas range from -$891 to
+$3,386. The external result is not separable and the direct V56 comparison is
negative, so confidence is inadequate: do **not** run the 288-cell or real-
engine promotion gates and do not promote V58. Retain the implementation and
tests as the correct nonlinear mechanism; its conservative full-proposal
average-price relaxation should be revisited only with selected-quantity route
trim and recertification, not by tuning a multiplier.
The initial persistent Codex session ID is
`01a04467-ce88-7170-8c53-5c62209fa102`; its first JSONL log is
`logs/remote_campaign/codex_20260827T180724Z_iter1.jsonl`.

## 54. V59 selected-quantity bundle recertification (implementation, 2026-08-28)

`whitebox/versions/v59_bundle_recertify.py` is an isolated V58-based arm for
the explicit relaxation left by section 53. V58 sends the route master a
conservatively priced full capital proposal, but a route-feasible subset still
carried that full proposal's average sale price when hire and fixed-activation
branches were compared. V59 freezes, before repricing, each column's
rule-derived product units and non-sale value. After the route master trims the
proposal to an executable set, the comparison objective is recertified from
only the selected quantities:

```
Q[item] = sum(output_units[column] for selected columns producing item)
selected_value = ordinary_task_value
               + sum(non_sale_value[selected capital columns])
               + sum(sell_revenue(item, Q[item], live robust book))
               - hire_cost - shared_activation_cost
```

This is deliberately conservative in scope. It can choose among already
route-certified hire/activation branches using their exact actual quantities;
it does not reopen rejected columns, invent a portfolio, or use purchased
capital before same-step unit actions. The input route values remain V58's
full-proposal certificate, so V59 adds no black-box search policy or fitted
coefficient. V56 and V58 behavior is unchanged because the recertified score
runs only for `capital_variant="bundle_recertify"`.

Two equation-level tests prove (a) a three-column STRAWBERRY certificate
trimmed to one column receives exact singleton revenue rather than one third of
the three-column bundle and (b) a two-column retained bundle applies nonlinear
sale revenue once while preserving ordinary task value, per-column non-sale
terms, hire cost, and shared BUY_LAND activation exactly once. The full
white-box suite passes 42/42 and the changed modules compile. Gameplay evidence
is recorded below; V59 is not promoted.

The fresh-process production import audit reports `FORBIDDEN_IMPORTED []` for
replay/opening/tape, mined schedule, learned package/weight, and search-policy
modules. The imported `whitebox.opponent_model` is the existing public-tile
maturity and shed-travel equation module, not a target fingerprint or policy.

A deliberately unsaturated serial determinism gate is
`logs/arena/v59_vs_v58_serial_mirror_18400.json` (simulator, 6 seeds, one
worker, 13.9 minutes): the V58 identity control was exactly zero on 6/6 seeds,
V59's own mirror was exactly zero on 6/6, and V59 versus V58 was zero on every
seed. There were no errors. Thus the candidate preserves its control exactly
when selected-quantity recertification does not change the winning branch; the
opponent-pool firing and margin screens follow below.

An isolated full simulator episode at seed 18450 versus
`kaggriculture-multi-route-farming-agent` measured 719 V59 decisions at 18.221
ms mean, 69.434 ms P95, 113.025 ms P99 and 152.605 ms maximum, with zero calls
at or above 170 ms (13.321 seconds episode wall time; final banks $42,788 /
$114,564). The selected-quantity aggregation does not threaten the 180 ms soft
deadline in this trace.

The valid CRN quick screen versus V58 is
`logs/arena/v59_vs_v58_quick_18500.json` (simulator, seed0 18500, 1.6 minutes,
both 6-seed mirrors exact, zero errors/not-done):

| screen | paired cells | absolute candidate | absolute baseline | V59-V58 | firing |
|---|---:|---:|---:|---:|---:|
| self-play | 6 | head-to-head -$2,850 total; 0-1-5 | n/a | -$475/seed, SE $434, t=-1.10 | 1/6 |
| hard pool | 18 | -$118,387.83 mean paired margin | -$118,673.00 | +$285.17 mean | 3/18 |

Conditional on pool firing the delta was +$1,711 (SE $6,112, t=0.28),
W-L 2-1. This sparse result is neutral and underpowered, not an obvious
regression. Per the campaign rule that quick screens only reject, advance to
the existing 108-cell standard gate; do not infer strength from this result.

The completed standard rejection gate is
`logs/arena/v59_vs_v58_standard108_18600.json` (simulator, seed0 18600, 5.6
minutes, both 18-seed mirrors exact, zero errors/not-done):

| screen | cells | V59 absolute paired margin | V58 absolute paired margin | V59-V58 | firing |
|---|---:|---:|---:|---:|---:|
| self-play | 18 seeds | head-to-head +$6,346 total; 2-0-16 | n/a | +$353/seed, SE $235, t=1.50 | 2/18 |
| standard external pool | 108 | -$112,357.85 mean; 0 absolute wins | -$112,799.44; 0 absolute wins | +$441.59 mean, SE $382.73, t=1.15 | 23/108 |

Conditional on pool firing, V59 gained +$2,073.57 (SE $1,756, t=1.18) with
14-9 firing-cell wins (60.9%). Per-opponent mean deltas were +$1,124.11,
+$29.06, -$47.28, +$1.06, +$81.06 and +$1,461.56 in the standard pool's
listed order. This is positive-neutral evidence, not adequate confidence:
only 23 independent pool cells fired and both the unconditional and
conditional t statistics are below the promotion threshold. Do not promote
V59, do not run the 288-cell or real-engine promotion gates from this result,
and do not tune a multiplier. Retain the exact mechanism and tests as an
unpromoted candidate. The next high-value work is the multi-day cash/feed/
labour/shed/order-slot portfolio certificate; it should produce certified
quantities for this route-trim/recertification interface rather than inherit
the fixed `6 COW + 4 SHEEP + 3 quadrants` proposal ceiling.

## 55. V60 multi-day incremental portfolio certificate (implementation, 2026-08-28)

`whitebox/versions/v60_cashflow_portfolio.py` is an isolated V59-based arm.
`whitebox/cashflow.py` replaces the inherited fixed capital proposal at the
once-per-day hour-0 MPC cadence with a deterministic portfolio invented from
the current observation and engine equations. Historical V56-V59 paths do not
import this module: `capital.py` loads it lazily only for
`capital_variant="cashflow_portfolio"`.

For every candidate crop/animal count and the exact no-land/next-land fixed-
charge branches, the certificate constructs a sufficient multi-day schedule:

```
upfront cash = seed + animal + one shared BUY_LAND charge + fixed product buys
daily work   = independent shed round trips at exact Manhattan distance
daily crew   = constructive first-fit packing into 22 route turns/worker
               (hour 0 purchase/hire, hour 1 start, final DROP reserved)
daily cash   = prior cash - exact Fibonacci hires - exact WHEAT buy
               + exact grouped same-item sell_revenue
```

It rejects any bundle whose cash falls below `plan.cash_floor` at any modelled
purchase point, whose animals/feed or rollover output exceed the 100-item shed,
whose hour-0 HIRE plus one aggregated feed order exceed ten slots, whose output
sale types exceed ten slots, or whose independent routes cannot fit. Crop
PLANT/WATER/production/HARVEST and animal BUILD/PLACE/FEED/CARE/production/
HARVEST dates come directly from the engine constants. Assets purchased in a
market phase are never credited to unit actions earlier in that step; this
conservative certificate starts their service on the next modelled day.

Future market uncertainty is explicit rather than fitted. The pricing book
reserves all rule-derived remaining output of both farms' currently visible
crops and animals ahead of the new bundle and ignores town drain. New output is
aggregated by `(day, item)` and applied once through `econ.sell_revenue`, with
the resulting inventory carried into later days. Hidden future opponent
capital is not guessed. This is therefore an incremental visible-supply book,
not yet the simultaneous opponent interval solver required later by the
architecture. Existing farm obligations remain protected by `plan.cash_floor`;
the certificate proves that the incremental portfolio never consumes that
reserve under its stated book.

Portfolio construction greedily adds the feasible asset with the largest
exact increment in certified final cash; every asset consumes one physical
slot and the next-land branch pays its activation once. This is a transparent
deterministic primal heuristic, not a learned policy or coefficient. The route
master then trims the certified proposal to executable current routes and the
V59 selected-quantity objective recertifies the retained nonlinear bundle.

Six equation tests prove grouped sale clearing and inventory movement, the
cash-reserve invariant on every modelled day, one-time shared land cost, shed
overflow rejection, combined daily HIRE/feed order-slot rejection, and a
day-0 proposal that is not the fixed six-COW/four-SHEEP ceiling. On the test
day-0 state the invented proposal is `1 COW + 1 SHEEP + 8 MELON`. The full
white-box suite passes 48/48 and the changed modules compile. No gameplay
evidence had been collected at that checkpoint; the rejection below controls.

On the actual seed-18700 initial simulator observation, V60's certificate saw
the fixed eight-WHEAT product buy and the computed $12 reserve, proposed
`1 COW + 1 SHEEP + 8 MELON`, paid $1,540 upfront, and produced a 30-point cash
path with $296 minimum and $16,117 final cash under its stated book. Peak daily
requirements were 10 workers, two WHEAT feed units and 50 rollover output
units. The route master emitted the same asset quantities plus one current HIRE;
V59 on that observation emitted `4 COW + 10 STRAWBERRY + 2 MELON` plus two
HIREs, confirming that the mechanism fires and is not a fixed-target alias.

A complete seed-18700 simulator episode versus
`kaggriculture-multi-route-farming-agent` finished at $35,909 / $138,610. Its
719 V60 calls measured 7.789 ms mean, 21.408 ms P95, 63.836 ms P99 and 90.803
ms maximum, with zero calls at or above 170 ms (5.805 seconds wall). No runtime
or engine error occurred. The daily MPC cadence has ample headroom under the
180 ms soft deadline in this trace.

The valid hard-pool CRN rejection screen is
`logs/arena/v60_vs_v59_quick_18800.json` (simulator, seed0 18800, 1.2 minutes,
both six-seed mirrors exact, zero errors/not-done):

| screen | cells | V60 absolute paired margin | V59 absolute paired margin | V60-V59 | firing |
|---|---:|---:|---:|---:|---:|
| self-play | 6 seeds | head-to-head -$366,036 total; 1-5 | n/a | -$61,006/seed, SE $15,508, t=-3.93 | 6/6 |
| hard external pool | 18 | -$205,375.61 mean; 0 wins | -$107,401.83 mean; 0 wins | -$97,973.78 mean, SE $11,563.79, t=-8.47 | 18/18 |

Every pool cell regressed (0-18); per-opponent mean deltas were -$124,722.83,
-$75,438.33 and -$93,760.17. This is a decisive rejection, not an underpowered
neutral: do not run the 108/288/real promotion gates and do not promote V60.
The certificate equations and log remain as a tombstone. Diagnose the gap
between certified and executed daily service/capital before attempting another
portfolio generator; do not tune asset multipliers against this loss.

A seed-18800 action/state trace found the causal interface failure. V59 bought
capital on days 0, 4-7, 9-10 and 12-16, reached 60 live crops on day 14 and
still held 26 on day 29; its bank was $68,348. V60 recomputed purchases daily,
including eleven WHEAT seed on every day 18-26, but the strategy/task layer
still followed the old fixed crop plan rather than the certificate. Live crops
fell from 17 on day 8 to zero by day 24 while seed kept being purchased; V60
banked $32,279 and let the opponent bank $158,097. The certificate proved an
existential schedule but its quantities were passed only to the market/route
selection layer, not adopted as future PLANT/PLACE targets. This invalidates
the execution premise behind V60's cash path and explains the field-wide loss.

The next principled formulation is not a quantity adjustment. It must (a) make
currently observable seed and animal inventory the exact execution targets of
the task layer and (b) reserve those already-purchased assets from the next
daily certificate. This closes the certificate-to-runtime commitment using
only current private observation; it requires no remembered plan or fitted
coefficient.

### V61 certificate execution bridge (2026-08-28)

`whitebox/versions/v61_cashflow_execute.py` keeps the V60 certificate but adds
two missing commitments, isolated behind `capital_variant="cashflow_execute"`
and `plan_variant="inventory_execution"`:

1. observable live crops plus private seed inventory become exact per-crop task
   targets, and observable live/shed/carried animals become exact placement and
   service targets; the crop mix contains exactly those target types;
2. pending seed and animal inventory reserve physical slots from the next daily
   certificate, so bought capital cannot be proposed again while awaiting
   execution.

The feed target and one-day cash reserve are recomputed from that exact
observable herd. No plan is remembered across turns and no inferred hidden
state is used. V60 retains its recorded behavior through the old branch. Two
additional tests prove pending inventory consumes slots and the execution plan
adopts every observed seed/animal asset. The full white-box suite passes 50/50,
changed modules compile, and the prohibited import audit remains empty.

On the seed-18800 trace used to diagnose V60, V61 kept pending seed near zero,
reached 33 live crops, and still held crops through day 29. Its own bank rose
from V60's $32,279 to $56,239, proving that the execution bridge is live and
mechanically useful. It bought/placed a visible 1 COW, 3 GOOSE and 4 SHEEP and
planted the generated MELON/STRAWBERRY/TOMATO/WHEAT cohorts rather than leaving
seed uncommitted. The opponent bank nevertheless rose from $158,097 to
$165,370; V59 on the same diagnostic seed banked $68,348 against $133,180.
Thus closing execution does not yet close the paired-margin objective gap.

The same V61 episode measured 719 decisions at 16.036 ms mean, 49.617 ms P95,
71.565 ms P99 and 108.062 ms maximum, with zero calls at or above 170 ms
(11.749 seconds wall). Runtime is safe in this trace. The formal CRN rejection
below controls; V61 is not promoted.

The valid V61-versus-V59 hard-pool CRN rejection screen is
`logs/arena/v61_vs_v59_quick_18900.json` (simulator, seed0 18900, 1.8 minutes,
both six-seed mirrors exact, zero errors/not-done):

| screen | cells | V61 absolute paired margin | V59 absolute paired margin | V61-V59 | firing |
|---|---:|---:|---:|---:|---:|
| self-play | 6 seeds | head-to-head -$336,059 total; 0-6 | n/a | -$56,009.83/seed, SE $12,684.26, t=-4.42 | 6/6 |
| hard external pool | 18 | -$183,810.28 mean; 0 wins | -$131,555.39 mean; 0 wins | -$52,254.89 mean, SE $13,017.04, t=-4.01 | 18/18 |

The pool W-L was 3-15 and per-opponent mean deltas were -$91,375.67,
-$22,151.50 and -$43,237.50. V61 recovered about half of V60's -$97,974
pool regression, which supports the execution diagnosis, but remains a clear
field-wide loss. Do not run 108/288/real promotion gates and do not promote
V61.

Retain V60/V61 as executable tombstones behind isolated variant switches; the
V56-V59 paths and imports remain unchanged. The next formulation must replace
V60's intentionally sufficient but extremely conservative `max_distance`
independent-round-trip labour book with a constructive shared open-route
schedule over actual candidate positions, then value volume against a
state-derived opponent sale interval/both seat orders. The measured shape is
not evidence for an asset multiplier: V61 proves cash and executes inventory,
but peaks around 33 live crops where V59 reaches 60, so it cannot create the
shared-price suppression needed for paired margin. Own final cash must remain
a feasibility state, not the portfolio objective.

### V62 positioned shared-route certificate (implementation checkpoint, 2026-08-28)

`whitebox/versions/v62_cashflow_shared.py` is an isolated V61-based arm behind
`capital_variant="cashflow_shared"`. V60 and V61 retain their recorded
independent-round-trip semantics. V62 replaces only the certificate's labour
book: every proposed crop/animal unit is assigned to one concrete eligible
slot in the same nearest-slot and animal-cost-first order used by the default
capital-column path, and every service day is expanded into positioned
`(tile, operation_count)` stops.

The deterministic constructive schedule orders those public positions by
nearest-next Manhattan distance from the public shed geometry and splits the
sweep into closed worker segments. For an ordered segment `R`, the exact
certificate action count is

```
C(R) = max_{s in four shed tiles} dist(s, first(R))
     + sum_{adjacent stops} dist(position_i, position_{i+1})
     + sum_{stops} engine_operations(stop)
     + min_{s in four shed tiles} dist(last(R), s)
     + 1 DROP
```

Every segment must satisfy `C(R) <= 23`: a hand hired by the hour-0 market
phase first acts at hour 1 and therefore has exactly 23 actions. The route
returns to a shed tile and explicitly drops, so the shed-start premise is
preserved across modelled days. This is a sufficient executable geometry
certificate, not a distance multiplier or fitted throughput coefficient.
Daily feed, crew cost, bridge cash, grouped nonlinear sales, shed capacity,
market-order slots and exact shared land activation remain the V60 equations.

Three new equation tests prove that nearby units share shed travel, all stops
and operations are covered exactly once by individually feasible closed
segments, and a mixed crop/animal certificate uses only unique concrete
candidate positions. The full white-box suite passes 53/53, changed modules
compile, and `git diff --check` is clean. Gameplay and runtime evidence had
not yet been collected at this checkpoint; no promotion claim follows from
the implementation. The greedy arm still ranks feasible bundles by nominal
own final cash, so even a mechanically successful labour repair remains
unpromoted until opponent-relative interval value and post-trim
recertification are supplied.

The first unoptimised seed-19000 simulator probe was runtime-unsafe: 719 V62
decisions measured 21.344 ms mean, 58.037 ms P95, 336.960 ms P99 and 675.172
ms maximum, with 12 calls at or above 170 ms. It was not gated. Profiling
showed the greedy count trials repeatedly sorting identical daily geometry and
walking identical marginal price curves. V62 now memoizes only exact pure
equations `(positioned stops -> closed routes)`, `(item, quantity, inventory ->
sale result)` and WHEAT buy cost, and updates an appended route's action count
algebraically. No deadline, candidate ordering or economic value changed; V60
and V61 retain the uncached historical branch.

Repeating the complete seed-19000 episode after that exact optimisation versus
`kaggriculture-multi-route-farming-agent` finished at $58,631 / $144,319 in
12.06 seconds. Its 719 calls measured 16.472 ms mean, 48.130 ms P95, 104.769
ms P99 and 152.587 ms maximum, with zero calls at or above 170 ms. This single
trace clears the runtime screen but is not gameplay evidence. On its initial
observation, the raw positioned certificate expanded V61's
`1 COW + 1 SHEEP + 8 MELON` (peak 10 certified workers) to
`1 COW + 2 SHEEP + 16 MELON + 3 WHEAT` (peak 6 workers); after runtime-safe
completion of the current route master, V62 emitted that full quantity plus
three HIREs. The production import audit returned `FORBIDDEN_IMPORTED []`,
and two fresh loads returned identical initial actions.

The formal V62-versus-immutable-V59 rejection screen is
`logs/arena/v62_vs_v59_quick_19000.json` (simulator, seed0 19000, 1.9 minutes,
zero episode errors and zero not-DONE statuses). The V59 identity control was
exact on 6/6 seeds, but V62's own mirror was nonzero on 1/6 seeds with a
+$16,953 paired total. Parallel fresh-process contention therefore still lets
the shared certificate consume enough of the agent's wall-clock budget to
change an anytime route-master branch. This invalidates the candidate's paired
numbers and violates the deterministic promotion gate even though the isolated
single-episode trace was below 170 ms.

The invalid-but-directionally-useful rejection statistics were:

| screen | cells | V62 absolute paired margin | V59 absolute paired margin | V62-V59 | firing |
|---|---:|---:|---:|---:|---:|
| self-play | 6 seeds | head-to-head -$252,558 total; 0-6 | n/a | -$42,093/seed, SE $9,420, t=-4.47 | 6/6 |
| hard external pool | 18 | -$161,141.72 mean; 0 wins | -$130,495.33 mean; 0 wins | -$30,646.39 mean, SE $11,695.43, t=-2.62 | 18/18 |

Pool W-L was 6-12. Per-opponent mean deltas were -$54,167.17,
-$16,192.33 and -$21,579.67 in hard-pool order. V62 recovers part of V61's
recorded -$52,254.89 mean regression, consistent with shared routing removing
some artificial labour scarcity, but it remains a field-wide loss and its own
mirror is invalid. Do not run the 108/288/real gates and do not promote V62.
Retain the isolated wrapper, equations, tests and log as a tombstone; V56-V59
remain unchanged. The next principled arm must make the portfolio construction
structurally bounded enough that wall-clock deadlines cannot select its output,
and must replace nominal own-final-cash ranking with the explicit both-seat
opponent-relative sale interval before increasing volume again. Do not tune an
asset-count or value multiplier from this loss.

### V63 bounded paired-market certificate (implementation checkpoint, 2026-08-28)

`whitebox/versions/v63_cashflow_paired.py` is an isolated V62-descended arm
behind `capital_variant="cashflow_paired"`. It addresses both causes recorded
after V62 rather than changing an asset multiplier.

First, `market_model.town_take_bounds` conditions on the exact currently
observable shop multiset and enumerates the minimum/maximum contribution of
each still-hidden future shop over the finite engine shop set. Current shops
and the town centre enter both endpoints exactly; there is no fixed seed,
sample average or learned coefficient. Cash feasibility retains V62's more
conservative no-town-drain book.

Second, the portfolio objective is separated from own final cash. For candidate
sale quantity `q`, public visible opponent upper quantity `u`, inventory `I`
and every integer `o in [0,u]`, V63 evaluates the incremental final-money
margin in both engine seat orders:

```
first(o)  = R(q,I) + R(o,I) - R(o, inventory_after(q,I))
second(o) = R(q, inventory_after(o,I))
paired(q) = min_{o=0..u} 0.5 * (first(o) + second(o))
```

`R` and every closing inventory are the exact unit-by-unit engine curve. The
factor one half is the two equally represented seat orders in an arena paired
cell, not a fitted risk weight. Opponent `u` contains only output derivable
from currently visible crops/animals under full service; hidden intent and
future purchases are not guessed. Guaranteed town drain is applied between
modelled sale days, while uncertain future-shop drain is excluded from the
robust lower endpoint.

The constructor is structurally bounded. It evaluates every legal singleton
once, fixes that equation-derived ordering, then extends each item ray only
while the exact paired objective improves. It solves at most
`1 + item_types + physical_slots + item_types` nonempty certificates per land
arm and never consults wall time. This is an explicit deterministic primal
heuristic, not an exact integer optimiser. After the current route master trims
the proposal, the actual selected quantities and actual selected tile set are
recertified through the same multi-day paired equation, including exact shared
land activation, instead of inheriting the full proposal's score.

V63 also selects an isolated deterministic daily-route primal: initial
route-aware insertion is retained, while deadline-sensitive relocation/prize
exchange passes and Held-Karp/heuristic switching are disabled in favour of
deterministic nearest-neighbour plus 2-opt. Historical wrappers retain the
refined route path. This is required because V62 proved that a wall-clock
branch is not a legal source of action variation under parallel load.

Six new equation tests cover analytical town intervals, exact public-shop
conditioning, robust both-seat quantity enumeration, visible-output scheduling,
the constructor solve bound and selected-quantity recertification. The complete
white-box suite passes 59/59 and changed modules compile. On the seed-19100
initial observation the raw arm proposed
`3 COW + 1 SHEEP + 5 MELON + 15 WHEAT`, used 39 certificate evaluations and
seven peak certified workers; its paired value was $16,699 versus $16,457 own
final certificate cash. The route master retained the full quantity with three
current HIREs.

The first complete seed-19100 trace before deterministic route isolation was
runtime-unsafe: P99 165.888 ms, maximum 180.295 ms and eight calls at or above
170 ms. After the isolated primal change, the same complete episode versus
`kaggriculture-multi-route-farming-agent` finished at $57,374 / $143,725 in
18.64 seconds. Its 719 calls measured 25.601 ms mean, 93.106 ms P95, 125.898
ms P99 and 155.835 ms maximum, with zero calls at or above 170 ms; the final
farm retained 16 crops and nine animals. This clears one local runtime trace,
not the parallel determinism or gameplay gates. No promotion claim is made at
this checkpoint.

The valid V63-versus-immutable-V59 quick rejection screen is
`logs/arena/v63_vs_v59_quick_19100.json` (simulator, seed0 19100, 2.0 minutes,
zero episode errors and zero not-DONE statuses). Both the V59 identity control
and V63's own mirror were exactly zero on 6/6 seeds. Thus the structurally
bounded constructor plus deterministic route primal repairs V62's parallel
action nondeterminism; the paired gameplay evidence is valid.

| screen | cells | V63 absolute paired margin | V59 absolute paired margin | V63-V59 | firing |
|---|---:|---:|---:|---:|---:|
| self-play | 6 seeds | head-to-head +$17,828 total; 4-2 | n/a | +$2,971/seed, SE $3,414, t=0.87 | 6/6 |
| hard external pool | 18 | -$126,832.50 mean; 0 wins | -$113,470.44 mean; 0 wins | -$13,362.06 mean, SE $7,430.15, t=-1.80 | 18/18 |

The hard-pool paired-delta W-L was 4-14. Per-opponent mean deltas were
-$32,110.33, -$3,661.00 and -$4,314.83 in hard-pool order. V63 is materially
less negative than V62's invalid -$30,646 and V61's -$52,255, while its
head-to-head result changes sign, but the external field is the decision and
`arena.py` correctly reports REGRESSION. Do not run the 108/288/real gates and
do not promote V63.

Retain V63's analytic shop interval, paired-sale equation, solve bound,
selected-quantity recertificate and deterministic route option as isolated
white-box mechanisms with this negative log. The result rejects their current
composition and visible-output uncertainty set, not the exact equations
individually. The largest remaining semantic gap is that the opponent interval
contains public standing production but not a conservation bound on hidden
stock accumulated from previously public harvests, while the bounded fixed-ray
primal can also lock into an early item ordering. The next arm should improve
that public-state stock conservation/portfolio optimisation formulation; do
not tune the 3-COW/1-SHEEP/5-MELON/15-WHEAT output from this six-seed loss.

### V64 exact exchange-line portfolio correction (implementation checkpoint, 2026-08-28)

`whitebox/versions/v64_cashflow_exchange.py` is an isolated V63 descendant
behind `capital_variant="cashflow_exchange"`. A per-item hidden-stock upper
was deliberately not added: after a harvested crop disappears, the current
observation cannot attribute the opponent's aggregate 100-item private shed
capacity by product, and assigning 100 independently to every item would reuse
the same physical capacity. That is not a valid conservation interval under
the strict current-observation contract.

V64 instead repairs V63's other recorded defect, fixed singleton-ray lock-in.
After V63 constructs its feasible bundle, V64 evaluates every legal one-unit
`remove item -> add item` exchange through the complete positioned multi-day
cash/labour/shed and paired-market certificate. It chooses the steepest
positive direction, then evaluates every integer quantity on that one exchange
line and returns its best feasible point. The deterministic work bound is

```
direction certificates <= item_types * (item_types - 1)
line certificates      <= quantity of the removed item <= physical slots
```

There is no iteration-until-time condition, fitted coefficient, count target or
opponent identity. This is an exact line search inside one finite exchange
neighbourhood, not a claim of global portfolio optimality. The current route
master still recertifies the actually retained quantities through V63's paired
equation.

One new equation test proves exchange search never reduces paired value and
respects the structural solve bound. The complete suite passes 60/60, changed
modules compile and the prohibited import audit is empty. On the seed-19200
initial observation, the steepest direction is `WHEAT -> MELON`; exact line
search replaces five units. The portfolio changes from
`3 COW + 1 SHEEP + 5 MELON + 15 WHEAT` to
`3 COW + 1 SHEEP + 10 MELON + 10 WHEAT`, raising certified paired value from
$16,699 to $22,562 and own certificate cash from $16,457 to $22,054 after 42
exchange evaluations. The current route master emits the full bundle with four
HIREs.

A complete seed-19200 simulator episode versus
`kaggriculture-multi-route-farming-agent` finished at $61,756 / $117,532 in
12.26 seconds. Its 719 decisions measured 16.745 ms mean, 46.709 ms P95,
69.961 ms P99 and 126.053 ms maximum, with zero calls at or above 170 ms. The
final farm had 15 animals and no standing crops. This clears one local runtime
trace but is not gameplay or parallel-determinism evidence; no promotion claim
is made at this checkpoint.

The first parallel V64 screen,
`logs/arena/v64_vs_v59_quick_19200.json`, is invalid: V59's identity control
was exact but V64's own mirror was nonzero on 1/6 seeds with +$13,674 paired
total. The deterministic exchange work left the downstream hour-0 capital
master close enough to its wall-clock cutoff that the cutoff selected an
action under 26-worker contention. There were zero episode errors and zero
not-DONE statuses. The inherited but invalid statistics were self-play
+$53,853 total (5-1, +$8,975.50/seed, SE $3,655.42, t=2.46) and hard-pool
candidate absolute -$131,661.72 versus V59 -$123,336.44, delta -$8,325.28
(SE $7,251.07, t=-1.15, W-L 7-11, firing 18/18). Per-opponent deltas were
-$3,708, -$6,463 and -$14,805. Do not use these numbers for a decision.

The bounded exchange itself has no time branch. The repair under test removes
the wall-clock cutoff only from V64's hour-0 capital master: that solve is
already finitely bounded by seven hire counts, physical tasks, exact cash and
ten order slots. Other variants and every non-hour-0 call retain the 180 ms
guard. This repair must pass a new parallel mirror and runtime probe before any
gameplay number is considered valid.

The bounded-master repair passes the complete 60/60 white-box suite, changed
modules compile and `git diff --check` is clean. A fresh complete seed-19300
simulator trace versus `kaggriculture-multi-route-farming-agent` finished at
$78,978 / $161,041 in 15.63 seconds. Across 719 V64 decisions it measured
21.429 ms mean, 71.245 ms P95, 100.284 ms P99 and 165.861 ms maximum, with
zero calls at or above 170 ms and zero at or above the engine's 1 second
timeout. This is a second single-process runtime trace, not a gameplay gate.

The repaired quick CRN screen is
`logs/arena/v64_vs_v59_quick_19300_bounded_master.json` (simulator, seed0
19300, 1.9 minutes, 26 workers). V59's identity control and V64's own mirror
are both exactly zero on 6/6 seeds, with zero episode errors and zero not-DONE
statuses, so unlike the seed-19200 screen this evidence is valid.

| screen | cells | V64 absolute paired margin | V59 absolute paired margin | V64-V59 | firing |
|---|---:|---:|---:|---:|---:|
| self-play | 6 seeds | head-to-head -$11,701 total; 1-5 | n/a | -$1,950.17/seed, SE $6,857.16, t=-0.28 | 6/6 |
| hard external pool | 18 | -$106,212.94 mean; 0 wins | -$123,029.11 mean; 0 wins | +$16,816.17 mean, SE $10,485.17, t=1.60 | 18/18 |

The hard-pool paired-delta W-L is 13-5. Per-opponent mean deltas are
-$17,888.83, +$32,274.83 and +$36,062.50 in hard-pool order. The opposite
directions in self-play and the first external opponent, plus only 18 paired
pool cells, make this an encouraging but underpowered quick result. It cannot
promote V64. Because quick screens are rejection-only and this one is not an
obvious regression, advance the unchanged arm to the immutable-V59 108-cell
standard simulator gate before considering any larger or real-engine gate.

The first standard attempt,
`logs/arena/v64_vs_v59_standard108_19400.json`, is invalid and must not be used
as gameplay evidence. It ran seed0 19400, 18 seeds over the six-opponent
standard pool and 26 workers for 6.8 minutes with zero pool episode errors and
zero not-DONE statuses. V64's mirror was exactly zero on 18/18 seeds, but
immutable V59's identity control was nonzero on 1/18 seeds by +$959, so the
arena correctly aborted the entire result. The aborted aggregates happened to
be self-play +$6,858.94/seed and standard-pool +$1,608.58/cell (SE $4,158.47,
t=0.39, W-L 42-66, firing 108/108), but none of those numbers is evidence.

Do not change V59 or V64 in response. This is the same historical-baseline
wall-clock sensitivity that the mandatory identity control is designed to
catch. Calibrate reduced parallelism with an immutable-V59 null run on the same
seed block; only after that control is exact may an unchanged V64 standard gate
be rerun at the proven worker count. Preserve this aborted log as the
contention tombstone.

The reduced-concurrency calibration is
`logs/arena/v59_identity_19400_workers12.json`: immutable V59 versus itself,
the same 18 seeds starting at 19400, no pool, 12 workers, 1.2 minutes. Its
identity control is exactly zero on 18/18 paired seeds. This establishes 12 as
the concurrency ceiling for the standard retry on this machine/load; it is a
harness-control result and says nothing about V64 gameplay.

The first 12-worker standard retry completed its 540 simulator episodes in
12.6 minutes with both mirrors exact and printed zero episode failures, but the
arena reporter then raised `ValueError` before writing the requested JSON. The
cause was two verdict-only old-style format strings using the unsupported
`%+,.0f` comma flag. The intended path
`logs/arena/v64_vs_v59_standard108_19400_workers12.json` was therefore not
created and the printed gameplay aggregates are not treated as durable gate
evidence. `arena.py` now formats those two notes with Python's valid
`"{:+,.0f}".format(...)`; no scheduling, episode, metric or verdict criterion
changed. Compile the harness and rerun the identical 12-worker gate to obtain a
complete JSON. This harness fix is independent of all model versions.

The complete valid standard gate is
`logs/arena/v64_vs_v59_standard108_19400_workers12_retry.json` (simulator,
seed0 19400, 18 seeds, six-opponent standard pool, 12 workers, 12.5 minutes).
Both immutable-V59 identity and V64 mirror controls are exactly zero on 18/18
seeds. There are zero episode errors and zero not-DONE statuses.

| screen | cells | V64 absolute paired margin | V59 absolute paired margin | V64-V59 | firing |
|---|---:|---:|---:|---:|---:|
| self-play | 18 seeds | head-to-head +$124,283 total; 11-7 | n/a | +$6,904.61/seed, SE $6,168.69, t=1.12 | 18/18 |
| standard external pool | 108 | -$112,119.25 mean; 0 wins | -$113,704.43 mean; 0 wins | +$1,585.18 mean, SE $4,158.53, t=0.38 | 108/108 |

The external paired-delta W-L is 41-67 (38.0%, win-rate t=-2.50), despite the
small positive blowout-sensitive mean. Per-opponent mean deltas in standard
pool order are +$3,681.89, +$5,627.44, +$2,317.78, -$1,530.00, +$9,311.89
and -$9,897.94. Corresponding V64/V59 absolute paired means are
-$109,819.61/-$113,501.50, -$113,623.83/-$119,251.28,
-$115,519.22/-$117,837.00, -$118,239.83/-$116,709.83,
-$107,494.39/-$116,806.28 and -$108,018.61/-$98,120.67.

This is a valid `REGRESSION` under the established paired win-probability rule:
V64 wins its improving cells by more but loses materially more cells. Do not
promote V64 and do not run its 288-cell or real-engine gates. Retain the exact
exchange-line mechanism, unit test, wrapper and logs as a tombstone; V59
remains the immutable selected baseline. The result rejects one steepest
one-exchange portfolio correction as a robust policy, not the underlying exact
bundle-clearing or paired-sale equations. A next arm should not tune the
WHEAT/MELON exchange from these outcomes. The remaining principled frontier is
a genuinely joint portfolio/cash-route optimiser (or a valid aggregate hidden
stock allocation uncertainty set), with the latter requiring one conserved
shed-capacity budget rather than independently assigning 100 hidden units to
every product.

Final post-gate verification on 2026-08-28 reran the complete 60/60 white-box
suite, compiled `whitebox/` and `arena.py`, and passed `git diff --check`. A
fresh seed-19500 V64 initial decision imported only `whitebox.agent`,
`capital`, `cashflow`, `econ`, `hiring`, `horizon`, `market`, `market_model`,
`opponent_model`, `paths`, `state`, `strategy`, `tasks` and `value` (plus the
version/package modules): the prohibited replay/tape/opening/weight/schedule/
search/mining audit is empty. In a separate fresh process immutable V59 still
does not import `whitebox.cashflow`, preserving its recorded semantics. The
repository is executable; no existing dirty or unrelated user file was reset,
removed or overwritten.

### V65 state-derived terminal sweep certificate (implementation checkpoint, 2026-08-28)

`whitebox/versions/v65_terminal_certificate.py` is an isolated V59 descendant.
It replaces V59's fixed eight-step terminal takeover only inside this wrapper;
V59-V64 retain their recorded semantics. The arm enters terminal mode only
when a live constructive certificate succeeds. Eligibility and feasibility are
derived from engine equations rather than a chosen window:

```
next_refresh_action = (current_day + 1) * turns_per_day - 1
production_closed   = next_refresh_action > last_engine_action
trip_actions        = distance(start, target) + HARVEST
                      + distance(target, nearest_shed) + DROP
max_worker_trip_actions <= last_engine_action - current_step + 1
current_shed + all currently carried drops <= shedCapacity
```

The certificate also rejects while a legal WATER on a harvestable one-time
crop can still create immediate output; such production does not require an
end-of-day refresh. Every currently ripe crop/animal target is claimed once by
a deterministic earliest-completion worker route. Harder shed-distance trips
enter first, every route is explicitly closed at a concrete shed tile, crop
decay before its proposed HARVEST is excluded, and current carried-delivery
legs consume the same remaining-action budget. This is a constructive feasible
primal, not a shortest-tour claim. If the complete residual sweep is not
certified, V65 continues through the ordinary V59 planner rather than using the
fixed collector.

When certified, V65 sells exactly current shed stock plus inventories whose
DROP executes before the market phase. All products share the engine's ten
order slots and 100-item shed. Its diagnostic terminal value uses the exact
both-seat sale equation against an upper relaxation of currently visible ripe
opponent output whose individual target-to-shed trip fits the remaining
actions. It deliberately does not invent an independent hidden-shed allowance
per product; the aggregate hidden-stock allocation remains unresolved and this
visible interval is not claimed to cover private holdings.

Seven new equation tests cover the last-refresh boundary, immediate one-time
crop production, unique joint target claims, residual-sweep rejection, carried
delivery time, shared drop capacity and same-turn sale aggregation. The full
white-box suite passes 67/67 and changed modules compile.

The first instrumented seed-19600 episode found and rejected an implementation
error before gameplay evaluation: the certificate initially checked newly
assigned target trips but not a unit's already-carried shed leg, so it reported
feasible at steps 716-718 even when `max_route_actions > remaining_actions` and
left three four-unit STRAWBERRY inventories stranded. No arena log was produced
and that trace is not gameplay evidence. The carried-delivery inequality and a
focused regression test now close the hole.

In the corrected repeat versus `kaggriculture-multi-route-farming-agent`, V65
finished at $39,264 / $110,759 in 11.23 seconds. Its 719 calls measured 15.322
ms mean, 66.662 ms P95, 110.136 ms P99 and 138.332 ms maximum, with zero calls
at or above 170 ms. The certificate correctly rejected future refreshes through
step 695, rejected the full residual sweep at steps 696-711, then rejected
carried deliveries that could not finish at steps 712-718. It never activated
on this trace; the ordinary planner still ended with three carried
four-STRAWBERRY inventories and an empty shed. This is a runtime and
feasibility diagnostic, not paired gameplay evidence. The immediate risk is
that removing the fixed collector may strand stock whenever the stronger
all-residual-target certificate cannot fire; run only a quick CRN rejection
screen before considering broader gates.

The valid V65-versus-immutable-V59 quick rejection screen is
`logs/arena/v65_vs_v59_quick_19700.json` (simulator, seed0 19700, 26 workers,
1.6 minutes). Both V59's identity control and V65's own mirror are exactly zero
on 6/6 seeds, with zero episode errors and zero not-DONE statuses.

| screen | cells | V65 absolute paired margin | V59 absolute paired margin | V65-V59 | firing |
|---|---:|---:|---:|---:|---:|
| self-play | 6 seeds | head-to-head -$8,587 total; 3-3 | n/a | -$1,431.17/seed, SE $1,109.20, t=-1.29 | 6/6 |
| hard external pool | 18 | -$122,980.06 mean; 0 wins | -$122,359.94 mean; 0 wins | -$620.11 mean, SE $362.75, t=-1.71 | 18/18 |

The hard-pool paired-delta W-L is 7-11. All three opponent means are negative:
-$142.33, -$446.17 and -$1,271.83 in hard-pool order. Corresponding V65/V59
absolute paired means are -$113,784.17/-$113,641.83,
-$128,405.50/-$127,959.33 and -$126,750.50/-$125,478.67. Although the harness
labels 18 cells statistically neutral, quick screens are rejection-only and
the consistent negative mechanism evidence plus the seed-19600 stranded-stock
trace reject this formulation. Do not run V65's 108/288/real gates and do not
promote it.

Retain V65's production-closure equation, immediate-WATER guard, exact carried
delivery inequality, joint capacity tests and log as a tombstone. The failed
assumption is requiring every residual target to fit before taking any
terminal action: profitable partial collection is sacrificed whenever one far
target makes the all-or-nothing certificate fail. The next principled terminal
arm may select a feasible partial residual set only if it aggregates repeated
product quantities through the exact nonlinear both-seat sale equation, leaves
hour 0 to the ordinary hire master, and has no fixed takeover step or fitted
value/distance coefficient.

### V66 nonlinear partial terminal primal (implementation checkpoint, 2026-08-28)

`whitebox/versions/v66_terminal_partial.py` is an isolated V59 descendant that
keeps V65's engine-derived production closure and feasibility equations but
removes the failed all-residual requirement. Final-day hour 0 is explicitly
left to V59's ordinary capital/hire master because hands bought in that market
phase first act at hour 1. From hour 1 onward, the bounded primal repeatedly
tests every reachable unclaimed target on every worker route and selects the
one with the largest positive increment in the exact aggregate both-seat sale
value:

```
gain(target) = paired_value(outputs + target_units,
                            visible_opponent_interval)
               - paired_value(outputs, visible_opponent_interval)
```

There is no per-task additive sale value, value/distance ratio, takeover step,
target count or fitted coefficient. Repeated units of one product are repriced
together through the engine's unit-by-unit market curve. Route completion cost,
then public position/item/unit index, only break exact economic ties. Every
accepted route remains closed by HARVEST, return-to-shed and DROP within the
remaining action budget. The result is a deterministic feasible primal, not a
global prize-collecting optimum.

Two new tests prove hour-0 hire deferral and that V66 keeps a reachable positive
subset when V65 correctly rejects the complete residual sweep. The full suite
passes 69/69 and changed modules compile.

On the corrected seed-19600 trace versus
`kaggriculture-multi-route-farming-agent`, V66 finished at $38,757 / $110,759
in 10.96 seconds. Its 719 calls measured 14.941 ms mean, 66.714 ms P95,
109.529 ms P99 and 137.153 ms maximum, with zero calls at or above 170 ms.
The certificate rejected future refresh through step 695 and the hour-0 hire
phase at 696, then fired at every step 697-718. At first activation it selected
14 targets with a longest 22-action closed route in exactly 22 remaining
actions. Final private hand inventories and shed were empty, while seven
standing yield units remained. This is mechanically feasible and runtime-safe,
but V66's own bank was $507 below V65's same-seed $39,264 diagnostic; neither
single-seat number is gameplay evidence. Run a fresh quick paired gate before
any larger evaluation.

The valid V66-versus-immutable-V59 quick rejection screen is
`logs/arena/v66_vs_v59_quick_19800.json` (simulator, seed0 19800, 26 workers,
1.5 minutes). V59's identity control and V66's own mirror are exactly zero on
6/6 seeds, with zero episode errors and zero not-DONE statuses.

| screen | cells | V66 absolute paired margin | V59 absolute paired margin | V66-V59 | firing |
|---|---:|---:|---:|---:|---:|
| self-play | 6 seeds | head-to-head -$5,618 total; 2-4 | n/a | -$936.33/seed, SE $662.87, t=-1.41 | 6/6 |
| hard external pool | 18 | -$113,645.56 mean; 0 wins | -$113,195.50 mean; 0 wins | -$450.06 mean, SE $235.90, t=-1.91 | 18/18 |

The paired-delta W-L is 7-11. Every hard-opponent mean is negative:
-$1,105.17, -$167.83 and -$77.17. Corresponding V66/V59 absolute paired means
are -$101,598.83/-$100,493.67, -$119,111.33/-$118,943.50 and
-$120,226.50/-$120,149.33. The harness calls 18 cells statistically neutral,
but this is again a rejection-only quick screen: both self-play and every pool
opponent move negative, and the external t statistic is -1.91. Do not run
V66's 108/288/real gates and do not promote it.

V66 proves that biological production closure alone is not the state condition
for replacing the general route master. Even with nonlinear bundle pricing,
hour-0 hiring preserved, exact mirrors, empty terminal inventories and closed
feasible trips, taking over from step 697 sacrifices more valuable routing than
it recovers. Retain the wrapper, equations, nine terminal tests, runtime trace
and log as a tombstone. A future terminal arm must compare a terminal route
column against the live general route master's executable objective and switch
only on a positive exact opportunity-cost difference; it must not infer route
dominance merely from the absence of another daily refresh, and it must not
reintroduce a fitted takeover window.

Final post-V66 verification on 2026-08-28 reran the complete 69/69 white-box
suite, compiled `whitebox/` and `arena.py`, and passed `git diff --check`. A
fresh terminal-state V66 certificate call exercised the late dynamic import of
`whitebox.cashflow`; the replay/tape/opening/weight/schedule/search/mining audit
remained empty. In a separate fresh process immutable V59 imported neither
`whitebox.terminal` nor `whitebox.cashflow`. V59 remains the selected baseline,
V65 and V66 remain isolated negative experiments, and no user or unrelated
dirty worktree content was reset, removed or overwritten.

### V67-V69 terminal opportunity and execution closure (2026-08-28)

V67 (`whitebox/versions/v67_terminal_opportunity.py`) implements the next
constraint left by V66: compare the complete terminal primal against the live
ordinary route master instead of inferring dominance from biological closure.
For each worker, `terminal.general_route_upper` walks the cached live stop order
from the current public position, charges missing-input pickup, remaining tile
operations and the shed-return/DROP tail, aggregates HARVEST and
COLLECT_FERTILIZER quantities by product, and reprices the joint quantity on
the same exact both-seat curve. Required inputs are optimistically available
and their costs are omitted, so this is deliberately an upper bound on general
terminal output value. A terminal switch is legal only under the strict proof

```
certified_terminal_paired_value > general_route_paired_value_upper_bound
```

with exact ties preserving general work. There is no tolerance, takeover step,
learned coefficient or cross-opponent feature. Two tests cover repeated-output
bundle repricing and strict tie behavior; the suite reached 71/71.

The seed-19600 diagnostic was safely inert: across steps 690-718 V67 made zero
terminal selections. At steps 697-711 its terminal value trailed the general
upper by only $2-$6, then carried-delivery infeasibility correctly blocked it.
It finished at $39,264 / $110,759, with 15.282 ms mean, 109.348 ms P99,
135.594 ms maximum and zero calls at or above 170 ms. Inspection found the
small value gap was an omitted engine output: the ordinary animal visit also
executes COLLECT_FERTILIZER, whereas V67's terminal target represented only
HARVEST. V67 is an incomplete comparator diagnostic and received no arena gate.

V68 (`whitebox/versions/v68_terminal_complete.py`) corrects that omission with
complete terminal tile bundles. An animal target contains HARVEST when ripe and
COLLECT_FERTILIZER when available; its route cost includes both operations and
its MILK/WOOL/EGG plus FERTILIZER outputs enter one nonlinear bundle. A focused
test proves the two-operation target and the suite reached 72/72. On seed 19600
V68 passed the strict opportunity proof at steps 697-701, but later returned to
the ordinary cached route as the live values crossed. It finished at
$38,874 / $110,759 with 15.256 ms mean, 110.041 ms P99, 136.493 ms maximum and
zero calls at or above 170 ms, but stranded sellable stock in three hands. A
multi-step certificate is not execution evidence if a later comparison may
abandon it; V68 therefore received no arena gate.

V69 (`whitebox/versions/v69_terminal_rescue.py`) closes that seam without
memory or hysteresis. On every current observation, each unit carrying
sellable stock compares the optimistic action cost of its complete live
general-route suffix plus DROP with the exact remaining engine actions. If the
suffix cannot finish but the direct shed leg can, only that unit's current
action is replaced by the shortest delivery action. Current same-turn DROPs
share actual shed room. A feasible general suffix is always preserved. Two
tests prove both sides of this inequality; the suite reached 74/74.

On seed 19600 V69 made seven strict terminal selections and 21 unit-level
delivery rescues, finishing at $38,855 / $110,759 in 11.14 seconds. Its 719
calls measured 15.195 ms mean, 66.003 ms P95, 109.709 ms P99 and 135.610 ms
maximum, with zero calls at or above 170 ms. Final shed and all eight unit
inventories were empty; eight standing yield units remained. This is the first
mechanically closed opportunity formulation and is eligible for a quick CRN
rejection screen, but its own bank is $409 below V67's same-seed no-switch
diagnostic and cannot support a gameplay claim.

The first seed-19900 quick attempt is
`logs/arena/v69_vs_v59_quick_19900.json` (simulator, 26 workers, 1.6 minutes),
and is **invalid**. V69's mirror was exactly zero, but immutable V59's identity
control was nonzero on 1/6 seed pairs and totaled -$7,576. The arena correctly
aborted. Its displayed V69/V59 self-play and pool aggregates are not evidence
and must not be used, even though they happen to match the later isolated run.

The leak was in the evaluation loader, not either model. `arena.load_agent`
gave each tiny version wrapper a unique module name but left its imported
`whitebox.*` implementation graph in `sys.modules`, so separate seats closed
over shared `_PLAN`, `_TRACKER` and market state. `arena.py` now removes the
candidate's local package tree before executing each file wrapper. Already
returned callables retain their independent module objects. This changes only
the local evaluator and never enters a production import/action path. A fresh
two-seed immutable-V59 null control,
`logs/arena/v59_null_loader_isolation_19900.json`, is exactly +$0 on both
pairs. It took 0.4 minutes with four workers and had no errors.

The exact seed block was then rerun without changing V69. The valid quick CRN
screen is `logs/arena/v69_vs_v59_quick_19900_isolated.json` (simulator, seed0
19900, 26 workers, 1.6 minutes). Both the V59 identity and V69 mirror controls
are exactly zero on all 6/6 pairs, with zero episode errors and zero not-DONE
statuses.

| screen | cells | V69 absolute paired margin | V59 absolute paired margin | V69-V59 | firing |
|---|---:|---:|---:|---:|---:|
| self-play | 6 seeds | head-to-head +$176 total; 4-2 | n/a | +$29.33/seed, SE $301.39, t=0.10 | 6/6 |
| hard external pool | 18 | -$111,205.39 mean; 0 wins | -$111,496.22 mean; 0 wins | +$290.83 mean, SE $119.80, t=2.43 | 18/18 |

The hard-pool paired-delta W-L is 15-3 (83.3%). Per-opponent mean deltas are
+$165.67, +$313.00 and +$393.83 in hard-pool order. Corresponding V69/V59
absolute paired means are -$107,823.83/-$107,989.50,
-$113,916.67/-$114,229.67 and -$111,875.67/-$112,269.50. This is encouraging
but only 18 independent external cells. Quick screens are rejection-only: do
not promote or claim improvement. Advance unchanged V69 to the existing
108-cell standard simulator gate against immutable V59; only a valid result
with exact mirrors may justify the 288-cell and both-seat real-engine gates.

The valid 108-cell standard gate is
`logs/arena/v69_vs_v59_standard108_20000_isolated.json` (simulator, seed0
20000, 18 seeds, six-opponent standard pool, 26 workers, 5.5 minutes). Both
immutable-V59 identity and V69 mirror controls are exactly zero on all 18/18
seed pairs. There are zero episode errors and zero not-DONE statuses.

| screen | cells | V69 absolute paired margin | V59 absolute paired margin | V69-V59 | firing |
|---|---:|---:|---:|---:|---:|
| self-play | 18 seeds | head-to-head +$8,392 total; 14-4 | n/a | +$466.22/seed, SE $129.05, t=3.61 | 18/18 |
| standard external pool | 108 | -$119,744.37 mean; 0 wins | -$120,108.46 mean; 0 wins | +$364.09 mean, SE $72.02, t=5.06 | 106/108 |

Conditional on firing, the external delta is +$370.96 (SE $73.17, t=5.07)
with W-L 79-27 and two inert ties, a 74.5% paired win probability. Per-opponent
mean deltas in standard-pool order are -$25.39, +$600.50, +$429.11, +$420.22,
+$425.56 and +$334.56. Corresponding V69/V59 absolute paired means are
-$114,408.78/-$114,383.39, -$121,354.56/-$121,955.06,
-$122,835.94/-$123,265.06, -$121,342.00/-$121,762.22,
-$126,194.72/-$126,620.28 and -$112,330.22/-$112,664.78.

This valid gate supports escalation but still does not support promotion. V69
is a major action-path change and must pass the prescribed 288 paired external
cells plus a both-seat, multi-seed real-engine gate. Keep V59 immutable and run
those gates on the unchanged V69 wrapper; do not tune the one near-zero
opponent result.

The required 288-cell confirmation is
`logs/arena/v69_vs_v59_standard288_20100_isolated.json` (simulator, seed0
20100, 48 seeds, six-opponent standard pool, 26 workers, 13.8 minutes). Both
V59 identity and V69 mirror controls are exactly zero on all 48/48 pairs, with
zero episode errors and zero not-DONE statuses.

| screen | cells | V69 absolute paired margin | V59 absolute paired margin | V69-V59 | firing |
|---|---:|---:|---:|---:|---:|
| self-play | 48 seeds | head-to-head +$14,542 total; 39-9 | n/a | +$302.96/seed, SE $163.89, t=1.85 | 48/48 |
| standard external pool | 288 | -$120,423.42 mean; 0 wins | -$120,657.45 mean; 0 wins | +$234.03 mean, SE $39.89, t=5.87 | 287/288 |

Conditional on firing, the external delta is +$234.85 (SE $40.01, t=5.87)
with W-L 199-88 and one inert tie, a 69.3% paired win probability. Per-opponent
mean deltas in standard-pool order are -$102.25, +$395.25, +$379.63,
+$284.56, +$326.38 and +$120.65. Corresponding V69/V59 absolute paired means
are -$116,874.04/-$116,771.79, -$122,624.38/-$123,019.63,
-$122,133.08/-$122,512.71, -$127,749.19/-$128,033.75,
-$120,469.42/-$120,795.79 and -$112,690.40/-$112,811.04.

The independent larger block confirms the simulator effect in both margin and
paired win probability. It still is not permission to promote: run unchanged
V69 through a fresh multi-seed, both-seat real-engine standard-pool gate, with
identity controls and statuses treated as hard validity conditions.

The valid true-engine gate is
`logs/arena/v69_vs_v59_real_standard6_20200.json` (real Kaggle engine, seed0
20200, six seeds, both seats, six-opponent standard pool, 12 workers, 4.5
minutes). Both V59 identity and V69 mirror controls are exactly zero on all
6/6 seed pairs. All 180 real-engine games finished `DONE/DONE`: zero errors,
zero not-DONE statuses, no timeout or invalid action.

| screen | cells | V69 absolute paired margin | V59 absolute paired margin | V69-V59 | firing |
|---|---:|---:|---:|---:|---:|
| self-play | 6 seeds | head-to-head -$221 total; 3-3 | n/a | -$36.83/seed, SE $175.47, t=-0.21 | 6/6 |
| standard external pool | 36 | -$127,014.56 mean; 0 wins | -$127,246.47 mean; 0 wins | +$231.92 mean, SE $127.59, t=1.82 | 33/36 |

Conditional on firing, the real-engine external delta is +$253.00 with W-L
23-10 and three inert ties, a 69.7% paired win probability (win-rate t=2.26).
Per-opponent mean deltas in standard-pool order are +$294.33, +$554.50,
+$315.00, -$447.33, +$244.33 and +$430.67. Corresponding V69/V59 absolute
paired means are -$112,616.50/-$112,910.83,
-$134,052.33/-$134,606.83, -$133,126.83/-$133,441.83,
-$120,593.17/-$120,145.83, -$134,427.17/-$134,671.50 and
-$127,271.33/-$127,702.00.

The real gate agrees with both simulator gates in external-pool margin and
paired-win direction while direct real self-play is statistically neutral.
V69 has now met the stated evidence sequence: valid 108 cells, independent 288
cells for a major change, and a multi-seed both-seat real-engine gate. Complete
the production import-closure, determinism, full-suite, compile/diff and
documentation audit before changing the selected-baseline designation; do not
submit externally.

Promotion audit completed cleanly on 2026-08-28. A new loader regression test
proves that two executions of a modular version wrapper close over distinct
`_TRACKER` and `tasks` module objects; the complete white-box suite passes
75/75. `python -m compileall -q whitebox arena.py`, `git diff --check`, and the
changed-file import checks pass. Two fresh isolated simulator runs of seed
20300 versus `kaggriculture-multi-route-farming-agent` returned identical
banks `(46716.0, 87576.0)`. That full episode exercised
`whitebox.terminal` and `whitebox.cashflow`; the prohibited
replay/tape/opening/weight/schedule/search/mining/behavior import audit returned
`FORBIDDEN_IMPORTED []`. A separate fresh-process V59 load imported neither
`whitebox.terminal` nor `whitebox.cashflow`, preserving its recorded semantics.

**V69 is now the selected strict-white-box baseline.** This is a local model
selection, not a Kaggle submission. The qualification rests on consistent
external-pool direction across the valid 108-cell simulator (+$364.09 mean,
79-27), independent 288-cell simulator (+$234.03 mean, 199-88 with one tie),
and true-engine (+$231.92 mean, 23-10 with three ties) gates, exact mirrors,
clean statuses, deterministic execution, and the rule-derived opportunity
inequality. Direct real self-play was neutral, not concealed: -$221 total over
six seeds, W-L 3-3. `whitebox/versions/v69_terminal_rescue.py` must now be
treated as immutable when evaluating the next mechanism. V59 remains an
immutable historical comparison baseline, and V65-V68 remain tombstones.

`whitebox/README.md`, `MODEL.md`, and `WHITEBOX_ARCHITECTURE.md` now carry an
explicit current-status note so their retained replay/tape-era research text
cannot be mistaken for the V69 production import/action path. No external
write or submission was made, and no unrelated dirty worktree content was
reset or removed.

The next unresolved high-value white-box mechanism is no longer fixed terminal
feasibility. Return to the portfolio frontier without reviving V64's rejected
one-exchange policy: integrate the already-tested multi-day certificate as
genuine route-master columns under one joint portfolio/cash/route solve, or
derive a single conserved hidden-stock allocation uncertainty set before using
it in the paired objective. Any new arm must compare against immutable V69 and
must not tune against the one negative multi-route or real `3000-socre` cells.

### V70 conserved hidden-shed allocation theorem (2026-08-28)

`whitebox/versions/v70_hidden_stock.py` is an isolated V69 descendant testing
the remaining aggregate-hidden-stock question. The uncertainty set is the
engine-derived integer polytope

```
h[item] >= 0 integer
sum_item h[item] <= shedCapacity = 100
```

so the same private shed capacity is never assigned independently to every
product. `cashflow._allocation_dp` is an exact finite solver for that shared
budget, and equation tests compare it with exhaustive allocation.

The exact both-seat terminal objective makes the uncertainty set algebraically
inert. If `R(x)` is revenue from our `x` units, `R(y)` opponent-alone revenue,
and `R(x+y)` joint revenue on one nonlinear book, the paired margin increment
over the two seat orders is

```
0.5 * (R(x) + R(y) - (R(x+y)-R(x)) + (R(x+y)-R(y))) = R(x).
```

Thus every feasible opponent quantity and every conserved hidden allocation
has exactly the same terminal paired value: our standalone bundle revenue.
V70 keeps the uncertainty-set interface explicit but evaluates this closed
form in O(number of products). It uses the same scenario for the terminal and
general-route columns and requires a strict positive difference; ties preserve
V69 work. Four new tests cover capacity conservation, cancellation on three
nonlinear books, exhaustive bundle equivalence and strict same-scenario route
comparison. The complete suite passes 79/79.

The literal online allocation-DP prototype was rejected before gameplay. Its
durable runtime tombstone is
`logs/whitebox/v70_hidden_dp_runtime_20400.txt`: on simulator seed 20400 versus
`kaggriculture-multi-route-farming-agent`, P99 was 574.319 ms, maximum
1009.385 ms and 14/719 calls were at or above 170 ms. Deadline-induced
fallbacks changed 19 actions and banks from V69's $91,012/$159,231 to
$90,754/$159,221. These are runtime-failure diagnostics, not gameplay
evidence. Replacing the inert DP by the proved closed form restored exact
719/719 action identity and banks $91,012/$159,231. Closed-form V70 measured
16.618 ms mean, 67.775 ms P95, 78.422 ms P99, 101.652 ms maximum and zero
calls at or above 170 ms; same-process V69 measured 16.642/59.216/79.506/
101.368 ms and zero cutoff calls.

The formal CRN identity screen is
`logs/arena/v70_vs_v69_quick_20500.json` (simulator, seed0 20500, hard pool,
26 workers, 1.5 minutes). V69 identity and V70 mirror controls are exactly zero
on 6/6 seeds, direct head-to-head is exactly $0 with 0/6 nonzero pairs, and all
18 external paired cells are exactly $0 with 0/18 firing. There are zero
errors and zero not-DONE statuses. The arena correctly returns `INERT`; do not
run 108/288/real gates and do not promote V70. V69 remains selected.

This closes same-terminal-phase hidden-stock allocation as a source of action
improvement under paired seats. Hidden stock can matter across different sale
times through persistent book state, but modelling that requires a multi-day
joint market/portfolio solve; it cannot be reintroduced as an independent
per-product terminal allowance. The next arm should address the remaining
portfolio/route coupling rather than tuning an opponent quantity.

### V71 post-unit-phase capital route timing (implementation, 2026-08-28)

`whitebox/versions/v71_phase_correct.py` is an isolated V69 descendant for the
explicit engine-ordering risk that market-phase capital and hires cannot act in
the unit phase that already committed earlier in the same step. Historical
variants continue to construct valuation units at `snap.hour` and from their
pre-action positions. Only `capital_variant="phase_correct"` applies

```
route_start_position[u] = engine_position_after(current_unit_action[u])
route_start_hour[u]     = current_hour + 1
remaining_actions[u]    = 24 - route_start_hour[u]
```

Movement projection uses the engine's cardinal displacement and board bound;
non-movement operations leave position unchanged. Candidate hands already had
the correct `hour+1` start and keep the engine spawn ordering. The same shifted
incumbents value both asset columns and HIRE because both market decisions
arrive after the current unit actions. No value coefficient or behavioural
feature is added.

Two equation tests prove exact post-movement positions/budgets and the hour-23
boundary: a one-operation capital task fits the historical one-action
relaxation but cannot use the already-spent final action in V71. The complete
suite passes 81/81 and changed modules compile.

The fresh seed-20600 diagnostic is preserved at
`logs/whitebox/v71_phase_runtime_20600.txt`. V69 finished at
$79,342/$150,630 and V71 at $45,779/$115,639; the own-bank difference is
-$33,563 and is not gameplay evidence. V71 changed 709/719 downstream actions.
The first divergence is step 5: identical unit actions, then V71 emits one
post-phase-valued HIRE while V69 emits no market order, confirming the variant
is firing through the intended master rather than an accidental dispatch path.
V71 remains runtime-safe: 19.736 ms mean, 71.954 ms P95, 97.548 ms P99,
112.318 ms maximum and zero calls at or above 170 ms; same-process V69 was
17.496/71.200/106.295/140.914 ms with zero cutoff calls. Because the
single-seed economic effect is very large and negative, run only a fresh quick
CRN rejection gate before considering any wider evaluation.

The valid quick rejection gate is
`logs/arena/v71_vs_v69_quick_20700.json` (simulator, seed0 20700, hard pool,
26 workers, 1.6 minutes). Both V69 identity and V71 mirror controls are exactly
zero on 6/6 seeds, with zero errors and zero not-DONE statuses.

| screen | cells | V71 absolute paired margin | V69 absolute paired margin | V71-V69 | firing |
|---|---:|---:|---:|---:|---:|
| self-play | 6 seeds | head-to-head -$146,050 total; 0-6 | n/a | -$24,341.67/seed, SE $4,194.98, t=-5.80 | 6/6 |
| hard external pool | 18 | -$133,643.17 mean; 0 wins | -$117,091.28 mean; 0 wins | -$16,551.89 mean, SE $5,597.81, t=-2.96 | 18/18 |

The external paired-delta W-L is 3-15. All opponent means are negative:
-$18,513.50, -$20,132.83 and -$11,009.33 in hard-pool order. Corresponding
V71/V69 absolute paired means are -$127,806.33/-$109,292.83,
-$141,775.83/-$121,643.00 and -$131,347.33/-$120,338.00. This is an obvious
regression by both margin and win probability. Do not run 108/288/real gates
and do not promote V71.

The failure identifies the missing equation: projecting only clock and
position is inconsistent when the current unit action also changes a tile or
private inventory. The master then values a post-action route against a
pre-action task/stock snapshot, which can create spurious HIRE value. Keep the
timing tests and negative log, but do not apply this partial transition
globally. A narrower arm may apply `hour+1` only when every current unit action
is PASS, where position, tile and inventory provably remain unchanged; a full
solution must project all current unit transitions before jointly valuing
portfolio and routes.

### V72 all-PASS phase certificate (negative determinism result, 2026-08-28)

`whitebox/versions/v72_idle_phase.py` narrows V71 to the only post-unit state
that needs no tile, inventory or position transition model: every committed
farmer/hand action is exactly PASS. In that state, V72 advances route start
time to `hour+1`; if any unit moves or performs an operation, it explicitly
retains V69 semantics. The activation predicate contains no fitted threshold.
One new test proves that every unit must PASS; the suite reaches 82/82.

On seed 20800 versus `kaggriculture-multi-route-farming-agent`, V72 and V69
were identical on all 719 actions and banks $34,705/$77,142. V72 measured
14.302 ms mean, 52.597 ms P95, 68.812 ms P99, 76.207 ms maximum and zero calls
at or above 170 ms; same-process V69 measured 14.507/53.039/69.972/78.354 ms.
This was an identity/runtime diagnostic, not gameplay evidence.

The formal screen `logs/arena/v72_vs_v69_quick_20900.json` (simulator, seed0
20900, hard pool, 26 workers, 1.7 minutes) is **not valid model evidence**.
Immutable V69's identity control is exact on 6/6 seeds, and direct V72-vs-V69
plus all 18 pool cells display exact zero with 0/18 firing and zero
errors/not-DONE. However, V72's own mirror is nonzero on 1/6 seeds and totals
-$5,358. The arena warning is decisive: the all-PASS predicate amplifies a
rare timing-sensitive upstream action difference into a state-dependent mode
change. Do not interpret the zero pool rows, do not rerun at lower worker count
to rescue it, and do not promote or widen-gate V72.

V71-V72 show that a phase-correct capital master cannot be layered on emitted
actions alone. It needs one deterministic projected post-unit `Snapshot`
covering positions, carried/shed inventory, tile operations, yield removal and
current task completion, after which both ordinary and capital columns must be
regenerated from that projected state. Until that complete rule transition is
implemented, V69 remains the immutable selected baseline and historical
optimistic capital timing must not be partially toggled by runtime action
shape.

Final post-V72 verification on 2026-08-28 reran the complete 82/82 suite,
compiled `whitebox/` and `arena.py`, passed `git diff --check` and touched-file
whitespace checks, and parsed every new durable log. Two fresh isolated V69
simulator runs on seed 21000 returned identical banks
`(58265.0, 121850.0)`. The episode exercised `whitebox.terminal` and
`whitebox.cashflow`; the replay/tape/opening/weight/schedule/search/mining/
behavior prohibited audit remained `FORBIDDEN_IMPORTED []`. In a separate
fresh process immutable V59 still imported neither `whitebox.terminal` nor
`whitebox.cashflow`.

Selected status is unchanged: V69 is immutable and locally promoted; V70 is an
inert theorem arm, V71 is a gameplay regression, and V72 is a determinism
tombstone. No 108/288/real gate is justified for any of V70-V72. No external
submission or write occurred, and no unrelated dirty worktree content was
reset, removed or overwritten. The next complete implementation should be the
deterministic post-unit snapshot transition required above, followed by task
regeneration and only then a joint portfolio/route solve against V69.

### V73 complete post-unit snapshot (implementation and diagnostic, 2026-08-28)

`whitebox/versions/v73_phase_snapshot.py` is the isolated V69 descendant that
implements the complete transition required by V71-V72. Before market/capital
selection it deterministically projects the already-committed farmer and hand
actions in engine order. The projected state covers bounded movement; DROP
with 100-item shed capacity and overflow destruction; PICKUP; animal/shed
PLACE; PLANT/WATER/HARVEST/FERTILIZE/DIG; structures; FEED/CARE/fertilizer;
seeds, carried inventories and tile indexes. It also applies the engine's
phase-level atomic seed equation:

```
demand[crop] > seeds_at_phase_start[crop]
    => every current PLANT(crop) becomes PASS
```

The projection does not advance the public step or simulate market clearing,
town consumption, decay or daily refresh, because all of those occur after the
market order now being chosen. V73 regenerates the strategy Plan, ordinary
tasks, fixed market orders and capital columns from the projected snapshot.
Every incumbent and new hand is valued from `hour+1`; incumbent positions are
already projected and candidate HIRE spawn occupancy therefore does not replay
movement. A projected DROP is present in the regenerated shed and absent from
the emptied unit inventory, so the existing same-turn banking layer prices it
once rather than duplicating it. There is no action-shape switch, fitted
coefficient, learned state or legacy master fallback in this variant.

Three new state tests compare every unit-operation equation directly with the
local simulator, prove aggregate seed rejection plus sequential BUILD->PLACE
on a shared tile, prove the input Snapshot is immutable, and prove projected
DROP stock is not merged twice. A capital test proves projected positions and
spawn occupancy are not moved twice. The complete white-box suite passes
86/86, changed files compile, and `git diff --check` passes.

The single-seed runtime/risk diagnostic is preserved at
`logs/whitebox/v73_phase_snapshot_runtime_21100.txt`. Against
`kaggriculture-multi-route-farming-agent` on simulator seed 21100, V69 banks
were `$75,488/$141,733` and V73 banks were `$83,750/$170,857`; the own-bank
delta is +$8,262 and is not gameplay evidence. V73 changed 653/719 actions.
The first divergence at step 55 retains identical unit actions (farmer WEST,
both hands WATER) and adds one HIRE, demonstrating intended post-unit master
firing. V73 latency was 15.583 ms mean, 54.763 ms P95, 77.267 ms P99 and
94.735 ms maximum, with zero calls at or above 170 ms; V69 measured
17.071/72.529/126.470/149.548 ms, also with zero cutoff calls. Two independent
fresh-process V73 repetitions returned exactly `(83750.0, 170857.0)`.

This is broad default-path behavior, so the diagnostic cannot qualify it.
Run a valid fresh quick CRN self-play plus hard-pool rejection screen against
immutable V69 next. Only if direction and both mirrors are credible should V73
receive the >=108-cell standard gate, then the major-change 288-cell and
both-seat multi-seed real-engine gates. V69 remains selected meanwhile.

The valid quick rejection screen is
`logs/arena/v73_vs_v69_quick_21200.json` (simulator, seed0 21200, hard pool,
26 workers, 1.7 minutes). Both immutable V69's identity control and V73's own
mirror are exactly zero on 6/6 seeds. There are zero errors and zero not-DONE
statuses, so unlike V72 this is valid gameplay evidence.

| screen | cells | V73 absolute paired margin | V69 absolute paired margin | V73-V69 | firing |
|---|---:|---:|---:|---:|---:|
| self-play | 6 seeds | head-to-head -$83,642 total; 1-5 | n/a | -$13,940.33/seed, SE $4,390.70, t=-3.17 | 6/6 |
| hard external pool | 18 | -$116,415.44 mean; 0 wins | -$109,786.61 mean; 0 wins | -$6,628.83 mean, SE $2,205.04, t=-3.01; W-L 6-12 | 18/18 |

Every opponent-specific delta is negative: -$9,928.83 for multi-route,
-$4,794.33 for frontier and -$5,163.33 for v111. Corresponding V73/V69
absolute paired margins are -$131,052.17/-$121,123.33,
-$106,647.00/-$101,852.67 and -$111,547.17/-$106,383.83. V73 is an obvious
regression by paired margin and win probability. The arena's mechanical final
label says `NEUTRAL` only because a quick screen has fewer than 100 cells; the
predeclared purpose of that screen is to reject obvious regressions, and this
one does. Do not run 108/288/real gates and do not promote V73.

Keep the exact projection and its fidelity tests as a dormant tombstone: it
closes an engine-ordering ambiguity and changes no V69 action path. Its failure
shows that phase consistency alone cannot repair the current objective. The
next principled arm should address the still-additive *ordinary* production
tasks: V59 aggregates and recertifies capital output, but the route master can
still sum repeated STRAWBERRY, MILK and WOOL service/harvest values as though
each task cleared against the untouched book. Any such arm must aggregate
selected same-item quantity before `econ.sell_revenue`, keep non-sale survival
terms explicit, and compare against immutable V69.

### V74 nonlinear bundles for ordinary route tasks (implementation, 2026-08-28)

`whitebox/versions/v74_task_bundles.py` is an isolated V69 descendant that
extends nonlinear market clearing from capital columns to ordinary production
tasks before daily route selection. For task `i`, product `p`, and exact
rule-derived output quantity `q[i,p]`, it freezes

```
b[i] = old_value[i] - sum_p sale_value(p, q[i,p])
Q[p] = sum_i q[i,p]
new_value[i] = b[i]
             + sum_p q[i,p] / Q[p] * sale_value(p, Q[p])
```

`q` includes current harvests, animal fertilizer, tonight's rule-triggered
production, explicit survival/CARE future units, crop survival/fertilizer
units, new crop output and placed-animal output. Feed and fertilizer
opportunity costs plus the per-animal `max(0, gross-feed)` floor remain visible
inside `b[i]`. Input costs are intentionally not bundle-discounted: summing
their standalone opportunity costs is conservative for a selected subset.
BUILD_ANIMAL_HOME and CLEAR_WEED are unchanged because their Task columns do
not encode an unambiguous future product; assigning one would be a hypothesis.
Because exact market marginal revenue is non-increasing, allocating the full
proposal bundle's average revenue is a conservative price for every routed
subset. No learned or fitted coefficient is introduced.

Four new equation tests prove one joint clearing quantity for repeated MILK,
WOOL and STRAWBERRY tasks, joint new-STRAWBERRY output, preservation of
feed/option-floor residuals and mandatory survival flags, and no guessed value
for an ambiguous build. The full white-box suite passes 90/90, changed modules
compile, and `git diff --check` passes.

The seed-21300 risk/runtime trace is
`logs/whitebox/v74_task_bundles_runtime_21300.txt`. Against multi-route, V69
banks were `$49,945/$103,213` and V74 banks were `$57,067/$110,279`; own bank
changed +$7,122, which is not paired gameplay evidence. V74 changed 497/719
actions. The first difference at step 220 changes one hand's PICKUP from WHEAT
to COW with every other unit action and the market identical, consistent with
repriced route ordering. V74 measured 16.469 ms mean, 63.625 ms P95, 108.561
ms P99 and 142.892 ms maximum, with zero calls at or above 170 ms; V69 measured
13.991/54.468/77.346/82.874 ms and zero cutoff calls.

The mechanism is broad and the own-bank diagnostic cannot qualify it. Run a
fresh quick isolated CRN self-play and hard-pool screen against immutable V69.
Reject on bad direction or nonzero mirrors; widen only if those controls and
paired direction are credible. V69 remains selected.

The valid quick screen is `logs/arena/v74_vs_v69_quick_21400.json`
(simulator, seed0 21400, hard pool, 26 workers, 1.7 minutes). Both V69 identity
and V74 candidate mirrors are exactly zero on 6/6 seeds, with zero errors and
zero not-DONE statuses. Self-play is directionally negative but underpowered:
-$17,750 total over six seeds, mean -$2,958.33, SE $2,364.47, t=-1.25, W-L
2-4. The external pool is positive on all three opponents:

| opponent | cells | V74 absolute paired margin | V69 absolute paired margin | delta | W-L |
|---|---:|---:|---:|---:|---:|
| multi-route | 6 | -$113,523.50 | -$117,155.00 | +$3,631.50 | 3-3 |
| frontier | 6 | -$99,094.17 | -$112,570.83 | +$13,476.67 | 5-1 |
| v111 | 6 | -$101,420.33 | -$112,324.50 | +$10,904.17 | 6-0 |
| **total** | **18** | **-$104,679.33** | **-$114,016.78** | **+$9,337.44, SE $3,385.36, t=2.76** | **14-4** |

V74 fires in 18/18 paired cells. This quick screen only rejects obvious
regressions; its positive pool direction earns, but cannot replace, the
predeclared 108-cell standard gate. Run 18 fresh seeds x six standard
opponents x both seats against immutable V69 next. V74 remains unpromoted.

The valid standard gate is
`logs/arena/v74_vs_v69_standard108_21500.json` (simulator, seed0 21500,
18 seeds x six standard opponents = 108 paired pool cells, both seats, 26
workers, 5.7 minutes). V69 identity and V74 candidate mirrors are both exactly
zero on 18/18 seeds. There are zero errors and zero not-DONE statuses.
Self-play is neutral-positive: +$5,873 total, +$326.28 per seed, SE $2,017.02,
t=0.16, W-L 10-8. The external result does **not** reproduce the quick gain:

| opponent | cells | V74 absolute paired margin | V69 absolute paired margin | delta | W-L |
|---|---:|---:|---:|---:|---:|
| multi-route | 18 | -$114,324.83 | -$113,981.83 | -$343.00 | 9-9 |
| frontier | 18 | -$123,501.33 | -$123,069.67 | -$431.67 | 8-10 |
| v111 | 18 | -$125,145.89 | -$127,027.83 | +$1,881.94 | 7-11 |
| 3000-socre | 18 | -$131,276.44 | -$129,077.00 | -$2,199.44 | 6-12 |
| rank-your-agent | 18 | -$121,548.67 | -$123,078.50 | +$1,529.83 | 9-9 |
| strong-barnyard | 18 | -$111,358.89 | -$110,687.72 | -$671.17 | 8-10 |
| **total** | **108** | **-$121,192.68** | **-$121,153.76** | **-$38.92, SE $1,305.28, t=-0.03** | **47-61** |

V74 fires on 108/108 cells, so dilution is not the explanation. Margin is
indistinguishable from zero and paired win probability is adverse (43.5%).
Confidence is inadequate: do not run the 288-cell or real-engine gates, do not
promote V74, and do not claim the quick result as improvement. V69 remains the
selected strict-white-box baseline.

The durable lesson is narrower than rejecting nonlinear clearing itself. The
equation is correct, but allocating the complete proposal's average revenue to
every task is a conservative linear relaxation that changes route ordering in
all games and does not distinguish the marginal subset ultimately selected.
The next principled formulation, if pursued, must put aggregate same-item
quantity inside the route-master selection or deterministically recertify and
re-solve selected quantities; it must not tune a partial product list or a
threshold against these opponent rows.

Final post-V74 verification on 2026-08-28 reran the complete 90/90 white-box
suite, compiled `whitebox/` and `arena.py`, and passed `git diff --check`.
Every new JSON/text log named above was parsed after completion. Two fresh,
isolated V69 simulator runs on seed 21600 versus multi-route returned exactly
`(51550.0, 120532.0)` both times. A V74 run on the same seed returned
`(59357.0, 125891.0)`; this is another own-bank diagnostic, not promotion
evidence. The production import-closure audit after full episodes found
`FORBIDDEN_IMPORTED []` across replay/tape/opening/weight/schedule/search/
mining/behavior paths. In a separate fresh process immutable V59 still
imported neither `whitebox.terminal` nor `whitebox.cashflow`, preserving its
recorded semantics.

Selected status at end of this campaign turn: V69 remains immutable and
locally promoted. V73 is a complete engine-fidelity phase projection with a
valid negative quick gate. V74 is the correct ordinary-bundle equation under a
conservative full-proposal linear relaxation, but its valid 108-cell gate is
neutral with adverse paired win count, so it is unpromoted and receives no
288/real gate. No external write or Kaggle submission was made, and no
unrelated dirty worktree content was reset, removed or overwritten.

### V75 selected-quantity nonlinear route objective (implementation, 2026-08-28)

`whitebox/versions/v75_bundle_master.py` is an isolated V69 descendant that
puts the exact aggregate same-item sale equation inside both ordinary route
selection and the joint ordinary/capital master. It does not inherit V74's
full-proposal average prices. For every identifiable task `i`, the model
decomposes the existing white-box value into exact product output and an
explicit residual,

```
b[i] = old_value[i] - sum_p R[p](q[i,p]),
V(S) = sum_(i in S) b[i] + sum_p R[p](sum_(i in S) q[i,p]),
Delta(i | S) = b[i] + sum_p (R[p](Q[p] + q[i,p]) - R[p](Q[p])).
```

Here `R[p](q)` is the existing `econ.sell_revenue` equation evaluated against
the current observed market and `Q[p]` is the quantity already selected by the
master. `CAPITAL_CROP` and `CAPITAL_ANIMAL` expose their exact output to the
same product book as ordinary harvest/service tasks; asset costs remain in
their residuals and fixed BUY_LAND activation is still paid once outside
`V(S)`. Prize swaps use the exact difference `V(S - old + new) - V(S)`, and
capital branch comparison recertifies the complete chosen set with `V(S)`.
There are no product-specific switches, fitted coefficients, thresholds, or
opponent-dependent terms.

The route master obtains candidates from a deterministic lazy marginal heap.
Exact market marginal revenue is non-increasing, so a stale heap key is an
upper bound and the selected head is reinserted until current; after every
successful insertion the quantity book is updated. The old static ordering is
retained when no bundle model is supplied, including immutable V69's path.

Three equation-level tests prove (1) a deliberately capacity-constrained
route chooses a diversified product instead of the additively overvalued
second MILK task, and that its exact bundle score is greater, (2) `swap_gain`
equals direct selected-set score subtraction, and (3) ordinary and capital
MILK output clear against one quantity book. The complete white-box suite
passes 93/93; the changed files compile and `git diff --check` passes. This is
only an implementation checkpoint. V75 is broad, unqualified, and must first
receive a fresh single-seed runtime/determinism audit followed by a quick CRN
self-play and hard-pool rejection screen against immutable V69. V69 remains
selected.

The seed-21700 runtime/determinism trace is
`logs/whitebox/v75_bundle_master_runtime_21700.txt`. Against multi-route, V69
banks were `$41,949/$78,402`; V75 and an independent fresh-process repeat were
both exactly `$25,419/$72,284`, with identical SHA256 over all 719 actions.
V75 differs from V69 on 549/719 actions; the first difference at step 147 adds
HIRE while all unit actions remain identical, demonstrating intended joint
master firing. The -$16,530 own-bank change is a risk diagnostic only.

V75 latency was 22.704 ms mean, 86.674 ms P95, 133.913 ms P99 and 180.823 ms
maximum, with one call at or above 170 ms. Its independent repeat measured
22.596/86.004/133.536/180.702 ms and one such call. V69 measured
16.587/63.956/135.505/180.208 ms with two calls at or above 170 ms under the
same host load. Thus the candidate's mean/P95 overhead is real, while the
near-181 ms maximum is not candidate-specific and comes from the inherited
internal deadline behavior. This is below the engine's 1 second timeout but
not promotion-safe relative to the 180 ms soft target. The correct next step
is still a small CRN quick rejection screen: the broad own-bank loss and
runtime overhead make a 108-cell run unjustified unless paired direction is
credible. Do not promote V75 from this diagnostic; V69 remains selected.

The first V75 quick screen is preserved at
`logs/arena/v75_vs_v69_quick_21800.json` (simulator, seed0 21800, hard pool,
26 workers, 1.9 minutes), but it is **invalid gameplay evidence**. V69's
identity mirror is exactly zero on 6/6 seeds; V75's own mirror is nonzero on
1/6 seeds, totaling +$365. The candidate's single-process repeat did not expose
this because the exact-marginal path only crossed the inherited wall-clock
fallback under parallel contention. There were zero engine errors and zero
not-DONE statuses.

For completeness only, the invalid screen reported self-play +$10,114 total
(+$1,685.67/seed, SE $3,046.04, t=0.55, W-L 4-2) and hard-pool candidate
absolute paired margin -$120,833.50 versus V69 -$122,336.61, delta +$1,503.11
(SE $3,256.24, t=0.46, W-L 11-7), firing 18/18. Per-opponent deltas were
-$5,651.17 multi-route, +$5,891.17 frontier, and +$4,269.33 v111. None of
these numbers may qualify or reject the mechanism because the candidate mirror
failed. Do not run 108 cells from this result.

The next implementation correction must make the isolated V75 route and
capital masters structurally finite and independent of `perf_counter`: use the
deterministic primal/heuristic route path and no wall-clock branch inside this
bounded formulation, without changing any historical wrapper. Then rerun unit
tests, a contended candidate mirror, runtime, and a fresh quick CRN screen. V69
remains selected.

### V76 structurally deterministic selected-bundle master (implementation, 2026-08-28)

`whitebox/versions/v76_deterministic_bundle_master.py` preserves V75's exact
selected-quantity objective but explicitly selects the bounded greedy route
primal and deterministic NN+2-opt tour emission. Only the conjunction
`bundle_master=True` and `deterministic_primal=True` removes the route deadline;
only the new capital variant `ordinary_bundle_master_deterministic` removes the
capital deadline. Consequently V75 retains its failed timing-dependent
semantics, V63/V64 retain their historical deterministic-route semantics, and
V69 is unchanged. The solve remains structurally bounded by the finite task
heap, finite crew candidates, at most 16 activation branches, and heuristic
route construction; it does not substitute a state-dependent fallback.

Two new structural tests pass an already-expired deadline and prove that V76's
daily route and capital masters receive `None`, while retaining a non-null exact
bundle model and deterministic primal. Together with the V75 bundle equations,
the complete white-box suite now passes 95/95; changed modules compile and
`git diff --check` passes. V76 remains unqualified. Next run the six-seed
candidate mirror under multiprocessing contention, then a single-seed runtime
audit. Only an exact mirror and safe runtime can earn a fresh quick CRN screen
against immutable V69.

The contended V76 mirror used simulator seeds 21900-21905, both seats, and 12
parallel workers. Every one of the six paired margins is exactly zero; there
are zero errors and zero not-DONE statuses, and wall time is 40.54 seconds.
This directly reproduces the contention condition that invalidated V75 and
shows that V76 removed its state-dependent branch.

The fresh seed-22000 runtime trace is
`logs/whitebox/v76_deterministic_bundle_runtime_22000.txt`. V69 banks were
`$39,021/$92,062`; two independent V76 runs were exactly
`$48,949/$114,629`, including identical SHA256 over all 719 actions. V76
differs from V69 on 689/719 actions; the first difference at step 2 changes
only the second hand's movement from NORTH to WEST, consistent with the
deterministic route primal. V76 latency was 21.037 ms mean, 91.552 ms P95,
124.139 ms P99 and 150.474 ms maximum; its repeat was
21.061/91.972/124.185/151.046 ms. Both had zero calls at or above 170 ms. V69
was 15.774/61.221/101.812/152.138 ms with zero cutoff calls. The typical
overhead is material but the 180 ms soft target is satisfied. Absolute banks
are not gameplay evidence. V76 now earns only a fresh quick CRN rejection
screen because its 689-action firing breadth remains high; V69 stays selected.

The valid V76 quick screen is
`logs/arena/v76_vs_v69_quick_22100.json` (simulator, seed0 22100, hard pool,
26 workers, 2.1 minutes). V69 identity and V76 candidate mirrors are both
exactly zero on 6/6 seeds, with zero errors and zero not-DONE statuses.
Self-play is +$8,732 total, +$1,455.33/seed, SE $3,662.20, t=0.40, W-L 4-2.

| opponent | cells | V76 absolute paired margin | V69 absolute paired margin | delta | W-L |
|---|---:|---:|---:|---:|---:|
| multi-route | 6 | -$108,240.33 | -$106,970.33 | -$1,270.00 | 3-3 |
| frontier | 6 | -$117,369.17 | -$129,107.00 | +$11,737.83 | 5-1 |
| v111 | 6 | -$125,333.17 | -$127,983.50 | +$2,650.33 | 3-3 |
| **total** | **18** | **-$116,980.89** | **-$121,353.61** | **+$4,372.72, SE $4,296.60, t=1.02** | **11-7** |

V76 fires in 18/18 cells. This screen is underpowered but both self-play and
pool directions are positive with exact mirrors, so it earns the predeclared
18-seed x six-opponent = 108-cell standard gate on fresh seeds. It does not
qualify promotion or the 288/real gates by itself. V69 remains selected.

The valid standard gate is
`logs/arena/v76_vs_v69_standard108_22200.json` (simulator, seed0 22200,
18 fresh seeds x six standard opponents = 108 paired cells, both seats, 26
workers, 7.1 minutes). V69 identity and V76 candidate mirrors are both exactly
zero on 18/18 seeds; there are zero errors and zero not-DONE statuses.
Self-play is +$25,449 total, +$1,413.83/seed, SE $3,019.57, t=0.47, paired
W-L 9-9 (episode W-L 19-17).

| opponent | cells | V76 absolute paired margin | V69 absolute paired margin | delta | W-L |
|---|---:|---:|---:|---:|---:|
| multi-route | 18 | -$115,047.56 | -$121,256.28 | +$6,208.72 | 12-6 |
| frontier | 18 | -$109,706.17 | -$117,186.06 | +$7,479.89 | 15-3 |
| v111 | 18 | -$110,318.06 | -$120,217.11 | +$9,899.06 | 13-5 |
| 3000-socre | 18 | -$117,390.83 | -$119,273.33 | +$1,882.50 | 9-9 |
| rank-your-agent | 18 | -$107,911.50 | -$118,708.50 | +$10,797.00 | 14-4 |
| strong-barnyard | 18 | -$113,709.06 | -$118,256.61 | +$4,547.56 | 11-7 |
| **total** | **108** | **-$112,347.19** | **-$119,149.65** | **+$6,802.45, SE $2,466.38, t=2.76** | **74-34** |

V76 fires in 108/108 cells and is positive on every opponent. This is a valid
standard-gate improvement signal, unlike V74's neutral gate. However the
mechanism is a major 689-action route/master change and self-play win count is
only 9-9. Do not promote yet: run the required disjoint 48-seed x six-opponent
= 288-cell simulator gate, then a both-seat multi-seed real-engine gate if and
only if that result remains credible. V69 remains selected.

The required major-change simulator gate is
`logs/arena/v76_vs_v69_standard288_22300.json` (simulator, seed0 22300,
48 disjoint seeds x six standard opponents = 288 paired cells, both seats, 26
workers, 18.4 minutes). V69 identity and V76 candidate mirrors are both exactly
zero on 48/48 seeds; there are zero errors and zero not-DONE statuses.
Self-play is -$71,371 total, -$1,486.90/seed, SE $1,539.80, t=-0.97, but paired
W-L is positive 26-22 and episode W-L is 53-43.

| opponent | cells | V76 absolute paired margin | V69 absolute paired margin | delta | W-L |
|---|---:|---:|---:|---:|---:|
| multi-route | 48 | -$108,465.96 | -$109,148.48 | +$682.52 | 27-21 |
| frontier | 48 | -$113,708.65 | -$127,109.08 | +$13,400.44 | 34-14 |
| v111 | 48 | -$115,899.56 | -$129,263.31 | +$13,363.75 | 36-12 |
| 3000-socre | 48 | -$124,600.90 | -$121,781.17 | -$2,819.73 | 25-23 |
| rank-your-agent | 48 | -$114,762.10 | -$124,594.58 | +$9,832.48 | 31-17 |
| strong-barnyard | 48 | -$108,713.46 | -$111,032.63 | +$2,319.17 | 28-20 |
| **total** | **288** | **-$114,358.44** | **-$120,488.21** | **+$6,129.77, SE $1,915.91, t=3.20** | **181-107** |

V76 fires in 288/288 cells. The pool gain and paired win probability replicate
the 108-cell gate, with strong positive results on frontier, v111 and
rank-your-agent and positive win counts on all six opponents. Robustness is not
perfect: mean delta is slightly positive/uncertain on multi-route, negative and
uncertain on 3000-socre, and self-play mean margin is negative despite positive
win probability. This passes the predeclared simulator evidence bar but does
not by itself authorize promotion. Run a disjoint both-seat, multi-seed real
engine gate across the standard pool. V69 remains selected pending that gate.

The real-engine gate is `logs/arena/v76_vs_v69_real6_22400.json` (installed
Kaggriculture engine, seed0 22400, six disjoint seeds x six standard opponents
= 36 paired pool cells, both seats, 12 workers, 6.0 minutes). V69 identity and
V76 candidate mirrors are exactly zero on 6/6 seeds. There are zero errors and
zero not-DONE statuses across all 180 real episodes. Real self-play is
-$43,945 total, -$7,324.17/seed, SE $7,677.24, t=-0.95, but paired W-L is 4-2
and episode W-L is 7-5.

| opponent | cells | V76 absolute paired margin | V69 absolute paired margin | delta | W-L |
|---|---:|---:|---:|---:|---:|
| multi-route | 6 | -$102,480.00 | -$105,483.00 | +$3,003.00 | 4-2 |
| frontier | 6 | -$117,361.67 | -$131,668.67 | +$14,307.00 | 5-1 |
| v111 | 6 | -$116,388.83 | -$132,996.00 | +$16,607.17 | 5-1 |
| 3000-socre | 6 | -$120,213.00 | -$122,730.00 | +$2,517.00 | 3-3 |
| rank-your-agent | 6 | -$115,491.17 | -$127,151.00 | +$11,659.83 | 4-2 |
| strong-barnyard | 6 | -$124,883.33 | -$108,836.67 | -$16,046.67 | 2-4 |
| **total** | **36** | **-$116,136.33** | **-$121,477.56** | **+$5,341.22, SE $4,647.92, t=1.15** | **23-13** |

V76 fires in 36/36 real cells. The real sample is underpowered by itself and
has a negative strong-barnyard row, but its aggregate margin and 63.9% paired
win direction agree closely with both independent simulator gates. Direct
self-play mean margin remains negative/uncertain and is not concealed. The
complete evidence sequence now meets the stated gate structure: valid 108,
valid disjoint 288 for the major default-path change, and a valid both-seat
multi-seed real-engine confirmation. Before changing selected status, complete
the full-suite, compile/diff, production import-closure, historical-wrapper and
fresh determinism audit. No external submission is authorized.

The V76 promotion audit completed cleanly on 2026-08-28. The complete
white-box suite passes 95/95; `python -m compileall -q whitebox arena.py` and
`git diff --check` pass. A fresh full seed-22500 V76 simulator episode versus
multi-route returned banks `$24,511/$60,042` and action SHA256
`1de07a0f557e86af3b4eba201b2c5c5acaac4b8d1e78414d75eb4440bae5aca6`.
The production import closure after that episode returned
`FORBIDDEN_IMPORTED []` across replay/tape/opening/weight/schedule/search/
mining/behavior paths.

Two fresh isolated V69 seed-22500 episodes both returned exactly
`$62,699/$131,160` with action SHA256
`b147ff2768d7aed8dd3315ce76ecf8bbc23834cadcdd71310ec1b56545fa7692`,
confirming the inactive shared-router changes preserve deterministic historical
behavior. In a separate fresh process immutable V59 imported neither
`whitebox.terminal` nor `whitebox.cashflow`; its expected shared
`whitebox.value` import remains present.

**V76 is now the selected strict-white-box baseline.** This is a local model
selection only, not a Kaggle submission. The qualification rests on the exact
selected-quantity economic equation, structural clock independence, valid
standard108 (+$6,802.45 mean, 74-34), disjoint standard288 (+$6,129.77,
181-107), and true-engine real6 (+$5,341.22, 23-13) external-pool results,
with exact mirrors, clean statuses, deterministic actions and runtime below
the 180 ms soft target. Direct self-play mean margin is negative/uncertain at
standard288 and real6, and the real strong-barnyard row is negative; these are
explicit residual risks, not omitted evidence. V76 must now be treated as
immutable for future comparisons. V69 and V59 remain immutable historical
baselines. No external write or Kaggle submission was made, and no unrelated
dirty worktree content was reset, removed or overwritten.

The next highest-value unresolved mechanism is the route-master/certificate
seam: certified multi-day portfolio quantities are still not passed as exact
columns to the selected-quantity route master, trimmed to executable routes,
and recertified from the actual chosen quantities in one deterministic loop.
Any next arm must compare against immutable V76, retain aggregate same-item
clearing and structural clock independence, and must not tune against the
negative 3000-socre/strong-barnyard or self-play rows above.

A final strict-contract source audit found inherited optional `WB_*` knobs in
the shared task/hiring modules. Although all gates used their defaults and
V76's clock-independent route/capital path already ignored the timing knob, a
promoted model may not admit environment-selected behavior. V76 now pins the
qualified constants on every call: 180 ms bookkeeping budget, 20-hand engine
ceiling, unit hire multiplier, rule-derived water slack, fertilizer enabled,
12-tile/3-day cohort hypothesis, cohort gate enabled, heuristic tour mode, and
legacy DROP threshold disabled. Historical wrappers do not call this pin and
retain their semantics. The dynamically-read fertilizer flag gained a
V76-only fixed override; its historical behavior is unchanged.

One new regression test corrupts every reachable module value and proves the
V76 pin restores the qualified constants; the complete suite passes 96/96.
More importantly, two fresh full seed-22500 episodes compared normal defaults
with adversarial values for `WB_ACT_BUDGET_MS`, `WB_MAX_HANDS`,
`WB_HIRE_SAFETY`, `WB_NO_LIVESTOCK`, `WB_WATER_SLACK`, `WB_FERT`, all three
`WB_WAVE_*` knobs, `WB_EXACT_TOUR`, both `WB_DELIVER_*` knobs and
`WB_CAPITAL_MASTER`. Both returned exactly `$24,511/$60,042`, SHA256
`1de07a0f557e86af3b4eba201b2c5c5acaac4b8d1e78414d75eb4440bae5aca6`,
and 0/719 action differences. This is byte-identical to the pre-pin promotion
audit, so all qualification logs retain their exact semantics while the
selected production path is no longer environment-dependent. V76 remains the
selected immutable strict-white-box baseline.

### V77 exact positioned certificate/route seam (implementation and runtime, 2026-08-28)

`whitebox/versions/v77_certified_bundle_routes.py` is an isolated, unpromoted
arm for the next architecture seam. At hour 0 its bounded paired multi-day
constructor now excludes every position already reserved by the observable
ordinary task proposal, exposes the exact item-to-position assignment used by
its constructive shared-route proof, and passes only those exact positioned
asset columns to V76's deterministic nonlinear route master. The route master
may trim the proposal for current executable routes. Branch comparison then
recertifies the retained item/position pairs themselves under daily cash,
full-service feed, exact Fibonacci crew cost, shed capacity, market-order
slots, grouped same-item sale clearing and the one-time land activation. It no
longer sorts retained positions and silently certifies a different assignment.
The next-day `inventory_execution` plan adopts only live purchased inventory;
capital bought in the current market phase is still unavailable to the unit
phase that already acted.

All new behavior is selected only by
`certified_bundle_master_deterministic`. Existing count-only certificate calls,
V60-V64 and immutable V69/V76 retain their semantics. V77 imports V76's strict
runtime pin, uses no wall-clock branch in either route or capital selection,
and contains no learned coefficient, tape, replay, seed lookup, target identity
or hidden schedule. Equation tests prove exact assignment exposure, duplicate
and out-of-domain position rejection, route-reservation exclusion, exact
positioned column construction, exact retained-position recertification and
clock-independent capital solving. The complete white-box suite passes
102/102; `python3 -m compileall -q whitebox arena.py` and `git diff --check`
pass.

The seed-22600 single-process diagnostic is preserved at
`logs/whitebox/v77_certified_bundle_runtime_22600.txt`. Against multi-route,
two fresh V77 episodes returned exactly `$56,584/$121,030` and identical action
SHA256 `c92946ae3e2b8d54486626cd5b528e69a6a37afa39b32d06da1ab4963200de36`.
Latency was 32.552 ms mean, 101.945 ms P95, 124.775 ms P99 and 149.165 ms max,
with zero calls at or above 170 ms; the repeat was 32.447/102.822/123.991/
149.490 ms and likewise zero cutoff calls. The same host sample measured V76
at 21.181/96.962/154.530/187.558 ms with three calls at or above 170 ms, so
V77's typical overhead is material but its observed tail remains within the
180 ms soft target. Absolute banks are not gameplay evidence. V77 is still
unqualified; run a fresh six-seed contended mirror plus hard-pool CRN rejection
screen against immutable V76 before any larger gate.

The fresh quick screen is
`logs/arena/v77_vs_v76_quick_22700.json` (simulator, seed0 22700, six seeds,
hard pool, both seats, 26 workers, 3.1 minutes). Both the V76 identity mirror
and V77 candidate mirror are exactly zero on 6/6 seeds; there are zero errors
and zero not-DONE statuses. Head-to-head self-play is +$161,072 total,
+$26,845.33/seed (SE $11,537.59, t=2.33, W-L 4-2). The external candidate
absolute paired margin is -$109,073.28 versus V76 -$117,935.56, a paired delta
of +$8,862.28 (SE $15,721.90, t=0.56, W-L 10-8), firing in 18/18 cells.

| opponent | cells | V77 absolute paired margin | V76 absolute paired margin | delta | W-L |
|---|---:|---:|---:|---:|---:|
| multi-route | 6 | -$137,783.83 | -$104,319.83 | -$33,464.00 | 2-4 |
| frontier | 6 | -$94,761.00 | -$124,732.33 | +$29,971.33 | 4-2 |
| v111 | 6 | -$94,675.00 | -$124,754.50 | +$30,079.50 | 4-2 |
| **total** | **18** | **-$109,073.28** | **-$117,935.56** | **+$8,862.28** | **10-8** |

This is valid but statistically neutral, with a large negative multi-route row
and opposite positive directions on frontier/v111. It is not promotion
evidence, but it is not an obvious quick rejection either; because the change
fires everywhere and replaces the portfolio ceiling, run the existing
18-seed x six-opponent 108-cell standard gate on disjoint seeds before deciding
whether V77 is a tombstone. Immutable V76 remains selected.

The disjoint standard gate is
`logs/arena/v77_vs_v76_standard108_22800.json` (simulator, seed0 22800,
18 seeds x six standard opponents = 108 paired pool cells, both seats, 26
workers, 10.8 minutes). V76's identity mirror and V77's candidate mirror are
both exactly zero on 18/18 seeds. There are zero errors and zero not-DONE
statuses. Head-to-head self-play is +$100,632 total, +$5,590.67/seed
(SE $3,778.00, t=1.48, W-L 12-6). External candidate absolute paired margin
is -$103,719.18 versus V76 -$112,607.58, a +$8,888.41 delta
(SE $4,617.19, t=1.93), but paired improvements are only 55-53 despite firing
in 108/108 cells.

| opponent | cells | V77 absolute paired margin | V76 absolute paired margin | delta | W-L |
|---|---:|---:|---:|---:|---:|
| multi-route | 18 | -$117,521.00 | -$107,402.83 | -$10,118.17 | 7-11 |
| frontier | 18 | -$85,121.78 | -$112,162.06 | +$27,040.28 | 12-6 |
| v111 | 18 | -$98,792.33 | -$111,790.94 | +$12,998.61 | 10-8 |
| 3000-socre | 18 | -$115,709.72 | -$124,398.44 | +$8,688.72 | 8-10 |
| rank-your-agent | 18 | -$96,636.17 | -$110,876.50 | +$14,240.33 | 11-7 |
| strong-barnyard | 18 | -$108,534.06 | -$109,014.72 | +$480.67 | 7-11 |
| **total** | **108** | **-$103,719.18** | **-$112,607.58** | **+$8,888.41** | **55-53** |

V77 is a valid **neutral tombstone**, not a promotion candidate. The positive
mean is blowout-sensitive and does not establish robust win probability: its
50.9% paired improvement rate is effectively a coin flip, multi-route regresses,
and two nominally positive rows still lose more cells than they win. This is
substantially weaker than V76's own 108-cell qualification (74-34, t=2.76).
Do not spend the required 288-cell or real-engine gates and do not promote.
The implementation and logs are preserved; immutable V76 remains selected.

The next principled formulation, if this seam is revisited, must remove the
remaining objective mismatch rather than tune portfolio item counts: V77's
route insertion order still values capital with the current-horizon V76
selected-output oracle, while only final crew/branch comparison receives the
multi-day positioned certificate. An exact selected-set multi-day marginal
oracle (with a structural evaluation bound and runtime proof) is required to
make route trimming optimize the same certificate that recertifies it.

The V77 closeout audit used a fresh full seed-22900 simulator episode against
an inert public-observation-only agent and returned banks `$101,027/$3,000`.
The resulting production import closure reports `FORBIDDEN_IMPORTED []` across
replay/tape/opening/weight/schedule/search/mining/behavior paths. After all
documentation and evidence updates, the complete suite again passes 102/102,
`python3 -m compileall -q whitebox arena.py` passes, and `git diff --check`
passes. No external write or Kaggle submission was made. The dirty worktree and
all unrelated user changes remain preserved.

### V78 exact multi-day marginal inside route trimming (implementation and runtime, 2026-08-28)

`whitebox/versions/v78_certified_marginal_routes.py` is an isolated follow-up
to the V77 tombstone. `capital.PositionedCertificateObjective` gives the route
master one internally consistent selected-set value:

```
V(S) = V_ordinary(S_ordinary)
     + CertificatePairedValue(exact positioned S_capital)
Delta(i | S) = V(S union {i}) - V(S).
```

Ordinary work retains V76's exact grouped current-market equation. Every
capital insertion and swap is the exact difference between two feasible
multi-day certificates with the retained item-to-tile assignments, daily
shared closed routes, cash reserve, feed, Fibonacci crew cost, shed capacity,
order slots, grouped daily sales and one-time land activation. Certificate
values are memoized by the finite selected physical task set and all shared
cash/opponent-visible contexts are computed once from the current observation.
There is no time cutoff, fitted coefficient, target identity, replay, tape,
seed lookup or hidden schedule. V77, V76 and all earlier variant strings retain
their behavior.

Three new equation/structural tests prove that exact insertion marginals
 telescope to final selected-set value, swap gain equals the exact score
difference, repeated subset queries are cache hits, and an expired clock cannot
alter the new capital master. The full white-box suite passes 105/105;
`python3 -m compileall -q whitebox arena.py` and `git diff --check` pass.

The seed-23000 diagnostic is
`logs/whitebox/v78_certified_marginal_runtime_23000.txt`. Two independent V78
runs returned exactly `$59,629/$114,702`, identical action SHA256
`e85006d16af1fbadf26e94e5cea0d46ab95229acc57bb09b6aca45381f1eccbd`,
and 0/719 repeat action differences. V78 differs from V77 on 647/719 actions.
Its two latency summaries were 28.873 ms mean, 81.670/82.391 ms P95,
105.123/105.135 ms P99 and 161.392/184.976 ms maximum, with respectively zero
and one calls at or above 170 ms. Thus typical runtime is safe and the solve is
structurally deterministic, but one repeat exceeded the 180 ms soft target by
4.98 ms; this tail risk must not be hidden. The solve remained far below the
engine's one-second timeout. V78 earns only a fresh quick contended mirror and
hard-pool rejection screen; V76 remains selected.

The fresh V78 rejection screen is
`logs/arena/v78_vs_v76_quick_23100.json` (simulator, seed0 23100, six seeds,
hard pool, both seats, 26 workers, 2.7 minutes). Both V76 and V78 mirrors are
exactly zero on 6/6 seeds, with zero errors and zero not-DONE statuses.
Head-to-head self-play is +$2,244 total, +$374.00/seed (SE $7,749.26, t=0.05,
W-L 3-3). External V78 absolute paired margin is -$109,192.78 versus V76
-$102,542.22: delta -$6,650.56 (SE $9,471.58, t=-0.70, W-L 6-12), firing
18/18.

| opponent | cells | V78 absolute paired margin | V76 absolute paired margin | delta | W-L |
|---|---:|---:|---:|---:|---:|
| multi-route | 6 | -$133,805.17 | -$110,977.17 | -$22,828.00 | 1-5 |
| frontier | 6 | -$95,513.83 | -$100,537.17 | +$5,023.33 | 2-4 |
| v111 | 6 | -$98,259.33 | -$96,112.33 | -$2,147.00 | 3-3 |
| **total** | **18** | **-$109,192.78** | **-$102,542.22** | **-$6,650.56** | **6-12** |

V78 is a valid quick-rejected tombstone. The exact objective consistency did
not repair V77's robust win probability and made two of three hard rows
negative, while the runtime trace also contained one 184.98 ms soft-target
breach. Do not run 108/288/real and do not promote. The next correctness arm
must address a separate inherited phase defect before judging the certificate
again: V77/V78 route feasibility starts current units at the pre-action hour
even though asset purchases commit only after those unit actions. A projected
post-unit snapshot and hour+1 route start are required; immutable V76 remains
selected.

### V79 projected post-unit capital phase (implementation and runtime, 2026-08-28)

`whitebox/versions/v79_phase_correct_certificate.py` isolates the phase repair
on top of V78. After current unit actions are chosen, it applies the exact
public/private unit transition with `state.project_unit_phase`, regenerates the
inventory-execution plan, ordinary tasks and fixed market orders from that
projected snapshot, and invokes the certificate/master from the projected
positions. Current units and newly spawned hires begin candidate routes at
`hour + 1`; no purchased seed or animal is credited with the action already
spent earlier in the same step. V76-V78 and historical phase variants retain
their exact paths.

One new structural test proves every unit supplied to the V79 capital master
starts at the next action hour on an already-projected snapshot. Together with
the exact projection transition tests and V78 marginal equations, the complete
white-box suite passes 106/106; compile and diff checks pass. The formulation
uses only the current observation, the agent's just-committed actions and exact
engine transition/economic equations.

The seed-23200 runtime trace is
`logs/whitebox/v79_phase_correct_runtime_23200.txt`. Two independent V79 runs
returned exactly `$52,248/$107,670`, identical action SHA256
`b106b2b75b4c61cc30283739d5de5979fc0be152ce64542c5ee629d304e7fdb4`,
and zero repeat differences; V79 differs from V78 on 712/719 actions. Mean
latency is 24.157/24.257 ms, P95 72.480/72.600 ms and P99 97.445/98.770 ms.
Maxima are 198.139 and 187.319 ms with two and three calls at or above 170 ms.
This is deterministic and far below the one-second engine timeout, but it does
not meet the 180 ms soft target. Preserve that risk and run only a quick
contended rejection screen; immutable V76 remains selected.

The V79 quick screen is
`logs/arena/v79_vs_v76_quick_23300.json` (simulator, seed0 23300, six seeds,
hard pool, both seats, 26 workers, 2.6 minutes). V76 and V79 mirrors are exactly
zero on 6/6 seeds and all episodes complete with zero errors/not-DONE statuses.
Head-to-head self-play is +$85,925 total, +$14,320.83/seed (SE $11,019.25,
t=1.30, W-L 4-2). The external candidate absolute paired margin is
-$109,627.67 versus V76 -$110,520.39, nominal delta +$892.72
(SE $9,510.92, t=0.09), but paired improvements are only 7-11 with firing
18/18.

| opponent | cells | V79 absolute paired margin | V76 absolute paired margin | delta | W-L |
|---|---:|---:|---:|---:|---:|
| multi-route | 6 | -$124,127.33 | -$98,774.83 | -$25,352.50 | 1-5 |
| frontier | 6 | -$102,027.00 | -$114,368.67 | +$12,341.67 | 3-3 |
| v111 | 6 | -$102,728.67 | -$118,417.67 | +$15,689.00 | 3-3 |
| **total** | **18** | **-$109,627.67** | **-$110,520.39** | **+$892.72** | **7-11** |

The arena verdict is correctly **REGRESSION — margin up, win rate below 50%**.
The phase correction is mechanically required for any future capital solver,
but it does not qualify this portfolio/certificate policy and its 187-198 ms
tails add runtime risk. V79 is a quick-rejected tombstone. Do not run
108/288/real and do not promote. Together V77-V79 show that exact positioned
columns, exact selected-set multi-day marginals and exact post-unit phase
alignment do not robustly beat V76 with the current portfolio certificate.
Stop iterating item counts or opponent rows. Any future return to this layer
must first align the certificate's calendar/cash proof with actual hour-1
same-day inventory execution; otherwise move to a different architecture gap.
Immutable V76 remains selected.

The V78/V79 closeout audit used a fresh full seed-23400 V79 simulator episode
against an inert public-observation-only agent and returned banks
`$88,191/$3,000`. Production import closure reports `FORBIDDEN_IMPORTED []`
across replay/tape/opening/weight/schedule/search/mining/behavior paths. The
complete white-box suite passes 106/106; `python3 -m compileall -q whitebox
arena.py` and `git diff --check` pass. The V76 identity mirrors in both quick
gates remain exact, confirming the new variant-only branches did not alter the
immutable baseline. No Kaggle submission or other external write occurred, and
all unrelated dirty worktree content remains preserved.

### V80 same-day calendar and bridge-cash certificate (implementation, 2026-08-28)

`whitebox/versions/v80_same_day_certificate.py` is an isolated repair of the
last known V79 certificate/execution mismatch. On the projected post-unit
hour-0 snapshot it models crops as PLANT+WATER on the purchase day and advances
their exact event calendar by one day. Animals are BUILD+PLACE on the purchase
day, survive that first un-fed night by the engine's exact two-night starvation
rule, and begin FEED+CARE the next day. Today's positioned acquisition route is
proved by the live hour+1 route master and is removed from the future service
certificate so work and hires are not charged twice. For crew arm `k`, requiring

```
min_day certificate_cash(day) >= plan_reserve + current_hire_cost(k)
```

is exactly the cash trajectory after paying that market-phase hire cost once;
the paired objective subtracts the same hire once outside the certificate.
Asset quantities, land activation, future feed, shared routes, shed capacity,
order slots and grouped same-item sale revenue retain the V78 equations.

V80 also adds a variant-only observable acquisition invalidator. It tracks the
conserved totals `standing crops + seeds` and `standing animals + shed animals
+ carried animals`; only an increase resets that seat's current-day route.
Consequently a purchase receives an executable same-day plan even when no hand
was hired, while PLANT and PLACE conserve the signature and cannot cause
per-turn route thrash. This memory contains only the agent's successive public/
private observations, no opponent fingerprint or hidden schedule.

The first correct implementation recomputed 56-57 identical physical subsets
for each of seven crew candidates and took 183-203 ms on the initial action.
The exact optimization now stores each zero-reserve physical certificate and
its `min(cash_path)` once; crew arms reuse its routes/output/value and apply
their distinct reserve inequality. This reduced the same initial action to
105.612 ms without changing its orders. Tests prove purchase-day WHEAT output
advances exactly from day 3 to day 2, first-night animal feed is deferred,
today's route is not double-counted, current hire tightens bridge cash, physical
certificates are shared without sharing the cash verdict, and acquisition
replans exactly once while planting does not. The complete targeted cashflow/
capital suite passes 51/51. V80 remains unqualified pending full suite,
determinism and runtime audit; immutable V76 remains selected.

The complete suite passes 111/111; compile and diff checks pass. The seed-23600
runtime audit is `logs/whitebox/v80_same_day_runtime_23600.txt`. Two independent
V80 runs returned exactly `$49,056/$96,964`, action SHA256
`96c49d994d9fca6dd65bc50dc0228b1d659fd19bf92d76a78d414c1776928a72`,
and 0/719 repeat differences. V80 differs from V79 on 716/719 actions. Latency
was 30.343/30.499 ms mean, 90.638/90.914 ms P95, 124.930/124.514 ms P99 and
165.910/190.683 ms max, with zero and one calls at or above 170 ms. It remains
far below the one-second timeout and contains no timing-dependent policy
branch, but one repeat missed the 180 ms soft target. V80 earns only a fresh
quick contended rejection screen; immutable V76 remains selected.

The V80 quick rejection screen is
`logs/arena/v80_vs_v76_quick_23700.json` (simulator, seed0 23700, six seeds,
hard pool, both seats, 26 workers, 2.9 minutes). V76 and V80 mirrors are exactly
zero on all 6 seeds; there are zero errors and zero not-DONE statuses.
Head-to-head self-play is +$90,521 total, +$15,086.83/seed (SE $8,281.01,
t=1.82, W-L 4-2). External candidate absolute paired margin is -$126,788.50
versus V76 -$102,853.94: delta -$23,934.56 (SE $7,393.81, t=-3.24,
W-L 5-13), firing 18/18.

| opponent | cells | V80 absolute paired margin | V76 absolute paired margin | delta | W-L |
|---|---:|---:|---:|---:|---:|
| multi-route | 6 | -$140,137.33 | -$101,678.83 | -$38,458.50 | 1-5 |
| frontier | 6 | -$116,305.00 | -$101,962.83 | -$14,342.17 | 2-4 |
| v111 | 6 | -$123,923.17 | -$104,920.17 | -$19,003.00 | 2-4 |
| **total** | **18** | **-$126,788.50** | **-$102,853.94** | **-$23,934.56** | **5-13** |

V80 is a decisive quick-rejected tombstone. Every external row is negative and
the aggregate t statistic is -3.24 despite favorable self-play, directly
demonstrating why head-to-head/own-bank evidence cannot promote this campaign.
Do not run 108/288/real and do not promote. V77-V80 now close the current
certificate-route integration line: surrogate positions, selected-set
objective mismatch, market-phase timing, cached-route acquisition adoption,
purchase-day calendar and current-hire bridge cash were each repaired, yet
robust external win probability did not improve and the fully aligned form
regressed materially. Preserve the mechanisms/tests as equation assets, but do
not make another inventory-portfolio item/count variant. The next campaign
must move to a different architecture gap and compare against immutable V76.

The V80 closeout audit used a fresh full seed-23800 simulator episode against
an inert public-observation-only agent and returned banks `$87,836/$3,000`.
Production import closure is `FORBIDDEN_IMPORTED []` across replay/tape/
opening/weight/schedule/search/mining/behavior paths. The complete white-box
suite passes 111/111; `python3 -m compileall -q whitebox arena.py` and
`git diff --check` pass. The V76 mirror in the quick gate is exact, no historical
baseline was edited, no external write or Kaggle submission occurred, and all
unrelated dirty worktree content remains preserved.

### V81 clock-free refined selected-bundle routes (implementation, 2026-08-28)

`whitebox/versions/v81_refined_bundle_routes.py` isolates a route-primal gap
outside the closed certificate line. V76 deliberately stops after exact
selected-bundle greedy insertion so wall-clock contention cannot enter its
policy. V81 retains V76's observation, task values, nonlinear selected-set
market book, fixed land activation, capital proposals, terminal certificate
and strict runtime pin, but enables the router's finite two-pass coordinate
descent: move a selected task only when total route actions strictly fall;
exchange an optional selected task only when exact selected-set value strictly
rises while cash, order, activation, exclusivity, stock and worker budgets
remain feasible; then greedily refill newly exposed capacity. Both daily and
crew/capital solves receive `deadline=None`, so the candidate contains no
clock-dependent cutoff or fallback.

The new flags default false and are included in the daily-plan cache identity;
V76 and every historical wrapper retain their exact paths. Three structural
tests prove that an already-expired deadline is removed for both V81 masters,
that refinement is explicitly enabled with the exact bundle model, and that a
concrete six-action route instance improves selected prize value from 12 to 16
under the finite exchange equations. The targeted joint-planner/capital suite
passes 47/47; compile and diff checks pass. V81 is unqualified pending the full
suite, deterministic runtime audit, import closure, and a fresh CRN rejection
screen against immutable V76.

The complete white-box suite passes 114/114; compile and diff checks pass. The
seed-23900 audit is `logs/whitebox/v81_refined_routes_runtime_23900.txt`.
Two independent V81 runs returned exactly `$69,694/$110,880`, identical action
SHA256 `11e85940e34cfe4d918dd082f76ad1f51508aece2e751c190225ddf1ab4ca669`,
and zero repeat differences; V81 differs from V76 on 695/719 actions. V81
latency was 36.933/37.028 ms mean, 153.406/154.203 ms P95,
248.643/249.957 ms P99 and 334.033/335.361 ms maximum, with 22 calls at or
above 180 ms in each repeat. The same run measured V76 at 24.986 ms mean,
116.809 ms P95, 177.687 ms P99 and 209.718 ms max, with six calls at or above
180 ms, so host contention is present but does not explain V81's much larger
tail. V81 is structurally deterministic and remains far below the engine's
one-second timeout, but materially fails the 180 ms soft target. Run only the
fresh six-seed CRN rejection screen; do not spend a 108/288/real gate without
exceptionally strong gameplay evidence. Immutable V76 remains selected.

The fresh V81 quick rejection screen is
`logs/arena/v81_vs_v76_quick_24000.json` (simulator, seed0 24000, six seeds,
hard pool, both seats, 26 workers, 3.3 minutes). V76 and V81 mirrors are exactly
zero on all 6/6 seeds; all episodes complete with zero errors and zero not-DONE
statuses. Head-to-head self-play is -$27,226 total, -$4,537.67/seed
(SE $3,272.21, t=-1.39, W-L 2-4). External V81 absolute paired margin is
-$110,964.94 versus V76 -$103,430.94: delta -$7,534.00 (SE $6,419.63,
t=-1.17, W-L 10-8), firing 18/18.

| opponent | cells | V81 absolute paired margin | V76 absolute paired margin | delta | W-L |
|---|---:|---:|---:|---:|---:|
| multi-route | 6 | -$91,527.83 | -$100,332.83 | +$8,805.00 | 5-1 |
| frontier | 6 | -$121,561.33 | -$108,588.67 | -$12,972.67 | 3-3 |
| v111 | 6 | -$119,805.67 | -$101,371.33 | -$18,434.33 | 2-4 |
| **total** | **18** | **-$110,964.94** | **-$103,430.94** | **-$7,534.00** | **10-8** |

The quick result is statistically neutral but negative in mean, negative in
self-play, and negative on two of three external rows. More importantly, the
same finite refinement materially violates the runtime soft target. V81 is a
valid tombstone: exact deterministic relocation/exchange/refill does not
provide evidence of robust paired improvement proportional to its 335 ms tail.
Do not run 108/288/real, do not promote, and do not hide the favorable
multi-route row or the aggregate 10-8 count. Any future route-primal arm must
derive a materially smaller structural work bound before gameplay evaluation;
wall-clock truncation is not an acceptable repair. Immutable V76 remains the
selected strict-white-box baseline.

The V81 closeout import audit used a fresh full seed-24100 simulator episode
against an inert public-observation-only agent and returned banks
`$74,242/$3,000`. Production import closure is `FORBIDDEN_IMPORTED []` across
replay/tape/opening/weight/schedule/search/mining/behavior paths. The complete
suite passes 114/114; compile and diff checks pass. No historical wrapper was
edited, no external write or Kaggle submission occurred, and unrelated dirty
work remains preserved.

### V82 current-shop guaranteed-drain market (implementation, 2026-08-28)

`whitebox/versions/v82_guaranteed_drain_market.py` isolates a market-control
contract gap outside the closed certificate and route-refinement lines. V76's
steady seller still reaches `market_model.TOWN_DAY`, a fixed-seed synthetic
shop average, and can expand its batch through thresholded opponent timing.
V82 retains V76's qualified task, route, capital and terminal paths but replaces
only ordinary sale scheduling with a current-observation certificate.

At hour zero, for each sellable item `p`, it computes the analytic lower town
drain `D[p]` over `[current_step, next_day_boundary)` from the exact observed
shop multiset, town-centre rule and the enumerated minimum contribution of each
still-hidden future shop. The ordinary batch is

```
q[p] = min(current non-feed shed stock[p], D[p])
```

trimmed only when its exact next engine marginal is the $1 floor. Hour zero is
the rule-derived cadence because carried inventories auto-deposit at the day
boundary; no remembered sale schedule is needed. The historical V82 claim that
same-phase opponent quantity cancels used V70's obsolete whole-batch equation;
section 59 supersedes it with the exact per-unit lockstep recurrence. The old fixed `opp_clear_round`
front-run is disabled for this variant, while exact terminal liquidation is
retained.

Outside hour zero, V82 sells only the minimum quantity required to prevent
currently known carried stock from overflowing the shared 100-item shed at the
next automatic deposit. Those units are allocated to the highest exact next
marginal revenues; separable non-increasing engine curves make that greedy
merge exact. Feed wheat is reserved by the live plan. Future opponent timing is
not credited as a benefit and remains an explicit unpromoted uncertainty; V82
is a test of guaranteed public absorption, not a claim that the two-stage
market game is solved.

All behavior is behind `market_variant="guaranteed_day_drain"`; defaults and
historical wrappers are unchanged. Four equation/structural tests prove exact
conditioning on an observed single-product shop (13 guaranteed WOOL units in
the test day), day-boundary-only batching, exact two-unit overflow release into
the highest marginal item, and removal of the thresholded endgame front-run.
The targeted market suites pass 16/16; compile and diff checks pass. V82 remains
unqualified pending the full suite, deterministic runtime/import audit and a
fresh CRN rejection screen against immutable V76.

The complete suite passes 118/118; compile and diff checks pass. The seed-24200
trace is `logs/whitebox/v82_guaranteed_drain_runtime_24200.txt`. Two independent
V82 runs returned exactly `$4,683/$130,425`, identical action SHA256
`7e95188dcd23b720ede1c3fe658e9bab474b2786f3bd98038c5a26780bc23ad7`,
and zero repeat differences; V82 differs from V76 on 670/719 actions. A direct
uncaught-agent repeat returned the same banks, proving this is the intended
policy rather than an outer safety fallback. Latency is 1.572/1.564 ms mean,
4.162/4.134 ms P95, 8.433/8.323 ms P99 and 18.871/19.317 ms maximum, with no
calls above 170 ms. Same-process V76 measured 21.943/91.452/119.744/164.518 ms
and likewise no calls above 170 ms. V82 is exactly deterministic and runtime
safe, but its extremely low own bank shows that guaranteed lower absorption
alone starves cash realization and therefore later capital/route work. Own bank
cannot decide the model; run only the fresh CRN rejection screen. Immutable
V76 remains selected.

The V82 quick rejection screen is
`logs/arena/v82_vs_v76_quick_24300.json` (simulator, seed0 24300, six seeds,
hard pool, both seats, 26 workers, 1.4 minutes). V76 and V82 mirrors are exactly
zero on 6/6 seeds, with zero errors and zero not-DONE statuses. Head-to-head
self-play is -$976,808 total, -$162,801.33/seed (SE $10,369.96, t=-15.70,
W-L 0-6). External V82 absolute paired margin is -$303,840.94 versus V76
-$113,302.50: delta -$190,538.44 (SE $9,155.78, t=-20.81, W-L 0-18),
firing 18/18.

| opponent | cells | V82 absolute paired margin | V76 absolute paired margin | delta | W-L |
|---|---:|---:|---:|---:|---:|
| multi-route | 6 | -$306,669.33 | -$95,295.67 | -$211,373.67 | 0-6 |
| frontier | 6 | -$301,711.17 | -$122,627.17 | -$179,084.00 | 0-6 |
| v111 | 6 | -$303,142.33 | -$121,984.67 | -$181,157.67 | 0-6 |
| **total** | **18** | **-$303,840.94** | **-$113,302.50** | **-$190,538.44** | **0-18** |

V82 is a decisive valid tombstone; do not run 108/288/real and do not promote.
The exact observed-shop lower drain is a valid absorption certificate, but it
is not a sufficient sale policy: retaining every unit beyond guaranteed drain
withholds the bridge cash that funds the productive capital/route system. This
is not evidence for restoring fixed-seed averages or opponent thresholds. The
next formulation must retain current-observation sale equations while imposing
a coefficient-free cash-realization boundary. Immutable V76 remains selected.

### V83 coefficient-free day-boundary market (implementation, 2026-08-28)

`whitebox/versions/v83_day_boundary_market.py` is the next principled arm after
V82's decisive cash-starvation failure. It retains V82's exact 100-item
overflow allocation and disables the same thresholded opponent front-run, but
replaces the insufficient guaranteed-drain cap with a rule-derived cash
realization boundary: at hour zero, immediately after the engine's prior
end-of-day automatic inventory deposit, sell every current non-feed shed unit.
At other hours sell only exact known overflow. Feed wheat remains reserved by
the live plan, terminal liquidation remains exact, and every sale quantity is
read directly from current private stock.

This is a deliberately myopic robust hypothesis, not a fitted pacing rule.
Same-phase opponent quantity cancels in paired value by the V70 theorem;
liquidating at the observable daily inventory boundary prevents unmodelled
future opponent timing from being credited and guarantees that yesterday's
production becomes bridge cash before the next day's capital decisions. It
does not claim an optimal multi-day market game. No fixed-seed shop average,
lead-day threshold, minimum opponent unit count, tracker holding estimate or
target identity is consulted in the V83 sale path.

All behavior is isolated behind
`market_variant="day_boundary_liquidation"`; V76 and historical defaults are
unchanged. Two additional tests prove exact liquidation of all non-feed stock
and structurally fail if the legacy `_sell_batch` model is reached. Together
with V82's observed-shop, overflow and front-run tests, the targeted market
suites pass 18/18; compile and diff checks pass. V83 is unqualified pending the
full suite, deterministic runtime/import audit and a fresh CRN rejection screen
against immutable V76.

The complete suite passes 120/120; compile and diff checks pass. The seed-24400
trace is `logs/whitebox/v83_day_boundary_runtime_24400.txt`. Two independent
V83 runs returned exactly `$76,727/$155,612`, identical action SHA256
`06e61bf4504f977e08905e5792bb78dc01d093f8d35fc6657137061141c987b6`,
and zero repeat differences. V83 differs from V76 on only 4/719 actions; V76
banks were `$76,728/$155,611`. V83 latency is 26.439/26.302 ms mean,
131.254/129.235 ms P95, 160.620/160.716 ms P99 and 183.881/182.398 ms max,
with one call above 180 ms in each repeat. Same-process V76 measured
26.494/129.129/162.936/182.451 ms and also one call above 180 ms. The host is
slightly beyond the soft target on all arms, while V83 adds no material tail
and remains far below the engine timeout. V83 is exactly deterministic and
earns a fresh quick CRN firing/rejection screen; immutable V76 remains selected.

The V83 quick rejection screen is
`logs/arena/v83_vs_v76_quick_24500.json` (simulator, seed0 24500, six seeds,
hard pool, both seats, 26 workers, 2.4 minutes). Both mirrors are exactly zero
on 6/6 seeds, and all episodes complete with zero errors and zero not-DONE
statuses. Head-to-head self-play is nearly inert at -$42 total, -$7.00/seed
(SE $6.12, t=-1.14, W-L-T 3-2-1). External V83 absolute paired margin is
-$111,124.28 versus V76 -$111,733.44: nominal delta +$609.17
(unconditional SE $667.78, t=0.91). Only 13/18 cells fire; conditional delta
is +$843.46 (SE $916, t=0.92) with W-L 4-9 and five ties.

| opponent | cells | V83 absolute paired margin | V76 absolute paired margin | delta | W-L | firing |
|---|---:|---:|---:|---:|---:|---:|
| multi-route | 6 | -$111,905.17 | -$112,867.50 | +$962.33 | 1-5 | 6/6 |
| frontier | 6 | -$111,369.00 | -$112,276.67 | +$907.67 | 2-2 | 4/6 |
| v111 | 6 | -$110,098.67 | -$110,056.17 | -$42.50 | 1-2 | 3/6 |
| **total** | **18** | **-$111,124.28** | **-$111,733.44** | **+$609.17** | **4-9** | **13/18** |

V83 is a valid quick-rejected regression: the small positive mean is
blowout-sensitive while the policy loses more than twice as many firing cells
as it wins. Do not run 108/288/real and do not promote. Together V82 and V83
bound this market simplification: guaranteed public drain alone destroys
bridge cash, while immediate day-boundary liquidation is almost inert and
reduces robust paired win probability. Preserve the exact observed-shop drain,
overflow allocator and coefficient-free liquidation tests as equation assets,
but the next market arm must solve cash value and inventory option value in one
multi-day objective rather than choosing either extreme.

The closeout audit used a fresh full seed-24600 V83 simulator episode against
an inert public-observation-only agent and returned banks `$102,047/$3,000`.
Production import closure is `FORBIDDEN_IMPORTED []` across replay/tape/
opening/weight/schedule/search/mining/behavior paths. The complete suite passes
120/120; compile and diff checks pass. V76's exact mirror confirms the opt-in
market variants did not alter the immutable baseline. No external write or
Kaggle submission occurred, and unrelated dirty work remains preserved.

### V84 conserved-opponent robust cash/capital market (implementation, 2026-08-28)

`whitebox/versions/v84_robust_cash_market.py` isolates the next cash/inventory
coupling defect exposed by V82/V83. V83 realizes yesterday's non-feed inventory
at the exact hour-zero boundary, but the inherited capital master values cash
before those sales and emits hires/assets before them. Consequently current
stock cannot finance even a rigorously safe same-phase productive purchase.

For V84's live day-boundary sale vector `q[p]`, current book `I[p]`, and one
opponent hidden-shed allocation `h[p]`, the guaranteed cash certificate is

```
C(q) = min_(h[p] >= 0, sum_p h[p] <= shedCapacity)
       sum_p R(q[p], inventory_after_sale(I[p], h[p])).
```

Every integer allocation of the single exact 100-item opponent shed is solved
by a bounded min-plus dynamic program. It is not duplicated independently per
product. Opponent units sold at the $1 floor do not add book inventory, exactly
matching the engine. Our requested sale quantities are capped by current live
shed stock and the ten-order queue before certification. The bound assumes the
opponent sells its adversarial allocation before every one of our product
orders, so it is safe in both seats and does not require an opponent policy,
tracker, tape or target identity.

Only `ordinary_bundle_master_cash_sales_deterministic` adds `C(q)` to the
capital cash budget. Its emitted queue is `certified sales -> prerequisite
product buys -> hires -> selected assets`, so the guaranteed cash physically
exists before any dependent spend. Sale orders and hires still consume their
exact market slots; asset cash, one-time land activation, route feasibility and
V76's exact selected-set nonlinear objective are unchanged. The master receives
`deadline=None`; its new DP is bounded by at most nine sellable products and
the engine shed capacity. V83, V76 and all historical compose/solver paths keep
their prior order and cash semantics.

Five new equation/structural tests prove equality with exhaustive conserved
allocation on a two-product nonlinear book, cap fictional sale quantities at
live shed stock, front-load every certified sale before spending, and remove an
already-expired clock from the V84 capital master. The fifth integration test
proves that the route master's maximum cash budget is current cash plus exactly
the independently computed certificate. The targeted market/capital suite
passes 42/42. The complete white-box suite passes 125/125; compile and diff
checks pass. On seed24700's initial empty shed, V83 and V84 correctly emit the
same action because no sale cash exists. V84 is unqualified pending the
deterministic runtime/import audit and a fresh CRN screen against immutable V76.

The full deterministic/runtime audit is
`logs/whitebox/v84_robust_cash_runtime_24800.txt` (simulator seed24800 versus
multi-route). Two independent V84 runs return exactly `$41,834/$95,199`, the
same action SHA256
`e09a628ba2db55838c379998e8e535d1e9c3818d4dcf302ed222ba4eb31918bf`,
and zero differences over 719 actions. V84 differs from V76 on 635/719 actions,
so the certified bridge cash causes a material capital/route cascade rather
than another nearly inert sale arm. Same-process V76 returns `$27,915/$59,212`.
The diagnostic absolute margins are therefore -$53,365 for V84 and -$31,297
for V76; this single seed is negative but is not qualification evidence.

V84 latency is 21.487/21.541 ms mean, 91.910/90.895 ms P95,
131.016/132.778 ms P99 and 166.178/166.452 ms max. Same-process V76 is
20.588/90.420/154.369/169.501 ms. No call in any arm reaches 170 ms or the
180 ms soft target. V84 is exactly deterministic and runtime-safe on this
trace; its high firing rate requires the planned fresh paired rejection gate.

The production import-closure audit used a fresh full seed25000 simulator
episode against an inert public-observation-only agent and returned banks
`$99,386/$3,000`. It reports `FORBIDDEN_IMPORTED []` across replay/tape/
opening/weight/schedule/search/mining/behavior paths. This is a runtime closure
check, not evidence of gameplay quality.

The fresh V84 quick rejection screen is
`logs/arena/v84_vs_v76_quick_24900.json` (simulator, seed0 24900, six seeds,
hard pool, both seats, 26 workers, 2.5 minutes). Both same-version mirrors are
exactly zero on all 6/6 seeds; all 108 episodes complete with zero errors and
zero not-DONE statuses. Head-to-head V84 versus V76 is favorable but
underpowered: +$27,202 total, +$4,533.67/seed (SE $3,331.57, t=1.36), paired
W-L 5-1 and episode W-L 8-4.

The external pool gives the opposite and decision-relevant result. V84's
absolute paired margin is -$125,328.67 versus V76 -$117,835.89: delta
-$7,492.78 per paired cell (SE $4,031.93, t=-1.86), with all 18/18 cells
firing and W-L 9-9. Every opponent row has a negative mean:

| opponent | cells | V84 absolute paired margin | V76 absolute paired margin | delta | W-L | firing |
|---|---:|---:|---:|---:|---:|---:|
| multi-route | 6 | -$123,311.50 | -$109,850.83 | -$13,460.67 | 2-4 | 6/6 |
| frontier | 6 | -$124,502.33 | -$121,138.67 | -$3,363.67 | 4-2 | 6/6 |
| v111 | 6 | -$128,172.17 | -$122,518.17 | -$5,654.00 | 3-3 | 6/6 |
| **total** | **18** | **-$125,328.67** | **-$117,835.89** | **-$7,492.78** | **9-9** | **18/18** |

V84 is a valid quick-rejected tombstone; do not run 108/288/real and do not
promote. The screen is not merely low-firing noise: the change fires in every
external cell, degrades absolute robust paired margin on every pool row, and
is almost two standard errors negative in aggregate. The favorable self-play
row is preserved and is insufficient to override the external CRN evidence.
The exact conserved-sale cash certificate and physical sale-before-spend queue
remain valid equation assets. What failed is exposing the capital master to
the entire day-boundary liquidation vector. The next isolated hypothesis
should test the phase correction on the already-selected V76 sale vector,
without simultaneously replacing inventory timing with sell-all liquidation.
Immutable V76 remains selected.

### V85 selected-sales phase-correct cash (implementation, 2026-08-28)

`whitebox/versions/v85_selected_sales_cash.py` isolates the valid V84 cash
certificate from the rejected V83 sell-all timing hypothesis. It is
behaviorally V76 except that the live sale orders V76 already selected are
valued by `robust_sale_cash` and physically emitted before dependent spending.
It does not opt into `day_boundary_liquidation`, invent any extra sale, change
a sale quantity, or alter the current-shop/future-shop analytic market model.

The exact feasibility equation, single conserved opponent shed, floor rule,
ten-slot limit, live-stock cap and deterministic bounded solver are therefore
identical to V84. The only causal variable is whether already-selected sale
cash may fund later orders in its actual market phase. V76 and all historical
wrappers remain immutable. Existing V84 tests cover the equation and the
sale-before-spend integration. The complete suite passes 125/125; compile and
diff checks pass. V85 is unqualified pending runtime/determinism/import closure
and fresh CRN screening against V76.

The V85 deterministic/runtime trace is
`logs/whitebox/v85_selected_sales_runtime_25100.txt` (simulator seed25100
versus multi-route). Both independent V85 runs return exactly
`$41,244/$76,172`, identical action SHA256
`d4601ec941a27a2d13960ed020654d741cc37b76d2921c592847f66212310b13`,
and zero repeat differences. V85 differs from V76 on 634/719 actions; moving
existing sales ahead of spending changes within-phase market order and the
subsequent capital/route state, so this is not an inert budget patch.
Same-process V76 returns `$37,168/$69,577`; diagnostic margins are -$34,928
and -$32,409 respectively, a one-seed negative that is not qualification
evidence.

V85 measures 22.478/22.532 ms mean, 82.101/82.849 ms P95,
139.084/137.230 ms P99 and 183.318/182.741 ms max. One call in each repeat
exceeds 170 and the 180 ms soft target; V76 measures
20.879/90.455/131.734/161.026 ms with no such call. V85 is exactly
deterministic and remains far below the engine timeout, but its repeatable
2.7-3.3 ms soft misses are a promotion risk that paired gameplay evidence
cannot erase. It receives one fresh quick rejection screen before closeout.

The V85 quick rejection screen is
`logs/arena/v85_vs_v76_quick_25200.json` (simulator, seed0 25200, six seeds,
hard pool, both seats, 26 workers, 2.5 minutes). Both same-version mirrors are
exactly zero on 6/6 seeds; all 108 episodes complete with zero errors and zero
not-DONE statuses. Head-to-head again favors the phase-correct arm: +$41,592
total, +$6,932/seed (SE $4,050.78, t=1.71), paired W-L 4-2 and episode W-L
8-4.

External evidence again reverses the self-play row. V85 absolute paired margin
is -$128,258.33 versus V76 -$122,663.22: delta -$5,595.11 (SE $5,395.45,
t=-1.04), firing 18/18 with W-L 7-11. Every pool row is negative:

| opponent | cells | V85 absolute paired margin | V76 absolute paired margin | delta | W-L | firing |
|---|---:|---:|---:|---:|---:|---:|
| multi-route | 6 | -$137,961.83 | -$129,783.50 | -$8,178.33 | 1-5 | 6/6 |
| frontier | 6 | -$124,280.83 | -$120,994.83 | -$3,286.00 | 4-2 | 6/6 |
| v111 | 6 | -$122,532.33 | -$117,211.33 | -$5,321.00 | 2-4 | 6/6 |
| **total** | **18** | **-$128,258.33** | **-$122,663.22** | **-$5,595.11** | **7-11** | **18/18** |

V85 is a valid tombstone; do not run 108/288/real and do not promote. It
degrades robust paired margin on every opponent row, loses 61.1% of firing
cells, and independently misses the runtime soft target in both deterministic
repeats. V84/V85 together show that merely making sale cash available to the
existing one-step capital objective drives a favorable self-play response but
an adverse external-market/capital response whether sales are sell-all or the
selected V76 vector. Preserve `robust_sale_cash` as an exact feasibility
primitive; do not attach it to the current capital objective again without a
joint multi-day inventory-option and opponent-relative objective. Immutable
V76 remains selected.

V85 closeout used a fresh full seed25300 simulator episode against an inert
public-observation-only agent and returned `$95,914/$3,000` with
`FORBIDDEN_IMPORTED []` across replay/tape/opening/weight/schedule/search/
mining/behavior paths. The final complete white-box suite passes 125/125;
compile and diff checks pass. No historical wrapper was edited, no external
write or Kaggle submission occurred, and unrelated dirty work remains
preserved.

### V86 current-observation-only market timing (implementation, 2026-08-28)

`whitebox/versions/v86_observation_only_market.py` isolates the remaining
unproved opponent-timing branches in immutable V76. The current public farm
does not reveal the opponent shed. For the same public observation, every
hidden allocation satisfying

```
h[item] >= 0 integer,  sum_item h[item] <= shedCapacity
```

is physically compatible, including stock sellable in the current market
phase and zero stock. Therefore `719-(ceil(animals/workers)+1)` is not a bound
on their liquidation time: it omits existing hidden shed stock, worker and
animal positions, yield readiness, HARVEST/PICKUP, return travel and DROP.
Likewise a threshold reconstructed from earlier market deltas is not part of
the current observation. Neither can support a guaranteed front-run decision.

Only `market_variant="observation_only_timing"` disables both consumers: the
mid-game `earliest_sellable`/tracker boost inside `_sell_batch` and the
terminal `opp_clear_round` insertion. V86 otherwise uses exactly V76's sale
quantities, live observed market book, shop-conditioned analytic model,
acquisitions, nonlinear route/capital objective and state-derived terminal
delivery rescue. It introduces no replacement sale cadence, coefficient,
opponent identity or memory-dependent fallback. Historical and V76 calls keep
their prior semantics.

Two structural tests prove the variant passes `opponent_timing=False` into the
ordinary batch path and suppresses the terminal front-run even in the public
animal-count state that triggers V76. The market suite passes 12/12 and the
complete white-box suite passes 127/127; compile and diff checks pass. V86 is
unqualified pending deterministic runtime/import audit and a fresh CRN screen
against immutable V76.

The deterministic runtime audit is
`logs/whitebox/v86_observation_only_runtime_25400.txt` (simulator seed25400
versus multi-route). Two independent V86 runs and same-process V76 all return
exactly `$69,378/$140,006`, action SHA256
`814b836a1926707adae7ea0441aad5f879de49424fd7c516e2948c0947cd61bf`,
and zero action differences over 719 calls. This seed does not enter either
removed timing branch, so it is an identity/runtime diagnostic rather than
gameplay evidence. V86 measures 22.679/22.741 ms mean,
95.483/95.197 ms P95, 122.259/121.819 ms P99 and 138.394/140.243 ms max;
V76 measures 22.732/95.349/120.862/138.255 ms. No call reaches 170 ms or the
180 ms soft target. V86 is exactly deterministic and adds no runtime risk on
this trace; a fresh multi-seed paired screen must establish firing.

The fresh V86 quick screen is
`logs/arena/v86_vs_v76_quick_25500.json` (simulator, seed0 25500, six seeds,
hard pool, both seats, 26 workers, 2.4 minutes). V76's identity mirror and
V86's candidate mirror are exactly zero on 6/6 seeds; all 108 episodes finish
with zero errors and zero not-DONE statuses. Direct self-play fires on 4/6
seeds and is +$477 total, +$79.50/seed (SE $41.62, t=1.91), paired W-L-T
4-0-2 and episode W-L-T 7-3-2.

V86 fires in every external cell. Its absolute paired margin is -$99,603.72
versus V76 -$100,552.72: delta +$949.00 (SE $232.10, t=4.09), W-L 18-0.
Every hard-pool row improves:

| opponent | cells | V86 absolute paired margin | V76 absolute paired margin | delta | W-L | firing |
|---|---:|---:|---:|---:|---:|---:|
| multi-route | 6 | -$97,530.67 | -$97,890.00 | +$359.33 | 6-0 | 6/6 |
| frontier | 6 | -$100,835.00 | -$101,778.00 | +$943.00 | 6-0 | 6/6 |
| v111 | 6 | -$100,445.50 | -$101,990.17 | +$1,544.67 | 6-0 | 6/6 |
| **total** | **18** | **-$99,603.72** | **-$100,552.72** | **+$949.00** | **18-0** | **18/18** |

This is strong but still rejection-only quick evidence. Do not promote or
claim a qualified improvement. The unchanged V86 earns a disjoint 18-seed x
six-opponent 108-cell standard simulator gate against immutable V76. Only an
exact-mirror result with credible paired direction can justify 288/real.

The valid V86 standard gate is
`logs/arena/v86_vs_v76_standard108_25600.json` (simulator, seed0 25600,
18 disjoint seeds x six standard opponents, both seats, 26 workers,
8.8 minutes). V76 and V86 mirrors are exactly zero on 18/18 seeds; all 540
episodes complete with zero errors and zero not-DONE statuses. Self-play fires
on 6/18 seeds and is +$881 total, +$48.94/seed (SE $25.72, t=1.90), W-L-T
6-0-12.

External V86 absolute paired margin is -$112,987.03 versus V76 -$113,261.02:
delta +$273.99 (SE $121.60, t=2.25). It fires in 82/108 cells; conditional
delta is +$360.87 (SE $159, t=2.27), W-L 68-14 with 26 inert ties. Every
opponent mean is positive:

| opponent | cells | V86 absolute paired margin | V76 absolute paired margin | delta | firing W-L-T |
|---|---:|---:|---:|---:|---:|
| multi-route | 18 | -$98,435.17 | -$98,443.50 | +$8.33 | 10-6-2 |
| frontier | 18 | -$119,072.33 | -$119,243.33 | +$171.00 | 11-2-5 |
| v111 | 18 | -$115,079.67 | -$116,130.22 | +$1,050.56 | 13-0-5 |
| 3000-socre | 18 | -$119,544.44 | -$119,727.72 | +$183.28 | 12-3-3 |
| rank-your-agent | 18 | -$112,497.33 | -$112,560.67 | +$63.33 | 10-2-6 |
| strong-barnyard | 18 | -$113,293.22 | -$113,460.67 | +$167.44 | 12-1-5 |
| **total** | **108** | **-$112,987.03** | **-$113,261.02** | **+$273.99** | **68-14-26** |

This replicates the quick paired-win direction on a broader distribution and
passes the existing 108-cell evidence gate. It still does not authorize
promotion: removing opponent timing changes a production market decision in
76% of cells. Run the prescribed independent 48-seed x six-opponent 288-cell
simulator confirmation on V86 unchanged. A real-engine gate is justified only
if that larger result retains exact mirrors and credible margin/win direction.

The required independent V86 simulator confirmation is
`logs/arena/v86_vs_v76_standard288_25700.json` (simulator, seed0 25700,
48 disjoint seeds x six standard opponents, both seats, 26 workers,
22.3 minutes). V76 and V86 mirrors are exactly zero on 48/48 seeds; all 1,440
episodes complete with zero errors and zero not-DONE statuses. Self-play is
+$2,948 total, +$61.42/seed (SE $34.46, t=1.78), W-L-T 23-4-21 and episode
W-L-T 45-25-26.

External V86 absolute paired margin is -$114,245.36 versus V76 -$114,549.27:
delta +$303.90 (SE $60.31, t=5.04). The arm fires in 223/288 cells;
conditional delta is +$392.48 (SE about $77, t=5.11), W-L 188-35 with 65
inert ties. Every standard opponent again has a positive mean and a positive
firing-cell win count:

| opponent | cells | V86 absolute paired margin | V76 absolute paired margin | delta | firing W-L-T |
|---|---:|---:|---:|---:|---:|
| multi-route | 48 | -$108,156.58 | -$108,472.52 | +$315.94 | 37-5-6 |
| frontier | 48 | -$116,642.48 | -$116,937.79 | +$295.31 | 33-2-13 |
| v111 | 48 | -$116,457.52 | -$116,913.98 | +$456.46 | 32-3-13 |
| 3000-socre | 48 | -$120,716.98 | -$120,997.94 | +$280.96 | 26-11-11 |
| rank-your-agent | 48 | -$112,934.44 | -$113,231.69 | +$297.25 | 33-5-10 |
| strong-barnyard | 48 | -$110,564.19 | -$110,741.69 | +$177.50 | 27-9-12 |
| **total** | **288** | **-$114,245.36** | **-$114,549.27** | **+$303.90** | **188-35-65** |

The disjoint 288-cell block confirms both robust paired margin and win
probability, with no opponent-specific sign reversal. V86 has met the
simulator evidence sequence but remains unpromoted. Run the unchanged arm
through a fresh six-seed, both-seat, six-opponent real-engine gate; statuses,
mirrors and timeout/invalid actions are hard validity conditions. Only after
that gate may the production import/determinism audit consider selection.

The first real-gate invocation,
`logs/arena/v86_vs_v76_real6_25800.json`, is invalid environment evidence. It
used system `python3`, where `kaggle_environments` is not installed, so all 72
attempted episodes errored with `ModuleNotFoundError`, no paired cell existed,
and the arena correctly aborted. Do not use any displayed zero aggregate. The
documented `/home/yilewang/kagg-env/bin/python` imports the installed engine;
rerun the unchanged V86/V76 seed block through that interpreter and preserve
this failed-invocation log as a harness tombstone.

The valid real-engine gate is
`logs/arena/v86_vs_v76_real6_25800_venv_retry.json`, run with
`/home/yilewang/kagg-env/bin/python` (installed Kaggriculture engine, seed0
25800, six disjoint seeds x six standard opponents, both seats, 12 workers,
6.7 minutes). V76 and V86 mirrors are exactly zero on 6/6 seeds. All 180 games
finish `DONE/DONE`: zero errors, zero not-DONE statuses, no timeout and no
invalid action. Real self-play is statistically neutral at -$61 total,
-$10.17/seed (SE $143.41, t=-0.07), W-L-T 3-1-2; episode W-L is 7-5.

External real V86 absolute paired margin is -$110,125.75 versus V76
-$110,588.44: delta +$462.69 (SE $114.95, t=4.03). The arm fires in 29/36
cells; conditional delta is +$574.38 (SE about $135, t=4.26), W-L 27-2 with
seven inert ties. Every opponent row remains positive:

| opponent | cells | V86 absolute paired margin | V76 absolute paired margin | delta | firing W-L-T |
|---|---:|---:|---:|---:|---:|
| multi-route | 6 | -$91,713.17 | -$92,245.67 | +$532.50 | 5-1-0 |
| frontier | 6 | -$113,567.83 | -$114,301.83 | +$734.00 | 5-0-1 |
| v111 | 6 | -$119,072.17 | -$119,475.50 | +$403.33 | 3-1-2 |
| 3000-socre | 6 | -$112,038.33 | -$112,319.67 | +$281.33 | 5-0-1 |
| rank-your-agent | 6 | -$111,455.33 | -$111,770.67 | +$315.33 | 6-0-0 |
| strong-barnyard | 6 | -$112,907.67 | -$113,417.33 | +$509.67 | 3-0-3 |
| **total** | **36** | **-$110,125.75** | **-$110,588.44** | **+$462.69** | **27-2-7** |

The real engine agrees with the quick, standard108 and independent
standard288 external directions in both margin and paired win probability.
Direct real self-play margin is neutral and is not concealed. V86 has met the
prescribed gameplay evidence sequence, but selection remains pending the final
full-suite, fresh determinism, production import-closure, strict source and
historical-wrapper audits. No external submission is authorized.

The final strict-source audit found one inherited environment seam not covered
by V76's pin: `WB_ANIMAL_BRIDGE` was read dynamically inside acquisition
proposal generation. V86 now passes an explicit `bridge_reserve=False` only
for `observation_only_timing`; historical callers retain their old default and
environment semantics. Its wrapper also pins computed-plan feed cover/max to
the qualified engine-policy values 2/16. Two new tests prove both pins. The
complete suite passes 129/129; compile and diff checks pass.

This post-gate hardening is byte-for-byte behavior preserving under the gate
environment. Before and after the change, fresh seed25900 V86 versus
multi-route returns `$35,843/$93,540` and action SHA256
`3710bb9fa4faad242fb5019068dc5727a1da3452b1e34f362b4eed4f319e98b5`.
A fresh process loaded with adversarial `WB_FEED_DAYS=99`, `WB_FEED_MAX=999`,
`WB_ANIMAL_BRIDGE=1`, `WB_MARKET_TIMING=1`, `WB_FRONTRUN_MIN_UNITS=1` and
`WB_FRONTRUN_LEAD=99` returns the same banks, hash and 0/719 action
differences. Thus the qualification logs retain the exact action semantics
while those environment values can no longer select a V86 policy.

Two independent clean seed25900 V86 episodes return the same banks/hash and
zero repeat action differences. The full runtime import audit reports
`FORBIDDEN_IMPORTED []` across replay/tape/opening/weight/schedule/search/
mining/behavior paths. Immutable V76's wrapper hash is
`4a4c797f95af70b2f45e449566e11cf932f05899109a45d5458f71d55252f0e6`;
it was not edited. The V76 identity controls were exact in every valid V86
gate, independently confirming historical baseline behavior.

**V86 is now the selected immutable strict-white-box baseline.** This is a
local model selection, not a Kaggle submission. Qualification rests on the
current-observation non-identifiability theorem, deterministic/runtime-safe
execution, valid standard108 (+$273.99, firing W-L 68-14), independent
standard288 (+$303.90, W-L 188-35), and real-engine (+$462.69, W-L 27-2)
external results. All valid mirrors are exact, all real games are `DONE/DONE`,
and every opponent row is positive in both larger gates. Direct real self-play
is neutral at -$61 total and remains an explicit caveat. V76, V69 and V59 are
immutable historical comparison baselines. No external write or submission
occurred, and unrelated dirty user work remains preserved.

The next high-value unresolved mechanism returns to the joint multi-day
cash/inventory-option objective identified by V84/V85. Do not reconnect sale
cash to the one-step capital score or revive an opponent timing threshold. A
new arm must put retained shed stock, certified cash, daily service, order
slots and opponent-relative multi-day market value in one structurally bounded
selected-set objective, compare against immutable V86, and retain the exact
sale-cash DP only as a feasibility constraint.

### V87 certified one-step retained-inventory option (implementation and neutral gate, 2026-08-28)

`whitebox/versions/v87_one_step_inventory_option.py` is an isolated V86 child.
It tests the smallest inventory-option correction which cannot repeat V84/V85's
one-step sale-cash/capital coupling. The ordinary V86 capital master composes
its complete executable queue first. Only then may V87 remove existing-stock
sales, so the freed slots and unrealized cash cannot select a current hire,
seed, animal, land purchase or product buy. Same-turn DROP sales are merged
after this post-process and retain V86 semantics. V86 and every historical
wrapper remain unchanged.

For aggregate executable live-shed sale quantities `q[p]`, current public book
`I[p]`, exact current-step public town drain `d[p]`, and one conserved opponent
hidden-shed allocation `h[p]`, V87 evaluates the bundle option

```
G(q) = min_(h[p] >= 0, sum_p h[p] <= shedCapacity)
       sum_p [R(q[p], inventory_after_sale(I[p] - d[p], h[p]))
              - R(q[p], inventory_after_sale(I[p], h[p]))].
```

The same `h` is used in both time alternatives and all products share the exact
public `shedCapacity`; opponent units sold at the $1 floor do not add book
inventory. Quantities are aggregated and capped by current live shed stock and
the ten-order queue before pricing. A bounded min-plus DP solves every integer
allocation. Public town consumption follows the current market phase, so
`market_model.town_take_bounds(step, step+1)` is exact; if its endpoints ever
differ, V87 refuses the option. Monotonic market curves make waiting weakly
better for every allocation. V87 defers only when `G(q) >= 0` and the
zero-hidden allocation is strictly better, which is the standard strict-
dominance condition (no state is worse and at least one is better). A
floor-saturating hidden allocation can correctly make `G(q) == 0`.

Execution guards make the option a one-transition certificate rather than a
sale-timing heuristic. The current queue must contain sales only, current money
must already cover `plan.cash_floor` (one computed feed/service reserve), no
unit may DROP this phase, current shed occupancy must satisfy the observed
capacity, the transition may not be daily rollover, and it may not cross V86's
endgame boundary. On the next public observation V86 recomputes the whole queue;
there is no remembered commitment, policy tape, opponent timing threshold or
target identity. The variant also inherits V86's explicit animal-bridge-off,
observation-only midgame sale sizing, terminal-front-run-off, and pinned feed
cover/max semantics.

Five equation/guard tests were added alongside the implementation: exact
equality with exhaustive shared-capacity allocation for a nonlinear MILK/WOOL
bundle; a sale-only strict-dominance firing case; no-drain and current-spend
identity; DROP/rollover/cash-floor vetoes; and preservation of V86's
observation-only timing switch. The complete suite passes 134/134; targeted
market tests pass 18/18; compile checks pass.

The deterministic/runtime record is
`logs/whitebox/v87_one_step_inventory_runtime_26000.txt` (simulator seed26000
versus multi-route). This seed does not fire: immutable V86 and two independent
V87 runs all return `$81,318/$159,794`, identical action SHA256
`deabd40302665df4458cb40cabbb1c8014fb434b830bda198fadec3fd80ac72c`,
zero repeat differences and 0/719 V87-versus-V86 differences. V87 repeat means
are 24.276/24.310 ms, P95 107.437/107.889 ms, P99 158.243/158.932 ms and maxima
194.101/195.685 ms. Immutable V86 is behavior-identical and measures 24.277 ms
mean, 107.222 ms P95, 158.533 ms P99 and 194.796 ms max. Both arms have two
calls at or above 170 ms and baseline itself has two above 180 ms; this trace
therefore misses the soft target for an inherited route tail but remains far
below the engine's one-second timeout. V87 causes no tail on this identity
trace. A maximum-shape nine-product/capacity-100 DP microbenchmark is bounded at
6.309 ms mean, 6.365 ms P95 and 8.865 ms max over 100 calls.

The fresh quick screen is
`logs/arena/v87_vs_v86_quick_26100.json` (simulator, seed0 26100, six seeds,
hard pool, both seats, 26 workers, 2.5 minutes). Both mirrors are exactly zero;
all 108 episodes finish with zero errors/not-DONE. Only 1/18 external paired
cells fires and loses `$144`: candidate absolute paired margin is
`-$119,736.61` versus V86 `-$119,728.61`, delta `-$8.00` (SE `$7.77`,
t=-1.03), conditional W-L 0-1. Self-play is +$2 total with one firing seed.
This is valid but too sparse to reject or qualify, so V87 advanced to the
existing 108-cell gate.

The valid standard gate is
`logs/arena/v87_vs_v86_standard108_26200.json` (simulator, seed0 26200,
18 seeds, six-opponent standard pool, both seats, 26 workers, 8.6 minutes).
Both V86 and V87 mirrors are exact on all 18 seeds; all 540 episodes complete
with zero errors and zero not-DONE statuses. Candidate absolute external paired
margin is `-$112,172.57` versus V86 `-$112,168.75`: delta `-$3.82` per cell
(SE `$7.91`, t=-0.48). Only 14/108 cells fire; conditional delta is `-$29.50`
with W-L 8-6 (94 ties). Direct self-play is -$248 total, W-L-T 1-1-16.

| opponent | cells | V87 absolute paired margin | V86 absolute paired margin | delta | W-L | firing |
|---|---:|---:|---:|---:|---:|---:|
| multi-route | 18 | -$114,362.22 | -$114,304.33 | -$57.89 | 0-3 | 3/18 |
| frontier | 18 | -$112,130.67 | -$112,128.83 | -$1.83 | 1-1 | 2/18 |
| v111 | 18 | -$111,984.94 | -$112,001.39 | +$16.44 | 3-0 | 3/18 |
| 3000-socre | 18 | -$123,309.33 | -$123,308.72 | -$0.61 | 2-1 | 3/18 |
| rank-your-agent | 18 | -$107,786.28 | -$107,784.00 | -$2.28 | 0-1 | 1/18 |
| strong-barnyard | 18 | -$103,462.00 | -$103,485.22 | +$23.22 | 2-0 | 2/18 |
| **total** | **108** | **-$112,172.57** | **-$112,168.75** | **-$3.82** | **8-6** | **14/108** |

V87 is a valid neutral tombstone. It has no positive margin signal, loses every
firing multi-route cell, has mixed opponent rows, and exercises only 14 cells;
there is inadequate confidence for promotion and no evidence-based reason to
spend a 288-cell or real-engine gate. **V86 remains the selected immutable
strict-white-box baseline.** The equation is retained as a proved local option,
but the evidence closes one-step drain delay as a sufficient solution. Do not
tune a drain threshold or expand it into another local timing rule.

The final fresh seed26300 closure episode versus an inert public-observation-
only opponent returns `$93,934/$3,000`, action SHA256
`ac781c09a75fcbb4b38d50c0810dfc236e4261fc71e67d9218b225b68b6328b1`,
and `FORBIDDEN_IMPORTED []` across replay/tape/opening/weights/schedule/search/
mining/behavior modules. Adversarial legacy environment settings return the
same banks and hash. V86's wrapper SHA256 remains
`1b9993e45b4f67cfdcc5cf653778012442657c432292a497c4582072d9142b0e`;
it was not edited. No external write or Kaggle submission occurred, and
unrelated dirty user work remains preserved.

The next high-value unresolved mechanism is still the full structurally bounded
multi-day selected-set objective, not another one-step patch. It must jointly
carry retained shed quantities, exact nonlinear aggregate sale values,
`robust_sale_cash` as feasibility only, daily feed/service cash, shed occupancy,
market-order slots and opponent-relative terminal value. V87 shows that exact
public drain creates only small mixed one-step effects when productive-cash and
future service options are held fixed.

A final post-edit immutable-baseline control reran V86 on its recorded seed25900
multi-route matchup and again returned exactly `$35,843/$93,540`. The local
audit's action-hash serialization differs from the earlier promotion audit, so
only the exact bank identity is asserted here; source SHA256 and arena identity
controls provide the byte/action-preservation checks above.

### V88 exact certified terminal inventory master (implementation and neutral gate, 2026-08-28)

`whitebox/versions/v88_terminal_inventory_master.py` isolates an exact boundary
case of the unresolved multi-day objective against immutable V86. It changes
only the branch where V86's state-derived complete terminal route certificate
strictly beats the live general-route upper bound. That certificate has already
proved every remaining action and output after the last production refresh.
Consequently no market purchase or future service action can create value in
this branch: productive capital, feed, crew and land-activation terms are
identically zero, rather than approximated or assigned a coefficient.

For each sellable product `p`, the certificate supplies total terminal output
`Q[p]`, the current observation supplies book `I[p]`, and the new decision is
the integer current sale `q[p]`. The final action is derived from public config
as `episodeSteps - 2`. The objective term is

```
V[p](q) = R(q[p], I[p])
          + R(Q[p] - q[p],
              inventory_after_sale(I[p], q[p]) - d[p]),
```

where `d[p]` is the analytic lower town drain from the current market phase to
the final one. At terminal time all standard shop slots are already public, so
the lower/upper interval is normally exact; retaining the lower endpoint makes
the formulation robust to nonstandard configurations. `R` is
`econ.sell_revenue` over the entire same-item quantity, and the exact $1-floor
inventory rule is applied after the current sale.

The original V88 report claimed that phase-by-phase paired-seat cancellation
removed opponent quantity. The 2026-09-01 engine audit in section 59 disproves
that claim: shared order slots clear per unit in lockstep. V88 therefore remains
a reproducible own-cash terminal tombstone, not a robust paired solver. No
hidden stock, policy timing, tracker, target identity or tape is consulted by
that historical objective.

A bounded integer DP combines product choices using states `(current units
sold, current product slots)`. It maximizes `sum_p V[p](q)`, enforces at most the
engine's ten orders, and requires

```
sum(all certified terminal outputs, including non-sellable occupants)
  - sum_p q[p] <= observed shedCapacity.
```

Current availability is exactly current shed stock plus inventory executing a
same-phase DROP. If the certified future bundle cannot fit even after selling
all currently available stock, V88 falls back to V86's maximum room-releasing
sale. Exact objective ties retain more units and use fewer slots. On the
configuration-derived final action all executable current stock is sold. The
master is recomputed from each public observation and remembers no schedule.
Before the terminal certificate wins, V88 is byte-semantics-equivalent to V86,
including observation-only steady sales, bridge-off, terminal-front-run-off,
route rescue and all pinned environment switches.

Four equation/structural tests accompany the implementation: deriving a
nonstandard final action and including same-turn DROP stock; releasing exactly
the shared capacity requirement including a non-sellable COW occupant;
retaining all stock when neither value nor capacity requires a sale; and exact
equality with exhaustive two-product nonlinear quantity enumeration. The
targeted terminal suite passes 18/18. The complete suite passes 138/138 and all
edited modules compile.

The deterministic/runtime record is
`logs/whitebox/v88_terminal_inventory_runtime_26400.txt` (simulator seed26400
versus multi-route). Immutable V86 returns `$47,201/$90,111`; two independent
V88 runs return `$47,594/$90,111`, identical action SHA256
`ddbe35c5ea53e410c3f765887be01c518797bd68439b273372dafabe50415f40`,
zero repeat differences, and 15/719 differences from V86 on steps
697,699,700,703,704,707,708,709,711,712,714,715,716,717,718. The diagnostic
own-bank gain is $393 with the opponent unchanged; it is not qualification
evidence.

V88 repeats measure 23.968/23.929 ms mean, 107.870/109.095 ms P95,
169.107/169.719 ms P99, and 182.331/180.811 ms max. V86 is action-different but
shares the inherited route tail at 23.806/108.122/169.473/183.021 ms. V88 is
deterministic and far below the engine timeout, but neither arm clears the
180 ms soft target on this seed. A maximum-shape nine-product, 99-unit,
capacity-50 master takes 21.318 ms mean, 21.445 ms P95 and 39.200 ms max over
100 calls. This bounded solve adds independent promotion tail risk and is not
optimized after neutral gameplay evidence.

The fresh quick screen is
`logs/arena/v88_vs_v86_quick_26500.json` (simulator, seed0 26500, six seeds,
hard pool, both seats, 26 workers, 2.4 minutes). Mirrors are exact; all 108
episodes complete with zero errors/not-DONE. External V88 absolute paired
margin is `-$122,391.67` versus V86 `-$122,496.56`: delta `+$104.89` per cell
(SE `$109.83`, t=0.96), firing 14/18, conditional `+$134.86`, W-L 8-6. Rows
are multi-route `+$305.67` (5-1), frontier `+$185.50` (2-2) and v111
`-$176.50` (1-3). Direct self-play is adverse at -$917 total, paired W-L 1-5.
The mixed but positive external screen earned the prescribed standard108 gate.

The valid standard gate is
`logs/arena/v88_vs_v86_standard108_26600.json` (simulator, seed0 26600,
18 seeds, six-opponent standard pool, both seats, 26 workers, 8.8 minutes).
Both mirrors are exact on all 18 seeds; all 540 episodes complete with zero
errors and zero not-DONE statuses. V88 absolute external paired margin is
`-$116,167.71` versus V86 `-$116,165.29`: delta `-$2.43` per cell (SE `$41.61`,
t=-0.06). The change fires in 82/108 cells; conditional delta is `-$3.20` and
conditional W-L is exactly 41-41 with 26 inert ties. Direct self-play is
-$1,103 total, paired W-L-T 6-9-3 (mean -$61.28, SE $57.14, t=-1.07).

| opponent | cells | V88 absolute paired margin | V86 absolute paired margin | delta | W-L | firing |
|---|---:|---:|---:|---:|---:|---:|
| multi-route | 18 | -$113,535.94 | -$113,773.00 | +$237.06 | 11-4 | 15/18 |
| frontier | 18 | -$118,633.00 | -$118,591.67 | -$41.33 | 7-7 | 14/18 |
| v111 | 18 | -$113,608.89 | -$113,381.83 | -$227.06 | 3-9 | 12/18 |
| 3000-socre | 18 | -$123,470.11 | -$123,442.83 | -$27.28 | 6-7 | 13/18 |
| rank-your-agent | 18 | -$115,103.56 | -$115,080.50 | -$23.06 | 8-6 | 14/18 |
| strong-barnyard | 18 | -$112,654.78 | -$112,721.89 | +$67.11 | 6-8 | 14/18 |
| **total** | **108** | **-$116,167.71** | **-$116,165.29** | **-$2.43** | **41-41** | **82/108** |

V88 is a valid neutral tombstone. The external mean and conditional mean are
slightly negative, firing win probability is exactly 50%, three of six rows are
negative (including v111 at -$227.06), direct self-play is adverse, and the
bounded master adds measurable tail work. It has no evidence-based claim to a
288-cell or real-engine gate and is not promoted. **V86 remains the selected
immutable strict-white-box baseline.** Preserve V88's terminal equation and
tests, but do not tune product timing or capacity around these opponents.

The final fresh seed26700 closure episode versus an inert public-observation-
only opponent returns `$112,182/$3,000`, action SHA256
`574f0f4075463509162ca9971b142d2f7769b810e68e862c6f292ed77a683744`,
and `FORBIDDEN_IMPORTED []` across replay/tape/opening/weights/schedule/search/
mining/behavior modules. Hostile legacy environment settings produce the same
banks and hash. V86's wrapper source SHA256 remains
`1b9993e45b4f67cfdcc5cf653778012442657c432292a497c4582072d9142b0e`.
No external write or Kaggle submission occurred; unrelated dirty work remains
preserved.

The next unresolved mechanism is the genuinely productive part of the
multi-day selected-set objective. V87 shows one-step retained value is tiny;
V88 shows exact terminal retention is neutral. A future arm must decide sale
cash and retained stock before production closes while simultaneously proving
the selected route's daily feed/service labor, bridge cash, shed trajectory and
market slots. Reusing the existing capital certificate without changing its
rejected V77-V80 portfolio proposal is not sufficient; the sale/retention state
must enter the same selected-set marginal as executable productive work.

### V89 exact solve-local route-cost memo (runtime promotion, 2026-08-28)

The post-V88 audit found no newer evaluation logs or unrecorded model arm. It
also confirmed immutable V86 source SHA256
`1b9993e45b4f67cfdcc5cf653778012442657c432292a497c4582072d9142b0e`.
The productive cash/inventory certificate remains the highest gameplay gap,
but V88's trace showed that selected V86 itself still exceeded the 180 ms soft
target. Adding another bounded master on top of an unidentified tail would not
be runtime-safe, so V89 isolates that prerequisite before resuming economic
work.

A candidate-seat-only cProfile of immutable V86 on simulator seed26800 versus
multi-route recorded 191,177,654 calls and 70.753 profiled seconds. Capital
selection consumed 66.865 seconds; its 5,221 `joint_assign` calls made
2,365,329 `route_cost` calls consuming 54.595 seconds. The lazy nonlinear
selected-bundle heap revisits a task whenever its same-item quantity signature
changes, but each revisit recomputed the unchanged singleton cost against every
worker.

`whitebox/versions/v89_exact_route_cost_memo.py` changes only V86's capital
variant name. In `route/router.py`, that variant creates one local dictionary
inside `joint_assign`. The physical route cost is a pure function

```
C(worker, selected task multiset, committed prefix, bank-output mode),
```

so its key is the worker id, sorted multiset of in-call task identities and
the explicit prefix; bank-output mode is constant for the solve. Task identity
is never used to order, value or emit a task. The dictionary is destroyed when
the solve returns and is not shared across turns, seats or episodes. It stores
no observation feature, policy, opponent fact, coefficient or schedule. Every
feasibility check, nonlinear selected-set marginal and deterministic tie-break
is unchanged. Historical variants do not enable the flag and V86's wrapper is
byte-unchanged.

Two new structural/equation tests prove (1) memoized and ordinary masters
return the same per-worker task order and leftover order while the memo makes
strictly fewer calls, and (2) only V89's capital variant is clock-free and opts
into the cache. The complete white-box suite passes 140/140; edited modules
compile.

The exact performance/determinism record is
`logs/whitebox/v89_exact_route_cost_memo_runtime_26800.txt`. Immutable V86 and
two fresh V89 episodes all return `$36,734/$89,384` with identical 719-action
SHA256 `fde1dfc446cc47eabb3685a3c0e2033d5ba8d7b8a8ee5329586030840e7a8dd2`.
There are zero V89 repeat differences and zero V89-versus-V86 differences.

| arm | mean ms | P95 ms | P99 ms | max ms | calls >=170/180 ms |
|---|---:|---:|---:|---:|---:|
| V86 | 23.520 | 111.284 | 152.577 | 182.872 | 2 / 1 |
| V89 repeat 1 | 17.638 | 81.009 | 110.329 | 126.764 | 0 / 0 |
| V89 repeat 2 | 17.683 | 80.992 | 110.946 | 127.571 | 0 / 0 |

Repeat 1 reduces mean/P95/P99/max by 25.008%/27.205%/27.690%/30.682%.
Unlike a deadline guard, this exact finite memo cannot select a different
incumbent under load; both repeats clear the 180 ms soft target with more than
52 ms headroom and remain far below the one-second engine timeout.

The quick CRN audit is
`logs/arena/v89_vs_v86_quick_27000.json` (simulator, seed0 27000, six seeds,
three-opponent hard pool, both seats, 26 workers, 2.2 minutes). Candidate and
baseline absolute external paired margin are both `-$119,835.28`; every one of
18 external cells and all three opponent rows has exactly `$0` delta and the
arm fires 0/18. Direct paired self-play is exactly `$0` on six ties. All 108
episodes complete with exact mirrors, zero errors and zero not-DONE statuses.

Because a runtime promotion still requires the project's 108-cell floor, the
standard CRN audit is
`logs/arena/v89_vs_v86_standard108_27100.json` (simulator, seed0 27100,
18 seeds, six-opponent standard pool, both seats, 26 workers, 7.7 minutes).
Candidate and baseline absolute external paired margin are identically
`-$113,110.92`; delta is exactly `$0`, firing is 0/108, and all six rows are
identical:

| opponent | cells | V89 absolute paired margin | V86 absolute paired margin | delta | firing |
|---|---:|---:|---:|---:|---:|
| multi-route | 18 | -$112,069.50 | -$112,069.50 | $0 | 0/18 |
| frontier | 18 | -$109,717.83 | -$109,717.83 | $0 | 0/18 |
| v111 | 18 | -$112,587.94 | -$112,587.94 | $0 | 0/18 |
| 3000-socre | 18 | -$128,520.67 | -$128,520.67 | $0 | 0/18 |
| rank-your-agent | 18 | -$109,228.89 | -$109,228.89 | $0 | 0/18 |
| strong-barnyard | 18 | -$106,540.67 | -$106,540.67 | $0 | 0/18 |
| **total** | **108** | **-$113,110.92** | **-$113,110.92** | **$0** | **0/108** |

Direct paired self-play is exactly `$0` on 18/18 ties. Both mirrors are exact;
all 540 episodes complete with zero errors and zero not-DONE statuses. This is
literal semantic identity, not a statistically neutral gameplay result.

The first real-engine invocation is the invalid environment tombstone
`logs/arena/v89_vs_v86_real6_27300.json`. System `python3` lacks
`kaggle_environments`, so all 72 attempted pool arm episodes and all 36 mirror/
head-to-head episodes errored before agent execution; the identity control
aborted, no paired cell exists, and no displayed zero is evidence.

The unchanged valid retry is
`logs/arena/v89_vs_v86_real6_27300_venv_retry.json`, run with
`/home/yilewang/kagg-env/bin/python` (installed Kaggriculture engine, seed0
27300, six seeds x six standard opponents, both seats, 12 workers, 6.2
minutes). All 180 games finish `DONE/DONE` with zero errors, zero not-DONE
statuses, no timeout and no invalid action. Candidate and baseline absolute
external paired margin are identically `-$118,956.03`; every row has `$0`
delta and 0/36 cells fire. Direct paired self-play is exactly `$0` on six ties;
both mirrors are exact.

| opponent | cells | V89 absolute paired margin | V86 absolute paired margin | delta | firing |
|---|---:|---:|---:|---:|---:|
| multi-route | 6 | -$109,490.33 | -$109,490.33 | $0 | 0/6 |
| frontier | 6 | -$123,235.33 | -$123,235.33 | $0 | 0/6 |
| v111 | 6 | -$123,251.67 | -$123,251.67 | $0 | 0/6 |
| 3000-socre | 6 | -$125,137.83 | -$125,137.83 | $0 | 0/6 |
| rank-your-agent | 6 | -$119,788.67 | -$119,788.67 | $0 | 0/6 |
| strong-barnyard | 6 | -$112,832.33 | -$112,832.33 | $0 | 0/6 |
| **total** | **36** | **-$118,956.03** | **-$118,956.03** | **$0** | **0/36** |

A 288-cell gameplay gate is neither required nor informative for this
non-major transformation: V89 makes no economic or action change, has matching
action hashes on every diagnostic call, and fires in 0/162 external simulator/
real cells after the mandatory standard108 and real gate. **V89 is promoted as
the selected strict-white-box executable solely for runtime safety.** It
inherits V86's previously qualified gameplay evidence and makes no new margin
or win-probability claim. V86 remains its immutable action-equivalent baseline.

The final fresh seed27200 closure episode versus an inert public-observation-
only opponent returns `$105,499/$3,000`, action SHA256
`7503e3a8f2d1f39a7eda398dc196f31933337d2a019e20b83da392797c895efc`,
and `FORBIDDEN_IMPORTED []` across replay/tape/opening/weights/schedule/search/
mining/behavior modules. Hostile legacy environment settings produce the same
banks and hash. V89 wrapper source SHA256 is
`fb37c4953c2f85510878257d02b6a0a887e509a8750b2f226343d3490d76919c`;
V86 remains byte-unchanged at its hash above. No external write or Kaggle
submission occurred; unrelated dirty work remains preserved.

### V95 paired-phase selected-output objective (standard-neutral/negative, 2026-08-28)

V95 is `whitebox/versions/v95_paired_phase_bundle.py`. It leaves the rejected
certificate line and targets a different objective mismatch. V89's ordinary
and capital `TaskBundleObjective` aggregates repeated selected output exactly,
but its revenue function remains an own-bank lower bound: our bundle is priced
after current visible opponent standing units. That is not the exact paired
margin for one simultaneous sale phase.

For current inventory `I`, our quantity `x`, any opponent quantity `y`, and
exact engine revenue/inventory transition `R`, averaging the two equally
represented seat orders gives

```
0.5 * [R_I(x) + R_I(y) - R_(I+x)(y) + R_(I+y)(x)] = R_I(x).
```

V95 therefore uses standalone nonlinear revenue on the current public book for
the selected output bundle. It first removes the exact historical output term
from every task, then substitutes the paired-phase term, so WHEAT/FERTILIZER
opportunity cost, survival, option floors, asset cost, fixed land activation,
cash, slots, routes and all other residuals remain unchanged. Both the daily
ordinary master and current capital master use the same objective. This is
explicitly a one-simultaneous-phase relaxation, not a claim that hidden stock
is irrelevant across distinct future sale times.

Four new equation/wiring tests prove cancellation for multiple opponent
quantities, exact preservation of a constructed non-sale residual, use of the
paired objective by the clock-free ordinary master, and use by the clock-free
memoized capital master. The full white-box suite passes 166/166; edited
modules compile and `git diff --check` passes.

Runtime/determinism is recorded at
`logs/whitebox/v95_paired_phase_bundle_runtime_28900.txt`. Against multi-route
on seed28900, V89 returns `$46,769/$105,307`; two V95 repeats return
`$60,933/$116,526` with identical 719-action SHA256
`a1a00bdcb4065803a675156f7b0c8d601f57580d2f25d47082c78fabcef04064`.
V95 differs from V89 on 501/719 actions. Repeat mean/P95/P99/max are
19.170/78.989/121.168/152.096 ms and
19.243/78.997/122.057/144.306 ms, with zero calls at or above 170 ms. V89's
same-process maximum was 186.527 ms with two calls above 180 ms; this does not
affect V95's exact repeat or qualify either candidate economically.

The rejection-only quick screen is
`logs/arena/v95_vs_v89_quick_29000.json` (simulator, seed0 29000, six seeds,
three hard opponents, both seats, 26 workers, 1.9 minutes). Both mirrors are
exact; all 108 episodes finish with zero errors and zero not-DONE statuses.
Candidate absolute external paired margin is `-$105,308.44` versus V89
`-$108,093.56`: delta `+$2,785.11/cell` (SE `$2,737.20`, t=1.02), firing
18/18 and W-L 9-9. Row deltas are `+$5,892.00`, `+$2,520.83`, and `-$57.50`.
Direct paired self-play is `-$45,242` total, mean `-$7,540.33` (SE
`$4,602.98`, t=-1.64), W-L 1-5. Because quick screens only reject and the
external direction was mixed rather than clearly adverse, the unchanged arm
advanced to the required standard gate.

The valid standard gate is
`logs/arena/v95_vs_v89_standard108_29100.json` (simulator, seed0 29100,
18 seeds, six standard opponents, both seats, 26 workers, 7.1 minutes). Both
mirrors are exact; all 540 episodes finish with zero errors and zero not-DONE
statuses. Candidate absolute external paired margin is `-$118,685.01` versus
V89 `-$118,410.27`: delta `-$274.74/cell` (SE `$1,719.50`, t=-0.16), firing
108/108 and W-L 51-57. Opponent-row deltas in standard order are
`-$511.06`, `-$398.78`, `-$1,185.28`, `-$2,890.44`, `-$3,490.78`, and
`+$6,827.89`, with row W-L respectively 8-10, 7-11, 7-11, 9-9, 7-11, and
13-5. Direct paired self-play is `+$14,515` total, mean `+$806.39` (SE
`$1,212.07`, t=0.67), W-L 9-9.

The standard result is statistically neutral but fails the campaign's required
positive external direction and paired win probability: five opponent rows
are negative, aggregate W-L is below half, and the sole strong-barnyard gain
masks those losses in the quick mean. V95 earns no 288 or real-engine gate and
is not promoted. The exact theorem is not rejected; the rejected policy
assumption is treating output generated at different future times as one
simultaneous phase on today's book. Future opponent-relative productive value
must preserve phase timing and persistent inventory rather than add another
opponent quantity reserve or tune row-specific weights.

Fresh seed29200 closure returns `$113,111/$3,000` against an inert opponent,
action SHA256
`e63e5a6a9aa910bc0e6e0de65372395b244f0e93a00c84dab2c214e25af31950`, and
`FORBIDDEN_IMPORTED []`; hostile legacy environment values produce identical
banks and hash. V95 wrapper SHA256 is
`2a30b1cadbd2c3879efa93c11cf2b801d0b4fd32d2cb93c0f205d61b41a9a466`.
V86/V89 remain byte-unchanged at their recorded hashes. V89 remains selected.
No external write or Kaggle submission occurred; unrelated dirty work remains
preserved.

The next gameplay mechanism is unchanged: construct a genuinely productive
multi-day selected-set objective that jointly decides sale cash and retained
stock while certifying executable route quantities, daily feed/service labor,
bridge cash, shed trajectory and market slots. Build that arm on V89's exact
runtime memo but compare gameplay against immutable V86/V89 identity. Do not
revive V77-V80's rejected portfolio generator or treat runtime savings as a
gameplay improvement.

Final post-documentation verification reran the complete suite at 140/140,
compiled the edited modules, passed `git diff --check`, and preserved V86's
wrapper hash exactly. A final seed26800 V89 control again returned
`$36,734/$89,384`, the recorded 719-action SHA256
`fde1dfc446cc47eabb3685a3c0e2033d5ba8d7b8a8ee5329586030840e7a8dd2`,
126.744 ms maximum and zero calls at or above 180 ms.

### V90 first-output productive inventory certificate (decisive regression, 2026-08-28)

V90 is `whitebox/versions/v90_productive_inventory_certificate.py`. It keeps
V89's observation-derived acquisition proposal unchanged and puts a binary
sale/retention bundle inside the positioned selected-capital marginal. For each
retained capital set it compares executing V89's complete current sale vector
with retaining that same vector until the selected portfolio's first certified
output day. It does not invent quantities, item targets or a portfolio.

The future lower book applies the exact guaranteed town drain to current book,
then reserves every rule-derived remaining unit on both public farms ahead of
new output. One conserved hidden opponent shed is allocated across products by
the exact min-plus DP. Repeated retained and first-output units are aggregated
once before `econ.sell_revenue`. Current paired sale value uses the exact
both-seat cancellation. A strict objective tie executes V89's current sale.

The physical certificate separately proves that asset/hire purchases preceding
the sale are affordable without sale cash, then permits only
`market.robust_sale_cash` to fund later service. It includes retained stock in
every daily shed peak, exact positioned closed routes, feed, Fibonacci hires,
fixed land activation and sale-product slots. It credits no speculative later
output cash: only the robust first certified joint sale can fund service after
that day. Six new equation/structural tests cover exhaustive shared-hidden
allocation, pre-sale versus post-sale cash timing, persistent shed occupancy,
proposal preservation, memo opt-in and the empty-capital V89 control. The full
suite passes 146/146.

`logs/whitebox/v90_productive_inventory_runtime_27400.txt` records simulator
seed27400 versus multi-route. V89 returns `$41,802/$90,094`. Two V90 repeats
return `$14,505/$166,780`, identical action SHA256
`400f55b0bb326ea655f377f8432e7fb5a20428485753a7f144bae2ccda177a9a`
and zero repeat differences. V90 differs from V89 on all 719 actions. It is
runtime-safe: repeat mean/P95/P99/max are
8.678/21.313/29.481/77.236 ms and 8.658/21.319/29.142/77.510 ms, with no call
at or above 170 ms. The low runtime is diagnostic of the certificate rejecting
most capital, not a model advantage.

The required quick gate is
`logs/arena/v90_vs_v89_quick_27500.json` (simulator, seed0 27500, six seeds,
three hard opponents, both seats, 26 workers, 1.4 minutes). Mirrors are exact;
all 108 episodes complete with zero errors and zero not-DONE statuses. V90
absolute external paired margin is `-$267,862.22` versus V89 `-$113,205.39`:
delta `-$154,656.83` per cell (SE `$14,808.80`, t=-10.44), firing 18/18 and
conditional W-L 0-18. Every row is strongly negative: multi-route
`-$186,613.17`, frontier `-$141,252.83`, and v111 `-$136,104.50`. Direct
self-play is `-$939,925` total, mean `-$156,654.17` (SE `$11,367.85`,
t=-13.78), W-L 0-6.

V90 is a decisive regression and did not earn standard108, 288, or real-engine
evaluation. The hypothesis failure is informative: charging the selected
portfolio's entire remaining service bill while crediting only its first robust
output collapses productive capital and changes the whole trajectory. Do not
tune reserves, output items or opponent bounds around this result.

Fresh seed27600 closure returns `$16,764/$3,000` against an inert opponent,
action SHA256
`90c647ec6f9555e23355e8c1fea9915237dfc7c7787471de6ba223c7deed1eb6`,
with `FORBIDDEN_IMPORTED []`; hostile legacy environment values produce the
same banks and hash. V90 wrapper SHA256 is
`e07e22581a2bb4e2c12c2d4c65df2a915e7e8f1f2b9b55a911298804afa0b2c7`.
V89 remains selected and immutable.

The next principled formulation is not a looser opponent assumption. Preserve
V90's same physical certificate and uncertainty set, but credit every certified
capital output under one shared hidden allocation. For bridge feasibility,
compute the worst cumulative revenue separately at every daily prefix; proving
each prefix for all allocations is sufficient even when the minimizing
allocation differs by checkpoint. This removes V90's deliberate first-output
lower-bound truncation without introducing a fitted terminal coefficient.

### V91 all-output robust inventory path (decisive regression, 2026-08-28)

V91 is `whitebox/versions/v91_productive_inventory_path.py`. It preserves V90's
unchanged V89 proposal, bundle-binary sale decision, exact positioned physical
certificate, visible-supply reserve and one conserved hidden opponent shed.
It removes only V90's deliberate first-output value truncation: every certified
capital output is now aggregated by item/day and credited on the exact nonlinear
curve.

The objective evaluates the full path under one hidden allocation shared across
products. Daily solvency uses a cheaper valid lower bound: at each prefix, each
product is priced after its individual worst 100 hidden units. Every physical
shared allocation gives each product at most 100, so the sum of those individual
minima cannot overstate cash. Each daily checkpoint proves

```
upfront cash + robust current sale cash
+ worst cumulative certified revenue through day d
- cumulative exact feed/Fibonacci-hire cost through day d >= reserve.
```

The asset purchase is still checked before current sale cash. Retained stock
remains in every shed peak through the certified sale day; repeated retained
and produced units share one order/product revenue call. Two additional tests
match full-path value against exhaustive shared allocations, prove every prefix
cash lower bound, and confirm the V91 objective/memo wiring. The complete suite
passes 148/148.

The deterministic/runtime record is
`logs/whitebox/v91_productive_inventory_path_runtime_27700.txt`. On seed27700
versus multi-route, V89 returns `$90,652/$150,233`. Two V91 repeats return
`$16,544/$93,212`, identical action SHA256
`eceedadbe716e8acf8cf74555ecba4064b7f0b012a4cc52f0a775b2e2e528a18`,
zero repeat differences and 719/719 differences from V89. Repeat
mean/P95/P99/max are 8.724/22.113/26.887/100.719 ms and
8.713/22.358/27.113/102.359 ms; no call reaches 170 ms. As with V90, low work
reflects a suppressed capital trajectory rather than an advantage.

The quick CRN gate is `logs/arena/v91_vs_v89_quick_27800.json` (simulator,
seed0 27800, six seeds, three hard opponents, both seats, 26 workers, 1.5
minutes). Both mirrors are exact and all 108 episodes finish with zero errors
or not-DONE statuses. Candidate absolute external paired margin is
`-$238,064.06` versus V89 `-$112,972.28`: delta `-$125,091.78` per cell
(SE `$10,029.94`, t=-12.47), firing 18/18, conditional W-L 0-18. Rows are
multi-route `-$138,702.50`, frontier `-$120,167.17`, and v111
`-$116,405.67`. Direct self-play is `-$726,939` total, mean
`-$121,156.50` (SE `$6,321.24`, t=-19.17), W-L 0-6.

V91 is a decisive regression and earns no standard108, 288 or real-engine
gate. Because crediting all certified output recovers only about $29,565/cell
of V90's $154,657 regression and still loses every firing cell, missing later
revenue is not the main defect. The shared failure is replacing V89's joint
current-horizon selected-set objective with a standalone full-season capital
objective; that double-horizon substitution suppresses the coupled route/hire/
capital system on every turn.

Fresh seed27900 closure returns `$38,974/$3,000` against an inert opponent,
action SHA256
`623796c9ebc322d8fcd8f9e529200599033ec43b66ca19dccb19ed5f3cad14a7`,
with `FORBIDDEN_IMPORTED []`; hostile legacy environment values return the same
banks and hash. V91 wrapper SHA256 is
`00285df386ada2f606e8436c22cb09d6c1ce90e3a750575e7cbad380d2b0e214`.

V89 remains selected. The next productive formulation should preserve V89's
existing joint `TaskBundleObjective` as the economic score and attach the
multi-day inventory/cash/service certificate only as a selected-set feasibility
oracle. Sale versus retention can alter feasibility and emitted fixed orders,
but must not replace or add a second full-season capital value. This directly
tests the double-horizon diagnosis without relaxing any physical or uncertainty
constraint.

Final post-documentation verification used the repository-native command
`python3 -m unittest discover -s whitebox -p 'test_*.py' -v`: all 148 tests
pass in 0.288 seconds. Edited modules compile and `git diff --check` passes.
The engine virtualenv and system interpreter do not contain optional `pytest`;
two attempted pytest invocations therefore exited before collecting tests and
are not evidence or model failures. V86/V89/V90/V91 wrapper SHA256 values are,
respectively, `1b9993e45b4f67cfdcc5cf653778012442657c432292a497c4582072d9142b0e`,
`fb37c4953c2f85510878257d02b6a0a887e509a8750b2f226343d3490d76919c`,
`e07e22581a2bb4e2c12c2d4c65df2a915e7e8f1f2b9b55a911298804afa0b2c7`,
and `00285df386ada2f606e8436c22cb09d6c1ce90e3a750575e7cbad380d2b0e214`.
The architecture header now names V89 as the selected executable and explicitly
retains V86 as its action-equivalent gameplay evidence source. No external
write or Kaggle submission occurred, and unrelated dirty work remains intact.

### V92 productive certificate as feasibility only (decisive regression, 2026-08-28)

V92 is `whitebox/versions/v92_productive_feasibility_oracle.py`. It directly
tests the V90/V91 double-horizon diagnosis. Its selected-set value is exactly
V89's existing `TaskBundleObjective`; the multi-day model contributes no
terminal value, coefficient or marginal. It may only map a capital subset to
feasible or infeasible. Equation tests prove that every feasible selected set,
every insertion marginal and the final branch score equal V89 exactly.

For each selected positioned capital set, the oracle proves closed daily
routes, feed and Fibonacci hires, exact current-hire cash, asset purchase cash
before any current sale, robust daily cash prefixes, retained-stock shed peaks,
sale-product slots and fixed land activation. Sell-now and retain are explicit
outer branches: they receive the same V89 economic score, retention frees its
actual current market slots, and a strict complete-score tie executes V89's
sale. Retention without a productive output anchor is infeasible. Repeated
output is aggregated before the nonlinear sale equation.

The initial exact implementation recertified identical capital subsets for
each hire arm and produced repeat maxima 779.274/782.574 ms, failing the runtime
contract before evaluation. The proof was then factored into a reserve-
independent minimum cash checkpoint shared by all exact Fibonacci-hire arms;
this reduced maxima to 179.710/178.382 ms without changing banks or any of 719
actions, but left inadequate soft-deadline headroom. Profiling showed V91's
terminal shared-allocation objective dominated the remaining proof even though
V92 never reads it. An explicit objective-free path now computes only the same
per-product worst-capacity daily prefix and skips that unused terminal DP.
Tests prove prefix cash and sale-product slots are identical to V91's full path.

The final deterministic/runtime record is
`logs/whitebox/v92_productive_feasibility_runtime_28000.txt`. On simulator
seed28000 versus multi-route, V89 returns `$66,111/$125,350`; two V92 repeats
return `$46,551/$107,952` with identical 719-action SHA256
`4a525aed1f2933110f06ab7dc0ce3616b439204215fbbd8acdeaf9734b9974e2`
and zero repeat differences. V92 differs from V89 on 719/719 actions. Final
repeat mean/P95/P99/max are 23.795/82.550/104.141/124.439 ms and
23.708/81.759/105.013/122.774 ms, with no call at or above 170 ms. The full
white-box suite passes 154/154; edited modules compile and `git diff --check`
passes.

The proportional-risk quick gate is
`logs/arena/v92_vs_v89_quick_28100.json` (simulator, seed0 28100, six seeds,
three hard opponents, both seats, 26 workers, 2.2 minutes). Both mirrors are
exact; all 108 episodes finish with zero errors and zero not-DONE statuses.
Candidate absolute external paired margin is `-$149,327.72` versus V89
`-$112,747.39`: delta `-$36,580.33` per cell (SE `$5,456.46`, t=-6.70),
firing 18/18 and conditional W-L 1-17. Row deltas are multi-route
`-$36,911.67`, frontier `-$36,716.33`, and v111 `-$36,113.00`. Direct paired
self-play is `-$129,713` total, mean `-$21,618.83` (SE `$4,617.21`, t=-4.68),
W-L 0-6.

V92 is a decisive regression and earns no standard108, 288 or real-engine
gate. Removing V91's second objective recovers about `$88,512/cell`, so that
diagnosis was real but incomplete. The remaining hard full-season certificate
still rejects too much capital for an agent that replans from realized public
state every day. Do not tune the opponent reserve, cash floor or hidden shed
capacity around this result: those would be unpromoted policy assumptions.

Fresh seed28200 closure returns `$93,092/$3,000` against an inert opponent with
action SHA256
`e1e470464770b2fe135a2f8ec75280cef3efaeca02aff386ebc0a7cff0118692` and
`FORBIDDEN_IMPORTED []`; hostile legacy environment values give identical banks
and hash. V92 wrapper SHA256 is
`5feede6bbdadd2ef1c6b6e59f4e25a332c9657acc4d44e619432da831587390b`.
V86 and V89 remain byte-unchanged at their recorded hashes. V89 remains the
selected executable.

The next arm should not impose another full-season worst-case proof on V89's
daily MPC. Keep V92 as a physical audit oracle, not a production constraint,
and move to a necessary realized-prefix mechanism: certify only obligations
that become unavoidable before the next public replan, or use exact certificate
failure reasons to repair the emitted current asset quantity and then
recertify. Any such arm must preserve V89's score and current-observation-only
contract and compare against immutable V89. No external write or submission
occurred; unrelated dirty work remains preserved.

### V93 post-selection actual-quantity repair (quick-rejected, 2026-08-28)

V93 is `whitebox/versions/v93_productive_postselection_repair.py`. It tests the
alternative left by V92 without putting certificate feasibility inside V89's
greedy marginal. V89's proposal, exact `TaskBundleObjective`, route insertion,
hire arms, activation branches and solve-local route memo all run unchanged.
Only after routing does V93 certify the actual selected capital item/position
pairs under V92's objective-free physical and daily-cash proof.

If that exact selected quantity is infeasible, V93 removes one capital column
at a time. At each finite step it evaluates every single-column removal with
V89's unchanged nonlinear selected-set score and keeps the trial with greatest
remaining value, including exact fixed land activation once. Equal economic
loss uses the existing order key, public tile, task kind and engine operations
as a deterministic tie-break. Ordinary work is never removed. The loop is
bounded by selected capital count, strictly reduces it, and uses no deadline,
fallback, fitted coefficient, opponent identity or remembered state.

Three tests prove that a certified V89 selection is an exact identity, an
uncertified two-unit quantity removes the lower-value unit and recertifies, and
the route master still receives `TaskBundleObjective`, a `None` deadline and
the exact route memo. The full white-box suite passes 157/157; edited modules
compile and `git diff --check` passes.

The deterministic/runtime record is
`logs/whitebox/v93_productive_postselection_runtime_28300.txt`. On simulator
seed28300 versus multi-route, V89 returns `$42,099/$91,150`; two V93 repeats
return `$56,990/$115,283` with identical 719-action SHA256
`43f093913b30606237643bd2b935b009130bc2431afc861b24d2f5955f12425d`
and zero repeat differences. V93 differs from V89 on 719/719 actions. Repeat
mean/P95/P99/max are 22.882/80.079/98.051/115.874 ms and
22.928/80.360/97.814/115.838 ms; no call reaches 170 ms. The apparent own-bank
gain is not gameplay evidence: opponent bank also rises and the one-seed paired
margin worsens.

The proportional-risk gate is
`logs/arena/v93_vs_v89_quick_28400.json` (simulator, seed0 28400, six seeds,
three hard opponents, both seats, 26 workers, 1.8 minutes). Both mirrors are
exact; all 108 episodes complete with zero errors and zero not-DONE statuses.
Candidate absolute external paired margin is `-$152,372.11` versus V89
`-$114,375.44`: delta `-$37,996.67` per cell (SE `$12,466.74`, t=-3.05),
firing 18/18 and W-L 6-12. Multi-route is statistically neutral at `+$456.17`
(W-L 4-2), but frontier loses `-$55,929.33` (W-L 1-5) and v111 loses
`-$58,516.83` (W-L 1-5). Direct paired self-play is `-$408,777` total, mean
`-$68,129.50` (SE `$6,487.24`, t=-10.50), W-L 0-6.

The arena's mechanical final label is `NEUTRAL` because 6-12 gives an
underpowered paired win-rate statistic at 18 cells. Under the campaign's
predeclared quick-screen rule this is still an obvious rejection: aggregate
margin t=-3.05, both non-multi opponents are large 1-5 regressions, direct
self-play is 0-6, and the arm fires everywhere. V93 earns no standard108, 288
or real-engine gate and is not promoted.

Fresh seed28500 closure returns `$103,089/$3,000` against an inert opponent,
action SHA256
`662715e67be4510c7ec0b7798db59ca4433ea47b91d857265628a301ca324597`,
and `FORBIDDEN_IMPORTED []`; hostile legacy environment values produce the
same banks and hash. V93 wrapper SHA256 is
`61eab705e58e492ae512cba6649cd8d5fd2b420a62ac291102d22e928395b0a5`.
V86/V89 remain byte-unchanged and V89 remains selected.

V92 and V93 together close full-season certificate enforcement on V89's fixed
proposal: moving the proof from the marginal to post-route repair changes the
opponent shape but not the adverse aggregate result. Do not make another trim
ordering, reserve, hidden-capacity or item-count arm. Preserve the certificate
as an offline audit/equation asset. The next gameplay mechanism must be a
different architecture gap, or a logically necessary constraint limited to
state transitions that occur before new public information and a fresh replan.
No external write or submission occurred; unrelated dirty work remains intact.

### V94 deadline-day post-market execution validator (inert, 2026-08-28)

V94 is `whitebox/versions/v94_deadline_phase_validation.py`. It tests the
logically necessary timing constraint left open after V92/V93 without imposing
another full-season proof. Engine crop and animal placement deadlines are
last-hour steps. Only on that exact rule day, after V89 has performed its
unchanged proposal, nonlinear `TaskBundleObjective`, route insertion, hire and
activation branches, V94 projects the already-committed unit phase because the
market purchase executes afterward. It rejects a deadline capital column if
the projected target tile is stale or if the remaining workers cannot complete
its initial PLANT+WATER or BUILD+PLACE operations before hour 24.

The remaining-route certificate uses the exact route equation and a conditional
bundle objective with all non-deadline work fixed. It deliberately ignores
competition from future ordinary tasks, feed and later service, so exclusion is
a necessary relaxation rather than another V92-style sufficient full-season
condition. It is finite, memoized, clock-free and contains no opponent label,
history, fitted coefficient or environment switch. Non-deadline days and tasks
are exact V89 identities.

Five new equation/wiring tests prove exact rule-day classification, that a
purchase cannot use the already-spent hour-23 action, retention of an early
same-day feasible route, invalidation when the current unit phase mutates the
target tile, and the V89 `TaskBundleObjective`/memo/clock-free outer solve plus
conditional validator solve. The full white-box suite passes 162/162; edited
modules compile and `git diff --check` passes.

Runtime/determinism is recorded at
`logs/whitebox/v94_deadline_phase_runtime_28600.txt`. Against multi-route on
seed28600, V89 and both V94 repeats return `$46,623/$91,734` and have the same
719-action SHA256
`470acdb8240134fabe7f3c4b42796dd75596a37f4133e12a012cb2c72bf1de63`.
V94 repeat mean/P95/P99/max are
20.701/92.397/135.165/163.821 ms and
20.711/91.648/135.049/166.471 ms, with zero calls at or above 170 ms.

The proportional-risk CRN gate is
`logs/arena/v94_vs_v89_quick_28700.json` (simulator, seed0 28700, six seeds,
three hard opponents, both seats, 26 workers, 2.1 minutes). Identity and
candidate mirrors are exact; all 108 episodes finish with zero errors and zero
not-DONE statuses. Candidate and baseline absolute external paired margin are
both `-$105,632.83/cell`. Every row delta, aggregate delta and six-seed direct
self-play delta is exactly `$0`; firing is 0/18 external cells and 0/6
self-play seeds. This is `INERT`, not evidence of neutrality or improvement.
No standard108, 288 or real-engine gate is warranted and V94 is not promoted.

Fresh seed28800 closure returns `$112,011/$3,000` against an inert opponent,
action SHA256
`49b6bc98494555d0330b2efbe9c58fca3a8d91d5d38fd4711990db0e5151d9e4`, and
`FORBIDDEN_IMPORTED []`; hostile legacy environment values return identical
banks and hash. V94 wrapper SHA256 is
`52e12853f1e6aeac466e9aef5138ab1c574c0caffe53abe00497b5c0c8b3d686`.
V86/V89 remain byte-unchanged at their recorded hashes and V89 remains the
selected executable.

V94 closes this narrow deadline transition as a gameplay candidate on the
tested distribution: the exact constraint exists and is now executable/tested,
but V89 did not emit a violating purchase in any gate cell. Keep the helper as
a white-box audit equation. Do not broaden it into the rejected full-season
certificate or run larger gates without measured firing. The next mechanism
should target a different observed decision seam. No external write or Kaggle
submission occurred; unrelated dirty work remains preserved.

### Latest campaign status after V95 (2026-08-28)

V95 is the latest evaluated arm; its full equation, runtime, quick18 and
standard108 record appears above under “V95 paired-phase selected-output
objective.” The decisive status is unpromoted: standard external delta
`-$274.74/cell` (SE `$1,719.50`), W-L 51-57, firing 108/108, with five of six
opponent rows negative. It received no 288 or real-engine gate. Immutable V89
remains the selected executable. The next opponent-relative productive model
must preserve distinct sale phases and persistent public inventory; do not
repeat V95 by tuning an opponent reserve or weighting its sole positive row.

### V96 full temporal selected-set objective (runtime tombstone, 2026-08-28)

V96 is `whitebox/versions/v96_temporal_paired_bundle.py`. It corrects V95's
one-phase collapse without adding an opponent policy. `task_sale_schedule`
places every rule-derived output on its first physical availability day:
already held HARVEST and collected fertilizer are current-day quantities, and
refresh output becomes available on refresh+1. Tests prove dated and undated
quantities are identical.

For each product, one public book persists through the selected phases. Exact
guaranteed current-shop drain is applied between phases. The both-seat theorem
makes our phase increment standalone nonlinear revenue on that phase's opening
book; the combined sale closes at the same inventory in both commit orders.
The only opponent uncertainty is currently visible standing yield. An
adversary may allocate each unit to at most one phase or retain it, under one
conserved engine shed-capacity bound of 100. No future service, private-stock
point estimate, policy, identity, coefficient or hidden schedule is assumed.
Historical non-sale residuals, fixed activation and physical constraints remain
explicit.

The exact finite DP is too slow as a per-insertion marginal. Full optimization
history is `logs/whitebox/v96_v97_temporal_runtime_29300.txt`. An unjustified
full-future-service prototype was interrupted after four minutes and removed.
The first valid DP repeated near 36.8 ms mean with 596/598 ms maxima. A shared
schedule cache reduced mean to 31.5 ms but left a 522 ms maximum. Exact
continuation-dominance pruning worsened the maximum to 626 ms and was reverted.

An exact local memo of the pure engine price equation is retained; cross-
product tests prove its sale transition equals the existing engine copy. Even
then, final seed29300 V96 repeats return the same `$28,165/$102,611` and action
SHA256
`36408b1f7d7022d122c8e7161d34181b78fc4249deaa81ac7283f2742f6b80d7`,
but mean/P95/P99/max are 26.782/138.010/205.006/315.139 ms and
26.834/135.790/202.552/317.607 ms. There are 24/26 calls at or above 170 ms
and 20/20 at or above 180 ms. V96 is runtime-invalid and received no arena,
288 or real-engine cells. This is not permission to add a clock fallback or
approximate opponent schedule.

### V97 route-trim temporal recertification (standard regression, 2026-08-28)

V97 is `whitebox/versions/v97_temporal_recertified_bundle.py`. It tests the
bounded route-trim/recertify seam. V89's `TaskBundleObjective` constructs
ordinary routes and every exact memoized capital route unchanged. Only after a
hire/activation branch has a complete executable selected set does the V96
dated objective recertify that actual quantity. Proposed but unrouted columns
never enter the score. No feasible set, route cost, cash, slot or activation
constraint changes.

Focused tests prove the route master receives V89's objective, a `None`
deadline and exact route memo, while the temporal scorer receives only selected
tasks. Sale-transition equivalence, schedule conservation, persistent own book,
conserved opponent stock and telescoping marginals are covered. The complete
suite passes 174/174; modules compile and `git diff --check` passes.

Runtime/determinism is in
`logs/whitebox/v96_v97_temporal_runtime_29300.txt`. Same-process V89 returns
`$28,929/$89,690`, mean/P95/P99/max 14.889/68.220/105.585/125.906 ms. Two
V97 repeats return `$32,557/$102,228`, identical action SHA256
`a9680c5581aa59c04a8cc5c89193f2f9d55a52d71a814cb1c2df37b8a4995fbc`,
zero repeat differences and 462/719 differences from V89. Their
mean/P95/P99/max are 16.881/60.891/85.732/108.845 ms and
16.853/61.298/85.350/108.413 ms, with zero calls at or above 170 ms.

The rejection-only quick gate is
`logs/arena/v97_vs_v89_quick_29400.json` (simulator, seed0 29400, six seeds,
three hard opponents, both seats, 26 workers, 2.0 minutes). Both mirrors are
exact; all 108 games finish with zero errors/not-DONE. Candidate absolute
external paired margin is `-$104,391.83` versus V89 `-$105,718.83`, delta
`+$1,327.00/cell` (SE `$2,063.12`, t=0.64), firing 18/18 and W-L 11-7.
Row deltas are `-$2,797.83`, `+$4,419.50`, `+$2,359.33`. Direct self-play is
`-$12,134` total, mean `-$2,022.33` (SE `$1,516.39`, t=-1.33), W-L 2-4.
Because this was not an obvious external regression, V97 advanced unchanged.

The valid standard gate is
`logs/arena/v97_vs_v89_standard108_29500.json` (simulator, seed0 29500, 18
seeds, six standard opponents, both seats, 26 workers, 7.4 minutes). Both
mirrors are exact; all 540 games finish with zero errors/not-DONE. Candidate
absolute external paired margin is `-$121,895.40` versus V89 `-$119,256.57`:
delta `-$2,638.82/cell` (SE `$1,068.63`, t=-2.47), firing 108/108 and W-L
48-60. Row deltas in standard order are `-$1,527.17`, `-$3,587.39`,
`-$4,958.83`, `-$400.94`, `-$5,744.94`, `+$386.33`, with W-L 9-9, 7-11,
8-10, 8-10, 5-13 and 11-7. Candidate/V89 absolute paired means are
`-$110,325.72/-$108,798.56`, `-$128,288.94/-$124,701.56`,
`-$128,413.17/-$123,454.33`, `-$127,063.22/-$126,662.28`,
`-$126,729.33/-$120,984.39`, and `-$110,552.00/-$110,938.33`. Direct
self-play is `-$53,444` total, mean `-$2,969.11` (SE `$2,535.40`, t=-1.17),
W-L 8-10.

The arena's mechanical label is neutral, but the predeclared decision is a
regression: aggregate t=-2.47, below-half paired win probability, five negative
rows and full firing. V97 receives no 288 or real-engine gate and is not
promoted. V89 remains selected. Do not tune opponent stock, drain, phase
weights or the sole positive barnyard row around this result. V96 proves the
full marginal unsafe; V97 proves exact dated branch recertification adverse.
Preserve the temporal equation as an audit/value primitive.

Fresh seed29600 closure versus an inert public-only opponent returns
`$73,181/$3,000`, action SHA256
`8d95dc4c681ec05a13456a112296d67f34044faf14063f48d16eae8501140bc2`, and
`FORBIDDEN_IMPORTED []`. Hostile legacy environment values return identical
banks/hash. V96/V97 wrapper hashes are respectively
`7fd931db7ea3757a2c30646ed6ffa79dc0bc00c01bec239837fbc13ba7a6d633` and
`0d22f6d1603e2c1b150e55ca5a401e9726911d5116cf50a3cbad2414354a3623`.
V86/V89 remain byte-unchanged at their recorded hashes.

The remaining productive-horizon gap is not another opponent-timing reserve or
post-route repricer. It is a single bounded MPC whose own selected-set marginal
jointly decides an invented asset portfolio, sale/retention, daily service/feed
labour, bridge cash, shed trajectory, order slots, exact activation and actual
routes. It must avoid the rejected V77-V80 generator, V90-V93 full-season
enforcement and V96/V97 temporal wrappers. No external write or Kaggle
submission occurred; unrelated dirty user work remains preserved.

### V98 constructive first-output prefix (quick-rejected, 2026-08-28)

V98 is isolated at `whitebox/versions/v98_first_output_prefix.py`; immutable
V89 remains the baseline and is byte-unchanged at SHA256
`fb37c4953c2f85510878257d02b6a0a887e509a8750b2f226343d3490d76919c`.
This arm attacks the asymmetry exposed by V90 without restoring a rejected
full-season proof. For every invented asset it certifies only the irreversible
prefix from purchase through its first physically available output and then
hands the state back to the next public-observation replan.

The constructive schedule follows engine equations exactly. A crop performs
PLANT+WATER on its modelled start day, WATER every second day (one unwatered
night is survivable; the second creates a weed), and one HARVEST after the
first rule maturity. An animal performs BUILD+PLACE, survives its legal first
unfed night, FEEDs the next day and every second day through first production,
and HARVESTs one base unit. CARE is absent because it cannot change the first
base yield. Every future closed route includes its return and DROP; V98 also
adds the PICKUP action omitted by the older abstract certificate, once per
distinct carried item on each route. Global crop seeds require no pickup under
the engine. Same-item first outputs are aggregated before the exact nonlinear
sale equation.

The bounded inventor evaluates the no-land and exact one-fixed-charge land
arms, ranks legal singleton derivatives, and extends each improving item ray
under physical slots, daily closed routes, exact Fibonacci hires, feed cost,
bridge cash, shed capacity and ten order types. It has the structural bound
`1 + item_types + slots + item_types` certificates per arm and no wall-clock
branch. The actual route master then uses the same positioned first-output
certificate as its exact selected-set marginal, trims to executable columns,
recertifies each selected subset, and raises every cash checkpoint by the exact
current hire cost. Ordinary work retains V89's nonlinear bundle objective.

Six initial equation/wiring tests prove alternate-day crop/animal survival, no
first-yield CARE credit, explicit animal/WHEAT pickups, pickup-aware route
splitting at the 23-action limit, exactly one grouped first sale, strictly less
service than the full-season certificate, invention beyond the old fixed
`6 COW + 4 SHEEP + 3 quadrants` ceiling, exact prefix-objective equality, and
clock-free memoized hire-aware route-master wiring. The complete white-box
suite passed 180/180 before the pending-capital audit; edited modules compiled
and `git diff --check` passed.
V98 wrapper SHA256 is
`eb5c9114f541eb54cab05ef23e761f5fd88e7c840c8d18a079f7365e4e7ea7eb`.
The first runtime pass exposed two correctable issues. Pickup-aware route
packing initially recomputed every partial sweep quadratically; exact
incremental accumulation removed that overhead without changing actions. More
importantly, a stable day-11 276-303 ms spike exposed that fresh proposals did
not reserve already purchased, unplaced private seeds/animals against physical
tiles. Enabling this necessary rule constraint eliminated repeated oversized
purchases and reduced the sampled day-11 call to 132 ms. A new equation test
proves 100 pending seeds consume all candidate capacity. The full suite now
passes 181/181.

Final seed29700 runtime/determinism is recorded at
`logs/whitebox/v98_first_output_prefix_runtime_29700.txt`. V89 returns
`$65,559/$161,129`, mean/P95/P99/max
18.981/77.203/114.171/127.558 ms. Two V98 repeats return
`$16,590/$140,530`, identical 719-action SHA256
`0fe22552483a5af781ce7a2103e8666bb99c1263b4e25cf2d75e838ee3a9323a`
and zero repeat differences. Their mean/P95/P99/max are
8.659/20.294/30.840/144.759 ms and 8.665/20.192/31.135/151.805 ms, with zero
calls at or above 170 or 180 ms. V98 differs from V89 on 719/719 calls. The
large own-bank decrease is not evidence by itself; the proportional CRN gate
was required. No gameplay claim follows from that snapshot.

The proportional-risk gate is
`logs/arena/v98_vs_v89_quick_29800.json` (simulator, seed0 29800, six seeds,
three hard opponents, both seats, 26 workers, 1.4 minutes). Both identity
mirrors are exact; all 108 episodes complete with zero errors and zero not-DONE
statuses. Candidate absolute external paired margin is `-$252,818.50` versus
V89 `-$107,355.17`: delta `-$145,463.33` per cell (SE `$15,902.21`,
t=-9.15), firing 18/18 and W-L 0-18. Row deltas are `-$152,814.67` against
multi-route, `-$139,645.33` against frontier and `-$143,930.00` against v111;
every row is 0-6. Direct paired self-play is `-$814,887` total,
`-$135,814.50/seed` (SE `$5,532.00`, t=-24.55), W-L 0-6.

This is decisive rejection evidence, not an underpowered neutral result. V98
earns no standard108, 288 or real-engine gate and is not promoted. Its failure
is architectural: purchase-to-first-output standalone profitability induces
near-saturation investment, while the certificate's future service routes do
not compete with the future ordinary work that the daily agent will actually
face. Stopping after first output fixes V90's full-season value asymmetry but
also assigns zero opportunity cost to all intervening ordinary service and to
the post-output standing capital. Do not tune item ranks, count ceilings,
service cadence or opponent rows around this result.

Fresh seed29900 closure versus an inert public-observation-only opponent returns
`$33,936/$3,000`, action SHA256
`37166874e070cfa57ad78922ec6d901b52cea6a2198b50a32e3128219eba5f05`, and
`FORBIDDEN_IMPORTED []`. Hostile legacy environment values return identical
banks/hash. The final suite passes 181/181; compilation and `git diff --check`
pass. V86/V89 remain byte-unchanged and V89 remains selected. V98 is preserved
as an equation/runtime tombstone; no external submission or write occurred and
unrelated dirty user work remains preserved.

The next productive-horizon formulation must include the public standing
farm's ordinary service stops in the same dated labour routes as proposed
capital, and attach a state-derived residual value or feasible abandonment
alternative at its finite horizon. Merely proving a standalone new-asset route
or replacing the missing tail with full-season service repeats V98 or V90.

### V99 exact earliest one-time crop output (quick-rejected, 2026-08-28)

Tracing V98 toward the proposed joint-farm baseline exposed a prerequisite
engine-equation error. V98 credited every one-time crop with `max_yield` at its
earliest legal harvest. The engine actually initializes WHEAT/CARROT/MELON at
one held unit and increments it only when WATER executes at crop age in
`[(max_yield_day + 1)//2, max_yield_day]`. Under the minimum alternating
survival schedule, WATER before the earliest legal HARVEST gives exact outputs
WHEAT=2, CARROT=2 and MELON=4, not 6/4/6. Ongoing crops and first animal output
remain one base unit.

V99 is isolated at `whitebox/versions/v99_exact_first_output.py`. It adds a
separate exact profile, inventor, selected-set objective and capital variant;
V98 and every older wrapper retain byte-identical recorded semantics. The
profile counts every productive WATER explicitly, uses two maturity-day
operations for a one-time crop, aggregates repeated units before exact market
clearing, and otherwise preserves V98's pending-capital slots, pickup-aware
closed routes, feed, hires, cash prefixes, shed/order limits and fixed land.
No fitted tail, hidden schedule, identity, tape, seed lookup or clock branch is
introduced.

Five new tests prove all five crop quantities/dates, maturity-day
WATER+HARVEST, strict V98 semantic isolation, exact certificate/objective
equality, direct agreement with the simulator transition for all three
one-time crops, and clock-free memoized wiring. The full suite passes 186/186;
modules compile and `git diff --check` passes.

Runtime/determinism is recorded at
`logs/whitebox/v99_exact_first_output_runtime_30000.txt`. Same-process V89
returns `$71,748/$139,277`, mean/P95/P99/max
20.379/78.470/112.633/147.333 ms. Two V99 repeats return
`$25,928/$138,952`, identical 719-action SHA256
`e00a046bb12721a50d47ab7622106908eb6650ebd1c3db3c4e02f90e91efa709`
and zero repeat differences. Their mean/P95/P99/max are
14.613/42.395/65.768/154.165 ms and 14.681/42.563/65.604/158.631 ms, with zero
calls at or above 170 or 180 ms. V99 differs from V89 on 719/719 calls. The
one-seed own-bank loss is diagnostic only; a quick CRN rejection screen is
required. V99 wrapper SHA256 is
`093e1a7ab6865ee41206bf38281464adf53dcbcacfd00f1b0eb69b1d83e9ebe6`.

The quick gate is `logs/arena/v99_vs_v89_quick_30100.json` (simulator,
seed0 30100, six seeds, hard pool, both seats, 26 workers, 1.8 minutes). Both
identity mirrors are exact; all 108 episodes complete without error. Candidate
absolute external paired margin is `-$215,890.61` versus V89 `-$117,487.89`:
delta `-$98,402.72/cell` (SE `$13,524.47`, t=-7.28), firing 18/18 and W-L
0-18. Multi-route, frontier and v111 deltas are respectively `-$106,335.33`,
`-$95,515.00` and `-$93,357.83`, each W-L 0-6. Direct paired self-play is
`-$664,729` total, `-$110,788.17/seed` (SE `$7,561.19`, t=-14.65), W-L 0-6.

V99 is decisively quick-rejected and receives no standard108, 288 or real-
engine gate. V98 and V99 used different seed blocks, so their headline losses
must not be subtracted as though they were a causal CRN comparison. What V99
does prove is that even with exact earliest quantities the standalone prefix
still fills improving physical rays without charging proposed assets for competition
with the already-visible farm's intervening service routes or a state-derived
horizon residual. Do not tune crop quantities, ray order or count limits.

Fresh seed30200 closure against an inert public-observation-only opponent
returns `$41,522/$3,000`, action SHA256
`2123f8f7567052e778941221ae06ba9b4bcf5f09cb95d013f06a84e8f06556c1`, and
`FORBIDDEN_IMPORTED []`. Hostile legacy environment values return identical
banks/hash. The final suite passes 186/186; compile and diff checks pass.
V86/V89/V98 remain byte-unchanged, V89 remains selected, and V99 is preserved
as the corrected-quantity tombstone. No external submission or write occurred;
unrelated dirty user work remains preserved.

The next arm should now implement the deferred joint-farm prefix: merge
rule-derived future service stops for currently visible assets with proposed
capital before packing daily routes and charging hires/feed/cash. Compare the
combined schedule against the same dated visible-farm baseline and use an
explicit feasible abandonment residual of zero. The comparison must not revive
V98's legacy crop quantities or V90's full-season obligation.

### V100 dated visible-farm prefix (quick-rejected, 2026-08-28)

V100 is isolated at `whitebox/versions/v100_joint_farm_prefix.py`; V89 and all
historical wrappers remain byte-identical at their recorded hashes. It executes
the deferred joint-farm experiment without adding a future policy. From the
next replan day through each candidate set's exact V99 first-output horizon,
every publicly visible ongoing own crop reserves WATER and every visible animal
reserves FEED on tomorrow/every-second-day. This is the exact periodic minimum
under the rule that one missed night is legal and the second kills the asset.
FEED carries an explicit WHEAT pickup/order. Visible one-time crops take the
named immediate-abandonment alternative at zero residual: routing or crediting
their harvest would require a separate sale/retention choice, while watering
past their finite life would create phantom work. CARE, standing-farm output
credit and every post-horizon residual are zero.

The combined certificate packs visible and proposed stops together before
charging exact closed routes, Fibonacci hires, nonlinear aggregate feed cost,
market slots and bridge cash. Its capital value is the combined paired value
minus a separately certified, identical-horizon visible-farm baseline. Thus the
standing farm is not charged to the proposal in isolation, but route sharing,
hire thresholds, feed-price interaction and cash congestion are genuinely
marginal. The bounded inventor and actual route master both use that same
selected-set equation; the current hire charge still raises every cash
checkpoint exactly once. No tape, replay, learned coefficient, seed lookup,
future shop schedule, clock branch or environment switch enters production.

Five new equation/wiring tests prove the exact alternating service dates,
explicit one-time-crop abandonment, WHEAT pickups, algebraic equality to
`combined - same dated baseline`, actual mixed visible/candidate route packing,
visible-animal feed in bridge cash, selected-set objective equality, and
clock-free memoized hire-aware wiring. The full white-box suite passes 191/191;
modules compile and `git diff --check` passes. V100 wrapper SHA256 is
`ddcf02761ee218261f469ca58e2de1ffb250a0f94e41d06c40263dc79aed55d1`.

The proportional CRN gate is
`logs/arena/v100_vs_v89_quick_30300.json` (simulator, seed0 30300, six seeds,
hard pool, both seats, 26 workers, 104.06 seconds). Both identity mirrors are
exact; all 108 episodes finish with zero errors and zero not-DONE. Candidate
absolute external paired margin is `-$220,610.72` versus V89 `-$107,733.50`, a
delta of `-$112,877.22/cell` (SE `$11,851.93`, t=-9.52), firing 18/18 and W-L
0-18. Multi-route, frontier and v111 row deltas are `-$141,097.33`,
`-$97,084.33` and `-$100,450.00`, each W-L 0-6. Direct paired self-play is
`-$534,419` total, mean `-$89,069.83` (SE `$4,333.31`, t=-20.55), W-L 0-6.

This is decisive rejection evidence. V100 receives no standard108, 288 or
real-engine gate and is not promoted. The key structural result is that a
standing-farm marginal cannot repair the first purchase decision: at day 0 the
visible farm is empty, so V100's baseline workload is empty and its inventor
still sees V99's profitable standalone rays. It buys the oversized portfolio
before any public standing assets exist; later joint service proofs cannot undo
that irreversible saturation. Do not tune service parity, opponent rows or
crop abandonment around this result. A productive next formulation must attach
a rule-derived opportunity cost or terminal/abandonment value to the proposed
standing capital itself at the initial purchase, not only to assets already on
the board. It must remain shorter than V90's rejected full-season obligation.

Runtime/determinism is recorded at
`logs/whitebox/v100_joint_farm_prefix_runtime_30400.txt`. Same-process V89
returns `$41,223/$103,132`, mean/P95/P99/max
19.721/81.514/123.624/146.968 ms. Two V100 repeats return
`$18,111/$117,716`, identical 719-action SHA256
`8b2f4149deb30fa9bc9f1a8207bd107b1fe32d6c2194367953ae8c5810745a1b`
and zero repeat differences. Their mean/P95/P99/max are
15.356/45.523/71.265/234.101 ms and 15.401/45.631/72.189/234.385 ms. Each has
one call at or above 170 and 180 ms. V100 is deterministic but independently
fails the 180 ms soft safety envelope; because margin already rejects it, no
runtime optimisation is warranted.

Fresh seed30500 closure against an inert public-observation-only opponent
returns `$28,789/$3,000`, action SHA256
`87c17acca3060fa81cf34cd2a6c8a87d529b0020cf5fa7f54ac058564b3ccf48`, and
`FORBIDDEN_IMPORTED []`. Hostile legacy environment values return identical
banks/hash. V86/V89/V98/V99 hashes remain unchanged, V89 remains selected, and
V100 is preserved as the joint-farm tombstone. No external submission or write
occurred; unrelated dirty user work remains preserved.

### V101 optional minimum-service continuation (quick-rejected, 2026-08-28)

The V100 lifecycle audit on fresh seed30600 established that the 24-MELON
prefix is physically executed rather than silently dropped: all 24 are planted
on day 1, survive, and clear for about `$14.4k` on day 11. V89's initial
portfolio on the same public observation is `4 COW + 10 STRAWBERRY + 2 MELON`,
whereas V99/V100 buy `24 MELON`. This isolates a horizon asymmetry: a one-time
crop receives its complete realizable value, while a recurring asset receives
one base unit and zero continuation.

V101 is isolated at `whitebox/versions/v101_optional_continuation.py`. For each
actual positioned selected set it compares two complete feasible endpoints.
Endpoint A is V99's exact first-output prefix followed by zero-value
abandonment. Endpoint B WATERs crops and FEEDs animals only tomorrow/every
second day, collects every reachable unconditional base output, and stops at
the final rule event. CARE, fertilizer and all production bonuses are absent;
one-time crop accumulation is still V99-exact. Each endpoint independently
packs pickup-aware closed routes and proves exact hires, nonlinear aggregate
feed, bridge cash, shed peaks, sale slots, fixed land and persistent same-item
market clearing. The higher feasible paired value is used, so continuation is
an option rather than V90/V91's forced obligation. This is a two-endpoint
finite envelope, not a fitted terminal coefficient or a full black-box policy.

Five new equation/wiring tests prove the exact four STRAWBERRY dates, every
other-day COW production through day 29, one base MILK unit per event, exact
alternate-day feed/pickups, strict identity with V99 for one-time MELON,
selection of profitable recurring continuation, selected-set objective
equality and clock-free memoized hire-aware wiring. The full suite passes
196/196; modules compile and `git diff --check` passes. V101 wrapper SHA256 is
`d3684059da80fff4e311d86929df970b9c81118cbd9caf6ea3569ce02cd4637a`.

The equation materially changes the seed30600 initial portfolio without a
target count or item weight: V101 emits `5 COW + 16 CARROT + 2 MELON + 1
TOMATO` and four hires, instead of V99's 24 MELON. Runtime/determinism is
recorded at `logs/whitebox/v101_optional_continuation_runtime_30700.txt`.
Same-process V89 returns `$76,714/$136,127`, mean/P95/P99/max
19.532/72.404/107.696/129.170 ms. Two V101 repeats return
`$26,106/$141,167`, identical 719-action SHA256
`3e6161256342ff73bea47290467a534c7ab1fc2b053defe7c24ae11f462ff8e0`
and zero repeat differences. Their mean/P95/P99/max are
10.447/23.967/48.689/153.272 ms and 10.458/24.197/47.809/153.361 ms, with zero
calls at or above 170 or 180 ms. The arm is deterministic and runtime-safe;
the low one-seed bank is diagnostic only.

The proportional CRN gate is
`logs/arena/v101_vs_v89_quick_30800.json` (simulator, seed0 30800, six seeds,
hard pool, both seats, 26 workers, 86.46 seconds). Both mirrors are exact and
all 108 episodes finish with zero errors and zero not-DONE. Candidate absolute
external paired margin is `-$219,156.39` versus V89 `-$125,519.83`: delta
`-$93,636.56/cell` (SE `$5,995.24`, t=-15.62), firing 18/18 and W-L 0-18.
Multi-route, frontier and v111 deltas are `-$90,576.83`, `-$95,119.17` and
`-$95,213.67`, each W-L 0-6. Direct paired self-play is `-$508,457` total,
mean `-$84,742.83` (SE `$4,839.35`, t=-17.51), W-L 0-6.

V101 is decisively quick-rejected and receives no standard108, 288 or real-
engine gate. V100 and V101 use different seed blocks, so their headline losses
are not a causal comparison. The mechanistic result is stronger: repairing the
one-time/recurring horizon asymmetry changes the invented bundle but not the
catastrophic trajectory. Both feasible endpoints still price a standalone
capital program separately from the ordinary future replans that must choose
and execute its service. An absolute-positive capital marginal consequently
fills all 24 physical slots (now with CARROT and COW rather than only MELON),
while the later online policy is free to choose a different path. Do not tune
endpoint choice, item ranks, service cadence or portfolio counts. V98-V101 now
close standalone invented-capital prefix/continuation valuation as a gameplay
direction. Preserve the equations as audit primitives and move to a different
architecture gap, preferably state-driven terminal feasibility/robust
opponent-relative liquidation rather than another capital horizon scalar.

Fresh seed30900 closure against an inert public-observation-only opponent
returns `$65,065/$3,000`, action SHA256
`89f2e388d08036c99b4ecfb3c070042f6048f3e7258d014c69c19331bb85a8c6`, and
`FORBIDDEN_IMPORTED []`. Hostile legacy environment values return identical
banks/hash. V86/V89/V99/V100 remain byte-unchanged, V89 remains selected, and
V101 is preserved as the optional-continuation tombstone. No external
submission or write occurred; unrelated dirty user work remains preserved.

### V102 capacity-certified chained terminal routes (implementation checkpoint, 2026-08-28)

V102 is isolated at `whitebox/versions/v102_chained_terminal_routes.py` and
inherits immutable selected V89 everywhere except its terminal primal. V89's
ordinary route upper bound already visits a sequence of live stops and pays one
final return/DROP, but V69/V89's terminal primal returned to the shed and paid
DROP after every selected tile. That made the strict opportunity comparison
physically asymmetric and could reject a feasible terminal bundle for no
economic reason. V102 uses the exact closed-chain action equation

```
L_u = dist(start_u, p_1) + ops(p_1)
    + sum_i>1 [dist(p_(i-1), p_i) + ops(p_i)]
    + dist(p_k, nearest_shed) + 1 DROP
```

for each worker. Current carried sellable stock is the initial load of the
same chain rather than forcing an intermediate delivery. Every harvest offset
still passes the crop-decay equation; repeated output is repriced once through
the exact nonlinear paired bundle equation; all targets are uniquely claimed;
and total current carried plus selected output is bounded by the one public
100-item shed capacity, so even simultaneous final DROPs fit. Current shed
stock is separately capacity-checked against current carried delivery and is
sold in the current later market phase. Production closure, hour-0 hire
deferral, strict terminal-vs-general opportunity dominance and V69's direct
delivery rescue remain unchanged. There is no fixed terminal step, route-value
coefficient, opponent fingerprint or retained hidden state.

Three new equation tests prove: two adjacent targets need seven actions under
one chained DROP where the historical return-per-target primal can select only
one; a worker carrying MILK can visit one further target and close exactly in
four actions; and a 99-unit initial load cannot add a two-unit target beyond
shared final capacity. The terminal suite passes 22/22; the complete white-box
suite passes 199/199. Modules compile and `git diff --check` passes. V102 wrapper
SHA256 is `c26625d97246a2792154d59ca87e2220226278e9422ad33e5378d97ea47f50ff`.
This is an implementation checkpoint only: no gameplay or runtime evidence has
yet been collected, V89 remains selected, and V102 must first pass deterministic
runtime/import closure and a proportional CRN screen.

The completed seed31000 runtime/determinism audit is
`logs/whitebox/v102_chained_terminal_runtime_31000.txt`. Same-process V89
returns `$57,423/$102,864`, mean/P95/P99/max
19.991/73.328/112.445/140.264 ms. Two V102 repeats return
`$58,260/$102,856`, identical 719-action SHA256
`46028fdac4f37d4c9a4f1e4f1d0c117754f50c172255e2402a5d3ba95045b0b3`
and zero repeat differences. Their mean/P95/P99/max are
19.876/73.653/113.782/141.316 ms and 19.967/73.874/113.780/139.988 ms, with
zero calls at or above 170 or 180 ms. V102 differs from V89 only at steps
710-718 on this trace and is deterministic/runtime-safe. Its +$837 own-bank
diagnostic proves execution but is not paired gameplay evidence; V89 remains
selected pending import closure and CRN evaluation.

Fresh seed31100 import/environment closure against an inert
public-observation-only opponent returns `$102,326/$3,000`, 719-action SHA256
`ef6ccaf96c9ddf2cbc190336e271230d1d8bab4944c92c17663229c440315692`,
and `FORBIDDEN_IMPORTED []`. A separate hostile-environment process with
`WB_FEED_DAYS=99`, `WB_FEED_MAX=999`, `WB_ANIMAL_BRIDGE=1`,
`WB_MARKET_TIMING=1`, `WB_FRONTRUN_MIN_UNITS=1` and `WB_FRONTRUN_LEAD=99`
returns identical banks, action count and hash. V102 therefore has no silent
legacy environment switch or forbidden production import. Proceed only to a
fresh proportional CRN quick screen; this closure result does not promote it.

The valid rejection-only CRN screen is
`logs/arena/v102_vs_v89_quick_31200.json` (simulator, seed0 31200, six seeds,
hard pool, both seats, 26 workers, 2.0 minutes). V89's identity and V102's own
mirror are exactly zero on 6/6 seed pairs; all 108 episodes finish with zero
errors and zero not-DONE statuses.

| screen | cells | V102 absolute paired margin | V89 absolute paired margin | V102-V89 | firing |
|---|---:|---:|---:|---:|---:|
| self-play | 6 seeds | head-to-head +$10,526 total; 6-0 | n/a | +$1,754.33/seed, SE $397.28, t=4.42 | 6/6 |
| hard external pool | 18 | -$112,630.83 mean; 0 wins | -$113,157.17 mean; 0 wins | +$526.33 mean, SE $174.68, t=3.01 | 18/18 |

The external paired-delta W-L is 17-1. Multi-route, frontier and v111 row
deltas are respectively +$1,008.50 (6-0), +$177.50 (5-1) and +$393.00
(6-0). Corresponding V102/V89 absolute paired means are
-$111,652.67/-$112,661.17, -$111,356.83/-$111,534.33 and
-$114,883.00/-$115,276.00. This is consistent positive mechanism evidence,
but quick gates can only reject. Advance the byte-unchanged V102 wrapper to the
existing 108-cell standard simulator gate against immutable V89. Do not promote
or run 288/real until that independent gate passes with exact mirrors, clean
statuses and sufficient firing.

The valid 108-cell standard gate is
`logs/arena/v102_vs_v89_standard108_31300.json` (simulator, seed0 31300,
18 seeds, six-opponent standard pool, both seats, 26 workers, 7.2 minutes).
V89 identity and V102 mirror controls are exactly zero on 18/18 seed pairs;
all 540 episodes finish with zero errors and zero not-DONE statuses. V89 and
V102 wrapper hashes remain respectively `fb37c495...` and `c26625d97...`.

| screen | cells | V102 absolute paired margin | V89 absolute paired margin | V102-V89 | firing |
|---|---:|---:|---:|---:|---:|
| self-play | 18 seeds | head-to-head +$28,724 total; 16-2 | n/a | +$1,595.78/seed, SE $275.02, t=5.80 | 18/18 |
| standard external pool | 108 | -$111,626.58 mean; 0 wins | -$112,421.93 mean; 0 wins | +$795.34 mean, SE $89.52, t=8.88 | 104/108 |

Conditional on firing, external delta is +$825.93 (SE about $91.64, t=9.01)
with W-L 90-14 and four inert ties, an 86.5% paired win probability. Every
opponent row is positive: multi-route +$989.67 (17-0-1), frontier +$677.61
(15-3), v111 +$556.44 (14-4), 3000-socre +$511.50 (14-2-2), rank-your-agent
+$931.39 (16-2), and strong-barnyard +$1,105.44 (14-3-1). Corresponding
V102/V89 absolute paired means are -$110,856.39/-$111,846.06,
-$109,198.11/-$109,875.72, -$111,558.28/-$112,114.72,
-$120,605.33/-$121,116.83, -$107,436.94/-$108,368.33, and
-$110,104.44/-$111,209.89.

This qualifies the unchanged major terminal action-path change for the required
independent 288-cell simulator confirmation, but not yet for promotion. Run 48
fresh seeds against the same standard pool with exact mirrors and statuses;
only a consistent result may justify the both-seat multi-seed real-engine gate.

The required independent 288-cell confirmation is
`logs/arena/v102_vs_v89_standard288_31400.json` (simulator, seed0 31400,
48 seeds, six-opponent standard pool, both seats, 26 workers, 17.8 minutes).
Both mirrors are exactly zero on 48/48 seed pairs; all 1,440 episodes finish
with zero errors and zero not-DONE statuses.

| screen | cells | V102 absolute paired margin | V89 absolute paired margin | V102-V89 | firing |
|---|---:|---:|---:|---:|---:|
| self-play | 48 seeds | head-to-head +$49,238 total; 43-4-1 | n/a | +$1,025.79/seed, SE $168.29, t=6.10 | 47/48 |
| standard external pool | 288 | -$115,386.52 mean; 0 wins | -$116,145.43 mean; 0 wins | +$758.91 mean, SE $46.56, t=16.30 | 284/288 |

Conditional on firing, external delta is +$769.60 (SE about $46.90, t=16.41)
with W-L 259-25 and four inert ties, a 91.2% paired win probability. All six
rows again remain positive: multi-route +$796.94 (45-2-1), frontier +$713.48
(42-5-1), v111 +$785.75 (42-6), 3000-socre +$650.44 (45-2-1), rank-your-agent
+$795.04 (41-6-1), strong-barnyard +$811.81 (44-4). Corresponding V102/V89
absolute paired means are -$112,557.96/-$113,354.90,
-$117,605.83/-$118,319.31, -$117,713.52/-$118,499.27,
-$121,183.83/-$121,834.27, -$114,609.19/-$115,404.23 and
-$108,648.77/-$109,460.58.

The independent larger block confirms the simulator mechanism in both robust
margin and paired win probability. V102 is still not promoted: run the exact
unchanged wrapper through a fresh six-seed, both-seat, six-opponent installed
real-engine gate. Mirrors, `DONE/DONE`, errors, invalid actions and timeouts are
hard validity conditions. Only matching real-engine evidence may trigger the
final source/test/documentation audit and selected-baseline decision.

The valid installed-engine gate is
`logs/arena/v102_vs_v89_real_standard6_31500.json` (real Kaggle engine,
seed0 31500, six seeds, both seats, six-opponent standard pool, 12 workers,
5.5 minutes). V89 and V102 mirrors are exactly zero on 6/6 seed pairs. All
180 games finish `DONE/DONE`: zero errors, zero not-DONE, no timeout and no
invalid action.

| screen | cells | V102 absolute paired margin | V89 absolute paired margin | V102-V89 | firing |
|---|---:|---:|---:|---:|---:|
| self-play | 6 seeds | head-to-head +$6,499 total; 5-0-1 | n/a | +$1,083.17/seed, SE $388.61, t=2.79 | 5/6 |
| standard external pool | 36 | -$120,749.64 mean; 0 wins | -$121,612.42 mean; 0 wins | +$862.78 mean, SE $145.55, t=5.93 | 36/36 |

External W-L is 34-2, a 94.4% paired win probability. Every installed-engine
row is positive: multi-route +$871.33 (6-0), frontier +$728.50 (6-0), v111
+$759.33 (6-0), 3000-socre +$422.67 (4-2), rank-your-agent +$669.50 (6-0),
and strong-barnyard +$1,725.33 (6-0). Corresponding V102/V89 absolute paired
means are -$97,758.50/-$98,629.83, -$124,014.50/-$124,743.00,
-$130,776.17/-$131,535.50, -$122,672.00/-$123,094.67,
-$128,801.00/-$129,470.50 and -$120,475.67/-$122,201.00.

The real engine agrees with quick18, standard108 and independent standard288
in both margin and paired win direction, and direct real self-play is positive
rather than concealed. V102 has met the required gameplay sequence but remains
pending the final complete-suite, compile/diff, determinism/import, strict
source and immutable historical-wrapper audit. No external submission is
authorized or performed.

Final promotion audit completed cleanly on 2026-08-28. The complete white-box
suite passes 199/199; `python -m compileall -q whitebox arena.py`,
`git diff --check`, and the selected-status documentation scan pass. Fresh
seed31600 V102 repeats versus multi-route both return `$77,818/$155,186`, 719
actions and SHA256
`ae155b4c129916f08b3a9f058284d6050d6488488a1bd3f435c5fd44e5d29b36`;
the repeat difference is zero and `FORBIDDEN_IMPORTED []`. The earlier clean
versus hostile-environment seed31100 closure is also exact.

Immutable wrapper hashes after every gate and the audit are:

```
V86  1b9993e45b4f67cfdcc5cf653778012442657c432292a497c4582072d9142b0e
V89  fb37c4953c2f85510878257d02b6a0a887e509a8750b2f226343d3490d76919c
V98  eb5c9114f541eb54cab05ef23e761f5fd88e7c840c8d18a079f7365e4e7ea7eb
V99  093e1a7ab6865ee41206bf38281464adf53dcbcacfd00f1b0eb69b1d83e9ebe6
V100 ddcf02761ee218261f469ca58e2de1ffb250a0f94e41d06c40263dc79aed55d1
V101 d3684059da80fff4e311d86929df970b9c81118cbd9caf6ea3569ce02cd4637a
V102 c26625d97246a2792154d59ca87e2220226278e9422ad33e5378d97ea47f50ff
```

**V102 is now the selected strict-white-box executable baseline.** This is a
local model-selection result, not an external submission. Its qualification is
quick18 +$526/cell (17-1), standard108 +$795/cell (90-14 plus four inert),
independent standard288 +$759/cell (259-25 plus four inert), and installed
real36 +$863/cell (34-2), with every opponent row positive at every gate, exact
mirrors, deterministic runtime below 142 ms in repeats, clean import closure,
and all 180 real games `DONE/DONE`. V89 remains the immutable gameplay baseline;
V86/V76/V69 remain earlier immutable baselines. No Kaggle action, network write,
or external submission occurred, and unrelated dirty user work was preserved.

The next unresolved terminal seam is no longer return-per-target feasibility.
V102's target/worker packing is still a deterministic exact-marginal greedy
primal, not a global prize-collecting optimum under shared time/capacity. A
successor may test a structurally bounded exact or certified-exchange chained
terminal master, but must retain one final DROP, exact decay, shared output
capacity, strict opportunity dominance and the 180 ms envelope. Do not tune a
route-value coefficient, fixed takeover step, opponent row, or target count.
The separate general-horizon gap also remains: multi-day retained inventory,
cash, service, shed room and persistent opponent-relative book value must be
selected jointly rather than through another one-step sale timing rule.

### V103 exact all-position terminal insertion (implementation checkpoint, 2026-08-28)

V103 is isolated at `whitebox/versions/v103_inserted_terminal_routes.py` and
inherits selected V102 everywhere except the terminal target-packing primal.
V102 selects each target by its exact aggregate nonlinear paired-sale marginal,
but can place it only after the last stop already assigned to a worker. That
append-only restriction is not an engine constraint: a lower-value target can
lie on the path through already selected higher-value stops and consume only
its named operation, while appending it after the endpoint would exceed the
remaining horizon.

V103 tests every insertion position `j=0..len(route_u)` for every worker and
target. Each trial recomputes the complete public-rule chain

```
L_u = distance(start_u, first) + operations(first)
    + sum_i>1 [distance(previous, next) + operations(next)]
    + distance(last, nearest_shed) + DROP
```

and revalidates the exact HARVEST offset/decay inequality for every target
already later in the reordered route. Target priority remains the exact
aggregate paired-sale gain. Complete closed length, incremental closed length,
public position/operations, worker index and insertion index break only equal
economic gains. Unique target claims, current carried load, one shared
100-item final capacity, production closure, hour-0 deferral, strict
terminal-vs-optimistic-general opportunity dominance and direct delivery
rescue are unchanged. There is no value/distance coefficient, fixed takeover
step, target-count limit, hidden schedule or remembered route.

Two equation tests prove that V103 collects three public targets in a 21-action
closed chain where V102's append-only primal can collect only the two
higher-value targets, and that inserting an operation is rejected when it
would delay a previously feasible crop past its exact decay step. The terminal
suite passes 24/24 and the complete white-box suite passes 201/201; modules
compile and `git diff --check` passes. V103 wrapper SHA256 is
`f2bece9da1436cfedb7f7c3059a79cce85965f715b92f3e68e4740c97adbb039`;
selected V102 remains byte-unchanged at `c26625d...`. This is implementation
evidence only. Run deterministic runtime/import closure, then a proportional
CRN screen against immutable V102 before any broader gate or selection claim.

The seed31700 runtime/determinism audit is
`logs/whitebox/v103_inserted_terminal_runtime_31700.txt`. Same-process V102
returns `$55,077/$95,340`, mean/P95/P99/max
21.332/103.368/135.781/174.462 ms. Two V103 repeats return
`$55,093/$95,344`, identical 719-action SHA256
`440ee21f53e8f0f85ccfc902c55937d67d0c398f666dc30252e0b6eb42c61f14`
and zero repeat differences. Their mean/P95/P99/max are
21.319/103.606/134.787/169.742 ms and 21.350/103.027/135.816/169.852 ms,
with zero calls at or above 170 or 180 ms. V103 differs from V102 only on
steps 706-718 in this trace and is deterministic/runtime-safe. The +$16 own
bank change proves execution but is not paired evidence; V102 remains selected
pending closure and CRN evaluation.

Fresh seed31800 import/environment closure against an inert public-only
opponent returns `$102,202/$3,000`, 719-action SHA256
`8e5c70cabfbda186ad21d2c756ddd15f77e1d1d3a71416c5c6e949be5fbc52e7`,
and `FORBIDDEN_IMPORTED []`. A separate hostile legacy-environment process
with the same six values used in the V102 audit returns identical banks,
action count and hash. V103 has no environment-selected policy or forbidden
production import. Proceed only to a fresh quick CRN screen against immutable
V102; closure alone is not selection evidence.

The valid rejection-only CRN screen is
`logs/arena/v103_vs_v102_quick_31900.json` (simulator, seed0 31900, six seeds,
hard pool, both seats, 26 workers, 1.9 minutes). Both mirrors are exactly zero
on 6/6 seed pairs and all 108 episodes finish with zero errors and zero
not-DONE statuses.

| screen | cells | V103 absolute paired margin | V102 absolute paired margin | V103-V102 | firing |
|---|---:|---:|---:|---:|---:|
| self-play | 6 seeds | head-to-head +$23 total; 4-2 | n/a | +$3.83/seed, SE $99.43, t=0.04 | 6/6 |
| hard external pool | 18 | -$110,645.28 mean; 0 wins | -$110,712.06 mean; 0 wins | +$66.78 mean, SE $37.94, t=1.76 | 18/18 |

External W-L is 10-8. Multi-route, frontier and v111 row deltas are
+$8.17 (1-5), +$132.50 (5-1) and +$59.67 (4-2); corresponding V103/V102
absolute paired means are -$90,018.00/-$90,026.17,
-$123,304.33/-$123,436.83 and -$118,613.50/-$118,673.17. The result is weak
and the multi-route win shape is a risk, but all row means, aggregate margin
and aggregate win count remain positive. Quick gates reject only obvious
regressions, so advance the byte-unchanged V103 to the independent 108-cell
standard gate against selected immutable V102. Do not promote or run 288/real
unless that larger block is consistently positive with exact mirrors/statuses.

The valid standard108 gate is
`logs/arena/v103_vs_v102_standard108_32000.json` (simulator, seed0 32000,
18 seeds, six-opponent standard pool, both seats, 26 workers, 6.9 minutes).
Both mirrors are exactly zero on 18/18 seed pairs; all 540 episodes finish with
zero errors and zero not-DONE statuses. V102/V103 wrapper hashes remain
`c26625d...` / `f2bece9d...`.

| screen | cells | V103 absolute paired margin | V102 absolute paired margin | V103-V102 | firing |
|---|---:|---:|---:|---:|---:|
| self-play | 18 seeds | head-to-head -$423 total; 10-8 | n/a | -$23.50/seed, SE $72.81, t=-0.32 | 18/18 |
| standard external pool | 108 | -$113,515.40 mean; 0 wins | -$113,600.86 mean; 0 wins | +$85.46 mean, SE $34.13, t=2.50 | 103/108 |

Conditional external delta is +$89.61 (SE about $35.70, t=2.51) with W-L
57-46 and five inert ties, a 55.3% paired win probability. Every row mean is
nonnegative: multi-route +$131.72 (10-6-2), frontier +$2.39 (9-8-1), v111
+$62.94 (9-9), 3000-socre +$9.61 (9-8-1), rank-your-agent +$64.22 (10-8),
and strong-barnyard +$241.89 (10-7-1). Corresponding V103/V102 absolute paired
means are -$102,305.78/-$102,437.50, -$115,434.94/-$115,437.33,
-$119,669.56/-$119,732.50, -$117,073.61/-$117,083.22,
-$114,899.78/-$114,964.00 and -$111,708.72/-$111,950.61.

The harness verdict is neutral because paired win probability is not yet
separable, and direct self-play is neutral/slightly negative. However, unlike
V77's stopped neutral gate, no opponent row has a negative mean; aggregate and
conditional margins are positive with full-shape firing. Confidence rather
than sign inconsistency is unresolved. Run the unchanged V103 through the
predeclared independent 288-cell standard confirmation. Do not run real-engine
or promote unless that larger block establishes positive robust paired win
probability as well as margin.

The predeclared independent 288-cell confirmation is
`logs/arena/v103_vs_v102_standard288_32100.json` (simulator, seed0 32100,
48 seeds, six-opponent standard pool, both seats, 26 workers, 17.4 minutes).
Both mirrors are exactly zero on 48/48 seed pairs; all 1,440 episodes finish
with zero errors and zero not-DONE statuses.

| screen | cells | V103 absolute paired margin | V102 absolute paired margin | V103-V102 | firing |
|---|---:|---:|---:|---:|---:|
| self-play | 48 seeds | head-to-head +$3,030 total; 30-17-1 | n/a | +$63.13/seed, SE $33.82, t=1.87 | 47/48 |
| standard external pool | 288 | -$114,901.09 mean; 0 wins | -$114,961.37 mean; 0 wins | +$60.28 mean, SE $17.34, t=3.48 | 275/288 |

Conditional external delta is +$63.13 (SE about $18.13, t=3.48), W-L 171-104
with 13 inert ties, a 62.2% paired win probability. Every row mean remains
positive: multi-route +$1.25 (24-22-2), frontier +$14.40 (25-20-3), v111
+$36.38 (30-17-1), 3000-socre +$32.52 (27-18-3), rank-your-agent +$39.29
(31-16-1), and strong-barnyard +$237.85 (34-11-3). Corresponding V103/V102
absolute paired means are -$107,433.56/-$107,434.81,
-$114,660.88/-$114,675.27, -$115,341.00/-$115,377.38,
-$124,288.77/-$124,321.29, -$111,859.19/-$111,898.48 and
-$115,823.15/-$116,061.00.

The larger independent block establishes positive aggregate margin and paired
win probability, and direct self-play is also positive. The effect is modest
and multi-route is effectively neutral, so no broad claim is warranted yet.
V103 has nevertheless met the major simulator gate sequence. Run the exact
unchanged wrapper through a fresh six-seed, both-seat installed real-engine
standard gate; mirrors/statuses are hard validity conditions and the real sign
must agree before any final selection audit.

The first installed-engine gate is valid but statistically neutral:
`logs/arena/v103_vs_v102_real_standard6_32200.json` (real Kaggle engine,
seed0 32200, six seeds, both seats, six-opponent standard pool, 12 workers,
5.6 minutes). Both mirrors are exact on 6/6 pairs and all 180 games finish
`DONE/DONE` with zero errors/not-DONE, timeout or invalid action.

| screen | cells | V103 absolute paired margin | V102 absolute paired margin | V103-V102 | firing |
|---|---:|---:|---:|---:|---:|
| self-play | 6 seeds | head-to-head +$498 total; 3-3 | n/a | +$83.00/seed, SE $111.10, t=0.75 | 6/6 |
| standard external pool | 36 | -$124,506.44 mean; 0 wins | -$124,564.11 mean; 0 wins | +$57.67 mean, SE $50.48, t=1.14 | 33/36 |

Conditional external delta is +$62.91, W-L 17-16 with three inert ties, only
51.5% paired. Row deltas are multi-route +$9.17 (3-2-1), frontier -$62.83
(2-4), v111 -$51.50 (1-5), 3000-socre +$93.67 (5-0-1), rank-your-agent
-$27.17 (2-4), and strong-barnyard +$384.67 (4-1-1). Corresponding V103/V102
absolute paired means are -$134,155.50/-$134,164.67,
-$116,981.17/-$116,918.33, -$120,072.00/-$120,020.50,
-$141,987.83/-$142,081.50, -$116,913.17/-$116,886.00 and
-$116,929.00/-$117,313.67.

The aggregate real margin sign matches simulator288, but paired win probability
and half the rows do not separate. Confidence is inadequate for promotion.
Because the simulator effect is independently significant yet only about
+$60/cell, the six-seed real sample is too small to distinguish it. Resolve
this once with a fresh 18-seed/six-opponent real108 confirmation of the
unchanged V103. Do not promote from real6, and stop this formulation if the
larger true-engine block does not establish both positive margin and paired
win probability.

The enlarged independent true-engine confirmation is
`logs/arena/v103_vs_v102_real_standard108_32300.json` (installed Kaggle engine,
seed0 32300, 18 fresh seeds, both seats, six-opponent standard pool, 12 workers,
16.4 minutes). Both mirrors are exactly zero on 18/18 seed pairs. All 540 games
finish `DONE/DONE`: zero errors, zero not-DONE, no timeout and no invalid action.

| screen | cells | V103 absolute paired margin | V102 absolute paired margin | V103-V102 | firing |
|---|---:|---:|---:|---:|---:|
| self-play | 18 seeds | head-to-head -$2,596 total; 7-11 | n/a | -$144.22/seed, SE $132.54, t=-1.09 | 18/18 |
| standard external pool | 108 | -$112,058.04 mean; 0 wins | -$112,100.03 mean; 0 wins | +$41.99 mean, SE $27.18, t=1.54 | 99/108 |

Conditional external delta is +$45.81 with W-L 66-33 and nine inert ties, a
66.7% paired win probability (win-rate t=3.32). Every true-engine row is
positive: multi-route +$34.28 (10-5-3), frontier +$31.94 (13-5), v111 +$10.50
(11-7), 3000-socre +$71.50 (8-6-4), rank-your-agent +$12.50 (11-6-1), and
strong-barnyard +$91.22 (13-4-1). Corresponding V103/V102 absolute paired means
are -$103,305.44/-$103,339.72, -$110,994.11/-$111,026.06,
-$114,693.94/-$114,704.44, -$124,003.39/-$124,074.89,
-$110,480.89/-$110,493.39 and -$108,870.44/-$108,961.67.

Direct real self-play is negative/neutral and is not concealed. The selected
objective is robust paired performance against the external pool: simulator288
is +$60.28 with W-L 171-104, preliminary real36 is +$57.67 with W-L 17-16,
and independent real108 is +$41.99 with W-L 66-33; every real108 row is
positive. This meets the prescribed simulator/true-engine evidence sequence
for a small major action-path change. V103 remains pending final complete-suite,
compile/diff, fresh determinism/import, documentation and immutable-hash audit
before any selected-baseline change. No external write or submission occurred.

Final V103 selection audit completed cleanly on 2026-08-28. The complete
white-box suite passes 201/201; compile, `git diff --check`, selected-status
documentation and JSON-log parsing pass. Fresh seed32400 V103 repeats versus
multi-route both return `$39,304/$75,087`, 719 actions and SHA256
`c3c6e422e03fe0d2e8b027c78044cf9cea4f2f8923f6221fa2a703531ad734c5`;
the repeat difference is zero and `FORBIDDEN_IMPORTED []`. The earlier
seed31800 clean/hostile-environment closure is exact.

Immutable wrapper hashes after every V103 gate and final audit are:

```
V89  fb37c4953c2f85510878257d02b6a0a887e509a8750b2f226343d3490d76919c
V102 c26625d97246a2792154d59ca87e2220226278e9422ad33e5378d97ea47f50ff
V103 f2bece9da1436cfedb7f7c3059a79cce85965f715b92f3e68e4740c97adbb039
```

**V103 is now the selected strict-white-box executable baseline.** This is a
local selection, not an external submission. Its evidence against immutable
V102 is quick18 +$66.78 (10-8), standard108 +$85.46 (57-46 plus five inert),
independent simulator288 +$60.28 (171-104 plus 13 inert), preliminary real36
+$57.67 (17-16 plus three inert), and independent installed real108 +$41.99
(66-33 plus nine inert). Simulator288 and real108 have every opponent row
positive; all 540 enlarged real games are `DONE/DONE`; runtime repeats stay
below 170 ms; imports/environment/determinism are clean. Direct enlarged real
self-play is negative at -$2,596, W-L 7-11, and remains explicit contrary
evidence. External robust paired margin/win probability—not own bank or direct
self-play alone—is the campaign objective. V102 remains the immutable gameplay
baseline; V89 and earlier wrappers remain immutable historical baselines.

No Kaggle action, network write or external submission occurred. The preexisting
dirty changes in `planner/simulate.py`, its fidelity test, `route/router.py`,
and all unrelated user files were preserved.

The next exact terminal gap is selected-set exchange, not insertion position.
V103 can insert each greedily accepted exact-marginal target anywhere, but it
cannot remove one earlier target to admit a jointly higher-value combination
under route time or shared capacity. A successor may test a deterministic
one-for-one certified exchange followed by exact insertion/refill, accepting
only a strict increase in the same aggregate paired objective and revalidating
all closed routes/decay/capacity. It must not add a value-distance ratio,
exchange-count knob, clock fallback or opponent-conditioned switch. Given
V103's modest incremental effect, require runtime evidence and reject quickly
if exchange is inconsistent. The separate higher-value general-horizon
cash/service/inventory objective remains unresolved as documented above.

### V104 certified terminal selected-set exchange (implementation checkpoint, 2026-08-28)

V104 is isolated at `whitebox/versions/v104_exchanged_terminal_routes.py` and
inherits selected V103 everywhere except the terminal target-set primal. It
first constructs the unchanged V103 inserted certificate. For every selected
target `q` and every rejected target `p`, it removes `q`, places `p` at the
shortest fully certified insertion among every worker/index, and refills all
remaining targets using V103's exact aggregate paired-sale marginal. Every
seeded route and refill trial recomputes complete closed length, all crop
HARVEST decay offsets, complete tile output, and the shared 100-item final
capacity. V104 replaces V103 only when final aggregate paired value is strictly
greater. This is one finite exchange neighborhood, not a tuned pass count;
route length breaks equal-value placement only. There is no value-distance
coefficient, clock fallback, opponent switch, hidden state, or remembered route.

Two new equation tests pass. In the defining eight-action counterexample, V103
greedily selects a distant one-WOOL trip because its singleton value is higher
than one MILK; neither nearby COW then fits. Removing WOOL, forcing one MILK,
and refilling the second produces a strictly higher two-MILK nonlinear bundle
in seven actions. A one-target case proves literal V103 certificate, route,
action, output, and value preservation when no rejected target exists. The
terminal suite passes 26/26 and the complete white-box suite passes 203/203;
compile and `git diff --check` pass. Immutable V102/V103 hashes remain
`c26625d...` / `f2bece9d...`; the V104 wrapper hash is
`5e65fe1d2f8bf74f889c540f74e35b61ec7ab2a1e4064eb301ad524da92c2b70`.
This is implementation evidence only. V103 remains selected. Next run a
deterministic runtime/action-firing audit and clean/hostile import closure; stop
or simplify V104 before gameplay if its structurally bounded neighborhood
threatens the 180 ms envelope.

The completed seed32500 runtime/determinism audit is
`logs/whitebox/v104_exchanged_terminal_runtime_32500.txt`. Same-process V103
returns `$44,590/$83,602`, mean/P95/P99/max
19.865/88.947/144.598/163.909 ms. Two V104 repeats return
`$44,497/$83,704`, identical 719-action SHA256
`d92ff8b3cfe11ef5916c2370752785a3b21bf798f4f501291b63a6ecc48ad2e3`
and zero repeat differences. Their mean/P95/P99/max are
19.955/88.262/145.040/161.867 ms and 20.042/90.852/143.636/163.823 ms,
with zero calls at or above 170 or 180 ms. V104 differs from V103 on steps
697-718, confirming broad terminal firing; its -$93 one-trace own-bank change
is diagnostic only. Fresh seed32600 clean and hostile-environment closure
versus an inert public-only opponent is exact: both return `$114,331/$3,000`,
719 actions and SHA256
`42589a6ef965ed74309678f1ffb6f69248714956d415d6bd0d619cc8bae464d6`,
with `FORBIDDEN_IMPORTED []`. V104 is deterministic, environment-independent,
import-clean and runtime-safe in this firing trace. V103 remains selected;
proceed only to a fresh rejection-sized CRN screen against immutable V103.

The valid rejection-only CRN screen is
`logs/arena/v104_vs_v103_quick_32700.json` (simulator, seed0 32700, six
seeds, hard pool, both seats, 26 workers, 2.1 minutes). Both V103 and V104
mirrors are exactly zero on 6/6 seed pairs; all 108 episodes finish with zero
errors and zero not-DONE statuses. Immutable V103 and V104 wrapper hashes are
`f2bece9d...` / `5e65fe1d...`.

| screen | cells | V104 absolute paired margin | V103 absolute paired margin | V104-V103 | firing |
|---|---:|---:|---:|---:|---:|
| self-play | 6 seeds | head-to-head +$622 total; 4-1-1 | n/a | +$103.67/seed, SE $64.63, t=1.60 | 5/6 |
| hard external pool | 18 | -$113,873.00 mean; 0 wins | -$114,007.67 mean; 0 wins | +$134.67 mean, SE $80.86, t=1.67 | 12/18 |

Conditional external delta is +$202.00 with W-L 11-1 among the 12 firing
cells; overall W-L-T is 11-1-6. Every row mean is positive: multi-route
+$322.83 (4-0 plus two inert), frontier +$55.33 (4-0 plus two inert), and v111
+$25.83 (3-1 plus two inert). Corresponding V104/V103 absolute paired means
are -$110,315.67/-$110,638.50, -$114,713.17/-$114,768.50, and
-$116,590.17/-$116,616.00. This is a strong rejection-screen shape, but only
12 external cells fire and the harness correctly labels it underpowered.
V103 remains selected. Advance the exact unchanged V104 to a fresh independent
18-seed, six-opponent simulator standard108 gate; do not run 288/real or select
unless the larger block preserves positive robust paired margin and win shape.

The independent standard gate is valid but not robust enough to advance:
`logs/arena/v104_vs_v103_standard108_32800.json` (simulator, seed0 32800,
18 seeds, six-opponent standard pool, both seats, 26 workers, 7.0 minutes).
Both mirrors are exactly zero on 18/18 seed pairs; all 540 episodes finish with
zero errors and zero not-DONE statuses. Wrapper hashes remain unchanged.

| screen | cells | V104 absolute paired margin | V103 absolute paired margin | V104-V103 | firing |
|---|---:|---:|---:|---:|---:|
| self-play | 18 seeds | head-to-head +$956 total; 8-2-8 | n/a | +$53.11/seed, SE $43.58, t=1.22 | 10/18 |
| standard external pool | 108 | -$107,774.89 mean; 0 wins | -$107,811.27 mean; 0 wins | +$36.38 mean, SE $26.99, t=1.35 | 53/108 |

Conditional external delta is +$74.13, W-L 36-17 among 53 firing cells; the
overall record is 36-17-55. Row deltas are multi-route +$132.28 (6-2-10),
frontier +$75.28 (6-5-7), v111 -$24.33 (4-4-10), 3000-socre +$25.56
(4-0-14), rank-your-agent +$65.39 (12-2-4), and strong-barnyard -$55.89
(4-4-10). Corresponding V104/V103 absolute paired means are
-$105,315.00/-$105,447.28, -$108,545.00/-$108,620.28,
-$110,150.72/-$110,126.39, -$118,014.56/-$118,040.11,
-$109,464.06/-$109,529.44, and -$95,160.00/-$95,104.11.

The aggregate and self-play signs are positive, but aggregate confidence still
crosses zero, only 49% of external cells fire, and two of six opponent rows are
negative. This fails the predeclared robust-row condition that allowed V103 to
advance. **V104 is therefore an unpromoted positive/neutral tombstone and gets
no 288-cell or real-engine gate. V103 remains the selected baseline.** Do not
tune exchange pass counts, value-distance ratios, target counts, or opponent
switches around this mixed result. The exact exchange equations and tests are
retained as audit primitives. The next high-value work should return to the
general productive-horizon gap: a policy-consistent cash/service/inventory
objective coupled to the actual daily replans, rather than a wider terminal
exchange or another standalone capital endpoint.

Final V104 tombstone audit completed cleanly on 2026-08-28. The complete
white-box suite passes 203/203; compile, `git diff --check`, selected-status
documentation and both JSON log-integrity checks pass. V89/V102/V103 remain
byte-unchanged at `fb37c4953...`, `c26625d...`, and `f2bece9d...`; evaluated
V104 remains `5e65fe1d...`. The dirty tracked planner/router work and all
unrelated user files remain preserved. No external write, Kaggle action, or
submission occurred.

### V105 complete shared-slot capital alternatives (implementation checkpoint, 2026-08-28)

V105 is isolated at `whitebox/versions/v105_complete_capital_tiles.py` and
inherits selected V103 except for the current daily capital route candidate
set. In V103's default `capital_tasks` construction, proposed animals consume
the nearest empty tiles before crop columns are built. If routing rejects such
an animal, the crop master cannot reclaim that physically empty tile because
no crop alternative exists there. This is proposal-order truncation, not an
engine constraint or an economic choice.

V105 gives every proposed animal/crop type every position in the same finite
shared frontier of size

```
min(number of live feasible empty slots, total proposed asset units).
```

Every column carries `exclusive_key=(CAPITAL_TILE, position)`, so at most one
asset occupies a tile. Exact per-market-order selection limits retain the
observation-derived proposal quantity for every item. The existing route
master then chooses item, tile, worker, hire count, cash, slots and fixed land
activation together under the unchanged aggregate nonlinear bundle objective.
This couples the correction to the actual daily replan without inventing an
asset, count, price, route-value coefficient, policy commitment, or future
schedule. V103 and all historical wrappers remain untouched.

Two equation/wiring tests prove that one proposed COW and one proposed MELON
both receive the identical two-position frontier, every alternative has exact
tile exclusivity, both item limits remain one, and the V105 master is
clock-independent, memoized and uses `TaskBundleObjective`. The complete suite
passes 205/205; compile and `git diff --check` pass. Immutable V103 remains
`f2bece9d...`; the V105 wrapper SHA256 is
`9cd42d6c6dbcd18d6edc39bce567d2a672c3e4409d03cb79e182a263bb1ab00d`.
This is implementation evidence only. V103 remains selected. Because the
complete column frontier is larger, runtime/determinism is a hard first gate;
do not run gameplay if any repeat threatens the 180 ms envelope.

The completed seed32900 runtime/determinism audit is
`logs/whitebox/v105_complete_capital_runtime_32900.txt`. Same-process V103
returns `$32,748/$79,596`, mean/P95/P99/max
18.795/70.234/93.192/111.653 ms. Two V105 repeats return
`$39,969/$82,096`, identical 719-action SHA256
`392c26c74ff865a3e981d173ec84d6e0015bf78b680c8fb3ff08b0e5dd0c8c37`
and zero repeat differences. Their mean/P95/P99/max are
21.022/84.399/114.867/131.903 ms and 21.014/83.457/113.756/132.038 ms,
with zero calls at or above 170 or 180 ms. V105 differs from V103 on 391
actions, first at step305 and last at step718. The +$7,221 own-bank and +$4,721
one-trace paired-margin changes are diagnostics only. Fresh seed33000 clean and
hostile-environment closure is exact: both return `$117,382/$3,000`, 719
actions and SHA256
`7eb9ae6035dd86ba0e3939bc38d54744eb3615b88ef625da51528a31425fd258`,
with `FORBIDDEN_IMPORTED []`. V105 is deterministic, environment-independent,
import-clean, broad-firing and runtime-safe in this trace. V103 remains
selected; proceed only to a fresh rejection-sized CRN screen.

The valid rejection-only CRN screen is
`logs/arena/v105_vs_v103_quick_33100.json` (simulator, seed0 33100, six
seeds, hard pool, both seats, 26 workers, 2.1 minutes). Both mirrors are
exactly zero on 6/6 seed pairs; all 108 episodes finish with zero errors and
zero not-DONE statuses. V103/V105 hashes remain `f2bece9d...` / `9cd42d6c...`.

| screen | cells | V105 absolute paired margin | V103 absolute paired margin | V105-V103 | firing |
|---|---:|---:|---:|---:|---:|
| self-play | 6 seeds | head-to-head -$61,815 total; 1-5 | n/a | -$10,302.50/seed, SE $6,428.34, t=-1.60 | 6/6 |
| hard external pool | 18 | -$130,153.11 mean; 0 wins | -$123,096.78 mean; 0 wins | -$7,056.33 mean, SE $3,444.92, t=-2.05 | 18/18 |

Every hard-pool row is negative: multi-route -$16,760.33 (1-5), frontier
-$1,586.00 (2-4), and v111 -$2,822.67 (2-4). Corresponding V105/V103 absolute
paired means are -$131,181.83/-$114,421.50,
-$128,385.33/-$126,799.33, and -$130,892.17/-$128,069.50. Overall external
W-L is 5-13 with full 18/18 firing. The harness's generic small-n label is
neutral, but the campaign decision is an obvious rejection: aggregate margin
is two SE negative, paired win probability is 27.8%, every opponent row is
negative, and direct self-play agrees.

**V105 is rejected and receives no standard108, 288-cell, or real-engine
gate. V103 remains selected.** The mechanism is physically correct and the
tests are retained, but completing the candidate tile set allows the unchanged
one-horizon value to choose a materially different, more productive own farm
that worsens opponent-relative margin. This is additional evidence that the
next step cannot expand the capital feasible set before the general objective
prices retained inventory, future service and persistent market externality
consistently with later daily replans. Do not tune frontier size, asset order,
item counts, or opponent-specific switches around this result.

Final V105 tombstone audit completed cleanly on 2026-08-28. The complete
white-box suite passes 205/205; compile, `git diff --check`, quick-log integrity
and selected-status documentation pass. V89/V102/V103/V104 remain byte-
unchanged at `fb37c4953...`, `c26625d...`, `f2bece9d...`, and `5e65fe1d...`;
evaluated V105 remains `9cd42d6c...`. The preexisting dirty planner/router
changes and all unrelated user files were preserved. No Kaggle action, network
write, external mutation, or submission occurred.

## 56. Desktop takeover and cumulative V103-versus-V56 gate (2026-08-28)

The user returned to the desktop after the persistent campaign. The STOP marker
`logs/remote_campaign/STOP` was created while iteration 35 was finishing. The
watchdog records iteration 35 `exit=0` followed by `stopped after iteration=35`,
and the `kagg-whitebox` tmux session is gone. There is no remaining remote
Codex, watchdog or arena process; the desktop task is now the sole writer to
`/home/yilewang/kaggriculture`.

Post-takeover verification passes 205/205 white-box tests, compileall and
`git diff --check`. Selected V103 remains byte-unchanged at
`f2bece9da1436cfedb7f7c3059a79cce85965f715b92f3e68e4740c97adbb039`.
V104 remains an unpromoted positive/neutral tombstone and V105 remains the
decisively rejected capital-frontier tombstone described above.

The selected-version gates establish several valid incremental improvements,
but the earlier handoff had no direct V103-versus-V56 common-random-number
measurement. A fresh desktop standard gate now closes that gap:
`logs/arena/v103_vs_v56_desktop_standard108_34000.json` (simulator, seed0
34000, 18 untouched seeds, six standard opponents, both seats, 26 workers,
6.3 minutes). Both V56 and V103 mirrors are exactly zero on 18/18 seed pairs;
all 540 games complete with zero errors and zero not-DONE statuses.

| screen | cells | V103 absolute paired margin | V56 absolute paired margin | V103-V56 | firing |
|---|---:|---:|---:|---:|---:|
| direct self-play | 18 seeds | head-to-head -$21,175 total; 10-8 | n/a | -$1,176.39/seed, SE $1,996.19, t=-0.59 | 18/18 |
| standard external pool | 108 | -$110,894.04; 0 wins | -$120,681.84; 0 wins | **+$9,787.81**, SE $2,444.37, t=4.00; 68-40 | 108/108 |

Every external opponent row improves in mean paired margin: multi-route
+$16,097.94 (15-3), frontier +$7,669.56 (12-6), v111 +$9,183.39 (10-8),
3000-socre +$16,358.89 (12-6), rank-your-agent +$8,127.94 (10-8), and
strong-barnyard +$1,289.11 (9-9). This is statistically credible cumulative
evidence that selected V103 is stronger than the V56 development state on the
predeclared external-pool objective.

Do not misreport the 68-40 record, or V103-versus-V102's real-engine 66-33-9,
as wins against the opponent pool. Those are **A/B improvement records**: a win
means the candidate's paired margin against a fixed opponent/seed is better
than the baseline's paired margin. Absolute V103 performance in this direct
gate is still 0/216 episode wins and 0/108 paired wins, with mean paired margin
-$110,894.04. Thus relative white-box performance improved materially, while
absolute competitive strength remains far from a gold-level agent. Direct
self-play against V56 is statistically neutral and slightly negative in margin;
it remains explicit contrary evidence.

V103 stays the selected strict-white-box executable. No Kaggle action, network
write or external submission occurred during takeover or this gate.

## 57. Hiring/task-expansion diagnosis and V107 crew-conditioned manifest checkpoint (2026-08-28)

The user correctly challenged the planning premise after the absolute strong-
pool audit remained at zero wins: the model appeared not to consider that
hiring more hands could make *more capital tasks* worth buying and completing.
The diagnosis confirms a structural defect rather than an interpretation issue.

### Opponent behaviour as a hypothesis source, not a policy source

A five-day engine-commit audit distinguishes actual successful HIREs from
requested tokens. Against selected V103, V103 hires `[2,0,3,2,4]` over days
0--4 and completes only six productive opening tiles: four COW and two
STRAWBERRY. Every standard-pool opponent successfully hires five hands at the
opening market phase. Multi-route, 3000-score and strong-barnyard complete 23
opening productive tiles (`7 WHEAT + 12 MELON + 2 COW + 2 SHEEP`); frontier,
V111 and rank complete 15 (`5 WHEAT + 5 MELON + 1 COW + 4 SHEEP`). The full
pool adds the same repeated families plus pure-architecture, which completes
21 tiles after four opening hires. These are observations for falsification,
not targets or action templates.

The transferable rule is derived from the engine instead. The first five
private-counter wages are exactly `1+1+2+3+5 = $12`, only 0.4% of the initial
bank, and a hand bought at opening hour zero contributes 23 action slots before
night. Hiring earlier weakly dominates the same affordable hire later because
the wage does not rise with the hour and the worker disappears at night. A hire
is nevertheless valuable only if re-solving the capital/task/routes with it
adds engine-valid work whose robust terminal-money increment exceeds its exact
Fibonacci marginal wage. Therefore neither `HIRE x5`, an opening tile count,
nor an opponent identity is admissible production logic.

The following reflection gate is now mandatory for every future behavioural
idea:

1. Observe only public or own-private engine state and successful commits.
2. Abstract an opponent action into an identity-free economic hypothesis.
3. Derive its cost, feasibility and payoff from engine equations.
4. Specify a counterfactual which can falsify the mechanism.
5. Implement only the transparent equation/certificate, never an action tape,
   fixed day schedule, opponent branch, fitted imitation weight or seed lookup.
6. Require deterministic execution plus absolute win, paired-margin and
   component-level A/B evidence. A familiar-looking farm is not evidence.

### Exact planning defect

The old capital path constructed `proposed -> columns -> all_tasks -> objective`
once before its crew loop. Each candidate `k` then changed only worker count,
Fibonacci cost, cash budget and remaining order slots. Thus a larger `k` could
reroute the same finite task set but could never create another seed/animal
purchase or another deployment task. `opening_hire_floor=5` in experimental
V106 consequently paid three extra workers *after* the capital solve without
rebuilding assets. A forced-five trace assigned all 16 tasks to only three
workers and left three paid workers empty.

Two additional non-white-box/consistency defects were found:

- `hiring.MAX_HIRE_CANDIDATES = 6` was explicitly justified by an observed
  historical maximum. The engine permits up to the ten market-order slots and
  has no six-hand rule.
- The route relaxation charged one aggregate PICKUP per item and included
  BUILD+PLACE, but `tasks.assign` discarded each tour's carry/operation
  manifest. Live execution then withdrew one item at a time, sometimes read
  another unit's inventory through `snap.carried()`, and represented an animal
  waiting in the shed as BUILD without its later PLACE. The planner therefore
  certified work that the emitted action path did not implement.

### Implemented strict-white-box repair

`whitebox/hiring.py` now accepts an optional `task_factory(k)` and rebuilds the
task universe for every cash/slot-feasible crew prefix. Its bound is

```
0 <= k <= min(remaining market slots, MAX_HANDS - current hands)
hire bill H(r,k) = sum_(j=0..k-1) fib(r+j)
```

with an exact cash-prefix test. There is no fixed five/six candidate cap. A
safe early stop is allowed only when the next nondecreasing Fibonacci wage is
greater than the maximum remaining positive value over *all already-inspected
future task universes*. Default fixed-task callers remain supported.

`capital.crew_conditioned_decision_curve` and
`capital_variant="crew_conditioned_phase_aligned_deterministic"` implement the
main repair used by the new candidate. For every legal `k`, the branch now:

1. pays the exact private-counter Fibonacci bill and consumes `k` current
   market slots;
2. independently calls the rule-derived paired portfolio inventor with that
   arm's service reserve, cash prefix and remaining slots;
3. converts that arm's own positioned proposal into PLANT+WATER or
   BUILD+PLACE columns;
4. jointly selects ordinary tasks and new capital under cash, physical tile,
   shed input, activation, order-key and day-boundary route constraints;
5. re-certifies the actually selected subset and records an audit row containing
   proposal/selection counts, completed tasks, capital cash, score and
   `J(k)-J(k-1)`;
6. returns assets from the winning `k` arm, never the legacy proposal or the
   final enumerated arm.

The new `Plan.service_cash_floor` separates observable husbandry obligations
from the historical fixed-five crew reserve.
`plan_variant="crew_conditioned_inventory_execution"` protects only that
service reserve and adopts observable live/seed/shed/carried capital as the
next execution target. The new arm solves the joint capital/crew program at
the day opening. Non-opening calls return an explicit zero-hire capital choice
instead of falling into the old fixed-task hire decider; a same-day fallback
had been measured hiring an extra hand at step 5, invalidating carried animal
manifests and losing placements that the opening certificate already funded.

`execution_variant="manifest_routes"` retains the complete route tour. Each
worker batch-PICKUPs its remaining route requirement once, reads only its own
inventory, executes the planned crop/animal identity and keeps BUILD+PLACE in
one task. `parallel_opening_manifest` additionally exposes the experimental
day-zero completion-balancing insertion. `route/router.py` now records the
transparent `turn_cost` and `completion_hour` certificate. Historical wrappers
which do not opt into a manifest retain their coordinate-only execution.

The isolated candidate is
`whitebox/versions/v107_crew_conditioned_manifest.py`, SHA256
`5feb540ea3394de35d8cf7bef2f3fb2ad3b2c762d1d2cd176ca0212c9cb6a242`. It
combines selected V103's market/terminal paths with:

```
capital_variant = crew_conditioned_phase_aligned_deterministic
plan_variant    = crew_conditioned_inventory_execution
execution       = manifest_routes
```

It does **not** set an opening hire floor or deterministic route refinement.

### Equation and trajectory evidence

On the seed-34000 opening observation, the auditable crew curve is:

| new hands `k` | exact bill | selected completed tasks | branch score | marginal score |
|---:|---:|---:|---:|---:|
| 0 | $0 | 7 | $11,131 | n/a |
| 1 | $1 | 12 | $16,884 | +$5,753 |
| 2 | $2 | 19 | $18,216 | +$1,332 |
| 3 | $4 | 24 | $19,101 | +$885 |
| 4 | $7 | 24 | $19,098 | -$3 |
| 5 | $12 | 24 | $17,916 | -$1,182 |

The winning branch independently proposes and selects
`3 COW + 1 SHEEP + 7 MELON + 13 WHEAT`. It hires three because the third hand
raises certified completed work from 19 to 24; the fourth adds no task and
fails its marginal wage. This is the intended white-box answer to the user's
challenge.

Manifest execution completes 22 of those assets before the first midnight:
`3 COW + 1 SHEEP + 7 MELON + 11 WHEAT`, with two WHEAT seeds pending. This is a
large mechanical change from selected V103's six opening tiles and unpromoted
V106's 12, but it also exposes a remaining two-task certificate/executor gap:
the capital arm's exact positioned layout admits 24 while the next-observation
daily greedy assignment selects 22. No claim of exact 24-task execution is
allowed until the selected positions/ownership are carried through or the
valuation uses the same 22-task assignment.

A finite deterministic route-refinement ablation raises actual opening
completion from 22 to 23, matching the strongest observed opening scale, but
it worsens the complete two-seat seed-34000 result to paired margin `-$123,890`
(`$77,600` versus `$139,545` in either orientation). It was removed from V107.
This is explicit counterevidence that maximising opening tile count is not the
season objective.

The unrefined V107 two-seat seed-34000 diagnostic versus multi-route is exactly
mirrored: V107 `$92,491` versus opponent `$133,214` in either orientation,
paired margin `-$81,446`. On the earlier same-seed diagnostics, unpromoted V106
was about `-$95,108` and selected V103 about `-$128,533`; V107 therefore moves
this one seed by approximately `+$13,662` versus V106 and `+$47,087` versus
V103. It still loses both episodes. This is one-seed mechanism evidence only,
not a pool result, confidence interval, promotion gate or win-rate improvement.

Manifest execution alone is not beneficial: replacing V106's executor without
the endogenous crew/capital model produced about `-$105,282` on the same
multi-route seed, worse than V106. The executor is a necessary consistency
component, not a standalone strategy.

V106 itself remains unpromoted. Its valid seed-35000 quick hard-pool A/B versus
V103 had exact mirrors and an encouraging 12-6 improvement-cell record with
about `+$4,562/cell`, but both arms still had zero absolute game and paired
wins, direct head-to-head was only 5-7, and the small screen was underpowered.
Forcing a cheap opening crew is therefore not accepted as the model.

### Verification and status

The complete repository test discovery passes **222/222**. Compileall for
`whitebox`, `route` and `arena.py`, plus `git diff --check`, passes. Hiring
tests cover engine h+1 spawn, eight legal hires, Fibonacci bills, early/late
day-boundary dominance, dynamic task factories, cash/slot bounds and the
value-proof stop. Capital tests prove per-k proposal rebuilding, exact
HIRE/reserve/slot inputs, winning-arm asset ownership and suppression of the
late fallback. Manifest tests cover aggregate pickup, per-unit inventory,
fertilizer, planned crop identity, BUILD+PLACE and day-boundary completion.

The initial V107 solve takes about 398 ms locally. This is below the one-second
engine action timeout but above the project's 180 ms soft envelope, so runtime,
parallel mirror determinism and clean/hostile import closure remain mandatory
before a gameplay gate. No hard-pool CRN screen has been run. **V107 is an
experimental checkpoint, not selected. V103 remains the selected strict-
white-box baseline.** Absolute selected-pool performance remains 0/216 episode
wins and 0/108 paired wins from section 56.

Next actions, in order:

1. Record a complete V107 runtime/action-hash repeat and clean/hostile import
   audit; stop or structurally memoize if the initial arm threatens timeout.
2. If valid, run only a fresh six-seed hard-pool CRN rejection screen versus
   immutable V103. Report actual episode/paired wins separately from A/B deltas.
3. Promote nothing from opening density or one seed. Advance only if external
   rows, true paired win probability and own/opp revenue decomposition agree.
4. If V107 survives, close the 24-certified/22-executed positioned-route seam;
   do not tune a target tile count or re-enable the rejected route refinement.
5. Continue the formal opponent-reflection loop on reinvestment, survival and
   sale timing, accepting only engine-derived, identity-free, falsifiable
   mechanisms.

No Kaggle action, network write or external submission occurred. The aborted
direct V107-versus-V103 command produced no durable result and is not evidence.

## 58. 2026-09-01 resume: current leader and behaviour-gap audit

The leaderboard/replay cache was refreshed rather than assuming the August
ranking. `planner.fetch_top_replays --top 8 --per-team 7 --sampling stratified`
downloaded 56/56 current-submission replays and updated
`logs/planner/top_replays.json`. The visible top eight were tetsuya 2918.2,
MtN 2835.6, Yusuke Hayashi 2831.8, islet 2830.3, Subramanya N 2816.3,
ringbearer 2814.3, yukino 2793.4 and zhyphirus 2778.1. Kaggle discussion also
warns that the displayed ELO can lag current code; the leader is therefore a
hypothesis source, never a policy oracle.

`logs/planner/top_analysis_20260901_002527.json` gives seven stratified current
tetsuya seats. Their mean final bank is about $110,240, with 315 total HIRE
requests, peak 12.3 hands, 3,118 useful operations and 39.7% operation use.
They sell about 1,681 units at $89.8/unit: the largest revenue shares are WOOL
27.6%, STRAWBERRY 20.4%, FERTILIZER 15.6%, MILK 14.1% and WHEAT 11.8%.

The repeatable public trajectory is concrete but is not copied into production:

- opening: 2 COW, 3 SHEEP, 10 WHEAT crop tiles and five HIREs;
- day 1: seven HIREs and the start of STRAWBERRY deployment;
- day 7/day 10: second and third quadrants;
- middle game: about 6 COW + 9 SHEEP, almost no GOOSE, about 35 STRAWBERRY;
- late game: STRAWBERRY/MELON gives way to roughly 45 WHEAT tiles;
- daily fertilizer collection and animal service continue until the terminal
  transition.

All seven openings also contain a reversible WHEAT treasury pattern. A
representative step buys 5 feed WHEAT, the assets/seeds/five HIREs, then 48
extra WHEAT; two steps later it sells 48 and buys the remaining SHEEP. This is
economically interpretable (unused market slot, reversible product curve,
public town drain and delayed capital commitment), but it is not a robust free
arbitrage against every feasible opponent market response. It remains a
candidate game action, not a hard-coded opening.

Against the same multi-route seed 79948465, V107 ends $93,182/$153,689. Its
opening is 3 COW + 1 SHEEP + 7 MELON + 13 WHEAT with three HIREs; it eventually
buys about 20 COW, 5 SHEEP, 4 GOOSE, only 12 STRAWBERRY and one extra quadrant.
The measured gap is therefore not simply "hire five": it is a coupled
cash-velocity, portfolio-mix, land-option, intraday-order-slot and opponent-
reaction gap.

## 59. Correct engine market game: per-unit lockstep, not batch cancellation

The installed engine source (`kaggle_environments` 1.32.6) and
`planner.simulate._process_market` both quote matching market-order slots one
unit at a time. In every joint round, both players receive `P(I)` from the same
pre-commit inventory `I`; successful above-floor commits then advance the book
twice. Only after one quantity is exhausted does the other order follow the
ordinary one-unit curve.

The older model treated whole batches as first/second, averaged the two seat
orders and concluded that opponent quantity cancels exactly. That theorem is
false for the engine. At STRAWBERRY inventory 10,000, prices begin 120, 118,
116. If we sell two units while the opponent sells one in the same slot, both
first units quote at 120 and our tail quotes at 116. Our exact zero-sum margin
increment is 236, versus the old standalone value 238.

`cashflow._lockstep_sale_result` now returns exact own revenue, opponent
revenue and closing inventory. `_paired_sale_exact` evaluates

```
our realised revenue
+ opponent revenue without our sale
- opponent revenue in the joint lockstep sale.
```

`_paired_sale_value` enumerates every opponent quantity in the named interval;
`_paired_bundle_value` and its candidate-minus-baseline form again use one
conserved hidden-shed allocation DP. The dated objective now adds the same exact
phase margin rather than standalone revenue. A direct differential test drives
`planner.simulate._process_market` and matches both banks and closing book.

This correction supersedes the cancellation claims in historical V70/V95
sections; those sections remain provenance, not current mathematics. Because
V103 imports the shared modules, its wrapper SHA256 remains `f2bece9d...` but
the earlier promotion gates do not requalify the corrected current-tree
semantics. V103 remains the historical selected comparison label; no successor
was promoted in this session.

## 60. V108--V110 fertilizer bridge: double-credit found and repaired

V108 explicitly credited one FERTILIZER only when a proposed animal's daily
route included `COLLECT_FERTILIZER`. V109 added solve-local pure-certificate
memoization plus pure engine-economics caches. Determinism is exact and a
seed-35100 repeat has identical banks/action hash, P95 about 13.3 ms and no call
at or above 180 ms.

The economic result is nevertheless a decisive rejection. V109's future book
contained product output from existing animals but omitted their daily
fertilizer. Every next-day capital solve therefore valued another animal as if
it were the first fertilizer supplier. A representative trace grew to more
than 30 animals. `logs/arena/arena_20260901_003212.json` gives V109 versus V103
hard-pool delta -$46,201 with W-L 1-17; versus V107,
`arena_20260901_003506.json` is -$55,148, W-L 4-14. Absolute pool wins remain
zero.

V110 reserves the exact public full-service fertilizer stream of all existing
own animals ahead of new output and exposes the opponent's corresponding
public upper schedule. Defaults preserve historical variants. On seed
79948465 it reduces V109's 51 purchased animals to 25, introduces 14
STRAWBERRY and improves own final bank from about $81k to $109k.
`arena_20260901_005643.json` confirms the repair versus V109: +$50,506/cell,
W-L 17-1. But the bridge creates no separable gain over V107:
`arena_20260901_005735.json` is -$2,827, W-L 9-9; versus historical V103,
`arena_20260901_005922.json` is a neutral +$8,013, W-L 9-9. Both candidate and
baseline still have zero absolute pool wins. V110 is a correct repair of a bad
experiment, not a promotion.

## 61. V111/V112 portfolio reflection: wider search is not the missing value

V111 tests one finite exact exchange direction after the bounded item-ray
constructor. It enumerates every one-unit replacement and then the whole
integer line only in the best direction; no mix target or fitted weight enters.
The certificate-selected exchange collapses one diagnostic farm from two
quadrants/29 animals to one quadrant/7 animals and $35,940 own bank.
`logs/arena/arena_20260901_010758.json` rejects it versus V107 at -$7,761/cell,
W-L 6-12, still zero absolute wins.

V112 removes the fixed singleton ordering instead: after every accepted asset
it recomputes all legal exact marginals, with the finite bound
`item_types * physical_slots`. It produces a more leader-like opening (2 COW,
2 SHEEP, six HIREs), later 25 STRAWBERRY and 16 SHEEP, and suppresses
multi-route strongly on one seed. Cross-opponent evidence does not hold:
`logs/arena/arena_20260901_011354.json` is +$3,655 mean but W-L 8-10, including
multi-route +$23,659 and frontier -$16,943. The harness correctly labels a
win-rate regression; absolute wins remain zero. V112 is not promoted.

The lesson is architectural. A more exact optimizer cannot fix a continuation
value which omits the option value of early cash/reinvestment and still treats
the opponent response as mostly exogenous. Search breadth merely chooses the
wrong objective more efficiently.

## 62. V113--V115 intraday hiring/land reflection: trajectory imitation fails

The leader's 12-hand days revealed a real engine option absent from V107:
HIRE and capital orders can be issued later in the same day, while V107 closes
the joint program after hour zero and forces HIRE, land and asset keys through
one ten-slot queue.

V113 reopened the complete joint crew/capital solve every turn using live
remaining hours and hires_today. It repeatedly credited fresh capital,
requested about 230 HIREs in one trace and regressed decisively:
`logs/arena/arena_20260901_012120.json` is -$55,765/cell, W-L 2-16; direct
head-to-head is 0-12. Runtime also expands from roughly 0.7 to 2.8 minutes for
the quick gate.

V114 kept capital at hour zero and reopened only the existing-task hire solver.
This did unlock a third quadrant, but exposed the omitted standing-farm future
workload: successive daily capital solves bought 116 GOOSE in one trace.
`logs/arena/arena_20260901_012528.json` rejects it at -$85,310/cell, W-L 3-15.

V115 then used the joint standing-farm/new-capital prefix only after a public
asset exists, while retaining V107's full-horizon empty-farm opening. It is the
closest emergent imitation of the leader so far: quadrants on days 7 and 12,
6 COW, 39 STRAWBERRY and a late WHEAT transition, without a target schedule.
That resemblance is actively misleading. `logs/arena/arena_20260901_012842.json`
is -$75,641/cell, W-L 1-17, and direct head-to-head is 0-12. Asset trajectory
without the leader's coupled sale/reinvestment/opponent policy is not a model.

All V108--V115 wrappers are isolated research arms. V111--V115 hashes are
recorded by the 2026-09-01 desktop transcript; none is selected.

## 63. Current status and next admissible architecture

The current complete white-box discovery suite passes 232/232 after the market
correction and all isolated variants; compileall and `git diff --check` pass.
No candidate achieved an absolute win against the hard opponent pool. V107 and
V110 remain useful experimental checkpoints, but only historical V103 carries
the prior promotion record, and the shared lockstep correction requires a new
qualification sequence before any current-tree selection claim.

The next architecture must couple three objects in one transparent state value:

1. early cash and its *feasible reinvestment option*, rather than treating a
   day-3 WHEAT dollar and day-12 MELON dollar as equivalent terminal cash;
2. standing-farm plus proposed-capital future labour/cash, with an explicit
   abandonment/continuation value so daily replans neither double-credit assets
   nor force an entire full-season policy;
3. a finite opponent response set whose asset/sale cost is charged to the
   opponent and whose market effect is evaluated by the exact lockstep game.

A valid lightweight Stackelberg arm should enumerate public, cash/slot/route-
feasible pure response directions and minimize absolute terminal margin over
them. Merely reserving every possible opponent output without its cost is too
conservative; predicting one likely response is not robust. Terminal work may
then use a small two-player tree over the last 5--8 days, but it is not the
largest observed gap and must not replace the productive-horizon work first.

Do not copy tetsuya's counts, add a sheep/strawberry multiplier, force three
quadrants, restore unrestricted intraday replanning, or promote a candidate
because its farm looks familiar. The required counterfactual remains absolute
pool wins plus paired margin/win-rate improvement under exact mirrors and a
true-engine gate. No Kaggle submission or other external write was made.

## 64. White-box documentation consistency audit

A final source/document audit removed the remaining live descriptions of the
obsolete whole-batch seat-average theorem. `MODEL.md` now gives the exact
per-unit lockstep recurrence and labels V95's premise invalid. V88's
`_terminal_split_value` and `inventory_master_orders` are explicitly documented
as reproducible own-cash tombstones rather than robust paired solvers; the
selected V103 terminal path does not call them. Current terminal/value
docstrings use the lockstep-margin terminology, and the old V82/V88 handoff
claims are marked as superseded by section 59.

This was a semantic/provenance correction, not a gameplay promotion. The final
verification remains 232/232 tests, successful `compileall`, and a clean
`git diff --check`. No current-tree candidate has passed the opponent-pool gate.

## 65. V116 unified finite Stackelberg capital value

`whitebox/stackelberg.py` implements the three previously missing objects in
one isolated capital value. The leader action set is finite: V107's public,
cash/slot/route-feasible crew rows. For a retained positioned capital set `a`,
the leader first chooses an endpoint `e` (exact first-output abandonment or
rule-minimum continuation) and one feasible realised-cash reinvestment `b`.
The follower response set contains `NO_RESPONSE` plus one direction for every
legal crop/animal. Within a direction, every publicly affordable integer
quantity on current unlocked empty tiles is certified; the exact standalone-
profit maximizer is retained. Opponent private shed/seeds are empty in this
proof, so every retained response is feasible from public money alone.

For response `r`, two persistent books are advanced by guaranteed public town
drain. The joint book clears our dated output against public standing opponent
output plus `r` using the exact per-unit lockstep engine recurrence. The
counterfactual book clears only standing opponent output. The payoff is

```
own realised revenue - joint opponent revenue
+ standing-only opponent revenue
- own certified asset/land/feed/hire cost
+ opponent certified asset/feed/hire cost.
```

The robust capital marginal is the candidate's minimum payoff over the named
responses minus the no-capital minimum over that same response set. This
normalization is load-bearing: setting no-capital to literal zero would charge
the leader for opponent profit that exists independently of our action and
would make every purchase lose by construction. No probability, lambda,
opponent identity, replay statistic, learned weight or target count enters.

Early cash is not multiplied by a coefficient. After the first certified sale
has reached cash, `feasible_reinvestments` may buy one crop on a still-empty
current-land tile, starting work the next day. It pays the exact seed cost,
additional Fibonacci hires and market slot, and combines an independently
closed exact first-output route with the standing/new workload. Every cash
prefix must preserve the live reserve. This is a constructive lower option,
not terminal dollars relabelled as early dollars.

Five initial equation/wiring tests covered response-cost sign, public response
feasibility, background normalization, realised-cash reinvestment, combined
standing/new routing and isolated variant dispatch. The final suite later grew
to 244 tests as the land/workload audits below were added.

## 66. V116 evidence: correct architecture, rejected policy

The first naive implementation put the max-min value inside every route
marginal and took 77 seconds for one opening decision. The final bounded
implementation generates the finite executable action rows first, then applies
the unified value only to complete candidates. Seed 36100 repeats are exactly
deterministic: identical banks and action SHA256
`ab0c85d30ae847fe484795f78034a12b84c8bd7b894ebb33bdbd61f57c690da2`.
Across 719 calls, mean/P95/P99/max are approximately
6.7/9.8/143/554 ms, with five calls at or above the 180 ms soft line and none
at the one-second engine limit. Runtime therefore remains experimental.

`logs/arena/v116_vs_v107_quick_36200.json` rejects V116 versus V107. The hard-
pool delta is -$28,730/cell, W-L 7-11, and candidate absolute game/paired wins
are both 0/36 and 0/18. Multi-route improves +$16,461, but frontier and v111
regress -$57,756 and -$44,895. Direct head-to-head is W-L 1-5 paired and
-$22,295/seed. Both same-version mirrors are exact.

The frontier diagnostic is explanatory. V116 buys no land, requests 156 hires,
executes 1,213 useful operations and earns $53,213, versus V107's one land,
170 hires, 1,780 operations and $74,235. The first reinvestment action set could
add only one crop to already-open land, so it did not represent the principal
cash option revealed by the leader audit.

## 67. V117/V118 land-option time consistency

V117 added a future action `BUY_LAND + BUY_SEED(q)` for every cash/slot/closed-
route-feasible one-product ray on the next quadrant. This was mathematically
feasible but dynamically inconsistent: the current value credited a future
land purchase which the later public replan was not committed to execute. A
frontier trace still bought zero land and fell to $55,902. It received no arena
gate.

V118 removed that promise. It allowed future fill only on a quadrant whose
current selected capital columns already paid the exact BUY_LAND activation.
All cash, seed, slot and closed-route constraints remained explicit. This arm
was action-identical to V116 on the same frontier diagnostic because V107's old
proposal objective chose the no-land universe before the robust recertifier
could compare a land universe. V118 also received no arena gate.

## 68. V119 land-arm recertification and rejection

V119 exposes exactly two physical proposal arms per crew count: current land
and exact next land. Each arm retains V107's bounded rule-derived asset rays,
then its complete proposal is recertified by the unified value before one arm
reaches the route solver. If land is already selected, future fill enumerates
every cash/labour-feasible quantity and retains the exact standalone-profit
maximizer per crop direction before the outer opponent min. This is a finite
equation reduction, not a crop or tile target.

The mechanism fires: on the frontier diagnostic V119 buys one land, restores
1,851 useful operations and improves own bank from V116's $53,213 to $64,334.
It also grows to 14 COW, 6 SHEEP and 10 GOOSE, revealing that the continuation
certificate still understates actual animal execution work.

`logs/arena/v119_vs_v107_quick_36300.json` rejects the arm. Pool delta is
-$26,282/cell, W-L 5-13, with all three opponent rows negative and zero
absolute candidate wins. Direct head-to-head is 0-6 paired at -$25,282/seed;
mirrors remain exact. V119 is not promoted.

## 69. V120 execution-aligned continuation audit

V120 changes only the optional continuation endpoint. New capital uses the
full engine-derived service profile including FEED, CARE, fertilizer collection
and dated HARVEST; ongoing crops pay daily WATER and dated HARVEST. The public
standing farm pays the same combined workload in candidate and baseline, and
its public output cash/market slots are credited symmetrically. First-output
abandonment remains available. Tests prove that today's projected unit phase
is excluded and future animal/crop operations and WHEAT pickups are explicit.

The correction exposes how optimistic V119 was, but it is too conservative as
an online policy: on the frontier diagnostic it makes only the opening
purchase, requests eight hires for the whole season, executes 346 useful
operations and ends $21,251/$154,432. The trace is a decisive mechanism-level
rejection, so no opponent-pool compute was spent. A full-service plan cannot be
treated as an obligation when the agent replans daily; an exact future model
must preserve continuation *and abandonment at every public replan node*, not
choose one all-season endpoint today.

V116--V120 are isolated research arms. None is selected. The implemented
Stackelberg equation is retained as an audit/value primitive, while the next
valid search must make its continuation policy recursively time-consistent.
Final verification is 244/244 tests, successful `compileall`, and clean
`git diff --check`. No Kaggle submission or external write occurred.

## 70. V121--V127 planner coverage/hiring audit (2026-09-01)

The user challenged the planner directly: enumerate more HIREs, cover the
current land, and tend toward filling a newly unlocked quadrant, but retain a
fully white-box economic test. The source/trajectory audit separates three
claims which had been conflated.

### What the existing crew master already does

At the untouched opening state, V107 enumerates every cash/slot/legal prefix
`k=0..10`. Its transparent curve is unchanged:

| new hands | exact bill | certificate-selected placements | score |
|---:|---:|---:|---:|
| 0 | $0 | 7 | $11,131 |
| 1 | $1 | 12 | $16,884 |
| 2 | $2 | 19 | $18,216 |
| 3 | $4 | 24 | $19,101 |
| 4 | $7 | 24 | $19,098 |

There are only 24 plantable tiles in the initial 5x5 quadrant because `(4,4)`
is a shed-access tile. Thus the planner does consider hiring enough people to
cover all current land: the third new hand adds five positive-value tasks; the
fourth adds no task under that certificate and correctly loses its extra $3
wage. No fixed crew target or leader count is missing from this enumeration.

The real defect is a planner/executor mismatch. The capital row uses its exact
near-shed positioned asset layout and `PositionedCertificateObjective`, then
the next observation discards those item/tile pairs, creates scan-order live
tasks and uses `TaskBundleObjective`. The certificate says 24, but V107's
emitted first day completes `3 COW + 1 SHEEP + 7 MELON + 11 WHEAT = 22`, with
two WHEAT seeds left. The exact next-observation projection added in
`capital._projected_execution_counts` proves the actual frontier: three hands
execute 22, four execute 24.

A seed-17 V107 trajectory already buys NE on day 8 and ends day 9 with 47 of
the 48 two-quadrant non-shed tiles occupied plus one pending STRAWBERRY seed.
It later opens empty tiles because one-shot crops mature/decay and assets die;
the observed gap is continuation/service and market value, not failure to
present a second-quadrant fill action.

### Exact mechanisms implemented

Seven isolated wrappers retain the rejected experiments and make each
hypothesis falsifiable:

1. **V121 positioned manifest.** The winning row records selected
   `positions_by_item`; the next live enumeration swaps fungible PLANT/PLACE
   tasks onto exactly those engine-valid tiles. Three opening hands now execute
   24/24. This retained object is our own just-issued action certificate, not a
   tape, identity feature or hidden model.
2. **V122 one-shot late hire.** Reopens the ordinary hire curve only at hour 1.
   It initially fires zero because that curve uses a different route objective
   and falsely believes all remaining work is already covered.
3. **V123 execution-aligned crew.** For every `k`, deterministically projects
   our HIRE/BUY effects, calls the exact next-observation live enumerator and
   bundle router, and caps purchases by executable item counts. It therefore
   chooses four opening hands and executes 24/24. Applying same-day completion
   to all later capital incorrectly deletes the long-horizon land option.
4. **V124 empty-farm execution alignment.** Restricts that truth condition to
   the observable state with no standing or pending capital. The opening state
   change alone still alters later land choice and regresses.
5. **V125 robust tail repair.** After the empty-farm crew winner, enumerates
   every integer quantity on only its last rule-derived asset ray under the
   unified finite Stackelberg value. The opening WHEAT ray peaks at 12, not 13;
   the thirteenth unit has positive own cash but negative robust margin. This
   local correction still cannot repair later recursive continuation.
6. **V126 incremental manifest hires.** At hour 1, prices new hands only against
   the opening cache's explicit `undone` tasks. Incumbents keep every original
   manifest, including animals already carried out of the shed; only new hands
   receive separate tail tours. It hires one extra opening hand, executes
   24/24 with all four animals placed and no seed remainder, and never performs
   another same-day hire solve.
7. **V127 empty-farm positioned manifest.** Retains the exact layout only for
   cold start, then restores ordinary daily replanning. This isolates the
   opening spatial choice from V121's later commitments.

The two structural predicates used above are live state predicates: empty
standing/pending capital and the current manifest's exact leftover set. There
is no calendar day, fixed crew count, target occupancy, fitted weight, replay
action, opponent name or hardcoded leader asset quantity.

### Game evidence: more coverage is real, but not yet better

`logs/arena/v121_vs_v107_quick_36400.json` is the only opponent-pool gate spent
on this line. Both same-version mirrors are exact. Direct V121-versus-V107 is
small and noisy at `+$680/seed`, paired W-L 2-4. Against the hard pool:

| opponent | V121-V107 delta/cell | W-L |
|---|---:|---:|
| multi-route | -$22,418 | 2-4 |
| frontier | -$9,126 | 2-4 |
| v111 | -$16,483 | 2-4 |
| **total** | **-$16,009** | **6-12** |

Candidate absolute results improve only from V107's 0/36 games and 0/18 pairs
to 1/36 games and 0/18 pairs. This is not a win-rate recovery or promotion.

The multi-route seed-36400 cell is more informative than occupied-tile counts,
but it does not identify coverage as the cause. V121 raises our bank from
`$34,464` to `$56,698` (`+$22,234`) but raises the opponent from `$80,872` to
`$143,609` (`+$62,737`), so paired margin falls `$40,503` per seat. The arm
simultaneously changes positioned execution, crop/animal composition, service,
later purchases and sale timing. V127's cold-start-only layout reproduces
almost the same cell (`$56,263/$143,565`), proving that the opening state starts
the divergence, not that high coverage itself is harmful. The earlier claim
that the denser layout by itself "keeps MILK/WOOL valuable" was an unsupported
causal attribution and is withdrawn.

Single-seed mechanism diagnostics reject the remaining variants before pool
compute. V123/V124 finish about `$47,152/$49,101` without land; V125 reaches
`$67,527/$86,805`; V126 reaches `$46,354/$49,432`; V127 reaches
`$65,979/$69,436`. These shared-process trajectories are explanations, not
statistical gates. They show that completing more profitable-own-cash tasks can
change later land and market state in the wrong zero-sum direction.

### Decision and next architecture

V121--V127 are research tombstones, not selected. V107 remains the experimental
crew/capital reference and historical V103 remains the selected label. Do not
add a direct coverage bonus, fixed four-hand opening, forced second-quadrant
fill or leader-derived peak-crew target. This does not forbid high coverage: it
requires coverage, composition, labour, cash and market interaction to win
together under robust terminal margin.

The next planner must make the productive continuation recursive. At each
later public state it must re-evaluate continuation versus abandonment while
carrying forward the shared market state and a finite costly opponent response.
That recursion must decide whether an early extra tile is valuable partly
because of—or harmful because of—its effect on the opponent's future sale book.
Without that term, a mechanically exact fill solver merely optimizes the wrong
game more efficiently.

All new task positions, market projections, Fibonacci costs, manifest tails,
route completion hours and robust tail quantities are directly auditable. The
complete suite now passes 250/250. V107's historical wrapper SHA256 remains
`5feb540ea3394de35d8cf7bef2f3fb2ad3b2c762d1d2cd176ca0212c9cb6a242`.
The V121--V127 wrapper SHA256 prefixes are respectively `8a64cd88`,
`9ac5bdb4`, `678024b3`, `3b9c1f5f`, `3e6c42eb`, `9d4d99d7` and `4de4058e`.
Final `compileall`, full discovery and `git diff --check` pass. No Kaggle
submission, network write or external deployment occurred.

## 71. Product-separated fixed-coverage repair (V128--V132, 2026-09-01)

The user correctly rejected section 70's causal shortcut: increasing our
output on a crop book does not directly conflict with an opponent's MILK or
WOOL book. The engine maintains an independent inventory/price curve for every
sellable product. The real planning question is which product occupies each
covered tile and whether entering the opponent's own book is valuable because
it takes revenue away from that opponent.

### Exact controlled comparison

For each winning crew row, the new coordinate solver keeps all of the following
fixed:

- the number and union of positioned capital tiles;
- the chosen Fibonacci hire prefix;
- current fixed market orders;
- whether the next quadrant is bought and its exact engine price.

It evaluates every legal one-unit source-to-target asset exchange from the
engine crop/animal tables, then enumerates the best direction's compatible
integer ray. Each candidate pays its exact capital bill and is recertified for
standing plus new labour, feed, shed/order capacity, dated cash, product-
specific shared books and finite paid opponent responses. Coverage contributes
zero objective value. The manifest persists the winning item/tile pairs, so the
executor cannot silently implement a different composition.

### Falsification chain

1. **V128, unconstrained robust exchange.** Opening coverage stays 24 and hires
   stay 3, but the mix changes from `3 COW + 1 SHEEP + 7 MELON + 13 WHEAT` to
   `3 COW + 1 SHEEP + 14 MELON + 6 WHEAT`. The quick hard-pool result is
   `-$35,436/cell`, W-L 2-16; head-to-head is `-$53,421/seed`, W-L 0-6. The
   finite endpoint preferred late MELON cash while deleting the early WHEAT
   action set. This is a research tombstone.
2. **V129, cash-prefix dominance.** An exchange is admissible only if exact
   post-cost cash is no lower on every certified day. The opening becomes
   `1 SHEEP + 10 MELON + 13 WHEAT`, still 24 positions, and the quick hard-pool
   gap recovers to `-$3,550/cell`, W-L 9-9. In the inspected multi-route game it
   buys NE on day 1 and finishes `$62,252/$119,890`, versus V107's
   `$34,464/$80,872`. Thus early land/coverage raises our production; the
   remaining loss is opponent-relative, not own-output failure.
3. **V130, full pure opponent continuation.** The old paid response set stopped
   at first output and represented a cow by one MILK. Each pure direction may
   now select abandonment or minimum-service full continuation. At opening the
   public set contains `BUY_COW_4_FULL` (44 output units, `$3,280` total paid
   cost), `BUY_SHEEP_5_FULL` (40 units, `$4,642`) and `BUY_GOOSE_8_FULL` (200
   units, `$5,993`), alongside all crop directions. V130 retains V129's opening
   action, so no pool gate was spent.
4. **V131, paid mixed responses.** Every unordered engine asset pair, affordable
   first quantity, remaining-budget second quantity and both nearest-slot
   layouts are certified. The opening context has 59 named responses and the
   worst response becomes a COW+MELON bundle, but the chosen action is still
   V129's and opening computation rises to about 1.55 seconds. It is retained
   only as an offline/tombstone arm.
5. **V132, scenario-dominant exchange.** A candidate must preserve the dated
   cash prefix *and* be opponent-margin non-worse in every named paid pure
   response, not merely improve whichever response currently attains the min.
   It opens `1 COW + 1 SHEEP + 9 MELON + 13 WHEAT`: 24 positions and 3 hires,
   with one COW retained for MILK-book contest.

The V132 quick gate at seed0 36400 is `+$2,639/cell`, W-L 12-6. The actual
>=100 firing-cell hard gate is
`logs/arena/v132_vs_v107_hard102_36500.json`: 102/102 fire, `+$3,194/cell`,
SE `$4,217`, t=0.76 and W-L 55-47. Per opponent:

| opponent | V132-V107 delta/cell | W-L |
|---|---:|---:|
| multi-route | +$6,794 | 20-14 |
| frontier | -$1,657 | 18-16 |
| v111 | +$4,444 | 17-17 |

Both mirrors are exact zero. The candidate still wins 0/204 individual hard
games and 0/102 absolute pairs, as does V107, so this is not a gold-level
recovery. The mean is positive but smaller than its standard error; the valid
verdict is **directional improvement, statistically neutral, not promoted**.

`logs/arena/v132_vs_v107_real_hard6_36500.json` is the real-engine sign check:
`+$1,958/cell`, W-L 3-3 over six paired cells, with exact mirrors. It agrees in
sign but is deliberately not treated as an independent promotion sample.

### Correct current interpretation

High coverage is economically compatible with crop output on books separate
from opponent MILK/WOOL. V129 and V132 recover most and then all of V121's
negative point estimate by changing composition while keeping coverage fixed.
However, a separate-book crop has an opportunity cost when producing MILK or
WOOL would saturate the very book from which the opponent earns rent. In the
seed-36400 V107 cell, early joint MILK/WOOL sales drive those books near the
floor. V129 delays MILK until day 11, allowing the opponent to sell much of its
day-8--18 MILK at high prices. V132's scenario dominance partially restores
that contest and is positive against the hard pool.

No result uses a replay action, opponent identity, fitted parameter, hidden
weight, probability over responses, or hardcoded leader asset count. V132 is
the current best research arm; V107 remains the comparison reference and V103
remains the historical selected label until a statistically separated gate and
absolute-win recovery exist.

The V128--V132 wrapper SHA256 prefixes are respectively `5fbe7b77`,
`6b32e81b`, `57b88415`, `7f0a2c64` and `10763ca1`. Final verification passes
254/254 white-box tests, `compileall` and `git diff --check`. No Kaggle
submission, network write or external deployment occurred.

## 72. Tape audit and joint crew/portfolio continuation tombstones (V133--V137, 2026-09-01)

The user correctly rejected treating `1 COW + 1 SHEEP + 9 MELON + 13 WHEAT`
as a plausible mainstream prior. All 56 files named by
`logs/planner/top_replays.json` were parsed from raw public replay state. The
day-one audit is:

| quantity | q25 | median | q75 | mode / frequency |
|---|---:|---:|---:|---:|
| opening HIRE | 5 | 5 | 5 | 5 / 49 of 56 |
| COW | 2 | 2 | 2 | 2 / 49 of 56 |
| SHEEP | 2 | 2 | 2 | 2 / 46 of 56 |
| MELON | 8 | 12 | 12 | 12 / 42 of 56 |
| WHEAT | 7 | 7 | 7 | 7 / 42 of 56 |
| occupied productive tiles | 22 | 23 | 23 | 23 / 39 of 56 |

The exact `2 COW + 2 SHEEP + 12 MELON + 7 WHEAT` vector occurs in 39/56
seats. GOOSE is zero in 55/56. A second six-seat regime adds seven CARROT, and
tetsuya is a seven-seat outlier. This concentration proves V132 is outside the
strong behavioural basin; it is **not** a production target. Production still
imports no replay/schedule/identity module, reads no action tape and exposes no
learned coefficient. Online tape features are explicitly `()`.

### Certificate diagnosis

On the initial public state, the same unified certificate values the strong
modal vector far above V107/V132 once own full service is included. The
important defects were outside the asset table:

- fixed coverage forced 24 positions although the modal vector uses 23;
- cash-prefix dominance treated lower early cash as lower utility even when
  the dated reserve/bridge certificate remained feasible;
- harvested one-time crop positions were blocked forever;
- current-land reinvestment allowed only one seed and one stage;
- own continuation used minimum survival while opponent responses received
  paid full continuation; and
- robust composition ran after the winning three-hand arm was selected.

New isolated primitives are `asset -> IDLE`, finite multi-ray strict ascent,
released-tile rotation chains, paid next-land fill, full FEED+CARE+wage
continuation, fertilizer cash/value separation, same-day selected-output wage
collateral, named service-reserve consumption and maximum-coverage crew-
frontier revaluation. A smaller crew row is pruned only when its full public
position set is contained in every retained frontier universe; excess
positions may be explicitly idled. No leader count enters that proof.

### Falsification results

1. **V133a, unrestricted variable coverage.** It selected `24 MELON`.
   `logs/arena/v133_vs_v107_quick_36600.json` is `-$70,292/cell`, W-L 1-17;
   direct head-to-head is 0-6.
2. **V133b/V134, full service and output-backed hiring.** Full fertilizer
   credit entered a GOOSE-heavy basin. The six-cell smoke
   `logs/arena/v133b_vs_v107_smoke_36700.json` is `-$144,838/cell`, W-L 0-6,
   and the no-opponent bank was about `$36.3k`. Output-backed hiring enumerated
   larger prefixes but still chose one day-one hire because the daily route
   relaxation said all service tasks already fit.
3. **V135, feed reserve consumption isolated on V132.** Feed may consume
   `service_cash_floor`; acquisitions may not. Against V132,
   `logs/arena/v135_vs_v132_quick_36800.json` is neutral: `-$482/cell`,
   SE `$7,189`, W-L 8-10, exact mirrors and zero absolute wins. A no-opponent
   trace falls from `$115,897` to `$90,137`, so it is not promoted.
4. **V136, fertilizer bridge without fertilizer utility.** Fertilizer cash can
   satisfy bridge feasibility but FERTILIZER is removed from leader payoff.
   This removes speculative GOOSE rent but still favours late MELON because
   continuation is not a complete multi-stage policy.
5. **V137, crew-frontier portfolio solve.** Revaluing every contained maximum-
   coverage crew arm before selection endogenously chooses five opening hires;
   nothing sets five in wrapper or solver. Its latest no-opponent bank is only
   `$25,721` versus V132's `$115,897`, so it is rejected without a pool gate.
   Opening computation is roughly 20 seconds and is also operationally
   inadmissible.

Appearance imitation is unsafe. The remaining architecture gap is a finite
multi-stage Stackelberg continuation jointly implementing intraday fertilizer
liquidation, service-input purchase, wage timing, repeated one-time-crop land
release, land activation and later asset reconfiguration. Its execution
manifest must reproduce the same cash bridge. Until then V132 remains the best
research arm, V107 the comparison reference and V103 the historical selected
label; absolute hard-pool wins remain zero.

V133--V137 wrapper SHA256 prefixes at this handoff are `e9f20cce`,
`c3a46eef`, `407b5e9f`, `2ba6148b` and `d931b20b`. Historical arena files
identify the checkpoint semantics above; these tiny wrappers share evolving
whitebox modules, so log plus handoff, not wrapper bytes alone, is the
reproducibility record. No Kaggle submission, network write or deployment
occurred.

Final local verification after these isolated additions passes 256/256
whitebox tests, `compileall -q whitebox` and scoped `git diff --check`.

## 73. Full-season herd audit and standing-book tombstones (V138--V145, 2026-09-01)

The prior 56-seat tape audit described only the day-one farm. A new read-only
scan of every public day boundary confirms the user's correction: livestock is
a cross-day capital ramp, not an opening constant.

| peak quantity | q25 | median | q75 | leading modes |
|---|---:|---:|---:|---|
| COW | 6 | 7 | 9 | 7 (15), 6 (13), 9 (13) |
| SHEEP | 5 | 6 | 9 | 6 (16), 5 (12), 9 (6) |

The common peak pairs are `7 COW + 6 SHEEP` (13/56), `9 + 5` (12/56),
`8 + 9` (5/56), `6 + 10` (4/56) and `6 + 11` (3/56). SHEEP reaches at least
eight in 21/56 seats and COW reaches at least eight in 22/56. One seat peaks at
`4 COW + 8 SHEEP`. This is offline falsification evidence only. No replay
feature, team identity, target count, fitted coefficient or schedule enters
the production dependency graph.

### Diagnosed equation error

V132's inspected passive trajectory grows from `1 COW + 1 SHEEP` on day one to
`8 COW + 1 SHEEP + 3 GOOSE`. The capital certificate did expand livestock,
but its candidate response margin omitted our standing output from the shared
market path. It therefore failed to charge a new COW for the MILK pressure
created by existing COWs.

The opt-in `stackelberg._standing_response_margin` merges the public standing
full-service schedule with candidate output before lockstep sale against every
paid response. `make_context(include_own_standing_book=True)` records the
standing schedule and computes the no-action robust reference with the same
equation. Existing variants default to the historical equation. Runtime inputs
remain public state plus engine costs, output clocks and market curves.

### Isolated results

1. **V138, standing book under the V132 cash-prefix order.** The changed
   marginal affects composition, but still cannot replace a `$400` COW with a
   `$500` SHEEP when early cash falls.
2. **V139/V140, cash as feasibility globally.** Removing the prefix across the
   entire portfolio bought four opening animals and left `$116`; the executor
   then protected the feed reserve from its own WHEAT purchase and all four
   animals escaped. Restricting exchange to the engine's crop/animal classes
   did not repair this execution mismatch.
3. **V141, executable service reserve.** Only WHEAT may consume the named
   service reserve; other capital still may not. Animals survive and the trace
   reaches `8 COW + 4 SHEEP` before over-expanding to 24 SHEEP. This proves the
   sheep action is reachable without a target, while falsifying the inherited
   maximum-coverage scale.
4. **V142, animal-to-IDLE scale.** Every animal can be deleted from a candidate
   only by strict robust improvement. The inspected endpoint becomes `9 COW +
   5 SHEEP + 1 GOOSE`, within the tape's broad herd distribution but not copied
   from it. `logs/arena/v142_vs_v132_quick_36900.json` is a regression-shaped
   `-$19,209/cell`, SE `$10,163`, t=-1.89 and W-L 8-10, so it is rejected.
5. **V143/V144, second-pass rebalancing.** The first pass is exactly V132;
   the second cannot change total livestock or crops. Engine structure, not
   tape frequency, separates PASTURE COW/SHEEP from COOP GOOSE. Requiring
   non-degradation in every response leaves the PASTURE rebalance inert.
6. **V145, pure robust PASTURE rebalance.** The second pass may harm a
   non-binding response only when the minimum paid-response margin strictly
   rises. The inspected passive endpoint is `12 COW + 1 SHEEP`, with `$121,079`
   versus V132's `$116,685`. The 18-cell quick screen is `+$5,486/cell`, W-L
   12-6, but the required hard gate reverses it:
   `logs/arena/v145_vs_v132_hard102_37000.json` is `-$3,881/cell`, SE `$3,818`,
   t=-1.02 and W-L 51-51. Per-opponent deltas are `-$1,906` multi-route,
   `-$8,620` frontier and `-$1,118` v111. Candidate absolute game wins are
   0.5% versus V132's 1.0%. V145 is not promoted.

The full-season audit validates a large and sometimes sheep-heavy herd, but it
does not validate any fixed animal vector. The remaining missing object is a
single multi-stage executable program over herd scale, PASTURE composition,
crew, land and service purchases. Its finite opponent quantity must be a paid
best response to each candidate, not the standalone-profit quantity reused for
all candidates. Until that exists, V132 remains the best research arm, V107
the comparison reference and V103 the historical selected label. Absolute
hard-pool performance remains effectively zero; there is no gold claim.

V138--V145 wrapper SHA256 prefixes at this handoff are `c5d7ebdd`,
`6928b7d3`, `367ec138`, `597fe5ee`, `760c915e`, `dd9a85f6`, `da1158d7f` and
`c9073b9a`. No submission, network write or deployment occurred.

Final verification passes 259/259 whitebox tests, `compileall -q whitebox` and
scoped `git diff --check`. The production modules contain no replay, schedule
or identity import; the only matching `replays/` text is an unreachable
historical explanatory comment in `strategy.py`.

## 74. Complete response quantities and the third-quadrant planner (V146--V152, 2026-09-02)

### What was repaired

`stackelberg.finite_public_responses(..., complete_products=P)` now retains
every feasible paid quantity for any response asset whose sale product is in
the leader candidate's named set `P`; unrelated directions keep the historical
standalone maximizer.  `make_context` records that set, and the standing-book
margin prices our existing output, current candidate output, opponent standing
output and the selected response on one dated nonlinear book.  V146 isolates
this on MILK/WOOL.  It is semantically correct but economically rejected: the
passive trace chooses 10 COW, no SHEEP and banks `$101,444`, below V132.

The land audit then proved that V132's fixed-coverage exchange cannot invent a
new position or `BUY_LAND`.  Earlier V119 did expose both physical arms, but
its land ray was won by durable animals and over-expanded.  V147 adds a
crop-only next-land arm; allowing it at opening destroys the validated
`1 COW + 1 SHEEP + early WHEAT` chain and banks only `$100,883`.  Restricting
it to later land is inert.  V148 puts later crop rays and all complete crop
responses into the global standing-book row ranking; it does not buy land,
changes every later no-land row, falls to `1 COW + 3 SHEEP` and `$67,673`, and
is operationally too slow.  Both are tombstones.

### V149 strict incremental challenger

V149 first completes V132 unchanged.  With at least two public quadrants, it
then creates crop-specific integer next-land quantities, keeping all feasible
leader quantities rather than only the standalone maximum.  For each crop it:

- pays exact land, seed, fixed-order, hire and service cash;
- retains every paid opponent quantity on that crop book;
- preserves incumbent positioned capital as mandatory route columns;
- treats incumbent ordinary tasks as explicit opportunity value, not a hard
  all-or-nothing constraint;
- routes the largest prefix that actually fits the crew/order/cash resources;
- rebuilds orders from the selected item/position pairs; and
- accepts only if robust capital margin plus retained task value minus wages
  strictly exceeds the exact V132 incumbent.

The key audited state is passive seed 37120, day 11.  The old one-sided ray
asked for 19 STRAWBERRY tiles and the route rejected the whole bundle.  The new
master selects 4 executable tiles with 7 hires, explicitly loses `$587` of
ordinary task value, and still raises total robust value `$21,494 -> $21,968`.
The emitted action buys the third quadrant and the four seeds; the end state is
`9 COW + 6 SHEEP + 1 GOOSE`, `$128,349`, versus V132's `$112,625`.  No number
in that vector appears in production code.

`logs/arena/v149_vs_v132_quick_37200.json` is the promising iteration screen:
`+$9,752/cell`, SE `$4,711`, t=2.07, 11/18 firing and conditional W-L 8-3.
The required gate is `logs/arena/v149_vs_v132_hard102_37300.json`:

| opponent | delta/cell | firing W-L-T |
|---|---:|---:|
| multi-route | +$4,471 | 17-9-8 |
| frontier | -$744 | 9-14-11 |
| v111 | +$760 | 9-9-16 |
| **total** | **+$1,496** | **35-32-35** |

The total SE is `$1,400`, t=1.07.  It fires 67/102 cells; conditional mean is
`+$2,277`.  Candidate and V132 absolute game and paired win rates are both
2.0%.  This is directional improvement with no absolute-win regression, but
it is statistically neutral and has fewer than 100 firing cells.  **Do not
promote V149.**  It is the strongest current land research arm; V132 remains
the evidence-backed research reference, V107 the historical comparison and
V103 the selected label.

### Recursive continuation failure

In the worst frontier seed 37320, V149 buys crop land correctly but later V132
replans the extra capacity as new animal space.  It ends with 24 COW + 1 SHEEP;
relative to V132 it sells 28 more MILK units but earns `$2,751` less on MILK,
loses `$3,835` of EGG revenue and lets the opponent bank roughly `$9,380` more.
This falsifies a one-stage land continuation.

- V150 applies candidate-complete COW/SHEEP/IDLE PASTURE repair only after the
  third quadrant.  It is inert in the diagnosed state.
- V151 allows every current asset class and IDLE after expansion.  Pure max-min
  instead raises the bad state to 27 COW and is rejected before a pool gate.
- V152 treats public quadrants after the first two as crop-land covenants and
  prevents current animal purchases there.  It repairs seed 37320 from
  `$112,113/$170,598` to `$125,821/$161,275`, while preserving the passive
  `$128,349`; however `logs/arena/v152_vs_v132_quick_37500.json` is
  `-$393/cell`, SE `$1,891`, firing W-L 2-8.  It is rejected.

The next admissible architecture is not another target mix.  It must carry the
actual next-observation replan (including later cross-product opponent
adaptation) inside the current land Stackelberg action, then emit the same
crew/capital manifest.  A permanent crop covenant is too restrictive; an
uncommitted land option is time-inconsistent.

V146--V152 wrapper SHA256 prefixes are `76ce79e4`, `39e35705`, `6057aae7`,
`d24541dc`, `db66a85f`, `f2538c4b` and `5c58d72a`.  No Kaggle submission,
network write or deployment occurred.

Final verification passes 269/269 white-box tests, compiles `whitebox/` and
`arena.py`, and passes `git diff --check`.  The scoped production search finds
no replay, opponent-file or identity import; the only matches are explanatory
statements that those inputs are absent.

## 75. Opponent-behaviour falsification and candidate-bound staged labour (V153--V158, 2026-09-02)

### The actual win-rate baseline

The current formal number has not improved: V149 and V132 each win 4 of 204
hard-pool episodes (`2.0%`) and 2 of 102 paired cells (`2.0%`) in
`logs/arena/v149_vs_v132_hard102_37300.json`.  The reported 35-32-35 is the
candidate-versus-baseline *delta* on firing paired cells, not our game record
against the opponent pool.  Absolute paired margin remains roughly `-$83,484`.

### What was learned from public opponent behaviour

The opponent sources/tapes were inspected only offline as falsification
witnesses.  Frontier/v111 request five opening hires, expand around days 6 and
10, and realize an approximately 8 COW + 4 SHEEP farm with substantial WHEAT,
MELON and STRAWBERRY occupancy; multi-route expands around days 6 and 11 and
realizes roughly 8 COW + 6 SHEEP with more crop positions.  Both families
request about 264--277 hires over a season.  In frontier seed 37320, frontier
earns `$170,598` from a far cheaper 8C+4S mixed farm while V149 ends at
`$112,113` after accumulating 24 COW.  Its main product revenues are WHEAT
`$18,020`, fertilizer `$11,726`, WOOL `$25,683`, MILK `$53,665`, MELON
`$16,210` and STRAWBERRY `$70,568`.

These observations refute our narrow capital/action set and recursive land
continuation; they are not model inputs.  Production contains no tape import,
opponent identity, target composition or replay counter.  In particular, no
8/4 or 8/6 vector was copied into a planner.

### Broad late-hire and standing-service failures

- V152 versus V149 at fresh seed 37600 is exactly inert in 18/18 cells
  (`logs/arena/v152_vs_v149_quick_37600.json`).
- V153 reopens generic existing-task hiring after the capital phase.  A passive
  episode requests 271 hires, buys 101 COW and ends at only `$46,082`; generic
  extra labour expands unpriced capital rather than serving a named marginal
  asset.
- V154 charges every proposed animal against the full standing-farm service
  book.  It avoids the 101-COW failure but is time-inconsistently conservative:
  only one extra quadrant, 7C+4S+1G and `$44,106`.  Full-season commitment is
  not a substitute for daily replanning.
- V155 combines current-empty-land crop rotation with generic hour-1 manifest
  hires.  Its passive bank is `$128,816`, but the decisive six-seed hard screen
  `logs/arena/v155_vs_v149_micro6_37700.json` is `-$25,017/cell`, SE `$8,325`,
  t=-3.01, firing W-L 1-5.  Multi-route, frontier and v111 are all negative.
- The causal split is exact: V156 (tail hires only) reproduces V155's passive
  trajectory; V157 (rotation only) reproduces V149's `$128,349`.  Therefore the
  loss came from unbound tail hiring, while the strict current-land challenger
  was inert.

### Exact two-phase certificate and V158

`cashflow._two_phase_hire_schedule` is retained as a rule-derived feasibility
primitive.  A future route set may use the farmer plus at most nine hour-0
hands when a WHEAT order occupies one of ten market slots, then at most ten
hour-1 hands; the second wave has 22 rather than 23 remaining actions.  The
certificate records `(hour0, hour1)` counts by day and rejects any route whose
closed-path cost exceeds the corresponding action horizon.  Tests cover
12 routes -> `(9,2)`, 20 -> `(9,10)`, and rejection of 21.

V158 makes that second wave candidate-bound.  The current-land challenger
enumerates an explicit deferred count, pays its exact Fibonacci prefix,
creates only those hour-1 spawn/action capacities, preserves every incumbent
ordinary task and positioned capital task, recertifies the retained crop
positions, and stores only the winning count for this seat/day.  Hour 1 pops
that certificate once; live order, hand, cash and service-floor checks may only
reduce it.  There is no later capital reopen and no crop/count/date target.

Passive seed 37120 keeps V149's land dates and 9C+6S+1G structure, triggers six
hour-1 events, nets 12 more seasonal hires and 15 more WHEAT purchases, but
raises final cash by only `$26` to `$128,375`.  The fresh hard screen is
`logs/arena/v158_vs_v149_micro6_37800.json`:

| opponent | delta/cell | firing W-L-T |
|---|---:|---:|
| multi-route | -$2,767 | 1-5-0 |
| frontier | +$3,683 | 3-3-0 |
| v111 | +$953 | 3-1-2 |
| **total** | **+$623** | **7-9-2** |

It fires 16/18 cells; conditional mean is `+$701`, SE `$1,526`, t=0.46.
Candidate and V149 absolute game win rates are both `2.8%`; paired pool wins
remain zero.  Because paired improvement frequency falls below 50%, this is a
rejected/neutral research arm, not a promotion.  The cross-opponent sign split
is evidence that the local route certificate still omits a dynamically
consistent shared-market/opponent-response continuation.

During this implementation a strict `missing_ordinary` condition accidentally
leaked from V158 into V149's shared next-land path and delayed V149's third
quadrant.  The condition is now explicitly gated by `allow_deferred_hires`.
Fresh replay of passive seed 37120 restores V149 exactly to `$128,349`, land on
days 2/11, 9C+6S+1G and 226 hires.  This isolation check is mandatory before
reading any V158 result.

V153--V158 SHA256 prefixes are `0eb21d8d`, `6af688c7`, `fb8da573`,
`9fb8c1fa`, `10fbe2c3` and `8bd77a5b`.  V132 remains the evidence-backed
research reference; V149 remains the strongest directional land arm.  No
gameplay candidate was promoted and no submission occurred.

### Persistent white-box campaign restart

The workspace is already on `jll-3090.server.thuiiif` (`10.144.51.6`; 52 CPU
cores, 187 GiB RAM).  `scripts/whitebox_remote_campaign.sh` now takes an
exclusive `campaign.lock`, publishes its active JSONL path in `current_log`,
and resumes every 30 seconds inside tmux.  The prompt has been updated from the
obsolete V55 state to V149/V158 and makes replay/identity/hidden-weight/leader-
count leakage a hard prohibition.  The restart uses a fresh Codex session;
old iteration logs are preserved.

Pre-restart verification passes 273/273 white-box tests, compiles `whitebox/`
and `arena.py`, passes `bash -n` on the watchdog and `git diff --check`, and
finds no production import of opponent modules, trace arrays or decompiler
code.

## 76. Closed deferred-capital action set (V159--V163, 2026-09-02)

### Execution mode and unchanged reference

The persistent campaign was stopped at the user's request.  This iteration ran
only in the foreground of the current task; no tmux/watchdog/background Codex
process was restarted.  V132 remains the evidence-backed reference and V149
remains the strongest directional land arm.  No candidate below is promoted,
submitted or deployed.

### Causal diagnosis of V158

A 24-episode, both-seat, six-seed audit against multi-route reproduced the
arena deltas exactly.  Relative to V149, V158 sold 262 more WHEAT, 45 more
TOMATO and 8 more CARROT, but 35 fewer EGG, 72 fewer FERTILIZER, 25 fewer
STRAWBERRY and 6 fewer WOOL.  The corresponding revenue changes include
`+$12,415` WHEAT and `+$3,645` TOMATO, versus `-$2,161` EGG,
`-$480` FERTILIZER, `-$1,392` STRAWBERRY and `-$3,446` WOOL.  Thus the
candidate-bound hour-1 hire was buying real crop output while displacing a
larger, cross-product continuation.

Seed 37801 exposed the first time inconsistency.  In one seat V158 filled a
current tile with CARROT on day 12; V149 left it empty and bought three SHEEP
the next day.  In the other seat V158 first filled WHEAT on day 15.  The final
paired delta was `-$13,170`.  The missing state value was not an opponent
identity or a preferred herd count: it was the option value of retaining
today's cash and tile for a legal capital action after the next observation.

### Transparent deferred-capital equation

`stackelberg.feasible_deferred_capital` now enumerates every still-legal crop
and animal quantity that can be bought tomorrow from certified cash and empty
tiles.  A route begins the following day and pays asset cost, incremental
Fibonacci hires, nonlinear WHEAT feed, order slots and a closed positioned
route before output receives value.  V161 also exposes a paid all-base-output
endpoint beside the first-output abandonment endpoint.  Certificates record
the selected reinvestment name, worst paid response, own cost and endpoint;
these are audit fields, not policy weights.

V159 added the option but left the historical free future crop rotation in the
same maximum.  It was exactly inert versus V158 on the diagnosed seed
(`logs/arena/v159_vs_v158_diag1_37801.json`): the uncommitted rotation dominated
the new alternative.  V160 removed only that fantasy.  It recovered `+$8,800`
versus V158 on seed 37801, but remained `-$4,370` versus V149.  V161's paid
full durable endpoint was again exactly inert versus V160 on that seed.  These
are implementation tombstones, not neutral economic evidence.

The deeper defect was an early return in `certify_unified`: when the current
capital set was empty it assigned the waiting action value zero before
enumerating deferred capital.  Consequently a current crop trial could use the
new option while its no-purchase baseline could not.  V162 closes that empty
action set.  A regression test proves that the historical path returns zero
while the closed path selects a named `DEFER_DAY_13...` action with positive
value, real cost and explicit worst response.  On seed 37801 V162 gains
`+$5,828` over V161, enough to move about `+$1,458` ahead of V149 in that
single diagnosed cell.

### Bounded productive-service horizon and rejection

V162's passive seed 37120 keeps V149's day-2/day-11 land purchases and
`9 COW + 6 SHEEP + 1 GOOSE`, but adds 16 WHEAT seeds and eight hires and falls
to `$121,826` from `$128,349`.  Its 18-cell hard micro gate is only `+$319`,
firing W-L-T `8-7-3`, and loses V149's one absolute win.  It is not promoted.

The remaining mismatch was explicit: candidate certificates required public
standing animals only to survive, while the standing-output value assumed
their FEED/CARE/HARVEST stream completed.  V163 derives one common finite MPC
horizon from the slowest legal tomorrow-capital first output.  Every action
packs the public standing farm's productive service and cash bridge through
that horizon; the rejected full-season commitment is disabled.  At day 12 the
rule-derived horizon is day 24, and tests prove that standing work is present
through that day and that no full endpoint can escape the bound.

Passive V163 improves on V162 to `$123,945`, with the same land/herd and 228
hires, but remains `$4,404` below V149.  All differences begin on days 25--27:
it buys 3/6/2 extra WHEAT seed and uses hour-1 hires on the first two days.
Two fresh six-seed hard blocks looked directional when combined: 36 cells,
30 firing, W-L-T `18-12-6`, about `+$1,086/cell`, with unchanged absolute win
rates.  This was iteration evidence only.

The required fresh formal gate rejects the arm decisively:
`logs/arena/v163_vs_v149_hard102_38000.json` is `-$2,044/cell`, SE `$719`,
t=`-2.84`, firing 83/102 and W-L-T `24-59-19`.  Every opponent row is negative:

| opponent | delta/cell | firing W-L-T |
|---|---:|---:|
| multi-route | -$2,901 | 6-21-7 |
| frontier | -$1,756 | 9-18-7 |
| v111 | -$1,475 | 9-20-5 |
| **total** | **-$2,044** | **24-59-19** |

Candidate and V149 absolute game/pair wins are both 1.0% on this block, so the
change does not worsen the already-low absolute win count, but its paired
effect is a statistically separated regression.

The multi-route causal audit explains why.  Across the firing seeds the
opponent sold essentially the same units, yet earned `+$12,050` more MILK
revenue.  Our added terminal WHEAT changed our own service/sale path, reduced
our MILK pressure and raised the opponent's realised MILK price.  A feasible
future route is not an executed future route: the next day rebuilds its own
manifest and hire decision.  The next admissible architecture must carry the
winning bounded continuation into the next day's actual crew/task manifest,
or assign a robust displacement value to any standing output it cannot
guarantee.  A date ban, opponent identity, copied herd, fitted penalty or more
micro-gate selection would not repair this execution gap.

Final isolation replay preserves V149 exactly at `$128,349`, land days 2/11,
`9 COW + 6 SHEEP + 1 GOOSE` and 226 hires.  Final verification passes 281/281
white-box tests, `compileall -q whitebox arena.py`, `git diff --check`, and the
production dependency scan for opponent imports, decompiler use and trace
action tables.  No campaign process is running; only the user's unrelated
`claude` and `jupyter` tmux sessions exist.
