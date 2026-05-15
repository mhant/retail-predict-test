/**
 * Retail Predict — Cloudflare Worker write proxy (M2)
 *
 * The GitHub Actions Python scraper POSTs batches of data here.
 * This Worker authenticates, validates, and bulk-inserts into D1.
 *
 * Endpoints:
 *   GET  /health          — health check (no auth)
 *   POST /ingest          — bulk insert rows into a table (requires auth)
 *
 * Auth: Authorization: Bearer <WRITE_TOKEN>
 * WRITE_TOKEN is set with: wrangler secret put WRITE_TOKEN
 */

// Whitelisted tables and their accepted column names.
// Any table or column not listed here is rejected — prevents SQL injection.
const SCHEMA = {
  pipeline_runs: [
    'started_at', 'finished_at', 'status', 'triggered_by',
    'subreddits_scraped', 'mentions_scraped', 'new_mentions',
    'vader_scored', 'prices_updated', 'predictions_written', 'error_message',
  ],
  raw_mentions: [
    'source', 'source_id', 'subreddit', 'ticker', 'title', 'selftext',
    'author', 'score', 'ups', 'upvote_ratio', 'num_comments',
    'url', 'created_utc', 'scraped_utc',
  ],
  sentiment_scores: [
    'mention_id', 'analyzer', 'compound', 'positive', 'negative',
    'neutral', 'processed_utc',
  ],
  ticker_sentiment_summary: [
    'ticker', 'window_hours', 'computed_at', 'mention_count',
    'avg_sentiment', 'upvote_weighted_sentiment', 'avg_upvote_ratio',
    'source_count', 'top_title',
  ],
  news_articles: [
    'source', 'article_id', 'ticker', 'title', 'summary',
    'url', 'published_utc', 'scraped_utc',
  ],
  price_snapshots: [
    'ticker', 'interval', 'ts', 'open', 'high', 'low', 'close', 'volume',
    'rsi_14', 'macd', 'macd_signal', 'macd_histogram',
    'bb_upper', 'bb_lower', 'bb_position',
    'sma_20', 'sma_50', 'atr_14', 'atr_normalized',
    'volume_ratio_20d', 'price_momentum_1d', 'price_momentum_5d',
  ],
  institutional_data: [
    'ticker', 'report_date', 'institutional_ownership_pct',
    'short_interest_pct', 'short_ratio', 'put_call_ratio',
    'insider_buy_count_30d', 'insider_sell_count_30d',
  ],
  insider_trades: [
    'filing_id', 'ticker', 'company_name', 'insider_name',
    'transaction_type', 'shares', 'price', 'filed_date', 'scraped_utc',
  ],
  model_predictions: [
    'ticker', 'horizon', 'predicted_at', 'signal',
    'probability_up', 'probability_down', 'confidence', 'feature_ts',
  ],
  hype_signals: [
    'ticker', 'computed_at', 'window_hours', 'signal',
    'avg_sentiment', 'upvote_weighted_sentiment',
    'mention_count', 'mention_velocity', 'source_count',
  ],
  combined_predictions: [
    'ticker', 'horizon', 'predicted_at', 'signal',
    'probability_up', 'confidence', 'model_weight', 'hype_weight',
    'model_prediction_id', 'hype_signal_id',
  ],
  prediction_outcomes: [
    'ticker', 'horizon', 'predicted_at', 'prediction_type',
    'prediction_id', 'predicted_signal', 'predicted_prob_up',
    'actual_return', 'evaluated_at', 'was_correct',
  ],
};

// Tables where we REPLACE (upsert) instead of IGNORE on conflict
const UPSERT_TABLES = new Set([
  'ticker_sentiment_summary',
  'institutional_data',
  'pipeline_runs',
]);

const D1_BATCH_SIZE = 100; // D1 batch limit per call


function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function unauthorized() {
  return json({ ok: false, error: 'Unauthorized' }, 401);
}

function badRequest(msg) {
  return json({ ok: false, error: msg }, 400);
}

function isAuthed(request, env) {
  const header = request.headers.get('Authorization') || '';
  const token = header.startsWith('Bearer ') ? header.slice(7) : '';
  return token.length > 0 && token === env.WRITE_TOKEN;
}

/**
 * Build and execute batch INSERT statements for one table.
 * Chunks into groups of D1_BATCH_SIZE to stay within D1 limits.
 */
async function batchInsert(db, table, rows, mode) {
  if (!rows.length) return { inserted: 0, skipped: 0 };

  const allowedCols = SCHEMA[table];
  // Use only columns that exist in this table's schema
  const cols = Object.keys(rows[0]).filter(c => allowedCols.includes(c));
  if (!cols.length) throw new Error(`No valid columns found for table '${table}'`);

  const verb = UPSERT_TABLES.has(table) || mode === 'replace'
    ? 'INSERT OR REPLACE'
    : 'INSERT OR IGNORE';

  const placeholders = cols.map((_, i) => `?${i + 1}`).join(', ');
  const sql = `${verb} INTO ${table} (${cols.join(', ')}) VALUES (${placeholders})`;

  let totalInserted = 0;

  // Process in chunks
  for (let i = 0; i < rows.length; i += D1_BATCH_SIZE) {
    const chunk = rows.slice(i, i + D1_BATCH_SIZE);
    const stmts = chunk.map(row => {
      const values = cols.map(c => row[c] ?? null);
      return db.prepare(sql).bind(...values);
    });
    const results = await db.batch(stmts);
    totalInserted += results.reduce((sum, r) => sum + (r.meta?.changes ?? 0), 0);
  }

  return { inserted: totalInserted, skipped: rows.length - totalInserted };
}


export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    // ── Health check (no auth) ────────────────────────────────────────────────
    if (request.method === 'GET' && path === '/health') {
      try {
        // Verify DB is reachable
        await env.DB.prepare("SELECT 1").first();
        return json({
          ok: true,
          service: 'retail-predict-worker',
          db: 'retail-predict',
          timestamp: new Date().toISOString(),
        });
      } catch (err) {
        return json({ ok: false, error: 'DB unreachable', detail: err.message }, 503);
      }
    }

    // ── Ingest endpoint ───────────────────────────────────────────────────────
    if (request.method === 'POST' && path === '/ingest') {
      if (!isAuthed(request, env)) return unauthorized();

      let body;
      try {
        body = await request.json();
      } catch {
        return badRequest('Invalid JSON body');
      }

      const { table, rows, mode } = body;

      if (!table || typeof table !== 'string') return badRequest('Missing or invalid "table"');
      if (!SCHEMA[table]) return badRequest(`Unknown table '${table}'. Allowed: ${Object.keys(SCHEMA).join(', ')}`);
      if (!Array.isArray(rows) || rows.length === 0) return badRequest('"rows" must be a non-empty array');
      if (rows.length > 5000) return badRequest('Max 5000 rows per request');

      try {
        const { inserted, skipped } = await batchInsert(env.DB, table, rows, mode);
        return json({ ok: true, table, attempted: rows.length, inserted, skipped });
      } catch (err) {
        console.error(`Ingest error for table '${table}':`, err);
        return json({ ok: false, error: err.message }, 500);
      }
    }

    return json({ ok: false, error: 'Not found' }, 404);
  },
};
