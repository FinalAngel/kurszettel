#!/bin/bash
# Kurszettel scheduled run wrapper (invoked by launchd).
#   ledger-run.sh <daily|weekly|monthly> [--no-open]
# Generates the issue, publishes it to GitHub Pages, then opens the site
# locally (unless --no-open). Self-improvement runs in the background.
set -u
CADENCE="${1:-daily}"
OPENFLAG="${2:-}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PY="/opt/homebrew/bin/python3"; [ -x "$PY" ] || PY="$(command -v python3)"
LOG="$REPO/data/launchd.log"

cd "$REPO" || exit 1
mkdir -p "$REPO/data"
echo "===== $(date '+%Y-%m-%d %H:%M:%S')  kurszettel $CADENCE =====" >> "$LOG"
"$PY" generate.py "$CADENCE" >> "$LOG" 2>&1
rc=$?
echo "generate exit $rc" >> "$LOG"

if [ "$rc" -eq 0 ]; then
  if "$REPO/bin/publish.sh" >> "$LOG" 2>&1; then
    echo "publish ok" >> "$LOG"
  else
    echo "publish failed rc=$?" >> "$LOG"
  fi
fi

if [ "$OPENFLAG" != "--no-open" ] && [ "$rc" -eq 0 ]; then
  /usr/bin/open "$REPO/site/index.html"
fi
exit "$rc"
