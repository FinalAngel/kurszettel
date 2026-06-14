#!/usr/bin/env python3
"""Fast, network-free self-tests. These are the gate the self-improvement
loop must keep green: any tuned weights or code change that breaks a check
here is rejected and rolled back. Run directly: `python3 tests.py`."""

import os
import sys
import json
import math
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib import indicators, signals, backtest, render, trends, portfolio

ROOT = os.path.dirname(os.path.abspath(__file__))
_fail = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}  {detail}")
        _fail.append(name)


# -- indicators --------------------------------------------------------
def test_indicators():
    up = [float(i) for i in range(1, 60)]            # strictly rising
    check("sma last", indicators.sma(up, 5) == sum(up[-5:]) / 5)
    check("sma short->None", indicators.sma([1, 2], 5) is None)
    check("pct_change", abs(indicators.pct_change([100, 110], 1) - 10.0) < 1e-9)
    check("rsi all-up ~100", indicators.rsi(up, 14) > 99)
    down = [float(i) for i in range(60, 1, -1)]
    check("rsi all-down ~0", indicators.rsi(down, 14) < 1)
    check("range_pos top", indicators.high_low_position(up) > 99)
    m = indicators.metrics(up)
    check("metrics keys", all(k in m for k in
          ("price", "sma50", "rsi", "macd_hist", "ret_1m", "range_pos",
           "volatility", "max_drawdown")))
    # max drawdown on a series that dips then recovers
    dd = indicators.max_drawdown([100, 120, 60, 90], lookback=10)
    check("max_drawdown negative", dd is not None and -51 < dd < -49, f"dd={dd}")
    check("volatility positive", indicators.volatility(
        [100 * (1.01 ** i) * (1.03 if i % 2 else 0.98) for i in range(40)]) > 0)


# -- signals + weights -------------------------------------------------
def test_signals():
    w = signals.load_weights()
    check("weights have lenses", set(w["lenses"]) ==
          {"trend", "momentum", "analyst", "position"})
    bands = signals.verdict_bands(w)
    ths = [t for t, _ in bands]
    check("thresholds descending", all(a >= b for a, b in zip(ths, ths[1:])))
    check("verdict high=BUY", signals.verdict(95, w) == "BUY")
    check("verdict low=SELL", signals.verdict(5, w) == "SELL")

    m = {"price": 100, "sma50": 90, "sma200": 80, "rsi": 60,
         "macd_hist": 1.0, "ret_1d": 1, "ret_1w": 2, "ret_1m": 4,
         "ret_3m": 8, "range_pos": 70}
    a = {"rec_mean": 2.0, "rec_key": "buy", "target_mean": 120}
    sc, bd = signals.score(m, a, w)
    check("score in range", 0 <= sc <= 100, f"sc={sc}")
    check("breakdown lenses", set(bd) <=
          {"trend", "momentum", "analyst", "position"})
    # the backtester must re-score from the stored breakdown the same way
    # the live scorer does — this invariant is what makes tuning valid
    recomputed = backtest.composite(bd, w["lenses"])
    check("backtest re-score matches live", abs(recomputed - sc) < 1.5,
          f"live={sc} backtest={recomputed:.1f}")
    # no-analyst name still scores
    sc3, bd3 = signals.score(m, {}, w)
    check("score without analyst", 0 <= sc3 <= 100 and "analyst" not in bd3)


def test_weights_file():
    p = os.path.join(ROOT, "weights.json")
    if not os.path.exists(p):
        print("  ok   weights.json absent (defaults in use)")
        return
    with open(p, encoding="utf-8") as f:
        w = json.load(f)
    lw = w.get("lenses", {})
    check("wf lens keys", set(lw) == {"trend", "momentum", "analyst", "position"})
    check("wf lens numeric>=0",
          all(isinstance(v, (int, float)) and v >= 0 for v in lw.values()))
    check("wf lens not all zero", sum(lw.values()) > 0)
    if "thresholds" in w:
        t = w["thresholds"]
        order = [t.get("BUY"), t.get("ACCUMULATE"), t.get("HOLD"), t.get("REDUCE")]
        check("wf thresholds present", all(x is not None for x in order))
        check("wf thresholds descending",
              all(a > b for a, b in zip(order, order[1:])))
        check("wf thresholds in range", all(0 <= x <= 100 for x in order))


