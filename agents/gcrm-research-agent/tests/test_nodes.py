"""fetch_missing_emails: homepage-first, then a short list of contact subpaths."""
from types import SimpleNamespace

from gcrm_research_agent import nodes


def _dependencies(pages: dict[str, str]):
    calls = []

    def fetch_page(url: str) -> str:
        calls.append(url)
        return pages.get(url, "")

    return SimpleNamespace(fetch_page=fetch_page), calls


def test_finds_email_on_homepage_without_trying_subpaths():
    dependencies, calls = _dependencies({"https://example-org.de": "Reach us at info@example-org.de"})
    state = {"city": "Munich", "organizations_to_save": [{"name": "Org", "website": "https://example-org.de"}]}

    result = nodes.fetch_missing_emails(state, dependencies)

    assert result["organizations_to_save"][0]["email"] == "info@example-org.de"
    assert calls == ["https://example-org.de"]


def test_falls_back_to_kontakt_page_when_homepage_has_no_email():
    dependencies, calls = _dependencies({
        "https://example-org.de": "Welcome to our site, no address here",
        "https://example-org.de/kontakt": "Kontakt: buero@example-org.de",
    })
    state = {"city": "Munich", "organizations_to_save": [{"name": "Org", "website": "https://example-org.de"}]}

    result = nodes.fetch_missing_emails(state, dependencies)

    org = result["organizations_to_save"][0]
    assert org["email"] == "buero@example-org.de"
    assert "_no_data" not in org
    assert calls == ["https://example-org.de", "https://example-org.de/kontakt"]


def test_flags_no_data_when_no_subpath_has_a_usable_email():
    dependencies, calls = _dependencies({"https://example-org.de": "Nothing to find here"})
    state = {"city": "Munich", "organizations_to_save": [{"name": "Org", "website": "https://example-org.de"}]}

    result = nodes.fetch_missing_emails(state, dependencies)

    org = result["organizations_to_save"][0]
    assert org.get("email") is None
    assert org["_no_data"] is True
    assert calls == [
        "https://example-org.de",
        "https://example-org.de/kontakt",
        "https://example-org.de/contact",
        "https://example-org.de/impressum",
        "https://example-org.de/about",
    ]


def test_skips_noise_domain_email_and_keeps_trying_subpaths():
    dependencies, calls = _dependencies({
        "https://example-org.de": "Built with Wix, support@wixpress.com",
        "https://example-org.de/impressum": "Verantwortlich: chef@example-org.de",
    })
    state = {"city": "Munich", "organizations_to_save": [{"name": "Org", "website": "https://example-org.de"}]}

    result = nodes.fetch_missing_emails(state, dependencies)

    assert result["organizations_to_save"][0]["email"] == "chef@example-org.de"


def test_no_website_is_flagged_without_fetching():
    dependencies, calls = _dependencies({})
    state = {"city": "Munich", "organizations_to_save": [{"name": "Org", "website": ""}]}

    result = nodes.fetch_missing_emails(state, dependencies)

    assert result["organizations_to_save"][0]["_no_data"] is True
    assert calls == []
