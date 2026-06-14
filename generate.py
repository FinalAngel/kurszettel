#!/usr/bin/env python3
"""
Ledger — generate a daily / weekly / monthly issue of the tech-market reading.

    python3 generate.py daily      # what's going on today  + ranked book
    python3 generate.py weekly     # the week in conviction
    python3 generate.py monthly    # the conviction list — what to invest in
    python3 generate.py build      # just rebuild the index from existing issues

Each daily run also stores a snapshot under data/snapshots/, which the weekly
and monthly issues read back to measure how signals are evolving over time.
"""

import os
import sys
import json
import glob
import shutil
import datetime
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.sources import Yahoo
from lib import indicators, signals, render, trends

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Zurich")
except Exception:
    TZ = None

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
SNAP = os.path.join(DATA, "snapshots")
SITE = os.path.join(ROOT, "site")
ISSUES_DIR = os.path.join(SITE, "zettel")
ISSUES_JSON = os.path.join(DATA, "issues.json")

BUYISH = ("BUY", "ACCUMULATE")

# data source + output paths are swapped out for `demo` mode
DEMO = False
SOURCE_FACTORY = Yahoo


def make_source():
    return SOURCE_FACTORY()


def use_demo_paths():
    """Point output + snapshots at *_demo locations so a demo run never
    touches the real archive or the back-test history."""
    global DEMO, SITE, ISSUES_DIR, ISSUES_JSON, SNAP
    DEMO = True
    SITE = os.path.join(ROOT, "site_demo")
    ISSUES_DIR = os.path.join(SITE, "zettel")
    ISSUES_JSON = os.path.join(DATA, "demo_issues.json")
    SNAP = os.path.join(DATA, "demo_snapshots")


# ---- helpers ---------------------------------------------------------

def now():
    return datetime.datetime.now(TZ) if TZ else datetime.datetime.now()


def load_config():
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def ensure_dirs():
    for d in (DATA, SNAP, SITE, ISSUES_DIR, os.path.join(SITE, "assets")):
        os.makedirs(d, exist_ok=True)
    shutil.copyfile(os.path.join(ROOT, "assets", "style.css"),
                    os.path.join(SITE, "assets", "style.css"))


def load_issues():
    if os.path.exists(ISSUES_JSON):
        with open(ISSUES_JSON, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_issues(issues):
    with open(ISSUES_JSON, "w", encoding="utf-8") as f:
        json.dump(issues, f, indent=2)


def pct(n, total):
    return (100.0 * n / total) if total else 0.0


def downsample(values, target=36):
    """Evenly thin a series down to ~target points for a sparkline."""
    vals = [v for v in values if v is not None]
    if len(vals) <= target:
        return [round(v, 4) for v in vals]
    step = (len(vals) - 1) / (target - 1)
    return [round(vals[round(i * step)], 4) for i in range(target)]


# ---- snapshot --------------------------------------------------------

def score_symbol(y, symbol, name=None, region="—"):
    """Fetch + score a single symbol. Returns a rec dict or None."""
    hist = y.history(symbol, rng="1y", interval="1d")
    if not hist or len(hist["closes"]) < 30:
        return None
    m = indicators.metrics(hist["closes"])
    a = y.analyst(symbol)
    sc, breakdown = signals.score(m, a)
    upside = None
    if a.get("target_mean") and m["price"]:
        upside = (a["target_mean"] / m["price"] - 1.0) * 100.0
    return {
        "symbol": symbol,
        "name": name or symbol,
        "region": region,
        "currency": hist.get("currency"),
        "price": round(m["price"], 2) if m["price"] else None,
        "ret_1d": m["ret_1d"], "ret_1w": m["ret_1w"],
        "ret_1m": m["ret_1m"], "ret_3m": m["ret_3m"],
        "rsi": m["rsi"], "range_pos": m["range_pos"],
        "volatility": m["volatility"], "max_drawdown": m["max_drawdown"],
        "score": sc, "verdict": signals.verdict(sc),
        "breakdown": breakdown,
        "rationale": signals.rationale(m, a, breakdown),
        "rec_key": a.get("rec_key"), "target_mean": a.get("target_mean"),
        "n_analysts": a.get("n_analysts"), "upside": upside,
        "spark": downsample(hist["closes"][-90:], 36),
    }


def build_snapshot(cfg, y=None, quiet=False):
    """Fetch + compute every watchlist name. Returns (recs, news)."""
    y = y or make_source()
    recs = []
    wl = cfg["watchlist"]
    for i, item in enumerate(wl, 1):
        if not quiet:
            sys.stderr.write(f"  [{i:>2}/{len(wl)}] {item['symbol']:<10}\r")
            sys.stderr.flush()
        rec = score_symbol(y, item["symbol"], item["name"], item["region"])
        if rec:
            recs.append(rec)
    sys.stderr.write("\n")

    # news only for the day's biggest absolute movers — keeps requests modest
    news = []
    movers = sorted([r for r in recs if r.get("ret_1d") is not None],
                    key=lambda r: abs(r["ret_1d"]), reverse=True)[:6]
    for r in movers:
        for it in y.news(r["symbol"], limit=2):
            it["ticker"] = r["symbol"]
            news.append(it)
    return recs, news


def save_snapshot(date_iso, recs):
    path = os.path.join(SNAP, f"{date_iso}.json")
    keep = ("symbol", "name", "region", "score", "verdict", "ret_1d",
            "ret_1w", "ret_1m", "price", "currency", "upside", "breakdown")
    slim = [{k: r.get(k) for k in keep} for r in recs]
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"date": date_iso, "recs": slim}, f, indent=2)


