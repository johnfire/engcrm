-- Private ratings have per-user conflict clocks; shared entity clocks must never mix accounts.
CREATE TABLE sync_private_field_versions (
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    entity_kind TEXT NOT NULL CHECK (entity_kind IN ('organization','person')),
    entity_sync_id UUID NOT NULL,
    field_name TEXT NOT NULL CHECK (field_name IN ('personal_priority','value_rating','short_term_value','long_term_value')),
    changed_at TIMESTAMPTZ NOT NULL, device_id UUID NOT NULL, mutation_id UUID NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('mobile','web','mcp','agent','migration')),
    PRIMARY KEY (workspace_id,user_id,entity_kind,entity_sync_id,field_name)
);
ALTER TABLE sync_private_field_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_private_field_versions FORCE ROW LEVEL SECURITY;
CREATE POLICY workspace_access ON sync_private_field_versions TO engcrm_workspace
    USING (workspace_id = request_workspace_id()) WITH CHECK (workspace_id = request_workspace_id() AND EXISTS (
        SELECT 1 FROM users WHERE users.id=sync_private_field_versions.user_id AND users.workspace_id=sync_private_field_versions.workspace_id
    ));
GRANT SELECT, INSERT, UPDATE, DELETE ON sync_private_field_versions TO engcrm_workspace;

INSERT INTO sync_private_field_versions(workspace_id,user_id,entity_kind,entity_sync_id,field_name,changed_at,device_id,mutation_id,source)
SELECT r.workspace_id,r.user_id,'organization',c.sync_id,fields.name,statement_timestamp(),
       '00000000-0000-0000-0000-000000000000','00000000-0000-0000-0000-000000000000','migration'
  FROM contact_user_priorities r JOIN contacts c ON c.id=r.contact_id
 CROSS JOIN LATERAL (VALUES ('personal_priority',r.priority),('short_term_value',r.short_term_value),('long_term_value',r.long_term_value)) fields(name,value)
 WHERE fields.value IS NOT NULL;
INSERT INTO sync_private_field_versions(workspace_id,user_id,entity_kind,entity_sync_id,field_name,changed_at,device_id,mutation_id,source)
SELECT r.workspace_id,r.user_id,'person',p.sync_id,fields.name,statement_timestamp(),
       '00000000-0000-0000-0000-000000000000','00000000-0000-0000-0000-000000000000','migration'
  FROM person_user_priorities r JOIN people p ON p.id=r.person_id
 CROSS JOIN LATERAL (VALUES ('value_rating',r.priority),('short_term_value',r.short_term_value),('long_term_value',r.long_term_value)) fields(name,value)
 WHERE fields.value IS NOT NULL;

-- Serialize rating writers against mobile clock comparisons, including direct SQL writers.
CREATE FUNCTION lock_private_rating_change() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    values_json JSONB := CASE WHEN TG_OP='DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END;
    target_id UUID;
BEGIN
    IF TG_ARGV[0]='person' THEN
        SELECT sync_id INTO target_id FROM people WHERE id=(values_json->>'person_id')::INTEGER;
    ELSE
        SELECT sync_id INTO target_id FROM contacts WHERE id=(values_json->>'contact_id')::INTEGER;
    END IF;
    IF target_id IS NOT NULL THEN
        PERFORM pg_advisory_xact_lock(hashtextextended(concat('sync-private:',values_json->>'workspace_id',':',
                values_json->>'user_id',':',TG_ARGV[0],':',target_id),0));
    END IF;
    RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END $$;
CREATE TRIGGER contact_rating_sync_lock BEFORE INSERT OR UPDATE OR DELETE ON contact_user_priorities
    FOR EACH ROW EXECUTE FUNCTION lock_private_rating_change('organization');
CREATE TRIGGER person_rating_sync_lock BEFORE INSERT OR UPDATE OR DELETE ON person_user_priorities
    FOR EACH ROW EXECUTE FUNCTION lock_private_rating_change('person');

