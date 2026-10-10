-- Migration 065: which offer a log entry or a draft is about.
-- See docs/plans/2026-10-10-offers-and-deals-design.md (phase 2).
--
-- NULL on a log entry means "general" — a chat that was not about selling
-- anything. Everything logged before today stays general: nothing recorded which
-- offer it was about, and guessing would put words in the log.
--
-- Drafts are different: every draft so far was written by the outreach agent,
-- which only ever worked for consulting, so they are marked Consulting.

ALTER TABLE interactions        ADD COLUMN IF NOT EXISTS offer_id INTEGER REFERENCES offers(id) ON DELETE SET NULL;
ALTER TABLE people_interactions ADD COLUMN IF NOT EXISTS offer_id INTEGER REFERENCES offers(id) ON DELETE SET NULL;
ALTER TABLE approval_queue      ADD COLUMN IF NOT EXISTS offer_id INTEGER REFERENCES offers(id) ON DELETE SET NULL;

UPDATE approval_queue SET offer_id = offer_id_for(workspace_id, 'consulting') WHERE offer_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_interactions_offer        ON interactions (offer_id) WHERE offer_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_people_interactions_offer ON people_interactions (offer_id) WHERE offer_id IS NOT NULL;
