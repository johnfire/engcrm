# Verzeichnis von Verarbeitungstätigkeiten — engcrm

Art. 30 GDPR processing record. Code-derivable columns are maintained by the
gdpr-audit skill; columns marked (human) are business decisions — fill and
keep them.

**Controller:** ⚠ TODO (human) — <name, address, contact>
**Last code-derived update:** 2026-07-23 | **Last human review:** ⚠ TODO

## Processing activities

| # | Activity | Data categories | Data subjects | Purpose (human) | Legal basis (human) | Recipients | Third-country transfer | Retention | Security measures (Art. 32) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Lead / venue management (contacts, people, interactions, field notes) | name, email, phone, address, city, website, notes, decision-maker name, impressions, price sensitivity, visit data, full Google Places payload | prospects, venue owners/staff, individual contacts | ⚠ TODO | ⚠ TODO (consent_log defaults `legitimate_interest`) | IONOS (DE); Anthropic (US) for enabled AI stages | US transfer: DPA/DPF or SCC/TIA must be confirmed | 3 years from contact creation; direct erasure supported | TLS, bcrypt auth, RBAC, rate limiting, correlated audit log |
| 2 | Lead research & enrichment (research/scout/enrichment agents) | public business names, owner/contact names, emails, websites, addresses, coordinates; AI fit scores | publicly listed business people who never used the service | approved narrow B2B research | legitimate interest; counsel validation pending | Google Places (US), Bright Data (IL), Anthropic (US), DeepSeek (CN when selected) | US transfer requires confirmation; IL adequacy; CN requires Art. 46/TIA evidence | linked AI data and shared agent runs: 3 years maximum | SSRF guard; advisory scores; human outreach approval |
| 3 | Outreach email drafting & dispatch (approval queue → Proton SMTP) | recipient name/email, draft subject+body, reviewer notes, outcomes | prospects | ⚠ TODO | ⚠ TODO (+ UWG §7 check) | Anthropic (US), Proton (CH) | US transfer requires confirmation; CH adequacy | linked drafts: 3 years from contact creation; direct erasure supported | human approval gate; opt-out enforced pre-send |
| 4 | Inbox processing & follow-up (IMAP fetch, classification, auto-drafts) | sender email, subject, **full email body**, classification + reasoning | correspondents (prospects and anyone who emails) | ⚠ TODO | ⚠ TODO | Anthropic (US), Proton (CH) | US transfer requires confirmation; CH adequacy | matched inbox: 3 years with contact; unmatched inbox: 365 days | STARTTLS; exact-match gating for automated actions |
| 5 | Business-card capture (mobile photo → OCR → contact/person) | card image (name, title, phone, email, address), GPS of capture (nullable), extracted JSON | people whose cards are collected | ⚠ TODO | ⚠ TODO | Anthropic Claude Haiku vision (US) | US transfer requires confirmation | image deleted on confirm/discard; linked contact can be erased | JWT-admin only; upload size caps; volume not in image |
| 6 | Voice-memo capture (mobile audio → transcript → interaction) | voice audio (transient), transcript, structured summary, follow-up | staff speaker; people mentioned in memos | ⚠ TODO | ⚠ TODO | Whisper self-hosted (DE), Anthropic (US) | US transfer requires confirmation | audio not persisted; linked interactions: 3 years from contact creation | JWT-admin only; size caps |
| 7 | User account management (web + mobile login) | email, name, bcrypt hash, role, active flag, last login, encrypted TOTP secret, invitations, reset/deletion tokens | staff — §26 BDSG if employees (F-06) | ⚠ TODO | ⚠ TODO | none (local) | no | account export/deletion persistence exists; operational retention needs human policy | bcrypt, fail-closed secrets, token versioning, rate-limited login, session cookie, audit log |
| 8 | Push notifications (mobile) | Expo push token; notification title/body (may name contacts) | staff devices; contacts named in notifications | ⚠ TODO | ⚠ TODO | Expo (exp.host, US) | US transfer requires confirmation | stale tokens: 90 days | tokens opaque; sent server-side only |
| 9 | Ops logging & AI-run bookkeeping (`agent_runs`, `run_costs`, `audit_log`, app logs) | run inputs/outputs (may embed contact data), audit actor/action/target/outcome, application logs | prospects, staff | ⚠ TODO | ⚠ TODO | IONOS (DE) | no code-evidenced third-country transfer | shared runs: 3 years maximum; audit: 730 days | correlated audit context; append-only audit log; scheduled purge |
| 10 | Database backups | full dump of all categories above | all of the above | ⚠ TODO | ⚠ TODO | none — local VPS directory | no (DE) | bounded: 7 daily / 4 weekly / 3 monthly | rotation automated; **dumps world-readable — F-08** |
| 11 | Storefront-sign capture & business research (mobile photo → OCR → Places resolution → enrichment + key-people lookup) | sign image, GPS of capture (nullable), extracted business name/type/phone/website, resolved Google Place payload, researched key-people names/roles/emails/phones | business owners/staff never contacted before, individuals named on business websites | ⚠ TODO | ⚠ TODO (Art. 14 and legitimate-interest review required) | Google Places (US), Bright Data (IL), Anthropic (US), DeepSeek (CN when selected) | US transfer requires confirmation; IL adequacy; CN requires Art. 46/TIA evidence | image deleted on confirm/discard; linked records follow configured retention | JWT-admin only; upload size caps; human accept/reject before contact creation |

## Notes

- Code-derived update 2026-07-23: DeepSeek is administrator-selectable, the
  public privacy page and mobile declaration are controller-approved and versioned,
  the processor register tracks provider evidence, and `run_retention` applies the
  configured erasure/retention schedule. Human-filled cells remain untouched;
  deployment scheduling and execution still need verification.
- Assumption to confirm: the 4 user accounts are staff/colleagues (drives the
  §26 BDSG row) and the tool remains B2B-internal (drives Art. 8 N/A).
- The approved outreach/rights procedure and AI safeguards are documented in
  `docs/legal/rights-request-procedure.md` and
  `docs/legal/lead-and-ai-data-handling-policy.md`.
- Confirm the configured periods and backup expiry with the controller/counsel,
  then install and monitor the documented daily retention cron job.
