# Security fixes plan — from the 26 Nov 2026 audit

Source: the read-only audit run on 2026-11-26 (chat report; four area reviews plus a core
review). Nothing in the audit changed code. This plan covers the five priority items and
what is deliberately deferred. Every file named below was read before it was written up.

Rules for whoever builds this: no branch; tests first and watch them fail for the right
reason; never delete, skip or weaken a failing test (one existing test changes its
*expectation* on purpose in fix 3 — it is called out, show Chris); one commit per fix;
run `uv run ruff check .` and the full unit suite before each commit; gate the commit on
pytest's own exit code, not on a pipe; ask Chris before pushing.

## Step 0 — operator checks (Chris, not code; do these first, they decide how urgent the rest is)

Reading the production host or its `.env` needs Chris's yes each time.

1. **Open Brain key and JWT** in public git history (commits 03f20a0 and b4106be). Confirm
   they were revoked in Open Brain/Supabase; if not, rotate and update the deployed `.env`.
   Then note the rotation date in `.gitleaksignore`'s comment.
2. **Google Maps key** (`engcrm-mobile/app.json:17`): in Google Cloud, restrict to the Android
   package + signing SHA-1, Maps SDK only, with a quota cap; use a different key from the
   server-side `GOOGLE_MAPS_API_KEY`.
3. **`ADMIN_PASSWORD`** in `/opt/engcrm/.env`: if user accounts exist, unset it. It bypasses
   MFA and its mobile tokens cannot be revoked (`gcrm/api/auth.py:71-75`).
4. **Apache**: (a) how it sets `X-Forwarded-For` (append vs replace) — decides fix 3b; (b) add
   `LimitRequestBody 27262976` (26 MiB) to the vhost — the outer wall for fix 3a.
5. **GitHub**: main requires a pull request or at least blocks force-push; consider a deploy
   Environment with a required reviewer.

## Fix 1 — inbox parser crash (M3) · files: `gcrm/tools/email.py`, new `tests/test_email_parse.py`

**Problem.** `_parse_message` (email.py:133) imports `re` and `html` inside the
`if not body.strip() and html_body:` branch (lines 164-166) but uses `re.search` at line 185
for every message. Python makes `re` local to the whole function, so a plain-text mail whose
From domain is in `Authentication-Results` raises `UnboundLocalError`. Reproduced on 26 Nov.

**Tests first** (`tests/test_email_parse.py`; build messages with `email.message.EmailMessage`,
parse with `email.message_from_bytes`, call `gcrm.tools.email._parse_message(parsed)`):
1. Plain-text body + `Authentication-Results: mx; spf=pass smtp.mailfrom=b.de` + `From: a@b.de`
   → returns a dict, `authenticated is True`. (Fails today with UnboundLocalError.)
2. Same but the header names a different domain → `authenticated is False`.
3. Same but `spf=fail` → `authenticated is False`.
4. HTML-only body → `body` is tag-stripped text (covers the branch that does import).
5. No `Authentication-Results` header → `authenticated is False`, no exception.

**Change.** Add `import html as html_mod` and `import re` to the module imports (top of
`email.py`, with `import email as email_lib`), delete the two inner imports at lines 165-166.
Nothing else.

**Verify.** `uv run pytest tests/test_email_parse.py tests/test_email_send.py -q`, then full suite.

**Note for Chris, not part of this fix.** Once this works, the "authenticated" flag starts
enabling automatic opt-out. That flag trusts any `Authentication-Results` header
(`email.py:140-186` has no authserv-id check), so before relying on it confirm that Postfix
stamps or strips that header. Opt-outs are also recognised only by the LLM classifier;
a deterministic keyword fallback ("unsubscribe", "abmelden") is a design item, see Deferred.

## Fix 2 — dossier GET must not generate (M2) · files: `gcrm/research/dossier.py`, `gcrm/api/routers/api_research.py`, test

