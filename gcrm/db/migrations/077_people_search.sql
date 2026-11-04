-- Decision-makers found by web search for companies the scout rated ready (never by
-- visiting LinkedIn or XING). A person's public XING profile is kept next to the
-- LinkedIn one; profile_searched_at records that the web was searched for their
-- profiles, so a person searched with neither link is shown as "no public profile
-- found" rather than "not looked for". people_searched_at on the company stops the
-- same company being searched on every run.
ALTER TABLE people ADD COLUMN IF NOT EXISTS xing_url TEXT;
ALTER TABLE people ADD COLUMN IF NOT EXISTS profile_searched_at TIMESTAMPTZ;
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS people_searched_at TIMESTAMPTZ;
