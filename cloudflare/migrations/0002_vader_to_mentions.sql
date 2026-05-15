-- Add VADER sentiment columns directly to raw_mentions.
-- This avoids needing to look up auto-incremented IDs after batch insert
-- in order to write to sentiment_scores. FinBERT scores will still use
-- the normalised sentiment_scores table when added later.
ALTER TABLE raw_mentions ADD COLUMN vader_compound REAL;
ALTER TABLE raw_mentions ADD COLUMN vader_positive REAL;
ALTER TABLE raw_mentions ADD COLUMN vader_negative REAL;
ALTER TABLE raw_mentions ADD COLUMN vader_neutral  REAL;
