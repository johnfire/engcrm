-- Each logged activity records two separate judgments, several values each:
--   attitude  how they appear to feel about me (was the single `impression`)
--   my_read   how they appear to me: trust, clarity, manner
-- on organization activities (interactions) and person activities
-- (people_interactions). Values are in gcrm/activity_types.py ATTITUDES and
-- MY_READS; adding one means a new migration for these CHECKs.
--
-- interactions.impression is copied into attitude and no longer written; it
-- stays until a later cleanup so the app version still running during a
-- deploy keeps working.

ALTER TABLE interactions ADD COLUMN IF NOT EXISTS attitude TEXT[]
    CHECK (attitude <@ ARRAY['warm', 'neutral', 'cold', 'skeptical']);
ALTER TABLE interactions ADD COLUMN IF NOT EXISTS my_read TEXT[]
    CHECK (my_read <@ ARRAY['trustworthy', 'straightforward', 'cant_tell', 'holding_back',
                            'story_doesnt_add_up', 'not_truthful', 'indecisive', 'confused', 'nh', 'cf']);

ALTER TABLE people_interactions ADD COLUMN IF NOT EXISTS attitude TEXT[]
    CHECK (attitude <@ ARRAY['warm', 'neutral', 'cold', 'skeptical']);
ALTER TABLE people_interactions ADD COLUMN IF NOT EXISTS my_read TEXT[]
    CHECK (my_read <@ ARRAY['trustworthy', 'straightforward', 'cant_tell', 'holding_back',
                            'story_doesnt_add_up', 'not_truthful', 'indecisive', 'confused', 'nh', 'cf']);

UPDATE interactions SET attitude = ARRAY[impression]
 WHERE impression IS NOT NULL AND attitude IS NULL;

COMMENT ON COLUMN interactions.impression IS 'Retired by migration 072 — copied into attitude, no longer written.';
