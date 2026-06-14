"""Offline, deterministic data source for `generate.py demo`.

Produces plausible synthetic price history / analyst views / news so you can see
a full set of issues without any network or rate-limit. IPO data is pulled live
from Nasdaq when reachable (it's a different host that isn't throttled), and
falls back to a synthetic list otherwise.

Everything here is SYNTHETIC and clearly labelled in the output — it exists to
demonstrate layout and mechanics, not to inform any real decision.
"""

import time
import zlib
import random


def _seed(s):
    return zlib.crc32(s.encode("utf-8")) & 0xFFFFFFFF


def _currency(symbol):
    if symbol.endswith(".SW"):
        return "CHF"
    if symbol.split(".")[-1] in ("AS", "DE", "PA", "HE", "ST", "MI", "BR"):
        return "EUR"
    return "USD"


def _rec_key(mean):
    if mean < 1.8:
        return "strong_buy"
    if mean < 2.5:
        return "buy"
    if mean < 3.2:
        return "hold"
    if mean < 4.0:
        return "underperform"
    return "sell"


class SyntheticSource:
    """Mimics the slice of the Yahoo interface generate.py uses. `as_of_offset`
    drops the last N days so seeded historical snapshots evolve over time."""

    def __init__(self, as_of_offset=0):
        self.offset = max(0, int(as_of_offset))
        self.pause = 0.0
        self.prices = {}

    # realistic anchor levels for benchmarks so market context reads plausibly
    _BASES = {"^GSPC": 6000, "^IXIC": 19500, "^VIX": 15, "^TNX": 43,
              "XLK": 260, "SMH": 310, "IGV": 340}

    # -- prices ----------------------------------------------------------
    def history(self, symbol, rng="1y", interval="1d"):
        r = random.Random(_seed(symbol))
        n = 260
        closes = []
        if symbol in self._BASES:
            # mean-reverting around a realistic level (keeps the VIX a VIX, an
            # index an index) rather than an unbounded random walk
            base = self._BASES[symbol]
            p = base
            vol = 0.035 if symbol == "^VIX" else 0.008
            for _ in range(n):
                p += (base - p) * 0.05 + p * r.gauss(0, vol)
                closes.append(max(0.5, p))
        else:
            drift = (r.random() - 0.35) * 0.0016   # slight positive bias, some negative
            vol = 0.010 + r.random() * 0.022
            p = 20 + r.random() * 400
            for _ in range(n):
                p *= (1 + drift + r.gauss(0, vol))
                closes.append(max(1.0, p))
        if self.offset:
            cut = max(40, n - self.offset)
            closes = closes[:cut]
        price = closes[-1]
        self.prices[symbol] = price
        now = int(time.time())
        ts = [now - (len(closes) - 1 - i) * 86400 for i in range(len(closes))]
        return {
            "symbol": symbol, "currency": _currency(symbol),
            "exchange": "DEMO", "price": round(price, 2),
            "prev_close": round(closes[-2], 2) if len(closes) > 1 else price,
            "timestamps": ts,
            "closes": [round(c, 4) for c in closes],
            "volumes": [1_000_000 + (i % 50) * 10_000 for i in range(len(closes))],
        }

    # -- analyst ---------------------------------------------------------
    def analyst(self, symbol):
        r = random.Random(_seed(symbol + "|a"))
        mean = round(1.6 + r.random() * 2.6, 2)
        price = self.prices.get(symbol) or (20 + r.random() * 400)
        factor = (r.random() - 0.32) * 0.5          # roughly -16%..+34% to target
        target = price * (1 + factor)
        return {
            "rec_mean": mean, "rec_key": _rec_key(mean),
            "target_mean": round(target, 2),
            "target_high": round(target * 1.18, 2),
            "target_low": round(target * 0.82, 2),
            "n_analysts": 8 + (_seed(symbol) % 35),
        }

    # -- fx --------------------------------------------------------------
    def fx(self, base, quote):
        if base == quote:
            return 1.0
        rates = {("USD", "CHF"): 0.885, ("EUR", "CHF"): 0.958,
                 ("GBP", "CHF"): 1.12, ("CHF", "USD"): 1.13,
                 ("CHF", "EUR"): 1.044, ("USD", "EUR"): 0.92,
                 ("EUR", "USD"): 1.087}
        return rates.get((base, quote), 1.0)

    # -- news ------------------------------------------------------------
    def news(self, symbol, limit=4):
        templates = [
            ("Analysts revisit {s} guidance ahead of earnings", "Reuters"),
            ("{s} extends move as sector rotation continues", "CNBC"),
            ("What the latest {s} numbers mean for the AI trade", "MarketWatch"),
        ]
        r = random.Random(_seed(symbol + "|n"))
        out = []
        for i in range(min(limit, 2)):
            t, src = templates[(_seed(symbol) + i) % len(templates)]
            out.append({"title": "[demo] " + t.format(s=symbol),
                        "link": "https://example.com/demo",
                        "source": src, "pubDate": "", "ticker": symbol})
        return out

    # -- ipos (real if reachable, else synthetic) ------------------------
    def ipo_calendar(self, months):
        try:
            from lib.sources import Yahoo
            data = Yahoo(pause=0.3).ipo_calendar(months)
            if data["upcoming"] or data["priced"]:
                return data
        except Exception:
            pass
        demo = [
            ("ACME", "Acme Robotics, Inc.", "NASDAQ Global Select",
             "expectedPriceDate", "6/20/2026", "18.00-20.00", "$480,000,000"),
            ("NOVA", "Nova Compute Holdings", "NYSE",
             "expectedPriceDate", "6/24/2026", "30.00-34.00", "$1,200,000,000"),
            ("BYTE", "Bytewave AI Corp.", "NASDAQ Global",
             "pricedDate", "6/09/2026", "22.00", "$640,000,000"),
        ]
        out = {"upcoming": [], "priced": []}
        for sym, co, exch, datekey, date, price, val in demo:
            row = {"proposedTickerSymbol": sym, "companyName": co,
                   "proposedExchange": exch, datekey: date,
                   "proposedSharePrice": price, "sharesOffered": "—",
                   "dollarValueOfSharesOffered": val, "dealID": sym}
            from lib.sources import _norm_ipo
            kind = "upcoming" if datekey == "expectedPriceDate" else "priced"
            out[kind].append(_norm_ipo(row, kind))
        return out
