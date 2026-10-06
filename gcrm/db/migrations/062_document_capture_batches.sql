-- Retry the same page upload without creating duplicate review drafts.
ALTER TABLE card_captures ADD COLUMN IF NOT EXISTS capture_batch_id VARCHAR(64);
ALTER TABLE card_captures ADD COLUMN IF NOT EXISTS document_row SMALLINT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_card_capture_document_row
    ON card_captures(capture_batch_id, document_row)
    WHERE capture_batch_id IS NOT NULL;
