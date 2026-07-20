"""
Data sources for Ledger — all via free, key-less endpoints.

  * Yahoo chart API      -> price + history (the backbone, very reliable)
  * Yahoo quoteSummary   -> analyst consensus & price targets (best effort)
  * Yahoo headline RSS    -> recent company news

Everything here runs on a bare Python install; if `curl_cffi` is available
(repo venv) it is used to impersonate a Chrome TLS fingerprint, which Yahoo
requires since mid-2026 — plain urllib gets HTTP 429 on every request.
"""

import json
import time
import urllib.request
import urllib.parse
import urllib.error
import http.cookiejar
import xml.etree.ElementTree as ET

try:
    from curl_cffi import requests as _curl
except ImportError:
    _curl = None

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _money(s):
    """Parse '$142,200,000' -> 142200000.0 (or None)."""
    if not s:
        return None
    try:
        return float(str(s).replace("$", "").replace(",", "").strip())
    except ValueError:
        return None


def _norm_ipo(r, kind):
    return {
        "symbol": (r.get("proposedTickerSymbol") or "").strip(),
        "company": (r.get("companyName") or "").strip(),
        "exchange": (r.get("proposedExchange") or "").strip(),
        "date": (r.get("expectedPriceDate") or r.get("pricedDate")
                 or r.get("filedDate") or "").strip(),
        "price": (r.get("proposedSharePrice") or "").strip(),
        "shares": (r.get("sharesOffered") or "").strip(),
        "value": (r.get("dollarValueOfSharesOffered") or "").strip(),
        "value_num": _money(r.get("dollarValueOfSharesOffered")),
        "kind": kind,
    }


