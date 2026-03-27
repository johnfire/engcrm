-- Tracks which city/industry combinations have been researched and when.
-- The supervisor picks the next batch of unresearched (or oldest) entries each run.

CREATE TABLE IF NOT EXISTS research_queue (
    id          SERIAL PRIMARY KEY,
    city        TEXT NOT NULL,
    industry    TEXT NOT NULL,
    country     TEXT NOT NULL DEFAULT 'DE',
    last_run_at TIMESTAMPTZ,
    run_count   INT NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (city, industry)
);
