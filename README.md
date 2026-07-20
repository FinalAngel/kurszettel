<div align="center">

# 📈 Kurszettel

**The quote sheet, reimagined.**
A daily / weekly / monthly reading of the tech market and your portfolio —
what to **buy, keep, and sell** — rendered as a self-contained static site.

[![CI](https://github.com/FinalAngel/kurszettel/actions/workflows/ci.yml/badge.svg)](https://github.com/FinalAngel/kurszettel/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![Dependencies](https://img.shields.io/badge/dependencies-none-success.svg)](#)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

[Live demo](https://finalangel.github.io/kurszettel/) ·
[Features](#features) · [Quickstart](#quickstart) · [How it works](#how-it-works)

</div>

> **Not investment advice.** Kurszettel is a mechanical, rules-based reading of
> public market data for personal information only. Signals can be wrong; do
> your own research; capital is at risk.

Inspired by the archival aesthetic of
[Ephemeris](https://vadim.sikora.name/ephemeris/) and the look of
[zed.dev](https://zed.dev) — built with **standard-library Python only**. No
API keys, no database. One optional dependency: [`curl_cffi`](https://pypi.org/project/curl-cffi/)
for live Yahoo data (Yahoo rejects non-browser TLS fingerprints with HTTP 429
since mid-2026); everything else, including the demo and tests, is stdlib.

## Features

- 📊 **Composite signal** — a transparent 0–100 score per stock from trend
  (SMA 50/200), momentum (RSI/MACD), analyst consensus, and 52-week position →
  `BUY · ACCUMULATE · HOLD · REDUCE · SELL`.
- 💼 **Portfolio-aware** — give it your holdings and it tells you what to
  **keep, sell, or buy**, with P&L, concentration X-ray, per-position risk, and
  a monthly budget plan rounded to whole shares.
- 🌤️ **Market context** — every page opens with a `Risk-on / Neutral / Risk-off`
  read from indices, the VIX, the 10-year yield and sector ETFs.
- 🆕 **IPO radar** — upcoming and just-listed names from Nasdaq's calendar.
- 🧠 **Self-improving** — each run back-tests its own past calls and tunes the
  scoring weights, keeping a change only if it beats the old one *and* the tests
  stay green. Fully reversible.
- 🎛️ **Zero-dep** — stdlib Python; charts are inline SVG. Output is a static
  site you can host anywhere.

## Quickstart

```bash
git clone https://github.com/FinalAngel/kurszettel.git
cd kurszettel
python3 generate.py demo        # offline, synthetic — no network needed
open site_demo/index.html       # macOS (or open it however you like)
```

For real data (Yahoo Finance + Nasdaq, key-less):

```bash
python3 -m venv .venv && .venv/bin/pip install curl_cffi   # once
.venv/bin/python generate.py daily        # or: weekly · monthly
open site/index.html
```

The launchd wrapper (`bin/ledger-run.sh`) picks up `.venv/bin/python`
automatically when it exists.

## How it works

Three readings, each with a different job:

| Command | Reading | Answers |
|---|---|---|
| `generate.py daily`   | **The Tape**       | What's moving today — your holdings, breadth, the ranked book. |
| `generate.py weekly`  | **The Review**     | Your standings + the keep/sell/buy shortlist, to retain. |
| `generate.py monthly` | **The Allocation** | The decision + where this month's budget goes. |

Each run stores a snapshot under `data/`, so weekly and monthly editions
("zettel") synthesise how signals evolve over time.

### Your portfolio

```jsonc
// config.json
"portfolio": {
  "base_currency": "CHF",
  "monthly_budget": 500,
  "holdings": [
    { "symbol": "NVDA", "shares": 20, "avg_cost": 95.0 },
    { "symbol": "ASML.AS", "shares": 3, "avg_cost": 620.0 }
  ]
}
```

`avg_cost` is in the stock's trading currency; FX is fetched and everything is
reported in your `base_currency`. Edit `watchlist`, `benchmarks` and `ipo` in
the same file.

### It tunes itself

On every run, `improve.py` (background, time-boxed) back-tests the scoring
weights against realised forward returns and adopts a better set **only if**
`python3 tests.py` still passes — backing up and rolling back otherwise. Off via
`config.json → self_improve.enabled: false`.

## Run on a schedule

Two schedulers cooperate — `generate.py` skips same-day duplicates, so
whoever runs first wins:

```bash
bash bin/install-launchd.sh      # local primary: daily 09:00 · weekly Mon · monthly 1st
bin/uninstall-launchd.sh         # remove
```

`.github/workflows/zettel.yml` is the **CI backstop**: it runs after the local
window (Mon–Fri 08:35 UTC, plus the 1st for monthlies), restores state from
`gh-pages` (`bin/sync-state.sh`), and builds + publishes only when the local
run was missed. See `bin/SCHEDULING.md` for the full picture.

## Deploy (GitHub Pages)

`bin/publish.sh` force-pushes the built `site/` (plus generator state under
`/data/`) to the `gh-pages` branch, which Pages serves — **Settings → Pages →
Source: Deploy from a branch → `gh-pages`**. After each push it verifies the
Pages build via API and re-requests it if GitHub's build service dropped it.

## Develop

```bash
python3 tests.py                 # fast, network-free test suite (the CI gate)
```

CI (`.github/workflows/ci.yml`) runs the suite on Python 3.9–3.12.

```text
generate.py        CLI: daily | weekly | monthly | demo | build
lib/               sources · indicators · signals · portfolio · trends · render · backtest
improve.py         self-improvement loop      tests.py   the test gate
bin/               launchd install + run wrapper
config.json        watchlist · portfolio · benchmarks · settings
```

## License

[MIT](LICENSE) © 2026 Angelo Dini. Not investment advice — see the disclaimer above.
