# Mobile privacy declaration — release checklist

This is the source artifact for the Google Play Data Safety and Apple App Store
privacy declarations. It describes the app as built on 2026-07-23; update it
before each store submission or material data-flow change.

## Data collected and purpose

| Data | Why the Android app processes it | Shared with |
|---|---|---|
| Staff account email, name, role and password hash | authentication and access control | EngCRM/IONOS (DE) |
| Business-card/sign photo and extracted contact data | create/review CRM contacts | Anthropic (US) for OCR when capture is used; EngCRM/IONOS (DE) |
| Optional capture GPS | resolve a photographed venue | Google Places (US), EngCRM/IONOS (DE) |
| Contact, lead, interaction and inbox data | CRM and human-approved outreach | Proton (CH); Anthropic (US) for enabled AI steps |
| Expo push token and notification content | notify signed-in staff | Expo (US) |

## Store declaration actions

- Provide `https://engcrm.christopherrehm.de/privacy` as the privacy-policy URL.
- Declare the rows above, including optional location and photos, in each store's
  current questionnaire.
- Do not claim data is not shared: the listed processors receive data when their
  associated feature is used.
- **Controller approval:** Christopher Rehm approved this declaration on
  2026-07-23 for use as the current store-submission source.
- Before each submission, confirm the store questionnaire still exactly matches
  the enabled production features and this data-flow inventory. Provider
  agreements and international-transfer safeguards are tracked separately in
  `docs/legal/processor-transfer-register.md` (GitHub issue #40).
