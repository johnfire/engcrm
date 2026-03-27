-- Migration 001: agent system tables
-- Run once against the shared artcrm PostgreSQL database.
-- These tables extend the existing schema without touching any existing tables.

-- Track every agent execution for auditing and the activity feed.
CREATE TABLE IF NOT EXISTS agent_runs (
    id          SERIAL PRIMARY KEY,
    agent_name  VARCHAR(60)  NOT NULL,
    started_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status      VARCHAR(20)  NOT NULL DEFAULT 'running',  -- running | completed | failed
    summary     TEXT,
    input_json  JSONB,
    output_json JSONB
);

-- GDPR consent tracking, one row per contact per event.
-- Append-only: never update rows, only insert.
CREATE TABLE IF NOT EXISTS consent_log (
    id                  SERIAL PRIMARY KEY,
    contact_id          INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    legal_basis         VARCHAR(60) NOT NULL DEFAULT 'legitimate_interest',
    first_contact_date  TIMESTAMPTZ,
    opt_out             BOOLEAN NOT NULL DEFAULT FALSE,
    opt_out_date        TIMESTAMPTZ,
    erasure_requested   BOOLEAN NOT NULL DEFAULT FALSE,
    erasure_date        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Emails drafted by the outreach agent waiting for human approval.
CREATE TABLE IF NOT EXISTS approval_queue (
    id              SERIAL PRIMARY KEY,
    contact_id      INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    agent_run_id    INTEGER REFERENCES agent_runs(id),
    draft_subject   VARCHAR(500) NOT NULL,
    draft_body      TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending | approved | rejected | edited
    reviewed_at     TIMESTAMPTZ,
    reviewer_note   TEXT,
    final_subject   VARCHAR(500),  -- set if human edited before approving
    final_body      TEXT           -- set if human edited before approving
);

-- Incoming emails read from IMAP, cached before processing.
CREATE TABLE IF NOT EXISTS inbox_messages (
    id                  SERIAL PRIMARY KEY,
    message_id          VARCHAR(500) UNIQUE NOT NULL,  -- IMAP Message-ID header
    from_email          VARCHAR(200) NOT NULL,
    subject             VARCHAR(500),
    body                TEXT,
    received_at         TIMESTAMPTZ,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed           BOOLEAN NOT NULL DEFAULT FALSE,
    matched_contact_id  INTEGER REFERENCES contacts(id)
);

-- Add 'candidate' as a valid contact status (non-destructive — just a data insert).
-- Uses ON CONFLICT DO NOTHING so re-running this migration is safe.
INSERT INTO lookup_values (category, value, label_de, label_en, sort_order)
VALUES ('contact_status', 'candidate', 'Kandidat', 'Candidate', 0)
ON CONFLICT (category, value) DO NOTHING;

-- Index for common query patterns.
CREATE INDEX IF NOT EXISTS idx_approval_queue_status  ON approval_queue (status);
CREATE INDEX IF NOT EXISTS idx_agent_runs_name_status ON agent_runs (agent_name, status);
CREATE INDEX IF NOT EXISTS idx_inbox_messages_processed ON inbox_messages (processed);
CREATE INDEX IF NOT EXISTS idx_consent_log_contact    ON consent_log (contact_id);
