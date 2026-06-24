-- Drop city_scans_level_check (was CHECK level BETWEEN 1 AND 5).
--
-- SCAN_LEVELS now defines 10 tiers and the UI/CLI accept 1-10, but this
-- constraint still capped at 5. Scanning levels 6-10 saved the contacts fine,
-- but record_scan_result's INSERT into city_scans was rejected -> no scan row
-- got written -> the city's level bubble stayed grey for 6-10 (and can_run_level
-- couldn't see the scan). SCAN_LEVELS (application) is the source of truth for
-- valid levels; drop the hardcoded range.
ALTER TABLE city_scans DROP CONSTRAINT IF EXISTS city_scans_level_check;
