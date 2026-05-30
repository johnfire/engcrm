-- =============================================================================
-- Migration 003: Add 'lead_unverified' Status for Lead Scout
-- =============================================================================
-- Phase 6-Alpha: Lead generation system needs a status for auto-discovered venues
-- that haven't been manually verified yet.
--
-- Created: 2026-02-12

-- Add new status for leads discovered by scout
INSERT INTO lookup_values (category, value, label_de, label_en, sort_order, active)
VALUES ('contact_status', 'lead_unverified', 'Lead (ungeprüft)', 'Lead (Unverified)', 5, TRUE)
ON CONFLICT (category, value) DO NOTHING;

-- Also add some additional subtypes that AI might infer
INSERT INTO lookup_values (category, value, label_de, label_en, sort_order, active) VALUES
('contact_subtype', 'alternative', 'Alternativ', 'Alternative', 75, TRUE),
('contact_subtype', 'corporate', 'Geschäftlich', 'Corporate', 80, TRUE),
('contact_subtype', 'indie', 'Unabhängig', 'Indie', 85, TRUE),
('contact_subtype', 'boutique', 'Boutique', 'Boutique', 90, TRUE),
('contact_subtype', 'chain', 'Kette', 'Chain', 95, TRUE)
ON CONFLICT (category, value) DO NOTHING;
