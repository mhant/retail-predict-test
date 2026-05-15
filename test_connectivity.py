"""
M1 Connectivity Test — comprehensive source survey.

Tests every potential data source and prints:
  - Whether the source is accessible from GitHub Actions
  - What data fields are available (critical for knowing what we can use)
  - Sample values so we can judge data quality

Reddit RSS field check is especially important — we need to confirm
whether upvotes/score are accessible without the JSON API.
"""
from __future__ import annotations

import json
import sys
import time
from typing import Any

import feedparser
import requests

_REDDIT_UA  = "retail-predict/1.0 (open-source research; github.com/mhant/retail-predict-test)"
_EDGAR_UA   = "retail-predict-research contact@retail-predict-research.com"
_TIMEOUT    = 20

results: list[dict] = []


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tag(status: str) -> str:
    return {"OK": "✅", "BLOCKED": "❌", "RATE_LIMITED": "⚠️",
            "ERROR": "❌", "EMPTY": "⚠️", "PARTIAL": "🟡"}.get(status, "?")


def check_rss(name: str, url: str, min_entries: int = 1,
              ua: str = _REDDIT_UA, inspect_fields: bool = False) -> bool:
    t0 = time.time()
    try:
        feed = feedparser.parse(url, agent=ua, request_headers={"User-Agent": ua})
        elapsed = round((time.time() - t0) * 1000)
        status = getattr(feed, "status", 200)
        if status in (403, 401):
            results.append({"source": name, "status": "BLOCKED", "ms": elapsed, "items": 0})
            print(f"  ❌ {name}: {status} Blocked ({elapsed}ms)")
            return False
        if status == 429:
            results.append({"source": name, "status": "RATE_LIMITED", "ms": elapsed, "items": 0})
            print(f"  ⚠️  {name}: 429 Rate limited ({elapsed}ms)")
            return False
        count = len(feed.entries)
        ok = count >= min_entries
        status_str = "OK" if ok else "EMPTY"
        results.append({"source": name, "status": status_str, "ms": elapsed, "items": count})
        print(f"  {_tag(status_str)} {name}: {count} entries in {elapsed}ms")

        if inspect_fields and feed.entries:
            e = feed.entries[0]
            all_keys = list(vars(e).keys()) if hasattr(e, '__dict__') else dir(e)
            useful = {k: getattr(e, k, None) for k in
                      ["title", "summary", "author", "published", "link", "id",
                       "score", "ups", "upvotes", "vote_count",
                       "media_thumbnail", "tags", "content"] if hasattr(e, k)}
            print(f"     Fields available: {sorted(useful.keys())}")
            for field, val in useful.items():
                preview = str(val)[:80].replace("\n", " ") if val else "—"
                print(f"       {field:20s}: {preview}")
            # Check for any Reddit-specific namespaced fields
            extra = [k for k in dir(e) if not k.startswith("_") and k not in
                     ["title","summary","author","published","link","id","content",
                      "tags","media_thumbnail","enclosures","authors","links",
                      "title_detail","summary_detail","author_detail","published_parsed",
                      "updated","updated_parsed","guidislink"]]
            if extra:
                print(f"     Extra fields: {extra}")
        return ok
    except Exception as exc:
        elapsed = round((time.time() - t0) * 1000)
        results.append({"source": name, "status": "ERROR", "ms": elapsed, "items": 0, "error": str(exc)})
        print(f"  ❌ {name}: {exc} ({elapsed}ms)")
        return False


