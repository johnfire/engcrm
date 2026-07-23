# Lead and AI data-handling policy

Effective 2026-07-23. This operational policy applies to all EngCRM users and
AI-agent configuration.

- Collect only public business-contact data relevant to a documented B2B opportunity.
- Record the public source of indirectly collected lead data where available.
- Use a legitimate-interest assessment for this narrowly tailored B2B research
  and one-to-one, human-approved outreach; do not run bulk marketing campaigns.
- Honor an objection immediately; do not create outreach drafts for an opted-out
  or erased contact.
- Include the public privacy-information link in every first-contact email.
- Do not enter health, religion, political opinions, union membership, biometric
  data, sexual life/orientation, or criminal-offence information in any notes,
  inbox summaries, card annotations, voice transcripts, or AI prompts.
- AI lead scores are prioritisation suggestions only. A human reviews outreach
  and may correct or override a score; no score makes a legal or similarly
  significant decision about a natural person.
- An administrator may select DeepSeek in Settings. That selection is an
  operational transfer decision: maintain the corresponding Art. 28/46/TIA
  evidence in the processor register before using it beyond personal testing.
- Retain each contact and its linked AI analyses, approval drafts, interactions,
  matched inbox messages, related people and card records for three years from
  the contact's creation date, whether or not outreach occurs. The daily
  retention job then permanently erases that linked data as one unit.
- Shared agent-run records are retained for the same three-year maximum. Inbox
  messages not matched to a contact follow the separate 365-day inbox period.
- Run `python -m gcrm.supervisor.run_retention` daily and investigate any failed
  run before the next business day.

## Approved controller decisions

- Research is limited to public business sources and business-relevant contact
  information. The first contact provides the privacy-information link and a
  direct opt-out route.
- An objection removes the contact from all future outreach immediately.
- Rights requests go to `car2187bus@pm.me`; verify the requester from the
  recorded contact channel where possible and respond within one month.
- Human approval is required before outreach. AI scores only prioritise work;
  they cannot accept, reject, or otherwise significantly decide for a person.

## Remaining controller decisions

Counsel/controller must validate the legitimate-interest assessment and UWG
position, processor agreements, transfer safeguards, backup expiry, and final
per-category periods.
