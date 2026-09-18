#!/usr/bin/env bash
# Unattended RL run: train, survive crashes, then evaluate.
#
# The machine has to keep working with nobody watching, so this covers the three
# ways an overnight run silently produces nothing:
#   - it crashes at hour 9 and there is no checkpoint  -> train.py saves 'latest'
#     every 20 iterations and this loop restarts with --resume
#   - it finishes and nobody scores it                 -> evaluate.py runs after
#   - it dies from a transient fault                   -> bounded retry loop
#
# Everything lands in logs/rl/. Read logs/rl/RESULTS.md when it is done.
set -u
cd "$(dirname "$0")/../.." || exit 1
PY=/home/yilewang/kagg-env/bin/python
OUT=logs/rl
mkdir -p "$OUT"

HOURS="${HOURS:-100000}"   # effectively forever; stop with pkill
EPISODES="${EPISODES:-96}"
WORKERS="${WORKERS:-26}"
MAX_RESTARTS="${MAX_RESTARTS:-9999}"

echo "=== unattended run started $(date -Is) ===" | tee -a "$OUT/run.log"
echo "budget ${HOURS}h, ${EPISODES} paired episodes/iter, ${WORKERS} workers" \
    | tee -a "$OUT/run.log"

DEADLINE=$(( $(date +%s) + $(printf '%.0f' "$(echo "$HOURS * 3600" | bc)") ))

for attempt in $(seq 1 "$MAX_RESTARTS"); do
    NOW=$(date +%s)
    LEFT=$(( DEADLINE - NOW ))
    if [ "$LEFT" -le 120 ]; then
        echo "budget exhausted" | tee -a "$OUT/run.log"
        break
    fi
    LEFT_H=$(echo "scale=3; $LEFT / 3600" | bc)
    RESUME=""
    [ "$attempt" -gt 1 ] && RESUME="--resume"
    [ -f "$OUT/latest.pt" ] && RESUME="--resume"
    echo "--- attempt $attempt, ${LEFT_H}h left $RESUME ---" | tee -a "$OUT/run.log"

    "$PY" dynamic/rl/train.py --iters 100000 --episodes "$EPISODES" \
        --workers "$WORKERS" --hours "$LEFT_H" --self_play "${SELF_PLAY:-0.5}" --kl "${KL:-0.003}" \
        --policy "${POLICY:-linear}" --curriculum "${CURRICULUM:-0.7}" \
        --id_logit "${ID_LOGIT:-3.0}" \
        $RESUME >> "$OUT/train.out" 2>&1
    rc=$?
    echo "train.py exited rc=$rc at $(date -Is)" | tee -a "$OUT/run.log"
    # rc 0 means the time budget ran out, which for an indefinite run means the
    # process ended cleanly and should simply come back.
    sleep 20
done

echo "=== evaluating $(date -Is) ===" | tee -a "$OUT/run.log"
CK="$OUT/best.npz"
[ -f "$CK" ] || CK="$OUT/latest.npz"
if [ -f "$CK" ]; then
    "$PY" dynamic/rl/evaluate.py 40 "$WORKERS" "$CK" >> "$OUT/eval.out" 2>&1
    echo "evaluation done, see $OUT/RESULTS.md" | tee -a "$OUT/run.log"
else
    echo "no checkpoint was ever written -- nothing to evaluate" | tee -a "$OUT/run.log"
fi
echo "=== finished $(date -Is) ===" | tee -a "$OUT/run.log"
