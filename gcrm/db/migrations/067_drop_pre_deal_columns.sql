-- Migration 067: phase 5 of offers and deals — drop what the deals replaced.
-- See docs/plans/2026-10-10-offers-and-deals-design.md (phase 5).
--
-- 1. sales.contact_id goes: a sale belongs to a deal, and the deal names the
--    organization. A sale with no deal yet (recorded while its organization had
--    no Consulting deal) first gets one: the organization's Consulting deal,
--    live or the latest removed one, or a new removed Consulting deal when it
--    never had one. Removed, so no organization re-enters a pipeline it left;
--    the sale keeps its organization and counts as consulting, as before.
-- 2. The legacy_* columns migration 064 retired go. Their indexes go with them.
--
-- Safe to re-run: each step only acts while the column it changes is there.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_name = 'sales' AND column_name = 'contact_id') THEN
        INSERT INTO deals (workspace_id, offer_id, contact_id, pipeline_stage, status, deleted_at)
        SELECT DISTINCT c.workspace_id, offer_id_for(c.workspace_id, 'consulting'), c.id,
               'candidate', 'none', NOW()
          FROM sales s JOIN contacts c ON c.id = s.contact_id
         WHERE s.deal_id IS NULL
           AND NOT EXISTS (SELECT 1 FROM deals d
                            WHERE d.contact_id = c.id
                              AND d.offer_id = offer_id_for(c.workspace_id, 'consulting'));

        UPDATE sales s SET deal_id = (
            SELECT d.id FROM deals d JOIN contacts c ON c.id = d.contact_id
             WHERE d.contact_id = s.contact_id
               AND d.offer_id = offer_id_for(c.workspace_id, 'consulting')
             ORDER BY d.deleted_at IS NOT NULL, d.deleted_at DESC, d.id DESC
             LIMIT 1)
         WHERE s.deal_id IS NULL;

        ALTER TABLE sales ALTER COLUMN deal_id SET NOT NULL;
        ALTER TABLE sales DROP COLUMN contact_id;
    END IF;
END $$;

ALTER TABLE contacts DROP COLUMN IF EXISTS legacy_pipeline_stage;
ALTER TABLE contacts DROP COLUMN IF EXISTS legacy_status;
ALTER TABLE people   DROP COLUMN IF EXISTS legacy_pipeline_stage;
ALTER TABLE people   DROP COLUMN IF EXISTS legacy_next_step;
ALTER TABLE people   DROP COLUMN IF EXISTS legacy_next_step_date;
