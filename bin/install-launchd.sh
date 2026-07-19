#!/bin/bash
# Install macOS launchd jobs so Ledger runs on schedule and opens itself:
#   daily   — 09:00, Mon–Fri
#   weekly  — 09:10, Monday
#   monthly — 09:20, 1st of the month
#
# launchd (unlike cron) runs a missed job when the Mac next wakes, so a closed
# lid at 09:00 won't skip your digest. Re-run this script any time to refresh.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
WRAP="$REPO/bin/ledger-run.sh"
AGENTS="$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"
BASH="/opt/homebrew/bin/bash"
mkdir -p "$AGENTS"
chmod +x "$WRAP"

# $1 label-suffix  $2 cadence  $3 calendar-xml
make_plist() {
  local suffix="$1" cadence="$2" cal="$3"
  local label="ch.devguard.ledger.$suffix"
  local plist="$AGENTS/$label.plist"
  cat > "$plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key>
  <array>
    <string>$BASH</string>
    <string>$WRAP</string>
    <string>$cadence</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string></dict>
  <key>RunAtLoad</key><false/>
  <key>StandardOutPath</key><string>$REPO/data/launchd.$suffix.log</string>
  <key>StandardErrorPath</key><string>$REPO/data/launchd.$suffix.log</string>
  <key>StartCalendarInterval</key>
$cal
</dict>
</plist>
PLIST
  # reload
  launchctl bootout "gui/$UID_NUM/$label" 2>/dev/null || true
  launchctl bootstrap "gui/$UID_NUM" "$plist"
  launchctl enable "gui/$UID_NUM/$label"
  echo "installed $label"
}

# daily — Mon(1)..Fri(5) at 09:00
DAILY='  <array>
    <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer></dict>
  </array>'
# weekly — Monday 09:10
WEEKLY='  <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>10</integer></dict>'
# monthly — 1st 09:20
MONTHLY='  <dict><key>Day</key><integer>1</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>20</integer></dict>'

make_plist "daily"   "daily"   "$DAILY"
make_plist "weekly"  "weekly"  "$WEEKLY"
make_plist "monthly" "monthly" "$MONTHLY"

echo
echo "Done. Schedule (local time):"
echo "  daily   09:00  Mon–Fri"
echo "  weekly  09:10  Monday"
echo "  monthly 09:20  1st of month"
echo
echo "Test one now:   launchctl kickstart -k gui/$UID_NUM/ch.devguard.ledger.daily"
echo "Or directly:    $WRAP daily"
echo "Logs:           $REPO/data/launchd.*.log"
echo "Remove all:     $REPO/bin/uninstall-launchd.sh"
