#!/bin/bash
# bin/publish.sh — publish the freshly built site/ to the gh-pages branch,
# which GitHub Pages serves publicly. Runs natively on macOS (needs network +
# your GitHub SSH key). Invoked by bin/ledger-run.sh after a successful generate.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$REPO/site"
BRANCH="gh-pages"
WT="$REPO/.gh-pages-worktree"

cd "$REPO"
[ -d "$SRC" ] || { echo "publish: $SRC not found — run generate first"; exit 1; }

# Recreate a clean gh-pages worktree from the current commit.
git worktree remove --force "$WT" 2>/dev/null || true
rm -rf "$WT"
git worktree prune
git worktree add --force -B "$BRANCH" "$WT" HEAD >/dev/null

# Swap tracked content for the built site (dotfiles and subdirs included).
cd "$WT"
git rm -rq . >/dev/null 2>&1 || true
( cd "$SRC" && tar cf - . ) | tar xf -
touch .nojekyll

# Ship generator state with the site so any machine (or the CI backstop)
# can pick up where the last publisher left off — see bin/sync-state.sh.
mkdir -p data
cp "$REPO/data/issues.json" data/ 2>/dev/null || true
if [ -d "$REPO/data/snapshots" ]; then cp -R "$REPO/data/snapshots" data/; fi
if [ -f "$REPO/weights.json" ]; then cp "$REPO/weights.json" data/; fi

git add -A
if git diff --cached --quiet; then
  echo "publish: nothing changed"
else
  git -c user.name="kurszettel-bot" -c user.email="noreply@devguard.ch" \
      commit -q -m "publish site $(date -u +%Y-%m-%dT%H:%M:%SZ)"
fi
git push -f origin "$BRANCH"
SHA="$(git rev-parse HEAD)"

cd "$REPO"
git worktree remove --force "$WT" 2>/dev/null || true
echo "publish: pushed $BRANCH -> GitHub Pages"

# The push succeeding does not mean GitHub built the site — the Pages build
# service can fail independently (outages). Verify the build for our commit
# and re-request it if it errors or never shows up.
GH="$(command -v gh || true)"
if [ -x "/opt/homebrew/bin/gh" ]; then GH="/opt/homebrew/bin/gh"; fi
SLUG="$(git remote get-url origin | sed -E 's#(git@github.com:|https://github.com/)##; s#\.git$##')"
if [ -n "$GH" ] && [ -x "$GH" ]; then
  for attempt in 1 2 3; do
    for i in $(seq 1 18); do   # up to ~3 min per attempt
      read -r bcommit bstatus <<< "$("$GH" api "repos/$SLUG/pages/builds/latest" \
          --jq '[.commit, .status] | join(" ")' 2>/dev/null || echo "? ?")"
      if [ "$bcommit" = "$SHA" ] && [ "$bstatus" = "built" ]; then
        echo "publish: Pages build verified ($SHA)"
        exit 0
      fi
      [ "$bcommit" = "$SHA" ] && [ "$bstatus" = "errored" ] && break
      sleep 10
    done
    echo "publish: Pages build missing/errored — re-requesting (attempt $attempt)"
    "$GH" api -X POST "repos/$SLUG/pages/builds" >/dev/null 2>&1 || true
  done
  echo "publish: WARNING — could not verify Pages build for $SHA"
  exit 1
fi
