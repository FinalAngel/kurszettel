"""Turn raw metrics + analyst data into a single composite score and a
plain-English verdict.

The score is a transparent, weighted blend of four lenses:

  trend     (30) — is price above its own moving averages? golden cross?
  momentum  (30) — RSI, MACD, and medium-term return
  analyst   (25) — Wall-Street consensus rating and upside to mean target
  position  (15) — where it sits in the 52-week range (room to run vs. extended)

Each lens yields 0..1, weighted and summed to a 0..100 score. This is a
mechanical, rules-based reading — not advice. It is meant to focus
attention, and every number that drives it is shown to the reader.

The lens weights and verdict thresholds are *tunable parameters*. They have
safe defaults below (so behaviour is fixed out of the box), but if a
`weights.json` exists at the repo root, its values override the defaults.
That file is what the self-improvement loop (improve.py) writes when it finds,
by back-testing past signals against realised returns, a parameter set that
predicts forward returns better — and only ever after the tests stay green.
"""

import os
import json

# -- tunable defaults --------------------------------------------------
DEFAULT_WEIGHTS = {
    # relative weight of each lens in the composite score
    "lenses": {"trend": 30.0, "momentum": 30.0, "analyst": 25.0, "position": 15.0},
    # score cut-offs for the verdict bands, high -> low
    "thresholds": {"BUY": 72.0, "ACCUMULATE": 58.0, "HOLD": 45.0, "REDUCE": 32.0},
}

_WEIGHTS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "weights.json"
)
_cache = {"mtime": None, "weights": None}


def _merge(base, over):
    out = {k: dict(v) if isinstance(v, dict) else v for k, v in base.items()}
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


def load_weights(path=None):
    """Load tuned weights from weights.json, falling back to defaults.
    Cached on file mtime so repeated calls in one run are cheap."""
    p = path or _WEIGHTS_PATH
    try:
        mt = os.path.getmtime(p)
    except OSError:
        return _merge(DEFAULT_WEIGHTS, None)
    if _cache["mtime"] != mt:
        try:
            with open(p, encoding="utf-8") as f:
                _cache["weights"] = _merge(DEFAULT_WEIGHTS, json.load(f))
            _cache["mtime"] = mt
        except Exception:
            return _merge(DEFAULT_WEIGHTS, None)
    return _cache["weights"]


def verdict_bands(weights=None):
    w = weights or load_weights()
    t = w["thresholds"]
    return [
        (t["BUY"], "BUY"),
        (t["ACCUMULATE"], "ACCUMULATE"),
        (t["HOLD"], "HOLD"),
        (t["REDUCE"], "REDUCE"),
        (0.0, "SELL"),
    ]


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def _trend_score(m):
    price, s50, s200 = m["price"], m["sma50"], m["sma200"]
    pts, parts = 0.0, 0
    if s50 is not None:
        pts += 1.0 if price > s50 else 0.0
        parts += 1
    if s200 is not None:
        pts += 1.0 if price > s200 else 0.0
        parts += 1
    if s50 is not None and s200 is not None:
        pts += 1.0 if s50 > s200 else 0.0  # golden vs death cross
        parts += 1
    return (pts / parts) if parts else 0.5


def _momentum_score(m):
    sub, w = 0.0, 0.0
    rsi = m["rsi"]
    if rsi is not None:
        # reward healthy 50–70 momentum, fade overbought >70 and weak <40
        if rsi >= 70:
            s = 0.55
        elif rsi >= 55:
            s = 0.9
        elif rsi >= 45:
            s = 0.6
        elif rsi >= 35:
            s = 0.35
        else:
            s = 0.2
        sub += s * 0.4
        w += 0.4
    if m["macd_hist"] is not None:
        sub += (1.0 if m["macd_hist"] > 0 else 0.25) * 0.3
        w += 0.3
    if m["ret_1m"] is not None:
        sub += _clamp(0.5 + m["ret_1m"] / 20.0) * 0.3
        w += 0.3
    return (sub / w) if w else 0.5


def _analyst_score(m, a):
    parts, w = 0.0, 0.0
    rec = a.get("rec_mean")
    if rec is not None:
        # Yahoo scale: 1 strong buy .. 5 sell -> map to 1..0
        parts += _clamp((5.0 - rec) / 4.0) * 0.6
        w += 0.6
    tgt, price = a.get("target_mean"), m["price"]
    if tgt and price:
        upside = (tgt / price - 1.0) * 100.0
        parts += _clamp(0.5 + upside / 40.0) * 0.4
        w += 0.4
    return (parts / w) if w else None  # None => no analyst coverage


def _position_score(m):
    rp = m["range_pos"]
    if rp is None:
        return 0.5
    # mid/upper range is constructive; the very top is extended, the very
    # bottom is falling-knife territory.
    if rp >= 92:
        return 0.55
    if rp >= 55:
        return 0.85
    if rp >= 35:
        return 0.6
    if rp >= 15:
        return 0.4
    return 0.25


def score(m, a, weights=None):
    lw = (weights or load_weights())["lenses"]
    lenses = {
        "trend": (_trend_score(m), lw["trend"]),
        "momentum": (_momentum_score(m), lw["momentum"]),
        "position": (_position_score(m), lw["position"]),
    }
    an = _analyst_score(m, a)
    if an is not None:
        lenses["analyst"] = (an, lw["analyst"])
    total_w = sum(w for _, w in lenses.values())
    raw = sum(v * w for v, w in lenses.values())
    sc = raw / total_w * 100.0 if total_w else 50.0
    return round(sc, 1), {k: round(v * 100) for k, (v, _) in lenses.items()}


def verdict(sc, weights=None):
    for threshold, label in verdict_bands(weights):
        if sc >= threshold:
            return label
    return "SELL"


def rationale(m, a, breakdown):
    """A short, readable explanation of the verdict."""
    bits = []
    price, s50, s200 = m["price"], m["sma50"], m["sma200"]
    if s50 and s200:
        if price > s50 > s200:
            bits.append("uptrend (above rising 50/200-day)")
        elif price < s50 < s200:
            bits.append("downtrend (below 50/200-day)")
        elif price > s200:
            bits.append("above 200-day, mixed short term")
        else:
            bits.append("below 200-day")
    rsi = m["rsi"]
    if rsi is not None:
        if rsi >= 70:
            bits.append(f"overbought (RSI {rsi:.0f})")
        elif rsi <= 35:
            bits.append(f"oversold (RSI {rsi:.0f})")
        else:
            bits.append(f"RSI {rsi:.0f}")
    if m["ret_1m"] is not None:
        bits.append(f"{m['ret_1m']:+.1f}% 1-mo")
    rec, tgt = a.get("rec_key"), a.get("target_mean")
    if rec:
        label = rec.replace("_", " ")
        if tgt and m["price"]:
            up = (tgt / m["price"] - 1.0) * 100.0
            bits.append(f"analysts: {label}, {up:+.0f}% to target")
        else:
            bits.append(f"analysts: {label}")
    return "; ".join(bits)