def check_json(name: str, url: str, headers: dict[str, str],
               min_items: int = 1, item_path: list[str] | None = None,
               count_keys: bool = False, inspect: bool = False) -> bool:
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
            items = items.get(key, []) if isinstance(items, dict) else []
        count = len(items.keys()) if count_keys and isinstance(items, dict) else \
                len(items) if isinstance(items, list) else 1
        ok = count >= min_items
        status_str = "OK" if ok else "EMPTY"
        results.append({"source": name, "status": status_str, "ms": elapsed, "items": count})
        print(f"  {_tag(status_str)} {name}: {count} items in {elapsed}ms")
        if inspect and isinstance(data, dict):
            print(f"     Top-level keys: {list(data.keys())[:10]}")
        elif inspect and isinstance(data, list) and data:
            print(f"     First item keys: {list(data[0].keys())[:10] if isinstance(data[0], dict) else type(data[0])}")
        return ok
    except Exception as exc:
        elapsed = round((time.time() - t0) * 1000)
        results.append({"source": name, "status": "ERROR", "ms": elapsed, "items": 0, "error": str(exc)})
        print(f"  ❌ {name}: {exc} ({elapsed}ms)")
        return False


_json_headers   = {"User-Agent": _REDDIT_UA, "Accept": "application/json"}
_edgar_headers  = {"User-Agent": _EDGAR_UA,  "Accept": "application/json"}
_rss_headers    = {"User-Agent": _REDDIT_UA,  "Accept": "application/rss+xml, application/xml, text/xml"}


# ══════════════════════════════════════════════════════════════════════════════
# REDDIT
# ══════════════════════════════════════════════════════════════════════════════
print("\n═══ REDDIT ═══")

print("\n  ── RSS feeds (workaround) ──")
reddit_rss_ok = all([
    check_rss("r/wallstreetbets hot RSS", "https://www.reddit.com/r/wallstreetbets/hot.rss",   min_entries=5, inspect_fields=True),
    check_rss("r/stocks hot RSS",         "https://www.reddit.com/r/stocks/hot.rss",            min_entries=5),
    check_rss("r/options hot RSS",        "https://www.reddit.com/r/options/hot.rss",           min_entries=5),
    check_rss("r/pennystocks hot RSS",    "https://www.reddit.com/r/pennystocks/hot.rss",       min_entries=3),
    check_rss("r/Superstonk hot RSS",     "https://www.reddit.com/r/Superstonk/hot.rss",        min_entries=3),
    check_rss("r/investing hot RSS",      "https://www.reddit.com/r/investing/hot.rss",         min_entries=3),
    check_rss("r/thetagang hot RSS",      "https://www.reddit.com/r/thetagang/hot.rss",         min_entries=3),
])

print("\n  ── JSON API (previously blocked — retesting) ──")
check_json("r/wallstreetbets JSON",
           "https://www.reddit.com/r/wallstreetbets/hot.json?limit=5&raw_json=1",
           headers=_json_headers, min_items=1, item_path=["data", "children"], inspect=True)


# ══════════════════════════════════════════════════════════════════════════════
# FINANCIAL NEWS RSS
# ══════════════════════════════════════════════════════════════════════════════
print("\n═══ FINANCIAL NEWS RSS ═══")

check_rss("Google News — GME stock",
          "https://news.google.com/rss/search?q=GME+stock+short+squeeze&hl=en-US&gl=US&ceid=US:en",
          min_entries=3, inspect_fields=True)
check_rss("Google News — wallstreetbets",
          "https://news.google.com/rss/search?q=wallstreetbets+reddit&hl=en-US&gl=US&ceid=US:en",
          min_entries=3)
check_rss("Reuters Business RSS",
          "https://feeds.reuters.com/reuters/businessNews",
          min_entries=5, inspect_fields=True)
check_rss("CNBC Markets RSS",
          "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135",
          min_entries=3)
check_rss("Seeking Alpha — Markets",
          "https://seekingalpha.com/market_currents.xml",
          min_entries=3)
check_rss("Benzinga News RSS",
          "https://www.benzinga.com/feed/",
          min_entries=3, inspect_fields=True)
check_rss("MarketWatch RSS",
          "https://feeds.marketwatch.com/marketwatch/topstories/",
          min_entries=3)
check_rss("Motley Fool RSS",
          "https://www.fool.com/feeds/index.aspx",
          min_entries=3)
check_rss("Investopedia News RSS",
          "https://www.investopedia.com/feedbuilder/feed/getfeed/?feedName=rss_headline",
          min_entries=3)


