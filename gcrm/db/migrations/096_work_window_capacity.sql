-- Migration 096: when the hours of a sale are worked, and how many hours a week the owner can work.
--   sales.work_from / work_to       the first and last day the sale's hours are worked (both or neither);
--                                   without them the hours fall in the month the payment is due.
--   income_plan.weekly_capacity     hours a week that can be worked; drawn as a limit on the weekly-hours chart.
ALTER TABLE sales ADD COLUMN IF NOT EXISTS work_from DATE;
ALTER TABLE sales ADD COLUMN IF NOT EXISTS work_to DATE;
ALTER TABLE sales DROP CONSTRAINT IF EXISTS sales_work_window;
ALTER TABLE sales ADD CONSTRAINT sales_work_window
    CHECK ((work_from IS NULL AND work_to IS NULL) OR (work_from IS NOT NULL AND work_to IS NOT NULL AND work_to >= work_from));
ALTER TABLE income_plan ADD COLUMN IF NOT EXISTS weekly_capacity NUMERIC(5, 2);
ALTER TABLE income_plan DROP CONSTRAINT IF EXISTS income_plan_weekly_capacity_range;
ALTER TABLE income_plan ADD CONSTRAINT income_plan_weekly_capacity_range
    CHECK (weekly_capacity IS NULL OR weekly_capacity BETWEEN 0 AND 168);
