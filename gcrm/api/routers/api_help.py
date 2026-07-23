"""JWT-protected Help Centre API used by the Android app."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from gcrm.api.jwt_auth import require_jwt_payload
from gcrm.tools.db_help import (
    complete_help_tour,
    has_completed_help_tour,
    list_published_help,
    record_help_feedback,
)
from gcrm.tools.db_users import get_user_by_id

router = APIRouter(prefix="/api/help", tags=["mobile-help"])


def _user_context(payload: dict) -> tuple[int | None, str, int | None]:
    user_id = payload.get("uid")
    user = get_user_by_id(user_id) if user_id is not None else None
    return user_id, (user or {}).get("ui_language", "en"), (user or {}).get("workspace_id")


@router.get("")
def list_help(q: str = "", payload: dict = Depends(require_jwt_payload)) -> list[dict]:
    _, language, workspace_id = _user_context(payload)
    return list_published_help(workspace_id, language, "mobile", q)


@router.get("/tour")
def get_tour_status(payload: dict = Depends(require_jwt_payload)) -> dict:
    user_id, _, _ = _user_context(payload)
    return {"completed": has_completed_help_tour(user_id)}


class FeedbackRequest(BaseModel):
    article_id: int
    helpful: bool
    comment: str = Field(default="", max_length=1000)


@router.post("/feedback")
def submit_feedback(body: FeedbackRequest, payload: dict = Depends(require_jwt_payload)) -> dict:
    user_id, _, workspace_id = _user_context(payload)
    record_help_feedback(workspace_id, body.article_id, user_id, body.helpful, body.comment)
    return {"recorded": True}


@router.post("/tour/complete")
def finish_tour(payload: dict = Depends(require_jwt_payload)) -> dict:
    user_id, _, _ = _user_context(payload)
    if user_id is not None:
        complete_help_tour(user_id)
    return {"completed": True}
