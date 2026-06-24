"""Mobile JSON API for people — the individuals on scanned cards, each linked to
their company contact. Read-only; people are created via the card-confirm flow."""
from fastapi import APIRouter, Depends, HTTPException

from gcrm.api.jwt_auth import require_jwt
from gcrm.tools.db import get_people, get_person

router = APIRouter(prefix="/api/people", tags=["mobile-people"])


@router.get("")
def list_people(search: str = "", _role: str = Depends(require_jwt)) -> list[dict]:
    return get_people(search)


@router.get("/{person_id}")
def person_detail(person_id: int, _role: str = Depends(require_jwt)) -> dict:
    person = get_person(person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    return person
