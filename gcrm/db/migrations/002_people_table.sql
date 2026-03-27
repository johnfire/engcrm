-- People table for individual contacts (friends, collectors, artists, collaborators)
-- Separate from the business contacts pipeline

CREATE TABLE IF NOT EXISTS people (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    city        TEXT,
    country     TEXT DEFAULT 'DE',
    email       TEXT,
    phone       TEXT,
    website     TEXT,
    relationship TEXT,   -- e.g. artist_friend, collector, collaborator
    notes       TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Add columns that may be missing if table was created previously
ALTER TABLE people ADD COLUMN IF NOT EXISTS city        TEXT;
ALTER TABLE people ADD COLUMN IF NOT EXISTS country     TEXT DEFAULT 'DE';
ALTER TABLE people ADD COLUMN IF NOT EXISTS phone       TEXT;
ALTER TABLE people ADD COLUMN IF NOT EXISTS website     TEXT;
ALTER TABLE people ADD COLUMN IF NOT EXISTS relationship TEXT;
