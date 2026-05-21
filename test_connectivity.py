"""
M1 Connectivity Test — approved sources only.

Sources tested: Mastodon, Bluesky, StockTwits, RSS feeds, yFinance, SEC EDGAR.
Reddit and PullPush removed: Reddit prohibits scraping for commercial/ML use
(Responsible Builder Policy, May 2026); PullPush ToS restricts to authorized
Reddit agents only.
"""
from __future__ import annotations

import sys
import time
from typing import Any

import feedparser
import requests

_BOT_UA   = "retail-predict-bot/1.0 (+https://github.com/mhant/retail-predict-test)"
_EDGAR_UA = "retail-predict-research contact@retail-predict-research.com"
_TIMEOUT  = 20
results: list[dict] = []


def _tag(s: str) -> str:
    return {"OK": "✅", "BLOCKED": "❌", "RATE_LIMITED": "⚠️", "ERROR": "❌", "EMPTY": "⚠️"}.get(s, "?")


def check_json(name: str, url: str, headers: dict, min_items: int = 1,
               item_path: list[str] | None = None) -> bool:
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
        return ok
    except Exception as exc:
        elapsed = round((time.time() - t0) * 1000)
        results.append({"source": name, "status": "ERROR", "ms": elapsed, "items": 0})
        print(f"  ❌ {name}: {exc} ({elapsed}ms)")
        return False


def check_rss(name: str, url: str, min_entries: int = 1, ua: str = _BOT_UA) -> bool:
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
        return ok
    except Exception as exc:
        elapsed = round((time.time() - t0) * 1000)
        results.append({"source": name, "status": "ERROR", "ms": elapsed, "items": 0})
        print(f"  ❌ {name}: {exc} ({elapsed}ms)")
        return False


_jh = {"User-Agent": _BOT_UA,   "Accept": "application/json"}
_eh = {"User-Agent": _EDGAR_UA, "Accept": "application/json"}


# ══════════════════════════════════════════════════════════════════════════════
# SOCIAL — Mastodon, Bluesky, StockTwits
# ══════════════════════════════════════════════════════════════════════════════
print("\n═══ SOCIAL SOURCES ═══")

check_json("Mastodon #investing",
           "https://mastodon.social/api/v1/timelines/tag/investing?limit=20",
           headers=_jh, min_items=1)

check_json("Mastodon #stocks",
           "https://mastodon.social/api/v1/timelines/tag/stocks?limit=20",
           headers=_jh, min_items=1)

check_json("Bluesky $GME search",
           "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts?q=%24GME&limit=10",
           headers=_jh, min_items=1, item_path=["posts"])

check_json("StockTwits TSLA stream",
           "https://api.stocktwits.com/api/2/streams/symbol/TSLA.json",
           headers=_jh, min_items=1, item_path=["messages"])


# ══════════════════════════════════════════════════════════════════════════════
# NEWS RSS
# ══════════════════════════════════════════════════════════════════════════════
print("\n═══ NEWS RSS ═══")

check_rss("CNBC Markets",
          "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135",
          min_entries=5)

check_rss("CNBC Finance",
          "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664",
          min_entries=5)

check_rss("Seeking Alpha Markets",
          "https://seekingalpha.com/market_currents.xml",
          min_entries=3)

check_rss("Yahoo Finance",
          "https://finance.yahoo.com/news/rssindex",
          min_entries=5)

check_rss("Benzinga",
          "https://www.benzinga.com/feed",
          min_entries=3)


# ══════════════════════════════════════════════════════════════════════════════
# YFINANCE
# ══════════════════════════════════════════════════════════════════════════════
print("\n═══ YFINANCE ═══")

try:
    import yfinance as yf

    for sym, label in [("GME", "GME"), ("NVDA", "NVDA"), ("AAPL", "AAPL")]:
        t0 = time.time()
        price = yf.Ticker(sym).fast_info.last_price
        elapsed = round((time.time() - t0) * 1000)
        results.append({"source": f"yFinance price {sym}", "status": "OK", "ms": elapsed, "items": 1})
        print(f"  ✅ yFinance {label}: ${price:.2f} in {elapsed}ms")

    t0 = time.time()
    gme_news = yf.Ticker("GME").news or []
    elapsed = round((time.time() - t0) * 1000)
    ok = len(gme_news) > 0
    results.append({"source": "yFinance news", "status": "OK" if ok else "EMPTY", "ms": elapsed, "items": len(gme_news)})
    print(f"  {'✅' if ok else '⚠️'} yFinance GME news: {len(gme_news)} articles in {elapsed}ms")

except Exception as exc:
    print(f"  ❌ yFinance error: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# SEC EDGAR
# ══════════════════════════════════════════════════════════════════════════════
print("\n═══ SEC EDGAR ═══")

check_rss("SEC EDGAR Form 4 RSS",
          "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4"
          "&dateb=&owner=include&count=40&search_text=&output=atom",
          min_entries=10, ua=_EDGAR_UA)


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
print(f"\n  {'Source':<40} {'Status':<12} {'Items':>6}  {'ms':>6}")
print(f"  {'-'*40} {'-'*12} {'-'*6}  {'-'*6}")
for r in results:
    print(f"  {_tag(r['status'])} {r['source']:<40} {r['status']:<12} {r['items']:>6}  {r['ms']:>5}ms")

mastodon_ok = any(r["status"] == "OK" and "Mastodon" in r["source"] for r in results)
rss_ok      = any(r["status"] == "OK" and r["source"].startswith("CNBC") for r in results)
yf_ok       = any(r["status"] == "OK" and "yFinance price" in r["source"] for r in results)

print(f"\n  Mastodon social:      {'✅' if mastodon_ok else '❌'}")
print(f"  RSS news feeds:       {'✅' if rss_ok else '❌'}")
print(f"  yFinance market data: {'✅' if yf_ok else '❌'}")

if not (rss_ok and yf_ok):
    print("\nFAIL: critical sources (RSS news, yFinance) not reachable.")
    sys.exit(1)

print("\n✅ M1 COMPLETE — critical sources reachable.")
sys.exit(0)
