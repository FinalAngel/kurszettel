"""HTML rendering for Kurszettel zettel and the archive index.

Renderers take already-computed context dicts (built in generate.py) and return
strings. No data access happens here. Charts are inline SVG — no JS, no deps.

Each cadence has its own identity:
  daily   "The Tape"        — what's happening (awareness)
  weekly  "The Review"      — your standings, retained (memory)
  monthly "The Allocation"  — keep / sell / buy + the monthly plan (action)
"""

import html

FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?'
    'family=Fraunces:ital,opsz,wght@0,9..144,400..600;1,9..144,400..500&'
    'family=Inter:wght@400;500;600;700;800&'
    'family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">'
)

CADENCE = {
    "daily":   {"eyebrow": "The Tape",       "sub": "today's market pulse"},
    "weekly":  {"eyebrow": "The Review",     "sub": "the week, retained"},
    "monthly": {"eyebrow": "The Allocation", "sub": "what to own — and how much"},
}


def esc(s):
    return html.escape(str(s if s is not None else ""))


# ---- formatting ------------------------------------------------------
def _pct(v, digits=2):
    if v is None:
        return '<span class="num faint">—</span>'
    cls = "up" if v > 0 else ("down" if v < 0 else "")
    return f'<span class="num {cls}">{v:+.{digits}f}%</span>'


def _points(v):
    if v is None:
        return '<span class="num faint">—</span>'
    cls = "up" if v > 0 else ("down" if v < 0 else "")
    return f'<span class="num {cls}">{v:+.0f}</span>'


_SYM = {"USD": "$", "EUR": "€", "CHF": "CHF ", "GBP": "£", "GBp": "p"}


def _price(v, ccy=None):
    if v is None:
        return "—"
    sym = _SYM.get(ccy, "")
    return f"{sym}{v:,.0f}" if v >= 1000 else f"{sym}{v:.2f}"


def _money(v, ccy):
    if v is None:
        return "—"
    return f"{ccy} {v:,.0f}"


def _level(v):
    if v is None:
        return "—"
    return f"{v:,.0f}" if v >= 1000 else f"{v:,.2f}"


# ---- charts (inline SVG) --------------------------------------------
def _sparkline(values, w=140, h=34, cls=None):
    vals = [v for v in (values or []) if v is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    pad = 3
    n = len(vals)
    pts = []
    for i, v in enumerate(vals):
        x = pad + i / (n - 1) * (w - 2 * pad)
        y = h - pad - (v - lo) / rng * (h - 2 * pad)
        pts.append((x, y))
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"{pad:.1f},{h - pad:.1f} {line} {w - pad:.1f},{h - pad:.1f}"
    klass = cls or ("spark-up" if vals[-1] >= vals[0] else "spark-down")
    return (f'<svg class="spark {klass}" viewBox="0 0 {w} {h}" '
            f'preserveAspectRatio="none" aria-hidden="true">'
            f'<polygon class="area" points="{area}"/>'
            f'<polyline points="{line}"/></svg>')


def _score_bar(score, verdict):
    s = max(0.0, min(100.0, score))
    return (f'<div class="sbar" title="Composite score {score:.0f}/100">'
            f'<div class="track"></div>'
            f'<span class="mk v-{verdict}" style="left:{s:.0f}%"></span></div>')


def _weight_bar(weight, cls=""):
    w = max(0.0, min(100.0, weight))
    return f'<div class="wbar {cls}"><span style="width:{w:.0f}%"></span></div>'


# ---- page shell ------------------------------------------------------
def page(cfg, issue, inner, *, asset_prefix="", is_index=False):
    title = esc(cfg["title"])
    kind = "home" if is_index else (issue.get("kind") or "daily")
    if is_index:
        head = f'{title} — {esc(cfg["tagline"])}'
    else:
        head = f'{title} №{issue["num"]:03d} — {esc(issue["title"])}'
    css = asset_prefix + "assets/style.css"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(head)}</title>
