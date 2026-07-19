# Verzeichnis von Verarbeitungstätigkeiten — engcrm

Art. 30 GDPR processing record. Code-derivable columns are maintained by the
gdpr-audit skill; columns marked (human) are business decisions — fill and
keep them.

**Controller:** ⚠ TODO (human) — <name, address, contact>
**Last code-derived update:** 2026-07-18 | **Last human review:** ⚠ TODO

## Processing activities

| # | Activity | Data categories | Data subjects | Purpose (human) | Legal basis (human) | Recipients | Third-country transfer | Retention | Security measures (Art. 32) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Lead / venue management (contacts, people, interactions, field notes) | name, email, phone, address, city, website, notes, decision-maker name, impressions, price sensitivity, visit data, full Google Places payload | prospects, venue owners/staff, individual contacts | ⚠ TODO | ⚠ TODO (consent_log defaults `legitimate_interest`) | DeepSeek (drafting/enrichment context) | **yes — China, no mechanism found (F-01)** | none found — soft delete only (F-03/F-05) | TLS, bcrypt auth, RBAC, EU VPS, rate limiting |
| 2 | Lead research & enrichment (research/scout/enrichment agents) | business names, owner/contact names, emails, websites, addresses, coordinates; AI fit scores | publicly listed business people who never used the service | ⚠ TODO | ⚠ TODO (Art. 14 duty open — F-11) | Google Places (US), OSM (EU), Bright Data (IL), DeepSeek (CN) | yes — US (verify DPF), CN (F-01); IL adequate | none found | SSRF guard on fetches; scores logged in `ai_analysis` |
| 3 | Outreach email drafting & dispatch (approval queue → Proton SMTP) | recipient name/email, draft subject+body, reviewer notes, outcomes | prospects | ⚠ TODO | ⚠ TODO (+ UWG §7 check — F-13) | DeepSeek (drafting, CN), Proton (CH) | yes — CN (F-01); CH adequate | none found — drafts kept forever | human approval gate on every send; opt-out enforced pre-send |
| 4 | Inbox processing & follow-up (IMAP fetch, classification, auto-drafts) | sender email, subject, **full email body**, classification + reasoning | correspondents (prospects and anyone who emails) | ⚠ TODO | ⚠ TODO | DeepSeek (classification/drafting, CN), Proton (CH) | yes — CN (F-01) | none found — bodies stored indefinitely (F-05) | STARTTLS to remote hosts; exact-match gating for automated actions |
| 5 | Business-card capture (mobile photo → OCR → contact/person) | card image (name, title, phone, email, address), GPS of capture (nullable), extracted JSON | people whose cards are collected | ⚠ TODO | ⚠ TODO | Anthropic Claude Haiku vision (US) | yes — US, verify DPF/DPA (F-12) | image deleted on confirm/discard (verified in prod); extracted text kept with contact | JWT-admin only; upload size caps; volume not in image |
| 6 | Voice-memo capture (mobile audio → transcript → interaction) | voice audio (transient), transcript, structured summary, follow-up | staff speaker; people mentioned in memos | ⚠ TODO | ⚠ TODO | Whisper self-hosted (DE — no transfer); DeepSeek (structuring, CN) | yes — CN (F-01) | audio never persisted; transcript kept as interaction, no expiry | JWT-admin only; size caps |
| 7 | User account management (web + mobile login) | email, name, bcrypt hash, role, active flag, last login; WIP: encrypted TOTP secret, invitations, reset/deletion tokens | staff (4 accounts) — §26 BDSG if employees (F-16) | ⚠ TODO | ⚠ TODO | none (local) | no | none found — accounts kept until admin-deactivated; deletion flow WIP (F-03) | bcrypt, fail-closed secrets, token versioning, rate-limited login, session cookie |
| 8 | Push notifications (mobile) | Expo push token; notification title/body (may name contacts) | staff devices; contacts named in notifications | ⚠ TODO | ⚠ TODO | Expo (exp.host, US) | yes — US, verify DPA (F-12) | tokens never expired (0 in prod currently) | tokens opaque; sent server-side only |
| 9 | Ops logging & AI-run bookkeeping (`agent_runs`, `run_costs`, app logs; audit_log WIP) | run inputs/outputs (may embed contact data), recipient emails in app logs (F-06) | prospects, staff | ⚠ TODO | ⚠ TODO | none (on-host) | no | none found — journald/rotation only for Apache (14d) | on-host only; audit-log table pending deploy (F-07) |
| 10 | Database backups | full dump of all categories above | all of the above | ⚠ TODO | ⚠ TODO | none — local VPS directory | no (DE) | bounded: 7 daily / 4 weekly / 3 monthly | rotation automated; **dumps world-readable — F-08** |

## Notes

- First audit 2026-07-18 (report: `gdpr-audit-2026-07-18.md`); all rows
  code-derived, no human-filled cells yet.
- The audited working tree contains uncommitted WIP (migrations 030–032, TOTP,
  account lifecycle) not yet in production — rows 7 and 9 describe both states
  explicitly. Re-derive after that work lands.
- Assumption to confirm: the 4 user accounts are staff/colleagues (drives the
  §26 BDSG row) and the tool remains B2B-internal (drives Art. 8 N/A).
- Policy line to adopt per F-15: no special-category data (health, religion,
  politics, etc.) in free-text notes fields.
- Retention column is uniformly "none found" outside cards/backups — filling
  the Purpose/Legal-basis columns and setting retention periods (F-13) is the
  main human homework from this audit.
