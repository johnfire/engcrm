# Business / legal identity — reference for Impressum & future legal docs

Source of truth for the operator identity used on the engcrm Impressum page
(`/impressum`) and for any future legal document (Datenschutzerklärung, Play
Store listing, invoices). Provided by Chris on 2026-07-21. Update this file
first if any of these facts change, then re-derive the published pages from it.

## Identity

- **Legal name:** Christopher Rehm (natural person / freelancer — no GmbH or
  other registered legal form given)
- **Trading as (Geschäftsbezeichnung):** Rehm KI Consulting
- **Address:**
  Alpenstr. 3
  86836 Klosterlechfeld
  Deutschland
- **Email:** car2187bus@pm.me
- **Phone:** not provided — not published. §5 DDG's contact requirement is
  satisfied by email alone per current case law (BGH, 2022) provided
  responses are prompt; add a phone number here if that ever becomes a
  concern, or if response times can't stay fast.

## VAT / registration status

- **Not provided/confirmed.** No Umsatzsteuer-ID (§27a UStG) given, no
  Handelsregister entry mentioned. §5 DDG only requires the VAT-ID field
  when one exists, so the published Impressum omits it entirely rather than
  asserting a Kleinunternehmer (§19 UStG) status that hasn't been confirmed.
- **TODO:** once VAT/registration status is settled (Kleinunternehmer vs.
  full VAT registration vs. a registered legal form), update this file and
  add the corresponding line to `gcrm/ui/templates/impressum.html`.

## Business status (context only — not published)

- As of 2026-07-21: **business is in start-up phase, not yet actively
  offering paid services.** This is relevant context for *whether* an
  Impressum is even legally required yet (§5 DDG applies to "geschäftsmäßige"
  telemedia), but the app already has a publicly reachable login page, so we
  built the Impressum anyway to be safe — see
  `docs/gdpr/gdpr-audit-2026-07-18.md` (F-09) and
  `docs/gdpr/gdpr-audit-2026-07-19.md` (F-03), both of which flagged the
  missing Impressum before this fact was known.
- This status is **not stated on the public Impressum page** — no legal
  requirement to disclose it there, and it will go stale the moment the
  business starts invoicing. Revisit this file (and the VAT section above)
  when that changes.

## Where this is used

- `gcrm/ui/templates/impressum.html` — the published Impressum, linked from
  the web app (login page + nav) and the Android app (login screen + settings).
- Not yet used for a Datenschutzerklärung (privacy policy) — that's a
  separate, larger piece of work (see the open GDPR findings) and wasn't
  part of this task.
