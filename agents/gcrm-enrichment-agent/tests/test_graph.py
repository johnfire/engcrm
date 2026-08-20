"""
Tests use dummy implementations of every Protocol — no real LLM, DB, or network.
Focus: the three ported behaviours — page fetching, language-aware queries, and
the never-overwrite-existing-data guard (with the research_exhausted fallback).
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


def make_tools(contacts, llm_responses, search_results=None, search_error=None):
    """Build a full set of dummy tools; capture searches, fetches, and updates.

    `search_results` overrides what web_search returns (pass [] for an outage);
    `search_error` makes it raise, mimicking a search backend that is down.
    """
    state = {
        "searched": [],      # queries passed to web_search
        "fetched": [],       # urls passed to fetch_page
        "updates": {},       # contact_id -> detail fields written
        "flags": {},         # contact_id -> suppression flag raised
        "runs": {},
    }

    def web_search(query: str) -> list[dict]:
        state["searched"].append(query)
        if search_error is not None:
            raise search_error
        if search_results is not None:
            return search_results
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

    def set_suppression_flag(contact_id: int, flag: str, value: bool = True) -> None:
        state["flags"][contact_id] = {flag: value}

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
        set_suppression_flag=set_suppression_flag,
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


def test_nothing_found_raises_research_exhausted():
    contacts = [{"id": 1, "name": "Ghost Co", "city": "Munich", "country": "DE"}]
    agent, state = make_tools(contacts, ['{"website": null, "email": null, "phone": null}'])

    result = agent.invoke({"limit": 10})

    assert state["flags"][1] == {"research_exhausted": True}
    assert result["not_found_count"] == 1
    assert result["enriched_count"] == 0


# A silently-broken web search once wrote off every contact it touched, including
# ones whose website was already in the database and never opened. These pin the
# behaviour that stops a search outage deciding a contact is unreachable.

def test_known_website_is_read_when_search_finds_nothing():
    contacts = [{
        "id": 1, "name": "Elektro Schneider", "city": "Landsberg", "country": "DE",
        "website": "https://schneider-landsberg.de", "email": "",
    }]
    agent, state = make_tools(
        contacts,
        ['{"website": null, "email": "info@schneider-landsberg.de", "phone": null}'],
        search_results=[],
    )

    result = agent.invoke({"limit": 10})

    assert state["fetched"] == [
        "https://schneider-landsberg.de",
        "https://schneider-landsberg.de/impressum",
    ]
    assert state["updates"][1] == {"email": "info@schneider-landsberg.de"}
    assert result["enriched_count"] == 1


def test_known_website_is_read_when_search_raises():
    contacts = [{
        "id": 1, "name": "Elektro Schneider", "city": "Landsberg", "country": "DE",
        "website": "https://schneider-landsberg.de", "email": "",
    }]
    agent, state = make_tools(
        contacts,
        ['{"website": null, "email": "info@schneider-landsberg.de", "phone": null}'],
        search_error=RuntimeError("search backend down"),
    )

    result = agent.invoke({"limit": 10})

    assert "https://schneider-landsberg.de" in state["fetched"]
    assert result["enriched_count"] == 1


def test_known_website_is_read_before_search_hits():
    contacts = [{
        "id": 1, "name": "Real Business", "city": "Munich", "country": "DE",
        "website": "https://ownsite.de", "email": "",
    }]
    agent, state = make_tools(
        contacts, ['{"website": null, "email": "info@ownsite.de", "phone": null}'],
    )

    agent.invoke({"limit": 10})

    assert state["fetched"][0] == "https://ownsite.de"
    assert state["fetched"][1] == "https://ownsite.de/impressum"
    # Still capped, so one contact cannot cost unbounded fetches.
    assert len(state["fetched"]) <= 3


def test_no_website_and_no_search_results_is_still_a_dead_end():
    contacts = [{"id": 1, "name": "Ghost Co", "city": "Munich", "country": "DE"}]
    agent, state = make_tools(
        contacts, ['{"website": null, "email": null, "phone": null}'], search_results=[],
    )

    result = agent.invoke({"limit": 10})

    assert state["fetched"] == []
    assert state["flags"][1] == {"research_exhausted": True}
    assert result["not_found_count"] == 1
