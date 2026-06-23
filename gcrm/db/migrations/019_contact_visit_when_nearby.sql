-- "Drop in when in the area" flag on contacts, set by the follow-up agent's
-- warm-classification path (set_visit_when_nearby). Note: 012 added a
-- visit_when_nearby column on inbox_messages; this is the contacts-level flag
-- that the tooling actually reads/writes.
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS visit_when_nearby BOOLEAN NOT NULL DEFAULT FALSE;
