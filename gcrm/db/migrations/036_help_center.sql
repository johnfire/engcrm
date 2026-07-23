-- Editable, bilingual customer guidance. Content is workspace-owned so a
-- future tenant can tailor help without exposing another customer's material.
CREATE TABLE IF NOT EXISTS help_articles (
    id SERIAL PRIMARY KEY,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
    slug TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'general',
    surfaces TEXT[] NOT NULL DEFAULT ARRAY['web', 'mobile'],
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published')),
    title_en TEXT NOT NULL DEFAULT '',
    title_de TEXT NOT NULL DEFAULT '',
    summary_en TEXT NOT NULL DEFAULT '',
    summary_de TEXT NOT NULL DEFAULT '',
    body_en TEXT NOT NULL DEFAULT '',
    body_de TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ,
    UNIQUE (workspace_id, slug)
);

CREATE TABLE IF NOT EXISTS help_tour_progress (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tour_key TEXT NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, tour_key)
);

CREATE TABLE IF NOT EXISTS help_feedback (
    id SERIAL PRIMARY KEY,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
    article_id INTEGER NOT NULL REFERENCES help_articles(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    helpful BOOLEAN NOT NULL,
    comment TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_help_articles_published
    ON help_articles (workspace_id, status, category);

INSERT INTO help_articles (workspace_id, slug, category, status, title_en, title_de, summary_en, summary_de, body_en, body_de)
SELECT id, 'getting-started', 'getting-started', 'published',
    'Getting started safely', 'Sicher starten',
    'Understand the customer workflow before changing or sending anything.', 'Den Kundenablauf verstehen, bevor etwas geändert oder versendet wird.',
    'EngCRM helps you research potential customers, keep contact context, and prepare outreach. Research and AI analysis can suggest information, but they do not send a first email. Review every draft in Approvals before sending it.\n\nUse Contacts to inspect a lead, Research to queue discovery work, and Inbox to record replies.',
    'EngCRM hilft Ihnen, potenzielle Kunden zu recherchieren, Kontaktkontext zu pflegen und Ansprache vorzubereiten. Recherche und KI-Analyse können Informationen vorschlagen, versenden aber keine erste E-Mail. Prüfen Sie jeden Entwurf unter Freigaben, bevor Sie ihn versenden.\n\nUnter Kontakte prüfen Sie Leads, unter Recherche starten Sie die Suche und unter Posteingang erfassen Sie Antworten.'
FROM workspaces WHERE slug = 'default'
ON CONFLICT (workspace_id, slug) DO NOTHING;

INSERT INTO help_articles (workspace_id, slug, category, status, title_en, title_de, summary_en, summary_de, body_en, body_de)
SELECT id, 'approvals', 'outreach', 'published',
    'Reviewing outreach safely', 'Ansprache sicher prüfen',
    'Every first-contact email stays queued until a person approves it.', 'Jede erste Kontakt-E-Mail bleibt in der Warteschlange, bis eine Person sie freigibt.',
    'Approvals are drafts, not sent messages. Check the recipient, personalization, and proposed next step. Approve only when the message is accurate and appropriate. Rejecting a draft does not contact the customer.',
    'Freigaben sind Entwürfe, keine versendeten Nachrichten. Prüfen Sie Empfänger, Personalisierung und den vorgeschlagenen nächsten Schritt. Geben Sie nur frei, wenn die Nachricht korrekt und passend ist. Das Ablehnen eines Entwurfs kontaktiert den Kunden nicht.'
FROM workspaces WHERE slug = 'default'
ON CONFLICT (workspace_id, slug) DO NOTHING;
