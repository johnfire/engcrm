-- German+English UI support: an account-level interface language (distinct
-- from contacts.preferred_language / people.preferred_language, which pick
-- the language the AI drafts OUTREACH in for a given business — unrelated).
ALTER TABLE users ADD COLUMN IF NOT EXISTS ui_language VARCHAR(5) NOT NULL DEFAULT 'en';
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_ui_language_check;
ALTER TABLE users ADD CONSTRAINT users_ui_language_check CHECK (ui_language IN ('en', 'de'));

-- Push tokens weren't previously tied to an account (send_push_to_all
-- broadcasts to every device, by design, for team-wide lead notifications).
-- A language-change push must reach only that account's own devices.
ALTER TABLE push_tokens ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id);
