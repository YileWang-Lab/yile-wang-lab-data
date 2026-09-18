# White-box V239 public scenario

`whitebox_v239_public_scenario_c06.py` is the current measured candidate.
It reproduces the publicly released C06 scenario-aware policy as readable
Python and uses only the current observation, our own public private inventory,
the visible farms, public market parameters, and engine rules.

## Audit

- imports: `collections.deque`, `math` only;
- no replay/action tape, compression, encoded payload, network access, or
  opponent identity lookup;
- opponent inputs are limited to visible tiles, visible standing animals, and
  public market/town state;
- own feed, seed, animal, shed, and worker decisions are recomputed from the
  current observation.

## Paired benchmark

Using 9 public opponents, seeds `11, 47, 101`, and both seat orders:

| candidate | wins | games | mean money margin |
| --- | ---: | ---: | ---: |
| V228 radial weed pressure | 1 | 54 | -32,902 |
| V239 public scenario C06 | 4 | 54 | -23,702 |

On the separate 30-game three-opponent holdout (`2, 3, 5, 7, 13`):

| candidate | wins | games | mean money margin |
| --- | ---: | ---: | ---: |
| V228 | 0 | 30 | -41,431 |
| V239 | 0 | 30 | -31,589 |

The candidate remains a measured improvement, not a claim of universal
victory.  The V228 modular architecture is retained for future experiments.

## V250 sale-turnover promotion

V250 applies a public market reserve multiplier of `0.60` to V239. This
releases more accumulated output for sale while preserving the terminal
liquidation rule.

| candidate | wins | games | mean money margin |
| --- | ---: | ---: | ---: |
| V239 | 4 | 54 | -23,702 |
| V250 | 4 | 54 | -22,960 |

On the same 30-game holdout, V250 averages `-30,447`, versus V239's
`-31,589`. The V250 bundle is the current submission candidate.