# -- backtest math -----------------------------------------------------
def test_backtest():
    bd = {"trend": 100, "momentum": 0, "analyst": 50, "position": 50}
    c = backtest.composite(bd, {"trend": 1, "momentum": 1, "analyst": 0, "position": 0})
    check("composite avg", abs(c - 50.0) < 1e-9, f"c={c}")
    c2 = backtest.composite(bd, {"trend": 1, "momentum": 0, "analyst": 0, "position": 0})
    check("composite weighted", abs(c2 - 100.0) < 1e-9, f"c2={c2}")
    # synthetic 2-snapshot history where score perfectly predicts return
    snaps = []
    for d in ("2026-01-01", "2026-01-02"):
        recs = []
        for i in range(12):
            recs.append({"symbol": f"S{i}", "price": 100.0,
                         "breakdown": {"trend": i * 9, "momentum": i * 9,
                                       "analyst": i * 9, "position": i * 9}})
        snaps.append({"date": d, "recs": recs})
    # make future prices rise with sub-score on the 2nd snapshot
    for i, r in enumerate(snaps[1]["recs"]):
        r["price"] = 100.0 * (1 + i / 100.0)
    val, n = backtest.objective(snaps, signals.load_weights(),
                                horizons=(1,), min_names=6)
    check("objective positive when score predicts", val is not None and val > 0,
          f"val={val}")


# -- trends / market context + ipo ------------------------------------
def test_trends():
    ctx = [
        {"symbol": "^GSPC", "name": "S&P 500", "kind": "index",
         "price": 6000, "sma200": 5500, "ret_1m": 2.0, "range_pos": 80},
        {"symbol": "^IXIC", "name": "Nasdaq", "kind": "index",
         "price": 20000, "sma200": 18000, "ret_1m": 3.0, "range_pos": 85},
        {"symbol": "^VIX", "name": "VIX", "kind": "vol",
         "price": 13.0, "sma200": 16, "ret_1m": -5, "range_pos": 20},
    ]
    label, sentence = trends.regime(ctx)
    check("regime risk-on", label == "Risk-on", f"label={label}")
    check("regime sentence", "200-day" in sentence and "VIX" in sentence)
    # stressed market -> risk-off
    bad = [dict(ctx[0], price=5000, sma200=5500, ret_1m=-4),
           dict(ctx[1], price=16000, sma200=18000, ret_1m=-6),
           dict(ctx[2], price=33.0)]
    check("regime risk-off", trends.regime(bad)[0] == "Risk-off")
    check("regime empty ok", trends.regime([])[0] in
          ("Risk-on", "Neutral", "Risk-off"))
    # ipo filtering by deal size
    ipos = {"upcoming": [{"symbol": "BIG", "company": "Big", "value_num": 2e8,
                          "value": "$200,000,000", "date": "6/20/2026"},
                         {"symbol": "SML", "company": "Small", "value_num": 1e6,
                          "value": "$1,000,000", "date": "6/21/2026"}],
            "priced": []}
    up, pr = trends.filter_ipos(ipos, 5e7, 12)
    check("ipo size filter", len(up) == 1 and up[0]["symbol"] == "BIG")


