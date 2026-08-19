-- Where a person was met — typed by hand on the card-confirm screen before the
-- lead is saved (a venue, event, or occasion; free text, never extracted from
-- the card itself).
ALTER TABLE people ADD COLUMN IF NOT EXISTS met_at TEXT;
