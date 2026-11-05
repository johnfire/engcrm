"""Carry a request's verified workspace into detached worker processes."""
import os

from gcrm.workspace_context import get_workspace_id, has_workspace_scope


def job_environment() -> dict[str, str]:
    environment = os.environ.copy()
    workspace_id = get_workspace_id()
    if workspace_id is None and has_workspace_scope():
        from gcrm.tools.db_account_lifecycle import get_default_workspace_id
        workspace_id = get_default_workspace_id()
    if workspace_id is not None:
        environment["GCRM_JOB_WORKSPACE_ID"] = str(workspace_id)
    return environment
