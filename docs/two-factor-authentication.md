# Two-factor authentication

Individual accounts can opt in at **Account settings → Two-factor authentication**.
Use an authenticator app with six-digit, time-based codes. Setup supports an
authenticator link and a manual key; no external QR or authentication service
receives the seed. Setup expires after ten minutes and remains disabled until
the current password and a valid authenticator code have been proved.

Save the ten recovery codes shown after activation. Each is a random 128-bit
value, works once together with the account password, and is stored only as a
SHA-256 hash. Codes are displayed once. Website and phone login accept either
an authenticator code or a recovery code. Accounts without MFA can leave the
code field blank. The phone's Settings screen links to website management.

Replacing recovery codes or disabling MFA requires the current password and
an unused second-factor code. These changes, and initial activation, increment
the account token version: all previous website and phone sessions must sign
in again. Replacing recovery codes invalidates the old set. Password reset
does not remove MFA. If both the authenticator and all recovery codes are lost,
there is no email-only factor reset or newly added administrator bypass.

Authenticator counters and recovery-code consumption are protected by a user
row lock, preventing simultaneous reuse across website and mobile login. Codes
allow one 30-second step of clock skew; an accepted counter cannot be reused.
Ten failed factor checks impose a five-minute account cooldown, in addition
to the existing per-client authentication rate limit. Authentication-storage
failure refuses credentials with 503. Factor-change and recovery-use audit
events include the user, workspace and request correlation ID, without secrets.

Pending and active seeds use the existing encrypted account-secret storage.
The management page uses private/no-store caching, no third-party scripts,
a restrictive CSP, frame protection and no-referrer policy. It also uses the
existing authenticated session and CSRF validation.

The documented, separately configured **shared emergency administrator** remains
independent of individual accounts. It cannot enroll in account MFA. Leaving
`ADMIN_PASSWORD` configured still permits that emergency access; unset it when
it is no longer needed. Account MFA is not a claim that this separate access
path has a second factor.

## Release requirements

Apply migration `080_mfa_enforcement.sql` before starting this application version.
Existing accounts remain opt-in; this release does not enable MFA for anyone
automatically. Publish the updated phone app before an account enables MFA on
an older phone version: the old login screen cannot supply a second factor.
The reviewer server needs the same migration/backend update to support MFA.
Configure a stable `ACCOUNT_ENCRYPTION_KEY`; rotating it without migrating stored
seeds makes existing authenticator seeds unreadable.

## Validation — 5 November 2026

- Four original bypass regressions failed before remediation and passed after it.
- Complete Python unit suite: **1,631 passed**, one existing skip.
- Complete real-PostgreSQL integration/workflow suite: **299 passed**.
- Final focused MFA workflow suite: **14 passed**, including setup expiry with an
  otherwise valid code, cross-channel replay, concurrent recovery use, recovery
  replacement, session revocation, password reset, hostile Origin and storage failure.
- Complete phone suite: **394 passed**; typecheck and changed-file lint passed.
- Five isolated mutations were killed: login enforcement, authenticator replay,
  recovery consumption, session revocation and enrollment expiry. The expiry
  test was strengthened after its first mutation survived.
- Local staging image built, migration applied, and browser sign-in plus
  navigation to the new management page verified. Enrollment/change workflows
  used real HTTP handlers in the isolated database tests.
- Existing auth unit mocks were updated to the new shared login boundary;
  assertions were preserved, and translated errors now mention the second factor.

Guidance: [OWASP MFA](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html)
and [RFC 6238](https://www.rfc-editor.org/rfc/rfc6238).
