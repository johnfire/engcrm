"""Mobile push-token registration."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from gcrm.api.jwt_auth import require_jwt_payload
from gcrm.db.connection import db
from gcrm.tools.db_audit import log_audit

router = APIRouter(prefix="/api/push", tags=["mobile-push"])


class PushTokenRequest(BaseModel):
    token: str


@router.post("/register", status_code=204)
def register_push_token(body: PushTokenRequest, _payload: dict = Depends(require_jwt_payload)) -> None:
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO push_tokens (token, updated_at)
            VALUES (%s, NOW())
            ON CONFLICT (token) DO UPDATE SET updated_at = NOW()
            """,
            [body.token],
        )
    log_audit(None, None, "push_token.registered", "push_token", "registered")
