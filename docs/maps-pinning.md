# Pinning companies on the Google Maps list

Chris walks with his phone's Google Maps: the private saved list **"Cold call candidates"**
holds the businesses to visit (a second list, **"Cold calls visited, left info"**, holds the
visited ones). Google has no API for personal lists, so pins are saved through the browser,
in Chris's own Google account, by Claude in the built-in browser — never from the server.
The CRM records every pin in `map_pins`, so the map and the database stay in step.

## When

After a Gather run or a lead-list import: "pin the new ones".

## Steps

1. **Queue** (read-only on the server): the companies waiting to be pinned, as loop items.
   ```bash
   ssh claude@82.165.32.162 "docker exec -i -e PGOPTIONS='-c default_transaction_read_only=on' engcrm-app uv run --no-sync python scripts/maps/pin_queue.py --import" > items.json
   ```
   `--gather` for the latest Gather run; no flag for every unpinned candidate. Companies
   with logged activity, do-not-contact, or neither coordinates nor an address are left out.
2. **Browser:** open `https://www.google.com/maps` in the built-in browser and check the
   signed-in account and that the "Cold call candidates" list exists. Load
   `scripts/maps/pin_loop.js` with `javascript_tool`, then run `await window.__pinLoop(items)`
   in batches of about 20 (each item takes ~10 s). Results build up in sessionStorage
   `__pins`; an interrupted run resumes, skipping what is done.
3. **Review:** `window.__pinResults()` → `results.json`, then the dry run:
   ```bash
   ssh claude@82.165.32.162 "docker exec -i engcrm-app uv run --no-sync python scripts/maps/apply_pins.py" < results.json
   ```
   Read every `saved` title. A pin saved on the wrong place is removed on the map by hand
   and its row deleted from the results before applying.
4. **Record:** the same command with `--apply` (production write: Chris's OK for the run,
   and an agent-diary record). Saved and already-pinned places are recorded; blank address,
   phone, website and coordinates are filled from Maps; nothing else is changed.

## Matching rules (in the loop)

- With CRM coordinates: the Maps place within 500 m (`maxDist` per item) and the name
  matching (normalised word overlap, Jaccard ≥ 0.6, or a per-item `expect` regex).
- Without (imported leads): searched by name + address; within 150 km of home, the
  postcode on the Maps card (or, without one, the website or the town), and the name.
- Closed places are never saved; an already-saved place is never toggled off; every save
  is confirmed by re-opening the Save menu (`unverified` otherwise, retried next run).

## Pitfalls seen (2026-11-03/04)

- Places already in another list show the Save button as "Saved (N)" — the loop handles it.
- A Save menu left open survives searches: reload the page; results survive in sessionStorage.
- A short CRM name can match another business ("Kern" → a shoe shop): the Jaccard rule
  catches most; read the dry-run titles for the rest.
- Map notes cannot be written by script (they need real keystrokes); details live in the CRM.
- CRM coordinates shared by 4+ organizations are town centroids: do not pin around them.
