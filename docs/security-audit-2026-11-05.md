# EngCRM security audit — 5 November 2026

## Decision

**Security work remains open.** Four high-priority application findings were
reproduced locally: browser-session revocation, workspace isolation, missing
CSRF validation, and bypass of organization suppression at approval time.
Do not use workspaces to isolate unrelated customers, reviewers, or test data.
The separate reviewer database described in `google-play-reviewer.md` is the
correct isolation approach. Local staging now uses a separate database too.

This is an internal engineering audit, not a claim that the site is secure or
an exhaustive independent penetration-test certification. Findings below are
unfixed unless explicitly stated otherwise. No production data was changed,
no production login was attempted, and no actual audit email was sent.

## Scope and method

- Source review began at `49a7139` on `main`. Unrelated Maps work continued in
  this shared checkout (`a5c16e2` during review); those edits were excluded from
  the audit changes. Application tests used the checked-out source.
  Further concurrent lead-import edits appeared at wrap-up; those later edits
  were neither audited nor included in the security commit. This is a dated
  snapshot, not an attestation of the evolving checkout or running production.
- FastAPI website, mobile JSON API, authentication, account lifecycle,
  PostgreSQL tenancy, uploads, URL fetching, remote MCP, mail approvals,
  agent boundaries, Docker packaging, and GitHub workflow configuration.
- Nineteen unauthenticated HTTPS requests to the production host, plus the
  HTTP redirect and language-cookie response. Requests were low-volume,
  read-only, and did not enumerate real record IDs.
- Disposable PostgreSQL 16 database on local port 55439; invented users in
  two workspaces; real HTTP application handlers exercised through TestClient.
  Only the email sender was replaced for the suppression reproduction.
- Fresh local staging image built from the repository Dockerfile, with
  separate database/secrets and no application Internet egress. Browser login
  and display of the invented organization were verified.
- Current PyPI/npm vulnerability lookups, Bandit source scan, Gitleaks history
  scan, and Trivy image scan. Scanner output was investigated rather than
  equated with confirmed exploitability.

## Findings and acceptance criteria

| ID | Priority | Finding | Evidence level |
| --- | --- | --- | --- |
| A01 | High | Browser credentials cannot be effectively revoked | Local reproduction |
| A02 | High | Workspace boundaries are incomplete | Local reproduction + schema |
| A03 | High | Cookie-authenticated writes lack CSRF validation | Local reproduction + source |
| A04 | High | Approving a queued email bypasses do-not-contact | Local reproduction with fake sender |
| A05 | Medium | Enabled MFA is ignored at login | Local reproduction |
| A06 | Medium | Mobile dependencies include high advisories; CI permits them | Current advisory scan + workflow |
| A07 | Medium | Container has high OS findings and excess privilege/tooling | Image scan + configuration |
| A08 | Medium | Public responses lack browser security headers | Production HTTP observations |
| A09 | Medium | Mobile revocation check fails open on database errors | Local reproduction + existing test |
| A10 | Low | Production secret validation accepts trivial values | Local reproduction |

### A01 — Browser-session revocation

`gcrm/api/auth.py:require_login` trusts the role in the signed session cookie.
It does not check the stored account, active flag, or token version.
`gcrm/tools/db_users.py` increments token versions on password changes and
account disablement, but only bearer-token validation consumes this value.
Logout merely tells the browser to clear its cookie.

Reproduction with a normally issued cookie:

- Disable the account; `GET /users/` still returns **200**.
- The same account's bearer token correctly returns **401** at `/api/auth/me`.
- Change its password; the original browser cookie still gets **200**.
- Log out and replay the saved cookie in a second client; `/users/` gets **200**.

The default signed-cookie lifetime is 14 days, and active responses renew the
cookie. A stolen cookie can remain useful despite attempted account recovery.
This does not demonstrate a way to steal the cookie in the first place.

**Fix acceptance:** centrally resolve active account and current permissions on
every protected web request; reject stale versions after password resets and
deactivation; revoke the specific session on logout, including captured-cookie
replay. Use a server-side session identifier or equivalent revocable design.
Keep emergency access explicitly bounded and separately revocable.

### A02 — Workspace isolation

Create spectator A in the default workspace and person B in another workspace.
Issue A a normal JWT through `/api/auth/token`, then request `/api/people/{B}`.
The response is **200** and includes B's invented private email address.

