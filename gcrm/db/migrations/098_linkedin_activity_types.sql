-- Migration 098: LinkedIn message as an activity type (a message I sent). A reply from them is recorded with the
-- method 'linkedin_reply' but is not work, so it has no minutes and is not in the minutes table.
-- The per-workspace minutes table still allowed only the six original types, so saving minutes for post_mail
-- (added later) was refused too. Allow every type in gcrm/activity_types.py ACTIVITY_TYPES.
ALTER TABLE activity_minute_defaults DROP CONSTRAINT IF EXISTS activity_minute_defaults_activity_type_check;
ALTER TABLE activity_minute_defaults ADD CONSTRAINT activity_minute_defaults_activity_type_check CHECK (
    activity_type IN ('drop_in', 'meeting', 'phone', 'video', 'email', 'post_mail', 'linkedin', 'note'));
