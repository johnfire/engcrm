# GDPR technical audit — engcrm — 2026-07-19

> **This is not legal advice.** This report lists technical findings from a
> code, database, and deployment review against GDPR / BDSG / TDDDG. Legal
> conclusions — legal basis, contract status, purposes — require a human
> (lawyer/DPO) and are explicitly flagged as judgment calls below.

**Scope:** engcrm commit `35d6b6e`: FastAPI/web backend, five AI agents, Expo Android app, PostgreSQL migrations, Docker/CI and GDPR documentation. This is a re-audit of [2026-07-18](gdpr-audit-2026-07-18.md). A single read-only SSH probe could not establish the deployed revision because `/opt/engcrm` is not a Git checkout; database, backup, and live-header evidence is therefore not re-verified. No project files other than this report and the Art. 30 record were changed.

**Auditor:** GPT-5, gdpr-audit skill v1.1
**Previous audit:** [2026-07-18](gdpr-audit-2026-07-18.md)

## Summary

The code now includes material improvements since the previous review: correlated user/AI audit logging, account-export and account-deletion persistence machinery, privacy documentation, a local web asset path, real-Postgres migration coverage, and security controls. This is not a compliance verdict: several high-impact external facts cannot be answered from code.

**6 findings: 1 violation-indicator, 2 gaps, 3 needs-legal-judgment.**

Priority order: (1) stop or legally safeguard the demonstrated DeepSeek/China personal-data transfer; (2) implement and operate actual contact/lead erasure and retention jobs; (3) obtain legal decisions and DPAs for outreach, processors, and scraped-lead notice duties.

## Findings

### Violation indicators

#### F-01 — Personal data is sent to DeepSeek in China (Art. 44–49, 28)
- **Evidence:** `gcrm/config.py` configures DeepSeek; `gcrm/tools/llm.py` calls its API. Agent prompts process contact names, emails, notes, inbox bodies, card/OCR data and voice-derived text.
- **Why it's a problem:** China has no EU adequacy decision. No Art. 46 transfer mechanism, TIA, or processor terms were found in the repository for this flow.
- **Suggested fix:** route personal-data prompts to an EU/adequate provider, pseudonymize before processing, or obtain and document a valid Art. 46 mechanism and Art. 28 terms.

### Gaps

#### F-02 — Contact erasure and retention remain incomplete (Art. 17; Art. 5(1)(e))
- **Evidence:** `gcrm/api/routers/contacts.py` still soft-deletes contacts; `gcrm/tools/db_approvals.py` records opt-out but does not erase. `gcrm/tools/db_account_lifecycle.py` and migration `031_workspace_account_lifecycle.sql` add account-deletion/export support, but no contact/lead purge job or retention scheduler was found.
- **Why it's a problem:** blocking outreach is not erasure, and indefinite storage of inbox content, interactions, AI inputs/outputs and deleted leads lacks a storage-limitation mechanism.
- **Suggested fix:** implement a reviewed erasure workflow covering contacts, people, interactions, inbox matches, AI data and card media; add documented per-category retention and a scheduled purge.

#### F-03 — Public privacy notice / mobile-store privacy declaration not evidenced (Art. 13–14; DDG §5)
- **Evidence:** GDPR documents exist under `docs/gdpr/`, but no public privacy or Impressum route/link was found in `gcrm/ui/templates/`; no app-store privacy-policy URL/declaration is versioned with the Android app.
- **Why it's a problem:** internal staff and scraped leads need the applicable information; a public login and published app need accessible notices.
- **Suggested fix:** publish and link a reviewed privacy notice and Impressum; ensure Play/App Store declarations match the actual mobile and processor flows.

### Needs legal judgment

#### F-04 — Processor contracts and transfers (Art. 28, 44–49)
- **Context:** code sends data to DeepSeek (CN), Anthropic card OCR (US), Expo push (US), Proton (CH), Google Places (US query/result flow), and Bright Data (IL).
- **Question for Chris/lawyer:** confirm each DPA and transfer mechanism; verify current EU-US DPF/SCC status for US vendors. Switzerland and Israel have adequacy decisions, but processor terms still need review.

