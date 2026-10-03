-- Website + address found for a company by searching the web and reading its
-- Impressum / contact page (gcrm.company_web), keyed by normalized company name
-- so a company is never searched twice. Every outcome is stored, with what was
-- found, so the review queue can show a human the website and address that
-- were read and let them accept it with one click.
--
-- outcome   resolved | needs_review | not_found
-- attempts  how many times we searched; a not_found is retried a few times
--           because search engines fail intermittently
CREATE TABLE IF NOT EXISTS company_web_lookups (
    company_key  TEXT PRIMARY KEY,
    outcome      TEXT NOT NULL CHECK (outcome IN ('resolved', 'needs_review', 'not_found')),
    website      TEXT,
    street       TEXT,
    postal_code  TEXT,
    city         TEXT,
    country      CHAR(2),
    source_url   TEXT,
    reason       TEXT,
    candidates   JSONB NOT NULL DEFAULT '[]'::jsonb,
    attempts     INTEGER NOT NULL DEFAULT 1,
    looked_up_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Where an organization's location came from, and the page it was read from.
-- location_source: website | places | manual
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS location_source   TEXT;
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS address_source_url TEXT;
