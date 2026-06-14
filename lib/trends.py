"""Market-context reading: turn a handful of benchmark instruments (indices,
the VIX, the 10-year yield, sector ETFs) into a one-line 'regime' so each
issue opens with the weather before the stock-picking.

This is deliberately simple and transparent — a risk-on / neutral / risk-off
label driven by how many equity indices are above their 200-day line and where
the VIX sits — and is shown, never hidden.
"""


def _above_200d(rec):
    s200 = rec.get("sma200")
    return s200 is not None and rec["price"] > s200


def regime(context):
    """context: list of benchmark recs (symbol, kind, price, sma200, ret_1m,
    range_pos...). Returns (label, sentence)."""
    eq = [r for r in context if r.get("kind") in ("index", "etf")]
    vix = next((r for r in context if r.get("kind") == "vol"), None)

    above = [r for r in eq if _above_200d(r)]
    n_eq = len(eq)
    breadth_up = len(above)
    vix_level = vix["price"] if vix and vix.get("price") else None

    if vix_level is None:
        vix_word = ""
    elif vix_level < 15:
        vix_word = "calm"
    elif vix_level < 20:
        vix_word = "subdued"
    elif vix_level < 28:
        vix_word = "elevated"
    else:
        vix_word = "stressed"

    trend_up = n_eq and breadth_up >= max(1, n_eq * 0.6)
    trend_dn = n_eq and breadth_up <= n_eq * 0.4

    if trend_up and (vix_level is None or vix_level < 20):
        label = "Risk-on"
    elif trend_dn or (vix_level is not None and vix_level > 28):
        label = "Risk-off"
    else:
        label = "Neutral"

    parts = []
    if n_eq:
        parts.append(f"{breadth_up}/{n_eq} equity gauges above their 200-day line")
    if vix_level is not None:
        parts.append(f"VIX {vix_level:.0f} ({vix_word})")
    # leadership: best 1-month sector/index
    led = max((r for r in eq if r.get("ret_1m") is not None),
              key=lambda r: r["ret_1m"], default=None)
    if led:
        parts.append(f"{led['name']} leading at {led['ret_1m']:+.1f}% 1-mo")
    sentence = label + " — " + "; ".join(parts) + "." if parts else label + "."
    return label, sentence


def filter_ipos(ipos, min_deal_usd, max_show):
    """Keep the most substantial deals, upcoming first then recently priced."""
    def big(rows):
        return [r for r in rows
                if r.get("value_num") is None or r["value_num"] >= min_deal_usd]
    up = sorted(big(ipos.get("upcoming", [])),
                key=lambda r: (r.get("value_num") or 0), reverse=True)
    pr = sorted(big(ipos.get("priced", [])),
                key=lambda r: (r.get("value_num") or 0), reverse=True)
    return up[:max_show], pr[:max_show]