**Problem.** `GET /api/research/dossier/{contact_id}` (api_research.py:56-63) is guarded by
`require_jwt` (any role) and calls `get_or_create_dossier`, which on a cache miss crawls,
calls an LLM and inserts a row (dossier.py:489-511). Its docstring promises 404.

**Tests first** (new `tests/test_api_dossier_get.py`; patch targets are the names as imported
in the router module; use the `Authorization: Bearer {create_token('spectator')}` header
pattern from `tests/test_deals_routes.py`):
1. GET with no stored dossier → 404 and `get_or_create_dossier` / `_generate_dossier` never
   called (patch them with `assert_not_called`). Fails today.
2. GET with a stored dossier → 200 and the dossier returned.
3. POST by a spectator → 403 (existing behaviour, pin it).

**Change.**
- `dossier.py`: add next to `_get_active_dossier` a public
  `def get_existing_dossier(contact_id: int) -> dict | None: return _get_active_dossier(contact_id)`.
- `api_research.py`: import it, and in `get_dossier` replace
  `dossier = get_or_create_dossier(contact_id)` with `dossier = get_existing_dossier(contact_id)`.
  Leave `generate_dossier` (the POST, admin-only) as it is.
- Check the web route `gcrm/api/routers/research.py:70-77` is admin-only (the audit says it
  is); do not change it.

**Verify.** the new tests, `tests/test_research_dossier.py`, full suite.

## Fix 3 — request size cap and the forwarded-address rule (M1, M7) · files: new `gcrm/api/body_limit.py`, `gcrm/api/main.py`, `gcrm/config.py`, `gcrm/api/rate_limit.py`, tests

### 3a. Cap bodies before anything reads them

**Problem.** `accepts_browser_write` (csrf.py:41-43) runs `await request.body()` then
`request.form()` for any form write that has a matching `Origin` and no CSRF header, before
authentication; nothing limits the size. The 25 MiB `MAX_UPLOAD_BYTES` is only checked after
the framework has already buffered the body.

**Design.** A pure ASGI middleware, so the cap holds for chunked bodies too:
- Reads `content-length`; if it exceeds the limit for this request, answer 413 at once.
- Otherwise wraps `receive`, counts bytes, and when the running total passes the limit
  sends 413 (only if the response has not started) and stops reading.
- Limits: multipart/form-data → `MAX_UPLOAD_BYTES + 1 MiB` (the upload routes read
  `MAX_UPLOAD_BYTES + 1` themselves and keep their friendly errors); everything else →
  `MAX_BODY_BYTES` (new config, default 4 MiB). **Before fixing the 4 MiB default, measure
  the largest realistic sync push** — `gcrm/sync/contracts.py` allows 100 mutations of up to 30
  fields each; build one near that size in a test and make sure it passes. Raise the default
  if it does not.
- Applies to every HTTP request except GET/HEAD/OPTIONS bodies of zero length.

**Tests first** (`tests/test_body_limit.py`, TestClient against `main.app`):
1. `POST /login` with `Content-Length` over the form limit → 413, and the route never runs.
2. Same without a Content-Length (generator body) that streams past the limit → 413.
3. A multipart upload under `MAX_UPLOAD_BYTES` still reaches its route (use an existing small
   upload route test as the model).
4. A normal login form post is unaffected.
5. A realistic maximal sync push JSON is accepted.

**Change.**
- `config.py`: `MAX_BODY_BYTES: int = int(os.getenv("MAX_BODY_BYTES", str(4 * 1024 * 1024)))` next to `MAX_UPLOAD_BYTES`.
- `body_limit.py`: the middleware class described above, JSON 413 body
  `{"detail": "Request too large"}`.
- `main.py`: `app.add_middleware(BodyLimitMiddleware)` **above** the existing
  `app.add_middleware(BrowserHeadersMiddleware)` line, so BrowserHeaders stays outermost and
  the 413 still carries the security headers (Starlette makes the last-added middleware the
  outermost).

### 3b. Trust the address Apache actually saw, not the first one in the header

