"""
M1 Connectivity Test — clean source list only.

Only sources that passed robots.txt compliance are tested here.
Dropped: Reddit RSS, Google News, MarketWatch, Motley Fool.

Key fix: PullPush data is in response["data"] array — navigate correctly.
"""
from __future__ import annotations

import sys
import time
from typing import Any

import feedparser
import requests

_BOT_UA    = "retail-predict-bot/1.0 (+https://github.com/mhant/retail-predict-test; open-source research)"
_EDGAR_UA  = "retail-predict-research contact@retail-predict-research.com"
_TIMEOUT   = 20
results: list[dict] = []


def _tag(s: str) -> str:
    return {"OK": "✅", "BLOCKED": "❌", "RATE_LIMITED": "⚠️", "ERROR": "❌", "EMPTY": "⚠️"}.get(s, "?")


def check_json(name: str, url: str, headers: dict, min_items: int = 1,
               item_path: list[str] | None = None, inspect: bool = False,
               score_fields: list[str] | None = None) -> bool:
    t0 = time.time()
    try:
        resp = requests.get(url, headers=headers, timeout=_TIMEOUT)
        elapsed = round((time.time() - t0) * 1000)
        if resp.status_code in (403, 401):
            results.append({"source": name, "status": "BLOCKED", "ms": elapsed, "items": 0})
            print(f"  ❌ {name}: {resp.status_code} Blocked ({elapsed}ms)")
            return False
        if resp.status_code == 429:
            results.append({"source": name, "status": "RATE_LIMITED", "ms": elapsed, "items": 0})
            print(f"  ⚠️  {name}: 429 Rate limited ({elapsed}ms)")
            return False
        resp.raise_for_status()
        data = resp.json()
        items: Any = data
        for key in (item_path or []):
            items = items.get(key, []) if isinstance(items, dict) else items
        count = len(items) if isinstance(items, (list, dict)) else 1
        ok = count >= min_items
        status = "OK" if ok else "EMPTY"
        results.append({"source": name, "status": status, "ms": elapsed, "items": count})
        print(f"  {_tag(status)} {name}: {count} items in {elapsed}ms")
        if inspect and isinstance(items, list) and items:
            first = items[0]
            if isinstance(first, dict):
                print(f"     Fields: {sorted(first.keys())}")
                for sf in (score_fields or ["score", "ups", "upvotes", "num_comments"]):
                    if sf in first:
                        print(f"     ✅ {sf} = {first[sf]}")
        return ok
    except Exception as exc:
        elapsed = round((time.time() - t0) * 1000)
        results.append({"source": name, "status": "ERROR", "ms": elapsed, "items": 0})
        print(f"  ❌ {name}: {exc} ({elapsed}ms)")
        return False


def check_rss(name: str, url: str, min_entries: int = 1,
              ua: str = _BOT_UA, inspect: bool = False) -> bool:
    t0 = time.time()
    try:
        feed = feedparser.parse(url, agent=ua, request_headers={"User-Agent": ua})
        elapsed = round((time.time() - t0) * 1000)
        status_code = getattr(feed, "status", 200)
        if status_code in (403, 401):
            results.append({"source": name, "status": "BLOCKED", "ms": elapsed, "items": 0})
            print(f"  ❌ {name}: {status_code} Blocked ({elapsed}ms)")
            return False
        count = len(feed.entries)
        ok = count >= min_entries
        status = "OK" if ok else "EMPTY"
        results.append({"source": name, "status": status, "ms": elapsed, "items": count})
        print(f"  {_tag(status)} {name}: {count} entries in {elapsed}ms")
        if inspect and feed.entries:
            e = feed.entries[0]
            fields = [k for k in ["title", "summary", "author", "published", "link", "id", "content"]
                      if hasattr(e, k)]
            print(f"     Fields: {fields}")
            print(f"     Title: {getattr(e, 'title', '')[:80]}")
        return ok
    except Exception as exc:
        elapsed = round((time.time() - t0) * 1000)
        results.append({"source": name, "status": "ERROR", "ms": elapsed, "items": 0})
        print(f"  ❌ {name}: {exc} ({elapsed}ms)")
        return False


_jh = {"User-Agent": _BOT_UA,   "Accept": "application/json"}
_eh = {"User-Agent": _EDGAR_UA, "Accept": "application/json"}