# ══════════════════════════════════════════════════════════════════════════════
# STOCKTWITS + ALTERNATIVES
# ══════════════════════════════════════════════════════════════════════════════
print("\n═══ SOCIAL / SENTIMENT SOURCES ═══")

check_json("StockTwits AAPL stream",
           "https://api.stocktwits.com/api/2/streams/symbol/AAPL.json",
           headers={**_json_headers, "Referer": "https://stocktwits.com/"},
           min_items=1, item_path=["messages"])

# Unusual Whales public API (they have some public endpoints)
check_json("Unusual Whales — flow alerts",
           "https://phx.unusualwhales.com/api/alerts/options",
           headers=_json_headers, min_items=1, inspect=True)

# WallStreetMemes RSS or similar
check_rss("WallStreetBets Discord (none — placeholder)", "", min_entries=1)   # skip

# Substack newsletters
check_rss("Market Sentiment Substack",
          "https://marketsentiment.substack.com/feed",
          min_entries=1, ua=_REDDIT_UA)
check_rss("Kyla Scanlon Substack",
          "https://kylascanlon.substack.com/feed",
          min_entries=1)
check_rss("The Diff (Byrne Hobart)",
          "https://www.thediff.co/feed",
          min_entries=1)


# ══════════════════════════════════════════════════════════════════════════════
# SEC EDGAR
# ══════════════════════════════════════════════════════════════════════════════
print("\n═══ SEC EDGAR ═══")

# Company tickers — returns a dict, use count_keys
check_json("SEC EDGAR company tickers",
           "https://www.sec.gov/files/company_tickers.json",
           headers=_edgar_headers, min_items=1000, count_keys=True, inspect=True)

# Form 4 (insider trades) via EDGAR full-text search
check_json("SEC EDGAR Form 4 search",
           "https://efts.sec.gov/LATEST/search-index?q=%22form+4%22&forms=4&dateRange=custom&startdt=2025-01-01",
           headers=_edgar_headers, min_items=1, inspect=True)

# EDGAR RSS feed for Form 4 filings
check_rss("SEC EDGAR Form 4 RSS",
          "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4&dateb=&owner=include&count=40&search_text=&output=atom",
          min_entries=5, ua=_EDGAR_UA, inspect_fields=True)

# Company submissions API (AAPL = CIK 0000320193)
check_json("SEC EDGAR AAPL submissions",
           "https://data.sec.gov/submissions/CIK0000320193.json",
           headers=_edgar_headers, min_items=1, inspect=True)


# ══════════════════════════════════════════════════════════════════════════════
# YFINANCE (extended)
# ══════════════════════════════════════════════════════════════════════════════
print("\n═══ YFINANCE (extended) ═══")