<meta name="description" content="{esc(cfg['tagline'])}">
{FONTS}
<link rel="stylesheet" href="{esc(css)}">
</head>
<body class="theme-{kind}">
<div class="wrap">
{inner}
</div>
</body>
</html>
"""


def masthead(cfg, issue, asset_prefix=""):
    kind = issue.get("kind", "daily")
    cad = CADENCE.get(kind, CADENCE["daily"])
    return f"""<header class="masthead">
  <div class="kicker">
    <a href="{asset_prefix}index.html">{esc(cfg['title'])}</a>
    <span>№{issue['num']:03d} · {esc(issue['date_long'])}</span>
  </div>
  <div class="eyebrow">{esc(cad['eyebrow'])} <span>— {esc(cad['sub'])}</span></div>
  <h1>{esc(issue['title'])}</h1>
  <p class="tagline">{esc(issue['headline'])}</p>
  <div class="issue-meta">
    <span>{esc(cfg['schedule_note'])}</span>
    <span>{esc(issue['universe_note'])}</span>
  </div>
</header>"""


def _strip(cells, cls=""):
    return (f'<div class="strip {cls}">' + "".join(
        f'<span class="cell"><span class="k">{esc(k)}</span>{v}</span>'
        for k, v in cells) + "</div>")


# ---- shared sections -------------------------------------------------
def _verdict_badge(rec):
    v = rec["verdict"]
    return (f'<span class="verdict v-{v}">{v}</span>'
            f'<span class="verdict score v-{v}">{rec["score"]:.0f}</span>')


def _rank_item(rec, idx):
    bars = rec.get("breakdown", {})
    chips = "".join(f'<span class="b">{k[:4]} {bars[k]}</span>'
                    for k in ("trend", "momentum", "analyst", "position")
                    if k in bars)
    return f"""<li class="row">
  <span class="idx">{idx:02d}</span>
  <div class="main">
    <div class="head"><span class="name">{esc(rec['name'])}</span>
      <span class="tkr">{esc(rec['symbol'])}</span>
      <span class="region">{esc(rec['region'])}</span>{_verdict_badge(rec)}</div>
    <div class="why">{esc(rec['rationale'])}</div>
    <div class="bars">{chips}</div>
    {_score_bar(rec['score'], rec['verdict'])}
  </div>
  <div class="aside">
    {_sparkline(rec.get('spark'))}
    <div class="px">{_price(rec['price'], rec.get('currency'))}</div>
    <div class="chg">{_pct(rec.get('ret_1d'))}</div>
  </div>
</li>"""


def _movers_col(title, rows, key="ret_1d", fmt=_pct):
    lis = "".join(
        f'<li><span>{esc(r["name"])} '
        f'<span class="tkr">{esc(r["symbol"])}</span></span>'
        f'{fmt(r.get(key))}</li>' for r in rows)
    return f'<div><h3>{esc(title)}</h3><ul>{lis}</ul></div>'


def _news_list(items):
    if not items:
        return '<p class="faint">No fresh headlines pulled this run.</p>'
    lis = ""
    for it in items:
        meta = " · ".join(x for x in [it.get("ticker"), it.get("source"),
                                      it.get("pubDate", "")[:16]] if x)
        lis += (f'<li><div class="t"><a href="{esc(it["link"])}" target="_blank" '
                f'rel="noopener">{esc(it["title"])}</a></div>'
                f'<div class="m">{esc(meta)}</div></li>')
    return f'<ul class="news">{lis}</ul>'


def _footer(cfg, asset_prefix=""):
    srcs = " · ".join(f'{esc(s["label"])} <span class="faint">({esc(s["note"])})</span>'
                      for s in cfg.get("sources", []))
    return f"""<footer class="foot">
  <p class="sources">Sources — {srcs}</p>
  <p class="disclaimer">{esc(cfg['title'])} is a mechanical, rules-based reading of public
  market data for personal information only. It is not investment advice, not a
  recommendation, and not a solicitation to buy or sell any security. Signals
  can be wrong and past behaviour does not predict returns. Do your own
  research; consider your situation; capital is at risk.</p>
  <p><a href="{asset_prefix}index.html">← All zettel</a></p>