def fetch_market_context(cfg, y):
    """Benchmark indices / VIX / yield / sector ETFs with trend metrics."""
    out = []
    for b in cfg.get("benchmarks", []):
        h = y.history(b["symbol"], rng="1y", interval="1d")
        if not h or len(h["closes"]) < 30:
            continue
        m = indicators.metrics(h["closes"])
        out.append({
            "symbol": b["symbol"], "name": b["name"], "kind": b.get("kind"),
            "price": round(m["price"], 2) if m["price"] else None,
            "ret_1d": m["ret_1d"], "ret_1m": m["ret_1m"],
            "sma200": m["sma200"], "range_pos": m["range_pos"],
            "spark": downsample(h["closes"][-90:], 36),
        })
    return out


def _month_strings(dt, ahead):
    months, cur = [dt.strftime("%Y-%m")], dt
    for _ in range(max(0, ahead)):
        ny = cur.year + (1 if cur.month == 12 else 0)
        nm = 1 if cur.month == 12 else cur.month + 1
        cur = cur.replace(year=ny, month=nm, day=1)
        months.append(cur.strftime("%Y-%m"))
    return months


def fetch_ipos(cfg, y, dt):
    icfg = cfg.get("ipo", {}) or {}
    raw = y.ipo_calendar(_month_strings(dt, int(icfg.get("months_ahead", 1))))
    return trends.filter_ipos(raw, icfg.get("min_deal_usd", 0),
                              int(icfg.get("max_show", 12)))


def add_portfolio_sections(cfg, y, recs, ctx, *, with_alloc=False):
    """Score holdings, build the keep/sell/buy decision + (monthly) the plan."""
    from lib import portfolio
    pcfg = cfg.get("portfolio", {}) or {}
    holdings = pcfg.get("holdings", []) or []
    base = pcfg.get("base_currency", cfg.get("base_currency", "USD"))
    budget = pcfg.get("monthly_budget", 0)
    ctx["base_ccy"], ctx["budget"] = base, budget
    if not holdings:
        return ctx

    rec_by = {r["symbol"]: r for r in recs}
    for h in holdings:               # score any holding not in the watchlist
        if h["symbol"] not in rec_by:
            r = score_symbol(y, h["symbol"])
            if r:
                rec_by[h["symbol"]] = r

    ccys = {r["currency"] for r in rec_by.values() if r.get("currency")}
    fx_to_base = {base: 1.0}
    for c in ccys:
        fx_to_base[c] = y.fx(c, base) or 1.0

    rows, totals = portfolio.analyze(holdings, rec_by, fx_to_base, base)
    held = {h["symbol"] for h in holdings}
    new_ideas = portfolio.buy_candidates(recs, held, limit=8)
    add_rows = [r for r in rows if r["bucket"] == "BUY"]

    buy_rows = ([{"name": r["name"], "symbol": r["symbol"], "score": r["score"],
                  "upside": r.get("upside"), "is_new": False} for r in add_rows]
                + [{"name": r["name"], "symbol": r["symbol"], "score": r["score"],
                    "upside": r.get("upside"), "is_new": True} for r in new_ideas])
    buy_rows.sort(key=lambda r: r["score"], reverse=True)

    ctx["portfolio_rows"] = rows
    ctx["portfolio_totals"] = totals
    ctx["keep_rows"] = [r for r in rows if r["bucket"] == "KEEP"]
    ctx["sell_rows"] = [r for r in rows if r["bucket"] == "SELL"]
    ctx["buy_rows"] = buy_rows

    if with_alloc:
        cands = []
        for r in add_rows:
            rec = dict(rec_by[r["symbol"]], _held=True)
            cands.append(rec)
        for r in new_ideas:
            cands.append(dict(r, _held=False))
        cands.sort(key=lambda r: r["score"], reverse=True)
        ctx["alloc_plan"], ctx["alloc_leftover"] = portfolio.allocation_plan(
            cands, budget, fx_to_base, base, max_positions=5)
    return ctx


