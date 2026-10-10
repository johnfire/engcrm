-- Migration 064: offers and deals — one CRM, several things to sell.
-- See docs/plans/2026-10-10-offers-and-deals-design.md (phase 1).
--
-- Until now one stage per organization and per person silently meant "where we
-- stand on consulting". A contact can now be pitched several offers, each with
-- its own stage, so the stage moves off the contact and onto a deal: one row per
-- offer per organization (or per person, for someone with no organization).
--
-- Every existing stage becomes a Consulting deal. The old columns are renamed
-- to legacy_* rather than dropped: nothing reads them any more, and a query the
-- move missed fails loudly instead of quietly showing a stale stage. They stay
-- until phase 5 so scripts/rollback_064_offers_and_deals.sql can put them back.
--
-- Re-running this migration changes nothing: tables and indexes use IF NOT
-- EXISTS, seeds use ON CONFLICT, and the backfill and rename run only while the
-- old column names still exist.

-- What is for sale, per workspace. Code and agents refer to an offer by slug.
CREATE TABLE IF NOT EXISTS offers (
    id           SERIAL PRIMARY KEY,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    slug         TEXT NOT NULL,
    name         TEXT NOT NULL,
    website      TEXT,
    revenue_kind TEXT NOT NULL DEFAULT 'one_off' CHECK (revenue_kind IN ('one_off', 'subscription')),
    sort_order   INTEGER NOT NULL DEFAULT 0,
    archived_at  TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, slug)
);

-- Every workspace sells at least what the agents work for: consulting. A new
-- workspace gets it from this trigger, so no signup path can forget it.
CREATE OR REPLACE FUNCTION seed_workspace_offers() RETURNS trigger AS $$
BEGIN
    INSERT INTO offers (workspace_id, slug, name, revenue_kind, sort_order)
    VALUES (NEW.id, 'consulting', 'Consulting', 'one_off', 10)
    ON CONFLICT (workspace_id, slug) DO NOTHING;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS workspaces_seed_offers ON workspaces;
CREATE TRIGGER workspaces_seed_offers
    AFTER INSERT ON workspaces
    FOR EACH ROW EXECUTE FUNCTION seed_workspace_offers();

INSERT INTO offers (workspace_id, slug, name, revenue_kind, sort_order)
SELECT id, 'consulting', 'Consulting', 'one_off', 10 FROM workspaces
ON CONFLICT (workspace_id, slug) DO NOTHING;

-- Christopher's own apps, in his workspace only.
INSERT INTO offers (workspace_id, slug, name, revenue_kind, sort_order)
SELECT w.id, o.slug, o.name, 'subscription', o.sort_order
  FROM workspaces w
 CROSS JOIN (VALUES ('learnwohl', 'LearnWohl', 20),
                    ('leguild', 'LeGuild.art', 30),
                    ('notes-world', 'notes-world', 40)) AS o(slug, name, sort_order)
 WHERE w.slug = 'default'
ON CONFLICT (workspace_id, slug) DO NOTHING;

-- The offer with this slug in this workspace. A record without a workspace
-- belongs to the default one, the same rule save_organization applies.
CREATE OR REPLACE FUNCTION offer_id_for(ws INTEGER, offer_slug TEXT) RETURNS INTEGER AS $$
    SELECT id FROM offers
     WHERE slug = offer_slug
       AND workspace_id = COALESCE(ws, (SELECT id FROM workspaces WHERE slug = 'default'))
$$ LANGUAGE sql STABLE;

-- One offer, one contact. The owner is either an organization (contact_id) or a
-- person with no organization in the CRM (person_id), never both. An
-- organization's deal can name a contact person; deleting that person only
-- clears the name, while deleting an owner deletes its deals.
CREATE TABLE IF NOT EXISTS deals (
    id                SERIAL PRIMARY KEY,
    workspace_id      INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    offer_id          INTEGER NOT NULL REFERENCES offers(id),
    contact_id        INTEGER REFERENCES contacts(id) ON DELETE CASCADE,
    person_id         INTEGER REFERENCES people(id) ON DELETE CASCADE,
    contact_person_id INTEGER REFERENCES people(id) ON DELETE SET NULL,
    pipeline_stage    TEXT NOT NULL DEFAULT 'candidate',
    status            TEXT NOT NULL DEFAULT 'none',
    next_step         TEXT,
    next_step_date    DATE,
    notes             TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at        TIMESTAMPTZ,
    CONSTRAINT deals_one_owner CHECK ((contact_id IS NULL) <> (person_id IS NULL)),
    CONSTRAINT deals_contact_person_on_organization CHECK (contact_person_id IS NULL OR contact_id IS NOT NULL)
);

