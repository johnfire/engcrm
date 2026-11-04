-- A company's own LinkedIn and XING pages (company pages, not people). Found from
-- web-search results during enrichment, never by visiting LinkedIn or XING, and kept
-- once found. company_pages_checked_at records that the search was done, so a company
-- with no page is not searched for again on every run.
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS linkedin_url TEXT;
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS xing_url TEXT;
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS company_pages_checked_at TIMESTAMPTZ;