class Yahoo:
    """A small session wrapper that carries cookies + a crumb for the
    authenticated quoteSummary endpoint, and retries on rate limiting."""

    def __init__(self, pause=0.6):
        self.pause = pause
        cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cj)
        )
        self.opener.addheaders = [("User-Agent", _UA)]
        self.sess = _curl.Session(impersonate="chrome") if _curl else None
        self.crumb = None

    # -- low level -------------------------------------------------------
    def _read(self, url_or_req, tries=3):
        """GET -> body bytes, preferring the Chrome-impersonating session."""
        if self.sess is None:
            with self._open(url_or_req, tries) as r:
                return r.read()
        if isinstance(url_or_req, urllib.request.Request):
            url = url_or_req.full_url
            headers = dict(url_or_req.header_items())
        else:
            url, headers = url_or_req, None
        last = None
        for i in range(tries):
            try:
                r = self.sess.get(url, headers=headers, timeout=12)
                if r.status_code in (429, 502, 503):
                    last = urllib.error.HTTPError(
                        url, r.status_code, "throttled", None, None)
                    if i < tries - 1:
                        time.sleep(1.0 + i)
                    continue
                if r.status_code >= 400:
                    raise urllib.error.HTTPError(
                        url, r.status_code, "error", None, None)
                return r.content
            except urllib.error.HTTPError:
                raise
            except Exception as e:  # transient network blips
                last = e
                if i < tries - 1:
                    time.sleep(0.8 + i)
        raise last

    def _open(self, url, tries=3):
        last = None
        for i in range(tries):
            try:
                return self.opener.open(url, timeout=12)
            except urllib.error.HTTPError as e:
                last = e
                if e.code in (429, 503, 502):
                    # back off, but fail fast on persistent throttling so a
                    # rate-limited run completes in seconds, not minutes
                    if i < tries - 1:
                        time.sleep(1.0 + i)
                    continue
                raise
            except Exception as e:  # transient network blips
                last = e
                if i < tries - 1:
                    time.sleep(0.8 + i)
        if last:
            raise last

    def _get_json(self, url_or_req):
        time.sleep(self.pause)
        return json.loads(self._read(url_or_req))

    def _ensure_crumb(self):
        if self.crumb:
            return self.crumb
        try:
            try:
                if self.sess is not None:
                    self.sess.get("https://fc.yahoo.com", timeout=10)
                else:
                    self.opener.open("https://fc.yahoo.com", timeout=10)
            except Exception:
                pass  # only here to plant the consent cookie
            crumb = self._read(
                "https://query2.finance.yahoo.com/v1/test/getcrumb"
            ).decode().strip()
            if crumb and "<" not in crumb:
                self.crumb = crumb
        except Exception:
            self.crumb = None
        return self.crumb

    # -- public ----------------------------------------------------------
    def history(self, symbol, rng="1y", interval="1d"):
        """Return dict with timestamps + closes + meta, or None."""
        url = (
            "https://query1.finance.yahoo.com/v8/finance/chart/"
            f"{urllib.parse.quote(symbol)}?range={rng}&interval={interval}"
        )
        try:
            d = self._get_json(url)
            res = d["chart"]["result"][0]
        except Exception:
            return None
        meta = res.get("meta", {})
        ts = res.get("timestamp", []) or []
        quote = (res.get("indicators", {}).get("quote") or [{}])[0]
        closes = quote.get("close") or []
        vols = quote.get("volume") or []
        # drop trailing None closes (today pre-open / holidays)
        rows = [
            (t, c, v)
            for t, c, v in zip(ts, closes, vols)
            if c is not None
        ]
        if not rows:
            return None
        return {
            "symbol": meta.get("symbol", symbol),
            "currency": meta.get("currency"),
            "exchange": meta.get("fullExchangeName"),
            "price": meta.get("regularMarketPrice"),
            "prev_close": meta.get("chartPreviousClose"),
            "timestamps": [r[0] for r in rows],
            "closes": [float(r[1]) for r in rows],
            "volumes": [r[2] for r in rows],
        }

    def analyst(self, symbol):
        """Analyst consensus & targets, best effort. Returns dict or {}."""
        crumb = self._ensure_crumb()
        if not crumb:
            return {}
        modules = "financialData,recommendationTrend,defaultKeyStatistics"
        url = (
            "https://query2.finance.yahoo.com/v10/finance/quoteSummary/"
            f"{urllib.parse.quote(symbol)}?modules={modules}"
            f"&crumb={urllib.parse.quote(crumb)}"
        )
        try:
            d = self._get_json(url)
            res = d["quoteSummary"]["result"][0]
        except Exception:
            return {}

        def raw(node, key):
            v = node.get(key)
            if isinstance(v, dict):
                return v.get("raw")
            return v

        fd = res.get("financialData", {}) or {}
        out = {
            "rec_mean": raw(fd, "recommendationMean"),
            "rec_key": fd.get("recommendationKey"),
            "target_mean": raw(fd, "targetMeanPrice"),
            "target_high": raw(fd, "targetHighPrice"),
            "target_low": raw(fd, "targetLowPrice"),
            "n_analysts": raw(fd, "numberOfAnalystOpinions"),
        }
        return out

    def fx(self, base, quote):
        """Spot FX rate base->quote (e.g. fx('USD','CHF')). 1.0 if equal."""
        if base == quote:
            return 1.0
        h = self.history(f"{base}{quote}=X", rng="5d", interval="1d")
        if h and h.get("price"):
            return h["price"]
        return None

    def ipo_calendar(self, months):
        """Upcoming + recently-priced IPOs from Nasdaq's public calendar.
        `months` is a list of 'YYYY-MM' strings. Key-less, best effort."""
        out = {"upcoming": [], "priced": []}
        seen = set()
        for ym in months:
            url = f"https://api.nasdaq.com/api/ipo/calendar?date={ym}"
            req = urllib.request.Request(url, headers={
                "User-Agent": _UA, "Accept": "application/json"})
            try:
                d = self._get_json(req)
            except Exception:
                continue
            data = d.get("data") or {}
            up = (((data.get("upcoming") or {}).get("upcomingTable") or {})
                  .get("rows") or [])
            pr = (data.get("priced") or {}).get("rows") or []
            for r in up:
                k = r.get("dealID") or r.get("proposedTickerSymbol")
                if k and k not in seen:
                    seen.add(k)
                    out["upcoming"].append(_norm_ipo(r, "upcoming"))
            for r in pr:
                k = r.get("dealID") or r.get("proposedTickerSymbol")
                if k and k not in seen:
                    seen.add(k)
                    out["priced"].append(_norm_ipo(r, "priced"))
        return out

    def news(self, symbol, limit=4):
        """Recent company headlines via Yahoo's RSS, newest first."""
        url = (
            "https://feeds.finance.yahoo.com/rss/2.0/headline?s="
            f"{urllib.parse.quote(symbol)}&region=US&lang=en-US"
        )
        try:
            time.sleep(self.pause)
            root = ET.fromstring(self._read(url))
        except Exception:
            return []
        items = []
        for it in root.iter("item"):
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            pub = (it.findtext("pubDate") or "").strip()
            src = (it.findtext("source") or "").strip()
            if title and link:
                items.append(
                    {"title": title, "link": link, "pubDate": pub, "source": src}
                )
            if len(items) >= limit:
                break
        return items