# -- portfolio ---------------------------------------------------------
def test_portfolio():
    holdings = [{"symbol": "AAA", "shares": 10, "avg_cost": 100.0},
                {"symbol": "BBB", "shares": 5, "avg_cost": 200.0}]
    rec_by = {
        "AAA": {"symbol": "AAA", "name": "Aco", "region": "US", "currency": "USD",
                "price": 150.0, "score": 80.0, "verdict": "BUY", "ret_1d": 1.0,
                "volatility": 30.0, "max_drawdown": -20.0, "upside": 12.0},
        "BBB": {"symbol": "BBB", "name": "Bco", "region": "US", "currency": "CHF",
                "price": 150.0, "score": 30.0, "verdict": "SELL", "ret_1d": -2.0,
                "volatility": 50.0, "max_drawdown": -40.0},
    }
    fx = {"USD": 0.9, "CHF": 1.0}
    rows, t = portfolio.analyze(holdings, rec_by, fx, "CHF")
    check("portfolio rows", len(rows) == 2)
    check("pnl computed", rows[0]["pnl_pct"] is not None)
    check("buckets assigned", {r["bucket"] for r in rows} == {"BUY", "SELL"})
    check("weights sum ~100", abs(sum(r["weight"] for r in rows) - 100) < 0.1)
    check("xray present", t["eff_n"] > 0 and 0 <= t["top_weight"] <= 100)
    check("ccy exposure", abs(sum(t["ccy_exp"].values()) - 100) < 0.1)
    # discrete allocation must not exceed budget and yield whole shares
    cands = [dict(rec_by["AAA"]), dict(rec_by["BBB"], score=75.0, verdict="BUY")]
    plan, leftover = portfolio.allocation_plan(cands, 1000, fx, "CHF", 5)
    spent = sum(p["amount_base"] for p in plan)
    check("alloc within budget", spent <= 1000 + 1e-6 and leftover >= -1e-6)
    check("alloc whole shares", all(float(p["shares"]).is_integer() for p in plan))
    check("alloc + leftover = budget", abs(spent + leftover - 1000) < 1e-6)
    # buy candidates exclude held symbols
    cand = portfolio.buy_candidates(
        [{"symbol": "CCC", "name": "C", "score": 75, "verdict": "BUY"},
         {"symbol": "AAA", "name": "A", "score": 90, "verdict": "BUY"}],
        {"AAA"})
    check("buy candidates exclude held", [c["symbol"] for c in cand] == ["CCC"])


