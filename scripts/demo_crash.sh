#!/bin/bash
# End-to-end crash demo: fresh run, SIGKILL mid-run, resume in a fresh
# process, verify the final answer. Exits non-zero on any failure.
set -euo pipefail
cd "$(dirname "$0")/.."

LOG=$(mktemp /tmp/crash-demo-XXXXXX.jsonl)
trap 'rm -f "$LOG"' EXIT

echo "=== 1. starting worker (slow mode: 0.3s per step) ==="
python3 -m checkpoint_replay.runner "$LOG" --slow --checkpoint-every 5 &
PID=$!

echo "=== 2. waiting until 6+ steps are durably logged, then kill -9 ==="
while :; do
  N=$(grep -c '"type": "step"' "$LOG" 2>/dev/null || true)
  if [ "${N:-0}" -ge 6 ]; then break; fi
  sleep 0.05
done
echo "    logged $N steps; killing worker pid $PID"
kill -9 $PID
wait $PID 2>/dev/null || true
echo "    worker is dead (SIGKILL)"

echo "=== 3. resuming in a fresh process ==="
python3 -m checkpoint_replay.runner "$LOG" --resume

echo "=== 4. verifying log integrity ==="
python3 -c "
from checkpoint_replay import log as logmod
problems = logmod.fsck('$LOG')
assert not problems, problems
print('fsck clean:', '$LOG')
"
echo "=== demo OK ==="
