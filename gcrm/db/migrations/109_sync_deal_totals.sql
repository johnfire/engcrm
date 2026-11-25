-- Refresh only the derived total on the phone; individual sale values stay on the server.
CREATE FUNCTION capture_sync_sale_total() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    changed JSONB := CASE WHEN TG_OP = 'INSERT' THEN '{}'::jsonb ELSE to_jsonb(OLD) END;
    replacement JSONB := CASE WHEN TG_OP = 'DELETE' THEN '{}'::jsonb ELSE to_jsonb(NEW) END;
    affected RECORD;
BEGIN
    FOR affected IN
        SELECT DISTINCT (item->>'workspace_id')::INTEGER AS workspace_id, (item->>'deal_id')::INTEGER AS deal_id
          FROM (VALUES (changed), (replacement)) AS changes(item)
         WHERE item->>'workspace_id' IS NOT NULL AND item->>'deal_id' IS NOT NULL
    LOOP
        INSERT INTO sync_entity_changes(workspace_id,entity_kind,entity_sync_id,operation,actor,correlation_id)
        SELECT d.workspace_id,'deal',d.sync_id,'upsert',
               NULLIF(current_setting('app.audit_actor', TRUE), ''),
               NULLIF(current_setting('app.audit_correlation_id', TRUE), '')
          FROM deals d WHERE d.workspace_id=affected.workspace_id AND d.id=affected.deal_id AND d.deleted_at IS NULL;
    END LOOP;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END $$;

CREATE TRIGGER sales_sync_total_change AFTER INSERT OR UPDATE OR DELETE ON sales
FOR EACH ROW EXECUTE FUNCTION capture_sync_sale_total();
