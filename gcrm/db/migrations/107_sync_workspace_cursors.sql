-- Keep the high-water mark even when account erasure removes private events.
CREATE TABLE sync_workspace_cursors (
    workspace_id INTEGER PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    last_sequence BIGINT NOT NULL CHECK (last_sequence >= 0)
);
ALTER TABLE sync_workspace_cursors ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_workspace_cursors FORCE ROW LEVEL SECURITY;
CREATE POLICY workspace_access ON sync_workspace_cursors TO engcrm_workspace
    USING (workspace_id = request_workspace_id()) WITH CHECK (workspace_id = request_workspace_id());
GRANT SELECT, INSERT, UPDATE ON sync_workspace_cursors TO engcrm_workspace;

INSERT INTO sync_workspace_cursors(workspace_id, last_sequence)
SELECT workspace_id, MAX(sequence) FROM sync_entity_changes GROUP BY workspace_id;

CREATE OR REPLACE FUNCTION assign_sync_change_sequence() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(1937337955, NEW.workspace_id);
    NEW.sequence := nextval('sync_entity_changes_sequence_seq');
    INSERT INTO sync_workspace_cursors(workspace_id, last_sequence) VALUES (NEW.workspace_id, NEW.sequence)
    ON CONFLICT (workspace_id) DO UPDATE SET last_sequence = EXCLUDED.last_sequence;
    RETURN NEW;
END $$;
