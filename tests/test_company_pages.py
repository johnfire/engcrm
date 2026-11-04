"""Decided 2026-11-04: a company's LinkedIn and XING pages are kept, never thrown away
like directory links. Only company pages count (not people), found from web-search
results, and only when the company's own name is on the result — a wrong page is
worse than none."""
from gcrm.company_pages import company_page_url, pick_company_pages


def test_linkedin_company_pages_are_recognised_and_tidied():
    assert company_page_url("https://de.linkedin.com/company/faist-group?trk=x") == (
        "linkedin", "https://www.linkedin.com/company/faist-group/")
    assert company_page_url("http://linkedin.com/company/meile-gmbh/about/") == (
        "linkedin", "https://www.linkedin.com/company/meile-gmbh/")


def test_xing_company_pages_are_recognised_in_both_url_styles():
    assert company_page_url("https://www.xing.com/pages/faist-systeme-gmbh") == (
        "xing", "https://www.xing.com/pages/faist-systeme-gmbh")
    assert company_page_url("https://www.xing.com/companies/meilegmbh/updates") == (
        "xing", "https://www.xing.com/pages/meilegmbh")


def test_people_jobs_and_other_sites_are_not_company_pages():
    for url in ("https://www.linkedin.com/in/max-mustermann", "https://www.linkedin.com/jobs/view/1",
                "https://www.xing.com/profile/Max_Mustermann", "https://www.linkedin.com/company/",
                "https://faist.de/company/history", "not a url", ""):
        assert company_page_url(url) is None


def result(url, title="", snippet=""):
    return {"url": url, "title": title, "snippet": snippet}


def test_pages_whose_name_matches_are_picked():
    pages = pick_company_pages("Faist Systeme GmbH", [
        result("https://www.xing.com/pages/faist-systeme-gmbh", "FAIST Systeme GmbH | XING"),
        result("https://de.linkedin.com/company/faist-group", "FAIST Group | LinkedIn",
               "FAIST Systeme GmbH, Untermeitingen. 4.000 Mitarbeitende"),
    ])
    assert pages == {"linkedin_url": "https://www.linkedin.com/company/faist-group/",
                     "xing_url": "https://www.xing.com/pages/faist-systeme-gmbh"}


def test_a_page_of_another_company_with_a_shared_word_is_not_picked():
    pages = pick_company_pages("Huber Maschinenbau GmbH", [
        result("https://www.linkedin.com/company/huber-se", "HUBER SE | LinkedIn", "Wasseraufbereitung"),
    ])
    assert pages == {}


def test_the_first_matching_page_per_network_wins():
    pages = pick_company_pages("Meile GmbH", [
        result("https://www.linkedin.com/company/meile-gmbh", "Meile GmbH | LinkedIn"),
        result("https://www.linkedin.com/company/meile-gruppe", "Meile Gruppe | LinkedIn"),
    ])
    assert pages == {"linkedin_url": "https://www.linkedin.com/company/meile-gmbh/"}


def test_a_name_with_nothing_distinctive_never_matches():
    assert pick_company_pages("GmbH", [result("https://www.linkedin.com/company/gmbh", "GmbH")]) == {}
