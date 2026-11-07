-- Migration 088: fine-tuning the forecast's plan.
--   income_plan.start_month   the first month with a target (first day of a month); earlier months
--                             have none, because the business was not running yet. NULL: no limit.
--   other_income.covers_from  the first month a line of other income *covers*, which can differ from
--                             the day it is paid (support paid in arrears for the month before).
--                             Existing lines cover the month of their first payment, as before.
ALTER TABLE income_plan ADD COLUMN IF NOT EXISTS start_month DATE;
ALTER TABLE income_plan DROP CONSTRAINT IF EXISTS income_plan_start_is_month_start;
ALTER TABLE income_plan ADD CONSTRAINT income_plan_start_is_month_start
    CHECK (start_month IS NULL OR EXTRACT(DAY FROM start_month) = 1);

ALTER TABLE other_income ADD COLUMN IF NOT EXISTS covers_from DATE;
UPDATE other_income SET covers_from = date_trunc('month', first_received_on)::date WHERE covers_from IS NULL;
ALTER TABLE other_income ALTER COLUMN covers_from SET NOT NULL;
ALTER TABLE other_income DROP CONSTRAINT IF EXISTS other_income_covers_is_month_start;
ALTER TABLE other_income ADD CONSTRAINT other_income_covers_is_month_start CHECK (EXTRACT(DAY FROM covers_from) = 1);
