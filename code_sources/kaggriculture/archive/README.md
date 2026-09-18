# Archived experiment inputs

This directory contains recoverable historical artifacts moved out of the
runtime search path to keep the active white-box workspace small.

- `whitebox_versions/`: superseded white-box candidates. A version remains
  active only when it is present in `whitebox/versions/` and referenced by a
  current wrapper or test.
- `submission_legacy/`: old submission/tape experiments; none is a production
  entry point.
- `opponents_offline/`: downloaded notebooks, external agents, and other
  replay/audit inputs. They are for offline analysis only and are not legal
  runtime dependencies of the white-box agent.

Nothing here is loaded by the production agent. Restore a file explicitly if
an old diagnostic script needs it; do not add archive paths to runtime policy.
