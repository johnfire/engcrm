"""Pipeline stage triggers: command mapping, validation, and the mobile endpoint.
subprocess.Popen is mocked — nothing actually spawns."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.jwt_auth import create_token
from gcrm.supervisor import pipeline

client = TestClient(main.app)
AUTH = {"Authorization": f"Bearer {create_token('admin')}"}


class TestValidate:
    def test_unknown_stage(self):
        with pytest.raises(ValueError):
            pipeline.validate("bogus", "Augsburg", 1)

    def test_city_required(self):
        with pytest.raises(ValueError):
            pipeline.validate("scout", "", None)

    def test_level_required_for_research(self):
        with pytest.raises(ValueError):
            pipeline.validate("research", "Augsburg", None)

    def test_followup_needs_nothing(self):
        pipeline.validate("followup", "", None)  # no raise


class TestSpawn:
    def test_research_command(self):
        with patch("gcrm.supervisor.pipeline.subprocess.Popen") as popen:
            pipeline.spawn_stage("research", city="Augsburg", level=1, country="DE")
        argv = popen.call_args.args[0]
        assert "gcrm.supervisor.run_research" in argv
        assert "--city" in argv and "Augsburg" in argv and "1" in argv

    def test_all_uses_run_pipeline(self):
        with patch("gcrm.supervisor.pipeline.subprocess.Popen") as popen:
            pipeline.spawn_stage("all", city="Augsburg", level=2)
        assert "gcrm.supervisor.run_pipeline" in popen.call_args.args[0]

    def test_followup_command(self):
        with patch("gcrm.supervisor.pipeline.subprocess.Popen") as popen:
            pipeline.spawn_stage("followup")
        assert "gcrm.supervisor.run_followup" in popen.call_args.args[0]

    def test_opportunity_command(self):
        with patch("gcrm.supervisor.pipeline.subprocess.Popen") as popen:
            pipeline.spawn_stage("opportunity")
        assert "gcrm.supervisor.run_opportunity_analysis" in popen.call_args.args[0]


class TestEndpoint:
    def test_requires_auth(self):
        assert client.post("/api/pipeline/scout/run", json={"city": "X"}).status_code in (401, 403)

    def test_queues_stage(self):
        with patch("gcrm.api.routers.api_pipeline.spawn_stage") as spawn:
            resp = client.post("/api/pipeline/research/run", headers=AUTH,
                               json={"city": "Augsburg", "level": 1})
        assert resp.status_code == 202
        assert resp.json()["stage"] == "research"
        assert spawn.call_args.kwargs["city"] == "Augsburg"

    def test_bad_request_is_422(self):
        # Real spawn_stage runs: research with no level -> ValueError -> 422
        resp = client.post("/api/pipeline/research/run", headers=AUTH, json={"city": "Augsburg"})
        assert resp.status_code == 422
