-- Migration 095: hours of work on a sale. NULL: not recorded. A payment of a contract carries its share
-- of the hours (split like the money), so the hours booked can be added up like the euros.
ALTER TABLE sales ADD COLUMN IF NOT EXISTS hours NUMERIC(8, 2);
ALTER TABLE sales DROP CONSTRAINT IF EXISTS sales_hours_range;
ALTER TABLE sales ADD CONSTRAINT sales_hours_range CHECK (hours IS NULL OR (hours > 0 AND hours <= 100000));
