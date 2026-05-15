"""
M3 scraper pipeline — runs in GitHub Actions on an hourly schedule.

Flow:
  1. PullPush Reddit  → raw_mentions (with VADER scores + upvote data)
  2. Ticker sentiment → ticker_sentiment_summary (pre-aggregated for fast reads)
  3. yFinance         → price_snapshots + institutional_data
  4. CNBC / SA RSS   → news_articles
  5. SEC EDGAR        → insider_trades
  6. Record           → pipeline_runs + scraper_events (invalid/delisted tickers)
"""
from __future__ import annotations

import logging
import re
import sys
import time
import warnings
from collections import Counter, defaultdict

import feedparser
import requests
import yfinance as yf
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from scraper import config
from scraper import d1_client as d1

# Suppress yfinance's noisy stderr warnings — we log them to D1 instead
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
warnings.filterwarnings("ignore", category=UserWarning, module="yfinance")

# ── VADER setup ────────────────────────────────────────────────────────────────
_vader = SentimentIntensityAnalyzer()
_vader.lexicon.update(config.FINANCE_LEXICON)

# ── HTTP session for PullPush + news ──────────────────────────────────────────
_BOT_UA    = "retail-predict-bot/1.0 (+https://github.com/mhant/retail-predict-test)"
_EDGAR_UA  = "retail-predict-research contact@retail-predict-research.com"
_session   = requests.Session()
_session.headers["User-Agent"] = _BOT_UA

# ── Ticker extraction ──────────────────────────────────────────────────────────
_CASHTAG_RE = re.compile(r"\$([A-Z]{1,5})\b")
_CAPS_RE    = re.compile(r"\b([A-Z]{2,5})\b")


def extract_tickers(text: str) -> list[str]:
    """
    Three-stage ticker extraction:
      1. Cashtag regex ($GME) — highest precision, always trusted
      2. ALL-CAPS words filtered against watchlist — moderate precision
      3. Company name lookup (case-insensitive) gated by financial context words —
         catches "tesla stock" / "gamestop shares" without matching "I ate an apple"
    """
    if not text:
        return []
    found: dict[str, int] = {}

    # Stage 1: cashtags
    for m in _CASHTAG_RE.finditer(text):
        sym = m.group(1)
        if sym not in found:
            found[sym] = m.start()

    # Stage 2: ALL-CAPS watchlist words
    for m in _CAPS_RE.finditer(text):
        sym = m.group(1)
        if sym in found or sym in config.STOPWORDS:
            continue
        if sym in config.WATCHLIST:
            found[sym] = m.start()

    # Stage 3: company name matching — only when financial context is present
    lower = text.lower()
    if any(w in lower for w in config.FINANCIAL_CONTEXT):
        for name, ticker in config.NAME_TO_TICKER.items():
            if ticker in found:
                continue
            pos = lower.find(name)
            if pos == -1:
                continue
            # Whole-word check: character before and after must not be alpha
            before_ok = (pos == 0 or not lower[pos - 1].isalpha())
            after_ok  = (pos + len(name) >= len(lower) or not lower[pos + len(name)].isalpha())
            if before_ok and after_ok:
                found[ticker] = pos

    return [s for s, _ in sorted(found.items(), key=lambda x: x[1])]


# ── PullPush scraper ───────────────────────────────────────────────────────────

def _fetch_pullpush(subreddit: str, sort: str, size: int = 25) -> list[dict]:
    """Fetch posts from PullPush Reddit archive."""
    url = (
        f"https://api.pullpush.io/reddit/search/submission/"
        f"?subreddit={subreddit}&size={size}&sort={sort}&sort_type=desc"
    )
    try:
        resp = _session.get(url, timeout=20)
        resp.raise_for_status()
        return resp.json().get("data", [])
    except Exception as exc:
        print(f"  [pullpush] {subreddit}/{sort}: {exc}")
        return []


