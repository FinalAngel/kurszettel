#!/bin/bash
# Remove the Ledger launchd jobs.
set -u
AGENTS="$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"
for suffix in daily weekly monthly; do
  label="ch.devguard.ledger.$suffix"
  launchctl bootout "gui/$UID_NUM/$label" 2>/dev/null || true
  rm -f "$AGENTS/$label.plist"
  echo "removed $label"
done
echo "Done — Ledger will no longer run on schedule."
