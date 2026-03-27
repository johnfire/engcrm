-- Migration 005: city market character
-- Adds market_character and market_notes to cities table.
-- market_character: tourist | mixed | upscale | unknown
-- market_notes: free text, updated via MCP or direct observation

ALTER TABLE cities ADD COLUMN IF NOT EXISTS market_character VARCHAR(20) DEFAULT 'unknown';
ALTER TABLE cities ADD COLUMN IF NOT EXISTS market_notes TEXT DEFAULT '';

-- Romantische Straße cities: tourist market, galleries cater to tourists
UPDATE cities SET
    market_character = 'tourist',
    market_notes = 'Romantische Straße city. Tourist-driven art market — galleries sell to visitors. All galleries worth contacting regardless of program.'
WHERE city IN ('Landsberg am Lech') AND country = 'DE';

-- Bodensee (Lake Constance): tourist market
UPDATE cities SET
    market_character = 'tourist',
    market_notes = 'Bodensee city. Strong tourist market — galleries and venues cater to visitors. All galleries worth trying.'
WHERE city IN ('Konstanz', 'Friedrichshafen', 'Lindau', 'Radolfzell am Bodensee', 'Singen') AND country = 'DE';

UPDATE cities SET
    market_character = 'tourist',
    market_notes = 'Bodensee city. Strong tourist market — galleries and venues cater to visitors. All galleries worth trying.'
WHERE city = 'Bregenz' AND country = 'AT';

-- Alpine/lake resorts around Munich: tourist market
UPDATE cities SET
    market_character = 'tourist',
    market_notes = 'Alpine resort town. Strong tourist market, visitors buy art as memories of the region. All galleries worth trying.'
WHERE city IN ('Garmisch-Partenkirchen') AND country = 'DE';

UPDATE cities SET
    market_character = 'tourist',
    market_notes = 'Regional lake/resort area. Tourist-influenced art market.'
WHERE city IN ('Rosenheim', 'Wangen im Allgäu', 'Kempten') AND country = 'DE';

-- Munich: upscale, very selective
UPDATE cities SET
    market_character = 'upscale',
    market_notes = 'Predominantly upscale and blue-chip gallery scene (~90%). Only promote galleries with clear evidence of showing emerging or regional artists. Very selective.'
WHERE city = 'Munich' AND country = 'DE';

-- Zurich and Basel: upscale
UPDATE cities SET
    market_character = 'upscale',
    market_notes = 'Major international art market city. High-end gallery scene. Be selective — look for clear signals of openness to emerging artists.'
WHERE city = 'Zurich' AND country = 'CH';

UPDATE cities SET
    market_character = 'upscale',
    market_notes = 'Home of Art Basel. Prestigious gallery scene. Be selective — only galleries with clear emerging artist program.'
WHERE city = 'Basel' AND country = 'CH';

-- Augsburg: explicitly mixed (user: "hip trendy and upscale")
UPDATE cities SET
    market_character = 'mixed',
    market_notes = 'Mix of hip/trendy and upscale galleries. Evaluate case by case — both types can be good fits.'
WHERE city = 'Augsburg' AND country = 'DE';

-- University/cultural cities: mixed
UPDATE cities SET
    market_character = 'mixed',
    market_notes = 'University and cultural city. Mixed gallery scene — evaluate individually.'
WHERE city IN ('Heidelberg', 'Tübingen', 'Freiburg', 'Regensburg') AND country = 'DE';