</footer>"""


# ---- market context --------------------------------------------------
def market_context_section(ctx):
    rows = ctx.get("benchmarks") or []
    label, sentence = ctx.get("regime", ("", ""))
    if not rows:
        return ('<section class="section"><h2>Market context</h2>'
                '<p class="faint">Benchmark data was unavailable this run '
                '(data source rate-limited).</p></section>')
    cls = {"Risk-on": "v-BUY", "Neutral": "v-HOLD", "Risk-off": "v-SELL"}.get(label, "v-HOLD")
    body = ""
    for r in rows:
        s200 = r.get("sma200")
        if s200 is None:
            arrow = '<span class="faint">·</span>'
        elif r["price"] > s200:
            arrow = '<span class="up">▲ above 200d</span>'
        else:
            arrow = '<span class="down">▼ below 200d</span>'
        body += (f'<li><span class="bn">{esc(r["name"])}</span>'
                 f'<span class="sp">{_sparkline(r.get("spark"), 80, 22)}</span>'
                 f'<span class="lv num">{_level(r.get("price"))}</span>'
                 f'<span class="num">{_pct(r.get("ret_1d"))}</span>'
                 f'<span class="num">{_pct(r.get("ret_1m"), 1)}</span>'
                 f'<span class="tr">{arrow}</span></li>')
    return f"""<section class="section">
  <h2>Market context</h2>
  <p class="lede"><span class="regime {cls}">{esc(label)}</span> {esc(sentence)}</p>
  <ul class="ctx">
    <li class="hd"><span class="bn">Gauge</span><span class="sp"></span>
      <span class="lv">Level</span><span>1d</span><span>1mo</span>
      <span class="tr">Trend</span></li>
    {body}
  </ul>
</section>"""


# ---- IPO radar -------------------------------------------------------
def _ipo_rows(rows, date_label):
    if not rows:
        return '<p class="faint">Nothing above the size threshold.</p>'
    out = '<ul class="ipo">'
    for r in rows:
        tkr = f'<span class="tkr">{esc(r["symbol"])}</span>' if r["symbol"] else ""
        out += (f'<li><div class="ic"><span class="co">{esc(r["company"])}</span> {tkr}'
                f'<div class="im">{esc(r.get("exchange") or "")}</div></div>'
                f'<div class="ir"><div class="num">{esc(r.get("value") or "")}</div>'
                f'<div class="im">{esc(date_label)} {esc(r.get("date") or "")}'
                f' · {esc(r.get("price") or "")}</div></div></li>')
    return out + "</ul>"


def ipo_section(ctx, *, show_priced=True):
    up, pr = ctx.get("ipos_up") or [], ctx.get("ipos_priced") or []
    if not up and not pr:
        return ('<section class="section"><h2>IPO radar</h2>'
                '<p class="faint">No upcoming or recent IPOs pulled this run.</p>'
                '</section>')
    cols = f'<div><h3>Pricing soon</h3>{_ipo_rows(up, "expected")}</div>'
    if show_priced:
        cols += f'<div><h3>Just listed</h3>{_ipo_rows(pr, "priced")}</div>'
    return f'<section class="section"><h2>IPO radar</h2><div class="movers">{cols}</div></section>'


# ---- portfolio -------------------------------------------------------
def _holding_row(r):
    risk = []
    if r.get("volatility") is not None:
        risk.append(f'vol {r["volatility"]:.0f}%')
    if r.get("max_drawdown") is not None:
        risk.append(f'maxDD {r["max_drawdown"]:.0f}%')
    if r.get("shares") and r.get("avg_cost"):
        risk.append(f'{r["shares"]:g} sh @ {_price(r["avg_cost"], r.get("currency"))}')
    risk_html = (' <span class="rk">· ' + " · ".join(risk) + "</span>") if risk else ""
    return f"""<li class="hrow">
  <div class="main">
    <div class="head"><span class="name">{esc(r['name'])}</span>
      <span class="tkr">{esc(r['symbol'])}</span>
      <span class="act a-{r['bucket']}">{esc(r['action'])}</span></div>
    <div class="why">{esc(r['action_blurb'])} · {esc(r['rationale'])}{risk_html}</div>
    {_score_bar(r['score'], r['verdict'])}
  </div>
  <div class="hnums">
    {_sparkline(r.get('spark'), 96, 28)}
    <div class="hval">{_money(r['value_base'], r.get('totals_base', ''))}
      <span class="hw">{r['weight']:.0f}%</span></div>
    <div class="hpnl">{_pct(r.get('pnl_pct'), 1)} <span class="faint">P&amp;L</span></div>
  </div>
