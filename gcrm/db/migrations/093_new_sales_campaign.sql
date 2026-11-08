-- Migration 093: how many months the new-sales campaign runs.
--   income_plan.expected_new_campaign  months, from this one, in which the expected new bookings are made;
--                                      after the last one no more are added. NULL = it never stops.
ALTER TABLE income_plan ADD COLUMN IF NOT EXISTS expected_new_campaign SMALLINT;
ALTER TABLE income_plan DROP CONSTRAINT IF EXISTS income_plan_expected_new_campaign_range;
ALTER TABLE income_plan ADD CONSTRAINT income_plan_expected_new_campaign_range
    CHECK (expected_new_campaign IS NULL OR expected_new_campaign BETWEEN 1 AND 120);
