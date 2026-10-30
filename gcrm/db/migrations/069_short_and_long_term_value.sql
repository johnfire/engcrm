-- Short- and long-term value join the existing private per-user ratings on
-- organizations (contact_user_priorities) and people (person_user_priorities):
-- 3 high, 2 medium, 1 low, 0 zero, NULL unrated. A row now holds any subset of
-- the three ratings, so priority may be NULL when only a value is rated.
ALTER TABLE contact_user_priorities ALTER COLUMN priority DROP NOT NULL;
ALTER TABLE contact_user_priorities
    ADD COLUMN IF NOT EXISTS short_term_value SMALLINT CHECK (short_term_value BETWEEN 0 AND 3);
ALTER TABLE contact_user_priorities
    ADD COLUMN IF NOT EXISTS long_term_value SMALLINT CHECK (long_term_value BETWEEN 0 AND 3);

ALTER TABLE person_user_priorities ALTER COLUMN priority DROP NOT NULL;
ALTER TABLE person_user_priorities
    ADD COLUMN IF NOT EXISTS short_term_value SMALLINT CHECK (short_term_value BETWEEN 0 AND 3);
ALTER TABLE person_user_priorities
    ADD COLUMN IF NOT EXISTS long_term_value SMALLINT CHECK (long_term_value BETWEEN 0 AND 3);
