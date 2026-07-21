# Verzeichnis von Verarbeitungstätigkeiten — engcrm

Art. 30 GDPR processing record. Code-derivable columns are maintained by the
gdpr-audit skill; columns marked (human) are business decisions — fill and
keep them.

**Controller:** ⚠ TODO (human) — <name, address, contact>
**Last code-derived update:** 2026-07-19 | **Last human review:** ⚠ TODO

## Processing activities

| # | Activity | Data categories | Data subjects | Purpose (human) | Legal basis (human) | Recipients | Third-country transfer | Retention | Security measures (Art. 32) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Lead / venue management (contacts, people, interactions, field notes) | name, email, phone, address, city, website, notes, decision-maker name, impressions, price sensitivity, visit data, full Google Places payload | prospects, venue owners/staff, individual contacts | ⚠ TODO | ⚠ TODO (consent_log defaults `legitimate_interest`) | DeepSeek (drafting/enrichment context) | **yes — China, no mechanism found (F-01)** | no contact/lead purge found; soft delete only (F-02) | TLS, bcrypt auth, RBAC, EU VPS, rate limiting, correlated audit log |
| 2 | Lead research & enrichment (research/scout/enrichment agents) | business names, owner/contact names, emails, websites, addresses, coordinates; AI fit scores | publicly listed business people who never used the service | ⚠ TODO | ⚠ TODO (Art. 14 duty open — F-11) | Google Places (US), OSM (EU), Bright Data (IL), DeepSeek (CN) | yes — US (verify DPF), CN (F-01); IL adequate | none found | SSRF guard on fetches; scores logged in `ai_analysis` |
| 3 | Outreach email drafting & dispatch (approval queue → Proton SMTP) | recipient name/email, draft subject+body, reviewer notes, outcomes | prospects | ⚠ TODO | ⚠ TODO (+ UWG §7 check — F-13) | DeepSeek (drafting, CN), Proton (CH) | yes — CN (F-01); CH adequate | none found — drafts kept forever | human approval gate on every send; opt-out enforced pre-send |
| 4 | Inbox processing & follow-up (IMAP fetch, classification, auto-drafts) | sender email, subject, **full email body**, classification + reasoning | correspondents (prospects and anyone who emails) | ⚠ TODO | ⚠ TODO | DeepSeek (classification/drafting, CN), Proton (CH) | yes — CN (F-01) | none found — bodies stored indefinitely (F-05) | STARTTLS to remote hosts; exact-match gating for automated actions |
| 5 | Business-card capture (mobile photo → OCR → contact/person) | card image (name, title, phone, email, address), GPS of capture (nullable), extracted JSON | people whose cards are collected | ⚠ TODO | ⚠ TODO | Anthropic Claude Haiku vision (US) | yes — US, verify DPF/DPA (F-12) | image deleted on confirm/discard (verified in prod); extracted text kept with contact | JWT-admin only; upload size caps; volume not in image |
| 6 | Voice-memo capture (mobile audio → transcript → interaction) | voice audio (transient), transcript, structured summary, follow-up | staff speaker; people mentioned in memos | ⚠ TODO | ⚠ TODO | Whisper self-hosted (DE — no transfer); DeepSeek (structuring, CN) | yes — CN (F-01) | audio never persisted; transcript kept as interaction, no expiry | JWT-admin only; size caps |
| 7 | User account management (web + mobile login) | email, name, bcrypt hash, role, active flag, last login, encrypted TOTP secret, invitations, reset/deletion tokens | staff — §26 BDSG if employees (F-06) | ⚠ TODO | ⚠ TODO | none (local) | no | account export/deletion persistence exists; operational retention needs human policy | bcrypt, fail-closed secrets, token versioning, rate-limited login, session cookie, audit log |
| 8 | Push notifications (mobile) | Expo push token; notification title/body (may name contacts) | staff devices; contacts named in notifications | ⚠ TODO | ⚠ TODO | Expo (exp.host, US) | yes — US, verify DPA (F-12) | tokens never expired (0 in prod currently) | tokens opaque; sent server-side only |
| 9 | Ops logging & AI-run bookkeeping (`agent_runs`, `run_costs`, `audit_log`, app logs) | run inputs/outputs (may embed contact data), audit actor/action/target/outcome, application logs | prospects, staff | ⚠ TODO | ⚠ TODO | none (on-host) | no | no application-data retention schedule found | correlated audit context; append-only audit log in code; deployed state not re-verified |
| 10 | Database backups | full dump of all categories above | all of the above | ⚠ TODO | ⚠ TODO | none — local VPS directory | no (DE) | bounded: 7 daily / 4 weekly / 3 monthly | rotation automated; **dumps world-readable — F-08** |
| 11 | Storefront-sign capture & business research (mobile photo → OCR → Places resolution → enrichment + key-people lookup) | sign image, GPS of capture (nullable), extracted business name/type/phone/website, resolved Google Place payload, researched key-people names/roles/emails/phones | business owners/staff never contacted before, individuals named on business websites | ⚠ TODO | ⚠ TODO (legitimate interest B2B outreach — same basis as row 2; third-party people identified from public web pages, no direct contact yet — Art. 14 duty likely applies, same as F-11) | Google Places (US), Bright Data (IL) / DuckDuckGo (fetch+search), Anthropic Claude Haiku (US, vision), DeepSeek (CN, key-people extraction) | yes — US (verify DPF/DPA, same as F-12), CN (F-01); IL adequate | image deleted on confirm/discard (reuses `CARD_IMAGE_RETENTION_DAYS`); no retention policy yet for researched people rows (⚠ new gap) | JWT-admin only; upload size caps; confirm screen requires human accept/reject of the resolved Place before a contact is created (mis-resolution guardrail) |

## Notes

- Re-audited 2026-07-19 (report: `gdpr-audit-2026-07-19.md`); human-filled
  cells remain untouched. The repo now includes account lifecycle and audit-log
  machinery; the permitted SSH probe could not verify deployment state.
- Assumption to confirm: the 4 user accounts are staff/colleagues (drives the
  §26 BDSG row) and the tool remains B2B-internal (drives Art. 8 N/A).
- Policy line to adopt per F-15: no special-category data (health, religion,
  politics, etc.) in free-text notes fields.
- Set retention periods for leads, inbox bodies, interactions, AI data, audit
  records and push tokens; then implement and operate the corresponding purge.
- New with row 11 (sign-scan research, added when the feature was built): no
  retention period set yet for `people` rows sourced from `sign_research` —
  decide one and fold it into the purge work above.
