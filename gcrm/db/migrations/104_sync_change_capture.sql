-- Person notes need their own workspace identity even after a parent is erased.
ALTER TABLE people_interactions ADD COLUMN workspace_id INTEGER REFERENCES workspaces(id) ON DELETE CASCADE;
UPDATE people_interactions note SET workspace_id = person.workspace_id
  FROM people person WHERE person.id = note.person_id;
ALTER TABLE people_interactions ALTER COLUMN workspace_id SET NOT NULL;

CREATE FUNCTION set_person_note_workspace() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    SELECT workspace_id INTO STRICT NEW.workspace_id FROM people WHERE id = NEW.person_id;
    RETURN NEW;
END $$;
CREATE TRIGGER person_note_workspace_before_write
BEFORE INSERT OR UPDATE OF person_id, workspace_id ON people_interactions
FOR EACH ROW EXECUTE FUNCTION set_person_note_workspace();

ALTER TABLE sync_entity_changes ADD COLUMN merge_target_sync_id UUID;

CREATE FUNCTION capture_sync_change() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    old_values JSONB := CASE WHEN TG_OP = 'INSERT' THEN '{}'::jsonb ELSE to_jsonb(OLD) END;
    new_values JSONB := CASE WHEN TG_OP = 'DELETE' THEN '{}'::jsonb ELSE to_jsonb(NEW) END;
    entity_values JSONB := CASE WHEN TG_OP = 'DELETE' THEN old_values ELSE new_values END;
    change_entity_kind TEXT := TG_ARGV[0];
    changed_field TEXT;
    event_kind TEXT := 'upsert';
    mobile_time TIMESTAMPTZ := NULLIF(current_setting('app.sync_changed_at', TRUE), '')::TIMESTAMPTZ;
    event_device UUID := NULLIF(current_setting('app.sync_device_id', TRUE), '')::UUID;
    event_mutation UUID := NULLIF(current_setting('app.sync_mutation_id', TRUE), '')::UUID;
    event_time TIMESTAMPTZ := COALESCE(mobile_time, clock_timestamp());
    event_actor TEXT := NULLIF(current_setting('app.audit_actor', TRUE), '');
    event_correlation TEXT := NULLIF(current_setting('app.audit_correlation_id', TRUE), '');
    event_source TEXT := CASE WHEN mobile_time IS NOT NULL THEN 'mobile' ELSE CASE current_setting('app.audit_actor_type', TRUE)
                             WHEN 'ai' THEN 'agent' WHEN 'mcp' THEN 'mcp' ELSE 'web' END END;
    target UUID;
    has_changes BOOLEAN := FALSE;
