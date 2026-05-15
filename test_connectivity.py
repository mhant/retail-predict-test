"""
M1 Connectivity Test — workaround edition.

Changes from first run:
  - Reddit: switched from public JSON API (403'd) to RSS feeds via feedparser
  - SEC EDGAR: fixed User-Agent to their required "Name email" format
  - StockTwits: JSON API 403'd — testing alternative public endpoints
  - Substack: retry with correct User-Agent
  - yFinance: was already passing ✅

Exit 0 = all critical sources passed (<5% error rate).
Exit 1 = critical failure.
"""
from __future__ import annotations

import sys
import time

import feedparser
import requests

# SEC EDGAR explicitly requires this User-Agent format or they block you
_EDGAR_UA = "retail-predict-research contact@retail-predict-research.com"
_REDDIT_UA = "retail-predict/1.0 (open-source research scraper; see github.com/mhant)"
_TIMEOUT = 20

results: list[dict] = []


def _check_rss(name: str, url: str, min_entries: int = 1, ua: str = _REDDIT_UA) -> bool:
    """Fetch an RSS/Atom feed via feedparser and check entry count."""
    t0 = time.time()
    try:
        feed = feedparser.parse(url, agent=ua, request_headers={"User-Agent": ua})
        elapsed = round((time.time() - t0) * 1000)
        # feedparser doesn't raise on 403 — check status code
        status = getattr(feed, "status", 200)
        if status == 403:
            results.append({"source": name, "status": "BLOCKED", "ms": elapsed, "items": 0})
            print(f"  ❌ {name}: 403 Blocked ({elapsed}ms)")
            return False
        if status == 429:
            results.append({"source": name, "status": "RATE_LIMITED", "ms": elapsed, "items": 0})
            print(f"  ⚠️  {name}: 429 Rate limited ({elapsed}ms)")
            return False
        count = len(feed.entries)
        ok = count >= min_entries
        results.append({"source": name, "status": "OK" if ok else "EMPTY", "ms": elapsed, "items": count})
        print(f"  {'✅' if ok else '❌'} {name}: {count} entries in {elapsed}ms")
        return ok
    except Exception as exc:
        elapsed = round((time.time() - t0) * 1000)
        results.append({"source": name, "status": "ERROR", "ms": elapsed, "items": 0, "error": str(exc)})
        print(f"  ❌ {name}: {exc} ({elapsed}ms)")
        return False


def _check_json(name: str, url: str, headers: dict, min_items: int = 1,
                item_path: list[str] | None = None) -> bool:
    """Fetch a JSON endpoint and check item count."""
    t0 = time.time()
    try:
        resp = requests.get(url, headers=headers, timeout=_TIMEOUT)
        elapsed = round((time.time() - t0) * 1000)
        if resp.status_code == 403:
            results.append({"source": name, "status": "BLOCKED", "ms": elapsed, "items": 0})
            print(f"  ❌ {name}: 403 Blocked ({elapsed}ms)")
            return False
        if resp.status_code == 429:
            results.append({"source": name, "status": "RATE_LIMITED", "ms": elapsed, "items": 0})
            print(f"  ⚠️  {name}: 429 Rate limited ({elapsed}ms)")
            return False
        resp.raise_for_status()
        data = resp.json()
        items = data
        for key in (item_path or []):
            items = items.get(key, []) if isinstance(items, dict) else []
        count = len(items) if isinstance(items, list) else 1
        ok = count >= min_items
        results.append({"source": name, "status": "OK" if ok else "EMPTY", "ms": elapsed, "items": count})
        print(f"  {'✅' if ok else '❌'} {name}: {count} items in {elapsed}ms")
        return ok
    except Exception as exc:
        elapsed = round((time.time() - t0) * 1000)
        results.append({"source": name, "status": "ERROR", "ms": elapsed, "items": 0, "error": str(exc)})
        print(f"  ❌ {name}: {exc} ({elapsed}ms)")
        return False


