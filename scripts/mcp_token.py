"""
Manage tokens for the remote MCP connector (Claude from anywhere, /mcp).

Usage:
    uv run python scripts/mcp_token.py create --email a@b.com [--label "Claude on my phone"]
    uv run python scripts/mcp_token.py list
    uv run python scripts/mcp_token.py revoke --id 3

`create` prints the token once, to stderr (so redirecting stdout does not capture the
secret). Paste it into the claude.ai connector as the request header
`Authorization: Bearer <token>`; it cannot be shown again, only replaced. Connects to the
database via DATABASE_URL (same as scripts/migrate.py).
"""
import argparse
import sys

from gcrm.mcp.tokens import create_token, list_tokens, revoke_token
from gcrm.tools.db_users import get_user_by_email


def cmd_create(args) -> int:
    user = get_user_by_email(args.email)
    if not user or not user.get("is_active"):
        print(f"No active user {args.email}", file=sys.stderr)
        return 1
    token = create_token(user["id"], args.label)
    print(f"Token for {user['email']} (shown once): {token}", file=sys.stderr)
    print("Created. Header for the connector: Authorization: Bearer <the token above>")
    return 0


def cmd_list(_args) -> int:
    tokens = list_tokens()
    if not tokens:
        print("(no tokens)")
    for t in tokens:
        state = "revoked" if t["revoked_at"] else "live"
        print(f"#{t['id']:<3} {t['email']:<32} {state:<8} {t['label'] or '—':<24} "
              f"last_used={t['last_used_at'] or 'never'}")
    return 0


def cmd_revoke(args) -> int:
    if not revoke_token(args.id):
        print(f"No live token #{args.id}", file=sys.stderr)
        return 1
    print(f"Revoked token #{args.id}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage remote MCP connector tokens.")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--email", required=True)
    create.add_argument("--label", default="")
    create.set_defaults(func=cmd_create)
    sub.add_parser("list").set_defaults(func=cmd_list)
    revoke = sub.add_parser("revoke")
    revoke.add_argument("--id", type=int, required=True)
    revoke.set_defaults(func=cmd_revoke)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
