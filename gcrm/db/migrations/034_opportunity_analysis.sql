-- Structured, explainable opportunity assessments for custom AI/software work.
ALTER TABLE ai_analysis
    ADD COLUMN IF NOT EXISTS analysis_kind VARCHAR(40) NOT NULL DEFAULT 'legacy',
    ADD COLUMN IF NOT EXISTS opportunity_score SMALLINT,
    ADD COLUMN IF NOT EXISTS confidence_score SMALLINT,
    ADD COLUMN IF NOT EXISTS evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS recommended_services JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS discovery_questions JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE ai_analysis
    ADD CONSTRAINT ai_analysis_opportunity_score_range
    CHECK (opportunity_score IS NULL OR opportunity_score BETWEEN 0 AND 100);

ALTER TABLE ai_analysis
    ADD CONSTRAINT ai_analysis_confidence_score_range
    CHECK (confidence_score IS NULL OR confidence_score BETWEEN 0 AND 100);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_analysis_active_opportunity_contact
    ON ai_analysis (contact_id)
    WHERE deleted_at IS NULL AND analysis_kind = 'opportunity';