</li>"""


def portfolio_standings_section(ctx):
    rows = ctx.get("portfolio_rows") or []
    t = ctx.get("portfolio_totals") or {}
    if not rows:
        return ('<section class="section"><h2>Where you stand</h2>'
                '<p class="faint">No holdings configured — add yours to '
                'config.json → portfolio.holdings.</p></section>')
    base = t.get("base", "")
    for r in rows:
        r["totals_base"] = base
    body = "".join(_holding_row(r) for r in rows)
    pnl = t.get("pnl")
    pnl_cls = "up" if (pnl or 0) > 0 else ("down" if (pnl or 0) < 0 else "")
    cells = [
        ("Portfolio value", f'<span class="num">{_money(t.get("value"), base)}</span>'),
        ("Total P&L", f'<span class="num {pnl_cls}">{(t.get("pnl_pct") or 0):+.1f}%'
                      f'<span class="sub">{_money(pnl, base)}</span></span>'),
        ("Keep / Sell / Buy", f'<span class="num">{t.get("n_keep",0)} / '
                              f'{t.get("n_sell",0)} / {t.get("n_add",0)}</span>'),
    ]
    if t.get("eff_n"):
        cells.append(("Diversification", f'<span class="num">{t["eff_n"]:.1f} eff · '
                      f'top {t.get("top_weight",0):.0f}%</span>'))
    if t.get("volatility"):
        cells.append(("Ann. volatility", f'<span class="num">{t["volatility"]:.0f}%</span>'))
    xray = ""
    if t.get("ccy_exp"):
        exp = " · ".join(f'{esc(k)} {v:.0f}%' for k, v in t["ccy_exp"].items())
        warn = (' <span class="warn">⚠ concentrated</span>'
                if t.get("top_weight", 0) > 35 else "")
        xray = (f'<p class="xray">Currency exposure — {exp}. '
                f'Effective holdings {t.get("eff_n",0):.1f} of {t.get("n",0)}.{warn}</p>')
    return f"""<section class="section">
  <h2>Where you stand — your holdings</h2>
  {_strip(cells, "strip-fit")}
  {xray}
  <ul class="holdings">{body}</ul>
</section>"""


def _decision_col(title, cls, rows, render_row):
    if not rows:
        inner = '<li class="faint">— none —</li>'
    else:
        inner = "".join(render_row(r) for r in rows)
    return (f'<div class="dcol {cls}"><h3>{esc(title)}</h3>'
            f'<ul>{inner}</ul></div>')


def decision_board_section(ctx):
    keep = ctx.get("keep_rows") or []
    sell = ctx.get("sell_rows") or []
    buy = ctx.get("buy_rows") or []
    if not (keep or sell or buy):
        return ""

    def hold_line(r):
        return (f'<li><span class="dn">{esc(r["name"])} '
                f'<span class="tkr">{esc(r["symbol"])}</span></span>'
                f'<span class="dd">{_pct(r.get("pnl_pct"),0)} · '
                f'<span class="num">{r["score"]:.0f}</span></span></li>')

    def buy_line(r):
        tag = '<span class="newtag">new</span>' if r.get("is_new") else \
              '<span class="newtag add">add</span>'
        up = f' · {r["upside"]:+.0f}% tgt' if r.get("upside") is not None else ""
        return (f'<li><span class="dn">{esc(r["name"])} '
                f'<span class="tkr">{esc(r["symbol"])}</span> {tag}</span>'
                f'<span class="dd"><span class="num">{r["score"]:.0f}</span>{esc(up)}</span></li>')

    cols = (_decision_col("Keep", "col-keep", keep, hold_line)
            + _decision_col("Sell / Trim", "col-sell", sell, hold_line)
            + _decision_col("Buy", "col-buy", buy, buy_line))
    return f"""<section class="section">
  <h2>The decision — keep · sell · buy</h2>
  <div class="board">{cols}</div>
