-- Tracks tickers that failed during market data fetch (delisted, not found, etc.)
-- Lets the dashboard surface "we tried these but couldn't get data" rather than silently dropping.
CREATE TABLE IF NOT EXISTS scraper_events (
    id                  INTEGER PRIMARY KEY,
    event_type          TEXT    NOT NULL,   -- ticker_not_found | delisted | rate_limit | parse_error
    ticker              TEXT,
    detail              TEXT,
    pipeline_started_at REAL,
    occurred_at         REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_events_ticker ON scraper_events (ticker, occurred_at DESC);
CREATE INDEX IF NOT EXISTS ix_events_type   ON scraper_events (event_type, occurred_at DESC);
