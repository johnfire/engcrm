-- Migration 113: the income calculator remembers each account's own figures. One row per account.
-- The figures include health, disability and medical amounts, so the application encrypts them
-- before they reach this table, each account reads only its own row, and the emailed data
-- backup leaves the table out. Safe to run twice.
CREATE TABLE IF NOT EXISTS income_calculator_inputs (
    user_id        INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    workspace_id   INTEGER NOT NULL DEFAULT request_workspace_id() REFERENCES workspaces(id) ON DELETE CASCADE,
    data_encrypted TEXT NOT NULL CHECK (length(data_encrypted) <= 20000),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE income_calculator_inputs ENABLE ROW LEVEL SECURITY;
ALTER TABLE income_calculator_inputs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS income_calculator_inputs_workspace ON income_calculator_inputs;
CREATE POLICY income_calculator_inputs_workspace ON income_calculator_inputs TO engcrm_workspace
    USING (workspace_id = request_workspace_id())
    WITH CHECK (workspace_id = request_workspace_id()
        AND EXISTS (SELECT 1 FROM users u WHERE u.id = user_id
                    AND u.workspace_id = income_calculator_inputs.workspace_id));
GRANT SELECT, INSERT, UPDATE, DELETE ON income_calculator_inputs TO engcrm_workspace;
