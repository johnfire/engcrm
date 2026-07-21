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
def register_push_token(body: PushTokenRequest, payload: dict = Depends(require_jwt_payload)) -> None:
    # uid is absent for the transitional shared break-glass admin — its
    # tokens stay untargeted (user_id NULL) and only reachable via
    # send_push_to_all, same as before this endpoint tracked accounts.
    user_id = payload.get("uid")
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO push_tokens (token, user_id, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (token) DO UPDATE SET user_id = EXCLUDED.user_id, updated_at = NOW()
            """,
            [body.token, user_id],
        )
    log_audit(None, None, "push_token.registered", "push_token", "registered")
