-- Serialize sequence assignment per workspace until each writer commits or rolls back.
-- A plain BIGSERIAL default is allocated before commit and can otherwise be skipped.
ALTER TABLE sync_entity_changes ALTER COLUMN sequence DROP DEFAULT;

CREATE FUNCTION assign_sync_change_sequence() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(1937337955, NEW.workspace_id);
    NEW.sequence := nextval('sync_entity_changes_sequence_seq');
    RETURN NEW;
END $$;

CREATE TRIGGER sync_change_sequence_before_insert
BEFORE INSERT ON sync_entity_changes
FOR EACH ROW EXECUTE FUNCTION assign_sync_change_sequence();
