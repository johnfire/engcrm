-- Migration 112: a Help Centre article about contracts, seeded for the default workspace as the first articles
-- were (migration 036). Web only: the phone has no contracts yet. ON CONFLICT DO NOTHING, so an article someone
-- has edited under Help is never overwritten. The line breaks in the bodies are real ones.
INSERT INTO help_articles (workspace_id, slug, category, surfaces, status, title_en, title_de,
                           summary_en, summary_de, body_en, body_de, published_at)
SELECT id, 'contracts', 'general', ARRAY['web'], 'published',
    'Contracts', 'Verträge',
    'What a contract is, how to create one and where to find it.',
    'Was ein Vertrag ist, wie man ihn anlegt und wo man ihn findet.',
    'A contract is one agreement with a customer. It keeps what we agreed to do (the assignment), links to the material, and the payments. Its value, hours, rate and dates are worked out from the payments, so they always match the Forecast. The dates are the days of work; without them, the days the payments are due; without those, the day it was agreed.

To create one, open the customer (an organization or a person) and use New contract: a title, a kind, the amount and, if you know it, when it is due. Monthly payments make one contract with several payments.

The Contracts page lists them as Running now, Upcoming and Finished; the finished ones stay closed until you open them. A contract whose payments are all cancelled is marked cancelled and counts in no total.

On a contract''s own page you can write the assignment, choose the contact person, add links, add or change payments, and delete the contract. Deleting it removes its payments too, also from the Forecast. Only an admin can make changes.',
    'Ein Vertrag ist eine Vereinbarung mit einem Kunden. Er hält fest, was zugesagt wurde (den Auftrag), die Links zu den Unterlagen und die Zahlungen. Wert, Stunden, Stundensatz und Zeitraum ergeben sich aus den Zahlungen und stimmen deshalb immer mit der Prognose überein. Der Zeitraum sind die Arbeitstage; fehlen sie, die Fälligkeiten der Zahlungen; fehlen auch diese, der Tag des Abschlusses.

Zum Anlegen öffnen Sie den Kunden (Organisation oder Person) und wählen „Neuer Vertrag“: Titel, Art, Betrag und, wenn bekannt, die Fälligkeit. Monatliche Zahlungen ergeben einen Vertrag mit mehreren Zahlungen.

Die Seite „Verträge“ zeigt sie unter Laufend, Anstehend und Beendet; die beendeten bleiben zugeklappt, bis Sie sie öffnen. Ein Vertrag, dessen Zahlungen alle storniert sind, ist als storniert markiert und zählt in keiner Summe mit.

Auf der Seite eines Vertrags schreiben Sie den Auftrag auf, wählen die Ansprechperson, fügen Links hinzu, ergänzen oder ändern Zahlungen und löschen den Vertrag. Beim Löschen verschwinden auch seine Zahlungen, ebenso aus der Prognose. Änderungen kann nur ein Admin vornehmen.',
    NOW()
FROM workspaces WHERE slug = 'default'
ON CONFLICT (workspace_id, slug) DO NOTHING;
