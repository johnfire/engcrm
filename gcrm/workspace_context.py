"""Request/job-local workspace identity used to enforce database tenancy."""
import os
from contextlib import contextmanager
from contextvars import ContextVar

_job_workspace_id = os.getenv("GCRM_JOB_WORKSPACE_ID")
JOB_WORKSPACE_ID = int(_job_workspace_id) if _job_workspace_id is not None else None

_workspace_id: ContextVar[int | None] = ContextVar("workspace_id", default=None)
_workspace_required: ContextVar[bool] = ContextVar("workspace_required", default=False)


def set_workspace_id(workspace_id: int | None) -> None:
    """Set the active workspace for the current request or background job."""
    _workspace_id.set(workspace_id)


def get_workspace_id() -> int | None:
    """Return the active workspace, if a request has established one."""
    return _workspace_id.get() if _workspace_id.get() is not None else JOB_WORKSPACE_ID


def require_workspace_scope(required: bool = True) -> None:
    """Require the default workspace even for authenticated legacy shared-admin tokens."""
    _workspace_required.set(required)


def has_workspace_scope() -> bool:
    return _workspace_required.get() or get_workspace_id() is not None


@contextmanager
def workspace_scope(workspace_id: int):
    """Temporarily enter a workspace and restore both identity and enforcement on exit."""
    identity_token = _workspace_id.set(workspace_id)
    enforcement_token = _workspace_required.set(True)
    try:
        yield
    finally:
        _workspace_required.reset(enforcement_token)
        _workspace_id.reset(identity_token)
