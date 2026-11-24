-- Rating values are private to one account; only that account needs the refresh event.
ALTER TABLE sync_entity_changes ADD COLUMN target_user_id INTEGER REFERENCES users(id) ON DELETE CASCADE;

CREATE FUNCTION capture_private_rating_change() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    rating_values JSONB := CASE WHEN TG_OP = 'DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END;
    target_sync_id UUID;
    target_kind TEXT := TG_ARGV[0];
BEGIN
    IF NOT EXISTS (SELECT 1 FROM users WHERE id = (rating_values->>'user_id')::INTEGER) THEN
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END IF;
    IF target_kind = 'person' THEN
        SELECT sync_id INTO target_sync_id FROM people
         WHERE id = (rating_values->>'person_id')::INTEGER AND deleted_at IS NULL;
    ELSE
        SELECT sync_id INTO target_sync_id FROM contacts
         WHERE id = (rating_values->>'contact_id')::INTEGER AND deleted_at IS NULL;
    END IF;
    IF target_sync_id IS NOT NULL THEN
        INSERT INTO sync_entity_changes(workspace_id, entity_kind, entity_sync_id, operation,
                                        actor, correlation_id, target_user_id)
        VALUES ((rating_values->>'workspace_id')::INTEGER, target_kind, target_sync_id, 'upsert',
                NULLIF(current_setting('app.audit_actor', TRUE), ''),
                NULLIF(current_setting('app.audit_correlation_id', TRUE), ''),
                (rating_values->>'user_id')::INTEGER);
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END $$;

CREATE TRIGGER contact_rating_sync_change AFTER INSERT OR UPDATE OR DELETE ON contact_user_priorities
FOR EACH ROW EXECUTE FUNCTION capture_private_rating_change('organization');
CREATE TRIGGER person_rating_sync_change AFTER INSERT OR UPDATE OR DELETE ON person_user_priorities
FOR EACH ROW EXECUTE FUNCTION capture_private_rating_change('person');
