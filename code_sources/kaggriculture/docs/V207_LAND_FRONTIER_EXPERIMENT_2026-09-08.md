# V207 land-frontier certificate experiment

V207 is a research-only white-box variant. It repairs the failure mode where a
legal `BUY_LAND` column exists in the current proposal but is discarded by the
ordinary prize-collecting route. The repair is accepted only when the current
public-state route can retain all incumbent ordinary work, select a legal land
anchor, select a productive animal/service column, and strictly improve the
same positioned certificate score.

The runtime uses only the observation, engine economics, legal task columns,
Manhattan routes, cash/order limits, and the existing paired/positioned
certificates. It does not read replay files, episode IDs, opponent names,
dates, fixed coordinates, or recorded action sequences. The top-player replay
audit is kept in `logs/planner/TOP_TASK_GEOMETRY.md` as offline mechanism
evidence only.

## Screening result

The first screen (before the animal-service guard) fired a land-plus-crop ray
around a public state with only about $1.8k cash and lost `-7,180` paired margin
against the hard pool. The guard removed the land-only ray and made the same
diagnostic seed wait for the observed legal animal-plus-land bundle. The second
screen improved to `-4,125` paired margin, with 36.4% paired improvements and
61% firing cells, but it remains negative against the hard pool and is not
promotable. Self-play was positive, which is not sufficient evidence for a
pool improvement.

The result is useful: the reference process's expansion is a bundled capital
decision, not merely an early land purchase. The certificate still needs a
stronger public-state model of the animal/crop mix and market timing before a
future candidate should be considered for production.

## Verification

- `python -m unittest whitebox.test_capital`: 110 passed.
- `python -m unittest discover -s whitebox`: 373 passed.
- `scripts/audit_whitebox_runtime.py` for V207: passed; 22 reachable modules,
  filesystem-free and white-box.
- `arena.py ... --quick --workers 8`: completed with identity controls at zero;
  V207 was retained as research-only and V204 remains the baseline/production
  line.
