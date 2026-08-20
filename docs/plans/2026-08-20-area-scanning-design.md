# Area-Based Business Scanning Design

**Date:** 2026-08-20

## Goal

Today, research only runs city-wide: pick a city + a business-type level, and
the research agent text-searches `"{term} {city}"` across that level's terms.
This adds a second way to trigger the same pipeline — scan a specific area
instead of a whole city: a Gewerbegebiet, or a 500m radius around wherever you
currently are. Map-pick a center point (tap on a map), with device GPS as the
fallback / "use my location" shortcut. Same downstream pipeline (scout →
enrichment) is reused untouched; only the discovery step changes.

## Data Model

```sql
CREATE TABLE scan_areas (
    id            SERIAL PRIMARY KEY,
    label         VARCHAR(150),                     -- optional, e.g. "Königsbrunn Gewerbegebiet Nord"
    latitude      DOUBLE PRECISION NOT NULL,
    longitude     DOUBLE PRECISION NOT NULL,
    radius_m      INTEGER NOT NULL CHECK (radius_m BETWEEN 100 AND 2000),
    city_id       INTEGER REFERENCES cities(id),     -- resolved via reverse-geocode, informational only
    workspace_id  INTEGER REFERENCES workspaces(id),
    created_by    INTEGER REFERENCES users(id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE area_scans (        -- mirrors city_scans, one row per area x level
    id                  SERIAL PRIMARY KEY,
    area_id             INTEGER NOT NULL REFERENCES scan_areas(id) ON DELETE CASCADE,
    level               SMALLINT NOT NULL,
    last_run_at         TIMESTAMPTZ,
    organizations_found INTEGER NOT NULL DEFAULT 0,
    run_count           INTEGER NOT NULL DEFAULT 0,
    complete            BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE(area_id, level)
);
```

Every scan is saved as a `scan_areas` row — even unlabelled ad-hoc GPS scans —
so the map can always show "already scanned here" markers and per-area history,
matching how `cities`/`city_scans` work today.

`workspace_id` follows the existing (if imperfectly enforced — reads on
`cities`/`contacts` don't filter by it either; that's a pre-existing gap, not
something this feature fixes) convention: set from `get_workspace_id()` on
insert for interactive requests, `COALESCE`d to the default workspace for
background subprocess jobs which have no request context.

`city_id` exists only so saved organizations get a sensible `city`/`country`
value and so the existing per-city dedup (`get_existing_organization_names`)
keeps working unchanged. An ad-hoc pin far from any city just gets `city_id =
NULL`.

No `area_id` column on `contacts`, and no PostGIS/earthdistance extension.
"Organizations found in this area" is computed at read time with a Haversine
distance expression against `contacts.latitude`/`longitude` (already-existing
columns) filtered to `< scan_areas.radius_m`. This keeps results live as
contacts move through the pipeline, avoids a migration-time extension
dependency, and needs no new join table.

The pre-existing "level 1 must run before other levels" gate
(`can_run_level`) does **not** apply to area scans — that ordering exists to
sequence a city-wide campaign by cost/pain tier; a small radius is explicit
enough that the gate would only get in the way.

## Discovery Layer