def add_market_sections(cfg, y, dt, ctx):
    """Attach market-context + IPO data to an issue context dict."""
    context = fetch_market_context(cfg, y)
    up, pr = fetch_ipos(cfg, y, dt)
    ctx["benchmarks"] = context
    ctx["regime"] = trends.regime(context) if context else ("", "")
    ctx["ipos_up"], ctx["ipos_priced"] = up, pr
    return ctx


def _series_maps(snaps):
    """Per-symbol score series + verdict series across snapshots (oldest first)."""
    ssm, vmap = {}, {}
    for s in snaps:
        for r in s["recs"]:
            if r.get("score") is not None:
                ssm.setdefault(r["symbol"], []).append(r["score"])
            if r.get("verdict"):
                vmap.setdefault(r["symbol"], []).append(r["verdict"])
    return ssm, vmap


def load_snapshots(days):
    """Load up to `days` most recent snapshots, oldest first."""
    files = sorted(glob.glob(os.path.join(SNAP, "*.json")))
    out = []
    for p in files[-days:]:
        try:
            with open(p, encoding="utf-8") as f:
                out.append(json.load(f))
        except Exception:
            pass
    return out


# ---- issue assembly --------------------------------------------------

def issue_meta(cfg, issues, kind, dt):
    type_label = {"daily": "Daily", "weekly": "Weekly", "monthly": "Monthly"}[kind]
    num = (max((it["num"] for it in issues), default=0)) + 1
    return {
        "num": num,
        "kind": kind,
        "type_label": type_label,
        "date_long": dt.strftime("%A, %-d %B %Y"),
        "date_short": dt.strftime("%Y-%m-%d"),
        "universe_note": (f"{len(cfg['watchlist'])} tech names · US · Europe · CH"
                          + (" · DEMO (synthetic prices)" if DEMO else "")),
    }


def commit_issue(cfg, issues, meta, inner, title, headline):
    meta["title"] = title
    meta["headline"] = headline
    fname = f"{meta['num']:03d}.html"
    html = render.page(cfg, meta, inner, asset_prefix="../")
    with open(os.path.join(ISSUES_DIR, fname), "w", encoding="utf-8") as f:
        f.write(html)
    issues.append({
        "num": meta["num"],
        "type": meta["type_label"],
        "title": title,
        "date": meta["date_short"],
        "path": f"zettel/{fname}",
    })
    save_issues(issues)
    rebuild_index(cfg, issues)
    return fname


def latest_ticker(limit=22):
    """Quotes for the landing-page ticker tape, from the most recent snapshot."""
    snaps = load_snapshots(1)
    if not snaps:
        return []
    out = [{"symbol": r["symbol"], "price": r.get("price"),
            "ret_1d": r.get("ret_1d"), "currency": r.get("currency"),
            "verdict": r.get("verdict")}
           for r in snaps[-1]["recs"] if r.get("price") is not None]
    out.sort(key=lambda o: abs(o.get("ret_1d") or 0), reverse=True)
    return out[:limit]


