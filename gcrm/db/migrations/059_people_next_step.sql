-- Migration 059: what happens next with a person.
--
-- next_step       the plan, in a few words ("invite to coffee at Café Dichtl")
-- next_step_date  optional: when it is due, so the People list can sort by it
--
-- Only the current step lives here. Every change is also written to the
-- person's note log (people_interactions, method 'next_step' or, when a step is
-- cleared, 'next_step_done'), so the history of what was planned stays.

ALTER TABLE people ADD COLUMN IF NOT EXISTS next_step      TEXT;
ALTER TABLE people ADD COLUMN IF NOT EXISTS next_step_date DATE;

CREATE INDEX IF NOT EXISTS idx_people_next_step_date
    ON people(next_step_date) WHERE next_step_date IS NOT NULL AND deleted_at IS NULL;
