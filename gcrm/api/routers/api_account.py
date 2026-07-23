"""Mobile self-service account settings (JWT auth)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from gcrm.api.jwt_auth import require_jwt_payload
from gcrm.api.push import send_silent_push_to_user
from gcrm.i18n import SUPPORTED_LANGUAGES
from gcrm.tools.db_ai_backends import CHEAP_MODELS, SMART_MODELS, get_ai_backends, set_ai_backends
from gcrm.tools.db_users import set_user_ui_language

router = APIRouter(prefix="/api/account", tags=["mobile-account"])


class LanguageRequest(BaseModel):
    ui_language: str


class AiBackendsRequest(BaseModel):
    cheap_llm: str
    smart_llm: str


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


@router.get("/ai")
def get_ai_backends_for_mobile(_: dict = Depends(require_jwt_payload)) -> dict:
    """Return the workspace AI backend selection for the mobile settings UI."""
    return get_ai_backends()


@router.patch("/ai")
def update_ai_backends(body: AiBackendsRequest, payload: dict = Depends(require_jwt_payload)) -> dict:
    """Allow only an administrator to change future background-run models."""
    if payload["sub"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        set_ai_backends(body.cheap_llm, body.smart_llm)
    except ValueError:
        raise HTTPException(status_code=400, detail="Unsupported AI backend")
    return {"cheap_llm": body.cheap_llm, "smart_llm": body.smart_llm,
            "cheap_models": CHEAP_MODELS, "smart_models": SMART_MODELS}
