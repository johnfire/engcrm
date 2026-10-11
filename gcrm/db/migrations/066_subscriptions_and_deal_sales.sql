-- Migration 066: money per offer — subscriptions on deals, sales on deals.
-- See docs/plans/2026-10-10-offers-and-deals-design.md (phase 3).

-- Recurring revenue on a deal. A price change ends one row and starts another,
-- so past months keep their real amount. ended_on is the last day paid for
-- (inclusive); NULL while it runs.
CREATE TABLE IF NOT EXISTS subscriptions (
    id               SERIAL PRIMARY KEY,
    workspace_id     INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    deal_id          INTEGER NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
    amount_eur_month NUMERIC(12, 2) NOT NULL CHECK (amount_eur_month > 0),
    started_on       DATE NOT NULL,
    ended_on         DATE,
    note             TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at       TIMESTAMPTZ,
    CONSTRAINT subscriptions_ends_after_start CHECK (ended_on IS NULL OR ended_on >= started_on)
);
CREATE INDEX IF NOT EXISTS idx_subscriptions_deal ON subscriptions (deal_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_subscriptions_period
    ON subscriptions (workspace_id, started_on, ended_on) WHERE deleted_at IS NULL;

-- A one-off sale belongs to a deal, so it knows its offer. Every sale so far was
-- consulting: it goes to its organization's Consulting deal (which the 064
-- backfill gave every organization). contact_id stays until phase 5.
ALTER TABLE sales ADD COLUMN IF NOT EXISTS deal_id INTEGER REFERENCES deals(id) ON DELETE CASCADE;
UPDATE sales s SET deal_id = d.id
  FROM contacts c
  JOIN deals d ON d.contact_id = c.id AND d.deleted_at IS NULL
              AND d.offer_id = offer_id_for(c.workspace_id, 'consulting')
 WHERE c.id = s.contact_id AND s.deal_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_sales_deal ON sales (deal_id) WHERE deleted_at IS NULL;
