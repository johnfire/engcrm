"""Mobile recon view — contacts nearest the user's GPS position, for on-foot visits."""
from fastapi import APIRouter, Depends

from gcrm.api.jwt_auth import require_jwt
from gcrm.tools.db_recon import get_organizations_near

router = APIRouter(prefix="/api/recon", tags=["mobile-recon"])


@router.get("")
def recon(
    lat: float,
    lng: float,
    not_contacted: bool = False,
    limit: int = 50,
    _role: str = Depends(require_jwt),
) -> list[dict]:
    return get_organizations_near(lat, lng, not_contacted=not_contacted, limit=min(limit, 200))
