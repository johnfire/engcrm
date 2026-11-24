-- Give records created before change capture a baseline clock without changing their data.
WITH entities AS (
    SELECT workspace_id, sync_id, 'organization' AS kind, to_jsonb(contacts) AS fields FROM contacts
    UNION ALL SELECT workspace_id, sync_id, 'person', to_jsonb(people) FROM people
    UNION ALL SELECT workspace_id, sync_id, 'deal', to_jsonb(deals) FROM deals
    UNION ALL SELECT workspace_id, sync_id, 'organization_activity', to_jsonb(interactions) FROM interactions
    UNION ALL SELECT workspace_id, sync_id, 'person_note', to_jsonb(people_interactions) FROM people_interactions
)
INSERT INTO sync_field_versions(workspace_id, entity_kind, entity_sync_id, field_name,
                                changed_at, device_id, mutation_id, source)
SELECT entities.workspace_id, entities.kind, entities.sync_id, field.name,
       statement_timestamp(), '00000000-0000-0000-0000-000000000000',
       '00000000-0000-0000-0000-000000000000', 'migration'
  FROM entities CROSS JOIN LATERAL jsonb_object_keys(entities.fields) AS field(name)
 WHERE field.name NOT IN ('id', 'sync_id', 'workspace_id', 'created_at', 'updated_at', 'deleted_at')
ON CONFLICT (workspace_id, entity_kind, entity_sync_id, field_name) DO NOTHING;
