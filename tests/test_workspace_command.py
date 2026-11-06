"""Container maintenance commands use the default workspace's restricted role."""
import sys
from unittest.mock import patch

import pytest

from gcrm.workspace_context import get_workspace_id, has_workspace_scope, workspace_scope
from scripts.workspace_command import run_workspace_command


def test_script_runs_in_default_workspace_and_restores_process_context():
    original = sys.argv
    observed = []

    def run(script, run_name):
        observed.append((script, run_name, list(sys.argv), get_workspace_id(), has_workspace_scope()))

    with patch("scripts.workspace_command.get_default_workspace_id", return_value=7), \
         patch("scripts.workspace_command.runpy.run_path", side_effect=run):
        run_workspace_command(["scripts/maps/pin_queue.py", "--import"])
    assert observed == [("scripts/maps/pin_queue.py", "__main__", ["scripts/maps/pin_queue.py", "--import"], 7, True)]
    assert sys.argv is original
    assert get_workspace_id() is None and not has_workspace_scope()


def test_command_failure_restores_workspace_and_arguments():
    original = sys.argv
    with patch("scripts.workspace_command.get_default_workspace_id", return_value=7), \
         patch("scripts.workspace_command.runpy.run_path", side_effect=RuntimeError("command failed")):
        with pytest.raises(RuntimeError, match="command failed"):
            run_workspace_command(["scripts/maps/pin_queue.py"])
    assert sys.argv is original
    assert get_workspace_id() is None and not has_workspace_scope()


def test_nested_workspace_scope_is_preserved():
    with workspace_scope(9), patch("scripts.workspace_command.runpy.run_path") as execute:
        run_workspace_command(["scripts/maps/pin_queue.py"])
        execute.assert_called_once()
        assert get_workspace_id() == 9 and has_workspace_scope()
    assert get_workspace_id() is None and not has_workspace_scope()


def test_missing_script_never_runs_a_command():
    with pytest.raises(ValueError, match="script path"):
        run_workspace_command([])
