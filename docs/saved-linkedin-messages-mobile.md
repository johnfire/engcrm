# Saved LinkedIn messages in mobile

Open a person's contact screen and tap **Saved LinkedIn messages**. The library
starts empty: only messages the user enters are stored. Add a label and the exact
wording, save, select a message, read its full preview, and copy it. Editing a saved
message changes the reusable original. Refresh loads changes from another device.

The inspected contact screen opens a stored LinkedIn profile through the existing
`openWebsite` / `Linking.openURL` flow. engcrm has no LinkedIn composer. **Copy message**
writes only the message body to the clipboard; **Open contact on LinkedIn** is a
separate action available when the contact has a profile. The device decides
whether the profile opens in the LinkedIn app or a browser. The user chooses the
conversation, pastes, edits, and sends manually. Copying is not logged as sending.

Messages belong to the signed-in user's account and workspace, using the existing
mobile JWT client and PostgreSQL storage patterns. A personal account is required;
the shared administrator login cannot access a shared library. There is no seed,
generated content, substitution, trimming, or translation of stored wording. Both
the API and clipboard service preserve whitespace, line breaks, and Unicode.
Labels allow 100 characters and bodies 20,000; a library of 6–12 fits comfortably.

Migration `063_saved_linkedin_messages.sql` adds private records with timestamps
and a version counter. User/workspace deletion cascades to these records. Stale
edits return 409 rather than replacing newer wording. Save errors retain the
editor contents. Successful creates and edits carry the user's identity and
request correlation ID into the append-only audit log without including wording.

## Verification

- Backend: 1,326 tests passed against a disposable PostgreSQL 16 database; one
  existing network test was deselected by the repository's `not network` gate.
  Includes real migration/persistence, exact text round trips, account/workspace
  isolation, deletion cascade, API authentication, version conflicts, and audit.
- Mobile: 295 tests across 43 suites, covering contact navigation, library
  add/select/preview/edit/copy, refresh, contact switching, and failure/retry flows.
- Repository Ruff, mobile ESLint, TypeScript, and `git diff --check` passed.
- Android Expo export produced a Hermes bundle. Expo Android autolinking resolved
  the new SDK 56 `expo-clipboard` module. No native release build or physical-device
  LinkedIn paste/send test was performed.
- The mobile CI's `npm audit --omit=dev --audit-level=critical` gate passed. npm
  still reports existing moderate/high dependency findings. The lockfile adds
  only `expo-clipboard`; none of the advisories name that module. Full audit
  counted 64 findings for the previous lock and 66 for the installed tree; the
  two additional propagated findings reference existing React Native peers.

During development, ESLint rejected an effect's indirect state update; loading
now updates state in promise callbacks. A new screen test initially used a
different error sentence from the translation; it now asserts the displayed
sentence and still verifies the library remains usable. Existing React `act`
warnings and a Starlette deprecation warning remain in the regression suites.

The backend migration/API and native mobile update need to ship together. Pushing
main triggers the existing backend deployment and Android build/Play submission
workflows. Local verification does not establish deployment or Play availability.
