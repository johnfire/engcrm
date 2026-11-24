"""Authenticated mobile synchronization endpoints."""

import time
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from itsdangerous import BadSignature, URLSafeTimedSerializer

from gcrm.api.jwt_auth import require_jwt_payload
from gcrm.config import JWT_SECRET
from gcrm.sync.contracts import DeviceRegistration, DeviceRegistrationResponse
from gcrm.tools.db_sync_bootstrap import read_bootstrap_page
from gcrm.tools.db_sync_devices import register_sync_device
from gcrm.tools.db_sync_pull import read_sync_changes
from gcrm.workspace_context import get_workspace_id

router = APIRouter(prefix="/api/sync", tags=["mobile-sync"])
_bootstrap_tokens = URLSafeTimedSerializer(JWT_SECRET, salt="mobile-sync-bootstrap-v1")


@router.post("/devices", response_model=DeviceRegistrationResponse)
def register_device(body: DeviceRegistration, payload: dict = Depends(require_jwt_payload)):
    user_id = payload.get("uid")
    workspace_id = get_workspace_id()
    if user_id is None or workspace_id is None:
        raise HTTPException(403, "A personal account is required for sync")
    if not register_sync_device(workspace_id, user_id, body):
        raise HTTPException(403, "This sync device has been revoked")
    return DeviceRegistrationResponse()


@router.get("/bootstrap")
def bootstrap(device_id: UUID, server_environment: Literal["production", "reviewer"] = "production",
              token: str | None = None, limit: int = Query(default=500, ge=1, le=500),
              payload: dict = Depends(require_jwt_payload)):
    user_id, workspace_id = payload.get("uid"), get_workspace_id()
    if user_id is None or workspace_id is None:
        raise HTTPException(403, "A personal account is required for sync")
    scope = {"workspace": workspace_id, "user": user_id, "device": str(device_id), "environment": server_environment}
    position = None
    started_at = int(time.time())
    if token:
        try:
            decoded = _bootstrap_tokens.loads(token, max_age=86400)
        except BadSignature as error:
            raise HTTPException(400, "Invalid or expired bootstrap token") from error
        if decoded.get("scope") != scope:
            raise HTTPException(400, "Bootstrap token belongs to another account or device")
        started_at = decoded["started_at"]
        if time.time() - started_at > 86400:
            raise HTTPException(400, "Bootstrap token has expired")
        position = decoded["position"]
    page = read_bootstrap_page(workspace_id, user_id, str(device_id), server_environment, position, limit)
    if page is None:
        raise HTTPException(403, "Sync device is unregistered or revoked")
    next_position = page.pop("position")
    page["next_token"] = _bootstrap_tokens.dumps({"scope": scope, "position": next_position,
                                                   "started_at": started_at}) if next_position else None
    return page


@router.get("/changes")
def changes(device_id: UUID, after: int = Query(ge=0), limit: int = Query(default=500, ge=1, le=500),
            server_environment: Literal["production", "reviewer"] = "production",
            payload: dict = Depends(require_jwt_payload)):
    user_id, workspace_id = payload.get("uid"), get_workspace_id()
    if user_id is None or workspace_id is None:
        raise HTTPException(403, "A personal account is required for sync")
    page = read_sync_changes(workspace_id, user_id, str(device_id), server_environment, after, limit)
    if page is None:
        raise HTTPException(403, "Sync device is unregistered or revoked")
    if page.get("bootstrap_required"):
        raise HTTPException(409, "bootstrap_required")
    return page
