#!/bin/bash
# Ledger scheduled run wrapper (invoked by launchd).
#
#   ledger-run.sh <daily|weekly|monthly> [--no-open]
#
# Generates the issue, logs to data/launchd.log, then opens the site in your
# default browser (unless --no-open). The self-improvement loop is launched in
# the background by generate.py itself.
set -u
CADENCE="${1:-daily}"
OPENFLAG="${2:-}"
REPO="/Users/angelo.dini/Sites/ledger"
PY="/opt/homebrew/bin/python3"
LOG="$REPO/data/launchd.log"

cd "$REPO" || exit 1
mkdir -p "$REPO/data"
echo "===== $(date '+%Y-%m-%d %H:%M:%S')  ledger $CADENCE =====" >> "$LOG"
"$PY" generate.py "$CADENCE" >> "$LOG" 2>&1
rc=$?
echo "exit $rc" >> "$LOG"

if [ "$OPENFLAG" != "--no-open" ] && [ "$rc" -eq 0 ]; then
  /usr/bin/open "$REPO/site/index.html"
fi
exit "$rc"
