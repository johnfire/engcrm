-- Incremental alphabetical scanning + geo-recon support.
-- latitude/longitude: captured from Google Places so contacts can be grouped by
--   proximity (plan on-foot recon by area).
-- city_scans.complete: true once a scan finds no new businesses for the level —
--   drives the 3-state status bubble (grey=not run, yellow=partial, green=complete).
ALTER TABLE contacts   ADD COLUMN IF NOT EXISTS latitude  double precision;
ALTER TABLE contacts   ADD COLUMN IF NOT EXISTS longitude double precision;
ALTER TABLE city_scans ADD COLUMN IF NOT EXISTS complete  boolean NOT NULL DEFAULT false;
