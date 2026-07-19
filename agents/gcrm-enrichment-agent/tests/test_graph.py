"""
Tests use dummy implementations of every Protocol — no real LLM, DB, or network.
Focus: the three ported behaviours — page fetching, language-aware queries, and
the never-overwrite-existing-data guard (with cannot_find_more_data fallback).
"""
from gcrm_enrichment_agent import create_enrichment_agent
from langchain_core.messages import AIMessage


class FakeLLM:
    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self._index = 0

    def invoke(self, messages):
        response = self._responses[self._index % len(self._responses)]
        self._index += 1
        return AIMessage(content=response)


def make_tools(contacts, llm_responses):
    """Build a full set of dummy tools; capture searches, fetches, and updates."""
    state = {
        "searched": [],      # queries passed to web_search
        "fetched": [],       # urls passed to fetch_page
        "updates": {},       # contact_id -> dict of kwargs written
        "runs": {},
    }

    def web_search(query: str) -> list[dict]:
        state["searched"].append(query)
        return [
            {"title": "Home", "url": "https://realbusiness.de", "snippet": "the business"},
            {"title": "Directory", "url": "https://www.google.com/maps/x", "snippet": "listing"},
        ]

    def fetch_page(url: str) -> str:
        state["fetched"].append(url)
        return "Kontakt: info@realbusiness.de"

    def fetch_contacts(limit: int) -> list[dict]:
        return contacts

    def update_contact(contact_id: int, **kwargs) -> None:
        state["updates"][contact_id] = kwargs

    def start_run(agent_name: str, input_data: dict) -> int:
        run_id = len(state["runs"]) + 1
        state["runs"][run_id] = {"agent": agent_name, "status": "running"}
        return run_id

    def finish_run(run_id: int, status: str, summary: str, output_data: dict) -> None:
        state["runs"][run_id].update(status=status, summary=summary)

    agent = create_enrichment_agent(
        llm=FakeLLM(llm_responses),
        web_search=web_search,
        fetch_page=fetch_page,
        fetch_contacts=fetch_contacts,
        update_contact=update_contact,
        start_run=start_run,
        finish_run=finish_run,
    )
    return agent, state


def test_fetches_pages_and_skips_directory_domains():
    contacts = [{"id": 1, "name": "Real Business", "city": "Munich", "country": "DE"}]
    agent, state = make_tools(contacts, ['{"website": "https://realbusiness.de", "email": "info@realbusiness.de", "phone": null}'])

    agent.invoke({"limit": 10})

    # Only the non-directory URL is fetched; the google.com/maps result is skipped.
    assert state["fetched"] == ["https://realbusiness.de"]


def test_german_query_targets_impressum_kontakt():
    contacts = [{"id": 1, "name": "Real Business", "city": "Munich", "country": "DE"}]
    agent, state = make_tools(contacts, ['{"website": null, "email": null, "phone": null}'])

    agent.invoke({"limit": 10})

    assert state["searched"] == ["Real Business Munich Impressum Kontakt"]


def test_non_german_query_is_generic_english():
    contacts = [{"id": 1, "name": "Real Business", "city": "London", "country": "GB"}]
    agent, state = make_tools(contacts, ['{"website": null, "email": null, "phone": null}'])

    agent.invoke({"limit": 10})

    assert state["searched"] == ["Real Business London contact website email"]


def test_never_overwrites_existing_data():
    # Website already present; LLM returns a different website + a new email.
    contacts = [{
        "id": 1, "name": "Real Business", "city": "Munich", "country": "DE",
        "website": "https://existing.de", "email": "",
    }]
    agent, state = make_tools(
        contacts,
        ['{"website": "https://guess.de", "email": "info@realbusiness.de", "phone": null}'],
    )

    result = agent.invoke({"limit": 10})

    # Email (was missing) is written; website (already present) is NOT overwritten.
    assert state["updates"][1] == {"email": "info@realbusiness.de"}
    assert "website" not in state["updates"][1]
    assert result["enriched_count"] == 1


def test_nothing_found_marks_cannot_find_more_data():
    contacts = [{"id": 1, "name": "Ghost Co", "city": "Munich", "country": "DE"}]
    agent, state = make_tools(contacts, ['{"website": null, "email": null, "phone": null}'])

    result = agent.invoke({"limit": 10})

    assert state["updates"][1] == {"status": "cannot_find_more_data"}
    assert result["not_found_count"] == 1
    assert result["enriched_count"] == 0
