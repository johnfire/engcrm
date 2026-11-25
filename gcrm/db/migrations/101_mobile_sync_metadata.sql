-- Sync metadata contains identities and clocks; domain values stay in domain tables.
CREATE TABLE mobile_sync_devices (
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_id UUID NOT NULL,
    server_environment TEXT NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    revoked_at TIMESTAMPTZ,
    app_version TEXT NOT NULL,
    schema_version INTEGER NOT NULL CHECK (schema_version >= 0),
    PRIMARY KEY (workspace_id, user_id, device_id, server_environment)
);

CREATE TABLE sync_entity_changes (
    sequence BIGSERIAL PRIMARY KEY,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    entity_kind TEXT NOT NULL CHECK (entity_kind IN
        ('organization', 'person', 'deal', 'organization_activity', 'person_note')),
    entity_sync_id UUID NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('upsert', 'soft_delete', 'hard_erase', 'merge_redirect')),
    changed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    mutation_id UUID,
    device_id UUID,
    actor TEXT,
    correlation_id TEXT
);
CREATE INDEX sync_entity_changes_workspace_sequence ON sync_entity_changes(workspace_id, sequence);

CREATE TABLE sync_field_versions (
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    entity_kind TEXT NOT NULL CHECK (entity_kind IN
        ('organization', 'person', 'deal', 'organization_activity', 'person_note')),
    entity_sync_id UUID NOT NULL,
    field_name TEXT NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL,
    device_id UUID NOT NULL,
    mutation_id UUID NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('mobile', 'web', 'mcp', 'agent', 'migration')),
    PRIMARY KEY (workspace_id, entity_kind, entity_sync_id, field_name)
);

CREATE TABLE sync_mutations (
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_id UUID NOT NULL,
    mutation_id UUID NOT NULL,
    entity_kind TEXT NOT NULL CHECK (entity_kind IN
        ('organization', 'person', 'deal', 'organization_activity', 'person_note')),
    entity_sync_id UUID NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('create', 'update')),
    request_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN
        ('applied', 'partially_applied', 'ignored_older', 'provisional', 'rejected_validation', 'rejected_clock', 'erased')),
    winning_fields TEXT[] NOT NULL DEFAULT '{}',
    ignored_fields TEXT[] NOT NULL DEFAULT '{}',
    server_id BIGINT,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    actor TEXT,
    correlation_id TEXT,
    PRIMARY KEY (workspace_id, device_id, mutation_id)
);

CREATE TABLE provisional_mobile_changes (
    id BIGSERIAL PRIMARY KEY,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_id UUID NOT NULL,
    mutation_id UUID NOT NULL,
    entity_kind TEXT NOT NULL CHECK (entity_kind IN
        ('organization', 'person', 'deal', 'organization_activity', 'person_note')),
    entity_sync_id UUID NOT NULL,
    parent_kind TEXT CHECK (parent_kind IN ('organization', 'person')),
    parent_sync_id UUID,
    reason TEXT NOT NULL CHECK (reason IN ('soft_deleted', 'merged')),
    patch JSONB,
    changed_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    expires_at TIMESTAMPTZ NOT NULL,
    merge_target_sync_id UUID,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'applied', 'recreated', 'discarded', 'expired')),
    reviewed_at TIMESTAMPTZ,
    reviewed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    decision TEXT,
    UNIQUE (workspace_id, device_id, mutation_id),
    CHECK (status NOT IN ('discarded', 'expired') OR patch IS NULL),
    CHECK ((parent_kind IS NULL) = (parent_sync_id IS NULL))
);

DO $$
DECLARE sync_table TEXT;
BEGIN
    FOREACH sync_table IN ARRAY ARRAY['mobile_sync_devices', 'sync_entity_changes',
        'sync_field_versions', 'sync_mutations', 'provisional_mobile_changes'] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', sync_table);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', sync_table);
        EXECUTE format('CREATE POLICY workspace_access ON %I TO engcrm_workspace '
            'USING (workspace_id = request_workspace_id()) '
            'WITH CHECK (workspace_id = request_workspace_id())', sync_table);
        EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON %I TO engcrm_workspace', sync_table);
    END LOOP;
END $$;
REVOKE UPDATE, DELETE ON sync_entity_changes FROM engcrm_workspace;
GRANT USAGE, SELECT ON SEQUENCE sync_entity_changes_sequence_seq TO engcrm_workspace;
GRANT USAGE, SELECT ON SEQUENCE provisional_mobile_changes_id_seq TO engcrm_workspace;