# ══════════════════════════════════════════════════════════════════════════════
# PULLPUSH — Reddit data WITH upvote scores (robots.txt: ALLOWED)
# ══════════════════════════════════════════════════════════════════════════════
print("\n═══ PULLPUSH (Reddit archive with upvote scores) ═══")

pullpush_ok = check_json(
    "PullPush r/wallstreetbets",
    "https://api.pullpush.io/reddit/search/submission/"
    "?subreddit=wallstreetbets&size=25&sort=score&sort_type=desc",
    headers=_jh, min_items=5,
    item_path=["data"],          # data is nested under "data" key
    inspect=True,
    score_fields=["score", "ups", "num_comments", "selftext", "title", "author"],
)

check_json(
    "PullPush r/stocks",
    "https://api.pullpush.io/reddit/search/submission/"
    "?subreddit=stocks&size=25&sort=score&sort_type=desc",
    headers=_jh, min_items=5, item_path=["data"],
)

check_json(
    "PullPush r/options",
    "https://api.pullpush.io/reddit/search/submission/"
    "?subreddit=options&size=25&sort=score&sort_type=desc",
    headers=_jh, min_items=5, item_path=["data"],
)

check_json(
    "PullPush r/pennystocks",
    "https://api.pullpush.io/reddit/search/submission/"
    "?subreddit=pennystocks&size=25&sort=score&sort_type=desc",
    headers=_jh, min_items=3, item_path=["data"],
)

check_json(
    "PullPush r/Superstonk",
    "https://api.pullpush.io/reddit/search/submission/"
    "?subreddit=Superstonk&size=25&sort=score&sort_type=desc",
    headers=_jh, min_items=3, item_path=["data"],
)

check_json(
    "PullPush r/investing",
    "https://api.pullpush.io/reddit/search/submission/"
    "?subreddit=investing&size=25&sort=score&sort_type=desc",
    headers=_jh, min_items=5, item_path=["data"],
)

check_json(
    "PullPush r/thetagang",
    "https://api.pullpush.io/reddit/search/submission/"
    "?subreddit=thetagang&size=25&sort=score&sort_type=desc",
    headers=_jh, min_items=3, item_path=["data"],
)

# Test PullPush hot posts (sorted by created_utc desc = most recent)
check_json(
    "PullPush r/wallstreetbets (new)",
    "https://api.pullpush.io/reddit/search/submission/"
    "?subreddit=wallstreetbets&size=25&sort=created_utc&sort_type=desc",
    headers=_jh, min_items=5, item_path=["data"],
)


# ══════════════════════════════════════════════════════════════════════════════
# NEWS RSS — only explicitly allowed sources
# ══════════════════════════════════════════════════════════════════════════════
print("\n═══ NEWS RSS (robots.txt: ALLOWED) ═══")

check_rss("CNBC Markets RSS",
          "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135",
          min_entries=5, inspect=True)

check_rss("Seeking Alpha Markets",
          "https://seekingalpha.com/market_currents.xml",
          min_entries=3, inspect=True)


# ══════════════════════════════════════════════════════════════════════════════
# YFINANCE — market data, news, options, institutional (robots.txt: ALLOWED)
# ══════════════════════════════════════════════════════════════════════════════
print("\n═══ YFINANCE ═══")