-- No CHECK on stage or status, deliberately — see migration 041.
COMMENT ON COLUMN deals.pipeline_stage IS 'Values in gcrm/organization_state.py PIPELINE_STAGES.';
COMMENT ON COLUMN deals.status IS 'Values in gcrm/organization_state.py STATUSES.';

CREATE UNIQUE INDEX IF NOT EXISTS idx_deals_offer_organization
    ON deals (offer_id, contact_id) WHERE contact_id IS NOT NULL AND deleted_at IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_deals_offer_person
    ON deals (offer_id, person_id) WHERE person_id IS NOT NULL AND deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_deals_stage
    ON deals (workspace_id, offer_id, pipeline_stage) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_deals_contact_person
    ON deals (contact_person_id) WHERE contact_person_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_deals_next_step_date
    ON deals (next_step_date) WHERE next_step_date IS NOT NULL AND deleted_at IS NULL;

DROP TRIGGER IF EXISTS update_deals_updated_at ON deals;
CREATE TRIGGER update_deals_updated_at
    BEFORE UPDATE ON deals
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Stage history now comes from deals. The row still names the owner in
-- entity_type/entity_id, so existing statistics queries keep working; offer_id
-- and deal_id say which pipeline moved. Everything recorded before today was
-- consulting.
ALTER TABLE stage_changes ADD COLUMN IF NOT EXISTS offer_id INTEGER REFERENCES offers(id) ON DELETE CASCADE;
ALTER TABLE stage_changes ADD COLUMN IF NOT EXISTS deal_id  INTEGER REFERENCES deals(id) ON DELETE SET NULL;
UPDATE stage_changes SET offer_id = offer_id_for(workspace_id, 'consulting') WHERE offer_id IS NULL;

CREATE OR REPLACE FUNCTION record_deal_stage_change() RETURNS trigger AS $$
BEGIN
    INSERT INTO stage_changes (entity_type, entity_id, workspace_id, from_stage, to_stage, offer_id, deal_id)
    VALUES (CASE WHEN NEW.contact_id IS NOT NULL THEN 'organization' ELSE 'person' END,
            COALESCE(NEW.contact_id, NEW.person_id), NEW.workspace_id,
            OLD.pipeline_stage, NEW.pipeline_stage, NEW.offer_id, NEW.id);
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS deals_stage_history ON deals;
CREATE TRIGGER deals_stage_history
    AFTER UPDATE OF pipeline_stage ON deals
    FOR EACH ROW WHEN (NEW.pipeline_stage IS DISTINCT FROM OLD.pipeline_stage)
    EXECUTE FUNCTION record_deal_stage_change();

DROP TRIGGER IF EXISTS contacts_stage_history ON contacts;
DROP TRIGGER IF EXISTS people_stage_history ON people;

-- The daily pipeline log counts deals per offer. Every snapshot so far was consulting.
ALTER TABLE pipeline_snapshots ADD COLUMN IF NOT EXISTS offer_id INTEGER REFERENCES offers(id) ON DELETE CASCADE;
UPDATE pipeline_snapshots SET offer_id = offer_id_for(workspace_id, 'consulting') WHERE offer_id IS NULL;
ALTER TABLE pipeline_snapshots ALTER COLUMN offer_id SET NOT NULL;
ALTER TABLE pipeline_snapshots DROP CONSTRAINT IF EXISTS pipeline_snapshots_pkey;
ALTER TABLE pipeline_snapshots ADD CONSTRAINT pipeline_snapshots_pkey
    PRIMARY KEY (workspace_id, day, offer_id, entity_type, stage);

