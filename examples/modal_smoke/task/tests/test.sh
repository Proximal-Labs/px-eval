#!/bin/bash
# Each check writes 1 or 0 into reward.json. The reward is 1 only when all checks pass.
check() { if eval "$2"; then echo "PASS $1"; echo "\"$1\": 1," >> /tmp/checks; else echo "FAIL $1"; echo "\"$1\": 0," >> /tmp/checks; fi; }
: > /tmp/checks
check separate_box '[ -e /verifier-image ] && [ ! -e /agent-image ]'
check answer '[ "$(cat /app/answer.txt 2>/dev/null)" = 42 ]'
check excludes '[ ! -e /app/node_modules/junk.js ]'
check app_writable 'touch /app/.verifier-write'
grep -q " /app " /proc/mounts && echo "INFO /app is a mount (snapshot)" || echo "INFO /app is a plain directory (upload)"
reward=$(grep -q ": 0," /tmp/checks && echo 0 || echo 1)
echo "{ $(cat /tmp/checks) \"reward\": $reward }" > /logs/verifier/reward.json
cat /logs/verifier/reward.json