</section>"""


def allocation_section(ctx):
    plan = ctx.get("alloc_plan") or []
    budget = ctx.get("budget")
    base = ctx.get("base_ccy", "")
    if not plan:
        return ""
    rows = ""
    for r in plan:
        tag = '<span class="newtag add">add to holding</span>' if r.get("is_held") else \
              '<span class="newtag">new idea</span>'
        rows += f"""<li>
  <div class="amain">
    <div class="head"><span class="name">{esc(r['name'])}</span>
      <span class="tkr">{esc(r['symbol'])}</span> {tag}
      <span class="verdict v-{r['verdict']}">{r['verdict']}</span></div>
    <div class="why">{esc(r['rationale'])}</div>
  </div>
  <div class="aamt">
    <div class="amt">{_money(r['amount_base'], base)}</div>
    <div class="im">buy <b>{r['shares']}</b> sh @ {_price(r['price'], r.get('currency'))}</div>
  </div>
</li>"""
    leftover = ctx.get("alloc_leftover")
    foot = (f'<p class="im" style="margin-top:10px">Uninvested cash carried '
            f'forward: {esc(_money(leftover, base))}.</p>' if leftover else "")
    return f"""<section class="section accent-box">
  <h2>This month's plan — invest {esc(_money(budget, base))}</h2>
  <p class="faint" style="margin:-6px 0 14px">Conviction-weighted across the
  strongest buy signals (held adds + new ideas), rounded to whole shares your
  budget can buy. Estimates, not orders.</p>
  <ul class="alloc">{rows}</ul>
  {foot}
</section>"""


def holdings_today_section(ctx):
    """Lightweight daily view: what moved in YOUR book today."""
    rows = ctx.get("portfolio_rows") or []
    if not rows:
        return ""
    movers = sorted([r for r in rows if r.get("ret_1d") is not None],
                    key=lambda r: abs(r["ret_1d"]), reverse=True)
    lis = ""
    for r in movers:
        lis += (f'<li><span class="dn">{esc(r["name"])} '
                f'<span class="tkr">{esc(r["symbol"])}</span> '
                f'<span class="act a-{r["bucket"]}">{esc(r["action"])}</span></span>'
                f'<span class="dd">{_pct(r.get("ret_1d"))} · '
                f'<span class="num">{_money(r["value_base"], ctx.get("base_ccy",""))}</span></span></li>')
    return f"""<section class="section">
  <h2>Your holdings today</h2>
  <ul class="htoday">{lis}</ul>
</section>"""


# ---- issue bodies ----------------------------------------------------
def daily_inner(cfg, issue, ctx):
    ranked = "".join(_rank_item(r, i + 1) for i, r in enumerate(ctx["ranked"]))
    shifts_html = ""
    if ctx.get("shifts"):
        rows = "".join(
            f'<li><span class="dn">{esc(s["name"])} '
            f'<span class="tkr">{esc(s["symbol"])}</span></span>'
            f'<span class="dd">{esc(s["from"])} → '
            f'<strong class="v-{s["to"]}">{esc(s["to"])}</strong></span></li>'
            for s in ctx["shifts"])
        shifts_html = (f'<section class="section"><h2>Signal shifts since '
                       f'yesterday</h2><ul class="htoday">{rows}</ul></section>')
    return f"""{masthead(cfg, issue)}
<section class="section">
  <p class="lede">{esc(ctx['lede'])}</p>
  {_strip(ctx['strip'])}
</section>
{holdings_today_section(ctx)}
{market_context_section(ctx)}
{shifts_html}
<section class="section">
  <h2>What to own now — the ranked book</h2>
  <ol class="rank">{ranked}</ol>
</section>
<section class="section">
  <h2>Today's movers — the market</h2>
  <div class="movers">
    {_movers_col("Leaders", ctx['gainers'], "ret_1d")}
    {_movers_col("Laggards", ctx['losers'], "ret_1d")}
  </div>
</section>
{ipo_section(ctx)}
<section class="section">
  <h2>On the wire</h2>
  {_news_list(ctx.get('news', []))}
