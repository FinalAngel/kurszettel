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

git add -A
if git diff --cached --quiet; then
  echo "publish: nothing changed"
else
  git -c user.name="kurszettel-bot" -c user.email="noreply@devguard.ch" \
      commit -q -m "publish site $(date -u +%Y-%m-%dT%H:%M:%SZ)"
fi
git push -f origin "$BRANCH"

cd "$REPO"
git worktree remove --force "$WT" 2>/dev/null || true
echo "publish: pushed $BRANCH -> GitHub Pages"
