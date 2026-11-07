-- Migration 084: scheduled data backups. One schedule per workspace, and the last few
-- generated copies so an admin can download them again. See
-- docs/plans/2026-11-07-scheduled-backup-design.md.
--   recipient_user_id  must be an active admin of the same workspace (checked in code), so a
--                      stolen session cannot point the backups at a stranger's address.
--   next_run_at        NULL while frequency = 'off'.
CREATE TABLE IF NOT EXISTS backup_schedules (
    workspace_id      INTEGER PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    frequency         TEXT NOT NULL DEFAULT 'off' CHECK (frequency IN ('off', 'daily', 'weekly')),
    weekday           SMALLINT NOT NULL DEFAULT 0 CHECK (weekday BETWEEN 0 AND 6),
    at_time           TIME NOT NULL DEFAULT '03:00',
    timezone          TEXT NOT NULL DEFAULT 'Europe/Berlin',
    recipient_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    next_run_at       TIMESTAMPTZ,
    last_run_at       TIMESTAMPTZ,
    last_status       TEXT CHECK (last_status IN ('sent', 'link', 'failed')),
    last_error        TEXT,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS backup_files (
    id           SERIAL PRIMARY KEY,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    filename     TEXT NOT NULL,
    size_bytes   INTEGER NOT NULL,
    content      BYTEA NOT NULL,
    manifest     JSONB NOT NULL,
    kind         TEXT NOT NULL DEFAULT 'scheduled' CHECK (kind IN ('scheduled', 'manual')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_backup_files_workspace ON backup_files (workspace_id, created_at DESC);

DO $$
DECLARE backup_table TEXT;
BEGIN
    FOREACH backup_table IN ARRAY ARRAY['backup_schedules', 'backup_files']
    LOOP
        EXECUTE format('ALTER TABLE %I ALTER COLUMN workspace_id SET DEFAULT request_workspace_id()', backup_table);
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', backup_table);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', backup_table);
        EXECUTE format('DROP POLICY IF EXISTS workspace_isolation ON %I', backup_table);
        EXECUTE format('CREATE POLICY workspace_isolation ON %I USING (workspace_id=request_workspace_id()) '
                       'WITH CHECK (workspace_id=request_workspace_id())', backup_table);
    END LOOP;
END $$;
GRANT SELECT, INSERT, UPDATE, DELETE ON backup_schedules, backup_files TO engcrm_workspace;
GRANT USAGE, SELECT ON SEQUENCE backup_files_id_seq TO engcrm_workspace;
