"""Judge (plan 2026-11-05): the scout, then opportunity analysis, then the list of companies
the scout has dropped that are still pinned on the Maps list. Started by hand only; one
step failing never stops the next."""
from gcrm.supervisor.run_judge import judge, summary_line


def step(calls, name, result=None, error=None):
    def run():
        calls.append(name)
        if error:
            raise error
        return result
    return run


def test_scout_then_opportunity_then_the_pinned_dropped_list():
    calls = []
    outcome = judge(step(calls, "scout", "scout: 5 promoted"), step(calls, "opportunity", "3 analysed"),
                    step(calls, "pins", [{"id": 9, "name": "Auto Frey GmbH"}]))
    assert calls == ["scout", "opportunity", "pins"]
    assert outcome["summaries"] == {"scout": "scout: 5 promoted", "opportunity": "3 analysed"}
    assert outcome["dropped_on_map"] == [{"id": 9, "name": "Auto Frey GmbH"}] and outcome["errors"] == []


def test_a_failing_scout_still_lets_ready_companies_be_analysed():
    calls = []
    outcome = judge(step(calls, "scout", error=RuntimeError("llm down")), step(calls, "opportunity", "1"),
                    step(calls, "pins", []))
    assert calls == ["scout", "opportunity", "pins"]
    assert outcome["errors"] == ["scout failed: llm down"]


def test_the_summary_names_the_dropped_companies_still_on_the_map():
    outcome = {"summaries": {"scout": "s", "opportunity": "o"}, "errors": [],
               "dropped_on_map": [{"id": 9, "name": "Auto Frey GmbH"}, {"id": 12, "name": "Action"}]}
    line = summary_line(outcome)
    assert "2 dropped but still on your map: Auto Frey GmbH #9, Action #12" in line


def test_a_long_dropped_list_is_shortened_in_the_summary():
    outcome = {"summaries": {}, "errors": [],
               "dropped_on_map": [{"id": number, "name": f"Firma {number}"} for number in range(30)]}
    line = summary_line(outcome)
    assert "30 dropped but still on your map" in line and "and 20 more" in line
