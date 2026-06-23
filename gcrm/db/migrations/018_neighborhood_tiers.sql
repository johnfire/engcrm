-- Per-neighborhood tier rating, used to bias outreach toward better-fit areas
-- (get_cold_contacts min_tier filter). Tiers are populated by the neighborhood
-- rating scripts; NULL tier is always allowed through.
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS neighborhood_tier TEXT
    CHECK (neighborhood_tier IN ('poor', 'normal', 'wealthy'));

CREATE TABLE IF NOT EXISTS neighborhood_tiers (
    id           SERIAL PRIMARY KEY,
    city         TEXT NOT NULL,
    neighborhood TEXT NOT NULL,
    tier         TEXT NOT NULL CHECK (tier IN ('poor', 'normal', 'wealthy')),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_neighborhood_tiers_city_hood
    ON neighborhood_tiers (lower(city), lower(neighborhood));

CREATE INDEX IF NOT EXISTS idx_contacts_neighborhood_tier
    ON contacts (neighborhood_tier) WHERE deleted_at IS NULL;