`google_maps_search(query, city, country, ...)` (`gcrm/tools/search.py`) gains
optional `lat`, `lon`, `radius_m` keyword arguments. When set, the Places
request body adds `locationRestriction: {circle: {center, radius}}` and the
text query drops the city name (`term` instead of `f"{term} {city}"`) — the
circle constrains geography, the string just picks the business type. This is
an additive change to the one function actually wired into the research
agent's `geo_search` dependency (`run_research.py` binds `geo_search =
google_maps_search`; the Overpass-based `geo_search` function in the same file
is not currently used by the live pipeline, but gets the equivalent
`around:{radius},{lat},{lon}` treatment for consistency, plus `lat`/`lon`
extraction from Overpass nodes since it's currently missing and would be
needed to place pins).

## Research Agent Changes

`ResearchState` (`agents/gcrm-research-agent/gcrm_research_agent/state.py`)
changes `level: int` to `levels: list[int]`, and adds `latitude: float | None`,
`longitude: float | None`, `radius_m: int | None`, `area_id: int | None`. City
scans pass `levels=[level]` unchanged (backward compatible).

`init` unions `maps_terms` across every level in `levels` instead of reading
one level's list. `run_maps_search` passes `latitude`/`longitude`/`radius_m`
through to `geo_search` when set. `save_organizations` records one
`area_scans` row per level (via `record_area_scan_result`) instead of
`city_scans` when `state["area_id"]` is set, mirroring `record_scan_result`
exactly. Everything else (`select_new_chunk`, `run_web_search`, `fetch_pages`,
`extract_organizations`, `fetch_missing_emails`) is level-list-agnostic
already, since they operate on `raw_results`/`organizations_to_save`, not the
level itself directly (aside from labels in logs/prompts, which take the
first level as a representative label).

## Pipeline / API

`gcrm/supervisor/pipeline.py` gets `spawn_area_stage(stage, area_id, levels,
...)`, invoking the same `run_research`/`run_scout`/`run_enrichment` modules
with `--area-id` and `--levels` instead of `--city`/`--level`. Those modules
branch once at startup (area vs. city) — everything downstream of discovery
is already city/level-agnostic since scout and enrichment operate on saved
contact rows.

New endpoints, mirroring the `research.py` / `api_research.py` split (session
auth for web, JWT for mobile):

- `POST /areas/scan` (web) / `POST /api/areas/scan` (mobile) — body `{lat, lon,
  radius_m, levels[], label?}`. Reuses an existing area if a saved point is
  within ~50m with the same radius (so repeat "scan here" taps don't spawn
  duplicate area rows), else creates one via reverse-geocode. Calls
  `spawn_area_stage("research", area_id, levels)`.
- `GET /areas/` / `GET /api/areas/` — list saved areas with per-level scan
  status, same shape as `build_research_overview()` produces for cities
  (`build_area_overview()`).
- `GET /areas/{id}/organizations` / `GET /api/areas/{id}/organizations` — the
  found orgs within that area's radius, `{id, name, lat, lon, pipeline_stage,
  ...}`, for map pins.

## Mobile UI

Two new screens under `(drawer)`, using `expo-location` (already a
dependency) for GPS. **`react-native-maps` is not currently a dependency** and
is a native module — adding it requires an EAS dev-client rebuild, not just a
Metro reload, so this is called out as separate, first infra work rather than
folded into the screen work.

- `area-scan.tsx` — full-screen `MapView`, centered on device GPS by default.
  A single tap drops a pin (map-pick); "Use my location" recenters to GPS
  (the fallback). A radius slider, 100m–2km, draws a circle overlay. Level
  chips below, multi-select, all selected by default. "Scan" posts to
  `/api/areas/scan`.
- `area-results.tsx` — same `MapView`, pins from
  `GET /api/areas/{id}/organizations` colored by `pipeline_stage` (reusing
  `organizations.tsx`'s existing stage-color mapping), tap → the existing
  `organization-detail.tsx`, unchanged.

`research.tsx` gets a new "Scan an area" entry point linking to
`area-scan.tsx`, alongside the existing city-form flow (not replacing it).

## Web UI

A new `areas.html` template (companion to `research.html`, not a
modification of it), using self-hosted Leaflet (no CDN, matching how the rest
of the UI avoids external calls) for the same pick-a-point-and-radius
interaction, minus GPS — a desktop "use my location" via
`navigator.geolocation` is a poor fit for "planning a scan at a desk," so it's
skipped rather than built for a case that won't get used. Below the map: the
same area list as mobile, styled like the existing per-level dot table, plus
a results map toggled between "pick" and "results" mode using the same
Leaflet instance.

## Rollout Order / Risks

1. **Backend first** (migration, `db_areas.py`, discovery-layer geo params,
   research agent multi-level support, pipeline + API routes) — fully
   testable without any native mobile dependency.
2. **Mobile map dependency** (`react-native-maps` + EAS dev-client rebuild) is
   isolated infra work that blocks on-device testing of the mobile screens —
   should happen before the mobile screens are built, not stalled behind them.
3. **Cost guard**: multi-level area scans multiply Google Places calls (up to
   ~90 terms across all 10 levels x up to 3 pages each). Worth a sanity cap
   (e.g. warn past 6 selected levels) so a big-radius "select all" doesn't
   burn quota pointlessly on a small area.
4. Confirm `locationRestriction` circles behave as expected against the live
   Places API (New) account before relying on it in production — the code
   already targets `places.googleapis.com/v1`, so this should already be the
   right tier, but worth a live smoke test.