</section>
{_footer(cfg)}"""


def _week_mover_row(r):
    return (f'<li><span class="dn">{esc(r["name"])} '
            f'<span class="tkr">{esc(r["symbol"])}</span></span>'
            f'<span class="wk">{_sparkline(r.get("score_series"), 70, 22, "spark-accent")}'
            f'{_points(r.get("score_delta"))}</span></li>')


def weekly_inner(cfg, issue, ctx):
    climb = "".join(_week_mover_row(r) for r in ctx["climbers"])
    fade = "".join(_week_mover_row(r) for r in ctx["faders"])

    def chg_line(s):
        return (f'<li><span class="dn">{esc(s["name"])} '
                f'<span class="tkr">{esc(s["symbol"])}</span></span>'
                f'<span class="dd"><span class="v-{s["from"]}">{esc(s["from"])}</span>'
                f' → <strong class="v-{s["to"]}">{esc(s["to"])}</strong></span></li>')
    ups = "".join(chg_line(s) for s in (ctx.get("upgrades") or [])) or '<li class="faint">— none —</li>'
    downs = "".join(chg_line(s) for s in (ctx.get("downgrades") or [])) or '<li class="faint">— none —</li>'

    return f"""{masthead(cfg, issue)}
<section class="section">
  <p class="lede">{esc(ctx['lede'])}</p>
  {_strip(ctx['strip'])}
</section>
{portfolio_standings_section(ctx)}
{decision_board_section(ctx)}
<section class="section">
  <h2>What changed this week</h2>
  <div class="movers">
    <div><h3>Conviction rising</h3><ul class="wmove">{climb}</ul></div>
    <div><h3>Conviction fading</h3><ul class="wmove">{fade}</ul></div>
  </div>
</section>
<section class="section">
  <h2>Upgrades &amp; downgrades</h2>
  <div class="board2">
    <div class="dcol col-buy"><h3>Upgraded</h3><ul>{ups}</ul></div>
    <div class="dcol col-sell"><h3>Downgraded</h3><ul>{downs}</ul></div>
  </div>
</section>
{market_context_section(ctx)}
{_footer(cfg)}"""


def _conviction_card(r, idx):
    return f"""<li class="ccard">
  <div class="crank">{idx:02d}</div>
  <div class="cmain">
    <div class="head"><span class="name">{esc(r['name'])}</span>
      <span class="tkr">{esc(r['symbol'])}</span>
      <span class="region">{esc(r['region'])}</span>
      <span class="verdict v-{r['verdict']}">{r['verdict']}</span></div>
    <div class="why">{esc(r['note'])}</div>
    <div class="cstats">
      <span>avg <b>{r['avg_score']:.0f}</b></span>
      <span>buy-rated <b>{r['buy_share']:.0f}%</b></span>
      <span>trend <b>{r['trend_disp']}</b></span>
      <span><b>{r['days']}</b> readings</span>
    </div>
  </div>
  <div class="cright">
    {_sparkline(r.get('score_series'), 130, 40, 'spark-accent')}
    <div class="cweight">
      <span class="wlbl">allocation</span>
      {_weight_bar(r.get('weight', 0), 'accent')}
      <span class="wpct">{r.get('weight', 0):.0f}%</span>
    </div>
    <div class="px">{_price(r['price'], r.get('currency'))} · {_pct(r.get('ret_1m'),1)}</div>
  </div>
</li>"""


def monthly_inner(cfg, issue, ctx):
    cards = "".join(_conviction_card(r, i + 1)
                    for i, r in enumerate(ctx["conviction"]))
    improving = _movers_col("Improving", ctx["improving"], "trend", _points)
    fading = _movers_col("Fading", ctx["fading"], "trend", _points)
    return f"""{masthead(cfg, issue)}
<section class="section">
  <p class="lede">{esc(ctx['lede'])}</p>
  {_strip(ctx['strip'])}
</section>
{allocation_section(ctx)}
{portfolio_standings_section(ctx)}
{decision_board_section(ctx)}
{market_context_section(ctx)}
<section class="section">
  <h2>Conviction list — the idea pool</h2>
  <p class="faint" style="margin:-6px 0 16px">Built from {esc(ctx['window_note'])}.
  Ranked by how strong, how consistent and how improving each name's signal has
  been. The suggested allocation bar weights by conviction.</p>
  <ul class="convlist">{cards}</ul>
</section>
<section class="section">
  <h2>Direction of travel</h2>
  <div class="movers">{improving}{fading}</div>