def scrape_reddit() -> list[dict]:
    """Scrape all subreddits (top-scored + most-recent). Returns mention rows ready for D1."""
    now = time.time()
    mention_rows: list[dict] = []

    for sub in config.SUBREDDITS:
        for sort in ("score", "created_utc"):
            posts = _fetch_pullpush(sub, sort, config.POSTS_PER_SUBREDDIT)
            time.sleep(0.4)   # polite delay

            for post in posts:
                full_text = f"{post.get('title', '')} {post.get('selftext', '')}".strip()
                tickers = extract_tickers(full_text)
                if not tickers:
                    continue

                scores = _vader.polarity_scores(full_text[:2000])

                for ticker in tickers:
                    mention_rows.append({
                        "source":        "pullpush_reddit",
                        "source_id":     post.get("id", ""),
                        "subreddit":     sub,
                        "ticker":        ticker,
                        "title":         post.get("title", "")[:500],
                        "selftext":      post.get("selftext", "")[:2000],
                        "author":        post.get("author", ""),
                        "score":         int(post.get("score", 0)),
                        "ups":           int(post.get("ups", 0)),
                        "upvote_ratio":  float(post.get("upvote_ratio", 0)),
                        "num_comments":  int(post.get("num_comments", 0)),
                        "url":           f"https://reddit.com{post.get('permalink', '')}",
                        "created_utc":   float(post.get("created_utc", now)),
                        "scraped_utc":   now,
                        "vader_compound": scores["compound"],
                        "vader_positive": scores["pos"],
                        "vader_negative": scores["neg"],
                        "vader_neutral":  scores["neu"],
                    })

        print(f"  [reddit] {sub}: scraped both sorts")

    # Deduplicate by (source_id, ticker) — Worker uses INSERT OR IGNORE but cheaper to dedup first
    seen: set[tuple] = set()
    unique: list[dict] = []
    for row in mention_rows:
        key = (row["source_id"], row["ticker"])
        if key not in seen:
            seen.add(key)
            unique.append(row)

    print(f"  [reddit] {len(unique)} unique mention rows from {len(config.SUBREDDITS)} subreddits")
    return unique


# ── Ticker sentiment summary ───────────────────────────────────────────────────

def compute_sentiment_summary(mentions: list[dict]) -> list[dict]:
    """Pre-aggregate sentiment per ticker from this batch (24h window)."""
    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for m in mentions:
        by_ticker[m["ticker"]].append(m)

    summaries: list[dict] = []
    now = time.time()

    for ticker, rows in by_ticker.items():
        sentiments = [r["vader_compound"] for r in rows if r.get("vader_compound") is not None]
        if not sentiments:
            continue
        scores  = [r["score"] for r in rows]
        ratios  = [r["upvote_ratio"] for r in rows if r.get("upvote_ratio")]

        # Upvote-weighted sentiment: weight each post by log(1 + score)
        import math
        weights  = [math.log1p(max(s, 0)) for s in scores]
        total_w  = sum(weights) or 1.0
        wt_sent  = sum(s * w for s, w in zip(sentiments, weights)) / total_w

        top_post = max(rows, key=lambda r: r["score"])

        summaries.append({
            "ticker":                    ticker,
            "window_hours":              24,
            "computed_at":               now,
            "mention_count":             len(rows),
            "avg_sentiment":             sum(sentiments) / len(sentiments),
            "upvote_weighted_sentiment": wt_sent,
            "avg_upvote_ratio":          sum(ratios) / len(ratios) if ratios else None,
            "source_count":              len({r["subreddit"] for r in rows}),
            "top_title":                 top_post.get("title", "")[:200],
        })

    return summaries


# ── Market data (yFinance) ─────────────────────────────────────────────────────

