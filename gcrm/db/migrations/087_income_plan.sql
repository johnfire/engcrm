-- Migration 087: the plan the forecast measures against. One row per workspace for the income
-- needed per month from sales, and any other income that covers part of it (a payment on a
-- date, repeated monthly): confirmed lines lower the target in the months they arrive, and
-- unconfirmed (possible) ones are only shown. The owner's own figures are data, not code.
CREATE TABLE IF NOT EXISTS income_plan (
    workspace_id INTEGER PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    monthly_need NUMERIC(12, 2) NOT NULL CHECK (monthly_need >= 0),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS other_income (
    id                SERIAL PRIMARY KEY,
    workspace_id      INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    label             TEXT NOT NULL CHECK (length(btrim(label)) > 0),
    amount_eur        NUMERIC(12, 2) NOT NULL CHECK (amount_eur > 0),
    first_received_on DATE NOT NULL,
    payments          SMALLINT NOT NULL CHECK (payments BETWEEN 1 AND 120),
    confirmed         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at        TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_other_income_workspace ON other_income (workspace_id) WHERE deleted_at IS NULL;

DO $$
DECLARE plan_table TEXT;
BEGIN
    FOREACH plan_table IN ARRAY ARRAY['income_plan', 'other_income']
    LOOP
        EXECUTE format('ALTER TABLE %I ALTER COLUMN workspace_id SET DEFAULT request_workspace_id()', plan_table);
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', plan_table);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', plan_table);
        EXECUTE format('DROP POLICY IF EXISTS workspace_isolation ON %I', plan_table);
        EXECUTE format('CREATE POLICY workspace_isolation ON %I USING (workspace_id=request_workspace_id()) '
                       'WITH CHECK (workspace_id=request_workspace_id())', plan_table);
    END LOOP;
END $$;
GRANT SELECT, INSERT, UPDATE, DELETE ON income_plan, other_income TO engcrm_workspace;
GRANT USAGE, SELECT ON SEQUENCE other_income_id_seq TO engcrm_workspace;