</section>
{ipo_section(ctx, show_priced=True)}
{_footer(cfg)}"""


# ---- landing ---------------------------------------------------------
def _latest_by_type(issues, type_label):
    matches = [it for it in issues if it.get("type") == type_label]
    return max(matches, key=lambda it: it["num"]) if matches else None


def _ticker_strip(cfg, ticker):
    """A scrolling marquee of quotes — the literal Kurszettel. Falls back to
    watchlist symbols when no snapshot data is available."""
    items = []
    for t in (ticker or []):
        ch = t.get("ret_1d")
        cls = "up" if (ch or 0) > 0 else ("down" if (ch or 0) < 0 else "flat")
        arrow = "▲" if (ch or 0) > 0 else ("▼" if (ch or 0) < 0 else "·")
        chg = f'{ch:+.2f}%' if ch is not None else ""
        px = _price(t.get("price"), t.get("currency")) if t.get("price") else ""
        items.append(f'<span class="tk"><b>{esc(t["symbol"])}</b>'
                     f'<span class="tp">{esc(px)}</span>'
                     f'<span class="{cls}">{arrow} {esc(chg)}</span></span>')
    if not items:
        for w in cfg.get("watchlist", [])[:18]:
            items.append(f'<span class="tk"><b>{esc(w["symbol"])}</b></span>')
    if not items:
        return ""
    run = "".join(items)
    return (f'<div class="ticker" aria-hidden="true"><div class="tk-track">'
            f'{run}{run}</div></div>')


def index_inner(cfg, issues, ticker=None):
    title = esc(cfg["title"])
    latest_all = max(issues, key=lambda it: it["num"]) if issues else None
    cta = (f'<a class="btn primary" href="{esc(latest_all["path"])}">'
           f'Read the latest zettel <span>→</span></a>' if latest_all else "")

    channels = [
        ("daily", "Daily", "The Tape", "What's moving today — your holdings, "
         "market breadth, the ranked book.", "daily · 09:00"),
        ("weekly", "Weekly", "The Review", "Your standings and the "
         "keep · sell · buy shortlist, so it sticks.", "Monday"),
        ("monthly", "Monthly", "The Allocation", "The decision and "
         "the plan — where this month's budget goes.", "1st of month"),
    ]
    cards = ""
    for kind, tlabel, name, blurb, when in channels:
        latest = _latest_by_type(issues, tlabel)
        link = latest["path"] if latest else "#"
        meta = (f'№{latest["num"]:03d} · {latest["date"]}' if latest else "soon")
        cards += f"""<a class="chan ch-{kind}" href="{esc(link)}">
      <span class="ctag">{esc(when)}</span>
      <span class="cname">{esc(name)}</span>
      <span class="cblurb">{esc(blurb)}</span>
      <span class="cmeta">{esc(meta)} <span class="ar">→</span></span>
    </a>"""

    tmap = {"Daily": "daily", "Weekly": "weekly", "Monthly": "monthly"}
    rows = ""
    for it in issues:
        k = tmap.get(it.get("type"), "daily")
        rows += f"""<li><a class="ti" href="{esc(it['path'])}">
    <span class="no">№{it['num']:03d}</span>
    <span class="badge b-{k}">{esc(it['type'])}</span>
    <span class="til">{esc(it['title'])}</span>
    <span class="dt">{esc(it['date'])} <span class="arrow">→</span></span>
  </a></li>"""
    archive = rows or '<li class="faint">No zettel yet — run the generator.</li>'

    return f"""<div class="lp">
{_ticker_strip(cfg, ticker)}
<header class="lp-hero">
  <div class="lp-inner">
    <div class="brand">{title}<i class="dot"></i></div>
    <h1 class="lp-title">Know what to <em>buy</em>, keep,<br>and sell — every morning.</h1>
    <p class="lp-sub">{esc(cfg['tagline'])} A quantitative reading of the tech
      market, your portfolio and the market's mood — distilled, scored, and
      turned into a monthly buy list you can act on.</p>
    <div class="lp-cta">{cta}
      <div class="chips"><span>daily 09:00</span><span>weekly Mon</span><span>monthly 1st</span></div>
    </div>
  </div>
</header>
<section class="lp-inner lp-block">
  <div class="eyebrow2">Three readings</div>
  <div class="channels">{cards}</div>
</section>
<section class="lp-inner lp-block">
  <div class="arc-head"><h2>The archive</h2><span>{len(issues)} zettel</span></div>
  <ul class="archive">{archive}</ul>
</section>
<div class="lp-inner">{_footer(cfg)}</div>
</div>"""
