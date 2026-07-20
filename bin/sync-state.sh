#!/bin/bash
# bin/sync-state.sh — restore site/ and generator state (data/, weights.json)
# from origin/gh-pages when the published state is ahead of the local one,
# e.g. because the CI backstop published while this machine was asleep.
# The published site carries its own state under /data/ (see publish.sh).
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

git fetch -q origin "+gh-pages:refs/remotes/origin/gh-pages" 2>/dev/null \
  || { echo "sync-state: cannot fetch origin/gh-pages — skipping"; exit 0; }

max_num() { python3 -c '
import json, sys
try:
    issues = json.load(open(sys.argv[1])) if sys.argv[1] != "-" else json.load(sys.stdin)
    print(max((i["num"] for i in issues), default=0))
except Exception:
    print(0)
' "$1"; }

remote_json="$(git show origin/gh-pages:data/issues.json 2>/dev/null || echo '[]')"
remote_max="$(printf '%s' "$remote_json" | max_num -)"
local_max="$(max_num data/issues.json)"

if [ "${remote_max:-0}" -le "${local_max:-0}" ]; then
  echo "sync-state: local state is current (№$local_max >= №$remote_max)"
  exit 0
fi

echo "sync-state: published state is ahead (№$remote_max > №$local_max) — restoring"
tmp="$(mktemp -d)"
git archive origin/gh-pages | tar -x -C "$tmp"

mkdir -p data/snapshots
if [ -d "$tmp/data/snapshots" ]; then cp -R "$tmp/data/snapshots/." data/snapshots/; fi
if [ -f "$tmp/data/issues.json" ]; then cp "$tmp/data/issues.json" data/issues.json; fi
if [ -f "$tmp/data/weights.json" ]; then cp "$tmp/data/weights.json" weights.json; fi
rm -rf "$tmp/data"

rm -rf site
mkdir site
cp -R "$tmp/." site/
rm -rf "$tmp"
echo "sync-state: restored site/ and data/ from origin/gh-pages (№$remote_max)"
