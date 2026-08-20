-- The "contacts are organizations" rename (39af8f4) rewrote every reference to
-- city_scans.contacts_found in application SQL to organizations_found, but no
-- migration renamed the physical column — this table was missed by the "schema
-- keeps the old name" exception, which only covers the `contacts` table itself.
-- Every query against city_scans has been failing with UndefinedColumn since
-- that deploy: the web Research page (500), record_scan_result() on every
-- completed scan, and the MCP research_status tool.

ALTER TABLE city_scans RENAME COLUMN contacts_found TO organizations_found;
