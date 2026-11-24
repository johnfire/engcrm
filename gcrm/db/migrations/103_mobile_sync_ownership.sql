-- A visible workspace row cannot refer to a user from another workspace.
ALTER POLICY workspace_access ON mobile_sync_devices
    WITH CHECK (workspace_id = request_workspace_id() AND EXISTS (
        SELECT 1 FROM users WHERE users.id = mobile_sync_devices.user_id
          AND users.workspace_id = mobile_sync_devices.workspace_id
    ));

ALTER POLICY workspace_access ON provisional_mobile_changes
    WITH CHECK (workspace_id = request_workspace_id() AND EXISTS (
        SELECT 1 FROM users WHERE users.id = provisional_mobile_changes.user_id
          AND users.workspace_id = provisional_mobile_changes.workspace_id
    ) AND (reviewed_by IS NULL OR EXISTS (
        SELECT 1 FROM users WHERE users.id = provisional_mobile_changes.reviewed_by
          AND users.workspace_id = provisional_mobile_changes.workspace_id
    )));
