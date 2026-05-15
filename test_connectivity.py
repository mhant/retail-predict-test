"""
M1 Connectivity Test — verifies all scraping targets are reachable from
GitHub Actions runner IPs before committing to the full migration.

Reports per-source: status, response time, item count, rate-limit signals.
Exit 0 = all critical sources passed. Exit 1 = failure.
"""
from __future__ import annotations

import sys
import time

import requests

_UA = "retail-predict-connectivity-test/1.0 (open-source research)"
_HEADERS = {"User-Agent": _UA, "Accept": "application/json"}
_TIMEOUT = 20

results: list[dict] = []


def check(name: str, url: str, min_items: int = 1, item_path: list[str] | None = None) -> bool:
    t0 = time.time()
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        elapsed = round((time.time() - t0) * 1000)
        if resp.status_code == 429:
            results.append({"source": name, "status": "RATE_LIMITED", "ms": elapsed, "items": 0})
            print(f"  ⚠️  {name}: 429 Rate Limited ({elapsed}ms)")
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


print("\n── Reddit (public JSON API) ──")
reddit_ok = all([
    check("r/wallstreetbets hot",
          "https://www.reddit.com/r/wallstreetbets/hot.json?limit=10&raw_json=1",
          min_items=5, item_path=["data", "children"]),
    check("r/stocks hot",
          "https://www.reddit.com/r/stocks/hot.json?limit=10&raw_json=1",
          min_items=5, item_path=["data", "children"]),
    check("r/options hot",
          "https://www.reddit.com/r/options/hot.json?limit=10&raw_json=1",
          min_items=5, item_path=["data", "children"]),
])

print("\n── StockTwits ──")
stocktwits_ok = check(
    "StockTwits AAPL stream",
    "https://api.stocktwits.com/api/2/streams/symbol/AAPL.json",
    min_items=1, item_path=["messages"],
)

print("\n── yFinance (via Yahoo Finance) ──")
try:
    import yfinance as yf
    t0 = time.time()
    info = yf.Ticker("AAPL").fast_info
    price = info.last_price
    elapsed = round((time.time() - t0) * 1000)
    yf_ok = price is not None and price > 0
    results.append({"source": "yFinance AAPL", "status": "OK" if yf_ok else "ERROR", "ms": elapsed, "items": 1})
    print(f"  {'✅' if yf_ok else '❌'} yFinance AAPL: ${price:.2f} in {elapsed}ms")
except Exception as exc:
    yf_ok = False
    results.append({"source": "yFinance AAPL", "status": "ERROR", "ms": 0, "error": str(exc)})
    print(f"  ❌ yFinance: {exc}")

print("\n── SEC EDGAR ──")
sec_ok = check(
    "SEC EDGAR company tickers",
    "https://www.sec.gov/files/company_tickers.json",
    min_items=100,
)

print("\n── Substack RSS ──")
try:
    import feedparser
    t0 = time.time()
    feed = feedparser.parse("https://marketsentiment.substack.com/feed")
    elapsed = round((time.time() - t0) * 1000)
    count = len(feed.entries)
    substack_ok = count > 0
    results.append({"source": "Substack RSS", "status": "OK" if substack_ok else "EMPTY", "ms": elapsed, "items": count})
    print(f"  {'✅' if substack_ok else '❌'} Substack RSS: {count} entries in {elapsed}ms")
except Exception as exc:
    substack_ok = False
    results.append({"source": "Substack RSS", "status": "ERROR", "ms": 0, "error": str(exc)})
    print(f"  ❌ Substack RSS: {exc}")

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n── Summary ──")
total = len(results)
passed = sum(1 for r in results if r["status"] == "OK")
rate_limited = sum(1 for r in results if r["status"] == "RATE_LIMITED")
errors = sum(1 for r in results if r["status"] in ("ERROR", "EMPTY"))
error_rate = round((total - passed) / total * 100, 1) if total else 0

print(f"  Passed:       {passed}/{total}")
print(f"  Rate limited: {rate_limited}")
print(f"  Errors:       {errors}")
print(f"  Error rate:   {error_rate}%  (target: <5%)")

critical_ok = reddit_ok and yf_ok
if not critical_ok:
    print("\nFAIL: critical sources (Reddit, yFinance) not reachable from this runner.")
    sys.exit(1)
if error_rate >= 5:
    print(f"\nFAIL: error rate {error_rate}% exceeds 5% threshold.")
    sys.exit(1)

print(f"\nPASS: all critical sources reachable, error rate {error_rate}% < 5%.")
sys.exit(0)
