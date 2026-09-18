# Reference gap analysis: public-state router

The linked Thomas Tschinkel notebook is useful as an engineering reference,
but its released implementation contains compressed action tables and route
labels that select precomputed traces. That is a replay/tape policy, not an
acceptable runtime dependency for this project.

## What we can keep

| Reference mechanism | White-box translation | Status |
| --- | --- | --- |
| Repair work from current visible state | Re-enumerate legal `DIG`, `WATER`, `FEED`, `CARE`, `HARVEST` task bundles | Active in `whitebox/tasks.py` |
| Route work by public board state | Deterministic prize-collecting multi-worker routing with Manhattan cost | Active in `route/router.py` |
| Protect scarce capacity | Exact shed, cash, order-slot, input-stock and worker-budget certificates | Active in `whitebox/capital.py` and `whitebox/value.py` |
| Clear useful output at the end | State-derived terminal route with exact return/DROP and shared 100-item capacity | Active in V103 |
| Animal survival priority | Mandatory FEED core before optional service suffix | Implemented experimentally in V206, not promoted |

## What is deliberately excluded

- compressed action arrays or six-day replay blocks;
- route labels, episode IDs, team names, opponent names or source-file lookup;
- fixed coordinate/date action schedules;
- hidden opponent inventory treated as a point estimate;
- fitted action frequencies used as runtime weights.

The production entry remains
`whitebox.versions.v103_inserted_terminal_routes`; V206 is a measured,
unpromoted experiment. The new static audit can be run with:

```text
/home/yilewang/kagg-env/bin/python scripts/audit_whitebox_runtime.py \
  --entry whitebox.versions.v103_inserted_terminal_routes \
  --callable whitebox_v103_inserted_terminal_routes
```

It follows the exact modules that `package_whitebox.py` would embed and checks
that the reachable closure has no replay/tape/opponent-file dependency or
filesystem/dynamic-code call. Both V103 and V206 currently pass this audit.
