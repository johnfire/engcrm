-- Organizations created from LinkedIn connections' employers.
--
-- company_key  the normalized company name an organization was created from
--              (gcrm.linkedin.normalize_company). It is the idempotency anchor:
--              re-importing a newer Connections.csv finds the organization it
--              already created instead of making a second one.
-- city_status  where the city came from / whether it still needs a human:
--              needs_review (no city yet), resolved (lookup accepted),
--              manual (entered by hand). NULL for organizations that were not
--              created from LinkedIn.

ALTER TABLE contacts ADD COLUMN IF NOT EXISTS company_key TEXT;
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS city_status TEXT;

-- One LinkedIn-created organization per company key per workspace.
CREATE UNIQUE INDEX IF NOT EXISTS idx_contacts_linkedin_company_key
    ON contacts (workspace_id, company_key)
    WHERE source = 'linkedin' AND company_key IS NOT NULL AND deleted_at IS NULL;

-- The "needs a city" work queue.
CREATE INDEX IF NOT EXISTS idx_contacts_city_review
    ON contacts (id) WHERE city_status = 'needs_review' AND deleted_at IS NULL;
