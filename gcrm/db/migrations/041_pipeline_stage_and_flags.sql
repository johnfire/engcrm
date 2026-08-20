-- Split contacts.status into three independent axes.
--
-- One column held three unrelated things, so they overwrote each other: a
-- bounced address (status='bad_email') erased "meeting booked", and an opt-out
-- erased the pipeline position. After this migration:
--
--   pipeline_stage  candidate | suspect | prospect | opportunity | customer |
--                   not_in_pipeline
--   status          none | ready | contacted | meeting | proposal | dormant |
--                   on_hold | dropped
--   flags           do_not_contact, email_bounced, research_exhausted
--
-- 'cold' becomes 'ready': in this codebase it never meant a cold lead, it meant
-- "scout scored it a good fit, send the first email" — the readiest state there
-- is. Keeping the word next to a stage called 'suspect' would confuse the next
-- reader as it confused this one.
--
-- Re-running this migration must change nothing: every UPDATE below matches
-- only the legacy vocabulary. Without that guard a second run would read the
-- new values, miss every CASE branch, and collapse the whole table to
-- candidate/none.
--
-- No CHECK constraint on either column, deliberately: migration 026 records
-- what happened the last time the database rejected what the agents write while
-- their stderr went to /dev/null. gcrm/contact_state.py is the source of truth
-- and coerces unknown values in the application layer, where the fallback is
-- logged instead of silent.

ALTER TABLE contacts
    ADD COLUMN IF NOT EXISTS pipeline_stage     VARCHAR(60)  NOT NULL DEFAULT 'candidate',
    ADD COLUMN IF NOT EXISTS do_not_contact     BOOLEAN      NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS email_bounced      BOOLEAN      NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS research_exhausted BOOLEAN      NOT NULL DEFAULT FALSE;

-- Raise the flags first, while the old status values are still readable.
UPDATE contacts SET do_not_contact     = TRUE WHERE status IN ('do_not_contact', 'opt_out');
UPDATE contacts SET email_bounced      = TRUE WHERE status = 'bad_email';
UPDATE contacts SET research_exhausted = TRUE WHERE status = 'cannot_find_more_data';

-- An opt-out recorded in the consent log outranks whatever the status column
-- says: it is the legal record, and the status could have been overwritten by
-- any later pipeline move.
UPDATE contacts c SET do_not_contact = TRUE
  FROM consent_log cl
 WHERE cl.contact_id = c.id AND cl.opt_out AND NOT c.do_not_contact;

-- Then place every row on the two new axes.
UPDATE contacts SET
    pipeline_stage = CASE status
        WHEN 'candidate'             THEN 'candidate'
        WHEN 'maybe'                 THEN 'candidate'
        WHEN 'lead_unverified'       THEN 'candidate'
        WHEN 'cannot_find_more_data' THEN 'candidate'
        WHEN 'cold'                  THEN 'suspect'
        WHEN 'contacted'             THEN 'suspect'
        WHEN 'bad_email'             THEN 'suspect'
        WHEN 'networking_visit'      THEN 'prospect'
        WHEN 'dormant'               THEN 'prospect'
        WHEN 'on_hold'               THEN 'prospect'
        WHEN 'meeting'               THEN 'opportunity'
        WHEN 'proposal'              THEN 'opportunity'
        WHEN 'accepted'              THEN 'customer'
        WHEN 'dropped'               THEN 'not_in_pipeline'
        WHEN 'rejected'              THEN 'not_in_pipeline'
        WHEN 'do_not_contact'        THEN 'not_in_pipeline'
        WHEN 'opt_out'               THEN 'not_in_pipeline'
        ELSE 'candidate'
    END,
    status = CASE status
        WHEN 'cold'             THEN 'ready'
        WHEN 'contacted'        THEN 'contacted'
        WHEN 'meeting'          THEN 'meeting'
        WHEN 'proposal'         THEN 'proposal'
        WHEN 'dormant'          THEN 'dormant'
        WHEN 'on_hold'          THEN 'on_hold'
        WHEN 'networking_visit' THEN 'on_hold'
        WHEN 'dropped'          THEN 'dropped'
        WHEN 'rejected'         THEN 'dropped'
        ELSE 'none'
    END,
    updated_at = NOW()
WHERE status IN (
    'candidate', 'maybe', 'lead_unverified', 'cannot_find_more_data', 'cold',
    'contacted', 'bad_email', 'networking_visit', 'dormant', 'on_hold',
    'meeting', 'proposal', 'accepted', 'dropped', 'rejected', 'do_not_contact',
    'opt_out'
);

-- Rows that never had a status at all still need to sit somewhere.
UPDATE contacts SET status = 'none', pipeline_stage = 'candidate', updated_at = NOW()
 WHERE status IS NULL;

-- Any value not named above — a status invented after this migration was
-- written — is left exactly as it is rather than guessed at. It shows up in the
-- data-quality audit as an unusual pair, which is a human's call to make.

CREATE INDEX IF NOT EXISTS idx_contacts_pipeline_stage
    ON contacts(pipeline_stage) WHERE deleted_at IS NULL;

COMMENT ON COLUMN contacts.pipeline_stage IS
    'Where the relationship stands. Values in gcrm/contact_state.py PIPELINE_STAGES.';
COMMENT ON COLUMN contacts.status IS
    'What is happening right now. Values in gcrm/contact_state.py STATUSES.';