**Problem.** `client_key` (rate_limit.py:311-319) returns `forwarded.split(",")[0]`. Apache
appends the connecting address to any `X-Forwarded-For` the client sent, so the leftmost
value is client-controlled: rotating it defeats the per-IP login limit.

**Change.** Use the last entry: `forwarded.split(",")[-1].strip()`, still only when the direct
peer is in `TRUSTED_PROXY_IPS`. With one trusted proxy hop the last entry is what that proxy
observed. If Apache is configured to *replace* the header (step 0.4a) the first and last
entries are the same, so this is safe either way.

**Tests.** `tests/test_rate_limit.py` line 52-53 currently asserts that
`"203.0.113.9, 127.0.0.1"` from peer `127.0.0.1` yields `203.0.113.9` — it encodes the
leftmost rule, which is the thing being fixed. **Change its expectation deliberately and tell
Chris**: new fixture `b"203.0.113.9, 198.51.100.7"` (spoofed value first, real client last)
expects `198.51.100.7`; add a second test that a client sending `X-Forwarded-For: 1.2.3.4`
through the proxy cannot choose its own bucket (two requests with different spoofed leftmost
values but the same last value share one bucket). Keep the untouched tests at lines 46-47
and 57.

**Verify.** `uv run pytest tests/test_body_limit.py tests/test_rate_limit.py tests/test_csrf.py -q`, full suite.

## Fix 4 — mobile sign-out and 401 cleanup (M4) · files in `engcrm-mobile/`

**Problem (verified 26 Nov).** The header `LogoutButton` (`app/(drawer)/_layout.tsx:19-22`)
and the 401 handler (`services/api.ts:44-49`) only call `clearToken()`. Only the Settings
logout (`app/(drawer)/settings.tsx:41-45`) stops field mode first. The location queue
(`field_points_v1`), the card/document photo queue (`card_upload_queue_v1` and
`Paths.document/card-queue/*.jpg`) and drafts (`meeting_draft_v1:*`) are global, so the next
account that signs in uploads or sees the previous account's data.

**Decision for Chris first.** Recommended rule: *queued data survives sign-out and sign-in of
the same account, and is purged when a different account signs in.* The alternative (purge on
every sign-out) can lose a photo captured offline, which the card-queue header comment says
must never happen.

**Tests first** (jest; models: `__tests__/services/fieldMode.test.ts`,
`cardQueue.test.ts`, `auth.test.ts`, `drafts.test.ts`):
1. New `__tests__/services/session-end.test.ts`: `endSession()` calls `stopFieldMode` before
   `clearToken` (stopFieldMode flushes queued points while the token still exists), and still
   clears the token if `stopFieldMode` throws.
2. `purgeForNewAccount()` removes `field_points_v1`, `card_upload_queue_v1` (and deletes the
   `card-queue` directory) and every `meeting_draft_v1:*` key.
3. `api.test.ts`: a 401 response triggers `endSession`-style cleanup (stop field mode +
   clear token) once, not per request.
4. Sign-in as the same account as last time does not purge; a different account does.

**Change.**
- New `services/session-end.ts` exporting `endSession()` (stopFieldMode with errors swallowed,
  then `clearToken`) and `purgeForNewAccount()`.
- `services/fieldMode.ts`, `services/cardQueue.ts`, `services/drafts.ts`: export a small
  `clearAll()` each (field: remove `QUEUE_KEY` and `STARTED_KEY`; cards: delete the
  `queueDir()` directory and remove `QUEUE_KEY`, through `mutateQueue` so it cannot race a
  flush; drafts: `AsyncStorage.getAllKeys()` filtered by `PREFIX`, then `multiRemove`).
- `_layout.tsx` `LogoutButton.finishLogout` and the 401 branch in `api.ts`: call `endSession()`
  instead of `clearToken()`. Settings `finishLogout` too, so there is one path.
  Note `api.ts` imports from `fieldMode.ts`, which imports `client` from `api.ts`: avoid a
  circular import by having `session-end.ts` import both and `api.ts` import only
  `session-end` lazily (`await import("./session-end")` inside the 401 branch) — check the
  jest mock set-up before choosing.
