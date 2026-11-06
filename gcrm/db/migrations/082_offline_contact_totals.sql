-- 081 is reserved by the saved runtime-hardening checkpoint.
CREATE TABLE offline_contact_totals (
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    month_start DATE NOT NULL CHECK (EXTRACT(DAY FROM month_start)=1 AND month_start >= DATE '2026-10-01'),
    total INTEGER NOT NULL CHECK (total BETWEEN 0 AND 1000000),
    PRIMARY KEY (workspace_id, month_start)
);
ALTER TABLE offline_contact_totals ENABLE ROW LEVEL SECURITY;
CREATE POLICY workspace_isolation ON offline_contact_totals
    USING (workspace_id=request_workspace_id())
    WITH CHECK (workspace_id=request_workspace_id());
GRANT SELECT, INSERT, UPDATE, DELETE ON offline_contact_totals TO engcrm_workspace;