-- Backfill, then retire the old columns. Guarded on the old name so a re-run
-- (when the columns are already legacy_*) skips both.
DO $$
DECLARE
    organization_deals INTEGER;
    person_deals       INTEGER;
    next_step_only     INTEGER;
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'contacts'
                  AND column_name = 'pipeline_stage') THEN
        -- Every organization, soft-deleted ones included, so restoring an
        -- organization brings its stage back with it.
        INSERT INTO deals (workspace_id, offer_id, contact_id, pipeline_stage, status, created_at, updated_at)
        SELECT COALESCE(c.workspace_id, (SELECT id FROM workspaces WHERE slug = 'default')),
               offer_id_for(c.workspace_id, 'consulting'), c.id,
               COALESCE(NULLIF(c.pipeline_stage, ''), 'candidate'),
               COALESCE(NULLIF(c.status, ''), 'none'),
               COALESCE(c.created_at, NOW()), COALESCE(c.updated_at, NOW())
          FROM contacts c
         WHERE NOT EXISTS (SELECT 1 FROM deals d
                            WHERE d.contact_id = c.id AND d.deleted_at IS NULL
                              AND d.offer_id = offer_id_for(c.workspace_id, 'consulting'));
        GET DIAGNOSTICS organization_deals = ROW_COUNT;

        -- People with a stage. A person's stage and their employer's stage were
        -- separate facts, and they stay separate deals. Someone with a next step
        -- but no stage gets a candidate deal so the next step is not lost.
        SELECT COUNT(*) INTO next_step_only FROM people
         WHERE NULLIF(pipeline_stage, '') IS NULL
           AND (NULLIF(btrim(next_step), '') IS NOT NULL OR next_step_date IS NOT NULL);

        INSERT INTO deals (workspace_id, offer_id, person_id, pipeline_stage, status,
                           next_step, next_step_date, created_at, updated_at)
        SELECT COALESCE(p.workspace_id, (SELECT id FROM workspaces WHERE slug = 'default')),
               offer_id_for(p.workspace_id, 'consulting'), p.id,
               COALESCE(NULLIF(p.pipeline_stage, ''), 'candidate'), 'none',
               NULLIF(btrim(p.next_step), ''), p.next_step_date,
               COALESCE(p.created_at, NOW()), COALESCE(p.updated_at, NOW())
          FROM people p
         WHERE (NULLIF(p.pipeline_stage, '') IS NOT NULL
                OR NULLIF(btrim(p.next_step), '') IS NOT NULL OR p.next_step_date IS NOT NULL)
           AND NOT EXISTS (SELECT 1 FROM deals d
                            WHERE d.person_id = p.id AND d.deleted_at IS NULL
                              AND d.offer_id = offer_id_for(p.workspace_id, 'consulting'));
        GET DIAGNOSTICS person_deals = ROW_COUNT;

        ALTER TABLE contacts RENAME COLUMN pipeline_stage TO legacy_pipeline_stage;
        ALTER TABLE contacts RENAME COLUMN status         TO legacy_status;
        ALTER TABLE people   RENAME COLUMN pipeline_stage TO legacy_pipeline_stage;
        ALTER TABLE people   RENAME COLUMN next_step      TO legacy_next_step;
        ALTER TABLE people   RENAME COLUMN next_step_date TO legacy_next_step_date;

        RAISE NOTICE 'offers and deals: % organization deals, % person deals (% people had a next step but no stage; they are now candidates)',
            organization_deals, person_deals, next_step_only;
    END IF;
END $$;

COMMENT ON COLUMN contacts.legacy_pipeline_stage IS 'Retired by migration 064 — the stage lives on deals. Dropped in phase 5.';
COMMENT ON COLUMN contacts.legacy_status IS 'Retired by migration 064 — the status lives on deals. Dropped in phase 5.';
COMMENT ON COLUMN people.legacy_pipeline_stage IS 'Retired by migration 064 — the stage lives on deals. Dropped in phase 5.';
COMMENT ON COLUMN people.legacy_next_step IS 'Retired by migration 064 — the next step lives on deals. Dropped in phase 5.';
COMMENT ON COLUMN people.legacy_next_step_date IS 'Retired by migration 064 — the next step lives on deals. Dropped in phase 5.';
