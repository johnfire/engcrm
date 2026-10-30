-- Log activity absorbs the old per-organization Visit Info block: each logged
-- activity now records how it felt and what was left behind. Its date is
-- interaction_date and a promised follow-up is next_action / next_action_date,
-- so only these two are new. The old contacts columns (last_visited_at,
-- visit_duration, first_impression, last_impression, materials_left,
-- followup_promised) are no longer written; they stay until a later cleanup.
ALTER TABLE interactions ADD COLUMN IF NOT EXISTS impression VARCHAR(20)
    CHECK (impression IN ('warm', 'neutral', 'cold', 'skeptical'));
ALTER TABLE interactions ADD COLUMN IF NOT EXISTS materials_left TEXT;
