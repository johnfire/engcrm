-- Migration 061: a daily log of how many organizations and people sit at each
-- pipeline stage. Everything else the statistics chart over time (activities,
-- hours, sales, new contacts) is computed from the records themselves; the size
-- of the pipeline on a past day is not, so the app writes one snapshot per day
-- (refreshed hourly, so a day's row ends as that day's last state).

CREATE TABLE IF NOT EXISTS pipeline_snapshots (
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    day          DATE NOT NULL,
    entity_type  TEXT NOT NULL CHECK (entity_type IN ('organization', 'person')),
    stage        TEXT NOT NULL,
    n            INTEGER NOT NULL,
    PRIMARY KEY (workspace_id, day, entity_type, stage)
);
