# Local security staging

Open <http://127.0.0.1:8086/login>. This is a separate, disposable CRM, not the
production website and not the Google Play reviewer deployment.

Two fictional accounts were created for the 5 November 2026 audit:

| Email | Role |
| --- | --- |
| audit-admin@example.test | Administrator |
| audit-viewer@example.test | Spectator |

Their local-only password is `Local-Audit-Only-2026!`. This deliberately public
test password must never be used on a hosted or production account. The
browser was left signed in as the fictional administrator. The only seeded
organization is Fictional Example Factory in Test Town.

## Isolation

- Standalone `docker-compose.staging.yml`; never merge it with the production
  Compose file. Project, network, database and secrets are separate.
- Only the proxy publishes a port, on **127.0.0.1:8086**. The app and database
  join an internal network. A fixed-upstream proxy bridges browser requests to
  the app; the app has no external network route. This was tested with an
  outbound socket request, which failed.
- No production `.env` is loaded. Provider/mail credentials are explicitly empty,
  dotenv loading is disabled, email is disabled, and no production directories,
  backups or Docker socket are mounted. Paid AI/research and mail delivery will
  therefore not work here; use test doubles/captured mail when testing them.
- Separate signing secrets live in `/tmp/engcrm-staging.env`, mode 0600. This
  file contains no production values. `/tmp` may be cleared on reboot.
- HTTP and non-Secure cookies are deliberate local exceptions. This setup is
  not ready to expose on a public interface. Hosted staging needs HTTPS and
  Secure cookies, controlled access, independent credentials and a reviewed
  external-service policy.
- The database and card-image storage use **tmpfs**. Container recreation or a
  host reboot can lose the fictional data. Nothing here is a durable backup.
- The application image preserves the production app's behavior, including the
  audit findings. It is a testing environment, not a hardened release.

## Start, inspect and stop

Run from the repository root, always specifying the staging file and secrets:

```sh
docker compose --env-file /tmp/engcrm-staging.env -f docker-compose.staging.yml up -d
docker compose --env-file /tmp/engcrm-staging.env -f docker-compose.staging.yml ps
docker compose --env-file /tmp/engcrm-staging.env -f docker-compose.staging.yml logs --tail 50 app proxy
```

Stop it when finished (tmpfs database contents are disposable):

```sh
docker compose --env-file /tmp/engcrm-staging.env -f docker-compose.staging.yml stop
```

## Rebuild from an empty staging database

If the secrets file is absent, generate two independent secrets; do not copy
production values. The following command refuses to overwrite an existing file:

```sh
umask 077
(set -C; printf 'STAGING_JWT_SECRET=%s\nSTAGING_SESSION_SECRET=%s\n' "$(openssl rand -hex 32)" "$(openssl rand -hex 32)" > /tmp/engcrm-staging.env)
```

Build, initialize the schema, then start the app/proxy. This reuses only the
staging services. All 81 current migrations ran on the audit's fresh database.

```sh
docker compose --env-file /tmp/engcrm-staging.env -f docker-compose.staging.yml build app
docker compose --env-file /tmp/engcrm-staging.env -f docker-compose.staging.yml up -d db
docker compose --env-file /tmp/engcrm-staging.env -f docker-compose.staging.yml run --rm app /app/.venv/bin/python scripts/migrate.py
docker compose --env-file /tmp/engcrm-staging.env -f docker-compose.staging.yml up -d app proxy
```

Create test accounts only when they are absent; the existing user-management
command will report duplicate accounts rather than silently replacing them:

```sh
docker compose --env-file /tmp/engcrm-staging.env -f docker-compose.staging.yml exec app /app/.venv/bin/python -m scripts.manage_users add --email audit-admin@example.test --role admin --password 'Local-Audit-Only-2026!'
docker compose --env-file /tmp/engcrm-staging.env -f docker-compose.staging.yml exec app /app/.venv/bin/python -m scripts.manage_users add --email audit-viewer@example.test --role spectator --password 'Local-Audit-Only-2026!'
```

Add invented organizations through the staging UI. Do not import a production
database, mailbox, document, push token, Maps key, or MCP token. For browser
tests of sibling-origin CSRF, keep both origins inside a controlled local
environment and do not expose vulnerable staging beside production.

The source build now has a `.dockerignore` excluding local environments,
credentials, backups and dependency trees. The newly built local image used
for the audit was `sha256:f7c254cd5160d0b783f850f98096605994b4bd971566fb4425b6c875520dda43`.
Production's running image was not inspected or changed.
