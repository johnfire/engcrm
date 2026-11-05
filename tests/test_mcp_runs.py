"""The local MCP server starts the same runs as the buttons (2026-11-05): Gather for a city
and level, and Judge. The old trigger_run, which started the retired six-step supervisor
chain, is gone."""
import json
from unittest.mock import patch

import gcrm.mcp.server as server


def test_gather_starts_the_gather_run_for_a_city_and_level():
    with patch("gcrm.mcp.server.spawn_stage") as spawn:
        result = json.loads(server.trigger_gather("Untermeitingen", 2))
    spawn.assert_called_once_with("all", city="Untermeitingen", level=2, country="DE")
    assert result["started"] == "gather"


def test_judge_starts_the_judge_run():
    with patch("gcrm.mcp.server.spawn_stage") as spawn:
        result = json.loads(server.trigger_judge())
    spawn.assert_called_once_with("judge")
    assert result["started"] == "judge"


def test_a_bad_request_comes_back_as_an_error_not_an_exception():
    with patch("gcrm.mcp.server.spawn_stage", side_effect=ValueError("all requires a level in [1..10]")):
        result = json.loads(server.trigger_gather("Untermeitingen", 99))
    assert "level" in result["error"]


def test_the_old_full_chain_trigger_is_gone():
    assert not hasattr(server, "trigger_run")