- `app/login.tsx` (read it before editing): after a successful login, compare the email with
  a `engcrm_last_account` SecureStore value; if different, call `purgeForNewAccount()`;
  then store the new value. Store it lower-cased.

**Verify.** `cd engcrm-mobile && npx jest`, `npx tsc --noEmit`, lint, as the Android workflow does.
Not verifiable here: real device behaviour; needs a phone check by Chris.

## Fix 5 — release pipeline and expiring exception (M5) · files: `.github/workflows/*.yml`, `scripts/security/mobile-dependency-policy.json`

1. **Pin actions to commit SHAs.** For each `uses:` line in `backend.yml`, `security.yml`,
   `android.yml`, `android-security.yml`, resolve the tag to a commit:
   `gh api repos/OWNER/REPO/commits/TAG --jq .sha` (this dereferences annotated tags), and
   write `uses: OWNER/REPO@<40-char sha> # TAG`. Dependabot keeps SHA pins current and
   understands the trailing comment. Do the two that hold deploy secrets first:
   `appleboy/ssh-action` (backend.yml:133) and `r0adkll/upload-google-play` (android.yml).
2. **Pin the VPS host key.** Chris runs `ssh-keyscan -t ed25519 <host> | ssh-keygen -lf -`
   (reads the server's public key only) and adds the `SHA256:...` value as a repository
   secret `VPS_HOST_FINGERPRINT`; add `fingerprint: ${{ secrets.VPS_HOST_FINGERPRINT }}`
   under `with:` of the deploy step. Check the action's README for the exact input name at the
   pinned version before editing — the audit's claim that it skips host-key checking without
   this input came from memory and is unverified.
3. **zod exception expires 2026-12-05.** Read `scripts/security/mobile-dependency-policy.json`
   and `docs/mobile-dependency-security.md`; either renew with a new date and a re-checked
   reason, or take the Expo upgrade. Do this before the 5th or CI goes red.
4. Push through a pull request run or `workflow_dispatch` once and confirm the deploy still
   works end to end before relying on it; a wrong fingerprint blocks deploys.

## Do not touch in this batch

The row-level-security migrations and `gcrm/db/connection.py`; the CSRF check logic (only its
callers' body size changes); `outreach_guard.py`; the sync protocol; any migration file;
`docker-compose.yml` hardening (separate item); the income calculator.

## Deferred — needs a design decision or a separate change

| Item | Why deferred |
| --- | --- |
| Real people's data in the public repo (`scripts/data/bavaria_directory.py`, `art-marketing.xlsx`) | Chris decides where the data lives; history purge is a separate, risky step |
| Suppression for people and addresses; opt-out line in the curiosity email (M8) | Compliance design; touches the send guard |
| Deterministic opt-out keywords; authserv-id check | After fix 1; needs the Postfix header behaviour |
| Encrypted or link-only backups, off-host DB dumps (M9) | Needs a key/passphrase design and a destination |
| Login timing, >72-byte password handling, admin-set password length, flash password in cookie | Small; batch as one "account hygiene" change |
| SSRF DNS pinning, `100.64.0.0/10`, response size caps, Crawl4AI guard | One change in `gcrm/tools/search.py`; plan separately |
| MCP tokens ignoring role; unthrottled invalid tokens | Small; separate |
| Android backup rules, token revocation on logout, `SYSTEM_ALERT_WINDOW`, deep-link id validation | Mobile hardening batch |
| `.dockerignore` for `gcrm/ui/static/_layout_audit` | One line; can go with fix 5 |
| CSV formula neutraliser for sign+digit payloads | Tiny; `backup_export.py:166-170` |

## Order

Step 0 now (in parallel with code). Then 1 → 2 → 3 → 4 → 5, one commit each. Fix 1 is minutes
and restores the opt-out path; fix 3 needs the Apache answer only for how it is described, not
to build.
