-- Undo migration 064 so the code from before offers and deals can run again.
--
-- Use only when rolling the application back to a release older than the
-- offers-and-deals phase 1. Copy this file to /opt/engcrm on the VPS and run it
-- before starting the old image:
--   sudo docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d gcrm -v ON_ERROR_STOP=1' \
--       < rollback_064_offers_and_deals.sql
--
-- Nothing is lost: each organization's and person's Consulting deal is copied
-- back into the columns the old code reads, including every stage change made
-- since the deploy. Deals for other offers have nowhere to go in the old schema
-- and are dropped with the deals table — before phase 2 there are none.
-- schema_migrations forgets 064, so the next deploy of the new code runs it
-- again and rebuilds the deals from the restored columns.
BEGIN;

ALTER TABLE contacts RENAME COLUMN legacy_pipeline_stage TO pipeline_stage;
ALTER TABLE contacts RENAME COLUMN legacy_status         TO status;
ALTER TABLE people   RENAME COLUMN legacy_pipeline_stage TO pipeline_stage;
ALTER TABLE people   RENAME COLUMN legacy_next_step      TO next_step;
ALTER TABLE people   RENAME COLUMN legacy_next_step_date TO next_step_date;

UPDATE contacts c
   SET pipeline_stage = d.pipeline_stage, status = d.status
  FROM deals d
 WHERE d.contact_id = c.id AND d.deleted_at IS NULL
   AND d.offer_id = offer_id_for(c.workspace_id, 'consulting');

-- A person without a live Consulting deal has no stage and no next step.
UPDATE people p
   SET pipeline_stage = d.pipeline_stage, next_step = d.next_step, next_step_date = d.next_step_date
  FROM deals d
 WHERE d.person_id = p.id AND d.deleted_at IS NULL
   AND d.offer_id = offer_id_for(p.workspace_id, 'consulting');
UPDATE people p
   SET pipeline_stage = NULL, next_step = NULL, next_step_date = NULL
 WHERE NOT EXISTS (SELECT 1 FROM deals d
                    WHERE d.person_id = p.id AND d.deleted_at IS NULL
                      AND d.offer_id = offer_id_for(p.workspace_id, 'consulting'));

CREATE TRIGGER contacts_stage_history
    AFTER UPDATE OF pipeline_stage ON contacts
    FOR EACH ROW WHEN (NEW.pipeline_stage IS DISTINCT FROM OLD.pipeline_stage)
    EXECUTE FUNCTION record_stage_change('organization');
CREATE TRIGGER people_stage_history
    AFTER UPDATE OF pipeline_stage ON people
    FOR EACH ROW WHEN (NEW.pipeline_stage IS DISTINCT FROM OLD.pipeline_stage)
    EXECUTE FUNCTION record_stage_change('person');

-- The old snapshot writer has no offer: keep the consulting rows, restore the old key.
DELETE FROM pipeline_snapshots WHERE offer_id <> offer_id_for(workspace_id, 'consulting');
ALTER TABLE pipeline_snapshots DROP CONSTRAINT pipeline_snapshots_pkey;
ALTER TABLE pipeline_snapshots DROP COLUMN offer_id;
ALTER TABLE pipeline_snapshots ADD CONSTRAINT pipeline_snapshots_pkey
    PRIMARY KEY (workspace_id, day, entity_type, stage);

-- Stage history keeps its rows; the new columns go.
ALTER TABLE stage_changes DROP COLUMN deal_id;
ALTER TABLE stage_changes DROP COLUMN offer_id;

DROP TABLE deals;
DROP FUNCTION record_deal_stage_change();
DROP TRIGGER workspaces_seed_offers ON workspaces;
DROP FUNCTION seed_workspace_offers();
DROP FUNCTION offer_id_for(INTEGER, TEXT);
DROP TABLE offers;

DELETE FROM schema_migrations WHERE migration_name = '064_offers_and_deals.sql';

COMMIT;
