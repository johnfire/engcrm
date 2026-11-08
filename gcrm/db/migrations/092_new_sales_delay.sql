-- Migration 092: how long after a booking its first payment arrives, for the expected new sales.
--   income_plan.expected_new_delay  months between booking and first payment (default 1; 0 = paid in
--                                   the month it is booked).
ALTER TABLE income_plan ADD COLUMN IF NOT EXISTS expected_new_delay SMALLINT NOT NULL DEFAULT 1;
ALTER TABLE income_plan DROP CONSTRAINT IF EXISTS income_plan_expected_new_delay_range;
ALTER TABLE income_plan ADD CONSTRAINT income_plan_expected_new_delay_range
    CHECK (expected_new_delay BETWEEN 0 AND 24);
