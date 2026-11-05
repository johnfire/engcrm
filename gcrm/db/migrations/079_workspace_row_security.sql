-- HTTP and remote-MCP transactions switch to this non-bypass role. Migrations
-- and explicitly invoked maintenance jobs keep the operator connection role.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='engcrm_workspace') THEN
        CREATE ROLE engcrm_workspace NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='engcrm_workspace' AND (rolsuper OR rolbypassrls)) THEN
        RAISE EXCEPTION 'engcrm_workspace must not bypass row security';
    END IF;
    EXECUTE format('GRANT engcrm_workspace TO %I', current_user);
END $$;
GRANT USAGE ON SCHEMA public TO engcrm_workspace;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO engcrm_workspace;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO engcrm_workspace;
REVOKE UPDATE, DELETE ON audit_log FROM engcrm_workspace;
REVOKE INSERT, UPDATE, DELETE ON lookup_values, ignored_chains, schema_migrations FROM engcrm_workspace;

CREATE FUNCTION request_workspace_id() RETURNS INTEGER
LANGUAGE sql STABLE AS $$
    SELECT NULLIF(current_setting('app.workspace_id', TRUE), '')::INTEGER
$$;

-- These lookup histories and suppressions were originally single-workspace.
ALTER TABLE company_city_lookups ADD COLUMN workspace_id INTEGER REFERENCES workspaces(id);
ALTER TABLE company_web_lookups ADD COLUMN workspace_id INTEGER REFERENCES workspaces(id);
ALTER TABLE neighborhood_tiers ADD COLUMN workspace_id INTEGER REFERENCES workspaces(id);
ALTER TABLE person_import_suppressions ADD COLUMN workspace_id INTEGER REFERENCES workspaces(id);

DO $$
DECLARE
    owned_table RECORD;
    relation RECORD;
    default_workspace INTEGER;
    visibility TEXT;
    parent_condition TEXT;
BEGIN
    SELECT id INTO STRICT default_workspace FROM workspaces WHERE slug='default';
    FOR owned_table IN
        SELECT c.oid, c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relkind='r'
          AND c.relname NOT IN ('schema_migrations','lookup_values','ignored_chains')
    LOOP
        visibility := '';
        IF owned_table.relname='workspaces' THEN
            visibility := 'id=request_workspace_id()';
        ELSIF EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid=owned_table.oid AND attname='workspace_id' AND NOT attisdropped) THEN
            EXECUTE format('UPDATE %I SET workspace_id=%s WHERE workspace_id IS NULL', owned_table.relname, default_workspace);
            EXECUTE format('ALTER TABLE %I ALTER COLUMN workspace_id SET DEFAULT COALESCE(request_workspace_id(),%s)', owned_table.relname, default_workspace);
            visibility := 'workspace_id=request_workspace_id()';
        END IF;
        -- Related records without workspace_id follow their visible parent.
        -- WITH CHECK also blocks writing a local row with a foreign parent ID.
        FOR relation IN
            SELECT a.attname AS child_column, p.relname AS parent_table, b.attname AS parent_column
            FROM pg_constraint fk
            JOIN pg_class p ON p.oid=fk.confrelid
            JOIN pg_attribute a ON a.attrelid=fk.conrelid AND a.attnum=fk.conkey[1]
            JOIN pg_attribute b ON b.attrelid=fk.confrelid AND b.attnum=fk.confkey[1]
            WHERE fk.contype='f' AND fk.conrelid=owned_table.oid
              AND p.relname NOT IN ('workspaces','lookup_values','ignored_chains')
              AND array_length(fk.conkey,1)=1
        LOOP
            parent_condition := format('(%1$I IS NULL OR EXISTS (SELECT 1 FROM %2$I parent_scope WHERE parent_scope.%3$I=%4$I.%1$I))',
                relation.child_column, relation.parent_table, relation.parent_column, owned_table.relname);
            visibility := concat_ws(' AND ', NULLIF(visibility,''), parent_condition);
        END LOOP;
        IF visibility <> '' THEN
            EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', owned_table.relname);
            EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', owned_table.relname);
            EXECUTE format('CREATE POLICY workspace_access ON %I TO engcrm_workspace USING (%s) WITH CHECK (%s)',
                           owned_table.relname, visibility, visibility);
        END IF;
    END LOOP;
END $$;
