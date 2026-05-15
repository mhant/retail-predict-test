-- Retail Predict — D1 schema
-- Compatible with Cloudflare D1 (SQLite dialect)
-- Apply with: wrangler d1 migrations apply retail-predict --remote

-- ── Pipeline runs ─────────────────────────────────────────────────────────────
-- One row per scraper execution. Start/finish times visible in dashboard timeline.
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id                  INTEGER PRIMARY KEY,
    started_at          REAL    NOT NULL,
    finished_at         REAL,
    status              TEXT    NOT NULL DEFAULT 'running', -- running | completed | failed
    triggered_by        TEXT    NOT NULL DEFAULT 'schedule',
    subreddits_scraped  INTEGER NOT NULL DEFAULT 0,
    mentions_scraped    INTEGER NOT NULL DEFAULT 0,
    new_mentions        INTEGER NOT NULL DEFAULT 0,
    vader_scored        INTEGER NOT NULL DEFAULT 0,
    prices_updated      INTEGER NOT NULL DEFAULT 0,
    predictions_written INTEGER NOT NULL DEFAULT 0,
    error_message       TEXT
);

-- ── Raw mentions (from PullPush Reddit archive) ───────────────────────────────
-- Includes upvote scores — the key advantage over Reddit RSS.
CREATE TABLE IF NOT EXISTS raw_mentions (
    id             INTEGER PRIMARY KEY,
    source         TEXT    NOT NULL,                -- 'pullpush_reddit'
    source_id      TEXT    NOT NULL,                -- Reddit post ID (e.g. 't3_abc123')
    subreddit      TEXT,
    ticker         TEXT    NOT NULL,
    title          TEXT,
    selftext       TEXT,
    author         TEXT,
    score          INTEGER NOT NULL DEFAULT 0,      -- net upvotes
    ups            INTEGER NOT NULL DEFAULT 0,
    upvote_ratio   REAL,                            -- 0.0–1.0
    num_comments   INTEGER NOT NULL DEFAULT 0,
    url            TEXT,
    created_utc    REAL    NOT NULL,
    scraped_utc    REAL    NOT NULL,
    UNIQUE(source_id, ticker)
);

CREATE INDEX IF NOT EXISTS ix_mentions_ticker_created  ON raw_mentions (ticker, created_utc DESC);
CREATE INDEX IF NOT EXISTS ix_mentions_subreddit       ON raw_mentions (subreddit, created_utc DESC);

-- ── Sentiment scores (VADER) ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sentiment_scores (
    id            INTEGER PRIMARY KEY,
    mention_id    INTEGER NOT NULL REFERENCES raw_mentions(id),
    analyzer      TEXT    NOT NULL DEFAULT 'vader',
    compound      REAL,
    positive      REAL,
    negative      REAL,
    neutral       REAL,
    processed_utc REAL    NOT NULL,
    UNIQUE(mention_id, analyzer)
);

CREATE INDEX IF NOT EXISTS ix_sentiment_mention ON sentiment_scores (mention_id);

-- ── Pre-aggregated sentiment summary (keeps D1 read counts low) ───────────────
-- Written at scrape time; avoids GROUP BY over millions of raw_mentions rows.
CREATE TABLE IF NOT EXISTS ticker_sentiment_summary (
    ticker                    TEXT    NOT NULL,
    window_hours              INTEGER NOT NULL, -- 24 | 168 | 336 | 720
    computed_at               REAL    NOT NULL,
    mention_count             INTEGER,
    avg_sentiment             REAL,
    upvote_weighted_sentiment REAL,
    avg_upvote_ratio          REAL,
    source_count              INTEGER,
    top_title                 TEXT,
    PRIMARY KEY (ticker, window_hours)
);

-- ── News articles (CNBC, Seeking Alpha, yFinance news) ───────────────────────
CREATE TABLE IF NOT EXISTS news_articles (
    id            INTEGER PRIMARY KEY,
    source        TEXT    NOT NULL,
    article_id    TEXT    NOT NULL,
    ticker        TEXT,                            -- null if not ticker-specific
    title         TEXT,
    summary       TEXT,
    url           TEXT,
    published_utc REAL,
    scraped_utc   REAL    NOT NULL,
    UNIQUE(source, article_id)
);

CREATE INDEX IF NOT EXISTS ix_news_ticker_pub ON news_articles (ticker, published_utc DESC);

-- ── Price snapshots (yFinance OHLCV + indicators) ────────────────────────────
CREATE TABLE IF NOT EXISTS price_snapshots (
    id                INTEGER PRIMARY KEY,
    ticker            TEXT    NOT NULL,
    interval          TEXT    NOT NULL,            -- '1h' | '1d'
    ts                REAL    NOT NULL,
    open              REAL,
    high              REAL,
    low               REAL,
    close             REAL,
    volume            INTEGER,
    rsi_14            REAL,
    macd              REAL,
    macd_signal       REAL,
    macd_histogram    REAL,
    bb_upper          REAL,
    bb_lower          REAL,
    bb_position       REAL,
    sma_20            REAL,
    sma_50            REAL,
    atr_14            REAL,
    atr_normalized    REAL,
    volume_ratio_20d  REAL,
    price_momentum_1d REAL,
    price_momentum_5d REAL,
    UNIQUE(ticker, interval, ts)
);

