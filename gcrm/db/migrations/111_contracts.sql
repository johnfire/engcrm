-- Migration 111: contracts. A contract wraps a deal's sales (its payments): value, hours and dates are
-- computed from the payments, never stored here, so the Contracts page and the Forecast cannot disagree.
-- Every sale belongs to a contract; the backfill below makes one for each existing payment series and
-- for each sale that has none. See docs/plans/2026-11-27-contracts-design.md.
-- Safe to run twice: every statement checks what is already there.

CREATE TABLE IF NOT EXISTS contracts (
    id                SERIAL PRIMARY KEY,
    workspace_id      INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    deal_id           INTEGER NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
    title             TEXT NOT NULL CHECK (length(trim(title)) > 0 AND length(title) <= 200),
    -- teaching_course, workshop, consulting, other: checked in the application (gcrm/contract_kinds.py),
    -- like pipeline stages (migration 041), so a new kind needs no migration.
    kind              TEXT NOT NULL DEFAULT 'other',
    assignment        TEXT NOT NULL DEFAULT '' CHECK (length(assignment) <= 20000),
    contact_person_id INTEGER REFERENCES people(id) ON DELETE SET NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at        TIMESTAMPTZ,
    UNIQUE (id, deal_id)
);
CREATE INDEX IF NOT EXISTS idx_contracts_deal ON contracts (workspace_id, deal_id) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS contract_links (
    id           SERIAL PRIMARY KEY,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    contract_id  INTEGER NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    label        TEXT NOT NULL CHECK (length(trim(label)) > 0 AND length(label) <= 200),
    url          TEXT NOT NULL CHECK (url ~* '^https?://' AND length(url) <= 2000),
    sort_order   INTEGER NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_contract_links_contract ON contract_links (contract_id, sort_order, id);

-- Row security like every other table (pattern of migration 099). WITH CHECK also requires each parent to
-- be visible, so a workspace cannot hang a contract on another workspace's deal or person, or a link on
-- another workspace's contract.
ALTER TABLE contracts ENABLE ROW LEVEL SECURITY;
ALTER TABLE contracts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS contracts_workspace ON contracts;
CREATE POLICY contracts_workspace ON contracts TO engcrm_workspace
    USING (workspace_id = request_workspace_id())
    WITH CHECK (workspace_id = request_workspace_id()
        AND EXISTS (SELECT 1 FROM deals d WHERE d.id = deal_id)
        AND (contact_person_id IS NULL OR EXISTS (SELECT 1 FROM people p WHERE p.id = contact_person_id)));
GRANT SELECT, INSERT, UPDATE, DELETE ON contracts TO engcrm_workspace;
GRANT USAGE, SELECT ON SEQUENCE contracts_id_seq TO engcrm_workspace;

ALTER TABLE contract_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE contract_links FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS contract_links_workspace ON contract_links;
CREATE POLICY contract_links_workspace ON contract_links TO engcrm_workspace
    USING (workspace_id = request_workspace_id())
    WITH CHECK (workspace_id = request_workspace_id()
        AND EXISTS (SELECT 1 FROM contracts c WHERE c.id = contract_id));
GRANT SELECT, INSERT, UPDATE, DELETE ON contract_links TO engcrm_workspace;
GRANT USAGE, SELECT ON SEQUENCE contract_links_id_seq TO engcrm_workspace;

ALTER TABLE sales ADD COLUMN IF NOT EXISTS contract_id INTEGER;

-- The backfill is a function so a test can run the very same code on seeded rows. It touches only sales
-- that have no contract yet: one contract per (deal, series) and one per sale without a series.
-- Title: the description, else "<offer> – MM.YYYY" of the first payment's won_on. Kind other. A contract is
-- created when its first payment was, and is deleted only when every one of its payments is. The
-- operator running the migration is not subject to row security. Returns how many contracts it made.
CREATE OR REPLACE FUNCTION backfill_sale_contracts() RETURNS INTEGER LANGUAGE plpgsql AS $$
DECLARE
    pending RECORD;
    made_id INTEGER;
    made INTEGER := 0;
BEGIN
    FOR pending IN
        SELECT s.workspace_id, s.deal_id, s.series_id,
               CASE WHEN s.series_id IS NULL THEN s.id END AS single_id,
               (array_agg(s.description ORDER BY s.series_part NULLS FIRST, s.id))[1] AS description,
               (array_agg(s.won_on ORDER BY s.series_part NULLS FIRST, s.id))[1] AS won_on,
               min(s.created_at) AS created_at,
               CASE WHEN bool_and(s.deleted_at IS NOT NULL) THEN max(s.deleted_at) END AS deleted_at
          FROM sales s
         WHERE s.contract_id IS NULL
         GROUP BY s.workspace_id, s.deal_id, s.series_id, CASE WHEN s.series_id IS NULL THEN s.id END
         ORDER BY min(s.created_at), min(s.id)
    LOOP
        made_id := NULL;
        INSERT INTO contracts (workspace_id, deal_id, title, created_at, updated_at, deleted_at)
        SELECT pending.workspace_id, pending.deal_id,
               left(COALESCE(NULLIF(trim(pending.description), ''),
                             o.name || ' – ' || to_char(pending.won_on, 'MM.YYYY')), 200),
               pending.created_at, pending.created_at, pending.deleted_at
          FROM deals d JOIN offers o ON o.id = d.offer_id
         WHERE d.id = pending.deal_id
        RETURNING id INTO made_id;
        IF made_id IS NULL THEN
            RAISE EXCEPTION 'no deal or offer for the sales of deal %', pending.deal_id;
        END IF;
        UPDATE sales SET contract_id = made_id
         WHERE contract_id IS NULL AND deal_id = pending.deal_id
           AND CASE WHEN pending.series_id IS NULL THEN id = pending.single_id ELSE series_id = pending.series_id END;
        made := made + 1;
    END LOOP;
    RETURN made;
END $$;
REVOKE ALL ON FUNCTION backfill_sale_contracts() FROM PUBLIC;

SELECT backfill_sale_contracts();

ALTER TABLE sales ALTER COLUMN contract_id SET NOT NULL;

-- A payment can never belong to a contract of another deal.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'sales_contract_same_deal') THEN
        ALTER TABLE sales ADD CONSTRAINT sales_contract_same_deal
            FOREIGN KEY (contract_id, deal_id) REFERENCES contracts (id, deal_id) ON DELETE CASCADE;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_sales_contract ON sales (contract_id);
