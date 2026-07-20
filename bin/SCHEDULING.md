# Daily kurszettel → GitHub Pages

Two schedulers cooperate; whoever runs first wins (same-day duplicates are
skipped by `generate.py`):

1. **This Mac (primary):** a launchd job generates the zettel and pushes the
   built site to the `gh-pages` branch, which GitHub Pages serves publicly.
2. **GitHub Actions backstop** (`.github/workflows/zettel.yml`): runs Mon–Fri
   08:35 UTC (plus the 1st for monthlies), restores state from `gh-pages` via
   `bin/sync-state.sh`, and builds + publishes only if the Mac missed its run
   (asleep, offline). Yahoo works from runners via `curl_cffi`'s Chrome TLS
   impersonation — plain HTTP clients get 429 since mid-2026.

State (issue ledger, snapshots, tuned weights) travels with the published site
under `/data/` on `gh-pages`; both schedulers sync from it before generating.
`bin/publish.sh` verifies the Pages build after each push and re-requests it
if GitHub's build service dropped it.

## One-time setup (run in Terminal)

```bash
cd ~/Sites/kurszettel

# 1. First real run: fetch data, build site/, publish to gh-pages (creates the branch)
bash bin/ledger-run.sh daily

# 2. Install the schedule (daily 09:00 Mon–Fri, weekly Mon 09:10, monthly 1st 09:20 — local time)
bash bin/install-launchd.sh

# 3. Commit the setup to main
git add -A
git commit -m "Publish real zettel to gh-pages via launchd; disable demo Pages workflow"
git push
```

Then enable Pages once: **GitHub → repo Settings → Pages → Build and deployment
→ Source: Deploy from a branch → Branch: `gh-pages` / `(root)` → Save.**
Or via CLI: `gh api -X POST repos/FinalAngel/kurszettel/pages -f source[branch]=gh-pages -f source[path]=/`

Site goes live at: https://finalangel.github.io/kurszettel/

## Notes
- Publishes the REAL zettel including your watchlist/portfolio — this is public.
- Logs: `data/launchd.log`. Test the job: `launchctl kickstart -k gui/$(id -u)/ch.devguard.ledger.daily`
- Remove schedule: `bash bin/uninstall-launchd.sh`
- The demo Actions workflow is disabled at `.github/workflows/pages.yml.disabled`.
