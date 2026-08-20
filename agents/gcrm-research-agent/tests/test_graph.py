"""
Tests use dummy implementations of every Protocol — no real LLM, DB, or network.
"""
from dataclasses import dataclass

from gcrm_research_agent import create_research_agent, nodes
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
    """Page fetching is a no-op in tests — contact extraction is driven by the fake LLM."""
    return ""


def make_tools():
    saved = []
    runs = {}

    def web_search(query: str) -> list[dict]:
        return [{"title": f"Result for {query}", "url": "http://example.com", "snippet": "A gallery"}]

    def geo_search(query: str, city: str, country: str = "DE", lat=None, lon=None, radius_m=None) -> list[dict]:
        return [{"name": "Test Gallery", "address": "Main St 1", "city": city, "country": country}]

    def save_organization(name, city, *, country="DE", type="", website="", email="", phone="", notes="",
                     scan_level=None, neighborhood="", research_exhausted=False,
                     latitude=None, longitude=None, google=None) -> int:
        saved.append({"name": name, "city": city, "scan_level": scan_level,
                      "neighborhood": neighborhood,
                      "research_exhausted": research_exhausted, "google": google})
        return len(saved)

    def start_run(agent_name: str, input_data: dict) -> int:
        run_id = len(runs) + 1
        runs[run_id] = {"agent": agent_name, "status": "running"}
        return run_id

    def finish_run(run_id: int, status: str, summary: str, output_data: dict) -> None:
        runs[run_id]["status"] = status
        runs[run_id]["summary"] = summary

    return web_search, geo_search, save_organization, start_run, finish_run, saved, runs


def test_agent_saves_organizations():
    web_search, geo_search, save_organization, start_run, finish_run, saved, runs = make_tools()

    llm = FakeLLM([
        '[{"name": "Galerie Nord", "city": "Munich", "country": "DE", "type": "gallery"}]',  # extract_organizations (only LLM call)
    ])

    agent = create_research_agent(
        llm=llm,
        web_search=web_search,
        geo_search=geo_search,
        fetch_page=_no_page,
        save_organization=save_organization,
        start_run=start_run,
        finish_run=finish_run,
        mission=DummyMission(),
    )

    result = agent.invoke({"city": "Munich", "industry": "gallery", "country": "DE"})

    assert len(result["saved_ids"]) == 1
    assert saved[0]["name"] == "Galerie Nord"
    assert "1 new contacts saved" in result["summary"]
    assert result["errors"] == []


def test_agent_handles_empty_search_results():
    web_search, geo_search, save_organization, start_run, finish_run, saved, runs = make_tools()

    def empty_geo_search(query, city, country="DE", lat=None, lon=None, radius_m=None):
        return []

    def empty_web_search(query):
        return []

    llm = FakeLLM([
        '["galleries Munich"]',  # plan_queries
        '[]',                    # extract_organizations — nothing found
    ])

    agent = create_research_agent(
        llm=llm,
        web_search=empty_web_search,
        geo_search=empty_geo_search,
        fetch_page=_no_page,
        save_organization=save_organization,
        start_run=start_run,
        finish_run=finish_run,
        mission=DummyMission(),
    )

    result = agent.invoke({"city": "Munich", "industry": "gallery"})

    assert result["saved_ids"] == []
    assert result["errors"] == []
    assert "0 new contacts saved" in result["summary"]


def test_agent_handles_llm_json_error():
    web_search, geo_search, save_organization, start_run, finish_run, saved, runs = make_tools()

    llm = FakeLLM(["this is not json"])  # will fail parse in plan_queries

    agent = create_research_agent(
        llm=llm,
        web_search=web_search,
        geo_search=geo_search,
        fetch_page=_no_page,
        save_organization=save_organization,
        start_run=start_run,
        finish_run=finish_run,
        mission=DummyMission(),
    )

    result = agent.invoke({"city": "Munich", "industry": "gallery"})

    assert len(result["errors"]) > 0
    assert "extract_organizations" in result["errors"][0]
    assert result["saved_ids"] == []


def test_agent_handles_markdown_wrapped_json():
    web_search, geo_search, save_organization, start_run, finish_run, saved, runs = make_tools()

    llm = FakeLLM([
        '```json\n[{"name": "Galerie Süd", "city": "Munich"}]\n```',  # extract_organizations (only LLM call)
    ])

    agent = create_research_agent(
        llm=llm,
        web_search=web_search,
        geo_search=geo_search,
        fetch_page=_no_page,
        save_organization=save_organization,
        start_run=start_run,
        finish_run=finish_run,
        mission=DummyMission(),
    )

    result = agent.invoke({"city": "Munich", "industry": "gallery"})

    assert len(result["saved_ids"]) == 1
    assert result["errors"] == []


class TestGoogleHostFilter:
    """fetch_pages skips Google's own result pages. The check used to be
    url.startswith("https://www.google"), which a look-alike host clears."""

    def test_real_google_hosts_are_skipped(self):
        for url in ("https://www.google.com/search?q=x", "https://google.com/", "https://maps.google.com/x"):
            assert nodes._is_google_host(url) is True

    def test_lookalike_hosts_are_not_skipped(self):
        for url in ("https://www.google.evil.test/", "https://notgoogle.com/", "https://evil.test/?u=https://www.google"):
            assert nodes._is_google_host(url) is False
