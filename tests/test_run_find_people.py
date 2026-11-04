"""The people-finder run: every ready company is searched once, one company failing never
stops the rest, and the summary counts profiles and existing connections."""
from gcrm.supervisor.run_find_people import find_people_for_ready_companies, summary_line

COMPANIES = [{"id": 1, "name": "Meile GmbH"}, {"id": 2, "name": "Broken GmbH"}, {"id": 3, "name": "Faist"}]


def run_with(found_by_company):
    marked, saved = [], []

    def find(organization):
        found = found_by_company[organization["name"]]
        if isinstance(found, Exception):
            raise found
        return found

    def save(organization, person):
        saved.append(person["name"])
        return {"name": person["name"], "linkedin_url": person.get("linkedin_url"), "xing_url": None,
                "is_connection": person.get("known", False)}

    totals = find_people_for_ready_companies(
        10, find=find, fetch_organizations=lambda limit: COMPANIES,
        save_person_found=save, mark_searched=marked.append,
    )
    return totals, marked, saved


def test_each_company_is_marked_searched_and_a_failure_is_counted_not_fatal():
    totals, marked, saved = run_with({
        "Meile GmbH": [{"name": "Klaus Meile", "linkedin_url": "https://www.linkedin.com/in/k"}],
        "Broken GmbH": RuntimeError("search down"),
        "Faist": [{"name": "Anwar Amir", "known": True}, {"name": "Anna Berg"}],
    })
    assert marked == [1, 3]  # the broken one is retried next run
    assert saved == ["Klaus Meile", "Anwar Amir", "Anna Berg"]
    assert totals == {"companies": 2, "people": 3, "with_profile": 1, "connections": 1, "errors": 1}


def test_a_company_with_nobody_found_is_still_marked_searched():
    totals, marked, _ = run_with({"Meile GmbH": [], "Broken GmbH": [], "Faist": []})
    assert marked == [1, 2, 3] and totals["people"] == 0


def test_the_summary_names_people_profiles_and_connections():
    line = summary_line({"companies": 2, "people": 3, "with_profile": 1, "connections": 1, "errors": 1})
    assert "3 people found" in line and "1 with a public profile" in line
    assert "1 already connections" in line and "1 error" in line


def test_the_pipeline_step_reports_and_survives_a_failure(monkeypatch):
    import gcrm.supervisor.run_find_people as runner
    from gcrm.supervisor.graph import _run_find_people_node

    monkeypatch.setattr(runner, "run", lambda limit: f"people_finder: {limit} companies")
    assert _run_find_people_node({"errors": []}) == {"people_summary": "people_finder: 20 companies"}

    def broken(limit):
        raise RuntimeError("db down")

    monkeypatch.setattr(runner, "run", broken)
    result = _run_find_people_node({"errors": []})
    assert "db down" in result["people_summary"] and result["errors"] == [result["people_summary"]]
