"""Portfolio awareness: take your holdings + the same signal engine used for
the watchlist and turn them into a clear keep / sell / buy decision, plus a
concrete monthly allocation plan for a fixed budget.

Recommendations are mechanical and signal-driven (not advice). The three
top-level buckets are:

  KEEP  — constructive or neutral signal, stay the course
  SELL  — signal has broken down (TRIM = lighten, SELL = exit)
  BUY   — strong signal worth adding to (held winners) or starting (new ideas)
"""

# fine-grained action -> (label, top-level bucket, blurb)
def action_for(score, verdict, pnl_pct):
    if verdict == "SELL":
        return ("SELL", "SELL", "signal broke down — exit")
    if verdict == "REDUCE":
        return ("TRIM", "SELL", "weakening — lighten the position")
    if verdict == "BUY":
        return ("ADD", "BUY", "strong signal — add on the monthly")
    if verdict == "ACCUMULATE":
        return ("KEEP+", "KEEP", "constructive — hold, add if room")
    return ("KEEP", "KEEP", "neutral — hold and watch")


def analyze(holdings, rec_by_symbol, fx_to_base, base_ccy):
    """Returns (rows, totals). Each row marries a holding to its live signal."""
    rows = []
    for h in holdings:
        sym = h["symbol"]
        rec = rec_by_symbol.get(sym)
        if not rec or not rec.get("price"):
            continue
        price = rec["price"]
        ccy = rec.get("currency") or base_ccy
        shares = h.get("shares", 0)
        avg = h.get("avg_cost")
        fx = fx_to_base.get(ccy, 1.0) or 1.0
        value_native = price * shares
        value_base = value_native * fx
        cost_base = (avg or 0) * shares * fx
        pnl_pct = ((price / avg - 1.0) * 100.0) if avg else None
        pnl_base = (value_base - cost_base) if avg else None
        label, bucket, blurb = action_for(rec["score"], rec["verdict"], pnl_pct)
        rows.append({
            "symbol": sym, "name": rec["name"], "region": rec.get("region", "—"),
            "currency": ccy, "shares": shares, "avg_cost": avg, "price": price,
            "value_native": value_native, "value_base": value_base,
            "pnl_pct": pnl_pct, "pnl_base": pnl_base,
            "score": rec["score"], "verdict": rec["verdict"],
            "ret_1d": rec.get("ret_1d"), "ret_1m": rec.get("ret_1m"),
            "upside": rec.get("upside"), "spark": rec.get("spark"),
            "volatility": rec.get("volatility"), "max_drawdown": rec.get("max_drawdown"),
            "rationale": rec.get("rationale", ""),
            "action": label, "bucket": bucket, "action_blurb": blurb,
        })
    total_value = sum(r["value_base"] for r in rows)
    total_cost = sum((r["avg_cost"] or 0) * r["shares"] *
                     (fx_to_base.get(r["currency"], 1.0) or 1.0) for r in rows)
    for r in rows:  # portfolio weight
        r["weight"] = (r["value_base"] / total_value * 100.0) if total_value else 0.0
    rows.sort(key=lambda r: r["value_base"], reverse=True)
    day = sum(r["value_base"] * (r.get("ret_1d") or 0) / 100.0 for r in rows)

    # concentration X-ray (Herfindahl index + effective number of holdings)
    fracs = [r["value_base"] / total_value for r in rows] if total_value else []
    hhi = sum(f * f for f in fracs)
    eff_n = (1.0 / hhi) if hhi else 0.0
    ccy_exp = {}
    for r in rows:
        ccy_exp[r["currency"]] = ccy_exp.get(r["currency"], 0.0) + r["value_base"]
    ccy_exp = {k: v / total_value * 100.0 for k, v in ccy_exp.items()} if total_value else {}
    # value-weighted annualised volatility
    port_vol = (sum(r["value_base"] * (r.get("volatility") or 0) for r in rows)
                / total_value) if total_value else None

    totals = {
        "value": total_value, "cost": total_cost,
        "day": day, "day_pct": (day / total_value * 100.0) if total_value else None,
        "pnl": total_value - total_cost,
        "pnl_pct": ((total_value / total_cost - 1.0) * 100.0) if total_cost else None,
        "base": base_ccy, "n": len(rows),
        "n_keep": sum(1 for r in rows if r["bucket"] == "KEEP"),
        "n_sell": sum(1 for r in rows if r["bucket"] == "SELL"),
        "n_add": sum(1 for r in rows if r["bucket"] == "BUY"),
        "hhi": hhi, "eff_n": eff_n, "top_weight": (max(fracs) * 100.0 if fracs else 0.0),
        "ccy_exp": dict(sorted(ccy_exp.items(), key=lambda kv: -kv[1])),
        "volatility": port_vol,
    }
    return rows, totals


def buy_candidates(watchlist_recs, held_symbols, limit=8):
    """New ideas: watchlist names you DON'T own, rated BUY/ACCUMULATE,
    best score first."""
    out = [r for r in watchlist_recs
           if r["symbol"] not in held_symbols
           and r["verdict"] in ("BUY", "ACCUMULATE")]
    out.sort(key=lambda r: r["score"], reverse=True)
    return out[:limit]


def allocation_plan(candidates, budget, fx_to_base, base_ccy, max_positions=5):
    """Conviction-weight `budget` across the strongest candidates, then convert
    to WHOLE shares the budget can actually buy (greedy largest-remainder).
    Returns (plan_rows, leftover_cash)."""
    picks = candidates[:max_positions]
    if not picks or budget <= 0:
        return [], budget
    weights = [max(1.0, r["score"] - 45) for r in picks]  # score above HOLD
    tot = sum(weights) or 1.0
    plan = []
    for r, w in zip(picks, weights):
        ccy = r.get("currency") or base_ccy
        fx = fx_to_base.get(ccy, 1.0) or 1.0
        price_base = (r["price"] or 0) * fx
        target = budget * w / tot
        shares = int(target // price_base) if price_base else 0
        plan.append({
            "symbol": r["symbol"], "name": r["name"], "region": r.get("region", "—"),
            "verdict": r["verdict"], "score": r["score"],
            "price": r["price"], "currency": ccy, "price_base": price_base,
            "target": target, "shares": shares,
            "amount_base": shares * price_base, "spark": r.get("spark"),
            "rationale": r.get("rationale", ""), "is_held": r.get("_held", False),
        })
    spent = sum(p["amount_base"] for p in plan)
    leftover = budget - spent
    # spend the remainder greedily on the highest-conviction affordable name
    changed = True
    while changed:
        changed = False
        for p in plan:  # picks are already score-sorted
            if 0 < p["price_base"] <= leftover + 1e-9:
                p["shares"] += 1
                p["amount_base"] += p["price_base"]
                leftover -= p["price_base"]
                changed = True
                break
    return [p for p in plan if p["shares"] > 0], leftover
