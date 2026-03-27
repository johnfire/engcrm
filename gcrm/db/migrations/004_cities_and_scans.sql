-- Migration 004: cities table + city_scans table
-- Replaces research_queue with a proper city registry and per-level scan tracking.
-- research_queue is kept intact — data is migrated, not deleted.

-- ---------------------------------------------------------------------------
-- Cities master table
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS cities (
    id          SERIAL PRIMARY KEY,
    city        VARCHAR(100) NOT NULL,
    country     CHAR(2)      NOT NULL DEFAULT 'DE',
    region      VARCHAR(100),
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE(city, country)
);

-- ---------------------------------------------------------------------------
-- City scans: one row per city × level
-- Level 1: galleries, cafes, interior designers, coworking spaces
-- Level 2: gift shops, esoteric/wellness shops, concept stores
-- Level 3: independent restaurants
-- Level 4: corporate offices / headquarters
-- Level 5: hotels
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS city_scans (
    id              SERIAL PRIMARY KEY,
    city_id         INTEGER     NOT NULL REFERENCES cities(id) ON DELETE CASCADE,
    level           SMALLINT    NOT NULL CHECK (level BETWEEN 1 AND 5),
    last_run_at     TIMESTAMPTZ,
    contacts_found  INTEGER     NOT NULL DEFAULT 0,
    run_count       INTEGER     NOT NULL DEFAULT 0,
    due_for_rerun   BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(city_id, level)
);

-- ---------------------------------------------------------------------------
-- Seed cities from the master targets list
-- ---------------------------------------------------------------------------

