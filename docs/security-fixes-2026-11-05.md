# High-priority security fixes — 5 November 2026

The four high-priority findings in the audit are fixed in local source and
verified on the isolated staging site. Production has not received these fixes;
the changes must be pushed and deployed before the live findings can be closed.

## What changed

- **A01, browser-session revocation:** cookies carry an opaque server-session
  identifier. PostgreSQL stores only its hash and a fixed 14-day expiry. Each
  web request refreshes active account, token version, workspace and role from
  the server. Logout revokes that session; password resets, deactivation and
  account deletion invalidate existing sessions. Stale role claims cannot keep
  administrator privileges. Emergency browser sessions remain supported when configured,
  are individually revocable, and stop working when the emergency password is
  changed/unset. Their password fingerprint is keyed; the raw password is never
  sent to PostgreSQL. Authentication storage failures refuse access.
- **A02, workspace isolation:** authenticated transactions switch to the
  non-login, non-superuser, non-bypass `engcrm_workspace` role. Row policies
  protect workspace-owned tables and related records. Insert/update policies
  refuse foreign parent links, including when a query omits its own filter.
  Browser identity is established before dispatch; an async bearer dependency
  establishes the verified scope before worker-thread handlers run. Research
  subprocesses and company-lookup threads retain that scope. User creation,
  invitations and AI settings use the active workspace.
- **A03, forged browser requests:** mutating web requests require an exact
  matching Origin (or Referer fallback) and the session-bound token. Server
  rendering adds hidden fields to mutating forms. HTMX and same-origin fetch
  calls send the corresponding header. Bearer-only API/MCP requests keep their
  separate authentication. Token-bearing HTML is private/no-store. Staging's
  proxy preserves the original Host and port; HTTPS proxy origins are covered.
- **A04, suppressed-recipient sends:** web approvals, held drafts and the local
  MCP approval tool check current suppression before claiming a draft and again
  immediately before SMTP. The final check locks the recipient while sending,
  serializing with opt-outs/erasure. Any opt-out/erasure record blocks sending;
  both organization links on a person are checked. A refusal after claiming is
  recorded as unsent with a reason and audit event. Held/MCP approvals claim
  atomically so concurrent approvals cannot send the same draft twice. Mobile
  approval flags use the recipient gate too.

The related **A09** token-version database-error behavior was strengthened to
return 503. Its existing test now asserts refusal rather than fail-open access.
Other medium/low findings, including MFA, dependency/image updates and account
lifecycle gaps, remain open. This does not make the product fully audited or
ready for unrelated customers in a shared database; retain separate staging and
reviewer databases.

## Validation

- Before fixes: 14 failing security regressions and one legitimate-flow pass.
- Complete unit run: **1,587 passed**, one existing skip.
- Complete PostgreSQL integration/workflow run: **243 passed**. Coverage includes
  both workspace directions, related-record reads/writes, real restricted-role
  checks, a fresh worker interpreter, role changes, expired/revoked sessions,
  shared-admin revocation, native forms, suppression races, person drafts and
  concurrent approval claims, invited signup and correctly scoped sign-in audit
  records. Background AI work retains the request correlation ID while recording
  its own AI actor rather than attributing the action to the requesting user.
- Four controlled mutations in an isolated source copy removed logout
  revocation, token comparison, role enforcement, and recipient suppression.
  Every mutant was killed by the regression tests. This was targeted boundary
  mutation coverage, not exhaustive mutation analysis of the application.
- Ruff and whitespace checks passed. New security helpers have cyclomatic
  complexity at or below 10; an exact five-statement AST duplication check of
  changed source found no repeated blocks.
- Staging built successfully; migrations 078 and 079 applied to the existing
  fictional database. A real browser signed in and submitted an authenticated
  form. External network denial, empty provider/mail credentials, and actual
  restricted database-role use were verified again.
- Existing route tests now obtain real browser-verification tokens. Tests that
  intentionally exercise security boundaries manage their own credentials;
  they do not use that compatibility fixture. No test was deleted or skipped
  to hide a failure. The earlier mobile timing failure remains a separate item;
  no Android code changed in this task.

## Deployment and operational constraints

1. Apply **078_web_sessions.sql** and **079_workspace_row_security.sql** using
   the migration/operator account before starting the new app. Migration 079
   creates/grants the restricted role; it needs permission to create roles,
   grant membership and alter policies. Stock Compose/CI PostgreSQL bootstrap
   credentials have those privileges. Verify any separately managed deployment.
2. Existing browser cookies require a fresh sign-in after deployment. Existing
   account-backed phone tokens remain usable when the account/version is valid.
3. Keep `APP_PUBLIC_URL` set to the actual HTTPS origin and secure cookies enabled
   on production. Check proxy Host preservation, normal forms, HTMX, file imports
   and sign-out/replay once deployed.
4. Manual CLI maintenance/migrations deliberately retain the operator role;
   request/connector/job transactions are scoped. This protects against missing
   query predicates, not compromised operator credentials or arbitrary malicious
   SQL with the bootstrap connection. Separating physical runtime/migration
   credentials remains part of the medium-priority deployment-hardening work.
5. New workspace-owned tables need row policies and explicit runtime grants.
   The integration test detects workspace columns without row security. Keep
   cross-workspace negative tests when adding routes and relations.

Local staging remains at `http://127.0.0.1:8086/`. It contains fictional records
only and cannot send mail or call external services. No production deployment,
mail delivery, or cloud-account permission change occurred during remediation.
