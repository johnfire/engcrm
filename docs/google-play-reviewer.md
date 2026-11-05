# Google Play reviewer environment

The reviewer account uses a separate Compose project and PostgreSQL database at
`/opt/engcrm-review` on the VPS. Apache routes `/reviewer/api/` to its
loopback-only service; ordinary traffic continues to production. JWT and
session secrets are independent. Email and external-provider credentials are
not configured. The disposable reviewer database is not in production backups.

The Android app routes the exact login `tester367google@example.test` to this
instance and stores the server choice with its token. Other logins use
production. A build including this routing must reach Google Play before these
credentials work in the Play-distributed app. The reviewer is an administrator
of the isolated instance: never add real customer or personal data to it. The
reserved `.test` address is not a working mailbox, so password recovery by email
is unavailable. Provide the reviewer with the generated password separately.

After review, disable the reviewer account with `scripts/manage_users.py` in
the reviewer app container and remove the public route if no longer needed.
Do not remove the database or files without Chris's permission. The test
environment tracks the deployed image only when deliberately updated; validate
it again as the production app changes.

`/delete-data` describes an email-based deletion request. This is a manual
process, not automatic deletion. Verify requests and confirm ownership before
touching shared CRM data. Explain any legal/security retention and the backup
schedule in the response. The page is not live until the backend is deployed.