CREATE INDEX IF NOT EXISTS ix_price_ticker_interval ON price_snapshots (ticker, interval, ts DESC);

-- ── Institutional data (yFinance holders + short interest) ───────────────────
CREATE TABLE IF NOT EXISTS institutional_data (
    id                          INTEGER PRIMARY KEY,
    ticker                      TEXT    NOT NULL,
    report_date                 TEXT    NOT NULL,
    institutional_ownership_pct REAL,
    short_interest_pct          REAL,
    short_ratio                 REAL,
    put_call_ratio              REAL,
    insider_buy_count_30d       INTEGER,
    insider_sell_count_30d      INTEGER,
    UNIQUE(ticker, report_date)
);

-- ── Insider trades (SEC EDGAR Form 4 RSS) ────────────────────────────────────
CREATE TABLE IF NOT EXISTS insider_trades (
    id               INTEGER PRIMARY KEY,
    filing_id        TEXT    NOT NULL UNIQUE,      -- EDGAR accession number
    ticker           TEXT,
    company_name     TEXT,
    insider_name     TEXT,
    transaction_type TEXT,                         -- 'buy' | 'sell' | 'other'
    shares           INTEGER,
    price            REAL,
    filed_date       TEXT,
    scraped_utc      REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_insider_ticker_date ON insider_trades (ticker, filed_date DESC);

-- ── Model predictions (pure XGBoost — technical + institutional only) ─────────
CREATE TABLE IF NOT EXISTS model_predictions (
    id              INTEGER PRIMARY KEY,
    ticker          TEXT    NOT NULL,
    horizon         TEXT    NOT NULL,              -- intraday | short | medium
    predicted_at    REAL    NOT NULL,
    signal          TEXT,
    probability_up  REAL,
    probability_down REAL,
    confidence      REAL,
    feature_ts      REAL,
    UNIQUE(ticker, horizon, predicted_at)
);

CREATE INDEX IF NOT EXISTS ix_model_pred_ticker ON model_predictions (ticker, horizon, predicted_at DESC);

-- ── Hype signals (retail sentiment only) ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS hype_signals (
    id                        INTEGER PRIMARY KEY,
    ticker                    TEXT    NOT NULL,
    computed_at               REAL    NOT NULL,
    window_hours              INTEGER NOT NULL,
    signal                    TEXT,               -- strong_buy | buy | neutral | sell | strong_sell
    avg_sentiment             REAL,
    upvote_weighted_sentiment REAL,
    mention_count             INTEGER,
    mention_velocity          REAL,
    source_count              INTEGER,
    UNIQUE(ticker, computed_at, window_hours)
);

CREATE INDEX IF NOT EXISTS ix_hype_ticker ON hype_signals (ticker, computed_at DESC);

-- ── Combined predictions (model + hype weighted blend) ───────────────────────
CREATE TABLE IF NOT EXISTS combined_predictions (
    id                   INTEGER PRIMARY KEY,
    ticker               TEXT    NOT NULL,
    horizon              TEXT    NOT NULL,
    predicted_at         REAL    NOT NULL,
    signal               TEXT,
    probability_up       REAL,
    confidence           REAL,
    model_weight         REAL    NOT NULL DEFAULT 0.3,
    hype_weight          REAL    NOT NULL DEFAULT 0.7,
    model_prediction_id  INTEGER REFERENCES model_predictions(id),
    hype_signal_id       INTEGER REFERENCES hype_signals(id),
    UNIQUE(ticker, horizon, predicted_at)
);

CREATE INDEX IF NOT EXISTS ix_combined_ticker ON combined_predictions (ticker, horizon, predicted_at DESC);

-- ── Prediction outcomes (actual vs predicted — for accuracy visualization) ────
-- populated by a daily accuracy-check job after enough time has passed.
CREATE TABLE IF NOT EXISTS prediction_outcomes (
    id                    INTEGER PRIMARY KEY,
    ticker                TEXT    NOT NULL,
    horizon               TEXT    NOT NULL,
    predicted_at          REAL    NOT NULL,
    prediction_type       TEXT    NOT NULL, -- model | hype | combined
    prediction_id         INTEGER,
    predicted_signal      TEXT,
    predicted_prob_up     REAL,
    actual_return         REAL,             -- null until evaluated
    evaluated_at          REAL,
    was_correct           INTEGER,          -- 1 | 0 | null
    UNIQUE(ticker, horizon, predicted_at, prediction_type)
);

CREATE INDEX IF NOT EXISTS ix_outcomes_ticker ON prediction_outcomes (ticker, horizon, predicted_at DESC);
