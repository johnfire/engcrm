-- Migration 085: a sale can start as an "expected" value, before anything is booked:
-- expected → booked → contracted → collected (or cancelled). Expected money is its own
-- pipeline line; it is not won, and not part of the firm (booked + contracted) pipeline.
ALTER TABLE sales DROP CONSTRAINT IF EXISTS sales_status_known;
ALTER TABLE sales ADD CONSTRAINT sales_status_known
    CHECK (status IN ('expected', 'booked', 'contracted', 'collected', 'cancelled'));
DROP INDEX IF EXISTS idx_sales_open;
CREATE INDEX IF NOT EXISTS idx_sales_open ON sales (workspace_id, status)
    WHERE deleted_at IS NULL AND status IN ('expected', 'booked', 'contracted');
