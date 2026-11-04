"""Decided 2026-11-04: a hit the research step labels as a shop or small service
(butcher, cafe, car dealer, ...) is not an AI-consulting buyer and is never saved."""
import json
from types import SimpleNamespace

from gcrm_research_agent import nodes
from langchain_core.messages import AIMessage


def extract(hits: list[dict]) -> list[dict]:
    llm = SimpleNamespace(invoke=lambda messages: AIMessage(content=json.dumps(hits)))
    mission = SimpleNamespace(identity="me", goal="goal", fit_criteria="criteria")
    state = {"city": "Augsburg", "levels": [4], "raw_results": [{"title": "x"}]}
    return nodes.extract_organizations(state, SimpleNamespace(llm=llm, mission=mission))["organizations_to_save"]


def test_shops_are_left_out_and_producers_are_kept():
    kept = extract([
        {"name": "Metzgerei Huber", "type": "butcher"},
        {"name": "Riegele Brauerei", "type": "food_producer"},
        {"name": "Aral", "type": "Gas_Station"},
    ])
    assert [hit["name"] for hit in kept] == ["Riegele Brauerei"]


def test_a_hit_without_a_type_is_kept_for_the_scout_to_judge():
    assert [hit["name"] for hit in extract([{"name": "Unbekannt GmbH"}])] == ["Unbekannt GmbH"]
