-- Assign every existing workspace-owned CRM record to the original workspace.
-- Constraints and RLS are deliberately added in the subsequent application
-- release after every query has been workspace-scoped.
DO $$
DECLARE
    default_workspace_id INTEGER;
    table_name TEXT;
    workspace_tables TEXT[] := ARRAY[
        'contacts', 'interactions', 'shows', 'ai_analysis', 'people',
        'agent_runs', 'consent_log', 'approval_queue', 'inbox_messages',
        'research_queue', 'cities', 'city_scans', 'outreach_outcomes',
        'run_costs', 'push_tokens', 'card_captures', 'audit_log'
    ];
BEGIN
    SELECT id INTO default_workspace_id FROM workspaces WHERE slug = 'default';
    IF default_workspace_id IS NULL THEN
        RAISE EXCEPTION 'Default workspace is required before tenant backfill';
    END IF;

    FOREACH table_name IN ARRAY workspace_tables LOOP
        IF to_regclass(table_name) IS NOT NULL THEN
            EXECUTE format(
                'ALTER TABLE %I ADD COLUMN IF NOT EXISTS workspace_id INTEGER REFERENCES workspaces(id)',
                table_name
            );
            EXECUTE format(
                'UPDATE %I SET workspace_id = $1 WHERE workspace_id IS NULL',
                table_name
            ) USING default_workspace_id;
            EXECUTE format(
                'CREATE INDEX IF NOT EXISTS %I ON %I (workspace_id)',
                'idx_' || table_name || '_workspace_id', table_name
            );
        END IF;
    END LOOP;
END $$;