def rebuild_index(cfg, issues):
    ordered = sorted(issues, key=lambda it: it["num"], reverse=True)
    inner = render.index_inner(cfg, ordered, ticker=latest_ticker())
    html = render.page(cfg, {}, inner, asset_prefix="", is_index=True)
    with open(os.path.join(SITE, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)


# ---- daily -----------------------------------------------------------

def gen_daily(cfg, issues, dt):
    y = make_source()
    recs, news = build_snapshot(cfg, y)
    if not recs:
        sys.exit("No data fetched — aborting.")
    save_snapshot(dt.strftime("%Y-%m-%d"), recs)

    ranked = sorted(recs, key=lambda r: r["score"], reverse=True)
    movers = [r for r in recs if r.get("ret_1d") is not None]
    gainers = sorted(movers, key=lambda r: r["ret_1d"], reverse=True)[:5]
    losers = sorted(movers, key=lambda r: r["ret_1d"])[:5]

    adv = sum(1 for r in movers if r["ret_1d"] > 0)
    dec = sum(1 for r in movers if r["ret_1d"] < 0)
    buys = [r for r in recs if r["verdict"] in BUYISH]
    n = len(recs)

    # signal shifts vs the previous snapshot (before today's)
    shifts = []
    prev = load_snapshots(2)
    if len(prev) >= 2:
        prev_map = {r["symbol"]: r["verdict"] for r in prev[-2]["recs"]}
        for r in ranked:
            old = prev_map.get(r["symbol"])
            if old and old != r["verdict"]:
                shifts.append({"symbol": r["symbol"], "name": r["name"],
                               "from": old, "to": r["verdict"]})

    top_names = ", ".join(r["name"] for r in ranked[:3] if r["verdict"] in BUYISH)
    lede = (f"{adv} of {n} names advanced today; {dec} fell. "
            f"{len(buys)} screen as buys"
            + (f", led by {top_names}. " if top_names else ". ")
            + f"The book's average reading is "
            f"{sum(r['score'] for r in recs)/n:.0f}/100.")

    strip = [
        ("Advancing", f'<span class="num up">{adv}</span>'),
        ("Declining", f'<span class="num down">{dec}</span>'),
        ("Buy-rated", f'<span class="num">{len(buys)}/{n}</span>'),
        ("Avg score", f'<span class="num">{sum(r["score"] for r in recs)/n:.0f}</span>'),
    ]

    ctx = {"lede": lede, "strip": strip, "ranked": ranked,
           "gainers": gainers, "losers": losers, "shifts": shifts, "news": news}
    add_market_sections(cfg, y, dt, ctx)
    add_portfolio_sections(cfg, y, recs, ctx)
    t = ctx.get("portfolio_totals") or {}
    if t.get("value"):
        strip.append(("Your book", f'<span class="num">{t["base"]} '
                      f'{t["value"]:,.0f}</span>'))
        strip.append(("Book today", render._pct(t.get("day_pct"), 2)))
    meta = issue_meta(cfg, issues, "daily", dt)
    meta["title"] = f"The tape — {dt.strftime('%-d %b %Y')}"
    meta["headline"] = (f"{len(buys)} buys across {n} tech names; breadth "
                        f"{adv}↑ / {dec}↓.")
    inner = render.daily_inner(cfg, meta, ctx)
    return commit_issue(cfg, issues, meta, inner, meta["title"], meta["headline"])


# ---- weekly ----------------------------------------------------------

def gen_weekly(cfg, issues, dt):
    y = make_source()
    recs, news = build_snapshot(cfg, y)
    if not recs:
        sys.exit("No data fetched — aborting.")
    save_snapshot(dt.strftime("%Y-%m-%d"), recs)

    snaps = load_snapshots(8)
    base = snaps[0] if len(snaps) >= 2 else None
    base_map = {r["symbol"]: r["score"] for r in base["recs"]} if base else {}
    ssm, vmap = _series_maps(snaps)
    for r in recs:
        r["score_delta"] = round(r["score"] - base_map.get(r["symbol"], r["score"]))
        r["score_series"] = downsample(ssm.get(r["symbol"]) or [], 24)

    # verdict upgrades / downgrades across the week
    rank_ord = {"SELL": 0, "REDUCE": 1, "HOLD": 2, "ACCUMULATE": 3, "BUY": 4}
    upgrades, downgrades = [], []
    for r in recs:
        vs = vmap.get(r["symbol"]) or []
        if len(vs) >= 2 and vs[0] != vs[-1]:
            item = {"name": r["name"], "symbol": r["symbol"],
                    "from": vs[0], "to": vs[-1]}
            (upgrades if rank_ord.get(vs[-1], 2) > rank_ord.get(vs[0], 2)
             else downgrades).append(item)

    ranked = sorted(recs, key=lambda r: r["score"], reverse=True)[:15]
    climbers = sorted(recs, key=lambda r: r["score_delta"], reverse=True)[:5]
    faders = sorted(recs, key=lambda r: r["score_delta"])[:5]
    wk = [r for r in recs if r.get("ret_1w") is not None]
    week_up = sorted(wk, key=lambda r: r["ret_1w"], reverse=True)[:5]
    week_down = sorted(wk, key=lambda r: r["ret_1w"])[:5]

    n = len(recs)
    buys = sum(1 for r in recs if r["verdict"] in BUYISH)
    avg_wk = sum(r["ret_1w"] for r in wk) / len(wk) if wk else 0.0
    lede = (f"Over the past week the book averaged {avg_wk:+.1f}%. "
            f"{buys} of {n} names now screen as buys. "
            + (f"Conviction rose most in {climbers[0]['name']}."
               if base and climbers and climbers[0]['score_delta'] > 0
               else "Signals were broadly stable."))
    strip = [
        ("Avg 1-wk", render._pct(avg_wk, 1)),
        ("Buy-rated", f'<span class="num">{buys}/{n}</span>'),
        ("Readings", f'<span class="num">{len(snaps)}</span>'),
    ]
    ctx = {"lede": lede, "strip": strip, "ranked": ranked,
           "climbers": climbers, "faders": faders,
           "week_up": week_up, "week_down": week_down,
           "upgrades": upgrades, "downgrades": downgrades}
    add_market_sections(cfg, y, dt, ctx)
    add_portfolio_sections(cfg, y, recs, ctx)
    meta = issue_meta(cfg, issues, "weekly", dt)
    meta["title"] = f"The week in conviction — {dt.strftime('%-d %b %Y')}"
    meta["headline"] = f"Book {avg_wk:+.1f}% on the week; {buys}/{n} rated buy."
    inner = render.weekly_inner(cfg, meta, ctx)
    return commit_issue(cfg, issues, meta, inner, meta["title"], meta["headline"])


# ---- monthly ---------------------------------------------------------

def gen_monthly(cfg, issues, dt):
    y = make_source()
    recs, news = build_snapshot(cfg, y)
    if not recs:
        sys.exit("No data fetched — aborting.")
    save_snapshot(dt.strftime("%Y-%m-%d"), recs)

    snaps = load_snapshots(28)
    cur = {r["symbol"]: r for r in recs}

    # gather each symbol's score history across the window
    hist = {}
    for s in snaps:
        for r in s["recs"]:
            hist.setdefault(r["symbol"], []).append(r)

    rows = []
    for sym, series in hist.items():
        scores = [x["score"] for x in series]
        if not scores or sym not in cur:
            continue
        avg = sum(scores) / len(scores)
        buy_share = pct(sum(1 for x in series if x["verdict"] in BUYISH), len(series))
        trend = scores[-1] - scores[0] if len(scores) > 1 else 0.0
        conviction = avg * 0.6 + buy_share * 0.25 + max(min(trend, 20), -20) * 0.6
        c = cur[sym]
        rows.append({
            "symbol": sym, "name": c["name"], "region": c["region"],
            "price": c["price"], "currency": c.get("currency"),
            "ret_1m": c.get("ret_1m"), "verdict": c["verdict"],
            "avg_score": avg, "buy_share": buy_share, "trend": round(trend),
            "trend_disp": f"{trend:+.0f} pts", "days": len(series),
            "conviction": conviction,
            "score_series": downsample(scores, 30),
            "note": _conviction_note(c, avg, buy_share, trend),
        })

    rows.sort(key=lambda r: r["conviction"], reverse=True)
    conviction = rows[:12]
    # a suggested model weighting from relative conviction (sums to 100%)
    tot = sum(max(0.0, r["conviction"]) for r in conviction) or 1.0
    for r in conviction:
        r["weight"] = max(0.0, r["conviction"]) / tot * 100.0
    improving = sorted(rows, key=lambda r: r["trend"], reverse=True)[:5]
    fading = sorted(rows, key=lambda r: r["trend"])[:5]

    n_days = len(snaps)
    window_note = (f"{n_days} reading{'s' if n_days != 1 else ''} over the "
                   f"trailing ~4 weeks")
    top = conviction[0]["name"] if conviction else "—"
    lede = (f"Synthesising the past 4 weeks of daily readings, the strongest, "
            f"most persistent signal sits with {top}. "
            f"The conviction list below ranks names by strength, consistency "
            f"and improvement of their signal.")
    buys_now = sum(1 for r in recs if r["verdict"] in BUYISH)
    strip = [
        ("Conviction names", f'<span class="num">{len(conviction)}</span>'),
        ("Buy-rated now", f'<span class="num">{buys_now}/{len(recs)}</span>'),
        ("Window", f'<span class="num">{n_days}d</span>'),
    ]
    ctx = {"lede": lede, "strip": strip, "conviction": conviction,
           "improving": improving, "fading": fading, "window_note": window_note}
    add_market_sections(cfg, y, dt, ctx)
    add_portfolio_sections(cfg, y, recs, ctx, with_alloc=True)
    meta = issue_meta(cfg, issues, "monthly", dt)
    meta["title"] = f"The conviction list — {dt.strftime('%B %Y')}"
    meta["headline"] = f"What to invest in: top {len(conviction)} tech names by 4-week conviction."
    inner = render.monthly_inner(cfg, meta, ctx)
    return commit_issue(cfg, issues, meta, inner, meta["title"], meta["headline"])


def _conviction_note(c, avg, buy_share, trend):
    bits = []
    if c.get("upside") is not None:
        bits.append(f"{c['upside']:+.0f}% to analyst target")
    if trend > 3:
        bits.append("signal strengthening")
    elif trend < -3:
        bits.append("signal cooling")
    else:
        bits.append("signal steady")
    if c.get("ret_3m") is not None:
        pass
    bits.append(c["rationale"] if c.get("rationale") else "")
    return "; ".join(b for b in bits if b)


# ---- main ------------------------------------------------------------

def launch_self_improvement(cfg):
    """Spend >=5 min (background, non-blocking) trying to improve the repo.
    Fires on every run unless disabled in config or LEDGER_NO_IMPROVE=1 is set
    (the latter is how the improver stops itself from recursing)."""
    if os.environ.get("LEDGER_NO_IMPROVE") == "1":
        return
    si = cfg.get("self_improve", {}) or {}
    if not si.get("enabled", True):
        return
    secs = int(si.get("seconds", 300))
    logf = open(os.path.join(DATA, "improve.run.log"), "a")
    try:
        subprocess.Popen(
            [sys.executable, os.path.join(ROOT, "improve.py"), "--seconds", str(secs)],
            cwd=ROOT, stdout=logf, stderr=logf,
            start_new_session=True,  # outlive this process / the cron job
        )
        print(f"↻ self-improvement running in background (~{secs//60} min; "
              f"tail data/improvements.log)")
    except Exception as e:
        print(f"(self-improvement could not start: {e})")


def run_demo(cfg):
    """Generate a full, browsable daily+weekly+monthly set offline using
    synthetic prices (real IPOs when reachable), seeded with ~3 weeks of
    history so weekly/monthly have something to synthesise. Writes to
    site_demo/ and data/demo_snapshots/ — the real archive is untouched."""
    global SOURCE_FACTORY
    from lib.demosource import SyntheticSource

    use_demo_paths()
    ensure_dirs()
    # start the demo archive fresh each time
    for stale in glob.glob(os.path.join(SNAP, "*.json")):
        os.remove(stale)
    if os.path.exists(ISSUES_JSON):
        os.remove(ISSUES_JSON)
    issues = []
    dt = now()

    nseed = 21
    print(f"Seeding {nseed} days of synthetic history…")
    for off in range(nseed, 0, -1):
        d = (dt - datetime.timedelta(days=off)).strftime("%Y-%m-%d")
        recs, _ = build_snapshot(cfg, SyntheticSource(off), quiet=True)
        save_snapshot(d, recs)

    SOURCE_FACTORY = lambda: SyntheticSource(0)  # noqa: E731
    print("Generating zettel…")
    gen_daily(cfg, issues, dt)
    gen_weekly(cfg, issues, dt)
    gen_monthly(cfg, issues, dt)
    print(f"\n✓ Demo built — {len(issues)} zettel. Open: site_demo/index.html")
    print("  (synthetic prices for layout/mechanics; IPO radar is live data)")


def main():
    kind = sys.argv[1] if len(sys.argv) > 1 else "daily"
    cfg = load_config()

    if kind == "demo":
        run_demo(cfg)
        return

    ensure_dirs()
    issues = load_issues()
    dt = now()

    if kind == "daily":
        f = gen_daily(cfg, issues, dt)
    elif kind == "weekly":
        f = gen_weekly(cfg, issues, dt)
    elif kind == "monthly":
        f = gen_monthly(cfg, issues, dt)
    elif kind == "build":
        rebuild_index(cfg, issues)
        print("Rebuilt index from", len(issues), "zettel.")
        launch_self_improvement(cfg)
        return
    else:
        sys.exit(f"Unknown command '{kind}'. Use daily|weekly|monthly|build|demo.")

    print(f"Wrote site/zettel/{f}  (№{issues[-1]['num']:03d}, {kind})")
    print(f"Open site/index.html")
    launch_self_improvement(cfg)


if __name__ == "__main__":
    main()
