"""The research runner split into functions for Gather (2026-11-05): each returns the ids of
the companies it saved and still records the scan as before."""
import pytest

import gcrm.supervisor.run_research as runner
import gcrm.tools as tools


class FakeAgent:
    def __init__(self, state_seen):
        self.state_seen = state_seen

    def invoke(self, state):
        self.state_seen.append(state)
        return {"saved_ids": [41, 42], "scan_complete": True, "summary": "2 saved"}


@pytest.fixture
def recorded(monkeypatch):
    calls = {"states": [], "area_scans": [], "city_scans": [], "thoughts": []}
    monkeypatch.setattr(runner, "_research_agent", lambda: FakeAgent(calls["states"]))
    monkeypatch.setattr(tools, "get_area", lambda area_id: {
        "city": "Untermeitingen", "country": "DE", "latitude": 48.16, "longitude": 10.8, "radius_m": 900})
    monkeypatch.setattr(tools, "record_area_scan_result",
                        lambda area_id, level, found, complete: calls["area_scans"].append((area_id, level, found, complete)))
    monkeypatch.setattr(tools, "can_run_level", lambda city, country, level: (True, ""))
    monkeypatch.setattr(tools, "record_scan_result",
                        lambda city, country, level, found, complete: calls["city_scans"].append((city, level, found)))
    monkeypatch.setattr("gcrm.tools.memory.capture_thought", lambda text: calls["thoughts"].append(text))
    return calls


def test_an_area_scan_returns_its_new_ids_and_records_each_level(recorded):
    assert runner.research_area(7, [1, 2]) == [41, 42]
    assert recorded["area_scans"] == [(7, 1, 2, True), (7, 2, 2, True)]
    assert recorded["states"][0]["levels"] == [1, 2] and recorded["states"][0]["area_id"] == 7


def test_a_city_scan_returns_its_new_ids_and_records_the_scan(recorded):
    assert runner.research_city("Untermeitingen", "DE", 2) == [41, 42]
    assert recorded["city_scans"] == [("Untermeitingen", 2, 2)]


def test_a_level_that_may_not_run_yet_is_refused(recorded, monkeypatch):
    monkeypatch.setattr(tools, "can_run_level", lambda city, country, level: (False, "run level 1 first"))
    with pytest.raises(ValueError, match="level 1 first"):
        runner.research_city("Untermeitingen", "DE", 2)
    assert recorded["states"] == []


def test_an_unknown_area_is_refused(recorded, monkeypatch):
    monkeypatch.setattr(tools, "get_area", lambda area_id: None)
    with pytest.raises(ValueError):
        runner.research_area(99, [1])
