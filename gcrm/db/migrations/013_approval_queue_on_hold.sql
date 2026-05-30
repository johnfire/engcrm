ALTER TABLE approval_queue
  ADD COLUMN IF NOT EXISTS final_body TEXT;

COMMENT ON COLUMN approval_queue.status IS
  'pending | approved | approved_unsent | rejected | edited | edited_unsent | on_hold';
