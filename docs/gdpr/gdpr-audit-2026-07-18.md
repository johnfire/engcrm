# GDPR technical audit — engcrm — 2026-07-18

> **This is not legal advice.** This report lists technical findings from a
> code, database, and deployment review against GDPR / BDSG / TDDDG. Legal
> conclusions — legal basis, contract status, purposes — require a human
> (lawyer/DPO) and are explicitly flagged as judgment calls below.

**Scope:** `/home/chris/ppp2/engcrm` working tree at commit `e4c06be` **plus
uncommitted changes** (another fleet agent has WIP on this shared checkout:
migrations 030–032, `totp.py`, `db_account_lifecycle.py`, `db_audit.py` — noted
where relevant). Covers: `gcrm/` FastAPI backend + web UI, five agents under
`agents/`, `engcrm-interview-agent/`, `engcrm-mobile/` (Expo/React Native),
`scripts/`, Docker/compose, CI. **Production was reachable:** read-only SSH to
the VPS (claude@82.165.32.162, IONOS DE), read-only SQL against the live `gcrm`
Postgres via `docker compose exec`, Apache vhost + logrotate + backup-file
inspection, and live header check of `https://engcrm.christopherrehm.de`.
Nothing on the VPS or in the repo outside `docs/gdpr/` was modified.

**Auditor:** Claude (Fable 5), gdpr-audit skill (2026-07)
**Previous audit:** none (first GDPR audit). Security posture cross-referenced
from `AUDIT-2026-07-17.md` and `CODE-REVIEW-2026-06-24.md` (memory) rather than
re-derived.

## Summary

engcrm is a single-workspace B2B lead CRM (315 contacts in production, 4 staff
accounts) hosted entirely on an IONOS VPS in Germany, with self-hosted Whisper
transcription and Proton (Switzerland) email — the hosting story is good, and
several privacy-by-design touches are real: a `consent_log` table with opt-out
and erasure flags that actually blocks outreach, card images deleted on
confirm/discard (verified on the production volume), voice audio never
persisted, no analytics or tracking anywhere, bounded backup retention.

**16 findings: 2 violation-indicators, 8 gaps, 6 needs-legal-judgment.**

Do first:
1. **F-01** — personal data (inbound email bodies, contact notes, voice
   transcripts) flows to DeepSeek in China, which has no adequacy decision.
   This is the single biggest exposure; switch the personal-data-bearing
   prompts to an EU/adequate provider or get a documented Art. 46 mechanism.
2. **F-03/F-05** — there is no erasure or retention machinery at all: contact
   "delete" is a soft delete that keeps everything forever, and the
   `erasure_requested` flag blocks outreach but erases nothing.
3. **F-02** — one-line fix: vendor `htmx` into `/static` instead of loading it
   from unpkg.com (US CDN) on every authenticated page view.

## Findings

### Violation indicators

#### F-01 — Personal data sent to DeepSeek (China — no adequacy decision) (Art. 44–49, 28)
- **Evidence:** `gcrm/config.py:130-131` — `CHEAP_LLM`/`SMART_LLM` both default
  to `deepseek-v4-flash`; `gcrm/tools/llm.py:63-72` sends to
  `https://api.deepseek.com`. Personal data demonstrably in prompts:
  - inbound email bodies + sender addresses for classification and follow-up
    drafting — `agents/gcrm-followup-agent/gcrm_followup_agent/graph.py:217,291,375`
  - contact name/notes/history in outreach drafts —
    `agents/gcrm-outreach-agent/gcrm_outreach_agent/graph.py:94-101`
  - voice-memo transcripts (free speech about people) —
    `gcrm/tools/voice.py:12` `structure_transcript()` → `get_llm()`
  - enrichment extraction over scraped pages —
    `agents/gcrm-enrichment-agent/gcrm_enrichment_agent/graph.py`
