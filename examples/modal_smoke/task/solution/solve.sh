#!/bin/bash
set -euo pipefail
echo 42 > /app/answer.txt
# The task excludes node_modules from the /app artifact, so the verifier must not see this file.
mkdir -p /app/node_modules && echo junk > /app/node_modules/junk.js
