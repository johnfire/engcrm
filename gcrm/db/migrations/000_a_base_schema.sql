-- Art CRM Initial Schema
-- Migration: 001_initial_schema.sql
-- Description: Create all core tables with soft delete support
-- Author: Christopher Rehm
-- Date: 2026-02-12

-- =============================================================================
-- MIGRATION TRACKING
-- =============================================================================

CREATE TABLE IF NOT EXISTS schema_migrations (
    id SERIAL PRIMARY KEY,
    migration_name VARCHAR(255) NOT NULL UNIQUE,
    applied_at TIMESTAMPTZ DEFAULT NOW(),
    checksum VARCHAR(64),
    execution_time_ms INTEGER,
    rolled_back_at TIMESTAMPTZ,
    rollback_reason TEXT
);

-- Record this migration
INSERT INTO schema_migrations (migration_name, checksum)
VALUES ('001_initial_schema.sql', 'initial');

-- =============================================================================
-- EXTENSIBLE LOOKUP VALUES
-- =============================================================================

CREATE TABLE lookup_values (
    id SERIAL PRIMARY KEY,
    category VARCHAR(60) NOT NULL,
    value VARCHAR(60) NOT NULL,
    label_de VARCHAR(120),
    label_en VARCHAR(120),
    sort_order INTEGER DEFAULT 0,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    UNIQUE (category, value)
);

-- Index for fast category lookups
CREATE INDEX idx_lookup_values_category ON lookup_values(category) WHERE deleted_at IS NULL;
CREATE INDEX idx_lookup_values_active ON lookup_values(category, active) WHERE deleted_at IS NULL;

COMMENT ON TABLE lookup_values IS 'Extensible categorical values for all dropdown fields. Add new values via INSERT, never ALTER TABLE.';
COMMENT ON COLUMN lookup_values.category IS 'The field this value applies to (e.g., contact_type, status, language)';
COMMENT ON COLUMN lookup_values.value IS 'The actual value stored in the database';
COMMENT ON COLUMN lookup_values.label_de IS 'German display label for UI';
COMMENT ON COLUMN lookup_values.label_en IS 'English display label for UI';

-- =============================================================================
-- CONTACTS
-- =============================================================================

CREATE TABLE contacts (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    type VARCHAR(60),
    subtype VARCHAR(60),
    city VARCHAR(100),
    country CHAR(2),
    address TEXT,
    website VARCHAR(300),
    email VARCHAR(200),
    phone VARCHAR(60),
    preferred_language VARCHAR(10) DEFAULT 'de',
    status VARCHAR(60),
    fit_score SMALLINT CHECK (fit_score >= 0 AND fit_score <= 100),
    success_probability SMALLINT CHECK (success_probability >= 0 AND success_probability <= 100),
    best_visit_time VARCHAR(200),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT chk_country_code CHECK (country IS NULL OR length(country) = 2)
);

-- Indexes for common queries
CREATE INDEX idx_contacts_name ON contacts(name) WHERE deleted_at IS NULL;
CREATE INDEX idx_contacts_city ON contacts(city) WHERE deleted_at IS NULL;
CREATE INDEX idx_contacts_type ON contacts(type) WHERE deleted_at IS NULL;
CREATE INDEX idx_contacts_status ON contacts(status) WHERE deleted_at IS NULL;
CREATE INDEX idx_contacts_updated_at ON contacts(updated_at DESC) WHERE deleted_at IS NULL;

-- Full text search index for notes and name
CREATE INDEX idx_contacts_search ON contacts USING gin(to_tsvector('german', coalesce(name, '') || ' ' || coalesce(notes, ''))) WHERE deleted_at IS NULL;

COMMENT ON TABLE contacts IS 'Galleries, cafes, hotels, offices, coworking spaces, online platforms, and other venues';
COMMENT ON COLUMN contacts.type IS 'FK to lookup_values(contact_type)';
COMMENT ON COLUMN contacts.subtype IS 'FK to lookup_values(contact_subtype)';
COMMENT ON COLUMN contacts.status IS 'FK to lookup_values(contact_status)';
COMMENT ON COLUMN contacts.preferred_language IS 'FK to lookup_values(language) - language for outreach messages';
COMMENT ON COLUMN contacts.fit_score IS 'AI-generated 0-100 score: how well does this venue match artist style';
COMMENT ON COLUMN contacts.success_probability IS 'AI-generated 0-100 estimate of success likelihood';
COMMENT ON COLUMN contacts.best_visit_time IS 'Free text: e.g., "Mon-Tue morning", "avoid weekends"';

-- =============================================================================
-- INTERACTIONS
-- =============================================================================

