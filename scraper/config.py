"""Central config — all settings read from environment variables."""
from __future__ import annotations
import os

WORKER_URL  = os.environ.get("WORKER_URL", "").strip().rstrip("/")
WRITE_TOKEN = os.environ.get("WRITE_TOKEN", "").strip()

if not WORKER_URL or not WRITE_TOKEN:
    raise EnvironmentError(
        "WORKER_URL and WRITE_TOKEN must be set. "
        "Add them as GitHub Actions secrets (repo Settings → Secrets → Actions)."
    )

SUBREDDITS = [
    "wallstreetbets",
    "stocks",
    "options",
    "pennystocks",
    "Superstonk",
    "investing",
    "thetagang",
]

# How many posts to fetch per subreddit per sort order
POSTS_PER_SUBREDDIT = 25

# Top N mentioned tickers to fetch market data for each run
TOP_TICKERS_FOR_MARKET_DATA = 50

# Ticker universe — cashtags always trusted; all-caps words checked against this list
WATCHLIST: frozenset[str] = frozenset([
    # Meme / high-retail-interest
    "GME", "AMC", "BBBY", "BB", "NOK", "KOSS", "EXPR", "CLOV",
    "WISH", "WKHS", "SPCE", "RIDE", "NKLA", "MULN", "FFIE",
    # Crypto-adjacent
    "COIN", "MARA", "RIOT", "MSTR", "HUT", "BITF", "CLSK",
    # Big tech / mega cap
    "AAPL", "MSFT", "NVDA", "GOOGL", "GOOG", "AMZN", "META",
    "TSLA", "NFLX", "AMD", "INTC", "QCOM", "AVGO", "MU",
    "ORCL", "CRM", "ADBE", "NOW", "SNOW", "PLTR", "UBER",
    # Finance / banks
    "JPM", "BAC", "WFC", "GS", "MS", "C", "BRK", "V", "MA",
    # EV / clean energy
    "RIVN", "LCID", "NIO", "XPEV", "LI", "FCEL", "PLUG", "CHPT",
    "BLNK", "EVGO", "FSR", "GOEV",
    # Social / retail faves
    "SNAP", "PINS", "RBLX", "U", "DKNG", "PENN", "HOOD",
    "SOFI", "AFRM", "UPST", "OPEN", "LMND",
    # Healthcare / biotech
    "MRNA", "PFE", "BNTX", "JNJ", "ABBV", "LLY",
    # ETFs frequently mentioned
    "SPY", "QQQ", "IWM", "DIA", "GLD", "SLV", "TLT", "VIX",
    # China / emerging
    "BABA", "JD", "PDD", "BIDU", "NIO",
    # Other popular
    "F", "GM", "GE", "T", "VZ", "DIS", "BA", "CAT", "XOM",
    "CVX", "OXY", "CLF", "X", "AA", "FCX",
])

# Words that look like tickers but never are
STOPWORDS: frozenset[str] = frozenset([
    "A", "I", "AM", "AN", "AS", "AT", "BE", "BY", "DO", "GO", "HE",
    "HI", "ID", "IF", "IN", "IS", "IT", "ME", "MY", "NO", "OF", "OH",
    "OK", "ON", "OR", "SO", "TO", "UP", "US", "WE", "AND", "ARE",
    "BUT", "CAN", "DID", "FOR", "GET", "GOT", "HAD", "HAS", "HER",
    "HIM", "HIS", "HOW", "ITS", "LET", "MAY", "NEW", "NOT", "NOW",
    "OFF", "OLD", "ONE", "OUR", "OUT", "OWN", "SAY", "SHE", "THE",
    "TOO", "TWO", "USE", "WAS", "WAY", "WHO", "WHY", "YET", "YOU",
    "ALL", "CEO", "CFO", "COO", "CTO", "IPO", "EPS", "ETF", "NFT",
    "BTC", "ATH", "ROI", "GDP", "CPI", "FED", "SEC", "NYSE",
    "WSB", "DD", "TA", "OTM", "ITM", "ATM", "IMO", "TBH", "NGL",
    "LMAO", "LOL", "WTF", "YOLO", "FOMO", "FUD", "HODL", "MOON",
    "BEAR", "BULL", "DM", "PM", "OP", "UK", "EU", "CA", "AU",
    "HIGH", "LOSS", "SELL", "PUTS", "CALL", "HOLD", "LONG", "STAY",
    "OPEN", "FLAT", "CASH", "LOAN", "DEBT", "FUND", "REAL", "RISK",
    "RATE", "MOVE", "GAIN", "DUMP", "PUMP", "BANK", "EARN", "GOOD",
    "OVER", "NEXT", "WEEK", "YEAR", "PLAN", "NEWS", "NEED", "WANT",
    "LIKE", "DONE", "BACK", "INTO", "THEN", "WHEN", "WITH", "YOUR",
    "ZERO", "ONLY", "JUST", "EVEN", "SAID", "SOME", "THAT", "THIS",
    "FROM", "HAVE", "BEEN", "WILL", "WHAT", "THEM", "THEY", "THAN",
    "MAKE", "TIME", "KNOW", "TAKE", "COME", "LOOK", "ALSO", "MUCH",
    "IRA", "RAM", "CPU", "GPU", "ISM", "FDA", "OTC", "SPAC", "PE",
    "EUR", "USD", "GBP", "CAD", "ETH", "SK", "RH",
])

