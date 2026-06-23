-- Chains/brands to permanently ignore when scouting contacts. Any new contact
-- whose name is >= ~90% similar to an entry here is silently skipped by the
-- research agent (and save_contact). Seed with chains relevant to your vertical;
-- left empty by default since the right blocklist is vertical-specific.
CREATE TABLE IF NOT EXISTS ignored_chains (
    id         SERIAL PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    reason     TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