INSERT INTO cities (city, country, region) VALUES
    -- Bavaria: immediate area
    ('Augsburg',                 'DE', 'Bavaria'),
    ('Königsbrunn',              'DE', 'Bavaria'),
    ('Pfaffenhofen an der Ilm',  'DE', 'Bavaria'),
    ('Olching',                  'DE', 'Bavaria'),
    ('Friedberg',                'DE', 'Bavaria'),
    ('Germering',                'DE', 'Bavaria'),
    ('Fürstenfeldbruck',         'DE', 'Bavaria'),
    ('Dachau',                   'DE', 'Bavaria'),
    ('Landsberg am Lech',        'DE', 'Bavaria'),
    -- Bavaria: wider ring
    ('Munich',                   'DE', 'Bavaria'),
    ('Kaufbeuren',               'DE', 'Bavaria'),
    ('Erding',                   'DE', 'Bavaria'),
    ('Memmingen',                'DE', 'Bavaria'),
    ('Kempten',                  'DE', 'Bavaria'),
    ('Garmisch-Partenkirchen',   'DE', 'Bavaria'),
    ('Wangen im Allgäu',         'DE', 'Bavaria'),
    ('Landshut',                 'DE', 'Bavaria'),
    ('Rosenheim',                'DE', 'Bavaria'),
    ('Ingolstadt',               'DE', 'Bavaria'),
    ('Lindau',                   'DE', 'Bavaria'),
    -- Baden-Württemberg: Ulm area
    ('Ulm',                      'DE', 'Baden-Württemberg'),
    ('Neu-Ulm',                  'DE', 'Baden-Württemberg'),
    ('Ehingen',                  'DE', 'Baden-Württemberg'),
    ('Biberach an der Riss',     'DE', 'Baden-Württemberg'),
    ('Heidenheim an der Brenz',  'DE', 'Baden-Württemberg'),
    ('Geislingen an der Steige', 'DE', 'Baden-Württemberg'),
    -- Baden-Württemberg: Swabian Alb / northeast
    ('Aalen',                    'DE', 'Baden-Württemberg'),
    ('Schwäbisch Gmünd',         'DE', 'Baden-Württemberg'),
    ('Schwäbisch Hall',          'DE', 'Baden-Württemberg'),
    ('Crailsheim',               'DE', 'Baden-Württemberg'),
    ('Öhringen',                 'DE', 'Baden-Württemberg'),
    ('Neckarsulm',               'DE', 'Baden-Württemberg'),
    ('Göppingen',                'DE', 'Baden-Württemberg'),
    -- Baden-Württemberg: Stuttgart metro
    ('Stuttgart',                'DE', 'Baden-Württemberg'),
    ('Esslingen am Neckar',      'DE', 'Baden-Württemberg'),
    ('Ludwigsburg',              'DE', 'Baden-Württemberg'),
    ('Tübingen',                 'DE', 'Baden-Württemberg'),
    ('Reutlingen',               'DE', 'Baden-Württemberg'),
    ('Sindelfingen',             'DE', 'Baden-Württemberg'),
    ('Böblingen',                'DE', 'Baden-Württemberg'),
    ('Leonberg',                 'DE', 'Baden-Württemberg'),
    ('Waiblingen',               'DE', 'Baden-Württemberg'),
    ('Schorndorf',               'DE', 'Baden-Württemberg'),
    ('Fellbach',                 'DE', 'Baden-Württemberg'),
    ('Bietigheim-Bissingen',     'DE', 'Baden-Württemberg'),
    ('Kirchheim unter Teck',     'DE', 'Baden-Württemberg'),
    ('Nürtingen',                'DE', 'Baden-Württemberg'),
    ('Herrenberg',               'DE', 'Baden-Württemberg'),
    ('Albstadt',                 'DE', 'Baden-Württemberg'),
    ('Balingen',                 'DE', 'Baden-Württemberg'),
    ('Tuttlingen',               'DE', 'Baden-Württemberg'),
    -- Baden-Württemberg: Lake Constance
    ('Friedrichshafen',          'DE', 'Baden-Württemberg'),
    ('Ravensburg',               'DE', 'Baden-Württemberg'),
    ('Konstanz',                 'DE', 'Baden-Württemberg'),
    ('Singen',                   'DE', 'Baden-Württemberg'),
    ('Radolfzell am Bodensee',   'DE', 'Baden-Württemberg'),
    -- Baden-Württemberg: Karlsruhe / Rhine area
    ('Karlsruhe',                'DE', 'Baden-Württemberg'),
    ('Rastatt',                  'DE', 'Baden-Württemberg'),
    ('Bruchsal',                 'DE', 'Baden-Württemberg'),
    ('Ettlingen',                'DE', 'Baden-Württemberg'),
    ('Offenburg',                'DE', 'Baden-Württemberg'),
    ('Kehl',                     'DE', 'Baden-Württemberg'),
    ('Bühl',                     'DE', 'Baden-Württemberg'),
    ('Achern',                   'DE', 'Baden-Württemberg'),
    ('Lörrach',                  'DE', 'Baden-Württemberg'),
    ('Weil am Rhein',            'DE', 'Baden-Württemberg'),
    ('Rheinfelden',              'DE', 'Baden-Württemberg'),
    ('Emmendingen',              'DE', 'Baden-Württemberg'),
    -- Baden-Württemberg: Heidelberg / Kraichgau
    ('Heidelberg',               'DE', 'Baden-Württemberg'),
    ('Weinheim',                 'DE', 'Baden-Württemberg'),
    ('Sinsheim',                 'DE', 'Baden-Württemberg'),
    ('Bretten',                  'DE', 'Baden-Württemberg'),
    ('Pforzheim',                'DE', 'Baden-Württemberg'),
    -- Austria
    ('Innsbruck',                'AT', 'Tyrol'),
    ('Salzburg',                 'AT', 'Salzburg'),
    ('Bregenz',                  'AT', 'Vorarlberg'),
    ('Dornbirn',                 'AT', 'Vorarlberg'),
    ('Feldkirch',                'AT', 'Vorarlberg'),
    -- Switzerland
    ('Zurich',                   'CH', 'Zurich'),
    ('Winterthur',               'CH', 'Zurich'),
    ('St. Gallen',               'CH', 'St. Gallen'),
    ('Basel',                    'CH', 'Basel')
ON CONFLICT (city, country) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Migrate research_queue data → city_scans level 1
-- Any city that has at least one completed run in research_queue gets
-- a level 1 scan record with the most recent run date.
-- contacts_found = count of contacts in the contacts table for that city.
-- ---------------------------------------------------------------------------

INSERT INTO city_scans (city_id, level, last_run_at, contacts_found, run_count)
SELECT
    ci.id,
    1 AS level,
    MAX(rq.last_run_at) AS last_run_at,
    (
        SELECT COUNT(*)
        FROM contacts co
        WHERE LOWER(co.city) = LOWER(ci.city)
    ) AS contacts_found,
    MAX(rq.run_count) AS run_count
FROM cities ci
JOIN research_queue rq ON LOWER(rq.city) = LOWER(ci.city)
    AND rq.country = ci.country
    AND rq.last_run_at IS NOT NULL
GROUP BY ci.id
ON CONFLICT (city_id, level) DO NOTHING;
