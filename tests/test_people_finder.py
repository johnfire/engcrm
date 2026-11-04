"""Decided 2026-11-04: for each company the scout rated ready, find up to three
decision-makers from web search (never from LinkedIn itself), then look for each
one's public LinkedIn or XING profile by web search. A person with no public profile
is kept and marked as such, so Chris can look them up by hand."""
import json

from gcrm.people_finder import find_people, is_decision_maker, pick_profile, profile_url

FAIST = {"id": 5, "name": "Faist Systeme GmbH", "city": "Untermeitingen", "country": "DE",
         "website": "https://www.faist.de"}


def hit(url, title="", snippet=""):
    return {"url": url, "title": title, "snippet": snippet}


def test_decision_maker_roles_are_recognised_in_german_and_english():
    for role in ("Geschäftsführer", "Geschäftsführerin", "CEO", "Inhaber", "Produktionsleiter",
                 "Head of IT", "Werkleiter", "Leiter Digitalisierung", "Managing Director", "Prokurist"):
        assert is_decision_maker(role), role
    for role in ("Financial & HR Manager", "Entrepreneur", "Werkstudent", "", None):
        assert not is_decision_maker(role), role


def test_profile_urls_are_people_pages_only():
    assert profile_url("https://de.linkedin.com/in/anwar-amir-123?trk=x") == (
        "linkedin", "https://www.linkedin.com/in/anwar-amir-123")
    assert profile_url("https://www.xing.com/profile/Anwar_Amir081717/cv") == (
        "xing", "https://www.xing.com/profile/Anwar_Amir081717")
    for url in ("https://www.linkedin.com/company/faist", "https://www.xing.com/pages/faist", "https://faist.de"):
        assert profile_url(url) is None


def test_a_profile_is_picked_only_when_it_names_the_person_and_the_company():
    results = [
        hit("https://www.linkedin.com/in/anwar-amir-9", "Anwar Amir – Produktionsleiter – ACME AG"),
        hit("https://www.xing.com/profile/Anwar_Amir081717", "Anwar Amir - Produktionsleiter - Faist Systeme Gmb",
            "Faist Systeme GmbH Verantwortung für technische Projekte"),
    ]
    assert pick_profile("Anwar Amir", "Faist Systeme GmbH", results) == (
        "xing", "https://www.xing.com/profile/Anwar_Amir081717")
    assert pick_profile("Anna Amir", "Faist Systeme GmbH", results) is None


class Fakes:
    """Web search answers by query; the LLM returns the people JSON it is given."""

    def __init__(self, people, results_by_word):
        self.people, self.results_by_word, self.queries, self.fetched = people, results_by_word, [], []

    def search(self, query):
        self.queries.append(query)
        return next((results for word, results in self.results_by_word.items() if word in query), [])

    def fetch_page(self, url):
        self.fetched.append(url)
        return "Impressum. Geschäftsführer: Dr. Klaus Faist, Maria Huber. Untermeitingen."

    def extract(self, system, user):
        return json.dumps(self.people)


def run(people, results_by_word):
    fakes = Fakes(people, results_by_word)
    found = find_people(FAIST, search=fakes.search, fetch_page=fakes.fetch_page, extract=fakes.extract)
    return found, fakes


def test_decision_makers_named_on_the_impressum_are_kept_with_their_role():
    found, _ = run([{"name": "Klaus Faist", "role": "Geschäftsführer"}], {})
    assert [(person["name"], person["role"]) for person in found] == [("Klaus Faist", "Geschäftsführer")]


def test_a_name_that_appears_nowhere_in_the_sources_is_dropped():
    found, _ = run([{"name": "Peter Erfunden", "role": "CEO"}], {})
    assert found == []


def test_people_without_a_decision_making_role_are_dropped():
    found, _ = run([{"name": "Maria Huber", "role": "Assistenz"}], {})
    assert found == []


def test_each_person_gets_a_profile_search_and_a_found_profile_is_kept():
    profile = hit("https://de.linkedin.com/in/klaus-faist", "Klaus Faist - Geschäftsführer - Faist Systeme GmbH")
    found, fakes = run([{"name": "Klaus Faist", "role": "Geschäftsführer"}], {'"Klaus Faist"': [profile]})
    assert found[0]["linkedin_url"] == "https://www.linkedin.com/in/klaus-faist"
    assert any('"Klaus Faist"' in query and "LinkedIn" in query for query in fakes.queries)


def test_no_public_profile_is_reported_as_none_not_guessed():
    found, _ = run([{"name": "Klaus Faist", "role": "Geschäftsführer"}], {})
    assert found[0]["linkedin_url"] is None and found[0]["xing_url"] is None


def test_profiles_in_the_company_search_become_people_directly():
    profile = hit("https://www.xing.com/profile/Anwar_Amir081717",
                  "Anwar Amir - Produktionsleiter - Faist Systeme Gmb", "Faist Systeme GmbH")
    found, _ = run([], {"LinkedIn XING": [profile]})
    assert [(person["name"], person["role"], person["xing_url"]) for person in found] == [
        ("Anwar Amir", "Produktionsleiter", "https://www.xing.com/profile/Anwar_Amir081717")]


def test_at_most_three_people_per_company_with_the_top_role_first():
    people = [{"name": "Maria Huber", "role": "Leiterin Einkauf"},
              {"name": "Klaus Faist", "role": "Geschäftsführer"}]
    sources = {"LinkedIn XING": [
        hit("https://www.linkedin.com/in/anna-berg-1", "Anna Berg - Werkleiterin - Faist Systeme GmbH"),
        hit("https://www.linkedin.com/in/bernd-ott", "Bernd Ott - Head of IT - Faist Systeme GmbH"),
    ]}
    found, _ = run(people, sources)
    assert len(found) == 3 and found[0]["name"] == "Klaus Faist"


def test_a_failing_search_or_llm_gives_no_people_instead_of_an_error():
    def broken(*args, **kwargs):
        raise RuntimeError("down")

    assert find_people(FAIST, search=broken, fetch_page=broken, extract=broken) == []


def test_a_profile_whose_link_belongs_to_someone_else_is_not_used():
    """Live 2026-11-04: a result titled 'Jan Oehler …' linked to Stefan Stark's profile."""
    mixed = hit("https://www.xing.com/profile/Stefan_Stark32", "XINGJan Oehler - Werkleiter - Faist Systeme GmbH")
    found, _ = run([], {"LinkedIn XING": [mixed]})
    assert found == []
    assert pick_profile("Jan Oehler", "Faist Systeme GmbH", [mixed]) is None


def test_a_site_name_stuck_to_the_title_is_removed():
    profile = hit("https://www.xing.com/profile/Jan_Oehler4", "XINGJan Oehler - Werkleiter - Faist Systeme GmbH")
    found, _ = run([], {"LinkedIn XING": [profile]})
    assert [person["name"] for person in found] == ["Jan Oehler"]


def test_it_alone_is_not_a_leadership_role():
    assert not is_decision_maker("Team Leader; IT")
    assert not is_decision_maker("IT Support")
    for role in ("IT-Leiter", "Leiter IT", "Head of IT", "IT Director", "CIO"):
        assert is_decision_maker(role), role


def test_an_empty_quoted_search_is_retried_without_quotes():
    fakes = Fakes([], {})
    find_people(FAIST, search=fakes.search, fetch_page=fakes.fetch_page, extract=fakes.extract)
    company_queries = [query for query in fakes.queries if "Faist Systeme GmbH" in query]
    assert any(query.startswith('"Faist Systeme GmbH"') for query in company_queries)
    assert any(query.startswith("Faist Systeme GmbH") for query in company_queries)
