-- Business-card capture: staging table for photographed cards.
-- A capture holds the raw image + the Claude-vision extraction, is reviewed/
-- edited on the mobile app, then promoted into `contacts` on confirm.
CREATE TABLE IF NOT EXISTS card_captures (
    id                  SERIAL PRIMARY KEY,
    captured_by         VARCHAR(60),                          -- JWT role/identity of the capturer
    captured_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    image_path          TEXT,                                 -- filename under CARD_IMAGE_DIR
    gps_lat             DOUBLE PRECISION,                     -- nullable; v2 storefront mode
    gps_lng             DOUBLE PRECISION,
    status              VARCHAR(30) NOT NULL DEFAULT 'pending_review', -- pending_review|confirmed|discarded
    extraction_status   VARCHAR(20) NOT NULL DEFAULT 'pending',        -- pending|done|failed
    extracted           JSONB,                                -- raw structured fields from the model
    extraction_model    VARCHAR(60),
    extraction_cost_usd NUMERIC(10,5),
    confidence          SMALLINT,                             -- 0-100, model self-report
    dup_contact_id      INTEGER REFERENCES contacts(id),      -- suggested duplicate (nullable)
    contact_id          INTEGER REFERENCES contacts(id),      -- set when promoted
    error               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_card_captures_status ON card_captures(status);

-- Where a contact originated (analytics + GDPR provenance): card_capture | research | scout | ...
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS source VARCHAR(40);
