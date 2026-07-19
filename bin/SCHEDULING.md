# Daily kurszettel → GitHub Pages

The real (live-data) zettel must be generated **on this Mac** — Yahoo Finance
blocks datacenter IPs, so CI / cloud runners can't fetch prices. A launchd job
generates it on a schedule and pushes the built site to the `gh-pages` branch,
which GitHub Pages serves publicly.

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