The relevant path is `gcrm/api/routers/api_people.py:person_detail` through
`gcrm/tools/db_people.py:get_person`. Other paths, including person-note reads,
capture-image reads, web organization lookup, and approval queries also need
a systematic ownership review. Some organization API and private-rating paths
already contain explicit workspace checks; protection is inconsistent.

`gcrm/db/connection.py` sets `app.workspace_id` when available, but the audited
schema has **no row-level security** on people, contacts, users or approvals.
Setting a PostgreSQL session variable alone does not filter a query. Migration
032 explicitly deferred constraints/RLS. Many bearer endpoints do not establish
workspace context centrally either.

**Fix acceptance:** derive identity/workspace from the active authenticated
account once, require ownership on every read and write, including related
records and background jobs; add two-workspace negative tests for every route
family. Adopt enforced RLS with a non-bypass application role if used as a
second boundary. Keep staging/reviewer databases separate in the meantime.

### A03 — CSRF validation

Using a legitimate admin browser cookie, POST `/settings/language` with a form
body, `Origin: https://staging.audit.invalid`, and `Sec-Fetch-Site: same-site`
returns **200** and changes the stored language. No CSRF token is needed.
The application contains no central token or Origin validation for web writes.
The same cookie authentication protects sensitive admin forms and approval
actions.

The cookie is `SameSite=Lax`, which helps against ordinary cross-site POSTs.
It does **not** isolate sibling subdomains. This reproduction demonstrates the
missing server validation; a real browser exploit needs a usable same-site
origin or another applicable browser delivery mechanism. CORS does not stop
simple HTML-form submissions.

**Fix acceptance:** add CSRF tokens to state-changing cookie-authenticated
forms/HTMX requests and validate Origin/Fetch Metadata as defense in depth.
Exercise both allowed requests and hostile sibling-origin submissions in a
browser. Verify login/logout flows too. Do not apply cookie-CSRF rules blindly
to the bearer-only API or MCP protocol.

### A04 — Suppression bypass at send time

Insert an organization with `do_not_contact=TRUE` and a pending draft. POST
`/approvals/{id}/approve` as an administrator. The response is **200** and the
fake `send_email` function is called with the suppressed recipient.

`gcrm/api/routers/approval.py:approve` and `_send_and_log` do not call the
existing `check_compliance` gate in `gcrm/tools/db_approvals.py`. The check at
draft creation cannot protect a draft that becomes suppressed later. Review
the held-draft sender in `gcrm/api/routers/drafts.py` for the same boundary.

**Fix acceptance:** recheck suppression, opt-out, erasure and deletion at the
last responsible send boundary; refuse safely and record the refusal. Cover
both draft queues and changes after drafting, including races with an opt-out.
Also review held-draft claim/idempotency: it currently reads, sends, then
updates, unlike the main queue's atomic claim.

### A05 — MFA is not enforced

The schema and TOTP helpers exist. Set a fictional user's `mfa_enabled=TRUE`
and store an encrypted seed. Password-only `/login` still returns **303**, and
password-only `/api/auth/token` returns **200** and issues a token.

`authenticate` does not check MFA and account lookup does not retrieve its MFA
state. There is no complete enrollment/challenge/recovery flow in the routes.
This is an implementation gap, not evidence that a live user enabled MFA.

**Fix acceptance:** complete opt-in enrollment, verify a second factor before
issuing either authenticated cookie or JWT, protect recovery and factor
changes, and test both web/mobile bypass attempts. Do not describe the current
helper functions as available two-factor protection.

### A06 — Mobile dependencies and release policy

`npm audit` against the public registry reported **34 affected packages**:
7 high, 18 moderate, 9 low, 0 critical. With `--omit=dev`, **26 remain**:
7 high, 12 moderate, 7 low. These counts include transitive parent packages;
they are not counts of independent vulnerabilities or successful attacks.

Direct advisory-bearing packages include decode-uri-component, zod and
node-forge. Expo tooling also appears under production npm dependencies, so
`--omit=dev` does not prove inclusion in the installed Android runtime.
Runtime/bundle reachability of each advisory remains to be established.

`.github/workflows/android.yml` uses `--audit-level=critical`: its dependency
gate exits successfully with these high findings. Do not blindly apply npm's
suggested major Expo downgrade. Plan compatible updates and verify the native
build, deep links and login again.

**Fix acceptance:** triage each advisory to build tooling or shipped behavior,
upgrade supported versions, document any bounded exception, and fail releases
on the chosen unacceptable severity. Keep all existing regression tests.

### A07 — Container/deployment hardening

