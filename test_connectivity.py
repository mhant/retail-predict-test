"""
M1 Connectivity Test — comprehensive source survey v3.

New in this version:
  - PullPush.io (Pushshift replacement) — Reddit data WITH upvote scores
  - Arctic Shift — another Reddit archive WITH scores
  - Google News per-ticker (sample: GME, NVDA, AAPL)
  - Google News broad topics (wallstreetbets, short squeeze, retail investors)
  - old.reddit.com JSON (same block check as www)
  - Reddit i.reddit.com mobile endpoint (different subdomain — might not be blocked)

Key question: can we get Reddit upvote scores from an unblocked endpoint?
"""
from __future__ import annotations

import sys
import time
from typing import Any

import feedparser
import requests

_REDDIT_UA = "retail-predict/1.0 (open-source research; github.com/mhant/retail-predict-test)"
_EDGAR_UA  = "retail-predict-research contact@retail-predict-research.com"
_TIMEOUT   = 20

results: list[dict] = []


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
            useful = {k: getattr(e, k, None) for k in
                      ["title", "summary", "author", "published", "link", "id",
                       "score", "ups", "upvotes", "vote_count", "tags", "content"]
                      if hasattr(e, k)}
            print(f"     Fields: {sorted(useful.keys())}")
            for field, val in useful.items():
                preview = str(val)[:100].replace("\n", " ") if val else "—"
                print(f"       {field:20s}: {preview}")
        return ok
    except Exception as exc:
        elapsed = round((time.time() - t0) * 1000)
        results.append({"source": name, "status": "ERROR", "ms": elapsed, "items": 0})
        print(f"  ❌ {name}: {exc} ({elapsed}ms)")
        return False