- **Why it's a problem:** China has no EU adequacy decision. A transfer of
  personal data to a Chinese processor requires an Art. 46 safeguard (SCCs +
  transfer impact assessment); absent that, the transfer is unlawful per the
  plain text of Art. 44. Chapter V has no de-minimis exception. DeepSeek's
  consumer terms also give no Art. 28 processor guarantees (verify current
  platform terms — that status check is the one judgment component here).
- **Suggested fix:** route prompts that carry personal data to an EU-hosted or
  adequacy-country model (the `CHEAP_LLM`/`SMART_LLM` knobs make this a config
  change), or strip/pseudonymize personal data before the call; alternatively
  document SCCs + TIA if DeepSeek offers them.

#### F-02 — htmx loaded from unpkg.com (US CDN) on every UI page (Art. 44 ff.; TDDDG §25; LG München I, 3 O 17493/20)
- **Evidence:** `gcrm/ui/templates/base.html:7` —
  `<script src="https://unpkg.com/htmx.org@1.9.12"></script>`. Every page
  extending `base.html` (all post-login pages; `login.html` is self-contained)
  makes the staff browser fetch from a US CDN, transmitting the user's IP
  without consent.
- **Why it's a problem:** the Google-Fonts judgment (LG München 2022)
  established that loading page resources from US servers, disclosing the
  visitor's IP without consent, is itself a violation. Exposure here is limited
  to the 4 authenticated staff users (mitigating severity, not the pattern).
- **Suggested fix:** vendor `htmx.min.js` into `gcrm/ui/static/` and reference
  it locally. One file, no build step.

### Gaps

#### F-03 — No erasure path: soft-delete-forever, erasure flag erases nothing (Art. 17)
- **Evidence:** `gcrm/api/routers/contacts.py:293-304` — contact delete sets
  `deleted_at = NOW()`; the comment says the row "isn't irreversibly
  destroyed". No code anywhere hard-deletes or anonymizes contacts, people,
  interactions, inbox messages, or AI analyses. `consent_log.erasure_requested`
  (`001_agent_tables.sql`) only blocks further outreach
  (`gcrm/tools/db.py:366-373`) — the data itself is never removed. Account
  deletion: migration `031_workspace_account_lifecycle.sql` (uncommitted WIP)
  creates `account_deletion_requests`, but no code references it
  (`grep account_deletion` over `gcrm/` returns only the migration) and the
  table does not exist in production (verified 2026-07-18).
- **Why it's a problem:** Art. 17 requires actual erasure on request.
  "Soft-delete with data retained forever" cannot satisfy it, and the
  machinery to honor `erasure_requested` end-to-end doesn't exist. Chris's
  coding-standards also mandate two-step account deletion — schema-only WIP is
  automatically a finding until the flow ships.
- **Suggested fix:** an erasure routine (hard-delete or anonymize the contact
  row + cascaded interactions/analyses/inbox matches + card images) triggered
  by `erasure_requested`, plus a purge job for soft-deleted rows; finish the
  account-deletion flow on top of migration 031.

#### F-04 — No data export for any data subject (Art. 15, 20)
- **Evidence:** no export/takeout endpoint in any router
  (`grep -rniE "export|takeout"` over `gcrm/api/` — no hits);
  `contacts_print.html` is a print view, not machine-readable; `scripts/` has
  importers only.
- **Why it's a problem:** Art. 15 (access) and Art. 20 (portability, for the
  account holders) need a way to produce a person's data in a common format.
  Coding-standards independently require data export — absence is
  automatically a finding.
- **Suggested fix:** JSON export endpoints: per-contact/person (everything
  linked to them) and per-user account.

#### F-05 — No retention mechanism for any stored personal data (Art. 5(1)(e))
- **Evidence:** the only expiry logic in the codebase is for card images
  (`api_cards.py:167-168,183` — delete on confirm/discard, verified working in
  production: discarded captures 4/8/11 have no file on the volume) and
  invitation/reset token expiry (WIP). Nothing ever expires
  `inbox_messages` (full email bodies), `ai_analysis.raw_response`,
  `agent_runs.input_json/output_json`, `interactions`, soft-deleted rows, or
  stale `push_tokens`. No cron/timer/job in repo, compose, or RUNBOOK.
