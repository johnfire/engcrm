-- "Not now" is a pipeline stage, not a status. An earlier build offered it as a
-- status; move any deal that was set that way to the stage, with nothing going on.
-- No CHECK on stage or status, deliberately — see migration 041.
UPDATE deals SET pipeline_stage = 'not_now', status = 'none' WHERE status = 'not_now';