try:
    import yfinance as yf
    ticker = yf.Ticker("GME")

    t0 = time.time()
    price = ticker.fast_info.last_price
    elapsed = round((time.time() - t0) * 1000)
    results.append({"source": "yFinance price", "status": "OK", "ms": elapsed, "items": 1})
    print(f"  ✅ yFinance GME price: ${price:.2f} in {elapsed}ms")

    t0 = time.time()
    news = ticker.news or []
    elapsed = round((time.time() - t0) * 1000)
    ok = len(news) > 0
    results.append({"source": "yFinance news", "status": "OK" if ok else "EMPTY", "ms": elapsed, "items": len(news)})
    print(f"  {'✅' if ok else '❌'} yFinance GME news: {len(news)} articles in {elapsed}ms")
    if news:
        print(f"     Sample news fields: {list(news[0].keys())}")

    t0 = time.time()
    try:
        holders = ticker.institutional_holders
        count = len(holders) if holders is not None else 0
        elapsed = round((time.time() - t0) * 1000)
        results.append({"source": "yFinance institutional holders", "status": "OK" if count > 0 else "EMPTY", "ms": elapsed, "items": count})
        print(f"  {'✅' if count > 0 else '⚠️'} yFinance GME institutional holders: {count} rows in {elapsed}ms")
    except Exception as exc:
        elapsed = round((time.time() - t0) * 1000)
        results.append({"source": "yFinance institutional holders", "status": "ERROR", "ms": elapsed, "items": 0})
        print(f"  ❌ yFinance institutional holders: {exc}")

    t0 = time.time()
    try:
        info = ticker.info
        short_pct = info.get("shortPercentOfFloat")
        elapsed = round((time.time() - t0) * 1000)
        results.append({"source": "yFinance short interest", "status": "OK" if short_pct else "EMPTY", "ms": elapsed, "items": 1})
        print(f"  {'✅' if short_pct else '⚠️'} yFinance GME short interest: {short_pct} in {elapsed}ms")
    except Exception as exc:
        elapsed = round((time.time() - t0) * 1000)
        results.append({"source": "yFinance short interest", "status": "ERROR", "ms": elapsed, "items": 0})
        print(f"  ❌ yFinance short interest: {exc}")

    t0 = time.time()
    try:
        opts = ticker.options
        elapsed = round((time.time() - t0) * 1000)
        results.append({"source": "yFinance options chain", "status": "OK" if opts else "EMPTY", "ms": elapsed, "items": len(opts)})
        print(f"  {'✅' if opts else '⚠️'} yFinance GME options dates: {len(opts)} expiries in {elapsed}ms")
    except Exception as exc:
        elapsed = round((time.time() - t0) * 1000)
        results.append({"source": "yFinance options chain", "status": "ERROR", "ms": elapsed, "items": 0})
        print(f"  ❌ yFinance options chain: {exc}")

except Exception as exc:
    print(f"  ❌ yFinance import failed: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# FINRA SHORT INTEREST
# ══════════════════════════════════════════════════════════════════════════════
print("\n═══ FINRA / SHORT INTEREST ═══")

check_json("FINRA short interest API",
           "https://regsho.finra.org/FNRAshortReportCurrentMonthlySummaryJson.json",
           headers=_json_headers, min_items=1, inspect=True)

check_rss("FINRA news RSS",
          "https://www.finra.org/rules-guidance/notices/rss",
          min_entries=1)


# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "═" * 60)
print("SUMMARY")
print("═" * 60)

total   = len([r for r in results if r["source"] != "WallStreetBets Discord (none — placeholder)"])
passed  = sum(1 for r in results if r["status"] == "OK")
blocked = sum(1 for r in results if r["status"] == "BLOCKED")
limited = sum(1 for r in results if r["status"] == "RATE_LIMITED")
partial = sum(1 for r in results if r["status"] in ("EMPTY", "PARTIAL"))
errors  = sum(1 for r in results if r["status"] == "ERROR")

print(f"\n  ✅ Accessible:    {passed}")
print(f"  ❌ Blocked:       {blocked}")
print(f"  ⚠️  Rate limited:  {limited}")
print(f"  🟡 Empty/partial: {partial}")
print(f"  ❌ Errors:        {errors}")
print(f"\n  {'Source':<40} {'Status':<14} {'Items':>6}  {'ms':>5}")
print(f"  {'-'*40} {'-'*14} {'-'*6}  {'-'*5}")
for r in results:
    if "placeholder" in r["source"]:
        continue
    icon = _tag(r["status"])
    print(f"  {icon} {r['source']:<40} {r['status']:<14} {r['items']:>6}  {r['ms']:>5}ms")

# Reddit RSS is critical; yFinance is critical
reddit_ok = any(r["status"] == "OK" and "wallstreetbets" in r["source"].lower() for r in results)
yf_ok = any(r["status"] == "OK" and "yFinance price" in r["source"] for r in results)

print()
if reddit_ok and yf_ok:
    print("✅ PASS — critical sources (Reddit RSS, yFinance) reachable from GitHub Actions.")
    print("   Review field availability above before proceeding to M2.")
else:
    print("❌ FAIL — critical sources not reachable.")
    sys.exit(1)
