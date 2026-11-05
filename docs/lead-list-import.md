# Importing a lead list

Research done in a chat app (Claude Desktop, ChatGPT Desktop, Claude Code) on a subscription
ends in a Markdown **lead list**: the master table from
`~/ai-workzone/marketing-leads/HOWTO-city-lead-lists.md`. This step loads that list into
engcrm so it can be pinned, walked and worked on LinkedIn. It is plain parsing and matching —
no LLM, no tokens.

## The format

One master table, header:

```
| Pg | # | Business | Location | Address | Website | Contact | Role | LinkedIn | LinkedIn status | Notes |
```

One row per person; a business with no person is one row with `—` as the contact. Rows with
the same business name and address are one company. `[profile](url)` is a confirmed LinkedIn
profile; `[candidate](url)` is kept only as a note. Other tables in the file (Areas, Page
index) are ignored. A `|` inside the Notes cell is fine.

## Run it

Always a dry run first; it writes nothing and prints what would happen:

```bash
ssh claude@82.165.32.162 "docker exec -i engcrm-app uv run --no-sync python scripts/import_lead_list.py - --list-name buchloe-office-parks --town Buchloe" < ~/ai-workzone/marketing-leads/buchloe-office-parks.md
```

Then the same command with `--apply`. `--town` is the town for rows whose address names none
(chain branches often have no address in a list). Production writes need Chris's OK and an
agent-diary record (`slog record … --undo …`).

## What it does

- **Company:** new → organization at stage candidate, source `lead_list`, with address,
  website, the park/area as neighbourhood and the list's notes. Already in the CRM (same
  name in the same town, compared normalised: case, umlauts, punctuation, legal forms and
  "und"/"+" ignored) → only blank address, website and neighbourhood are filled.
  Companies are not matched by website: two entities in one list can share a site.
- **Possible duplicates:** a name whose words contain, or sit inside, an existing name in
  the same town ("Carglass GmbH Kaufbeuren" / "Carglass") is listed by the dry run, and
  `--apply` refuses until you add `--similar match` (same company) or `--similar new`.
- **Person:** on the company, with the role as title. A confirmed profile becomes the
  LinkedIn link; "connected" marks a LinkedIn connection; an unconfirmed profile and the
  list's LinkedIn status go into the notes. A person already on the company (same name,
  or the same profile on it) is reused. A person who runs two companies gets a record on
  each, so at either door you know whom to ask for; the report counts them.
- **Not geocoded:** pinning on the Maps list fills the exact coordinates.
- **Recorded** as a `lead_import` run with its company ids, so the pin queue can take
  "the companies from the latest import" (`latest_import_ids`).
- **Re-importing** the same list changes nothing.

## Then

Pin the imported companies on the "Cold call candidates" Maps list (pin queue with
`latest_import_ids()`), then walk them or work them on LinkedIn. Judge is optional.
