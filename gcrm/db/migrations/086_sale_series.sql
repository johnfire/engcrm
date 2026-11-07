-- Migration 086: a contract paid over several months is one sale row per payment, tied
-- together by a series id (same contract; each payment has its own due day in expected_on,
-- its own amount and its own status — marking March received leaves April expected).
-- A one-off sale has no series. series_part counts from 1 up to series_total.
ALTER TABLE sales ADD COLUMN IF NOT EXISTS series_id UUID;
ALTER TABLE sales ADD COLUMN IF NOT EXISTS series_part SMALLINT;
ALTER TABLE sales ADD COLUMN IF NOT EXISTS series_total SMALLINT;

ALTER TABLE sales DROP CONSTRAINT IF EXISTS sales_series_complete;
ALTER TABLE sales ADD CONSTRAINT sales_series_complete CHECK (
    (series_id IS NULL AND series_part IS NULL AND series_total IS NULL)
    OR (series_id IS NOT NULL AND series_part BETWEEN 1 AND series_total AND series_total BETWEEN 2 AND 60));

CREATE INDEX IF NOT EXISTS idx_sales_series ON sales (deal_id, series_id) WHERE series_id IS NOT NULL;
