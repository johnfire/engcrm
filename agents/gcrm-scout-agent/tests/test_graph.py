from dataclasses import dataclass
from langchain_core.messages import AIMessage
from gcrm_scout_agent import create_scout_agent


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


SAMPLE_CANDIDATE = {
    "id": 1, "name": "Galerie Nord", "city": "Munich",
    "type": "gallery", "status": "candidate",
}


def make_tools(candidates=None):
    updates = []
    runs = {}

    def fetch_candidates(limit=50):
        return [SAMPLE_CANDIDATE] if candidates is None else candidates

    def update_contact(contact_id, status, fit_score, notes=""):
        updates.append({"id": contact_id, "status": status, "score": fit_score})

    def start_run(agent_name, input_data):
        run_id = len(runs) + 1
        runs[run_id] = {"status": "running"}
        return run_id

    def finish_run(run_id, status, summary, output_data):
        runs[run_id]["status"] = status

    return fetch_candidates, update_contact, start_run, finish_run, updates, runs


def test_agent_promotes_high_score():
    fetch, update, start_run, finish_run, updates, runs = make_tools()
    llm = FakeLLM(['{"score": 80, "reasoning": "Good contemporary focus", "promote": true}'])

    agent = create_scout_agent(
        llm=llm, fetch_candidates=fetch, update_contact=update,
        start_run=start_run, finish_run=finish_run, mission=DummyMission(),
    )
    result = agent.invoke({"limit": 50})

    assert result["promoted_count"] == 1
    assert result["dropped_count"] == 0
    assert updates[0]["status"] == "cold"
    assert updates[0]["score"] == 80


def test_agent_drops_low_score():
    fetch, update, start_run, finish_run, updates, runs = make_tools()
    llm = FakeLLM(['{"score": 30, "reasoning": "Wrong style", "promote": false}'])

    agent = create_scout_agent(
        llm=llm, fetch_candidates=fetch, update_contact=update,
        start_run=start_run, finish_run=finish_run, mission=DummyMission(),
    )
    result = agent.invoke({"limit": 50})

    assert result["promoted_count"] == 0
    assert result["dropped_count"] == 1
    assert updates[0]["status"] == "dropped"


def test_agent_handles_empty_candidates():
    fetch, update, start_run, finish_run, updates, runs = make_tools(candidates=[])
    llm = FakeLLM(["{}"])

    agent = create_scout_agent(
        llm=llm, fetch_candidates=fetch, update_contact=update,
        start_run=start_run, finish_run=finish_run, mission=DummyMission(),
    )
    result = agent.invoke({"limit": 50})

    assert result["promoted_count"] == 0
    assert result["dropped_count"] == 0
    assert updates == []


def test_agent_continues_on_score_parse_error():
    candidates = [
        {"id": 1, "name": "Gallery A", "city": "Munich", "type": "gallery"},
        {"id": 2, "name": "Gallery B", "city": "Berlin", "type": "gallery"},
    ]
    fetch, update, start_run, finish_run, updates, runs = make_tools(candidates=candidates)
    # first response invalid, second valid
    llm = FakeLLM(["not json", '{"score": 75, "reasoning": "Good fit", "promote": true}'])

    agent = create_scout_agent(
        llm=llm, fetch_candidates=fetch, update_contact=update,
        start_run=start_run, finish_run=finish_run, mission=DummyMission(),
    )
    result = agent.invoke({"limit": 50})

    # first contact dropped due to score error, second promoted
    assert result["promoted_count"] == 1
    assert result["dropped_count"] == 1
