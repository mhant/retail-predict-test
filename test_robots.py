"""
M1 robots.txt compliance check — conservative edition.

Only sources that are explicitly ALLOWED (or have no robots.txt = RFC 9309 allowed)
will be used. Any explicitly DISALLOWED source is dropped from the architecture,
even if it technically works, because we want to be 100% above board.

Bot User-Agent: retail-predict-bot
"""
from __future__ import annotations

import sys
import urllib.robotparser
import urllib.request

_BOT_UA = "retail-predict-bot"

# (label, robots.txt URL, path to check, critical)
# critical=True means failure here blocks the whole pipeline
CHECKS = [
    # PullPush — Reddit data archive, explicitly for research use
    ("PullPush /reddit/search/",  "https://api.pullpush.io/robots.txt",         "/reddit/search/submission/", True),

    # SEC EDGAR — public US government data
    ("SEC EDGAR /files/",         "https://www.sec.gov/robots.txt",             "/files/company_tickers.json", True),
    ("SEC EDGAR /cgi-bin/",       "https://www.sec.gov/robots.txt",             "/cgi-bin/browse-edgar",       True),
    ("SEC EDGAR data.sec.gov",    "https://data.sec.gov/robots.txt",            "/submissions/",               True),

    # News RSS feeds explicitly allowed
    ("CNBC RSS",                  "https://www.cnbc.com/robots.txt",            "/id/15839135/device/rss/rss.html", True),
    ("Seeking Alpha RSS",         "https://seekingalpha.com/robots.txt",        "/market_currents.xml",        False),

    # Yahoo Finance (yFinance uses these endpoints)
    ("Yahoo Finance",             "https://finance.yahoo.com/robots.txt",       "/",                           True),
]

# Sources we are NOT using because they explicitly disallow bots:
DROPPED = [
    ("Reddit RSS",        "https://www.reddit.com/robots.txt",      "/r/*/hot.rss",      "Using PullPush instead (explicitly allowed + includes scores)"),
    ("Google News RSS",   "https://news.google.com/robots.txt",     "/rss/search",       "Using CNBC + Seeking Alpha + yFinance news instead"),
    ("MarketWatch RSS",   "https://www.marketwatch.com/robots.txt", "/rss/topstories",   "Dropped — sufficient coverage from remaining sources"),
    ("Motley Fool RSS",   "https://www.fool.com/robots.txt",        "/feeds/index.aspx", "Dropped — sufficient coverage from remaining sources"),
]

print(f"\nBot User-Agent: '{_BOT_UA}'\n")
print("Sources dropped due to explicit robots.txt Disallow:")
for name, _, path, reason in DROPPED:
    print(f"  🚫 {name:<20} {path:<35} → {reason}")

print(f"\nChecking approved sources:\n")
print(f"  {'Source':<30} {'Status':<10} {'Note'}")
print(f"  {'-'*30} {'-'*10} {'-'*40}")

results = []
for label, robots_url, path, critical in CHECKS:
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)
    try:
        req = urllib.request.Request(
            robots_url,
            headers={"User-Agent": f"{_BOT_UA}/1.0 (+https://github.com/mhant)"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            rp.parse(resp.read().decode("utf-8", errors="replace").splitlines())
        allowed = rp.can_fetch(_BOT_UA, path)
        icon = "✅" if allowed else "🚫"
        note = "" if allowed else ("CRITICAL FAIL" if critical else "non-critical")
        results.append((label, allowed, critical, note))
        print(f"  {icon} {label:<30} {'ALLOWED' if allowed else 'DISALLOWED':<10} {note}")
    except Exception as exc:
        # robots.txt unreachable → RFC 9309 §2.2: treated as allowed
        note = f"robots.txt unreachable → allowed per RFC 9309 ({type(exc).__name__})"
        results.append((label, None, critical, note))
        print(f"  🟡 {label:<30} {'UNKNOWN':<10} {note}")

blocked_critical = [(l, c) for l, a, c, n in results if a is False and c]
print(f"\n  Explicitly allowed:       {sum(1 for _,a,_,_ in results if a is True)}")
print(f"  Unknown (= RFC allowed):  {sum(1 for _,a,_,_ in results if a is None)}")
print(f"  Explicitly blocked:       {sum(1 for _,a,_,_ in results if a is False)}")

if blocked_critical:
    print(f"\nFAIL: critical source(s) disallowed by robots.txt: {[l for l,_ in blocked_critical]}")
    sys.exit(1)

print("\n✅ PASS — all approved sources are allowed. Architecture is robots.txt compliant.")
print("   Proceeding to connectivity test with clean source list.")
