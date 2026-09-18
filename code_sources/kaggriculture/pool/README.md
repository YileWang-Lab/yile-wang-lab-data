# Sparring pool — why this is empty

Building a pool by extracting top-ladder players' tapes DOES NOT WORK, and the
attempt is quarantined in `../pool_invalid/`.

`pbt/agreement.py` measures whether an agent replays a fixed schedule by
comparing three of its own games step by step. Measured on the current top of
the ladder:

| team | farmer agreement | hands | market |
|---|---|---|---|
| tetsuya (88% real win rate) | 49.1% | 19.1% | 76.5% |
| カワシギ (rank 1) | 37.4% | 26.1% | 43.4% |
| 我的AI是GPT | 39.9% | 27.7% | 45.1% |
| mandgeee | 65.2% | 33.0% | 52.6% |

For comparison the V16-RC5 notebook reconstructed Nikita Lugovoy's submission at
**99.91%** market agreement -- that one really was a tape. **The current top of
the ladder is adaptive.** One episode is a *trace*, not a policy, and replaying
it blindly produces an agent that only looks right in the game it was copied
from. The quarantined files lost to our submission by up to -106,857, which is
implausible for a 2899-rated opponent winning 77% of its real games; that number
measures the degradation, not their strength.

**Run `pbt/agreement.py` before trusting any extracted opponent.**

What the crawl *is* good for (`pbt/build_pool.py`, cache in `pbt/ladder_cache.json`):
episode metadata carries `team_id`, `submission_id`, `reward` and seat index, so
2,616 real ladder games were mapped without downloading anything. That gives
真实 head-to-head records for the whole top 20 -- a far better strength signal
than any local simulation.