# ── Reddit RSS (workaround for JSON 403) ─────────────────────────────────────
print("\n── Reddit (RSS feeds) ──")
reddit_ok = all([
    _check_rss("r/wallstreetbets RSS", "https://www.reddit.com/r/wallstreetbets/.rss", min_entries=5),
    _check_rss("r/stocks RSS",         "https://www.reddit.com/r/stocks/.rss",         min_entries=5),
    _check_rss("r/options RSS",        "https://www.reddit.com/r/options/.rss",         min_entries=5),
    _check_rss("r/pennystocks RSS",    "https://www.reddit.com/r/pennystocks/.rss",     min_entries=3),
    _check_rss("r/Superstonk RSS",     "https://www.reddit.com/r/Superstonk/.rss",      min_entries=3),
])

# ── StockTwits (trying symbol stream with explicit headers) ───────────────────
print("\n── StockTwits ──")
_st_headers = {
    "User-Agent": _REDDIT_UA,
    "Accept": "application/json",
    "Referer": "https://stocktwits.com/",
}
stocktwits_ok = _check_json(
    "StockTwits AAPL stream",
    "https://api.stocktwits.com/api/2/streams/symbol/AAPL.json",
    headers=_st_headers,
    min_items=1,
    item_path=["messages"],
)

# ── yFinance ──────────────────────────────────────────────────────────────────
print("\n── yFinance ──")
try:
    import yfinance as yf
    t0 = time.time()
    price = yf.Ticker("AAPL").fast_info.last_price
    elapsed = round((time.time() - t0) * 1000)
    yf_ok = price is not None and price > 0
    results.append({"source": "yFinance AAPL", "status": "OK" if yf_ok else "ERROR", "ms": elapsed, "items": 1})
    print(f"  {'✅' if yf_ok else '❌'} yFinance AAPL: ${price:.2f} in {elapsed}ms")
except Exception as exc:
    yf_ok = False
    results.append({"source": "yFinance AAPL", "status": "ERROR", "ms": 0, "error": str(exc)})
    print(f"  ❌ yFinance: {exc}")

# ── SEC EDGAR (fixed User-Agent) ──────────────────────────────────────────────
print("\n── SEC EDGAR (fixed User-Agent) ──")
sec_ok = _check_json(
    "SEC EDGAR company tickers",
    "https://www.sec.gov/files/company_tickers.json",
    headers={"User-Agent": _EDGAR_UA, "Accept": "application/json"},
    min_items=100,
)

# ── Substack RSS ──────────────────────────────────────────────────────────────
print("\n── Substack RSS ──")
substack_ok = all([
    _check_rss("Market Sentiment RSS", "https://marketsentiment.substack.com/feed", min_entries=1),
    _check_rss("Chartr RSS",           "https://chartr.substack.com/feed",           min_entries=1),
])

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n── Summary ──")
total = len(results)
passed  = sum(1 for r in results if r["status"] == "OK")
blocked = sum(1 for r in results if r["status"] == "BLOCKED")
limited = sum(1 for r in results if r["status"] == "RATE_LIMITED")
errors  = sum(1 for r in results if r["status"] in ("ERROR", "EMPTY"))
error_rate = round((total - passed) / total * 100, 1) if total else 0

print(f"  Passed:       {passed}/{total}")
print(f"  Blocked:      {blocked}")
print(f"  Rate limited: {limited}")
print(f"  Errors/empty: {errors}")
print(f"  Error rate:   {error_rate}%  (target: <5%)")
print()

# Show per-source detail
for r in results:
    status_icon = {"OK": "✅", "BLOCKED": "❌", "RATE_LIMITED": "⚠️", "ERROR": "❌", "EMPTY": "⚠️"}.get(r["status"], "?")
    print(f"  {status_icon} {r['source']:35s} {r['status']:12s} {r['items']:4d} items  {r['ms']}ms")

print()
critical_ok = reddit_ok and yf_ok
if not critical_ok:
    print("FAIL: critical sources (Reddit RSS, yFinance) not reachable.")
    sys.exit(1)
if error_rate >= 5:
    print(f"FAIL: error rate {error_rate}% exceeds 5% threshold.")
    sys.exit(1)

print(f"PASS: critical sources reachable, error rate {error_rate}% < 5%.")
if not stocktwits_ok:
    print("NOTE: StockTwits blocked — will need alternative or skip.")
sys.exit(0)
