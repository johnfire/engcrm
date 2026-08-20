from dataclasses import dataclass

from gcrm_scout_agent import create_scout_agent
from langchain_core.messages import AIMessage


@dataclass(frozen=True)
class DummyMission:
    goal: str = "Find art venues"
    identity: str = "Test Artist"
    targets: str = "galleries, cafes"
    fit_criteria: str = "contemporary art friendly"
    outreach_style: str = "personal"
    language_default: str = "de"


class FakeLLM:
    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self._index = 0

    def invoke(self, messages):
        response = self._responses[self._index % len(self._responses)]
        self._index += 1
        return AIMessage(content=response)


def _no_page(url: str) -> str:
    """Website fetch is a no-op in tests — scoring is driven by the fake LLM."""
    return ""


def _no_city_context(city: str, country: str = "DE") -> dict:
    """No city market context in tests."""
    return {}


# Mixed-case type that IS a SCORED_TYPES member — also exercises case-insensitive matching.
SAMPLE_CANDIDATE = {
    "id": 1, "name": "Nord Unternehmensberatung", "city": "Munich",
    "type": "Unternehmensberatung", "pipeline_stage": "candidate", "status": "none",
}


def make_tools(candidates=None):
    updates = []
    runs = {}

    def fetch_candidates(limit=50):
        return [SAMPLE_CANDIDATE] if candidates is None else candidates

    def set_contact_state(contact_id, *, pipeline_stage, status, fit_score=None, notes=""):
        updates.append(
            {"id": contact_id, "stage": pipeline_stage, "status": status, "score": fit_score}
        )

    def start_run(agent_name, input_data):
        run_id = len(runs) + 1
        runs[run_id] = {"status": "running"}
        return run_id

    def finish_run(run_id, status, summary, output_data):
        runs[run_id]["status"] = status

    return fetch_candidates, set_contact_state, start_run, finish_run, updates, runs


def test_agent_promotes_high_score():
    fetch, update, start_run, finish_run, updates, runs = make_tools()
    llm = FakeLLM(['{"outcome": "fit", "reasoning": "Good contemporary focus"}'])

    agent = create_scout_agent(
        llm=llm, fetch_candidates=fetch, set_contact_state=update,
        fetch_page=_no_page, fetch_city_context=_no_city_context,
        start_run=start_run, finish_run=finish_run, mission=DummyMission(),
    )
    result = agent.invoke({"limit": 50})

    assert result["promoted_count"] == 1
    assert result["no_fit_count"] == 0
    assert updates[0]["stage"] == "suspect"
    assert updates[0]["status"] == "ready"
    assert updates[0]["score"] == 75  # FIT_SCORES["fit"]


def test_agent_drops_low_score():
    fetch, update, start_run, finish_run, updates, runs = make_tools()
    llm = FakeLLM(['{"outcome": "no_fit", "reasoning": "Wrong style"}'])

    agent = create_scout_agent(
        llm=llm, fetch_candidates=fetch, set_contact_state=update,
        fetch_page=_no_page, fetch_city_context=_no_city_context,
        start_run=start_run, finish_run=finish_run, mission=DummyMission(),
    )
    result = agent.invoke({"limit": 50})

    assert result["promoted_count"] == 0
    assert result["no_fit_count"] == 1
    assert updates[0]["stage"] == "not_in_pipeline"
    assert updates[0]["status"] == "dropped"


def test_agent_handles_empty_candidates():
    fetch, update, start_run, finish_run, updates, runs = make_tools(candidates=[])
    llm = FakeLLM(["{}"])

    agent = create_scout_agent(
        llm=llm, fetch_candidates=fetch, set_contact_state=update,
        fetch_page=_no_page, fetch_city_context=_no_city_context,
        start_run=start_run, finish_run=finish_run, mission=DummyMission(),
    )
    result = agent.invoke({"limit": 50})

    assert result["promoted_count"] == 0
    assert result["no_fit_count"] == 0
    assert updates == []


def test_agent_continues_on_score_parse_error():
    candidates = [
        {"id": 1, "name": "Beratung A", "city": "Munich", "type": "Unternehmensberatung"},
        {"id": 2, "name": "Beratung B", "city": "Berlin", "type": "Unternehmensberatung"},
    ]
    fetch, update, start_run, finish_run, updates, runs = make_tools(candidates=candidates)
    # first response invalid (scoring error -> 'unsure'), second valid -> 'fit'
    llm = FakeLLM(["not json", '{"outcome": "fit", "reasoning": "Good fit"}'])

    agent = create_scout_agent(
        llm=llm, fetch_candidates=fetch, set_contact_state=update,
        fetch_page=_no_page, fetch_city_context=_no_city_context,
        start_run=start_run, finish_run=finish_run, mission=DummyMission(),
    )
    result = agent.invoke({"limit": 50})

    # first contact left a candidate for review (scoring error is non-fatal),
    # second promoted to suspect/ready
    assert result["promoted_count"] == 1
    assert result["unsure_count"] == 1
    assert result["no_fit_count"] == 0
