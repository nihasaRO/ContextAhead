#!/usr/bin/env bash
# Checks without the Connect IQ SDK. Needs Node 18+ and Python 3 (with tools/sim's dependencies: none beyond the
# standard library). Run from the project folder:  bash tools/check/check.sh
set -euo pipefail
cd "$(dirname "$0")"
[ -d node_modules ] || npm install --silent
node parse.cjs ../../source/*.mc | grep -v '^ok' || true
node lint.cjs ../../source/*.mc
node mc2js.cjs ../../source/Context.mc ../../source/Ic.mc ctx.cjs
python3 ../sim/export_cases.py cases.json
node harness.cjs | tail -2
IMP=1 node harness.cjs | tail -1
node fuzz.cjs | head -1
python3 widths.py
