-- Which organizations are pinned on one of the user's Google Maps lists, for example the
-- private saved list "Cold call candidates" that the phone's Maps app shows for walking
-- visits. The CRM is where candidates are decided and Maps is where they are found in the
-- field; this table is the link between the two, so nothing is pinned twice and a pin that
-- was never made is visible. One row per organization, list and Google place (two
-- companies in one building share a place, each with its own row). A pin removed on the
-- map is kept with removed_at set.
CREATE TABLE IF NOT EXISTS map_pins (
    id           BIGSERIAL PRIMARY KEY,
    workspace_id INTEGER     NOT NULL REFERENCES workspaces(id),
    contact_id   INTEGER     NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    list_name    TEXT        NOT NULL,
    place_key    TEXT        NOT NULL,  -- Google's id of the place: the 0x...:0x... part of its link
    maps_name    TEXT        NOT NULL,  -- the name Maps shows, which may differ from the CRM's
    maps_address TEXT        NOT NULL DEFAULT '',
    maps_url     TEXT        NOT NULL DEFAULT '',
    latitude     DOUBLE PRECISION CHECK (latitude BETWEEN -90 AND 90),
    longitude    DOUBLE PRECISION CHECK (longitude BETWEEN -180 AND 180),
    note         TEXT        NOT NULL DEFAULT '',  -- the private note written on the pin
    saved_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    removed_at   TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS map_pins_live
    ON map_pins (contact_id, list_name, place_key) WHERE removed_at IS NULL;
CREATE INDEX IF NOT EXISTS map_pins_contact ON map_pins (contact_id) WHERE removed_at IS NULL;
CREATE INDEX IF NOT EXISTS map_pins_list ON map_pins (workspace_id, list_name) WHERE removed_at IS NULL;
