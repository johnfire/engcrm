"""Decided 2026-11-04: engcrm scans only for AI-consulting buyers (Mittelstand, 50-5,000
employees). Nothing art-related is searched for, and the research step labels every hit
from one fixed list of types that the scout and the save step both understand."""
import re

from gcrm.prompts.research import extract_organizations_prompt
from gcrm.vertical import (
    BUYER_TYPES,
    FIT_CRITERIA,
    FIT_SIGNALS,
    NOT_A_BUYER_TYPES,
    SCAN_LEVELS,
    SIZE_RULE,
)

ART_WORDS = re.compile(r"galerie|gallery|\bkunst\b|atelier|artist|künstler|interior|coworking", re.IGNORECASE)


def test_there_are_ten_levels_and_each_searches_for_something():
    assert sorted(SCAN_LEVELS) == list(range(1, 11))
    assert all(info["maps_terms"] for info in SCAN_LEVELS.values())


def test_no_level_searches_for_anything_art_related():
    terms = [term for info in SCAN_LEVELS.values() for term in [info["label"], *info["maps_terms"]]]
    assert [term for term in terms if ART_WORDS.search(term)] == []


def test_small_shops_and_services_are_not_buyer_types():
    for shop in ("butcher", "bakery", "supermarket", "cafe", "restaurant", "gas_station",
                 "landmark", "car_dealer", "car_repair", "locksmith", "discount_store", "gallery"):
        assert shop in NOT_A_BUYER_TYPES and shop not in BUYER_TYPES


def test_the_size_rule_names_the_range_and_sweet_spot():
    assert "50 to 5,000" in SIZE_RULE and "500 to 2,500" in SIZE_RULE


def test_the_scout_text_carries_no_size_threshold_for_the_llm_to_misapply():
    """Faist Group (2026-11-04): with '5,000' in its criteria, the LLM called 4,000 employees too many."""
    scout_text = " ".join([FIT_CRITERIA, *FIT_SIGNALS])
    assert "5,000" not in scout_text and "2,500" not in scout_text


def test_the_research_notes_are_told_the_size_rule():
    class Mission:
        identity, goal, fit_criteria = "me", "goal", "criteria"

    _, user = extract_organizations_prompt(Mission(), "Augsburg", [2], [])
    assert SIZE_RULE in user


def test_the_research_prompt_offers_exactly_the_known_types():
    class Mission:
        identity, goal, fit_criteria = "me", "goal", "criteria"

    _, user = extract_organizations_prompt(Mission(), "Augsburg", [2], [])
    for type_label in (*BUYER_TYPES, *NOT_A_BUYER_TYPES):
        assert type_label in user
    assert "gallery/restaurant/hotel/cafe" not in user
