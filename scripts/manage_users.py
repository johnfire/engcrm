"""
Manage EngCRM web-UI user accounts (email + bcrypt password).

Usage:
    uv run python scripts/manage_users.py add --email a@b.com [--name "A B"] [--role admin|spectator] [--password PW]
    uv run python scripts/manage_users.py passwd  --email a@b.com [--password PW]
    uv run python scripts/manage_users.py disable --email a@b.com
    uv run python scripts/manage_users.py enable  --email a@b.com
    uv run python scripts/manage_users.py list

If --password is omitted, a strong one is generated and printed once — to
stderr, so redirecting stdout to a file doesn't capture the secret.
Connects to the database via DATABASE_URL (same as scripts/migrate.py).
"""
import argparse
import secrets
import string
import sys

from gcrm.api.security import hash_password
from gcrm.tools.db import (
    create_user,
    list_users,
    set_user_active,
    set_user_password,
)


def _generate_password(length: int = 18) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _show_secret(label: str, password: str) -> None:
    """Print a generated password to stderr, not stdout.

    It still lands on the admin's terminal, which is the whole point of the
    tool — but `manage_users.py add ... > users.log` now keeps the secret out
    of the file. CodeQL flags this as clear-text logging either way; the two
    alerts are dismissed as false positives, since a password you cannot read
    once is a password you cannot hand over.
    """
    print(f"{label}: {password}", file=sys.stderr)


def cmd_add(args):
    password = args.password or _generate_password()
    user_id = create_user(args.email, hash_password(password), role=args.role, name=args.name)
    print(f"Created user #{user_id}: {args.email.lower()} (role={args.role})")
    if not args.password:
        _show_secret("Generated password", password)


def cmd_passwd(args):
    password = args.password or _generate_password()
    if not set_user_password(args.email, hash_password(password)):
        sys.exit(f"No such user: {args.email}")
    print(f"Password updated for {args.email.lower()}")
    if not args.password:
        _show_secret("New password", password)


def cmd_disable(args):
    if not set_user_active(args.email, False):
        sys.exit(f"No such user: {args.email}")
    print(f"Disabled {args.email.lower()}")


def cmd_enable(args):
    if not set_user_active(args.email, True):
        sys.exit(f"No such user: {args.email}")
    print(f"Enabled {args.email.lower()}")


def cmd_list(args):
    users = list_users()
    if not users:
        print("(no users)")
        return
    for u in users:
        state = "active" if u["is_active"] else "DISABLED"
        last = u["last_login_at"] or "never"
        print(f"#{u['id']:<3} {u['email']:<32} {u['role']:<9} {state:<8} last_login={last}")


def main():
    parser = argparse.ArgumentParser(description="Manage EngCRM user accounts.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="create a user")
    p_add.add_argument("--email", required=True)
    p_add.add_argument("--name", default="")
    p_add.add_argument("--role", default="admin", choices=["admin", "spectator"])
    p_add.add_argument("--password", default="", help="omit to auto-generate")
    p_add.set_defaults(func=cmd_add)

    p_pw = sub.add_parser("passwd", help="reset a user's password")
    p_pw.add_argument("--email", required=True)
    p_pw.add_argument("--password", default="", help="omit to auto-generate")
    p_pw.set_defaults(func=cmd_passwd)

    p_dis = sub.add_parser("disable", help="disable (lock out) a user")
    p_dis.add_argument("--email", required=True)
    p_dis.set_defaults(func=cmd_disable)

    p_en = sub.add_parser("enable", help="re-enable a user")
    p_en.add_argument("--email", required=True)
    p_en.set_defaults(func=cmd_enable)

    p_ls = sub.add_parser("list", help="list users")
    p_ls.set_defaults(func=cmd_list)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
