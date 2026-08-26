-- people.workspace_id was added by migration 032's dynamic backfill, but
-- save_person() never set it on INSERT (unlike save_organization(), which
-- has always done so) — so every person created since has workspace_id
-- NULL. That silently breaks any workspace-scoped check on a person, e.g.
-- set_person_value_rating()'s `p.workspace_id = u.workspace_id` match,
-- which can never succeed against NULL. save_person() now sets it going
-- forward (see db_people.py); this backfills the existing rows.
UPDATE people
SET workspace_id = (SELECT id FROM workspaces WHERE slug = 'default')
WHERE workspace_id IS NULL;
