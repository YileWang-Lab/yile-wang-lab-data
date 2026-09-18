# White-box V292 public weed-priority candidate

V292 keeps the audited V250 public-state C06 policy and changes only the
priority of visible weed jobs.  Every `dig_weed` job is promoted to priority
3 with a minimum rule-derived value of 180 once it is generated.  The route
planner still checks the current board, worker positions, inventory, shed
capacity, and action horizon before emitting `DIG`; there is no replay,
opponent identity, encoded schedule, or private opponent state.

## Paired measurements

The candidate was evaluated with the repository's public opponent pool, both
seat orders, and seeds `11, 47, 101` (54 games):

| candidate | wins | mean money margin |
| --- | ---: | ---: |
| V250 sale60 | 4/54 | -22,960 |
| V292 weed priority 3 | 3/54 | -22,018 |

On the fixed three-opponent holdout (seeds `2, 3, 5, 7, 13`, both seats,
30 games):

| candidate | wins | mean money margin |
| --- | ---: | ---: |
| V250 sale60 | 0/30 | -30,447 |
| V292 weed priority 3 | 0/30 | -30,387 |

An additional 54-game check on seeds `17, 19, 23` improved from `-24,008`
(V250) to `-23,573` (V292).  These are measurements, not a guarantee of
universal wins.

## Runtime audit

The reachable bundle contains only `whitebox`, `whitebox.versions`, the
public C06 implementation, and this V292 wrapper.  The static runtime audit
passes with no forbidden imports or filesystem/dynamic calls; the 424 targeted
white-box tests also pass.

