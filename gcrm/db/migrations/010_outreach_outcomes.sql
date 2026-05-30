CREATE TABLE IF NOT EXISTS outreach_outcomes (
    id                   SERIAL PRIMARY KEY,
    contact_id           INTEGER NOT NULL REFERENCES contacts(id),
    sent_interaction_id  INTEGER REFERENCES interactions(id),
    reply_interaction_id INTEGER REFERENCES interactions(id),
    warm                 BOOLEAN NOT NULL DEFAULT true,
    word_count           INTEGER,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS outreach_outcomes_contact_id_idx ON outreach_outcomes(contact_id);
CREATE INDEX IF NOT EXISTS outreach_outcomes_created_at_idx ON outreach_outcomes(created_at);
