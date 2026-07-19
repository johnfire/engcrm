"""Request/job-local workspace identity used to enforce database tenancy."""
from contextvars import ContextVar

_workspace_id: ContextVar[int | None] = ContextVar("workspace_id", default=None)


def set_workspace_id(workspace_id: int | None) -> None:
    """Set the active workspace for the current request or background job."""
    _workspace_id.set(workspace_id)


def get_workspace_id() -> int | None:
    """Return the active workspace, if a request has established one."""
    return _workspace_id.get()
