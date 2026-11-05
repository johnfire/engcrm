"""Gather (plan 2026-11-05): research, then enrichment and the people finder on exactly the
companies research just saved. A failing step never stops the next one from working on
what was found, and nothing runs when research found nothing new."""
from gcrm.supervisor.run_gather import gather


def recorder(calls, name, result=None, error=None):
    def step(*args):
        calls.append((name, *args))
        if error:
            raise error
        return result
    return step


def test_enrichment_and_people_get_only_the_ids_research_saved():
    calls = []
    outcome = gather(recorder(calls, "research", [11, 12]),
                     enrich=recorder(calls, "enrich", "2 enriched"),
                     find_people=recorder(calls, "people", "3 people"))
    assert calls == [("research",), ("enrich", [11, 12]), ("people", [11, 12])]
    assert outcome["saved_ids"] == [11, 12] and outcome["errors"] == []
    assert outcome["summaries"] == {"enrichment": "2 enriched", "people": "3 people"}


def test_nothing_new_found_means_no_further_steps():
    calls = []
    outcome = gather(recorder(calls, "research", []),
                     enrich=recorder(calls, "enrich"), find_people=recorder(calls, "people"))
    assert calls == [("research",)] and outcome["saved_ids"] == []


def test_a_failing_enrichment_does_not_stop_the_people_finder():
    calls = []
    outcome = gather(recorder(calls, "research", [7]),
                     enrich=recorder(calls, "enrich", error=RuntimeError("search down")),
                     find_people=recorder(calls, "people", "1 person"))
    assert ("people", [7]) in calls
    assert outcome["errors"] == ["enrichment failed: search down"]


def test_a_failing_research_is_reported_and_stops_the_run():
    calls = []
    outcome = gather(recorder(calls, "research", error=RuntimeError("maps quota")),
                     enrich=recorder(calls, "enrich"), find_people=recorder(calls, "people"))
    assert calls == [("research",)]
    assert outcome["errors"] == ["research failed: maps quota"] and outcome["saved_ids"] == []
