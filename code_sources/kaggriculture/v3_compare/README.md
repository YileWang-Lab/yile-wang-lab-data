# v3: tape, tree, flat array, fully expanded — side by side

Files that are all **the same agent**, in different representations. One stores
its 720-turn route as ten compressed blobs; one refits it as a perfect-fit CART;
one addresses it as a flat array over an explicit state space; one has every
blob in the file expanded to literal source. Same moves, same money, to the
dollar. Built and verified 2026-08-21.

| file | bytes | what it is |
|---|---|---|
| `v3_tape.py` | 155,305 | the submitted v3, unmodified |
| `v3_tree.py` | 196,410 | `v3_tape.py` + a 41,105 B CART blob |
| `v3_flat.py` | 158,663 | `v3_tape.py` + a 3,358 B flat state array ← **ship this one** |
| `v3_expanded.py` | 1,463,844 | `v3_tape.py` with all 12 blobs as literals, nothing appended |
| `v3_flat_expanded.py` | 1,467,202 | flat array **and** all 12 blobs as literals ← **read/edit this one** |
| `flat_block.py` | 3,358 | the flat block alone — the whole substitution |
| `market_tapes.py` | 53,144 | just the two market tapes, expanded |
| `tree_block.py` / `tree_block_readable.py` | 41,105 / 3,190 | the superseded CART block |

## Nothing is compressed any more

`v3_tape.py` carried **twelve** `json.loads(zlib.decompress(base64.b85decode(…)))`
one-liners. `pbt/expand.py` rewrites all twelve as literal source, one row per
line with its step number, and touches nothing else:

| blob | rows | read by |
|---|---|---|
| `_ACTIONS_{10C4S_3Q, 8C6S_3Q, 6C8S_3Q, 6C12S_4Q_FIRST_YARN, 6C12S_4Q_SECOND_YARN}` | 719 each | the route |
| `_LEGACY_ACTIONS_…` (same five) | 719 each | the route, legacy layout |
| `_V17_R5_MARKETS` | 720 | `_v17_r5_counter` |
| `_V17_MD_MARKETS` | 719 | `_v17_md_counter` |

```python
_ACTIONS_8C6S_3Q = [
    {"farmer": ["BUILD_PASTURE"], "hands": [], "market": [["HIRE"], …]},          #   0
    {"farmer": ["PICKUP", "SHEEP", 1], "hands": [["WEST"], …], "market": […]},    #   1
```

Blobs are located by **AST**, not regex — any module-level assignment whose
value contains a `b85decode`/`b64decode` call, whatever it is named and however
many lines it spans (the route tables are one line each, the market tapes are
three). A name-based match on `_ACTIONS_` would have silently skipped the market
pair, which is the half nobody had ever read. Values come from **executing the
file**, so what is written is what that file produced — not a re-derivation and
not a snapshot from `logs/`.

The two market guards are live, not vestigial: over 20 pool episodes
`_v17_r5_counter` changed the action on **16** turns and `_v17_md_counter` on
**140**, so the gameplay equivalence runs below genuinely exercise both.

### What expansion costs, measured cold

| | compact | expanded |
|---|---|---|
| file | 155 KB | 1.46 MB (×9.4) |
| **cold** import | 0.047 s | **0.387 s** (×8.2) |
| episode wall, real engine | 4.98 s | 5.36 s (**+7.6 %**) |

**Do not quote the warm number.** Measured with a populated `__pycache__` the
expanded file imports **73 % faster**, because the 1.5 MB parse is cached to
`.pyc` while the compact file's zlib+json decode has to run at every import.
That is an artifact — Kaggle writes the submission and imports it, so the parse
is paid. `pbt/expand.py --check` now measures in a fresh temp directory only.

So: **ship `v3_flat.py`** (+0.1 % wall time), **read and edit
`v3_flat_expanded.py`**. Both are equivalent; the expanded one just spends a
third of a second per episode to be legible. Nothing is near a timeout either
way, so this is a preference, not a constraint.

**The flat array supersedes the tree.** Both are pure lookup substitutions and
both verify identical, but the CART was structure for its own sake: 41 KB of
opaque base64, a decode step at first use, and ~13 comparisons to answer a
lookup an array answers in one. Nothing ever depended on its branch structure —
its leaves were already `(table, step)` references. Its only real product was
the *substrate*, and a flat array is a strictly better substrate. The tree is
kept here for comparison, not for use.

## The diff is an append, in both cases

```bash
head -c 155305 v3_flat.py | cmp - v3_tape.py     # silent = identical
head -c 155305 v3_tree.py | cmp - v3_tape.py     # silent = identical
```

Nothing in the original was edited — not the guards, not the market layer, not
the tables. The ten arrays are still there and both layers still read their
actions out of them. That is deliberate: baking a fresh file from `route/bake.py`
would regenerate every layer from today's generators, and v3's market layer came
from an older `pbt/intervene.py` (no `_IV_STRUCT`, `_IV_MIN_PRICE`, `_IV_STAGED`),
so a rebuild would silently swap it. `pbt/flatify.py` copies and appends.

