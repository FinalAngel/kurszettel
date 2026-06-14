# Ledger

A daily reading of the tech market — *what is moving, what is shifting, and
what is worth owning.* Modelled on the clean, archival aesthetic of
[Ephemeris](https://vadim.sikora.name/ephemeris/), but for stocks.

Ledger pulls public market data every morning, scores every name on a
transparent, rules-based system, and renders a minimalist static issue. Issues
are numbered and archived, so you build up a history you can read back.

Three cadences, matching how you asked to use it:

| Command | What it answers |
|---|---|
| `python3 generate.py daily`   | **What's going on today** — movers, breadth, the full ranked book, signal shifts vs. yesterday, fresh headlines. |
| `python3 generate.py weekly`  | **What's going on this week** — conviction gains/drops, weekly leaders & laggards, where the book stands. |
| `python3 generate.py monthly` | **What to invest in** — the *conviction list*, synthesised from the past ~4 weeks of daily readings. |

`python3 generate.py build` just rebuilds `site/index.html` from existing issues.

Every run also kicks off a **self-improvement pass** in the background (see below).

## Run it

No dependencies, no API keys — standard-library Python 3.9+ only.

```bash
python3 generate.py daily
open site/index.html       # macOS; or serve the site/ folder
```

The first run writes one snapshot. Weekly/monthly issues get richer as
snapshots accumulate (they read back `data/snapshots/*.json` to measure how
each name's signal is evolving). Run `daily` every trading day and the weekly
and monthly syntheses become meaningful within a week / month.

## Your portfolio — keep · sell · buy

Ledger is **portfolio-aware**. Tell it what you hold and it marries each position
to the same signal engine, then tells you clearly what to **keep, sell, or buy**.

Set it in `config.json → portfolio`:

```json
"portfolio": {
  "base_currency": "CHF",
  "monthly_budget": 500,
  "holdings": [
    { "symbol": "NVDA", "shares": 20, "avg_cost": 95.0 },
    { "symbol": "ASML.AS", "shares": 3, "avg_cost": 620.0 }
  ]
}
```

`avg_cost` is in the stock's trading currency; Ledger fetches FX and reports
everything in your `base_currency`. Each issue then carries:

- **Where you stand** — every holding with live price, P&L, portfolio weight,
  annualised volatility, max drawdown, and a per-position verdict, plus a
  **concentration X-ray** (effective number of holdings, top weight, currency
  exposure, with a warning if any one name exceeds ~35%).
- **The decision board** — three columns: **Keep**, **Sell / Trim**, **Buy**
  (your held winners worth adding to, marked *add*, plus new ideas from the
  watchlist you don't own yet, marked *new*).
- **The monthly plan** *(monthly only)* — your `monthly_budget` (e.g. CHF 500)
  conviction-weighted across the strongest buy signals and **rounded to whole
  shares your budget can actually buy**, with any uninvested cash carried forward.

The three cadences are deliberately different in job:

- **Daily — "The Tape"**: what's happening. Leads with *your holdings today*
  (what moved in your book), market context, signal shifts, market movers, news.
- **Weekly — "The Review"**: a reminder to retain the picture. Full standings +
  decision board + what changed (conviction shifts, upgrades & downgrades).
- **Monthly — "The Allocation"**: where you act. Standings + decision board +
  the budget plan + the conviction idea-pool.

Ideas adapted from open-source tools (PyPortfolioOpt discrete allocation,
Ghostfolio's concentration X-ray, QuantStats risk metrics, Stockopedia-style
ranking): inverse-volatility and conviction weighting, whole-share rounding,
HHI/effective-N concentration, and annualised vol / max-drawdown per holding.

## Market context & IPO radar

Every issue opens with a **Market context** read before the stock-picking — the
S&P 500, Nasdaq, the VIX ("fear"), the 10-year yield and the tech-sector ETFs
(XLK / SMH / IGV), each with its trend vs. the 200-day line, condensed into a
one-line **Risk-on / Neutral / Risk-off** regime (`lib/trends.py`). It answers
"what's the weather?" before "what do I buy?".

Daily and monthly issues also carry an **IPO radar** — *pricing soon* and *just
listed* names from Nasdaq's public IPO calendar, filtered by deal size and
sorted biggest-first, so upcoming listings are on your radar before they trade.
Configure both in `config.json` (`benchmarks`, `ipo.min_deal_usd`,
`ipo.months_ahead`, `ipo.max_show`). Once a new listing has a few days of price
history you can drop its ticker into `watchlist` to have it scored like any
other name.

## How the score works

Each name gets a **0–100 score** blended from four transparent lenses, and a
verdict band — **BUY ≥72 · ACCUMULATE ≥58 · HOLD ≥45 · REDUCE ≥32 · SELL**:

- **Trend (30%)** — price vs. its 50- & 200-day moving averages; golden/death cross.
- **Momentum (30%)** — RSI(14), MACD histogram, 1-month return.
- **Analyst (25%)** — Wall-Street consensus rating + upside to the mean price target.
- **Position (15%)** — where price sits in its 52-week range (room to run vs. extended).

Every input that drives the score is printed next to each name, so nothing is a
black box. The `trend / momentum / analyst / position` chips under each row are
the per-lens sub-scores (0–100).

## It improves itself on every run

Whenever a command runs in this repo, Ledger launches `improve.py` in the
background and spends a time budget (default **5 minutes**, `config.json →
self_improve.seconds`) trying to get *measurably better* — without ever
delaying your digest and without ever being able to break itself. The full log
is `data/improvements.log`.

It does three things, in order, each strictly gated:

1. **Self-heal.** Runs the test suite. If it's red (a bad hand-edit, a previous
   bad tune), it tries to restore a known-good state before doing anything else.

2. **Tune itself against reality.** Because every daily snapshot stores each
   name's per-lens sub-scores *and* its price, the engine can re-score all of
   history under any candidate set of lens weights and ask: **did the names we
   scored highest actually outperform the ones we scored lowest?** (the average
   top-third-minus-bottom-third forward-return spread — see `lib/backtest.py`).
   It searches thousands of weight combinations to maximise that spread and
   writes the winner to `weights.json` — **but only if** the gain is material
   *and* `python3 tests.py` still passes. Otherwise it reverts. Every adopted
   change is stamped with before/after numbers in `weights.json` and the log.

   This is the engine that makes it "better at each run": with little history it
   reports *insufficient data* and changes nothing; as daily snapshots
   accumulate, the backtest gets stronger and the weights converge toward
   whatever has actually been predictive in **your** universe.

3. **(Optional) LLM code pass.** If you opt in *twice* — `config.json →
   self_improve.llm_code_improve: true` **and** environment `LEDGER_ALLOW_LLM=1`
   — and the `claude` CLI is installed, it lets an agent make one small code
   improvement, **reverted automatically unless the tests stay green**. Off by
   default, because autonomous self-editing on every run carries cost and risk.

**Safety model:** every change is backed up to `data/backups/<timestamp>/`
first and rolled back on any failure; the test suite is the gate for *all*
changes; a lockfile (`data/.improve.lock`) prevents overlapping runs; and an
`LEDGER_NO_IMPROVE=1` recursion guard stops the improver from improving itself.
Tuning only ever touches `weights.json` — your code and signals logic are
untouched unless you enable the optional LLM pass. Disable the whole thing with
`self_improve.enabled: false`, or per-invocation with `LEDGER_NO_IMPROVE=1`.

There's also a wrapper so *any* command triggers it, not just `generate.py`:

```bash
./ledger daily              # generate, then self-improve
./ledger python3 tests.py   # run anything; still self-improves afterward
./ledger                    # just run a self-improvement pass now
```

## Data sources

All key-less and free:

- **Yahoo Finance** — prices, 1-year history, analyst consensus & price targets,
  plus the benchmark indices / VIX / yield / sector ETFs for market context.
- **Yahoo headline RSS** — recent company news for the day's biggest movers
  (aggregating Reuters / CNBC / MarketWatch and others).
- **Nasdaq IPO calendar** — upcoming and recently-priced IPOs (key-less).

To add a premium provider later (Finnhub, Financial Modeling Prep, Alpha
Vantage…), add a fetch method in `lib/sources.py` and merge its fields into the
record built in `generate.py`. The scoring layer is provider-agnostic.

## Configure

Edit `config.json`:

- `watchlist` — the tickers (use Yahoo symbols, e.g. `ASML.AS`, `LOGN.SW`).
  Tech-focused US + Europe + Switzerland by default.
- `title`, `tagline`, `schedule_note`, `sources`, `base_currency`.

## Automate (recommended: local launchd on your Mac)

Run it locally — not in CI. Yahoo rate-limits datacenter IPs hard (GitHub
Actions / cloud agents get banned), your home IP is the reliable data path, and
your holdings stay private. One command installs scheduled jobs that generate
each issue and open it in your browser:

```bash
bash bin/install-launchd.sh      # installs the three jobs
bin/uninstall-launchd.sh         # remove them
```

Schedule (local time): **daily 09:00 Mon–Fri · weekly Monday 09:10 · monthly 1st
09:20**. Unlike cron, launchd runs a missed job when the Mac next wakes, so a
closed lid at 09:00 won't skip your digest. Edit the times in
`bin/install-launchd.sh` and re-run. Test one immediately:

```bash
launchctl kickstart -k gui/$(id -u)/ch.devguard.ledger.daily   # or:
bin/ledger-run.sh daily          # run + open now
```

Logs land in `data/launchd.*.log`. To read it on your phone too, have the job
push only the rendered `site/` to a (private) GitHub Pages repo — keep
`config.json`/holdings out of it. (A plain `crontab` works as well, but launchd
handles sleep/wake and is the macOS-native choice.)

## Layout

```
config.json            watchlist + settings (incl. self_improve)
ledger                 wrapper: run any command, then self-improve
generate.py            CLI: daily | weekly | monthly | build
improve.py             self-improvement loop (tune + self-heal + optional LLM)
tests.py               the gate — every self-change must keep this green
lib/sources.py         Yahoo data access (stdlib only)
lib/indicators.py      SMA, RSI, MACD, returns, 52w position
lib/signals.py         composite score -> verdict (+ tunable weights.json)
lib/portfolio.py       holdings analysis, keep/sell/buy, allocation, X-ray
lib/trends.py          market-context regime + IPO filtering
lib/demosource.py      offline synthetic data for `generate.py demo`
lib/backtest.py        scores-vs-realised-returns objective for tuning
lib/render.py          HTML rendering (Fraunces + Inter)
assets/style.css       the look
weights.json           tuned parameters (written by improve.py; absent = defaults)
data/snapshots/        one JSON per daily run (history the backtest reads)
data/improvements.log  what the self-improvement loop did, each run
data/backups/          pre-change backups for rollback
data/issues.json       the archive index
site/                  the published static site (open index.html)
```

## Important — not advice

Ledger is a **mechanical, rules-based reading of public data for personal
information only**. It is **not investment advice**, not a recommendation, and
not a solicitation to buy or sell any security. Signals can be wrong and past
behaviour does not predict returns. Do your own research and consider your own
situation — **capital is at risk.**
