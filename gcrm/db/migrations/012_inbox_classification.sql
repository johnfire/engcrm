ALTER TABLE inbox_messages
  ADD COLUMN IF NOT EXISTS classification          VARCHAR(60),
  ADD COLUMN IF NOT EXISTS classification_reasoning TEXT,
  ADD COLUMN IF NOT EXISTS visit_when_nearby        BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_inbox_classification
  ON inbox_messages (classification)
  WHERE processed = TRUE;
