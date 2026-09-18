# White-box cleanup and V206 screen (2026-09-07)

## Scope

The public first-place notebooks were used only for offline gap analysis. Their
replay/tape/state-router traces are not runtime inputs and are not copied into
the production policy. The white-box contract remains: current observation,
public engine rules, our own legal state, and deterministic optimisation only.

The reusable rule-level ideas retained for investigation are continuous
survival feasibility, shared route/capacity accounting, and terminal inventory
drain. V206 tests the first of these as a hard animal `FEED` core with optional
`CARE/HARVEST/COLLECT_FERTILIZER` suffix work.

## Cleanup

Historical files were moved, not deleted:

- `archive/whitebox_versions/`: superseded white-box candidates;
- `archive/submission_legacy/`: old submission/tape experiments;
- `archive/opponents_offline/`: downloaded notebooks and offline opponent
  inputs.

The still-imported white-box dependencies V59, V76, V86 and V89 were restored
to `whitebox/versions/`. Offline v3 tape tools now point at the archive, while
the active arena pool remains in `opponents/`.

Repeated real-engine match boilerplate is now in [`route/match.py`](../route/match.py)
and is shared by `route/evaluate.py`, `route/batch.py` and
`route/tournament.py`. It always imports a fresh module per episode and reports
both final money values. The stricter paired/common-random-number protocol in
`arena.py` remains the decision entry point for white-box promotion.

## V206 evidence

Screen command:

```text
/home/yilewang/kagg-env/bin/python arena.py \
  whitebox/versions/v206_survival_feed_hard_core.py \
  --baseline whitebox/versions/v204_retained_land_commitment.py \
  --quick --workers 8
```

Results on the 3-opponent hard pool and 6 seeds per opponent:

- 18 paired pool cells, all 18 firing;
- paired pool delta: **-$1,778 per cell**, A>B = 50%;
- candidate self-play against V204: paired margin **-$65,796 total** over 6
  paired seeds, paired win rate 16.7%;
- opponent deltas: kawa -$12,732, frontier -$20,044, v111 +$27,440.

This is a screen, not a promotion sample. The negative self-play result and
non-positive hard-pool aggregate mean V206 stays an unpromoted research arm;
the production wrapper is unchanged. No replay identity, opponent name, fixed
coordinate, or action trace was added to V206.

## Verification

- `372` white-box unit tests pass;
- arena isolation + joint-planner subset: `66` tests pass;
- `compileall` passes for `whitebox`, `route`, `arena.py` and `scripts`;
- shared matcher smoke test passes on a same-agent real-engine episode;
- V204 packaging and generated bundle compilation pass.