# Financial context words — used to gate company-name matching so "I ate an apple"
# never becomes AAPL but "apple stock looks cheap" does.
FINANCIAL_CONTEXT: frozenset[str] = frozenset([
    "stock", "stocks", "share", "shares", "equity", "equities",
    "buy", "bought", "buying", "sell", "sold", "selling",
    "short", "shorting", "long", "position", "positions",
    "call", "calls", "put", "puts", "option", "options",
    "trade", "trading", "trader", "invest", "investing", "investor",
    "price", "ticker", "market", "earnings", "revenue", "profit",
    "dividend", "yield", "ipo", "portfolio", "holding", "holdings",
    "bullish", "bearish", "bull", "bear", "rally", "dump", "moon",
    "squeeze", "yolo", "tendies", "gains", "losses", "dd",
])

# Company name → ticker mapping for lowercase/natural-language detection.
# Only matched when FINANCIAL_CONTEXT words appear in the same text.
# Deliberately conservative — excluded common words that cause too many false positives
# even with context (e.g. "meta", "riot", "snap" as non-finance words).
NAME_TO_TICKER: dict[str, str] = {
    # Big tech — specific enough to be safe
    "apple":        "AAPL",
    "microsoft":    "MSFT",
    "nvidia":       "NVDA",
    "intel":        "INTC",
    "tesla":        "TSLA",
    "amazon":       "AMZN",
    "alphabet":     "GOOGL",
    "google":       "GOOGL",
    "netflix":      "NFLX",
    "uber":         "UBER",
    "lyft":         "LYFT",
    # Meme / retail faves
    "gamestop":     "GME",
    "game stop":    "GME",
    "coinbase":     "COIN",
    "palantir":     "PLTR",
    "robinhood":    "HOOD",
    "sofi":         "SOFI",
    "affirm":       "AFRM",
    "upstart":      "UPST",
    "roblox":       "RBLX",
    "draftkings":   "DKNG",
    "opendoor":     "OPEN",
    "lemonade":     "LMND",
    # EV
    "rivian":       "RIVN",
    "lucid":        "LCID",
    # Crypto adjacent
    "microstrategy": "MSTR",
    "marathon digital": "MARA",
    # Banks / finance
    "jpmorgan":     "JPM",
    "jp morgan":    "JPM",
    "bank of america": "BAC",
    "goldman":      "GS",
    "goldman sachs": "GS",
}

# Finance slang lexicon injected into VADER
FINANCE_LEXICON: dict[str, float] = {
    "moon": 3.0, "mooning": 3.0, "tendies": 2.5, "squeeze": 2.0,
    "short squeeze": 3.5, "gamma squeeze": 3.0, "apes": 1.5,
    "diamond hands": 2.0, "to the moon": 3.0, "calls": 1.5,
    "bull": 1.5, "bullish": 2.0, "rocket": 2.0, "lambo": 2.0,
    "yolo": 1.0, "printing": 1.5, "ripping": 2.0,
    "bagholder": -2.5, "bag holder": -2.5, "dump": -2.0,
    "dumping": -2.0, "rugged": -3.0, "rug pull": -3.0,
    "rekt": -2.5, "wrecked": -2.0, "puts": -1.5,
    "bear": -1.5, "bearish": -2.0, "crash": -2.5,
    "worthless": -2.0, "bankrupt": -3.0, "fraud": -3.0,
    "short": -1.0, "shorted": -1.5, "drill": -2.0,
    "capitulate": -2.0, "margin call": -2.5,
}
