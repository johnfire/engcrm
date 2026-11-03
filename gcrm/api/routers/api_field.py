"""Mobile JSON API for field mode: the phone sends where the user is, a batch of points
at a time, while its Field mode switch is on. Each user only ever reads or deletes their
own points. See gcrm/tools/field_locations.py and
docs/plans/2026-11-03-field-mode-and-remote-mcp-plan.md."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from gcrm.api.jwt_auth import require_jwt_payload
from gcrm.api.routers.api_organizations import _personal_identity
from gcrm.tools.field_locations import MAX_BATCH, delete_history, latest_point, record_points

router = APIRouter(prefix="/api/me", tags=["mobile-field"])


class Point(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_m: float | None = Field(default=None, ge=0)
    recorded_at: datetime  # with its time zone, as the phone took the fix


class Points(BaseModel):
    points: list[Point] = Field(max_length=MAX_BATCH)


def _own_user_id(payload: dict) -> int:
    """The signed-in account; the shared admin login has no person to locate."""
    user_id, _ = _personal_identity(payload)
    if user_id is None:
        raise HTTPException(status_code=403, detail="Field mode needs a personal account")
    return user_id


@router.post("/locations")
def add_locations(body: Points, payload: dict = Depends(require_jwt_payload)) -> dict:
    """Store points of the travel history; points already stored are skipped, so a
    retried upload is harmless."""
    user_id = _own_user_id(payload)
    try:
        stored = record_points(user_id, [point.model_dump() for point in body.points])
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return {"stored": stored}


@router.get("/location")
def current_location(payload: dict = Depends(require_jwt_payload)) -> dict:
    """The newest point, its age, and whether it is too old to trust."""
    return {"location": latest_point(_own_user_id(payload))}


@router.delete("/locations")
def forget_locations(payload: dict = Depends(require_jwt_payload)) -> dict:
    """Delete the whole travel history."""
    return {"deleted": delete_history(_own_user_id(payload))}