BEGIN
    IF (mobile_time IS NOT NULL OR event_device IS NOT NULL OR event_mutation IS NOT NULL)
       AND (mobile_time IS NULL OR event_device IS NULL OR event_mutation IS NULL) THEN
        RAISE EXCEPTION 'incomplete mobile sync context';
    END IF;
    IF TG_OP = 'DELETE' THEN
        target := NULLIF(current_setting('app.sync_merge_target', TRUE), '')::UUID;
        event_kind := CASE WHEN change_entity_kind = 'person' AND target IS NOT NULL
                           THEN 'merge_redirect' ELSE 'hard_erase' END;
        DELETE FROM sync_field_versions
         WHERE workspace_id = (entity_values->>'workspace_id')::INTEGER
           AND entity_kind = change_entity_kind
           AND entity_sync_id = (entity_values->>'sync_id')::UUID;
        IF event_kind = 'merge_redirect' THEN
            UPDATE provisional_mobile_changes
               SET merge_target_sync_id = target,
                   reason = CASE WHEN status = 'pending' THEN 'merged' ELSE reason END
             WHERE workspace_id = (entity_values->>'workspace_id')::INTEGER
               AND ((entity_kind = 'person' AND entity_sync_id = (entity_values->>'sync_id')::UUID)
                    OR (parent_kind = 'person' AND parent_sync_id = (entity_values->>'sync_id')::UUID)
                    OR merge_target_sync_id = (entity_values->>'sync_id')::UUID);
        END IF;
        IF event_kind = 'hard_erase' THEN
            UPDATE sync_mutations mutation SET status='erased'
             WHERE mutation.workspace_id = (entity_values->>'workspace_id')::INTEGER
               AND mutation.status = 'provisional'
               AND ((mutation.entity_kind = change_entity_kind
                     AND mutation.entity_sync_id = (entity_values->>'sync_id')::UUID)
                    OR EXISTS (SELECT 1 FROM provisional_mobile_changes proposal
                        WHERE proposal.workspace_id = mutation.workspace_id
                          AND proposal.device_id = mutation.device_id AND proposal.mutation_id = mutation.mutation_id
                          AND ((proposal.parent_kind = change_entity_kind
                                AND proposal.parent_sync_id = (entity_values->>'sync_id')::UUID)
                               OR (change_entity_kind = 'person'
                                   AND proposal.merge_target_sync_id = (entity_values->>'sync_id')::UUID))));
            DELETE FROM provisional_mobile_changes
             WHERE workspace_id = (entity_values->>'workspace_id')::INTEGER
               AND ((entity_kind = change_entity_kind
                     AND entity_sync_id = (entity_values->>'sync_id')::UUID)
                    OR (parent_kind = change_entity_kind
                        AND parent_sync_id = (entity_values->>'sync_id')::UUID)
                    OR (change_entity_kind = 'person'
                        AND merge_target_sync_id = (entity_values->>'sync_id')::UUID));
        END IF;
    ELSIF TG_OP = 'UPDATE' AND old_values->>'deleted_at' IS NULL
          AND new_values->>'deleted_at' IS NOT NULL THEN
        event_kind := 'soft_delete';
    END IF;
    IF TG_OP <> 'DELETE' THEN
        FOR changed_field IN SELECT key FROM jsonb_each(new_values)
          WHERE key NOT IN ('id', 'sync_id', 'workspace_id', 'created_at', 'updated_at', 'deleted_at')
            AND (TG_OP = 'INSERT' OR old_values->key IS DISTINCT FROM new_values->key)
        LOOP
            has_changes := TRUE;
            INSERT INTO sync_field_versions(workspace_id, entity_kind, entity_sync_id, field_name,
                                            changed_at, device_id, mutation_id, source)
            VALUES ((entity_values->>'workspace_id')::INTEGER, change_entity_kind,
                    (entity_values->>'sync_id')::UUID, changed_field, event_time,
                    COALESCE(event_device, '00000000-0000-0000-0000-000000000000'),
                    COALESCE(event_mutation, '00000000-0000-0000-0000-000000000000'), event_source)
            ON CONFLICT (workspace_id, entity_kind, entity_sync_id, field_name) DO UPDATE
                SET changed_at = EXCLUDED.changed_at, device_id = EXCLUDED.device_id,
                    mutation_id = EXCLUDED.mutation_id, source = EXCLUDED.source;
        END LOOP;
    END IF;
    IF TG_OP = 'UPDATE' AND NOT has_changes AND old_values->'deleted_at' IS NOT DISTINCT FROM new_values->'deleted_at' THEN
        RETURN NEW;
    END IF;
    INSERT INTO sync_entity_changes(workspace_id, entity_kind, entity_sync_id, operation,
                                    changed_at, actor, correlation_id, merge_target_sync_id,device_id,mutation_id)
    VALUES ((entity_values->>'workspace_id')::INTEGER, change_entity_kind,
            (entity_values->>'sync_id')::UUID, event_kind, event_time,
            event_actor, event_correlation, CASE WHEN event_kind = 'merge_redirect' THEN target END,event_device,event_mutation);
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END $$;

CREATE TRIGGER contacts_sync_change AFTER INSERT OR UPDATE OR DELETE ON contacts
FOR EACH ROW EXECUTE FUNCTION capture_sync_change('organization');
CREATE TRIGGER people_sync_change AFTER INSERT OR UPDATE OR DELETE ON people
FOR EACH ROW EXECUTE FUNCTION capture_sync_change('person');
CREATE TRIGGER deals_sync_change AFTER INSERT OR UPDATE OR DELETE ON deals
FOR EACH ROW EXECUTE FUNCTION capture_sync_change('deal');
CREATE TRIGGER interactions_sync_change AFTER INSERT OR UPDATE OR DELETE ON interactions
FOR EACH ROW EXECUTE FUNCTION capture_sync_change('organization_activity');
CREATE TRIGGER people_interactions_sync_change AFTER INSERT OR UPDATE OR DELETE ON people_interactions
FOR EACH ROW EXECUTE FUNCTION capture_sync_change('person_note');
