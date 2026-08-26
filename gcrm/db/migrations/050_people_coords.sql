-- Mirrors migration 028's contacts.latitude/longitude: lets people be geocoded
-- (from city) so distance-from-home can be shown and sorted on, same as
-- companies.
ALTER TABLE people ADD COLUMN IF NOT EXISTS latitude  double precision;
ALTER TABLE people ADD COLUMN IF NOT EXISTS longitude double precision;