Trivy 0.74.0 with a freshly downloaded database reported **51 HIGH
package/advisory matches, zero CRITICAL**, on the locally built application
image. **46 OS matches represent 10 distinct CVEs**; the report showed no fixed
OS versions. These are inventory matches, not demonstrated remotely reachable
exploits. Production's running image was not inspected and may differ.

Five additional Python matches came from SBOM inventory: msgpack 1.1.2,
setuptools 70.3.0 and urllib3 2.7.0. The application environment imports
urllib3 **2.8.0** and has no importable msgpack/setuptools. The system Python's
pip **26.2.2** does vendor urllib3 **2.7.0**. Thus the package manager is one
confirmed location for an affected version; do not call these five active
application-library vulnerabilities or dismiss all five without further review.

The Dockerfile runs as root, retains gcc/development packages and uv's build
cache, uses mutable image/action tags, and runs `uv sync` without `--locked`.
The production Compose configuration uses the PostgreSQL bootstrap credentials
for the application; with the stock PostgreSQL image that bootstrap role is a
superuser. No separate limited runtime DB role is configured. Actual production
role grants, host firewall and backup security were not inspected.

**Fix acceptance:** refresh/reduce the runtime image, remove compiler and build
cache/package-manager exposure where possible, run as a non-root user with
restricted capabilities, separate migration and runtime DB roles, pin the
deployable image to the tested commit/digest, and enforce lockfile builds.
Add an image vulnerability gate with reviewed exceptions where fixes do not
exist. Verify deployment configuration and restore a backup on an isolated host.

### A08 — Browser security headers

The production `/login` HTTPS response has no HSTS, CSP/frame-ancestors,
X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy or
explicit Cache-Control. Sampled protected redirects/API errors also lacked
these headers. HTTPS redirects correctly from HTTP; the language-cookie
response includes **Secure, HttpOnly, SameSite=Lax**.

**Fix acceptance:** set an appropriate central header policy; add frame
protection and `nosniff`, private/no-store caching for sensitive responses,
then introduce a tested CSP compatible with the existing inline JS/HTMX/maps.
Set HSTS after checking the intended domain/subdomain deployment. Verify the
policy on successful, redirected and failed responses.

### A09 — Authentication fails open

`gcrm/api/jwt_auth.py:_token_version_ok` returns True when the database lookup
raises. A local simulated database exception confirmed this, and
`tests/test_token_revocation.py` currently explicitly expects it. That existing
test was not edited or weakened. The code's claim that every protected action
will necessarily fail on the same database outage is not a reliable security
boundary: transient failures and later successful queries can differ.

**Fix acceptance:** on authentication-store failure, return a controlled
unavailable/unauthenticated response; do not authorize the request. Deliberately
change the behavioral requirement and its test together during remediation.
Review emergency uid-less JWT issuance and revocation separately.

### A10 — Weak configured secrets are accepted

`resolve_secret('JWT_SECRET', 'x', 'production')` returns `x`. The production
guard rejects empty values and one placeholder string but does not enforce the
documented strong-secret requirement. Cookie Secure also defaults to false
unless explicitly enabled; production currently sends Secure correctly.

**Fix acceptance:** require suitably long independent randomly generated secrets,
production HTTPS/public URL and secure-cookie settings; reject common
placeholders and weak configured values. This test does not establish that
the live secrets are weak; their values were not read.

## Additional observations and unfinished coverage

- Nineteen public probes: CRM web pages redirect to login; sampled JSON APIs
  and both MCP spellings return **401**; `.env` and `.git/HEAD` return **404**;
  reviewer people API returns **401**. These checks show authentication on
  these paths, not complete authorization coverage.
- `/openapi.json` remains public (**200**) even though Swagger/ReDoc are disabled.
  This exposes API structure, not CRM records. Decide whether publication is
  intentional; hiding it is not a substitute for fixing access controls.
- Gitleaks scanned **423 commits**, producing seven matches. Five are German
  LinkedIn translation text false positives. Two are the same Android Maps
  client key in configuration/manifest history. Client keys are extractable by
  design; verify Google API/application/package/signing-certificate restrictions
  and quotas. Those cloud settings were unavailable and the key was not used.
  No key values are included here.
- Bandit on tracked Python files: 325 alerts (131 medium, 194 low, 0 high).
  Of these, 130 flag dynamic SQL construction and one flags the JSON Markup
  wrapper. Reviewed query paths use bound values/allowlisted fragments, and
  the JSON filter escapes script-breaking characters. No SQL injection or XSS
  was confirmed. Not every alert received a full independent dataflow proof.
