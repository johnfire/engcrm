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


class TestValidateArea:
    def test_unknown_stage(self):
        with pytest.raises(ValueError):
            pipeline.validate_area("scout", 1, [1])

    def test_invalid_area_id(self):
        with pytest.raises(ValueError):
            pipeline.validate_area("research", 0, [1])

    def test_no_levels(self):
        with pytest.raises(ValueError):
            pipeline.validate_area("research", 1, [])

    def test_unknown_level(self):
        with pytest.raises(ValueError):
            pipeline.validate_area("research", 1, [99])

    def test_too_many_levels(self):
        with pytest.raises(ValueError):
            pipeline.validate_area("research", 1, [1, 2, 3, 4, 5, 6, 7])

    def test_valid_request_does_not_raise(self):
        pipeline.validate_area("research", 1, [1, 3])


class TestSpawnArea:
    def test_research_command(self):
        with patch("gcrm.supervisor.pipeline.subprocess.Popen") as popen:
            pipeline.spawn_area_stage("research", area_id=7, levels=[1, 3])
        argv = popen.call_args.args[0]
        assert "gcrm.supervisor.run_research" in argv
        assert "--area-id" in argv and "7" in argv
        assert "--levels" in argv and "1,3" in argv


class TestEndpoint:
    def test_requires_auth(self):
        assert client.post("/api/pipeline/scout/run", json={"city": "X"}).status_code in (401, 403)

    def test_queues_stage_for_a_canonical_city(self):
        with patch("gcrm.api.routers.api_pipeline.spawn_stage") as spawn, \
             patch("gcrm.api.routers.api_pipeline.add_city") as add, \
             patch("gcrm.api.routers.api_pipeline.normalize_city",
                   return_value=[{"name": "Augsburg", "state": "Bayern", "type": "city"}]):
            resp = client.post("/api/pipeline/research/run", headers=AUTH,
                               json={"city": "Augsburg", "level": 1})
        assert resp.status_code == 202
        assert resp.json()["stage"] == "research"
        assert spawn.call_args.kwargs["city"] == "Augsburg"
        add.assert_called_once_with("Augsburg", "DE")

    def test_variant_asks_for_confirmation_and_queues_nothing(self):
        candidates = [{"name": "Landsberg am Lech", "state": "Bayern", "type": "town"}]
        with patch("gcrm.api.routers.api_pipeline.spawn_stage") as spawn, \
             patch("gcrm.api.routers.api_pipeline.add_city") as add, \
             patch("gcrm.api.routers.api_pipeline.normalize_city", return_value=candidates):
            resp = client.post("/api/pipeline/research/run", headers=AUTH,
                               json={"city": "Landsberg", "level": 1})
        assert resp.status_code == 200
        assert resp.json() == {"status": "needs_confirmation", "typed": "Landsberg",
                               "candidates": candidates}
        spawn.assert_not_called()
        add.assert_not_called()

    def test_unplaceable_city_asks_for_confirmation(self):
        with patch("gcrm.api.routers.api_pipeline.spawn_stage") as spawn, \
             patch("gcrm.api.routers.api_pipeline.normalize_city", return_value=[]):
            resp = client.post("/api/pipeline/scout/run", headers=AUTH, json={"city": "Augsbrug"})
        assert resp.json()["status"] == "needs_confirmation"
        assert resp.json()["candidates"] == []
        spawn.assert_not_called()

    def test_confirmed_city_skips_the_lookup(self):
        with patch("gcrm.api.routers.api_pipeline.spawn_stage") as spawn, \
             patch("gcrm.api.routers.api_pipeline.add_city") as add, \
             patch("gcrm.api.routers.api_pipeline.normalize_city") as lookup:
            resp = client.post("/api/pipeline/research/run", headers=AUTH,
                               json={"city": "Landsberg am Lech", "level": 1, "confirmed": True})
        assert resp.status_code == 202
        lookup.assert_not_called()
        add.assert_called_once_with("Landsberg am Lech", "DE")
        assert spawn.call_args.kwargs["city"] == "Landsberg am Lech"

    @pytest.mark.parametrize("stage", ["followup", "opportunity"])
    def test_global_stages_skip_the_city_check(self, stage):
        with patch("gcrm.api.routers.api_pipeline.spawn_stage") as spawn, \
             patch("gcrm.api.routers.api_pipeline.add_city") as add, \
             patch("gcrm.api.routers.api_pipeline.normalize_city") as lookup:
            resp = client.post(f"/api/pipeline/{stage}/run", headers=AUTH, json={})
        assert resp.status_code == 202
        lookup.assert_not_called()
        add.assert_not_called()
        spawn.assert_called_once()

    def test_bad_request_is_422(self):
        # Real spawn_stage runs: research with no level -> ValueError -> 422
        with patch("gcrm.api.routers.api_pipeline.add_city"):
            resp = client.post("/api/pipeline/research/run", headers=AUTH,
                               json={"city": "Augsburg", "confirmed": True})
        assert resp.status_code == 422
