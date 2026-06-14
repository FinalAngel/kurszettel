"""Pure-Python technical indicators computed from a list of closing prices.

Lists are ordered oldest -> newest. Functions return None when there is
not enough data rather than raising, so a short-history ticker degrades
gracefully instead of breaking the whole run.
"""


def sma(closes, n):
    if len(closes) < n:
        return None
    return sum(closes[-n:]) / n


def pct_change(closes, n):
    """Percent return over the last n bars (n bars back -> now)."""
    if len(closes) <= n:
        return None
    past = closes[-(n + 1)]
    if past == 0:
        return None
    return (closes[-1] / past - 1.0) * 100.0


def rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = 0.0, 0.0
    for i in range(-period, 0):
        diff = closes[i] - closes[i - 1]
        if diff >= 0:
            gains += diff
        else:
            losses -= diff
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _ema(values, n):
    if len(values) < n:
        return None
    k = 2.0 / (n + 1)
    ema = sum(values[:n]) / n
    for v in values[n:]:
        ema = v * k + ema * (1 - k)
    return ema


def macd_hist(closes, fast=12, slow=26, signal=9):
    """Return the MACD histogram (MACD line - signal line) latest value."""
    if len(closes) < slow + signal:
        return None
    macd_line = []
    for i in range(slow, len(closes) + 1):
        window = closes[:i]
        ef = _ema(window, fast)
        es = _ema(window, slow)
        if ef is None or es is None:
            continue
        macd_line.append(ef - es)
    if len(macd_line) < signal:
        return None
    sig = _ema(macd_line, signal)
    if sig is None:
        return None
    return macd_line[-1] - sig


def high_low_position(closes, lookback=252):
    """Where the latest price sits in its 52-week range, as 0..100."""
    window = closes[-lookback:] if len(closes) >= lookback else closes
    hi, lo = max(window), min(window)
    if hi == lo:
        return 50.0
    return (closes[-1] - lo) / (hi - lo) * 100.0


def volatility(closes, lookback=63):
    """Annualised volatility (%) from recent daily returns."""
    w = closes[-(lookback + 1):]
    if len(w) < 12:
        return None
    rets = [w[i] / w[i - 1] - 1.0 for i in range(1, len(w)) if w[i - 1]]
    if len(rets) < 8:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return (var ** 0.5) * (252 ** 0.5) * 100.0


def max_drawdown(closes, lookback=252):
    """Worst peak-to-trough decline (%) over the window, as a negative number."""
    w = closes[-lookback:] if len(closes) >= lookback else closes
    if len(w) < 2:
        return None
    peak, mdd = w[0], 0.0
    for p in w:
        peak = max(peak, p)
        if peak:
            mdd = min(mdd, p / peak - 1.0)
    return mdd * 100.0


def metrics(closes):
    """Bundle the indicators we use into one dict."""
    return {
        "price": closes[-1],
        "sma50": sma(closes, 50),
        "sma200": sma(closes, 200),
        "rsi": rsi(closes, 14),
        "macd_hist": macd_hist(closes),
        "ret_1d": pct_change(closes, 1),
        "ret_1w": pct_change(closes, 5),
        "ret_1m": pct_change(closes, 21),
        "ret_3m": pct_change(closes, 63),
        "range_pos": high_low_position(closes),
        "volatility": volatility(closes),
        "max_drawdown": max_drawdown(closes),
    }
