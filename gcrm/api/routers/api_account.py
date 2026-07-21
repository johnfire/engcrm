"""Mobile self-service account settings (JWT auth)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from gcrm.api.jwt_auth import require_jwt_payload
from gcrm.api.push import send_silent_push_to_user
from gcrm.i18n import SUPPORTED_LANGUAGES
from gcrm.tools.db_users import set_user_ui_language

router = APIRouter(prefix="/api/account", tags=["mobile-account"])


class LanguageRequest(BaseModel):
    ui_language: str


@router.patch("/language")
def update_language(body: LanguageRequest, payload: dict = Depends(require_jwt_payload)) -> dict:
    if body.ui_language not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail="Unsupported language")
    user_id = payload.get("uid")
    if user_id is None:
        raise HTTPException(status_code=400, detail="No account to update (shared admin)")
    if not set_user_ui_language(user_id, body.ui_language):
        raise HTTPException(status_code=404, detail="Account not found")
    # Best-effort — tells this account's other signed-in devices to refresh
    # immediately even if they're currently foregrounded (send_silent_push_to_user
    # never raises, so a delivery failure can't fail this request).
    send_silent_push_to_user(user_id, {"type": "ui_language_changed", "ui_language": body.ui_language})
    return {"ui_language": body.ui_language}
