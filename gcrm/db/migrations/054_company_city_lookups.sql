-- Cache of "which city is this company in?" lookups (Google Places text search),
-- keyed by the normalized company name. Every outcome is stored, including
-- "not found" and "ambiguous", so a company is never looked up twice (each
-- lookup is a billed API request) and the review queue can show what Google
-- offered. Only company names are sent to Google — never anything about the
-- people who work there.
--
-- outcome: resolved | ambiguous | not_found
CREATE TABLE IF NOT EXISTS company_city_lookups (
    company_key  TEXT PRIMARY KEY,
    outcome      TEXT NOT NULL CHECK (outcome IN ('resolved', 'ambiguous', 'not_found')),
    city         TEXT,
    country      CHAR(2),
    place_id     TEXT,
    candidates   JSONB NOT NULL DEFAULT '[]'::jsonb,   -- [{name, city, country}] as offered
    looked_up_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