- **Why it's a problem:** storage limitation requires data be kept no longer
  than needed; "nothing is ever deleted" is a gap by default. (The periods
  themselves are a business decision — see F-13 context.)
- **Suggested fix:** a small retention job (systemd timer or in-app scheduler)
  with per-table retention config; start with inbox bodies and purged
  soft-deletes.

#### F-06 — Recipient emails and lead PII written to application logs (Art. 5(1)(c))
- **Evidence:** `gcrm/tools/email.py:63` —
  `logger.info("send_email: sent to %s — %s", to_email, subject)` (also lines
  44, 66); `agents/gcrm-enrichment-agent/gcrm_enrichment_agent/graph.py:157` —
  logs contact name, city, website, and discovered email at INFO. Logs land in
  container stdout/journald on the VPS and `~/logs/` in dev, outside all
  deletion machinery.
- **Why it's a problem:** copies of personal data accumulate in logs with no
  retention control; contradicts data minimization. Coding-standards pattern
  (log IDs, not records) already exists in the audit-log design.
- **Suggested fix:** log contact/user IDs instead of addresses; drop the
  discovered-email from the enrichment INFO line.

#### F-07 — No audit logging of personal-data access/changes in production (Art. 32; coding-standards)
- **Evidence:** production DB has no `audit_log` table (verified 2026-07-18:
  21 tables, `audit_log` absent — migration `030_audit_log.sql` is uncommitted
  WIP). Even in the working tree, `gcrm/tools/db_audit.py` is wired only into
  approvals (`api_approvals.py:49,69`, `approval.py:122,154`) — contact
  edits/deletes, exports, card promotions, and user management are unaudited.
- **Why it's a problem:** Art. 32 expects the ability to reconstruct who
  accessed/changed personal data; coding-standards require audit logging of
  user and AI actions. Currently a deleted or edited contact leaves no trace
  of who did it.
- **Suggested fix:** land migration 030 and extend `log_audit` calls to all
  mutating personal-data routes (contacts, people, cards, users, inbox).

#### F-08 — Database backup dumps world-readable on the VPS (Art. 32)
- **Evidence:** `/opt/engcrm/backups/daily/gcrm-*.sql.gz` are `-rw-r--r--
  root:root` (verified 2026-07-18); the directory tree is `drwxr-xr-x`. Any
  local account on the shared VPS (which runs ~15 other services and multiple
  user accounts) can read complete dumps of all contact/user personal data.
- **Why it's a problem:** confidentiality of processing (Art. 32(1)(b)) —
  the dumps bypass all application access control.
- **Suggested fix:** `chmod 700` the backups dir (the backup container writes
  as root regardless); consider encrypting dumps at rest.

#### F-09 — No privacy notice, no Impressum (Art. 13; DDG §5)
- **Evidence:** no Datenschutzerklärung or privacy link anywhere in
  `gcrm/ui/templates/` (`grep -ri "impressum|datenschutz|privacy"` — no hits),
  including the publicly reachable login page at
  `https://engcrm.christopherrehm.de/login`; nothing in the mobile app either
  (Play-Store listing not checked — Play requires a privacy-policy URL).
- **Why it's a problem:** the 4 account holders are data subjects and must
  receive Art. 13 information; total absence is a gap (content correctness
  would be a judgment call). Impressum (DDG §5): adjacent one-line note only —
  a publicly reachable business login page likely needs one; flagged, not
  audited.
- **Suggested fix:** a short privacy page linked from login + app; add the
  Play-Store privacy-policy URL.

