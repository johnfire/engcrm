-- Migration 043: scan_areas + area_scans
-- Generalizes city_scans to arbitrary map-picked / GPS circles. See
-- docs/plans/2026-08-20-area-scanning-design.md for the full design.

CREATE TABLE IF NOT EXISTS scan_areas (
    id            SERIAL PRIMARY KEY,
    label         VARCHAR(150),
    latitude      DOUBLE PRECISION NOT NULL,
    longitude     DOUBLE PRECISION NOT NULL,
    radius_m      INTEGER NOT NULL CHECK (radius_m BETWEEN 100 AND 2000),
    city_id       INTEGER REFERENCES cities(id),
    workspace_id  INTEGER REFERENCES workspaces(id),
    created_by    INTEGER REFERENCES users(id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scan_areas_workspace_id ON scan_areas (workspace_id);
CREATE INDEX IF NOT EXISTS idx_scan_areas_city_id ON scan_areas (city_id);

CREATE TABLE IF NOT EXISTS area_scans (
    id                  SERIAL PRIMARY KEY,
    area_id             INTEGER NOT NULL REFERENCES scan_areas(id) ON DELETE CASCADE,
    level               SMALLINT NOT NULL CHECK (level BETWEEN 1 AND 10),
    last_run_at         TIMESTAMPTZ,
    organizations_found INTEGER NOT NULL DEFAULT 0,
    run_count           INTEGER NOT NULL DEFAULT 0,
    complete            BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE(area_id, level)
);
