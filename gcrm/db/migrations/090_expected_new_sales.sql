-- Migration 090: the new sales the owner expects to book each month.
--   income_plan.expected_new_monthly  euros of new sales assumed to be booked every month, starting
--                                     with this one; drawn as its own line on the Outlook chart so
--                                     "what is already entered" and "what I hope to add" stay apart.
--   income_plan.monthly_need          may now be empty: the expectation can be set before any need is.
ALTER TABLE income_plan ALTER COLUMN monthly_need DROP NOT NULL;
ALTER TABLE income_plan ADD COLUMN IF NOT EXISTS expected_new_monthly NUMERIC(12, 2);
ALTER TABLE income_plan DROP CONSTRAINT IF EXISTS income_plan_expected_new_not_negative;
ALTER TABLE income_plan ADD CONSTRAINT income_plan_expected_new_not_negative
    CHECK (expected_new_monthly IS NULL OR expected_new_monthly >= 0);
