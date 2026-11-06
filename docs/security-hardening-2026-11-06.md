# Remaining security hardening — 6 November 2026

This batch addresses A07, A08 and A10 in **local source**. It is not deployed.
Production verification still follows an explicitly authorized push/deployment.

## A08: browser response protections

Central response middleware adds a nonce-based Content Security Policy, frame
protection, content-type protection, referrer and permissions policies, and
private/no-store caching outside static assets. HTTPS deployments add one year
of HSTS for this hostname, without assuming control of every subdomain.

Scripts and style blocks carry response nonces. HTMX uses a locally served,
licensed copy; its expression evaluation is disabled. Declarative form handlers
retain confirmations and repeat-submit protection. Map popups construct text
nodes rather than interpreting external labels as HTML. Partial responses use
the originating page's nonce so existing HTMX interactions can continue.

## A10: fail-closed production configuration

Production and staging reject short, obviously patterned, and placeholder
signing secrets. JWT and browser-session signing keys must differ. Public
deployments require an HTTPS public URL and Secure cookies; staging's HTTP
exception is limited to loopback origins. Existing account-encryption material
is retained: never silently regenerate it or change it when restoring MFA data.

## A07: isolated runtime and release image

The application and locked dependencies are built on an immutable Python 3.13
Alpine base. The running image omits the compiler, uv, pip/bootstrap archives,
and the apk executable. It runs as UID/GID 10001 with a read-only filesystem,
no Linux capabilities, no privilege escalation, bounded process/memory use,
and only uploads, temporary files, and its private credential mount available.

The final complete minimal-base image scan reported zero vulnerabilities.
A release gate rejects high, critical, and unknown
severity findings, incomplete OS scans, and end-of-life OS results. There is no
blanket exception for unfixed findings. CI retains the full scan report and
publishes the same local image that passed the gate, then deploys its digest.

Migration 081 creates a limited `engcrm_app` login distinct from the database
owner. Authentication tables are available before identity is established;
CRM reads/writes require entering `engcrm_workspace` with the active workspace.
The app cannot run migrations, disable row security, or become the operator.
Runtime provisioning refuses excessive role flags/memberships and mismatched
saved database targets. A configured runtime file cannot fall back to the owner
URL and must contain a private, appropriately sized application login.

Compose separates three responsibilities:

- `initialize`: offline root job that prepares upload ownership and a private
  runtime settings file, excluding database-owner credentials. It restricts the
  host backup folder to root-owned mode 0700 so permissive dump-file defaults
  do not expose contact data to other host users.
- `migrate`: one-shot restricted container using operator credentials only
  while applying migrations and provisioning the application login.
- `app`: receives sanitized settings and a read-only private DSN volume, with
  no operator URL/password in its environment or mounted files.

The deployment preflight validates settings before writing the new runtime
environment. The migration/init services are explicit tools, not continuously
running services. The workflow checks command failures and waits for health.
Compose is extracted from the tested release image rather than an older VPS
checkout. Its required image reference prevents accidental use of `latest`.

For later manual Compose inspection/startup, use both environment files:

```sh
sudo docker compose --env-file .env --env-file .runtime/image.env ps
```

Inside the app container, trusted maintenance scripts must explicitly enter
the selected/default workspace. For example:

```sh
docker exec -i engcrm-app python -m scripts.workspace_command scripts/maps/pin_queue.py --import
```

Use `GCRM_ACTOR` and `GCRM_ACTOR_TYPE` to identify an agent running maintenance;
the wrapper supplies an audit correlation ID. Local source-based operator
commands can still use their explicit owner connection outside the web runtime.

## Verification

- Full server unit suite: **1,711 passed, one pre-existing skipped test**.
- Real PostgreSQL integration/workflow suite: **313 passed**. An initial attempt
  could not reach the stopped disposable database; the unchanged suite passed
  after restart. No failing test was hidden, removed or weakened.
- All six agent packages passed **72 tests**, run separately to avoid their shared
  test-module names. Browser-interaction tests passed four checks; eight deliberate
  mutations of the startup, credential and image-gate rules were detected;
  four browser-script mutations were detected too.
- Final Trivy image report: **zero reported vulnerabilities**, with a fresh DB.
  This is scanner evidence, not proof of absence of every security defect.
- Fresh local hardened stack applied 86 migration files. A second initialization
  and migration/provisioning run applied zero changes; the existing running app
  continued authenticating and reading scoped CRM data.
- Actual container inspection confirmed UID/GID 10001, read-only root filesystem,
  no capabilities/privilege escalation, resource bounds, a private read-only DSN,
  and no database-owner credentials in the app environment or mounted files.
  Native app bindings, TLS trust roots and Europe/Berlin timezone support passed.
- Real HTTP/browser flows passed: sign-in, API writes, forged-request rejection,
  offline totals and stage save/reload. Browser password visibility controls worked
  under CSP, with no recorded CSP errors.
- The backup container produced a real dump of fictional data. It was restored
  into a second independent PostgreSQL cluster with bootstrapped limited roles.
  Contact data, the saved offline count, audit correlation, limited-role access
  and the complete original migration history matched the backup state. The
  history contains 88 records because two legacy bootstrap rows are additional
  to the 86 files; an initial fixed-count assertion was corrected to compare
  the full original/restored history instead.
- Private backup-directory verification confirmed root ownership/mode 0700 in
  the Docker host namespace and denied read/traversal to an unrelated UID 10001.
  The backup job still wrote successfully, and its latest dump was restored to
  another fresh database in the independent cluster, including the later browser
  update and audit history. Host-side namespace mappings were not mistaken for
  the container's real ownership.

## Restore essentials and remaining boundary

Keep an independently protected copy of `.env`/account-encryption material as
well as database backups. A database dump does not preserve the cluster's roles
or their memberships. On a new cluster, create `engcrm_workspace` and `engcrm_app`
with the flags from migrations 079/081, grant the workspace role to the operator
and app role, restore database objects/data/ACLs, then provision a fresh private
runtime DSN for the restored target. Do not reuse a saved DSN for a different
host/database. Verify application login and scoped access before switching traffic.

Production host patching, firewall/TLS configuration, cloud key restrictions,
and encrypted off-host backup storage were not changed or verified by these local
checks. Additional unconfirmed URL-fetch/upload questions and account lifecycle
product gaps remain listed in the original audit; this batch does not close them.

References: [Docker tool profiles](https://docs.docker.com/compose/how-tos/profiles/),
[Trivy filtering](https://trivy.dev/docs/latest/configuration/filtering/).
