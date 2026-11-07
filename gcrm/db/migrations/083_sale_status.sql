-- Migration 083: a sale has a life — booked, contracted (a written contract),
-- collected (the money is in) or cancelled. Only collected sales are money won;
-- booked and contracted ones are the pipeline.
--   won_on       the day the sale was agreed (unchanged)
--   expected_on  when it is expected to run or pay (optional)
--   collected_on the day the money came in; set exactly when status = 'collected'
-- Every sale so far was money in the bank, so it becomes collected on its won_on.

ALTER TABLE sales ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'collected';
ALTER TABLE sales ADD COLUMN IF NOT EXISTS expected_on DATE;
ALTER TABLE sales ADD COLUMN IF NOT EXISTS collected_on DATE;

UPDATE sales SET collected_on = won_on WHERE status = 'collected' AND collected_on IS NULL;

ALTER TABLE sales DROP CONSTRAINT IF EXISTS sales_status_known;
ALTER TABLE sales ADD CONSTRAINT sales_status_known
    CHECK (status IN ('booked', 'contracted', 'collected', 'cancelled'));
ALTER TABLE sales DROP CONSTRAINT IF EXISTS sales_collected_has_a_day;
ALTER TABLE sales ADD CONSTRAINT sales_collected_has_a_day
    CHECK ((status = 'collected') = (collected_on IS NOT NULL));

CREATE INDEX IF NOT EXISTS idx_sales_collected_on ON sales (workspace_id, collected_on)
    WHERE deleted_at IS NULL AND status = 'collected';
CREATE INDEX IF NOT EXISTS idx_sales_open ON sales (workspace_id, status)
    WHERE deleted_at IS NULL AND status IN ('booked', 'contracted');
