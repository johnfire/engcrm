-- Migration 091: how long each month's expected new booking keeps paying.
--   income_plan.expected_new_months  months each booking pays its amount (1 = a one-off, paid in the
--                                    month it is booked); NULL = it keeps paying every month for ever.
ALTER TABLE income_plan ADD COLUMN IF NOT EXISTS expected_new_months SMALLINT DEFAULT 1;
ALTER TABLE income_plan DROP CONSTRAINT IF EXISTS income_plan_expected_new_months_range;
ALTER TABLE income_plan ADD CONSTRAINT income_plan_expected_new_months_range
    CHECK (expected_new_months IS NULL OR expected_new_months BETWEEN 1 AND 120);
