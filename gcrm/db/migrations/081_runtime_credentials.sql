-- The app connects as this role; only the isolated migration job keeps the
-- operator credentials. Request transactions still SET ROLE engcrm_workspace.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='engcrm_app') THEN
        CREATE ROLE engcrm_app NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
            NOREPLICATION NOBYPASSRLS NOINHERIT;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='engcrm_app'
               AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls OR rolinherit)) THEN
        RAISE EXCEPTION 'engcrm_app must be a limited runtime role';
    END IF;
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO engcrm_app', current_database());
END $$;
GRANT engcrm_workspace TO engcrm_app;
GRANT USAGE ON SCHEMA public TO engcrm_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO engcrm_app;

-- Authentication necessarily precedes establishment of a workspace. Only these
-- account/session tables are available in that phase, never CRM records or DDL.
GRANT SELECT, INSERT, UPDATE ON users, web_sessions, password_reset_tokens,
    account_invitations, mcp_tokens TO engcrm_app;
GRANT SELECT ON workspaces TO engcrm_app;
GRANT INSERT ON audit_log TO engcrm_app;

DO $$
DECLARE authentication_table TEXT;
BEGIN
    FOREACH authentication_table IN ARRAY ARRAY['users','web_sessions','password_reset_tokens',
                                                'account_invitations','mcp_tokens']
    LOOP
        EXECUTE format('CREATE POLICY runtime_authentication ON %I TO engcrm_app USING (TRUE) WITH CHECK (TRUE)',
                       authentication_table);
    END LOOP;
END $$;
CREATE POLICY runtime_workspace_lookup ON workspaces FOR SELECT TO engcrm_app USING (TRUE);
CREATE POLICY runtime_authentication_audit ON audit_log FOR INSERT TO engcrm_app WITH CHECK (TRUE);
