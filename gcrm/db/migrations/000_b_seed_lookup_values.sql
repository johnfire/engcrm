-- Art CRM Lookup Values Seed Data
-- Migration: 002_seed_lookup_values.sql
-- Description: Minimal initial seed data for extensible categorical fields
-- Author: Christopher Rehm
-- Date: 2026-02-12

-- Record this migration
INSERT INTO schema_migrations (migration_name, checksum)
VALUES ('002_seed_lookup_values.sql', 'initial_seed');

-- =============================================================================
-- CONTACT TYPES
-- =============================================================================

INSERT INTO lookup_values (category, value, label_de, label_en, sort_order) VALUES
('contact_type', 'gallery', 'Galerie', 'Gallery', 10),
('contact_type', 'cafe', 'Café', 'Café', 20),
('contact_type', 'hotel', 'Hotel', 'Hotel', 30),
('contact_type', 'office', 'Büro', 'Office', 40),
('contact_type', 'restaurant', 'Restaurant', 'Restaurant', 50),
('contact_type', 'coworking_space', 'Coworking Space', 'Coworking Space', 60),
('contact_type', 'online_platform', 'Online-Plattform', 'Online Platform', 70),
('contact_type', 'museum', 'Museum', 'Museum', 80),
('contact_type', 'corporate', 'Firmenkunde', 'Corporate', 90),
('contact_type', 'other', 'Sonstiges', 'Other', 100);

-- =============================================================================
-- CONTACT SUBTYPES
-- =============================================================================

INSERT INTO lookup_values (category, value, label_de, label_en, sort_order) VALUES
('contact_subtype', 'upscale', 'Gehoben', 'Upscale', 10),
('contact_subtype', 'hippy', 'Alternativ', 'Hippy', 20),
('contact_subtype', 'commercial', 'Kommerziell', 'Commercial', 30),
('contact_subtype', 'contemporary', 'Zeitgenössisch', 'Contemporary', 40),
('contact_subtype', 'traditional', 'Traditionell', 'Traditional', 50),
('contact_subtype', 'tourist', 'Touristisch', 'Tourist', 60),
('contact_subtype', 'local', 'Lokal', 'Local', 70);

-- =============================================================================
-- CONTACT STATUS
-- =============================================================================

INSERT INTO lookup_values (category, value, label_de, label_en, sort_order) VALUES
('contact_status', 'cold', 'Kalt (noch nicht kontaktiert)', 'Cold', 10),
('contact_status', 'contacted', 'Kontaktiert', 'Contacted', 20),
('contact_status', 'meeting', 'Termin vereinbart', 'Meeting Scheduled', 30),
('contact_status', 'proposal', 'Vorschlag eingereicht', 'Proposal Sent', 40),
('contact_status', 'accepted', 'Akzeptiert', 'Accepted', 50),
('contact_status', 'rejected', 'Abgelehnt', 'Rejected', 60),
('contact_status', 'dormant', 'Ruhend (>12 Monate)', 'Dormant', 70),
('contact_status', 'on_hold', 'Pausiert', 'On Hold', 80);

-- =============================================================================
-- LANGUAGES
-- =============================================================================

INSERT INTO lookup_values (category, value, label_de, label_en, sort_order) VALUES
('language', 'de', 'Deutsch', 'German', 10),
('language', 'en', 'Englisch', 'English', 20),
('language', 'fr', 'Französisch', 'French', 30),
('language', 'cs', 'Tschechisch', 'Czech', 40),
('language', 'nl', 'Niederländisch', 'Dutch', 50),
('language', 'es', 'Spanisch', 'Spanish', 60),
('language', 'it', 'Italienisch', 'Italian', 70);

-- =============================================================================
-- INTERACTION METHODS
-- =============================================================================

INSERT INTO lookup_values (category, value, label_de, label_en, sort_order) VALUES
('interaction_method', 'email', 'E-Mail', 'Email', 10),
('interaction_method', 'in_person', 'Persönlich', 'In Person', 20),
('interaction_method', 'phone', 'Telefon', 'Phone', 30),
('interaction_method', 'letter', 'Brief', 'Letter', 40),
('interaction_method', 'social_media', 'Social Media', 'Social Media', 50),
('interaction_method', 'unknown', 'Unbekannt', 'Unknown', 100);

-- =============================================================================
-- INTERACTION OUTCOMES
-- =============================================================================

INSERT INTO lookup_values (category, value, label_de, label_en, sort_order) VALUES
('interaction_outcome', 'no_reply', 'Keine Antwort', 'No Reply', 10),
('interaction_outcome', 'interested', 'Interessiert', 'Interested', 20),
('interaction_outcome', 'rejected', 'Abgelehnt', 'Rejected', 30),
('interaction_outcome', 'meeting_set', 'Termin vereinbart', 'Meeting Set', 40),
('interaction_outcome', 'proposal_requested', 'Vorschlag angefordert', 'Proposal Requested', 50),
('interaction_outcome', 'accepted', 'Akzeptiert', 'Accepted', 60),
('interaction_outcome', 'left_material', 'Unterlagen hinterlassen', 'Left Material', 70),
('interaction_outcome', 'follow_up_needed', 'Nachfassen nötig', 'Follow-up Needed', 80),
('interaction_outcome', 'not_interested', 'Nicht interessiert', 'Not Interested', 90);

-- =============================================================================
-- SHOW STATUS
-- =============================================================================

INSERT INTO lookup_values (category, value, label_de, label_en, sort_order) VALUES
('show_status', 'possible', 'Möglich', 'Possible', 10),
('show_status', 'confirmed', 'Bestätigt', 'Confirmed', 20),
('show_status', 'completed', 'Abgeschlossen', 'Completed', 30),
('show_status', 'cancelled', 'Abgesagt', 'Cancelled', 40);

-- =============================================================================
-- VERIFICATION
-- =============================================================================

DO $$
DECLARE
    category_counts RECORD;
    expected_categories TEXT[] := ARRAY[
        'contact_type',
        'contact_subtype',
        'contact_status',
        'language',
        'interaction_method',
        'interaction_outcome',
        'show_status'
    ];
    cat TEXT;
    found_count INTEGER;
BEGIN
    FOREACH cat IN ARRAY expected_categories
    LOOP
        SELECT COUNT(*) INTO found_count
        FROM lookup_values
        WHERE category = cat AND deleted_at IS NULL;

        IF found_count = 0 THEN
            RAISE EXCEPTION 'Migration failed: no values found for category: %', cat;
        ELSE
            RAISE NOTICE 'Category % has % values', cat, found_count;
        END IF;
    END LOOP;

    RAISE NOTICE 'Migration 002 successful: all lookup values seeded';
END $$;

-- =============================================================================
-- SUMMARY
-- =============================================================================

-- Display summary of seeded values
SELECT
    category,
    COUNT(*) as value_count,
    string_agg(value, ', ' ORDER BY sort_order) as values
FROM lookup_values
WHERE deleted_at IS NULL
GROUP BY category
ORDER BY category;