## What changed, in one line

```python
actions = _kawa_actions(obs)          # was: a list.  now: a _FrRoute proxy
```

That is the whole substitution. The eleven guards below it are untouched:

```python
step   = min(max(0, int(_get(obs, "step", 0) or 0)), len(actions) - 1)
action = _weed_repair_action(obs, _copy_action(actions[step]), step)
action = _v17_feed_guard(obs, action, step)
action = _v17_room_evac(obs, action, step)
action = _repay_shift(obs, action, step)
action = _rank_sell_slots(obs, action, None)
action = _preempt_shift(obs, action, step)
action = _v17_r5_counter(obs, action, step)
action = _v17_md_counter(obs, action, step)
action = _v17_room_guard(obs, action, step)
action = _terminal_liquidation(obs, action, step)
return _align_hands(action, obs)
```

`len(actions)` and `actions[step]` are the only operations performed on it, so
an object with `__len__` and `__getitem__` drops straight in.

## The state space, written down

A route decision is a function of exactly three things, and the tape always knew it:

```
legacy in {0, 1}     _kawa_use_legacy_layout(obs)   per-seat latch, stateful
label  in {0..4}     _kawa_route_label(obs)         pure
step   in {0..718}

s1 = (legacy * 5 + label) * 719 + step               |s1| = 7,190
```

**The key space and the reference space are the same space.** `s1` decomposes
as `table * 719 + step`, because the table index *is* `legacy * 5 + label`. So
identity is `_FR_CODES[i] == i`, and there are two edit primitives:

```python
_FR_REMAP[i] = j      # state i plays whatever state j plays   (re-point, 1 int)
_FR_EDITS[i] = act    # state i plays this literal action       (novel action)
```

A re-point is always a legal action and cannot desync the ten arrays. Both
dicts are consulted by all three readers. Empty, the file is v3 exactly.

### Three editing surfaces, now that the blobs are open

| want to | do | in |
|---|---|---|
| change what one state plays, from scratch | edit the row in place: `_ACTIONS_8C6S_3Q[30]` | `v3_flat_expanded.py` |
| make state *i* play state *j*'s action | `_FR_REMAP[i] = j` | either flat build |
| give state *i* a novel action | `_FR_EDITS[i] = act` | either flat build |

The first only became possible with expansion, and it is the one to reach for
when you know *what* you want the agent to do at a step. The other two are for
search, where the point is to generate candidates programmatically —
`RouteArray.patch()` writes them without reformatting the rest of the file.

One asymmetry worth knowing: editing a row in place changes that action for
**every** state that references it, which with the identity array is exactly one
state — but stops being true the moment `_FR_REMAP` points others at it.

The 7,190 identity ints are **not** written out as a literal — that costs 42,028
bytes of source to say nothing, more than the tree blob it replaces. The array
is `list(range(7190))` with sparse deviations applied at import, so it is a
real, mutable, indexable list at runtime while the file carries only the
deltas.

### There is no s2

An opponent axis was considered and deliberately left out. The opponent does not
enter the **route** — it enters the eleven guards, which are already white-box
and already reactive. `(opp, legacy, label, step)` is a one-multiply change to
the layout if it is ever justified, but it multiplies the parameters to fit by
`|s2|` while the pool that scores them stays the same size. Condition on the
opponent in the guards, where it is free, until there is evidence a route-level
split pays.

## Why a proxy and not a lookup function

Three places read the table, and replacing only the obvious one leaves the other
two planning against the route the tape *used to* have:

| site | index | who depends on it |
|---|---|---|
| `agent` | `step` | the base action |
| `_trace_actor_action` | `step` (current) | `_weed_repair_action` replays a deferred op for up to `_WEED_REPLAY_STEPS` = 8 steps |
| `_future_sells` | `step + 1` | `_preempt_shift` borrows tomorrow's premium sells into today and books the amount in `_SHIFT_STATE["due"]` for `_repay_shift` to subtract next turn |

A proxy makes all three resolve through the same array, so an edit is coherent
everywhere *by construction* rather than by remembering to patch three places.

## No numpy in the agent, numpy in the tooling

The lookup runs 3 reads × 720 turns = 2,160 times an episode, where boxed numpy
scalar indexing is *slower* than list indexing — and the base agent's
stdlib-only import set (base64, copy, json, math, zlib) is worth keeping when
the sandbox is someone else's. Vectorisation is a search-time need, not a
runtime one, so it lives in `dynamic/tape/route_array.py`:

```python
from dynamic.tape.route_array import RouteArray
r = RouteArray.load("submission/v3_flat.py")

r.codes                      # int32[7190], identity by default
r.key(0, "8c6s_3q", 30)      # -> 749        r.unkey(749) -> (0, '8c6s_3q', 30)
r.keys(legacy=0, steps=(72, 300))            # vectorised slice of the space
r.action(i) / r.fingerprints() / r.diff(other)
r.measure_reach(); print(r.reach_report())
r.patch("out.py", remap={...}, edits={...})  # textual, rest of file untouched
```

