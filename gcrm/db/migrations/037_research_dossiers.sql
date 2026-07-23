-- Evidence-backed company research dossiers.
-- One active dossier per contact; superseded rows are soft-deleted.
-- Agents query by contact_id WHERE deleted_at IS NULL.
--
-- The dossier is populated by the company research crawler (Crawl4AI primary,
-- Bright Data / HTTP fallback). Agents (opportunity, scout, outreach) call
-- get_or_create_dossier(contact_id) which returns the active dossier or
-- generates one on demand.

CREATE TABLE IF NOT EXISTS research_dossiers (
    id SERIAL PRIMARY KEY,
    contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    official_domain VARCHAR(300),
    company_summary TEXT,
    research_status VARCHAR(40) NOT NULL DEFAULT 'pending',
    -- complete: all requested pages fetched, evidence extracted
    -- partial: some pages failed, but we have usable data
    -- blocked: all fetches failed (robots.txt, paywall, timeout)
    -- no_authoritative_source: no verifiable official website found
    -- pending: queued but not yet started
    research_version VARCHAR(40),
    -- evidence: array of {url, title, retrieved_at, excerpt_hash, source_type, content_summary}
    evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- people: array of {name, role, source_url, confidence (0-100)}
    people JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- person_context: array of {name, context, source_url}
    person_context JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

-- One active dossier per contact.
CREATE UNIQUE INDEX IF NOT EXISTS idx_research_dossiers_active_contact
    ON research_dossiers (contact_id)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_research_dossiers_status
    ON research_dossiers (research_status)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_research_dossiers_created
    ON research_dossiers (created_at DESC)
    WHERE deleted_at IS NULL;

COMMENT ON TABLE research_dossiers IS 'Evidence-backed company research dossiers — one active per contact';
COMMENT ON COLUMN research_dossiers.official_domain IS 'The verified company domain, selected by domain verification';
COMMENT ON COLUMN research_dossiers.company_summary IS 'Short factual description extracted from the official website';
COMMENT ON COLUMN research_dossiers.research_status IS 'complete, partial, blocked, no_authoritative_source, pending';
COMMENT ON COLUMN research_dossiers.research_version IS 'Extraction policy version for reproducibility';
COMMENT ON COLUMN research_dossiers.evidence IS 'Array of {url, title, retrieved_at, excerpt_hash, source_type} objects';
COMMENT ON COLUMN research_dossiers.people IS 'Array of {name, role, source_url, confidence} — only from authoritative sources';
COMMENT ON COLUMN research_dossiers.person_context IS 'Array of {name, context, source_url} — opt-in professional context';