def fetch_market_data(
    tickers: list[str], pipeline_started_at: float
) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Returns (price_snapshot_rows, institutional_data_rows, scraper_event_rows).
    Invalid/delisted tickers are logged to scraper_events instead of printing warnings.
    """
    price_rows:   list[dict] = []
    inst_rows:    list[dict] = []
    event_rows:   list[dict] = []
    today = time.strftime("%Y-%m-%d")
    now   = time.time()

    for ticker in tickers:
        try:
            t    = yf.Ticker(ticker)
            hist = t.history(period="7d", interval="1d", auto_adjust=True)

            if hist.empty:
                event_rows.append({
                    "event_type":          "ticker_not_found",
                    "ticker":              ticker,
                    "detail":              "yfinance returned empty history (possibly delisted)",
                    "pipeline_started_at": pipeline_started_at,
                    "occurred_at":         now,
                })
                continue

            for ts, row in hist.iterrows():
                price_rows.append({
                    "ticker":   ticker,
                    "interval": "1d",
                    "ts":       ts.timestamp(),
                    "open":     float(row["Open"])   if row["Open"]   else None,
                    "high":     float(row["High"])   if row["High"]   else None,
                    "low":      float(row["Low"])    if row["Low"]    else None,
                    "close":    float(row["Close"])  if row["Close"]  else None,
                    "volume":   int(row["Volume"])   if row["Volume"] else None,
                })

            inst_row: dict = {"ticker": ticker, "report_date": today}
            try:
                full_info = t.info
                inst_row.update({
                    "short_interest_pct":          full_info.get("shortPercentOfFloat"),
                    "short_ratio":                 full_info.get("shortRatio"),
                    "institutional_ownership_pct": full_info.get("institutionsPercentHeld"),
                })
            except Exception:
                pass
            inst_rows.append(inst_row)

            time.sleep(0.3)

        except Exception as exc:
            detail = str(exc)[:300]
            event_type = "delisted" if "delisted" in detail.lower() else "parse_error"
            event_rows.append({
                "event_type":          event_type,
                "ticker":              ticker,
                "detail":              detail,
                "pipeline_started_at": pipeline_started_at,
                "occurred_at":         now,
            })

    print(f"  [yfinance] {len(price_rows)} price rows, {len(inst_rows)} ok, {len(event_rows)} skipped")
    if event_rows:
        skipped = [e["ticker"] for e in event_rows]
        print(f"  [yfinance] skipped tickers: {skipped}")

    return price_rows, inst_rows, event_rows


# ── News RSS (CNBC + Seeking Alpha) ───────────────────────────────────────────

def fetch_news() -> list[dict]:
    """Fetch news from allowed RSS sources."""
    news_rows: list[dict] = []
    now = time.time()

    sources = [
        ("cnbc",          "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135"),
        ("seeking_alpha", "https://seekingalpha.com/market_currents.xml"),
    ]

    for source, url in sources:
        try:
            feed = feedparser.parse(url, agent=_BOT_UA, request_headers={"User-Agent": _BOT_UA})
            for entry in feed.entries:
                article_id = getattr(entry, "id", getattr(entry, "link", ""))
                title      = getattr(entry, "title", "")
                # Try to extract a ticker from the headline
                tickers = extract_tickers(title)
                news_rows.append({
                    "source":       source,
                    "article_id":   article_id[:200],
                    "ticker":       tickers[0] if tickers else None,
                    "title":        title[:400],
                    "summary":      getattr(entry, "summary", "")[:500],
                    "url":          getattr(entry, "link", "")[:500],
                    "published_utc": now,
                    "scraped_utc":  now,
                })
            print(f"  [news] {source}: {len(feed.entries)} articles")
        except Exception as exc:
            print(f"  [news] {source}: {exc}")

    return news_rows


# ── SEC EDGAR Form 4 (insider trades) ─────────────────────────────────────────

def fetch_insider_trades() -> list[dict]:
    """Fetch recent Form 4 filings from SEC EDGAR RSS."""
    rows: list[dict] = []
    now  = time.time()
    url  = (
        "https://www.sec.gov/cgi-bin/browse-edgar"
        "?action=getcurrent&type=4&dateb=&owner=include&count=40&search_text=&output=atom"
    )
    try:
        feed = feedparser.parse(url, agent=_EDGAR_UA, request_headers={"User-Agent": _EDGAR_UA})
        for entry in feed.entries:
            title      = getattr(entry, "title", "")
            summary    = getattr(entry, "summary", "")
            link       = getattr(entry, "link", "")
            filing_id  = getattr(entry, "id", link)

            # Extract filing date from summary ("Filed: YYYY-MM-DD")
            date_match = re.search(r"Filed:</b>\s*(\d{4}-\d{2}-\d{2})", summary)
            filed_date = date_match.group(1) if date_match else None

            rows.append({
                "filing_id":   filing_id[:200],
                "ticker":      None,           # Form 4 RSS doesn't include ticker; enriched later
                "company_name": title[:200],
                "insider_name": None,
                "transaction_type": None,
                "shares":      None,
                "price":       None,
                "filed_date":  filed_date,
                "scraped_utc": now,
            })

        print(f"  [edgar] {len(rows)} Form 4 filings")
    except Exception as exc:
        print(f"  [edgar] {exc}")

    return rows


# ── Main pipeline ──────────────────────────────────────────────────────────────

def run() -> None:
    started_at = time.time()
    stats: dict[str, int] = {k: 0 for k in [
        "subreddits_scraped", "mentions_scraped", "new_mentions",
        "vader_scored", "prices_updated", "predictions_written",
    ]}
    error_msg: str | None = None

    try:
        print("\n── Scraping Reddit (PullPush) ──")
        mentions = scrape_reddit()
        stats["subreddits_scraped"] = len(config.SUBREDDITS)
        stats["mentions_scraped"]   = len(mentions)
        stats["vader_scored"]       = len(mentions)

        result = d1.ingest("raw_mentions", mentions)
        stats["new_mentions"] = result["inserted"]
        print(f"  → {result['inserted']} new, {result['skipped']} dupes")

        print("\n── Computing ticker sentiment summary ──")
        summaries = compute_sentiment_summary(mentions)
        d1.ingest("ticker_sentiment_summary", summaries, mode="replace")
        print(f"  → {len(summaries)} ticker summaries written")

        print("\n── Fetching market data (yFinance) ──")
        ticker_counts = Counter(m["ticker"] for m in mentions)
        top_tickers   = [t for t, _ in ticker_counts.most_common(config.TOP_TICKERS_FOR_MARKET_DATA)]
        price_rows, inst_rows, event_rows = fetch_market_data(top_tickers, started_at)

        d1.ingest("price_snapshots", price_rows)
        d1.ingest("institutional_data", [
            r for r in inst_rows
            if any(v for k, v in r.items() if k not in ("ticker", "report_date") and v is not None)
        ], mode="replace")
        if event_rows:
            d1.ingest("scraper_events", event_rows)
        stats["prices_updated"] = len(price_rows)

        print("\n── Fetching news (CNBC + Seeking Alpha) ──")
        news_rows = fetch_news()
        d1.ingest("news_articles", news_rows)

        print("\n── Fetching insider trades (SEC EDGAR Form 4) ──")
        insider_rows = fetch_insider_trades()
        d1.ingest("insider_trades", insider_rows)

        status = "completed"
        print(f"\n── Run complete in {time.time() - started_at:.1f}s ──")
        print(f"   mentions={stats['mentions_scraped']} new={stats['new_mentions']} prices={stats['prices_updated']}")

    except Exception as exc:
        status    = "failed"
        error_msg = str(exc)
        print(f"\n[PIPELINE ERROR] {exc}", file=sys.stderr)
        raise

    finally:
        d1.ingest("pipeline_runs", [{
            "started_at":          started_at,
            "finished_at":         time.time(),
            "status":              status,
            "triggered_by":        "schedule",
            "subreddits_scraped":  stats["subreddits_scraped"],
            "mentions_scraped":    stats["mentions_scraped"],
            "new_mentions":        stats["new_mentions"],
            "vader_scored":        stats["vader_scored"],
            "prices_updated":      stats["prices_updated"],
            "predictions_written": stats["predictions_written"],
            "error_message":       error_msg,
        }])


if __name__ == "__main__":
    run()
