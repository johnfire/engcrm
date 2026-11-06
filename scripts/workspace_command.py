"""Run a trusted maintenance script using the selected/default workspace's limited role."""
import os
import runpy
import sys
from uuid import uuid4

from gcrm.audit_context import audit_scope
from gcrm.tools.db_account_lifecycle import get_default_workspace_id
from gcrm.workspace_context import get_workspace_id, workspace_scope


def run_workspace_command(arguments: list[str]) -> None:
    if not arguments:
        raise ValueError("A maintenance script path is required")
    workspace_id = get_workspace_id() or get_default_workspace_id()
    previous_arguments = sys.argv
    try:
        sys.argv = arguments
        with workspace_scope(workspace_id), audit_scope(os.getenv("GCRM_ACTOR", "operator-cli"),
                                                       os.getenv("GCRM_ACTOR_TYPE", "user"), str(uuid4())):
            runpy.run_path(arguments[0], run_name="__main__")
    finally:
        sys.argv = previous_arguments


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python -m scripts.workspace_command scripts/example.py [arguments]")
    run_workspace_command(sys.argv[1:])
