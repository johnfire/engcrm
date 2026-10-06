# Photo contact capture — issue #93

Implemented on main; backend and mobile release are required before this is available on a phone.

## Mobile workflow

- **Scan Page**: photograph a whole document or choose a library image. Extract every visible contact into a separate editable draft. Review each in **Capture Queue**, correct its fields, accept a suggested existing organization or save a new one. A named person is linked to that organization; enrichment starts after confirmation.
- **Scan Sign**: photograph a storefront sign. Request current foreground GPS, search Places with a 5 km location bias, and sort matches by distance. Review the matched business/address, accept or reject it, then save and start the existing enrichment/key-people research flow. Location bias is a preference, not a guarantee of the correct business.
- Library sign images use name-only search: the phone's current position may be unrelated to an old photo. Missing GPS is explicitly disclosed. Cards continue to use their existing flow.

## Implementation

`POST /api/documents` accepts multipart `image` and `capture_batch_id`. Vision reads printed contact rows; structured output is checked before writing drafts. Unreadable, malformed, or token-truncated responses never partially import a page. Pages containing more than 50 contacts should be photographed in smaller sections.

Migration `062_document_capture_batches.sql` adds a unique batch/row identity to `card_captures`. An advisory lock and unique index prevent duplicate drafts from simultaneous or offline retries. Each draft has an independent photo copy so discarding one cannot remove another's source. Extraction cost is recorded once per page. Existing capture-image retention/erasure applies to the individual drafts.

Offline pages retain their capture mode and original batch ID. Old card queue entries remain compatible. An unreadable queued page remains local for a future retry. The shared upload queue allows only one flush at a time and serializes index changes, so a concurrent upload cannot overwrite a newly queued photo.

The queue now distinguishes sign and card/document review screens. Document drafts carry duplicate suggestions and `document_capture` provenance. Confirmation locks the capture row and saves reviewed fields. If person creation fails, the document draft stays pending, allowing a safe retry against the already-created organization. User review and AI extraction/enrichment carry distinct audit identities and the request correlation ID.

## Verification

- Mobile TypeScript and ESLint pass.
- Mobile suite: 239 tests passed (32 suites). The first broad run encountered a cold-start timing failure in the existing organization-detail priority test; its isolated rerun and the subsequent full runs passed, without changing the test.
- Focused backend capture/extraction/search tests and PostgreSQL photo-flow tests pass. Coverage includes independent saves, repeated upload identity, person-save failure recovery, discard retention, sign GPS and research scheduling.
- Android JavaScript/Hermes bundle export succeeds. This is not an APK installation or physical camera/GPS test.
- The broader backend run passed 1,152 tests and failed four existing i18n tests. All four failures reproduce on unchanged main with a migrated test database: `TestAuthMe.test_returns_account_language`, `TestUpdateLanguage.test_rejects_unsupported_language`, `test_updates_and_sends_silent_push`, and `test_unknown_account_is_404` return 401 because their hard-coded account's token-version lookup is not mocked. No tests were removed, skipped, or weakened.
- Live AI/Places calls and a physical phone were not exercised.

## Release

Apply migrations before serving the updated API, then release the updated mobile app through existing CI/CD. Existing Anthropic, Google Places, image-volume and retention configuration are reused. No new credentials or mobile dependencies are needed. No production deploy or push was performed for this task.

SDK references checked: [Expo 56 ImagePicker](https://docs.expo.dev/versions/v56.0.0/sdk/imagepicker/), [ImageManipulator](https://docs.expo.dev/versions/v56.0.0/sdk/imagemanipulator/), [Location](https://docs.expo.dev/versions/v56.0.0/sdk/location/) and [Places Text Search](https://developers.google.com/maps/documentation/places/web-service/reference/rest/v1/places/searchText).
