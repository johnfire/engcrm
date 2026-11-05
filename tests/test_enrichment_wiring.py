"""Bug found 2026-11-05: since 81117fa (2026-08-20) the enrichment agent needs a
set_suppression_flag, but the standalone runner and the supervisor built it without one,
so every enrichment run outside business-card capture crashed on start. Every caller now
uses one builder; these tests build and run it the way the runs do, with fake tools."""
import gcrm.tools as tools
from gcrm.supervisor.run_enrichment import build_enrichment_agent, enrich_ids


class FakeLLM:
    def invoke(self, messages):
        from langchain_core.messages import AIMessage
        return AIMessage(content='{"website": null, "email": null, "phone": null}')


def fake_tools(monkeypatch):
    calls = {"flags": [], "pages": [], "fetched_with": []}
    monkeypatch.setattr(tools, "get_llm", lambda model: FakeLLM())
    monkeypatch.setattr(tools, "web_search", lambda query: [])
    monkeypatch.setattr(tools, "fetch_page", lambda url: "")
    monkeypatch.setattr(tools, "update_organization_details", lambda contact_id, **values: None)
    monkeypatch.setattr(tools, "set_suppression_flag",
                        lambda contact_id, flag, value=True: calls["flags"].append((contact_id, flag)))
    monkeypatch.setattr(tools, "save_company_pages",
                        lambda contact_id, **pages: calls["pages"].append(contact_id))
    monkeypatch.setattr(tools, "start_run", lambda name, data: 1)
    monkeypatch.setattr(tools, "finish_run", lambda *args: None)

    def needing_enrichment(limit=50, city=None, ids=None):
        calls["fetched_with"].append(ids)
        return [{"id": 5, "name": "Ghost GmbH", "city": "Untermeitingen", "country": "DE", "email": ""}]

    monkeypatch.setattr(tools, "get_organizations_needing_enrichment", needing_enrichment)
    return calls


def test_the_built_agent_runs_and_can_mark_a_dead_end(monkeypatch):
    calls = fake_tools(monkeypatch)
    agent = build_enrichment_agent(tools.get_organizations_needing_enrichment)
    agent.invoke({"limit": 5})
    assert calls["flags"] == [(5, "research_exhausted")]
    assert calls["pages"] == [5]


def test_enrich_ids_works_on_exactly_the_given_companies(monkeypatch):
    calls = fake_tools(monkeypatch)
    summary = enrich_ids([5, 6])
    assert calls["fetched_with"] == [[5, 6]]
    assert "enrichment_agent" in summary
