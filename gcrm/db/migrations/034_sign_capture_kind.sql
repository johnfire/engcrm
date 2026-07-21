-- Storefront-sign captures reuse card_captures (same photo -> vision -> confirm
-- pipeline) rather than a parallel table. `kind` distinguishes a photographed
-- business card from a photographed storefront sign; place_id/place_json record
-- the Google Place resolved from the sign's business name + GPS, so the confirm
-- screen can show a specific match and the user can accept or reject it before
-- a contact is created.
ALTER TABLE card_captures ADD COLUMN IF NOT EXISTS kind       VARCHAR(10) NOT NULL DEFAULT 'card';
ALTER TABLE card_captures ADD COLUMN IF NOT EXISTS place_id   VARCHAR(120);
ALTER TABLE card_captures ADD COLUMN IF NOT EXISTS place_json JSONB;

CREATE INDEX IF NOT EXISTS idx_card_captures_kind ON card_captures(kind);