#### F-05 — Scraped-lead notice and cold outreach basis (Art. 14; Art. 6(1)(f); UWG §7)
- **Context:** research/enrichment ingest publicly listed business/contact data; `consent_log` records legitimate interest and opt-outs, while agents draft outreach.
- **Question for Chris/lawyer:** document the LIA, Art. 14 notice/source process, and whether the intended B2B email channel satisfies UWG §7.

#### F-06 — AI scoring and free-text special-category risk (Art. 9, 22)
- **Context:** scout scoring can drop leads automatically; contact/person/voice notes can contain unrestricted sensitive information.
- **Question for Chris/lawyer:** confirm the B2B scoring effect is not Art. 22-significant and adopt a policy forbidding special-category data in free-text notes.

## Recipients & transfers table

| Recipient | Data sent | Country | Adequacy/mechanism | DPA status |
|---|---|---|---|---|
| DeepSeek | lead/contact, email, OCR and voice-derived prompt content | China | no adequacy; F-01 | not found |
| Anthropic | business-card image/OCR context | US | verify DPF/SCC | needs legal judgment |
| Expo | device token and notification text | US | verify DPF/SCC | needs legal judgment |
| Proton | outreach and inbox email content | Switzerland | adequacy | confirm DPA |
| Google Places | location/industry searches; results ingested | US | verify provider terms | needs legal judgment |
| Bright Data | target website URLs/fetched content | Israel | adequacy | confirm DPA |
| IONOS VPS | application/database/backups | Germany | EU | controller hosting contract |

## Checklist appendix

| Item | Status | Note |
|---|---|---|
| 1.1 Schema sweep | OK | contacts, people, users, emails, locations, notes, audit/run data, push tokens inventoried |
| 1.2 Special categories | FINDING → F-06 | unrestricted free text |
| 1.3 Uploads & media | OK | card image and transient voice flows identified |
| 1.4 Derived/imported data | FINDING → F-05 | scraped/enriched leads |
| 1.5 Identifiers in URLs | OK | no PII query strings found |
| 2.1 Access/export | OK | account lifecycle export machinery exists; operational coverage must be tested |
| 2.2 Erasure | FINDING → F-02 | account mechanism exists; lead/contact erasure/purge absent |
| 2.3 Rectification | OK | contact/person and account settings paths |
| 2.4 Restriction/objection | OK | opt-out blocks outreach; broader policy is F-05 |
| 2.5 Automated decisions | FINDING → F-06 | lead scoring judgment call |
| 2.6 Identity/deadline | FINDING → F-05 | operational procedure not evidenced |
| 3.1–3.7 Recipients | FINDING → F-01/F-04 | table above; no analytics/APM/payment found |
| 4.1–4.4 Consent/cookies | OK / N/A | necessary session/SecureStore only; no non-essential tracking found |
| 5.1 PII logs | OK | correlated audit logging added; continue avoiding raw PII in application logs |
| 5.2 Web logs | N/A | not re-verified after SSH scope failure |
| 5.3 Retention | FINDING → F-02 | no scheduled retention found |
| 5.4 Backups | N/A | not re-verified after SSH scope failure |
| 5.5 Minimization | OK (watch) | full Places payload and free text warrant periodic review |
| 6.1 Password hashing | OK | bcrypt |
| 6.2 TLS/HSTS | OK (repo evidence) | prior remediation; live header not re-verified |
| 6.3 Access control | OK | JWT/session guards and admin dependencies |
| 6.4 Audit logging | OK | audit context/log tools cover user and AI state changes |
| 6.5 Encryption at rest | N/A | proportionality/hosting fact needs review |
| 6.6 Breach readiness | OK (thin) | audit trail and CI/security controls; operational response is human-owned |
| 7.1–7.4 Database pass | N/A | live DB was not reachable through the permitted probe |
| 8.1–8.5 Deployment pass | N/A | live deployment could not be re-verified |
| 9.1 §26 BDSG | FINDING → F-06 | staff-account employment context needs confirmation |
| 9.2 Minors | N/A | internal B2B tool |
| 9.3 Impressum | FINDING → F-03 | no public link evidenced |
| 9.4 Privacy policy | FINDING → F-03 | no public link evidenced |
| 9.5 App-store obligations | FINDING → F-03 | declaration/URL not versioned |
