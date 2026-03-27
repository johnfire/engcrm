from dataclasses import dataclass
from langchain_core.messages import AIMessage
from gcrm_outreach_agent import create_outreach_agent


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


SAMPLE_CONTACT = {
    "id": 1, "name": "Galerie Nord", "city": "Munich",
    "type": "gallery", "preferred_language": "de",
}

DRAFT_RESPONSE = '{"subject": "Anfrage zur Ausstellung", "body": "Sehr geehrte Damen und Herren..."}'


def make_tools(contacts=None, compliance_result=True):
    queued = []
    runs = {}

    def fetch_ready_contacts(limit=20):
        return [SAMPLE_CONTACT] if contacts is None else contacts

    def check_compliance(contact_id):
        return compliance_result

    def queue_for_approval(contact_id, run_id, subject, body):
        queued.append({"contact_id": contact_id, "subject": subject, "body": body})
        return len(queued)

    def start_run(agent_name, input_data):
        run_id = len(runs) + 1
        runs[run_id] = {"status": "running"}
        return run_id

    def finish_run(run_id, status, summary, output_data):
        runs[run_id]["status"] = status

    return fetch_ready_contacts, check_compliance, queue_for_approval, start_run, finish_run, queued, runs


def test_agent_queues_compliant_contact():
    fetch, check, queue, start_run, finish_run, queued, runs = make_tools()
    llm = FakeLLM([DRAFT_RESPONSE])

    agent = create_outreach_agent(
        llm=llm, fetch_ready_contacts=fetch, check_compliance=check,
        queue_for_approval=queue, start_run=start_run, finish_run=finish_run,
        mission=DummyMission(),
    )
    result = agent.invoke({"limit": 20})

    assert result["queued_count"] == 1
    assert result["blocked_count"] == 0
    assert queued[0]["subject"] == "Anfrage zur Ausstellung"


def test_agent_blocks_opted_out_contact():
    fetch, _, queue, start_run, finish_run, queued, runs = make_tools(compliance_result=False)
    llm = FakeLLM([DRAFT_RESPONSE])

    def check_compliance_false(contact_id):
        return False

    agent = create_outreach_agent(
        llm=llm, fetch_ready_contacts=fetch, check_compliance=check_compliance_false,
        queue_for_approval=queue, start_run=start_run, finish_run=finish_run,
        mission=DummyMission(),
    )
    result = agent.invoke({"limit": 20})

    assert result["queued_count"] == 0
    assert result["blocked_count"] == 1
    assert queued == []


def test_agent_handles_draft_parse_error():
    fetch, check, queue, start_run, finish_run, queued, runs = make_tools()
    llm = FakeLLM(["not valid json"])

    agent = create_outreach_agent(
        llm=llm, fetch_ready_contacts=fetch, check_compliance=check,
        queue_for_approval=queue, start_run=start_run, finish_run=finish_run,
        mission=DummyMission(),
    )
    result = agent.invoke({"limit": 20})

    assert result["queued_count"] == 0
    assert result["blocked_count"] == 1
    assert queued == []


def test_agent_handles_empty_contacts():
    fetch, check, queue, start_run, finish_run, queued, runs = make_tools(contacts=[])
    llm = FakeLLM([DRAFT_RESPONSE])

    agent = create_outreach_agent(
        llm=llm, fetch_ready_contacts=fetch, check_compliance=check,
        queue_for_approval=queue, start_run=start_run, finish_run=finish_run,
        mission=DummyMission(),
    )
    result = agent.invoke({"limit": 20})

    assert result["queued_count"] == 0
    assert result["blocked_count"] == 0
    assert "0 contacts" in result["summary"]
