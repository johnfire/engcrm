"""Unit tests for the company research dossier module — domain policy, URL safety,
candidate ranking, and page classification. Tests are network-free and DB-free."""

import pytest

from gcrm.research.dossier import (
    _classify_page_type,
    _extract_domain,
    _page_priority,
    _DIRECTORY_DOMAINS,
    should_crawl,
    verify_domain,
)


class TestExtractDomain:
    def test_simple_domain(self):
        assert _extract_domain("https://example.com/about") == "example.com"

    def test_strips_www(self):
        assert _extract_domain("https://www.example.com") == "example.com"

    def test_subdomain_kept(self):
        assert _extract_domain("https://blog.example.com") == "blog.example.com"

    def test_no_scheme(self):
        assert _extract_domain("example.com/contact") == "example.com"

    def test_invalid_url_returns_none(self):
        assert _extract_domain("not a url") is None


class TestShouldCrawl:
    def test_same_domain_allowed(self):
        assert should_crawl("https://example.com/about", "example.com") is True

    def test_different_domain_blocked(self):
        assert should_crawl("https://other.com/page", "example.com") is False

    def test_www_variant_is_same_domain(self):
        assert should_crawl("https://www.example.com/team", "example.com") is True

    def test_image_skipped(self):
        assert should_crawl("https://example.com/logo.png", "example.com") is False

    def test_pdf_skipped(self):
        assert should_crawl("https://example.com/brochure.pdf", "example.com") is False

    def test_css_skipped(self):
        assert should_crawl("https://example.com/style.css", "example.com") is False

    def test_mailto_skipped(self):
        assert should_crawl("mailto:info@example.com", "example.com") is False

    def test_subdomain_blocked(self):
        # Non-www subdomain != base domain — blocked.
        assert should_crawl("https://shop.example.com/products", "example.com") is False

    def test_fragment_handled(self):
        # Fragment is ignored; the URL is valid.
        assert should_crawl("https://example.com/about#team", "example.com") is True

    def test_loopback_blocked(self):
        assert should_crawl("http://127.0.0.1/admin", "127.0.0.1") is False


class TestPagePriority:
    def test_homepage_highest(self):
        assert _page_priority("/") < _page_priority("/about")

    def test_about_before_contact(self):
        assert _page_priority("/about") < _page_priority("/contact")

    def test_services_before_news(self):
        assert _page_priority("/services") < _page_priority("/news")

    def test_unknown_path_lowest(self):
        assert _page_priority("/some-random-page") > _page_priority("/contact")

    def test_trailing_slash_ignored(self):
        assert _page_priority("/about/") == _page_priority("/about")

    def test_german_paths_recognized(self):
        assert _page_priority("/ueber-uns") == _page_priority("/about")
        assert _page_priority("/impressum") == _page_priority("/imprint")


class TestClassifyPageType:
    def test_homepage(self):
        assert _classify_page_type("https://example.com/") == "homepage"
        assert _classify_page_type("https://example.com/index") == "homepage"

    def test_about(self):
        assert _classify_page_type("https://example.com/about") == "about"
        assert _classify_page_type("https://example.com/ueber-uns") == "about"
        assert _classify_page_type("https://example.com/team") == "about"

    def test_contact(self):
        assert _classify_page_type("https://example.com/contact") == "contact"
        assert _classify_page_type("https://example.com/kontakt") == "contact"

    def test_imprint(self):
        assert _classify_page_type("https://example.com/impressum") == "imprint"

    def test_services(self):
        assert _classify_page_type("https://example.com/leistungen") == "services"
        assert _classify_page_type("https://example.com/portfolio") == "services"

    def test_news(self):
        assert _classify_page_type("https://example.com/news") == "news"
        assert _classify_page_type("https://example.com/blog") == "news"

    def test_other(self):
        assert _classify_page_type("https://example.com/random") == "other"


class TestVerifyDomain:
    def test_google_places_wins(self):
        candidates = [
            {"url": "https://real-company.com", "source": "google_places", "title": "Real Company"},
            {"url": "https://directory.com/real-company", "source": "web_search", "title": "Real Company on Directory"},
        ]
        assert verify_domain(candidates, "Real Company") == "real-company.com"

    def test_name_match_in_title_wins(self):
        candidates = [
            {"url": "https://random-site.com", "source": "web_search", "title": "Random Stuff"},
            {"url": "https://real-company.com", "source": "web_search", "title": "Real Company — Official Website"},
        ]
        assert verify_domain(candidates, "Real Company") == "real-company.com"

    def test_directories_filtered_out(self):
        candidates = [
            {"url": "https://facebook.com/realcompany", "source": "web_search", "title": "Real Company"},
            {"url": "https://real-company.com", "source": "web_search", "title": "Some Page"},
        ]
        # Facebook is filtered; falls through to the non-directory URL.
        assert verify_domain(candidates, "Real Company") == "real-company.com"

    def test_all_directories_returns_none(self):
        candidates = [
            {"url": "https://linkedin.com/company/real", "source": "web_search", "title": "Real"},
            {"url": "https://gelbeseiten.de/real", "source": "web_search", "title": "Real"},
        ]
        assert verify_domain(candidates, "Real Company") is None

    def test_empty_candidates_returns_none(self):
        assert verify_domain([], "Anything") is None

    def test_no_urls_returns_none(self):
        candidates = [
            {"source": "web_search", "title": "Just a title, no URL"},
        ]
        assert verify_domain(candidates, "Company") is None
