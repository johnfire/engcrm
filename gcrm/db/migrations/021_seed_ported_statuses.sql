-- Statuses used by ported features:
--   networking_visit      — follow-up "warm" path (interested but no opportunity yet)
--   bad_email             — bounce handling (address undeliverable)
--   cannot_find_more_data — research/enrichment dead-end (no web presence found)
-- Status is free-text on contacts; these rows provide the UI dropdown labels.
INSERT INTO lookup_values (category, value, label_de, label_en, sort_order, active) VALUES
    ('contact_status', 'networking_visit',      'Netzwerk-Besuch',       'Networking Visit', 15, TRUE),
    ('contact_status', 'bad_email',             'Ungültige E-Mail',      'Bad Email',        16, TRUE),
    ('contact_status', 'cannot_find_more_data', 'Keine Daten auffindbar', 'No Data Found',   17, TRUE)
ON CONFLICT (category, value) DO NOTHING;