CREATE TABLE interactions (
    id SERIAL PRIMARY KEY,
    contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    interaction_date DATE NOT NULL,
    method VARCHAR(60),
    direction VARCHAR(10) CHECK (direction IN ('outbound', 'inbound')),
    summary TEXT,
    outcome VARCHAR(60),
    next_action TEXT,
    next_action_date DATE,
    ai_draft_used BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

-- Indexes for common queries
CREATE INDEX idx_interactions_contact_id ON interactions(contact_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_interactions_date ON interactions(interaction_date DESC) WHERE deleted_at IS NULL;
CREATE INDEX idx_interactions_next_action_date ON interactions(next_action_date) WHERE deleted_at IS NULL;
CREATE INDEX idx_interactions_outcome ON interactions(outcome) WHERE deleted_at IS NULL;

COMMENT ON TABLE interactions IS 'Full interaction history per contact. Replaces the 5-column spreadsheet model.';
COMMENT ON COLUMN interactions.method IS 'FK to lookup_values(interaction_method): email, in_person, phone, letter, social_media';
COMMENT ON COLUMN interactions.direction IS 'outbound = we contacted them, inbound = they contacted us';
COMMENT ON COLUMN interactions.outcome IS 'FK to lookup_values(interaction_outcome): no_reply, interested, rejected, meeting_set, etc.';
COMMENT ON COLUMN interactions.ai_draft_used IS 'TRUE if this message was drafted by AI';

-- =============================================================================
-- SHOWS
-- =============================================================================

CREATE TABLE shows (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200),
    venue_contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
    city VARCHAR(100),
    date_start DATE,
    date_end DATE,
    theme VARCHAR(200),
    status VARCHAR(60),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT chk_show_dates CHECK (date_end IS NULL OR date_start IS NULL OR date_end >= date_start)
);

-- Indexes for common queries
CREATE INDEX idx_shows_date_start ON shows(date_start) WHERE deleted_at IS NULL;
CREATE INDEX idx_shows_date_end ON shows(date_end) WHERE deleted_at IS NULL;
CREATE INDEX idx_shows_venue ON shows(venue_contact_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_shows_status ON shows(status) WHERE deleted_at IS NULL;

COMMENT ON TABLE shows IS 'Exhibition pipeline: possible, confirmed, completed, cancelled';
COMMENT ON COLUMN shows.venue_contact_id IS 'Link to contacts table. NULL if venue not in contacts yet.';
COMMENT ON COLUMN shows.status IS 'FK to lookup_values(show_status): possible, confirmed, completed, cancelled';

-- =============================================================================
-- AI ANALYSIS
-- =============================================================================

CREATE TABLE ai_analysis (
    id SERIAL PRIMARY KEY,
    contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    analysis_date TIMESTAMPTZ DEFAULT NOW(),
    model_used VARCHAR(100),
    fit_reasoning TEXT,
    suggested_approach TEXT,
    suggested_next_contact DATE,
    priority_score SMALLINT CHECK (priority_score >= 0 AND priority_score <= 100),
    raw_response TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

-- Indexes for common queries
CREATE INDEX idx_ai_analysis_contact_id ON ai_analysis(contact_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_ai_analysis_date ON ai_analysis(analysis_date DESC) WHERE deleted_at IS NULL;
CREATE INDEX idx_ai_analysis_model ON ai_analysis(model_used) WHERE deleted_at IS NULL;

COMMENT ON TABLE ai_analysis IS 'Stored AI reasoning and suggestions per contact. Never a black box.';
COMMENT ON COLUMN ai_analysis.model_used IS 'e.g., "ollama/llama3" or "claude-3-5-sonnet"';
COMMENT ON COLUMN ai_analysis.priority_score IS '0-100 urgency score for contacting this week';
COMMENT ON COLUMN ai_analysis.raw_response IS 'Full AI output for debugging and transparency';

-- =============================================================================
-- PEOPLE (Phase 2+)
-- =============================================================================

CREATE TABLE people (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    email VARCHAR(200),
    preferred_language VARCHAR(10) DEFAULT 'de',
    notes TEXT,
    linked_contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

-- Indexes for common queries
CREATE INDEX idx_people_name ON people(name) WHERE deleted_at IS NULL;
CREATE INDEX idx_people_linked_contact ON people(linked_contact_id) WHERE deleted_at IS NULL;

COMMENT ON TABLE people IS 'Individual collectors. Phase 2+ feature. Table defined now for completeness.';
COMMENT ON COLUMN people.linked_contact_id IS 'Optional link to a venue/gallery in contacts table';

-- =============================================================================
-- FUNCTIONS AND TRIGGERS
-- =============================================================================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_contacts_updated_at
    BEFORE UPDATE ON contacts
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_shows_updated_at
    BEFORE UPDATE ON shows
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_people_updated_at
    BEFORE UPDATE ON people
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- GRANTS
-- =============================================================================

-- Grant all privileges to artcrm_admindude
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO artcrm_admindude;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO artcrm_admindude;

-- =============================================================================
-- VERIFICATION
-- =============================================================================

-- Verify all tables exist
DO $$
DECLARE
    missing_tables TEXT[];
    expected_tables TEXT[] := ARRAY[
        'schema_migrations',
        'lookup_values',
        'contacts',
        'interactions',
        'shows',
        'ai_analysis',
        'people'
    ];
    tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY expected_tables
    LOOP
        IF NOT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name = tbl
        ) THEN
            missing_tables := array_append(missing_tables, tbl);
        END IF;
    END LOOP;

    IF array_length(missing_tables, 1) > 0 THEN
        RAISE EXCEPTION 'Migration failed: missing tables: %', array_to_string(missing_tables, ', ');
    ELSE
        RAISE NOTICE 'Migration 001 successful: all tables created';
    END IF;
END $$;
