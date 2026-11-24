"""Authenticated mobile synchronization endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from gcrm.api.jwt_auth import require_jwt_payload
from gcrm.sync.contracts import DeviceRegistration, DeviceRegistrationResponse
from gcrm.tools.db_sync_devices import register_sync_device
from gcrm.workspace_context import get_workspace_id

router = APIRouter(prefix="/api/sync", tags=["mobile-sync"])


@router.post("/devices", response_model=DeviceRegistrationResponse)
def register_device(body: DeviceRegistration, payload: dict = Depends(require_jwt_payload)):
    user_id = payload.get("uid")
    workspace_id = get_workspace_id()
    if user_id is None or workspace_id is None:
        raise HTTPException(403, "A personal account is required for sync")
    if not register_sync_device(workspace_id, user_id, body):
        raise HTTPException(403, "This sync device has been revoked")
    return DeviceRegistrationResponse()
