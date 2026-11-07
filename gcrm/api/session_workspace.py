"""The workspace of the signed-in session (the shared admin login works in the default one)."""
from fastapi import Request

from gcrm.db.connection import db


def session_workspace_id(request: Request) -> int:
    workspace_id = request.session.get("workspace_id")
    if workspace_id is not None:
        return workspace_id
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        return cur.fetchone()["id"]
