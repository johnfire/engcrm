-- agent_runs.status was VARCHAR(20), but the opportunity agent's
-- generate_report node writes 'completed_with_errors' (22 chars) whenever any
-- per-organization save fails. That UPDATE then throws "value too long for
-- type character varying(20)" — masking whatever error actually happened
-- during the run, since finish_run() is called after errors are already
-- collected.
ALTER TABLE agent_runs ALTER COLUMN status TYPE VARCHAR(30);
