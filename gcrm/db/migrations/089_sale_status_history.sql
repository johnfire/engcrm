-- Migration 089: write down every status a sale has had, with the time, so a graph can later show the
-- pipeline as it stood on any past day. Written by triggers, so no screen, script or agent can forget it.
-- A sale that already exists gets one starting row (no earlier status, its current one) dated when it
-- was entered: what happened to it before today was never recorded and is not guessed.
CREATE TABLE IF NOT EXISTS sale_status_changes (
    id           BIGSERIAL PRIMARY KEY,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    sale_id      INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
    from_status  TEXT,
    to_status    TEXT NOT NULL,
    changed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sale_status_changes_sale ON sale_status_changes (sale_id, id);
CREATE INDEX IF NOT EXISTS idx_sale_status_changes_when ON sale_status_changes (workspace_id, changed_at);

-- Seeded before row security is switched on, so a non-superuser owner can still write the rows.
INSERT INTO sale_status_changes (workspace_id, sale_id, from_status, to_status, changed_at)
SELECT s.workspace_id, s.id, NULL, s.status, s.created_at
  FROM sales s
 WHERE NOT EXISTS (SELECT 1 FROM sale_status_changes c WHERE c.sale_id = s.id);

CREATE OR REPLACE FUNCTION record_sale_status_change() RETURNS trigger AS $$
BEGIN
    INSERT INTO sale_status_changes (workspace_id, sale_id, from_status, to_status)
    VALUES (NEW.workspace_id, NEW.id, CASE WHEN TG_OP = 'INSERT' THEN NULL ELSE OLD.status END, NEW.status);
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS sales_status_history_insert ON sales;
CREATE TRIGGER sales_status_history_insert
    AFTER INSERT ON sales
    FOR EACH ROW EXECUTE FUNCTION record_sale_status_change();

DROP TRIGGER IF EXISTS sales_status_history_update ON sales;
CREATE TRIGGER sales_status_history_update
    AFTER UPDATE OF status ON sales
    FOR EACH ROW WHEN (NEW.status IS DISTINCT FROM OLD.status)
    EXECUTE FUNCTION record_sale_status_change();

ALTER TABLE sale_status_changes ALTER COLUMN workspace_id SET DEFAULT request_workspace_id();
ALTER TABLE sale_status_changes ENABLE ROW LEVEL SECURITY;
ALTER TABLE sale_status_changes FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workspace_isolation ON sale_status_changes;
CREATE POLICY workspace_isolation ON sale_status_changes
    USING (workspace_id = request_workspace_id()) WITH CHECK (workspace_id = request_workspace_id());
GRANT SELECT, INSERT ON sale_status_changes TO engcrm_workspace;
GRANT USAGE, SELECT ON SEQUENCE sale_status_changes_id_seq TO engcrm_workspace;
