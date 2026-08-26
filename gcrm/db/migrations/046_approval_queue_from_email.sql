-- Let a held draft carry its own sender identity, chosen when the draft is
-- created (or changed on review). NULL means "use the configured default"
-- (MAIL_FROM_EMAIL) at send time — every existing row stays that way.
ALTER TABLE approval_queue ADD COLUMN IF NOT EXISTS from_email VARCHAR(200);
