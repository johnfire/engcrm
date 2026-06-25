-- Store the full Google Places payload + the high-value fields we filter on.
-- google_data holds the entire place object (nothing Google sends is lost);
-- business_status/rating/user_ratings are promoted to columns for querying.
-- All within the Enterprise field tier we already pay for (no Atmosphere fields).
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS google_data     jsonb;
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS business_status text;
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS rating          double precision;
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS user_ratings    integer;