# -- render smoke ------------------------------------------------------
def test_render():
    cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
    rec = {"symbol": "AAA", "name": "Test Co", "region": "US",
           "currency": "USD", "price": 123.45, "ret_1d": 1.2, "ret_1w": 2.0,
           "ret_1m": 3.0, "score": 80.0, "verdict": "BUY",
           "breakdown": {"trend": 70, "momentum": 60, "analyst": 75, "position": 55},
           "rationale": "uptrend; RSI 58", "upside": 10.0}
    issue = {"num": 1, "type_label": "Daily", "title": "t", "headline": "h",
             "date_long": "Sunday, 14 June 2026", "universe_note": "n"}
    bench = [{"symbol": "^GSPC", "name": "S&P 500", "kind": "index",
              "price": 6000.0, "ret_1d": 0.5, "ret_1m": 2.0, "sma200": 5500,
              "range_pos": 80}]
    ipos_up = [{"symbol": "NEW", "company": "Newco", "exchange": "NASDAQ",
                "date": "6/20/2026", "price": "18.00", "value": "$200,000,000",
                "value_num": 2e8}]
    hrow = {"symbol": "HLD", "name": "Holdco", "region": "US", "currency": "USD",
            "shares": 10, "avg_cost": 100.0, "price": 150.0, "value_native": 1500.0,
            "value_base": 1350.0, "pnl_pct": 50.0, "pnl_base": 450.0, "weight": 60.0,
            "score": 80.0, "verdict": "BUY", "ret_1d": 1.0, "ret_1m": 5.0,
            "volatility": 30.0, "max_drawdown": -20.0, "spark": [1, 2, 3],
            "rationale": "uptrend", "action": "ADD", "bucket": "BUY",
            "action_blurb": "strong"}
    totals = {"value": 2250.0, "cost": 1800.0, "pnl": 450.0, "pnl_pct": 25.0,
              "day": 10.0, "day_pct": 0.4, "base": "CHF", "n": 1,
              "n_keep": 0, "n_sell": 0, "n_add": 1, "eff_n": 1.0, "top_weight": 60.0,
              "ccy_exp": {"USD": 100.0}, "volatility": 30.0}
    ctx = {"lede": "x", "strip": [("A", "1")], "ranked": [rec],
           "gainers": [rec], "losers": [rec], "shifts": [], "news": [],
           "benchmarks": bench, "regime": trends.regime(bench),
           "ipos_up": ipos_up, "ipos_priced": [],
           "portfolio_rows": [hrow], "portfolio_totals": totals, "base_ccy": "CHF",
           "keep_rows": [], "sell_rows": [],
           "buy_rows": [{"name": "Holdco", "symbol": "HLD", "score": 80,
                         "upside": 12, "is_new": False}]}
    html = render.daily_inner(cfg, issue, ctx)
    check("daily renders verdict", "v-BUY" in html and "Test Co" in html)
    check("daily renders market context", "Market context" in html and
          "above 200d" in html and "Risk-on" in html)
    check("daily renders ipo radar", "IPO radar" in html and "Newco" in html)
    check("daily renders holdings today", "Your holdings today" in html and
          "Holdco" in html)

    # weekly: standings + decision board
    wk = dict(ctx, climbers=[dict(rec, score_delta=5, score_series=[1, 2, 3])],
              faders=[dict(rec, score_delta=-5, score_series=[3, 2, 1])],
              upgrades=[{"name": "X", "symbol": "X", "from": "HOLD", "to": "BUY"}],
              downgrades=[])
    hw = render.weekly_inner(cfg, dict(issue, kind="weekly", type_label="Weekly"), wk)
    check("weekly standings", "Where you stand" in hw and "decision" in hw.lower())

    # monthly: allocation plan + conviction cards
    conv = dict(rec, avg_score=78, buy_share=80, trend_disp="+6 pts", days=20,
                note="strong", weight=40, score_series=[1, 2, 3, 4])
    mc = dict(ctx, conviction=[conv], improving=[dict(rec, trend=6)],
              fading=[dict(rec, trend=-6)], window_note="20 readings",
              budget=500, alloc_plan=[{"name": "Holdco", "symbol": "HLD",
              "region": "US", "verdict": "BUY", "score": 80, "amount_base": 480,
              "price": 150, "currency": "USD", "shares": 3, "rationale": "x",
              "is_held": True}], alloc_leftover=20)
    hm = render.monthly_inner(cfg, dict(issue, kind="monthly", type_label="Monthly"), mc)
    check("monthly allocation", "This month's plan" in hm and "buy <b>3</b>" in hm)
    check("monthly conviction cards", "Conviction list" in hm and "allocation" in hm)

    # graceful when feeds are empty (throttled) + no portfolio
    ctx2 = dict(ctx, benchmarks=[], regime=("", ""), ipos_up=[], ipos_priced=[],
                portfolio_rows=[], portfolio_totals={})
    html2 = render.daily_inner(cfg, issue, ctx2)
    check("daily degrades gracefully", "unavailable" in html2 and
          "No upcoming or recent IPOs" in html2)
    page = render.page(cfg, issue, html, asset_prefix="../")
    check("page wraps html", page.startswith("<!doctype html>") and "</html>" in page)
    issues_l = [{"num": 1, "type": "Daily", "title": "t",
                 "date": "2026-06-14", "path": "zettel/001.html"}]
    idx = render.index_inner(cfg, issues_l, ticker=[
        {"symbol": "NVDA", "price": 300.0, "ret_1d": 1.5, "currency": "USD"},
        {"symbol": "AAPL", "price": 200.0, "ret_1d": -0.8, "currency": "USD"}])
    check("landing hero", "lp-title" in idx and cfg["title"] in idx)
    check("landing ticker", "tk-track" in idx and "NVDA" in idx)
    check("landing channels", "The Tape" in idx and "The Allocation" in idx)
    check("landing archive", "The archive" in idx and "zettel/001.html" in idx)
    # ticker falls back to watchlist when no snapshot
    idx2 = render.index_inner(cfg, issues_l)
    check("ticker fallback", "tk-track" in idx2)


def main():
    for t in (test_indicators, test_signals, test_weights_file,
              test_backtest, test_trends, test_portfolio, test_render):
        print(t.__name__)
        t()
    print()
    if _fail:
        print(f"FAILED: {len(_fail)} check(s): {', '.join(_fail)}")
        sys.exit(1)
    print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()
