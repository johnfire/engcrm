"""Decided 2026-11-04: the scout looks for AI-consulting buyers of 50-5,000 employees
(sweet spot 500-2,500). Shops, cafes and other non-producers are dropped without an
LLM call, contacts Chris entered himself are never judged by size, and the size band
the LLM reads off the website decides the score."""
from gcrm_scout_agent import create_scout_agent

from .test_graph import DummyMission, RecordingLLM, make_tools

SCAN_HIT = {"id": 21, "name": "Huber Maschinenbau GmbH", "city": "Augsburg",
            "type": "manufacturer", "source": "research_agent",
            "pipeline_stage": "candidate", "status": "none"}


def run_scout(candidates, llm, **options):
    fetch, update, start_run, finish_run, updates, runs = make_tools(candidates=candidates)
    agent = create_scout_agent(
        llm=llm, fetch_candidates=fetch, set_organization_state=update,
        fetch_page=lambda url: "", fetch_city_context=lambda city, country="DE": {},
        start_run=start_run, finish_run=finish_run, mission=DummyMission(), **options,
    )
    return agent.invoke({"limit": 50}), updates


def verdict(outcome: str, size_band: str, employees="null") -> str:
    return (f'{{"outcome": "{outcome}", "size_band": "{size_band}", '
            f'"employees": {employees}, "reasoning": "ok"}}')


def test_a_stated_employee_count_overrides_a_wrong_band():
    """Faist Group (2026-11-04): '4000 employees' came back as over_5000 and was dropped."""
    result, updates = run_scout([SCAN_HIT], RecordingLLM([verdict("fit", "over_5000", "4000")]))
    assert result["promoted_count"] == 1 and updates[0]["score"] == 75


def test_a_stated_count_of_30_is_too_small_whatever_the_band():
    result, updates = run_scout([SCAN_HIT], RecordingLLM([verdict("fit", "500_2500", "30")]))
    assert result["no_fit_count"] == 1


def test_the_size_band_follows_the_stated_count_at_the_edges():
    scores = {
        count: run_scout([SCAN_HIT], RecordingLLM([verdict("fit", "unknown", count)]))[1][0]["score"]
        for count in ("49", "50", "499", "500", "2500", "2501", "5000", "5001")
    }
    assert scores["49"] == scores["5001"] == 20
    assert scores["500"] == scores["2500"] == 85
    assert scores["50"] == scores["499"] == scores["2501"] == scores["5000"] == 75


def test_a_butcher_from_a_scan_is_dropped_without_asking_the_llm():
    llm = RecordingLLM([verdict("fit", "500_2500")])
    result, updates = run_scout([{**SCAN_HIT, "type": "butcher"}], llm)
    assert llm.prompts == []
    assert result["no_fit_count"] == 1
    assert (updates[0]["stage"], updates[0]["status"]) == ("not_in_pipeline", "dropped")


def test_a_scan_hit_with_any_ordinary_type_is_scored_by_the_llm():
    llm = RecordingLLM([verdict("fit", "50_499")])
    run_scout([SCAN_HIT], llm)
    assert len(llm.prompts) == 1


def test_a_business_card_contact_is_not_judged_by_size():
    llm = RecordingLLM([verdict("no_fit", "under_50")])
    result, updates = run_scout([{**SCAN_HIT, "source": "card_capture", "type": "cafe"}], llm)
    assert llm.prompts == []
    assert result["promoted_count"] == 1 and updates[0]["stage"] == "suspect"


def test_too_small_is_dropped_even_when_the_llm_likes_it():
    result, updates = run_scout([SCAN_HIT], RecordingLLM([verdict("fit", "under_50")]))
    assert result["no_fit_count"] == 1 and updates[0]["status"] == "dropped"


def test_too_large_is_dropped_even_when_the_llm_likes_it():
    result, updates = run_scout([SCAN_HIT], RecordingLLM([verdict("fit", "over_5000")]))
    assert result["no_fit_count"] == 1 and updates[0]["status"] == "dropped"


def test_the_sweet_spot_scores_higher_than_the_rest_of_the_range():
    _, sweet = run_scout([SCAN_HIT], RecordingLLM([verdict("fit", "500_2500")]))
    _, edge = run_scout([SCAN_HIT], RecordingLLM([verdict("fit", "50_499")]))
    _, unknown = run_scout([SCAN_HIT], RecordingLLM([verdict("fit", "unknown")]))
    assert sweet[0]["score"] > edge[0]["score"] > unknown[0]["score"]
    assert {sweet[0]["stage"], edge[0]["stage"], unknown[0]["stage"]} == {"suspect"}


def test_an_unknown_size_band_word_counts_as_unknown():
    _, updates = run_scout([SCAN_HIT], RecordingLLM([verdict("fit", "huge")]))
    _, unknown = run_scout([SCAN_HIT], RecordingLLM([verdict("fit", "unknown")]))
    assert updates[0]["score"] == unknown[0]["score"]


def test_the_prompt_carries_the_fit_criteria_and_asks_for_a_size_band():
    llm = RecordingLLM([verdict("fit", "500_2500")])
    run_scout([SCAN_HIT], llm)
    system, user = llm.prompts[0]
    assert DummyMission().fit_criteria in system
    assert "size_band" in user and "500_2500" in user


def test_skip_scoring_promotes_everything_unscored():
    llm = RecordingLLM([verdict("no_fit", "under_50")])
    result, _ = run_scout([SCAN_HIT, {**SCAN_HIT, "id": 22}], llm, skip_scoring=True)
    assert llm.prompts == [] and result["promoted_count"] == 2