def check_json(name: str, url: str, headers: dict,
               min_items: int = 1, item_path: list[str] | None = None,
               count_keys: bool = False, inspect: bool = False,
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
            items = items.get(key, []) if isinstance(items, dict) else []
        count = len(items.keys()) if count_keys and isinstance(items, dict) else \
                len(items) if isinstance(items, list) else 1
        ok = count >= min_items
        status_str = "OK" if ok else "EMPTY"
        results.append({"source": name, "status": status_str, "ms": elapsed, "items": count})
        print(f"  {_tag(status_str)} {name}: {count} items in {elapsed}ms")
        if inspect:
            if isinstance(items, list) and items and isinstance(items[0], dict):
                print(f"     Fields in first item: {sorted(items[0].keys())}")
                # Check for upvote-related fields
                for sf in (score_fields or ["score", "ups", "upvotes", "likes"]):
                    if sf in items[0]:
                        print(f"     ✅ UPVOTE FIELD FOUND: '{sf}' = {items[0][sf]}")
            elif isinstance(items, dict):
                print(f"     Top-level keys: {list(items.keys())[:8]}")
        return ok
    except Exception as exc:
        elapsed = round((time.time() - t0) * 1000)
        results.append({"source": name, "status": "ERROR", "ms": elapsed, "items": 0})
        print(f"  ❌ {name}: {exc} ({elapsed}ms)")
        return False


_jh  = {"User-Agent": _REDDIT_UA, "Accept": "application/json"}
_eh  = {"User-Agent": _EDGAR_UA,  "Accept": "application/json"}


# ══════════════════════════════════════════════════════════════════════════════
# REDDIT — can we get upvotes from anywhere?
# ══════════════════════════════════════════════════════════════════════════════
print("\n═══ REDDIT — UPVOTE SOURCES ═══")
print("\n  ── Pushshift / Reddit archives (include scores) ──")

# PullPush.io — a Pushshift.io replacement
check_json("PullPush.io wallstreetbets",
           "https://api.pullpush.io/reddit/search/submission/"
           "?subreddit=wallstreetbets&size=10&sort=score&sort_type=desc",
           headers=_jh, min_items=1, inspect=True,
           score_fields=["score", "ups", "upvotes"])

check_json("PullPush.io stocks",
           "https://api.pullpush.io/reddit/search/submission/"
           "?subreddit=stocks&size=10&sort=score&sort_type=desc",
           headers=_jh, min_items=1, inspect=False)

# Arctic Shift — another Reddit data archive
check_json("Arctic Shift wallstreetbets",
           "https://arctic-shift.quadratic-labs.de/api/posts"
           "?subreddit=wallstreetbets&limit=10&sort=score",
           headers=_jh, min_items=1, inspect=True,
           score_fields=["score", "ups", "upvotes"])

# Reddit mobile endpoint (different subdomain — may not be on blocklist)
print("\n  ── Reddit alternative subdomains ──")
check_json("Reddit i.reddit.com (mobile)",
           "https://i.reddit.com/r/wallstreetbets/hot.json?limit=5&raw_json=1",
           headers={**_jh, "User-Agent": "Reddit/Version 2024.10.0/iOS"},
           min_items=1, item_path=["data", "children"], inspect=True,
           score_fields=["score", "ups"])

check_json("Reddit old.reddit.com",
           "https://old.reddit.com/r/wallstreetbets/hot.json?limit=5&raw_json=1",
           headers=_jh, min_items=1, item_path=["data", "children"], inspect=True,
           score_fields=["score", "ups"])

print("\n  ── Reddit RSS (confirmed working — field check) ──")
check_rss("r/wallstreetbets hot RSS",
          "https://www.reddit.com/r/wallstreetbets/hot.rss",
          min_entries=5, inspect_fields=True)
check_rss("r/wallstreetbets new RSS",
          "https://www.reddit.com/r/wallstreetbets/new.rss",
          min_entries=5)


# ══════════════════════════════════════════════════════════════════════════════
# GOOGLE NEWS — per-ticker + broad topics
# ══════════════════════════════════════════════════════════════════════════════
print("\n═══ GOOGLE NEWS ═══")

_GN = "https://news.google.com/rss/search?hl=en-US&gl=US&ceid=US:en&q="

print("\n  ── Per-ticker (sample: top retail-discussed stocks) ──")
sample_tickers = [("GME", "GameStop"), ("AMC", "AMC"), ("NVDA", "NVIDIA"),
                  ("TSLA", "Tesla"), ("AAPL", "Apple")]
ticker_results = {}
for ticker, name in sample_tickers:
    ok = check_rss(
        f"Google News: {ticker}",
        f"{_GN}{ticker}+stock+buy+sell+short",
        min_entries=3, inspect_fields=(ticker == "GME"),
    )
    ticker_results[ticker] = ok

print("\n  ── Broad topic searches ──")
check_rss("Google News: wallstreetbets",
          f"{_GN}wallstreetbets+reddit+stock",
          min_entries=5)
check_rss("Google News: short squeeze",
          f"{_GN}short+squeeze+retail+investors",
          min_entries=5)
check_rss("Google News: meme stocks",
          f"{_GN}meme+stocks+retail+trading",
          min_entries=3)
check_rss("Google News: options unusual activity",
          f"{_GN}unusual+options+activity+stock",
          min_entries=3)


# ══════════════════════════════════════════════════════════════════════════════
# FINANCIAL NEWS RSS (confirmed from last run)
# ══════════════════════════════════════════════════════════════════════════════
print("\n═══ FINANCIAL NEWS RSS ═══")
check_rss("CNBC Markets RSS",      "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135", min_entries=3)
check_rss("MarketWatch RSS",       "https://feeds.marketwatch.com/marketwatch/topstories/", min_entries=3)
check_rss("Motley Fool RSS",       "https://www.fool.com/feeds/index.aspx",                 min_entries=5)
check_rss("Seeking Alpha Markets", "https://seekingalpha.com/market_currents.xml",          min_entries=3)


# ══════════════════════════════════════════════════════════════════════════════
# YFINANCE + SEC EDGAR (confirmed — quick recheck)
# ══════════════════════════════════════════════════════════════════════════════
print("\n═══ YFINANCE + SEC EDGAR ═══")
try:
    import yfinance as yf
    for ticker in ["GME", "NVDA"]:
        t0 = time.time()
        p = yf.Ticker(ticker).fast_info.last_price
        elapsed = round((time.time() - t0) * 1000)
        results.append({"source": f"yFinance {ticker}", "status": "OK", "ms": elapsed, "items": 1})
        print(f"  ✅ yFinance {ticker}: ${p:.2f} in {elapsed}ms")
except Exception as exc:
    print(f"  ❌ yFinance: {exc}")

check_rss("SEC EDGAR Form 4 RSS",
          "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4"
          "&dateb=&owner=include&count=40&search_text=&output=atom",
          min_entries=5, ua=_EDGAR_UA)


# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "═" * 64)
print("SUMMARY")
print("═" * 64)
real = [r for r in results if r["items"] != 0 or r["status"] != "EMPTY" or "placeholder" not in r["source"]]
passed  = sum(1 for r in real if r["status"] == "OK")
blocked = sum(1 for r in real if r["status"] == "BLOCKED")
limited = sum(1 for r in real if r["status"] == "RATE_LIMITED")
empty   = sum(1 for r in real if r["status"] == "EMPTY")
errors  = sum(1 for r in real if r["status"] == "ERROR")

print(f"\n  ✅ Accessible:    {passed}")
print(f"  ❌ Blocked:       {blocked}")
print(f"  ⚠️  Rate limited:  {limited}")
print(f"  🟡 Empty:         {empty}")
print(f"  ❌ Errors:        {errors}")
print(f"\n  {'Source':<45} {'Status':<14} {'Items':>6}  {'ms':>6}")
print(f"  {'-'*45} {'-'*14} {'-'*6}  {'-'*6}")
for r in real:
    print(f"  {_tag(r['status'])} {r['source']:<45} {r['status']:<14} {r['items']:>6}  {r['ms']:>5}ms")

reddit_rss_ok  = any(r["status"] == "OK" and "wallstreetbets hot RSS" in r["source"] for r in results)
yfinance_ok    = any(r["status"] == "OK" and "yFinance" in r["source"] for r in results)
pullpush_ok    = any(r["status"] == "OK" and "PullPush" in r["source"] for r in results)
arctic_ok      = any(r["status"] == "OK" and "Arctic" in r["source"] for r in results)
google_news_ok = any(r["status"] == "OK" and "Google News" in r["source"] for r in results)

print(f"\n  Reddit RSS (no scores):  {'✅' if reddit_rss_ok else '❌'}")
print(f"  PullPush (with scores):  {'✅ UPVOTES AVAILABLE' if pullpush_ok else '❌ blocked/down'}")
print(f"  Arctic Shift (scores):   {'✅ UPVOTES AVAILABLE' if arctic_ok else '❌ blocked/down'}")
print(f"  Google News per-ticker:  {'✅' if google_news_ok else '❌'}")
print(f"  yFinance:                {'✅' if yfinance_ok else '❌'}")

if not (reddit_rss_ok and yfinance_ok):
    print("\nFAIL: critical sources not reachable.")
    sys.exit(1)

print("\nPASS — check upvote source results above to decide on weighting strategy.")
sys.exit(0)