CREATE OR REPLACE FUNCTION capture_private_rating_change() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    rating_values JSONB := CASE WHEN TG_OP = 'DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END;
    old_values JSONB := CASE WHEN TG_OP = 'INSERT' THEN '{}'::jsonb ELSE to_jsonb(OLD) END;
    new_values JSONB := CASE WHEN TG_OP = 'DELETE' THEN '{}'::jsonb ELSE to_jsonb(NEW) END;
    target_sync_id UUID;
    target_kind TEXT := TG_ARGV[0];
    column_name TEXT;
    sync_field TEXT;
    mobile_time TIMESTAMPTZ := NULLIF(current_setting('app.sync_changed_at', TRUE), '')::TIMESTAMPTZ;
    event_device UUID := NULLIF(current_setting('app.sync_device_id', TRUE), '')::UUID;
    event_mutation UUID := NULLIF(current_setting('app.sync_mutation_id', TRUE), '')::UUID;
    event_source TEXT := CASE WHEN mobile_time IS NOT NULL THEN 'mobile' ELSE CASE current_setting('app.audit_actor_type', TRUE)
                             WHEN 'ai' THEN 'agent' WHEN 'mcp' THEN 'mcp' ELSE 'web' END END;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM users WHERE id=(rating_values->>'user_id')::INTEGER) THEN
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END IF;
    IF target_kind = 'person' THEN
        SELECT sync_id INTO target_sync_id FROM people WHERE id=(rating_values->>'person_id')::INTEGER AND deleted_at IS NULL;
    ELSE
        SELECT sync_id INTO target_sync_id FROM contacts WHERE id=(rating_values->>'contact_id')::INTEGER AND deleted_at IS NULL;
    END IF;
    IF target_sync_id IS NOT NULL THEN
        FOREACH column_name IN ARRAY ARRAY['priority','short_term_value','long_term_value'] LOOP
            IF COALESCE(old_values->column_name, 'null'::jsonb) IS DISTINCT FROM COALESCE(new_values->column_name, 'null'::jsonb) THEN
                sync_field := CASE WHEN column_name='priority' THEN CASE WHEN target_kind='person' THEN 'value_rating' ELSE 'personal_priority' END ELSE column_name END;
                INSERT INTO sync_private_field_versions(workspace_id,user_id,entity_kind,entity_sync_id,field_name,changed_at,device_id,mutation_id,source)
                VALUES ((rating_values->>'workspace_id')::INTEGER,(rating_values->>'user_id')::INTEGER,target_kind,target_sync_id,sync_field,
                        COALESCE(mobile_time,clock_timestamp()),COALESCE(event_device,'00000000-0000-0000-0000-000000000000'),
                        COALESCE(event_mutation,'00000000-0000-0000-0000-000000000000'),event_source)
                ON CONFLICT (workspace_id,user_id,entity_kind,entity_sync_id,field_name) DO UPDATE
                    SET changed_at=EXCLUDED.changed_at,device_id=EXCLUDED.device_id,mutation_id=EXCLUDED.mutation_id,source=EXCLUDED.source;
            END IF;
        END LOOP;
        INSERT INTO sync_entity_changes(workspace_id,entity_kind,entity_sync_id,operation,actor,correlation_id,target_user_id)
        VALUES ((rating_values->>'workspace_id')::INTEGER,target_kind,target_sync_id,'upsert',
                NULLIF(current_setting('app.audit_actor', TRUE), ''),NULLIF(current_setting('app.audit_correlation_id', TRUE), ''),
                (rating_values->>'user_id')::INTEGER);
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END $$;

CREATE FUNCTION erase_private_sync_clocks() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    DELETE FROM sync_private_field_versions WHERE workspace_id=OLD.workspace_id AND entity_kind=TG_ARGV[0] AND entity_sync_id=OLD.sync_id;
    RETURN OLD;
END $$;
CREATE TRIGGER contacts_sync_private_erase AFTER DELETE ON contacts FOR EACH ROW EXECUTE FUNCTION erase_private_sync_clocks('organization');
CREATE TRIGGER people_sync_private_erase AFTER DELETE ON people FOR EACH ROW EXECUTE FUNCTION erase_private_sync_clocks('person');