- URL fetching validates public HTTP destinations and redirect hops. DNS is
  checked separately from the HTTP connection, leaving a rebinding/TOCTOU
  concern; downloads are read before text truncation, leaving a resource-limit
  concern. Neither was exploited. Test controlled DNS changes and response
  size/decompression bounds on staging before closing those questions.
- Image/audio upload limits and administrator mutation checks exist; the
  existing upload/security tests pass. No large-body or sustained denial-of-
  service tests were run on production. A reverse-proxy body limit and parser
  spooling limits still need deployment-level verification.
- Remote MCP validates hashed live tokens, user activity and rate limits before
  tools; its field tools bind workspace and audit context. Only its public 401
  behavior was tested remotely. Token revocation, expiry policy and ownership
  should also receive authenticated staging tests.
- SMTP/IMAP require STARTTLS and verify remote certificates; localhost bridges
  have an explicit certificate-verification exception. Mail approvals preserve
  a human checkpoint, but A04 needs correction. No mail service was contacted.
- Agent inputs include untrusted websites, documents and inbox text. Model
  output must remain untrusted; do not allow a model to change permissions,
  suppression or approval requirements. No paid model calls or prompt-injection
  campaign was run. Production/hosted agent runtime was not inspected.
- Account data export, self-service email change and two-step account deletion
  are incomplete; `/delete-data` is a manual request page. This is a product/
  house-standard gap, not a legal-compliance determination.
- Production server patch state, TLS protocol/cipher matrix, SSH/firewall,
  Cloud/Play-console permissions, production secrets, encrypted backup storage,
  retention scheduling, restore testing, and APK/emulator instrumentation remain
  outside this session's verified scope. No claim of their safety is made.

## Verification results and limitations

| Check | Result |
| --- | --- |
| Main Python unit suite | 1,561 passed, 1 skipped, 209 deselected |
| Real PostgreSQL integration + workflow tests | 208 passed |
| Six agent suites, each in its own process | 72 passed |
| Mobile full suite | **389 passed, 1 failed**; see below |
| Installed Python environment pip-audit | 120 entries, no known vulnerabilities reported |
| Frozen release dependency export pip-audit | 88 entries, no known vulnerabilities reported |
| Local image build + migrations | Built; 81 migrations applied to empty staging DB |
| Staging browser | Admin sign-in and fictional organization verified |
| Staging egress/credential isolation | External socket failed; provider/mail credentials empty |

The failing mobile test is
`engcrm-mobile/__tests__/app/organization-detail.test.tsx:118`,
`organization detail — opportunity analysis › lets a spectator set and clear a private priority`.
It timed out waiting for `1 Best`; only an ActivityIndicator rendered. A focused
rerun of that unchanged suite passed all **34 tests**, suggesting timing or
suite-interaction flakiness; the original full-suite failure remains recorded.
No test was deleted, skipped, or weakened.

The initial all-agent-in-one-process command had an import-name collision
between the research and scout `tests.test_graph` modules. Running each agent
in its own process, as CI does, passed. Initial sandboxed process/network
attempts stalled; definitive results above came from completed runs with local
database access. The first migration attempt exposed a legacy hard-coded
`artcrm_admindude` grant; a role was added only in the disposable audit DB.

## Remediation order

1. Revoke browser sessions correctly, add central CSRF validation, and enforce
   suppression at all send boundaries. Add reproductions as regression tests
   before each fix. Resolve the mobile test failure without weakening it.
2. Finish workspace ownership enforcement and the MFA login flow. Continue
   isolated reviewer/staging databases throughout this work.
3. Triage/update dependencies and image findings, tighten release policy,
   reduce runtime/DB privileges and add browser headers.
4. Run authenticated staging browser/API/MCP tests, controlled URL-fetch and
   upload/prompt-injection tests, then verify production configuration and
   limited read-only behavior again after an explicitly approved deployment.

## References

- [OWASP session management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP CSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP SSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)
- [Zod advisory](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5)
- [decode-uri-component advisory](https://github.com/advisories/GHSA-vcc3-ghjq-m6fr)
- [Google Maps key restrictions](https://developers.google.com/maps/api-security-best-practices)

Local evidence is saved separately from the repository under the current chat's
visualizations directory. Raw vulnerability scans are evidence, not additional
confirmed findings. This report and staging setup are committed locally only;
publishing the findings or deploying fixes requires a later push instruction.