## Reachability is the number that matters

Measured, not assumed — every read instrumented, including the weed replay and
the step+1 peek, over the five-opponent pool × 3 seeds × both seats:

```
reachable 2,205 / 7,190 states (30.7%)
  legacy=0  10c4s_3q     647 states, steps  72..718
  legacy=0  8c6s_3q      719 states, steps   0..718     <- the workhorse
  legacy=1  10c4s_3q     647 states, steps  72..718
  legacy=1  8c6s_3q      192 states, steps  24..215
  never selected: 6c8s_3q, 6c12s_4q_first_yarn, 6c12s_4q_second_yarn (both legacies)
```

**Six of the ten tables are never selected at all** against this pool — 4,985
dead states. Search the mask, not the space, and always report the mask size
with the result: "no improvement in 7,190 states" and "no improvement in 2,205
states" are different claims.

## Evidence

Two drivers, on purpose. `planner.simulate` is ours and is fast enough for a
216-episode sweep; `kaggle_environments` is what actually scores the
competition, so only it can answer "is this submittable".

| check | tool | tree | flat | expanded | flat_expanded |
|---|---|---|---|---|---|
| all route keys | — | 7,190/7,190 | 7,190/7,190 | — | 7,190/7,190 |
| blob values after expansion | `expand.py --check` | — | — | **12/12** | 12/12 |
| pool games, per-seed final banks | `v3_bench.py` | 120/120 | 72/72 | **72/72** | **72/72** |
| self-play `*_vs_base`, paired margin | `v3_bench.py` | +0, 0/16 | +0, 0/12 | **+0, 0/12** | **+0, 0/12** |
| `base_vs_base` (identity control) | `v3_bench.py` | +0, 0/16 | +0, 0/12 | **+0, 0/12** | **+0, 0/12** |
| real engine, by file path | `v3_submit_check.py` | 30/30 | 30/30 | **30/30** | **30/30** |
| episode wall time | `v3_submit_check.py` | +0.3% | **+0.1%** | +7.6% | +7.4% |
| Kaggle entry point | `--check` | `_treeroute_entry` | `_flatroute_entry` | `_submission_entry` | `_flatroute_entry` |

`V3_LAYER=tree|flat|expanded|flat_expanded` selects the build on both harnesses.
Note the entry point differs: expansion alone leaves `_submission_entry` in
place because it appends nothing, so the two transformations are independent and
were verified independently as well as together.

Self-play is scored by **paired margin** — both seat orders per seed, summed —
never win rate. An agent against a byte-identical copy of itself wins seat 0
only 15% of the time, so a win-rate reading of a mirror is noise wearing a
number.

### The check that actually matters

Identical output has an innocent explanation: the appended block could be dead
code, and then every row above is vacuous. So both edit surfaces were sabotaged
on purpose, at a reachable key (`(0, '8c6s_3q', 30)` = state 749), seed 9000 vs
`strong-barnyard-economist`:

```
flat                                   76,829
+ _FR_EDITS[749] = PASS                55,293
+ _FR_REMAP[749] = key(0,'10c4s',0)    77,557
```

Both paths are in the execution path. **A first attempt at the remap test
returned 76,829 — unchanged** — and that was *not* dead code: the remap target
`_ACTIONS_10C4S_3Q[30]` is byte-identical to `_ACTIONS_8C6S_3Q[30]`, so it asked
for nothing. HANDOFF §21: an identical row can mean **inert**, not neutral.
Check which before concluding.

## What this buys, and what it does not

**It is worth exactly zero points.** A perfect substitution scores what the
array scored; shipping it alone adds risk and no reward. What it buys is a
surface — the tape was previously immutable (HANDOFF §4) and no longer is, per
state, at all three read sites.

But §4's *measurement* still stands: edits are mostly catastrophic. A
single-step PASS at steps 0–20 costs between −6k and −299k. Steps beyond 100 are
the untested region and the only place a "soft" state is likely to exist.

Editability is a substrate, not a gain.

## Reproduce

```bash
python pbt/expand.py  submission/v3_base.py     submission/v3_expanded.py --check
python pbt/flatify.py submission/v3_expanded.py submission/v3_flat_expanded.py --check
python dynamic/tape/route_array.py                    # state space + reachability

V3_LAYER=flat_expanded python dynamic/tape/v3_bench.py
V3_LAYER=flat_expanded ~/kagg-env/bin/python dynamic/tape/v3_submit_check.py
```

`v3_submit_check.py` needs `~/kagg-env` — `kaggle_environments` is not in the
default interpreter. It is a **local** check and never contacts Kaggle.

Equivalence is a property of a **build**, not of the generator. Rerun both after
regenerating; never trust a number in a comment.
