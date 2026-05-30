DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'outreach_outcomes_sent_interaction_unique'
    ) THEN
        ALTER TABLE outreach_outcomes
            ADD CONSTRAINT outreach_outcomes_sent_interaction_unique
            UNIQUE (sent_interaction_id);
    END IF;
END $$;
