-- Migration 094: the expected new sales are entered as hours of work a week at a rate per hour; the
-- monthly value (hours x rate x 52/12) is worked out and kept in expected_new_monthly as before.
--   income_plan.expected_new_hours_per_week  hours a week each expected booking asks for
--   income_plan.expected_new_rate            euros charged per hour
ALTER TABLE income_plan ADD COLUMN IF NOT EXISTS expected_new_hours_per_week NUMERIC(6, 2);
ALTER TABLE income_plan ADD COLUMN IF NOT EXISTS expected_new_rate NUMERIC(8, 2);
ALTER TABLE income_plan DROP CONSTRAINT IF EXISTS income_plan_expected_new_hours_range;
ALTER TABLE income_plan ADD CONSTRAINT income_plan_expected_new_hours_range
    CHECK (expected_new_hours_per_week IS NULL OR expected_new_hours_per_week BETWEEN 0 AND 168);
ALTER TABLE income_plan DROP CONSTRAINT IF EXISTS income_plan_expected_new_rate_range;
ALTER TABLE income_plan ADD CONSTRAINT income_plan_expected_new_rate_range
    CHECK (expected_new_rate IS NULL OR expected_new_rate BETWEEN 0 AND 10000);
