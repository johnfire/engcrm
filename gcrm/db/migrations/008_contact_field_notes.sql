ALTER TABLE contacts
    ADD COLUMN IF NOT EXISTS access_notes             text,
    ADD COLUMN IF NOT EXISTS visit_duration           varchar(100),
    ADD COLUMN IF NOT EXISTS decision_maker           varchar(200),
    ADD COLUMN IF NOT EXISTS first_impression         varchar(20),
    ADD COLUMN IF NOT EXISTS last_impression          varchar(20),
    ADD COLUMN IF NOT EXISTS price_sensitivity        text,
    ADD COLUMN IF NOT EXISTS space_notes              text,
    ADD COLUMN IF NOT EXISTS preferred_contact_method varchar(60),
    ADD COLUMN IF NOT EXISTS last_visited_at          date,
    ADD COLUMN IF NOT EXISTS materials_left           text,
    ADD COLUMN IF NOT EXISTS followup_promised        text;
