# Scheduled data backup (decided 2026-11-07)

**Goal.** A workspace admin can have all their CRM data sent to them automatically (daily or
weekly, at a time they choose), so that if the website is ever gone they still hold their data.
It is for every customer workspace, not only the first one.

**Decisions (Chris).**
- The backup is **attached** to the email, so it survives the site being down. If the ZIP is over
  `BACKUP_MAX_ATTACHMENT_MB` (10) the email carries a login-protected download link instead.
- Password protection (AES-256 ZIP) is **optional, off by default** (phase 2).
- Schedule: **off / daily / weekly**, a time of day, a weekday for weekly, a time zone.
- Format: **CSV** (UTF-8 with BOM, comma, ISO dates), one file per kind of record, in one ZIP.
- Workspaces are completely separate: one workspace's backup never contains another's rows.

**The ZIP.** `organizations.csv`, `people.csv`, `activities.csv`, `deals.csv`, `sales.csv`,
`subscriptions.csv`, `offers.csv`, `README.txt`, `manifest.json` (export time, row counts).
Every row keeps its stable `id`; related rows carry the id *and* the readable name, so the files
make sense on their own and can be joined in any spreadsheet or mapped to another CRM's import
(HubSpot, Salesforce, …) later with one column-mapping table per target.
Left out on purpose: password hashes, sessions, tokens, MFA secrets, the audit log, AI keys,
raw Google Maps blobs and business-card photos. Soft-deleted rows are not exported.
Cells starting with `=`, `@` or a sign followed by a letter get a leading `'`, so a spreadsheet
never runs a typed-in formula (phone numbers like `+49 …` are left alone).

**How it runs.**
1. `backup_schedules` — one row per workspace (frequency, weekday, time, time zone, recipient,
   `next_run_at`, last result). Row-level security like every workspace table.
2. A background loop (like the pipeline snapshot loop) wakes every minute, finds schedules whose
   `next_run_at` has passed, and for each one enters that workspace's scope, builds the ZIP,
   emails it, stores a copy (`backup_files`, newest 7 kept) and moves `next_run_at` on.
   One workspace failing is logged and recorded; the others still run. A missed run (server down)
   is made up once, not repeated.
3. Settings (admin only): the schedule form, "Send me a backup now", "Download now", and the
   stored copies with their size and date.

**Why not just a link.** A link points back at the website, which is useless in the disaster the
backup is for. Hence the attachment.

**Out of scope for now.** The cross-platform pull script (Windows / macOS / Linux), push to the
customer's own cloud storage, per-CRM import mappings, mobile screens.