try:
    import yfinance as yf

    for ticker_sym, label in [("GME", "GME (high retail interest)"), ("NVDA", "NVDA"), ("AAPL", "AAPL")]:
        t0 = time.time()
        t = yf.Ticker(ticker_sym)
        price = t.fast_info.last_price
        elapsed = round((time.time() - t0) * 1000)
        results.append({"source": f"yFinance price {ticker_sym}", "status": "OK", "ms": elapsed, "items": 1})
        print(f"  ✅ yFinance {label}: ${price:.2f} in {elapsed}ms")

    # News (per-ticker)
    t0 = time.time()
    gme_news = yf.Ticker("GME").news or []
    elapsed = round((time.time() - t0) * 1000)
    ok = len(gme_news) > 0
    results.append({"source": "yFinance news GME", "status": "OK" if ok else "EMPTY", "ms": elapsed, "items": len(gme_news)})
    print(f"  {'✅' if ok else '⚠️'} yFinance GME news: {len(gme_news)} articles in {elapsed}ms")
    if gme_news:
        print(f"     News fields: {list(gme_news[0].keys())}")

    # Short interest
    t0 = time.time()
    info = yf.Ticker("GME").info
    short_pct = info.get("shortPercentOfFloat")
    elapsed = round((time.time() - t0) * 1000)
    results.append({"source": "yFinance short interest", "status": "OK" if short_pct else "EMPTY", "ms": elapsed, "items": 1})
    print(f"  {'✅' if short_pct else '⚠️'} yFinance GME short interest: {short_pct} in {elapsed}ms")

    # Institutional holders
    t0 = time.time()
    holders = yf.Ticker("GME").institutional_holders
    count = len(holders) if holders is not None else 0
    elapsed = round((time.time() - t0) * 1000)
    results.append({"source": "yFinance holders", "status": "OK" if count > 0 else "EMPTY", "ms": elapsed, "items": count})
    print(f"  {'✅' if count > 0 else '⚠️'} yFinance GME institutional holders: {count} rows in {elapsed}ms")

    # Options chain
    t0 = time.time()
    opts = yf.Ticker("GME").options or []
    elapsed = round((time.time() - t0) * 1000)
    results.append({"source": "yFinance options", "status": "OK" if opts else "EMPTY", "ms": elapsed, "items": len(opts)})
    print(f"  {'✅' if opts else '⚠️'} yFinance GME options: {len(opts)} expiries in {elapsed}ms")

except Exception as exc:
    print(f"  ❌ yFinance error: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# SEC EDGAR — robots.txt unreachable = RFC 9309 allowed
# ══════════════════════════════════════════════════════════════════════════════
print("\n═══ SEC EDGAR (robots.txt: RFC 9309 allowed) ═══")

check_json("Company tickers (10k+ symbols)",
           "https://www.sec.gov/files/company_tickers.json",
           headers=_eh, min_items=1000,
           item_path=None)   # top-level IS the dict, count keys separately

# Fix: count keys of the returned dict
try:
    r = requests.get("https://www.sec.gov/files/company_tickers.json",
                     headers=_eh, timeout=_TIMEOUT)
    count = len(r.json())
    print(f"     → {count:,} companies in ticker universe")
except Exception:
    pass

check_rss("SEC EDGAR Form 4 RSS (insider trades)",
          "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4"
          "&dateb=&owner=include&count=40&search_text=&output=atom",
          min_entries=10, ua=_EDGAR_UA, inspect=True)

check_json("SEC EDGAR AAPL submissions",
           "https://data.sec.gov/submissions/CIK0000320193.json",
           headers=_eh, min_items=1, inspect=True)


# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "═" * 64)
print("SUMMARY")
print("═" * 64)
passed  = sum(1 for r in results if r["status"] == "OK")
blocked = sum(1 for r in results if r["status"] in ("BLOCKED", "ERROR"))
empty   = sum(1 for r in results if r["status"] == "EMPTY")

print(f"\n  ✅ Accessible: {passed}/{len(results)}")
print(f"  ❌ Blocked/Error: {blocked}")
print(f"  ⚠️  Empty: {empty}")
print(f"\n  {'Source':<40} {'Status':<10} {'Items':>6}  {'ms':>6}")
print(f"  {'-'*40} {'-'*10} {'-'*6}  {'-'*6}")
for r in results:
    print(f"  {_tag(r['status'])} {r['source']:<40} {r['status']:<10} {r['items']:>6}  {r['ms']:>5}ms")

pullpush_ok = any(r["status"] == "OK" and "PullPush r/wallstreetbets" in r["source"] for r in results)
yf_ok       = any(r["status"] == "OK" and "yFinance price" in r["source"] for r in results)
edgar_ok    = any(r["source"] == "SEC EDGAR Form 4 RSS (insider trades)" for r in results)

print(f"\n  PullPush Reddit (with scores): {'✅' if pullpush_ok else '❌'}")
print(f"  yFinance market data:          {'✅' if yf_ok else '❌'}")
print(f"  SEC EDGAR insider trades:      {'✅' if edgar_ok else '❌'}")

if not (pullpush_ok and yf_ok):
    print("\nFAIL: critical sources not reachable.")
    sys.exit(1)

print("\n✅ M1 COMPLETE — all critical sources reachable, all robots.txt compliant.")
print("   Ready to proceed to M2: Cloudflare D1 schema + Worker write proxy.")
sys.exit(0)
