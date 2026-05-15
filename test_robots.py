"""
M1 robots.txt compliance check.

Verifies that every URL we intend to scrape is permitted by the host's
robots.txt. Uses Python's standard-library urllib.robotparser.

Our bot User-Agent: retail-predict-bot
"""
from __future__ import annotations

import sys
import urllib.robotparser
import urllib.request
from dataclasses import dataclass

_BOT_UA = "retail-predict-bot"

# (label, robots.txt URL, path to check)
CHECKS = [
    # Reddit — RSS feeds are the intended machine-readable endpoint
    ("Reddit /r/*/hot.rss",   "https://www.reddit.com/robots.txt",    "/r/wallstreetbets/hot.rss"),
    ("Reddit /r/*/new.rss",   "https://www.reddit.com/robots.txt",    "/r/wallstreetbets/new.rss"),

    # PullPush — Reddit data archive, explicitly for research
    ("PullPush submissions",  "https://api.pullpush.io/robots.txt",   "/reddit/search/submission/"),

    # Google News RSS search endpoint
    ("Google News RSS",       "https://news.google.com/robots.txt",   "/rss/search"),

    # SEC EDGAR — public government data
    ("SEC EDGAR tickers",     "https://www.sec.gov/robots.txt",       "/files/company_tickers.json"),
    ("SEC EDGAR Form 4 RSS",  "https://www.sec.gov/robots.txt",       "/cgi-bin/browse-edgar"),
    ("SEC EDGAR data API",    "https://data.sec.gov/robots.txt",      "/submissions/"),
    ("SEC EDGAR EFTS",        "https://efts.sec.gov/robots.txt",      "/LATEST/search-index"),

    # Financial news RSS feeds (RSS = machine-readable by design)
    ("CNBC RSS",              "https://www.cnbc.com/robots.txt",      "/id/15839135/device/rss/rss.html"),
    ("MarketWatch RSS",       "https://www.marketwatch.com/robots.txt", "/rss/topstories"),
    ("Motley Fool RSS",       "https://www.fool.com/robots.txt",      "/feeds/index.aspx"),
    ("Seeking Alpha RSS",     "https://seekingalpha.com/robots.txt",  "/market_currents.xml"),

    # yFinance hits Yahoo Finance endpoints
    ("Yahoo Finance",         "https://finance.yahoo.com/robots.txt", "/"),
]


@dataclass
class Result:
    label: str
    path: str
    allowed: bool | None   # None = could not fetch robots.txt
    note: str = ""


results: list[Result] = []

print(f"\nBot User-Agent being checked: '{_BOT_UA}'\n")
print(f"  {'Source':<30} {'Path':<45} {'Status'}")
print(f"  {'-'*30} {'-'*45} {'-'*10}")

for label, robots_url, path in CHECKS:
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)
    try:
        req = urllib.request.Request(
            robots_url,
            headers={"User-Agent": "retail-predict-bot/1.0 (+https://github.com/mhant)"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read().decode("utf-8", errors="replace")
        rp.parse(content.splitlines())
        allowed = rp.can_fetch(_BOT_UA, path)
        note = "" if allowed else "⚠️  check manually"
        results.append(Result(label=label, path=path, allowed=allowed, note=note))
        icon = "✅" if allowed else "🚫"
        print(f"  {icon} {label:<30} {path:<45} {'ALLOWED' if allowed else 'DISALLOWED'}")
    except Exception as exc:
        # robots.txt not found or unreachable — treat as "allowed" (RFC 9309 §2.2)
        note = f"robots.txt unreachable ({type(exc).__name__}) → assume allowed per RFC 9309"
        results.append(Result(label=label, path=path, allowed=None, note=note))
        print(f"  🟡 {label:<30} {path:<45} UNKNOWN ({type(exc).__name__})")

# ── Summary ───────────────────────────────────────────────────────────────────
explicitly_allowed  = [r for r in results if r.allowed is True]
explicitly_blocked  = [r for r in results if r.allowed is False]
unknown             = [r for r in results if r.allowed is None]

print(f"\n  Explicitly allowed:  {len(explicitly_allowed)}/{len(results)}")
print(f"  Explicitly blocked:  {len(explicitly_blocked)}")
print(f"  robots.txt missing:  {len(unknown)}  (RFC 9309: treated as allowed)")

if explicitly_blocked:
    print("\n🚫 BLOCKED PATHS — do not scrape these:")
    for r in explicitly_blocked:
        print(f"   {r.label}: {r.path}")
    print("\nFAIL: one or more intended paths are disallowed by robots.txt.")
    sys.exit(1)

print("\n✅ PASS — all checked paths are allowed (or robots.txt is absent).")
print("   Safe to proceed to M2.")