#### F-10 — No HSTS header on the production vhost (Art. 32 — minor)
- **Evidence:** `curl -D -` against `https://engcrm.christopherrehm.de/login`
  (2026-07-18) returns no `Strict-Transport-Security`; no `Header` directives
  in `/etc/apache2/sites-enabled/engcrm-le-ssl.conf`. TLS itself is fine
  (Let's Encrypt, Apache sole entry, app bound to 127.0.0.1).
- **Why it's a problem:** without HSTS a first request can be downgraded;
  cheap hardening for a service carrying personal data. Same deferred-HSTS
  pattern as notes-world #91.
- **Suggested fix:** `Header always set Strict-Transport-Security
  "max-age=31536000"` in the `-le-ssl` vhost.

### Needs legal judgment

#### F-11 — Art. 14 information duty toward scraped leads (Art. 14)
- **Context:** production holds 315 contacts and 7 people, built by agents
  from OpenStreetMap, Google Places (`gcrm/tools/search.py:101-181`), web
  scraping via Bright Data (`search.py:212+`), card OCR, and LLM enrichment —
  data about people (owners, `decision_maker`, emails) who never interacted
  with the service. Art. 14 requires informing them within a month or at first
  contact, unless disproportionate effort (Art. 14(5)(b)) applies.
- **Question for Chris/lawyer:** does first-contact outreach include (or
  should it include) privacy information + data source, and is Art. 14(5)(b)
  arguable for leads never contacted?

#### F-12 — Processor/DPA status for the non-EU service inventory (Art. 28, 44–49)
- **Context:** see recipients table. Anthropic (US — business-card images with
  names/titles/contact details, `gcrm/tools/cards.py:44-70`; mitigated by
  image deletion on confirm), Expo push (US — device tokens + notification
  text that can name contacts, `gcrm/api/push.py:9,19`), Google Places (US —
  queries are only "industry + city", results are ingested rather than data
  sent), Bright Data (Israel — adequacy exists; URLs fetched are contact
  websites), Proton (Switzerland — adequacy exists; all mail content).
- **Question for Chris/lawyer:** for each — is a DPA in place, and for the US
  providers is the vendor currently EU-US DPF-certified (or SCCs signed)?
  Check Anthropic's commercial terms and Expo's DPA specifically.

#### F-13 — Legal basis for cold outreach + retention periods (Art. 6(1)(f); UWG §7)
- **Context:** `consent_log` hardcodes `legal_basis='legitimate_interest'`
  (`gcrm/tools/db.py:336-357`) — good machinery, but the balancing test (LIA)
  is a document, not code. Adjacent non-GDPR flag: UWG §7(2) Nr. 2 generally
  requires prior consent for e-mail advertising even B2B.
- **Question for Chris/lawyer:** is a legitimate-interest assessment written
  down, and is the e-mail outreach channel defensible under UWG §7? Also:
  set the retention periods F-05 needs (how long to keep dead leads, inbox
  bodies, interactions).

#### F-14 — AI scoring auto-drops leads without human review (Art. 22)
- **Context:** the scout agent scores candidates and drops those below
  `SCOUT_THRESHOLD` (default 75, `.env.example`) with no human in the loop;
  outreach drafts, by contrast, are always human-approved (approval queue).
  Being excluded from marketing is unlikely to be a "legal or similarly
  significant effect" on a business venue, but it is an automated decision
  about identifiable people.
- **Question for Chris/lawyer:** confirm Art. 22 doesn't bite for B2B
  lead-filtering; if the tool is ever pointed at individuals (e.g. artists,
  applicants), revisit.

#### F-15 — Special categories in free-text fields (Art. 9)
- **Context:** `contacts.notes`, `access_notes`, `price_sensitivity`,
  `people.notes`, voice-memo summaries — staff can write anything about a
  person, including health/religion/etc.; nothing prevents or detects it.
  Standard CRM situation, worth a policy line rather than code.
- **Question for Chris:** agree (and note in the Art. 30 record) that special
  categories must not be recorded in notes fields.

#### F-16 — Staff account data (§26 BDSG)
- **Context:** 4 user accounts (email, name, role, `last_login_at`; TOTP
  secrets encrypted in WIP migration 031). Minimal scope, but if any users are
  employees/contractors, §26 BDSG governs it.
- **Question for Chris:** confirm accounts stay limited to
  login/role/last-login and users are informed (ties into F-09).

## Recipients & transfers table

| Recipient | Data sent | Country | Adequacy/mechanism | DPA status |
|---|---|---|---|---|
| DeepSeek (api.deepseek.com) | email bodies + senders, contact names/notes, voice transcripts, enrichment text | China | **none** — no adequacy; Art. 46 mechanism unknown | ⚠ verify (F-01) |
| Anthropic (Claude Haiku vision) | business-card images (names, titles, phones, emails) | US | DPF only if certified — verify | ⚠ verify (F-12) |
| Expo push (exp.host) | device push tokens, notification title/body | US | DPF/SCC — verify | ⚠ verify (F-12) |
| Google Places API | outbound: industry+city text query only; inbound: business data | US | DPF (Google LLC certified) — verify current | ⚠ verify (F-12) |
| Bright Data (api.brightdata.com) | URLs of lead websites fetched via proxy | Israel | adequacy decision (Israel) | ⚠ verify DPA |
| Proton Mail (via local Bridge, SMTP/IMAP) | all outreach + inbound mail content | Switzerland | adequacy decision (CH) | ⚠ verify DPA |
| unpkg.com CDN | staff IP address, user-agent (browser fetch) | US | none — no consent | n/a — remove (F-02) |
| OSM Nominatim / Overpass | city/industry queries — no personal data | EU/DE | n/a | n/a |
| Whisper (faster-whisper) | voice audio | self-hosted, same VPS (DE) | n/a — no transfer | n/a |
| GHCR / GitHub CI | container images, code — no personal data | US | n/a | n/a |

## Positive observations (so they don't get "fixed" away)

- `consent_log` with opt-out + erasure flags gating outreach (`db.py:366`) —
  rare to see; F-03 is about finishing it, not replacing it.
- Card images deleted on confirm and discard, verified against the production
  volume; `CARD_IMAGE_RETENTION_DAYS` knob documented in `.env.example`.
- Voice audio transcribed in memory via self-hosted Whisper — never persisted.
- No analytics, tracking, or marketing storage anywhere (web or mobile);
  session cookie + SecureStore JWT are strictly necessary → no consent banner
  needed, which is the best outcome.
- EU hosting (IONOS SE, DE — verified by IP allocation), backups on the same
  DE host with bounded 7d/4w/3m rotation, Apache access logs rotated daily ×14.
- bcrypt passwords, fail-closed secrets, rate-limited login, RBAC, SSRF guard,
  gitleaks CI — see `AUDIT-2026-07-17.md` for the security review proper.

## Checklist appendix

| Item | Status | Note |
|---|---|---|
| 1.1 Schema sweep | OK | 33 migrations read; inventory in Art. 30 record (contacts, people, users, interactions, inbox_messages, approval_queue, ai_analysis, card_captures, consent_log, push_tokens, agent_runs) |
| 1.2 Special categories | FINDING → F-15 | free-text notes fields unrestricted |
| 1.3 Uploads & media | OK | card images (VPS volume, deleted on confirm/discard); voice audio never stored |
| 1.4 Derived/imported data | FINDING → F-11 | scraped + enriched leads; Art. 14 duty open |
| 1.5 Identifiers in URLs | OK | numeric IDs only in paths; no PII in query strings found |
| 2.1 Access/export | FINDING → F-04 | no export endpoint anywhere |
| 2.2 Erasure | FINDING → F-03 | soft-delete-forever; erasure flag blocks outreach only; account deletion schema-only WIP |
| 2.3 Rectification | OK | contact/person edit UI (`contacts.py` edit routes); users via admin page |
| 2.4 Restriction/objection | OK | opt-out mechanism exists and is enforced pre-send (`db.py:366`); wider objection = organizational |
| 2.5 Automated decisions | FINDING → F-14 | scout auto-drop below threshold; outreach itself human-approved |
| 2.6 Identity + deadline plumbing | FINDING → F-13 | organizational; no process documented — folded into judgment rows |
| 3.1 Outbound inventory | OK | full URL sweep across backend/agents/mobile; see recipients table |
| 3.2 LLM/AI APIs | FINDING → F-01, F-12 | DeepSeek (CN) prominent; Anthropic (US) card OCR |
| 3.3 Frontend loads | FINDING → F-02 | htmx from unpkg.com; login page itself is clean |
| 3.4 Analytics & tracking | OK | none present (web + mobile) |
| 3.5 Email/SMS providers | OK / verify | Proton via local Bridge, STARTTLS verified for remote hosts; CH adequacy; DPA → F-12 |
| 3.6 Payment providers | N/A | no payment processing in this codebase |
| 3.7 Error reporting / APM | OK | no Sentry/APM; logs stay on-host |
| 4.1 Storage-access inventory | OK | web: session cookie (necessary); mobile: SecureStore JWT+role, AsyncStorage offline card queue (necessary) |
| 4.2 Consent gating | OK | no non-essential storage → banner-free is correct (unpkg load handled as F-02) |
| 4.3 Consent quality | N/A | no banner exists or is needed |
| 4.4 Dark patterns | N/A | no consent UI |
| 5.1 PII in logs | FINDING → F-06 | recipient emails + enrichment PII at INFO |
| 5.2 Web-server logs | OK | Apache logrotate daily, rotate 14 (verified on VPS) |
| 5.3 Retention mechanism | FINDING → F-05 | only card images expire; everything else forever |
| 5.4 Backups | OK / FINDING → F-08 | rotation bounded (7d/4w/3m) so deletions would propagate ≤3 months; but dumps world-readable |
| 5.5 Data minimization | OK (note) | `google_data` stores full Places payload "nothing lost" (`029`, `search.py:175`); GPS on card capture nullable/unused v2 field — watch both |
| 6.1 Password hashing | OK | bcrypt (`gcrm/api/security.py`) |
| 6.2 TLS | OK / FINDING → F-10 | LE TLS via Apache, app on 127.0.0.1; HSTS missing |
| 6.3 Access control | OK | require_admin / require_jwt_admin + token versioning; single-workspace; per AUDIT-2026-07-17 |
| 6.4 Audit logging | FINDING → F-07 | approvals only; table not in prod |
| 6.5 Encryption at rest | OK (judgment) | DB/images unencrypted on EU VPS — proportionality call; TOTP secrets encrypted (WIP) |
| 6.6 Breach readiness | OK (thin) | uptime watchdog + rate-limit + gitleaks; no access-anomaly review — acceptable at this scale, revisit with audit log (F-07) |
| 7.1 Schema vs inventory | OK | prod = migrations ≤029; 030–032 not applied; no undocumented PII tables |
| 7.2 Orphaned data | OK | 0 soft-deleted contacts, 0 orphaned interactions; discarded card rows keep stale `image_path` string (files verified gone — cosmetic) |
| 7.3 Stale data | OK | oldest data 2026 (young system); inbox_messages currently 0 rows; 315 contacts, 13 captures, 36 agent runs |
| 7.4 Real data in non-prod | OK (caveat) | tests use fixtures/example.com; whether prod dumps are restored to dev machines wasn't verifiable from code |
| 8.1 Hosting location | OK | IONOS SE, Berlin DE (IP 82.165.32.162 allocation verified) |
| 8.2 Backup destination | OK | same VPS, DE; no off-site copy (availability note, not a GDPR transfer issue) |
| 8.3 Volumes & file storage | OK | card-images named volume; app container access only |
| 8.4 Secrets handling | OK | `.env` gitignored, fail-closed secret resolution, gitleaks CI; break-glass ADMIN_PASSWORD transitional (see security audit) |
| 8.5 Container/CI | OK | GHCR images contain code only; CI has no personal data |
| 9.1 §26 BDSG | FINDING → F-16 | 4 staff accounts, minimal fields |
| 9.2 Art. 8 / age 16 | N/A | internal B2B tool, no minors plausibly |
| 9.3 Impressum (DDG §5) | FINDING → F-09 | absent on public login page (one-line flag, not audited) |
| 9.4 Privacy policy | FINDING → F-09 | none found anywhere |
