-- Approval records the last outbound outreach time on the contact.
ALTER TABLE contacts
ADD COLUMN IF NOT EXISTS last_emailed_at TIMESTAMPTZ;
