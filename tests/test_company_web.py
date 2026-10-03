"""Finding a company's website and address from its name: site ranking, page
parsing, address extraction and the lookup that ties them together. Search and
fetching are injected fakes — no network."""
import pytest

from gcrm.company_web import (
    Address,
    WebResult,
    address_in_text,
    contact_urls,
    domain_extra,
    find_addresses,
    is_directory,
    llm_prompt,
    lookup_company,
    name_on_page,
    parse_llm_address,
    parse_page,
    rank_sites,
    registrable_host,
    search_with_retry,
)
from gcrm.linkedin import normalize_company


def hit(url, title="", snippet=""):
    return {"url": url, "title": title, "snippet": snippet}


class TestSites:
    def test_registrable_host(self):
        assert registrable_host("https://de.wikipedia.org/wiki/X") == "wikipedia.org"
        assert registrable_host("https://www.acme.de/impressum") == "acme.de"
        assert registrable_host("https://shop.acme.co.uk/") == "acme.co.uk"

    def test_directories_and_social_sites_are_never_the_company(self):
        for url in ("https://www.linkedin.com/company/x", "https://de.wikipedia.org/wiki/X",
                    "https://www.northdata.de/x", "https://web2.cylex.de/firma"):
            assert is_directory(url)
        assert not is_directory("https://www.fintiba.com/")

    def test_the_tightest_domain_wins(self):
        key = normalize_company("IHK Schwaben")
        assert domain_extra("https://www.ihk.de/schwaben/", key) == 0
        assert domain_extra("https://www.ihk-akademie-schwaben.de", key) == 8
        ranked = rank_sites([hit("https://www.ihk-akademie-schwaben.de/x"),
                             hit("https://www.ihk.de/schwaben/service")], key)
        assert ranked[0]["host"] == "ihk.de"

    def test_a_site_that_lacks_the_name_does_not_match(self):
        assert domain_extra("https://grokipedia.com/page", normalize_company("Stadt Augsburg")) is None

    def test_words_like_stadt_need_not_be_in_the_domain_but_the_name_words_must(self):
        key = normalize_company("Stadt Augsburg")
        assert domain_extra("https://www.augsburg.de/", key) is not None
        assert domain_extra("https://www.augsburg.de/", key, strict=True) is None  # 'stadt' missing

    def test_directories_are_dropped_from_the_ranking(self):
        ranked = rank_sites([hit("https://www.linkedin.com/company/fintiba"),
                             hit("https://fintiba.com/de/about")], normalize_company("Fintiba GmbH"))
        assert [s["host"] for s in ranked] == ["fintiba.com"]


class TestPages:
    HTML = """<html><head><style>.x{}</style><script>var a=1;</script></head><body>
      <nav><a href="/impressum">Impressum</a> <a href="/produkte">Produkte</a>
      <a href="mailto:a@b.de">Mail</a> <a href="#top">Top</a></nav>
      <p>Acme GmbH</p><div>Hauptstraße 5<br>86150 Augsburg</div></body></html>"""

    def test_text_drops_scripts_and_styles_and_links_are_absolute(self):
        text, links = parse_page(self.HTML, "https://acme.de/")
        assert "var a" not in text and ".x" not in text
        assert "86150 Augsburg" in text and "Hauptstraße 5" in text
        assert ("https://acme.de/impressum", "Impressum") in links
        assert all(not url.startswith(("mailto:", "#")) for url, _ in links)

    def test_malformed_html_does_not_raise(self):
        assert parse_page("<div><<a href=", "https://x.de/")[0] is not None

    def test_contact_pages_are_found_in_order_then_guessed(self):
        links = [("https://acme.de/produkte", "Produkte"), ("https://acme.de/kontakt", "Kontakt"),
                 ("https://acme.de/impressum", "Impressum"), ("https://other.de/impressum", "Impressum")]
        urls = contact_urls("https://acme.de/", links, ["https://acme.de/de/impressum"])
        assert urls[0] == "https://acme.de/de/impressum"  # the search already returned it
        assert urls.index("https://acme.de/impressum") < urls.index("https://acme.de/kontakt")
        assert "https://other.de/impressum" not in urls  # another site
        assert "https://acme.de/imprint" in urls  # conventional guess


class TestAddresses:
    def test_german_address_with_the_street_on_the_same_line(self):
        [address] = find_addresses("Acme GmbH\nHauptstraße 5, 86150 Augsburg\nTelefon 0821 123", "acme.de")
        assert address == Address("Hauptstraße 5", "86150", "Augsburg", "DE")

    def test_street_on_the_line_above_the_town(self):
        [address] = find_addresses("Universitätsstraße 2\n86159 Augsburg\nDeutschland", "uni.de")
        assert (address.street, address.postal_code, address.city) == ("Universitätsstraße 2", "86159", "Augsburg")

    def test_trailing_labels_are_not_part_of_the_town(self):
        [address] = find_addresses("Börsenplatz 4, 60313 Frankfurt am Main Telefon: 069 1", "x.com")
        assert address.city == "Frankfurt am Main"

    def test_a_copyright_year_is_not_a_postal_code(self):
        """Regression: '© 2026 Fintiba. Alle Rechte vorbehalten' was read as an address."""
        assert find_addresses("© 2026 Fintiba. Alle Rechte vorbehalten", "fintiba.com") == []
        assert find_addresses("Copyright 2026 Fintiba Alle Rechte", "fintiba.at") == []

    def test_four_digit_codes_need_austrian_or_swiss_evidence(self):
        assert find_addresses("Im Jahr 2024 Wien wuchs die Firma", "acme.com") == []
        [address] = find_addresses("Ringstraße 1, 1010 Wien", "acme.at")
        assert (address.postal_code, address.country) == ("1010", "AT")

    def test_the_country_is_only_named_with_evidence(self):
        [bare] = find_addresses("Rue de la Paix 3, 75002 Paris", "acme.com")
        assert bare.country == ""  # five digits are also French
        [german] = find_addresses("Hauptstraße 5, 86150 Augsburg\nUSt-IdNr. DE123456789", "acme.com")
        assert german.country == "DE"
        [by_text] = find_addresses("Hauptstraße 5, 86150 Augsburg\nDeutschland", "acme.com")
        assert by_text.country == "DE"

    def test_no_stray_punctuation_after_the_town(self):
        [address] = find_addresses("Börsenplatz 4, 60313 Frankfurt am Main. Alle Angaben", "x.de")
        assert address.city == "Frankfurt am Main"

    def test_a_german_language_impressum_establishes_germany(self):
        [address] = find_addresses("Impressum\nAsklepios Kliniken GmbH\nRübenkamp 226, 22307 Hamburg", "asklepios.com")
        assert address.country == "DE"
        [french] = find_addresses("Mentions légales\nAcme SA, 3 Rue de la Paix, 75002 Paris", "acme.com")
        assert french.country == ""

    def test_the_most_repeated_address_with_a_street_comes_first(self):
        text = "Postfach 12345 Berlin\nHauptstraße 5, 86150 Augsburg\nHauptstraße 5, 86150 Augsburg"
        assert find_addresses(text, "a.de")[0].city == "Augsburg"

    def test_verification_requires_the_address_on_the_page(self):
        text = "Hauptstraße 5, 86150 Augsburg"
        assert address_in_text(Address("", "86150", "Augsburg", "DE"), text)
        assert not address_in_text(Address("", "80331", "München", "DE"), text)


class TestLlmFallback:
    PAGE = "Acme Ltd, 12 High Street, Reading RG1 1AA, United Kingdom"

    def test_a_well_formed_answer_found_on_the_page_is_kept(self):
        raw = '{"street": "12 High Street", "postal_code": "RG1 1AA", "city": "Reading", "country": "gb"}'
        assert parse_llm_address(raw, self.PAGE) == Address("12 High Street", "RG1 1AA", "Reading", "GB")

    def test_an_invented_address_is_discarded(self):
        raw = '{"street": "1 Fake Rd", "postal_code": "ZZ9 9ZZ", "city": "Gotham", "country": "GB"}'
        assert parse_llm_address(raw, self.PAGE) is None

    @pytest.mark.parametrize("raw", ["", "no json", '{"city": null, "postal_code": null}', "{broken"])
    def test_garbage_is_discarded(self, raw):
        assert parse_llm_address(raw, self.PAGE) is None

    def test_the_prompt_forbids_guessing_and_people(self):
        system, user = llm_prompt("Acme", "page")
        assert "Never guess" in system and "individual people" in system and "Acme" in user


class TestSearchRetry:
    def test_a_flaky_empty_answer_is_retried(self):
        answers = iter([[], [], [hit("https://a.de")]])
        sleeps = []
        assert search_with_retry(lambda q: next(answers), "x", sleeps.append) == [hit("https://a.de")]
        assert len(sleeps) == 2

    def test_it_gives_up_after_the_retries(self):
        calls = []
        assert search_with_retry(lambda q: calls.append(q) or [], "x", lambda s: None) == []
        assert len(calls) == 3


HOME = "<html><body>" + "Willkommen bei Acme. " * 20 + '<a href="/impressum">Impressum</a></body></html>'
IMPRESSUM = ("<html><body><h1>Impressum</h1>Acme GmbH<br>Hauptstraße 5<br>86150 Augsburg<br>"
             "Amtsgericht Augsburg HRB 123 " + "Text. " * 40 + "</body></html>")


def fake_web(pages):
    def fetch(url):
        for known, html in pages.items():
            if url.rstrip("/") == known.rstrip("/"):
                return known, html
        return "", ""
    return fetch


def no_sleep(_):
    return None


class TestLookupCompany:
    def search_for(self, results):
        return lambda query: results

    def test_resolves_website_and_address(self):
        result = lookup_company(
            "Acme GmbH", self.search_for([hit("https://www.linkedin.com/company/acme"), hit("https://acme.de/")]),
            fake_web({"https://acme.de/": HOME, "https://acme.de/impressum": IMPRESSUM}), sleep=no_sleep)
        assert result.outcome == "resolved"
        assert result.website == "https://acme.de/"
        assert result.address == Address("Hauptstraße 5", "86150", "Augsburg", "DE")
        assert result.source_url == "https://acme.de/impressum"

    def test_nothing_found_is_not_found(self):
        result = lookup_company("Acme GmbH", self.search_for([]), fake_web({}), sleep=no_sleep)
        assert result.outcome == "not_found" and result.searched is False

    def test_only_directories_found_is_not_found(self):
        result = lookup_company("Acme GmbH", self.search_for([hit("https://www.xing.com/pages/acme")]),
                                fake_web({}), sleep=no_sleep)
        assert result.outcome == "not_found"

    def test_an_unreadable_site_goes_to_review_with_the_website_kept(self):
        result = lookup_company("Acme GmbH", self.search_for([hit("https://acme.de/")]),
                                fake_web({}), sleep=no_sleep)
        assert result.outcome == "needs_review" and result.website == "https://acme.de/"

    def test_a_site_without_the_company_name_is_not_trusted(self):
        """A plausible address on someone else's site must not be accepted."""
        other = IMPRESSUM.replace("Acme GmbH", "Somebody Else GmbH")
        result = lookup_company("Acme GmbH", self.search_for([hit("https://random-portal.de/")]),
                                fake_web({"https://random-portal.de/": HOME,
                                          "https://random-portal.de/impressum": other}), sleep=no_sleep)
        assert result.outcome == "needs_review"
        assert "does not carry the company name" in result.reason

    def test_the_name_on_the_page_can_vouch_for_a_site_whose_domain_does_not(self):
        result = lookup_company(
            "Acme GmbH", self.search_for([hit("https://acme-holding-group.de/")]),
            fake_web({"https://acme-holding-group.de/": HOME,
                      "https://acme-holding-group.de/impressum": IMPRESSUM}), sleep=no_sleep)
        assert result.outcome == "resolved"

    def test_an_unknown_country_goes_to_review(self):
        french = IMPRESSUM.replace("Amtsgericht Augsburg HRB 123", "").replace(
            "Hauptstraße 5<br>86150 Augsburg", "3 Rue de la Paix<br>75002 Paris")
        result = lookup_company("Acme GmbH", self.search_for([hit("https://acme.com/")]),
                                fake_web({"https://acme.com/": HOME, "https://acme.com/impressum": french}),
                                sleep=no_sleep)
        assert result.outcome == "needs_review" and "country" in result.reason
        assert result.address.city == "Paris"  # the reading is kept for the human

    def test_two_trusted_sites_with_different_addresses_go_to_review(self):
        munich = IMPRESSUM.replace("86150 Augsburg", "80331 München")
        result = lookup_company(
            "Acme GmbH", self.search_for([hit("https://acme.de/"), hit("https://acme.com/")]),
            fake_web({"https://acme.de/": HOME, "https://acme.de/impressum": IMPRESSUM,
                      "https://acme.com/": HOME, "https://acme.com/impressum": munich}), sleep=no_sleep)
        assert result.outcome == "needs_review" and "different addresses" in result.reason

    def test_two_sites_with_the_same_address_are_fine(self):
        result = lookup_company(
            "Acme GmbH", self.search_for([hit("https://acme.de/"), hit("https://acme.com/")]),
            fake_web({"https://acme.de/": HOME, "https://acme.de/impressum": IMPRESSUM,
                      "https://acme.com/": HOME, "https://acme.com/impressum": IMPRESSUM}), sleep=no_sleep)
        assert result.outcome == "resolved"

    def test_the_llm_fallback_reads_non_german_pages_but_only_what_is_on_the_page(self):
        english = ("<html><body>Acme Ltd " + "About us. " * 30 +
                   "Registered office: 12 High Street, Reading RG1 1AA, United Kingdom</body></html>")

        def llm(name, text):
            return parse_llm_address(
                '{"street":"12 High Street","postal_code":"RG1 1AA","city":"Reading","country":"GB"}', text)
        result = lookup_company("Acme Ltd", self.search_for([hit("https://acme.co.uk/")]),
                                fake_web({"https://acme.co.uk/": english}), llm_address=llm, sleep=no_sleep)
        assert result.outcome == "resolved" and result.address.city == "Reading"

    def test_candidates_are_always_kept_for_the_review_page(self):
        result = lookup_company("Acme GmbH", self.search_for([hit("https://acme.de/")]),
                                fake_web({}), sleep=no_sleep)
        assert result.candidates and result.candidates[0]["website"] == "https://acme.de/"

    def test_a_blank_name_never_searches(self):
        def boom(query):
            raise AssertionError("must not search")
        assert lookup_company("Self-employed", boom, fake_web({}), sleep=no_sleep).outcome == "not_found"

    def test_a_failing_search_or_fetch_never_raises(self):
        def bad_search(query):
            return []
        assert isinstance(lookup_company("Acme GmbH", bad_search, fake_web({}), sleep=no_sleep), WebResult)


class TestNameOnPage:
    def test_the_whole_name_must_appear(self):
        key = normalize_company("Helios Kliniken GmbH")
        assert name_on_page(key, "Helios Kliniken GmbH, Friedrichstraße 136")
        assert not name_on_page(key, "Kliniken in ganz Deutschland. Helios ist toll.")  # words, not the name


class TestWebsiteRoot:
    def test_a_company_that_lives_under_a_path_keeps_it(self):
        from gcrm.company_web import _site_root
        key = normalize_company("IHK Schwaben")
        assert _site_root("https://www.ihk.de/schwaben/service", "https://www.ihk.de/", key) == \
            "https://ihk.de/schwaben/"

    def test_an_ordinary_site_is_just_the_host(self):
        from gcrm.company_web import _site_root
        key = normalize_company("Fintiba GmbH")
        assert _site_root("https://fintiba.com/de/about", "https://fintiba.com/", key) == "https://fintiba.com/"


class TestWebsiteRootSubdomain:
    def test_a_portal_subdomain_is_stored_as_the_main_site(self):
        from gcrm.company_web import _site_root
        key = normalize_company("Technische Hochschule Augsburg")
        assert _site_root("https://hisinone.hs-augsburg.de/qis", "https://hisinone.hs-augsburg.de/",
                          key) == "https://hs-augsburg.de/"


class TestAuthoritativePages:
    def test_the_impressum_wins_over_a_different_address_in_the_homepage_footer(self):
        """Regression: Fintiba came back with a different address on a different run,
        depending on which page was read first."""
        home = ("<html><body>" + "Willkommen bei Acme. " * 20 +
                "<footer>Acme Büro Börsenplatz 4, 60313 Frankfurt am Main</footer>"
                '<a href="/impressum">Impressum</a></body></html>')
        result = lookup_company(
            "Acme GmbH", lambda q: [hit("https://acme.de/")],
            fake_web({"https://acme.de/": home, "https://acme.de/impressum": IMPRESSUM}), sleep=no_sleep)
        assert result.outcome == "resolved"
        assert result.address.city == "Augsburg" and result.source_url == "https://acme.de/impressum"


class TestSiteConflicts:
    def test_a_site_named_after_the_company_beats_one_that_only_mentions_it(self):
        munich = IMPRESSUM.replace("86150 Augsburg", "80331 München")
        result = lookup_company(
            "Acme GmbH", lambda q: [hit("https://acme-portal.de/"), hit("https://acme.de/")],
            fake_web({"https://acme.de/": HOME, "https://acme.de/impressum": IMPRESSUM,
                      "https://acme-portal.de/": HOME, "https://acme-portal.de/impressum": munich}),
            sleep=no_sleep)
        assert result.outcome == "resolved" and result.address.city == "Augsburg"

    def test_the_surplus_count_ignores_words_the_domain_need_not_carry(self):
        """Regression: 'hs-augsburg' scored as a perfect match for 'Technische Hochschule Augsburg'."""
        key = normalize_company("Technische Hochschule Augsburg")
        assert domain_extra("https://www.hs-augsburg.de/", key) == 2  # 'hs' is surplus
        assert domain_extra("https://www.augsburg.de/", key) == 0


class TestSearchOutage:
    def test_a_search_that_never_answers_is_not_recorded_as_not_found(self):
        result = lookup_company("Acme GmbH", lambda q: [], fake_web({}), sleep=no_sleep)
        assert result.outcome == "not_found" and result.searched is False

    def test_an_answer_with_only_directories_is_a_real_not_found(self):
        result = lookup_company("Acme GmbH", lambda q: [hit("https://www.xing.com/pages/acme")],
                                fake_web({}), sleep=no_sleep)
        assert result.outcome == "not_found" and result.searched is True


class TestAcronymsAndNames:
    def test_an_acronym_domain_matches_a_long_name(self):
        key = normalize_company("KfH Kuratorium für Dialyse und Nierentransplantation e.V.")
        assert domain_extra("https://www.kfh.de/", key) == 0
        assert domain_extra("https://www.nature.com/", key) is None

    def test_an_acronym_only_counts_when_it_is_the_whole_domain(self):
        key = normalize_company("ABB Ltd")
        assert domain_extra("https://abb.com/", key) == 0
        assert domain_extra("https://abbott.com/", key, strict=True) is None

    def test_the_name_check_ignores_und_and_legal_forms_in_the_page(self):
        key = normalize_company("KfH Kuratorium für Dialyse und Nierentransplantation e.V.")
        page = "Impressum KfH Kuratorium für Dialyse und Nierentransplantation e.V. Martin-Behaim-Str. 20"
        assert name_on_page(key, page)
        assert not name_on_page(key, "Dialyse und Nierentransplantation Kuratorium")  # wrong order

    def test_a_third_site_is_read_only_when_the_first_two_failed(self):
        pages = {"https://acme-ccc.de/": HOME, "https://acme-ccc.de/impressum": IMPRESSUM}
        result = lookup_company(
            "Acme GmbH", lambda q: [hit("https://acme-aaa.de/"), hit("https://acme-bbb.de/"),
                                    hit("https://acme-ccc.de/")], fake_web(pages), sleep=no_sleep)
        assert result.outcome == "resolved" and result.website == "https://acme-ccc.de/"


class TestPrecision:
    """Wrong answers found by running the lookup on real companies."""

    def test_a_long_unrelated_domain_is_not_rescued_by_a_path_segment(self):
        """Regression: 'Stadt Augsburg' was resolved from historicgermany.com/augsburg."""
        key = normalize_company("Stadt Augsburg")
        assert domain_extra("https://historicgermany.com/augsburg", key) is None
        assert domain_extra("https://www.augsburg.de/", key) == 0

    def test_a_short_domain_may_be_completed_by_its_path(self):
        assert domain_extra("https://www.ihk.de/schwaben/", normalize_company("IHK Schwaben")) == 0

    def test_a_name_mentioned_on_an_ordinary_page_does_not_vouch_for_an_address(self):
        article = ("<html><body><h1>Augsburg erleben</h1>" + "Reisetipps für die Stadt Augsburg. " * 15 +
                   "Besuchen Sie uns: Schießgrabenstraße 14, 86150 Augsburg</body></html>")
        result = lookup_company(
            "Stadt Augsburg", lambda q: [hit("https://travel-tips.com/augsburg")],
            fake_web({"https://travel-tips.com/augsburg": article}), sleep=no_sleep)
        assert result.outcome != "resolved"

    def test_contact_pages_are_recognised_by_address_or_heading(self):
        from gcrm.company_web import is_contact_page
        assert is_contact_page("https://a.de/impressum", "x")
        assert is_contact_page("https://a.de/p/42", "Kontakt\nAcme GmbH")
        assert not is_contact_page("https://a.de/blog/augsburg", "Reisetipps " * 40)


class TestPrecisionFromRealRuns:
    def test_a_report_title_is_not_an_austrian_address(self):
        """Regression: Accenture resolved to '2025 Gartner Magic Quadrant, AT' because the
        page mentioned Austria somewhere else."""
        text = "Accenture ist in Austria aktiv.\nGartner: 2025 Gartner Magic Quadrant für Cloud"
        assert find_addresses(text, "accenture.com") == []

    def test_a_four_digit_code_is_fine_with_the_country_on_the_same_line(self):
        [a] = find_addresses("Ringstraße 1, A-1010 Wien", "acme.com")
        assert (a.postal_code, a.country) == ("1010", "AT")
        [b] = find_addresses("Bahnhofplatz 14, 8021 Zürich, Schweiz", "ameos.eu")
        assert (b.postal_code, b.country) == ("8021", "CH")

    def test_an_umbrella_bodys_address_is_not_an_institutes_address(self):
        """Regression: 'Fraunhofer IIS' resolved to the society's Munich head office, because
        its Impressum names many institutes."""
        impressum = ("<html><body><h1>Impressum</h1>Herausgeber: Fraunhofer-Gesellschaft e.V.<br>"
                     "Hansastraße 27 c<br>80686 München<br>Amtsgericht München VR 4461<br>" +
                     "Institute: Fraunhofer IIS, Fraunhofer IAO, Fraunhofer IPA. " * 12 + "</body></html>")
        result = lookup_company(
            "Fraunhofer IIS", lambda q: [hit("https://fraunhofer.de/")],
            fake_web({"https://fraunhofer.de/": HOME, "https://fraunhofer.de/impressum": impressum}),
            sleep=no_sleep)
        assert result.outcome != "resolved"

    def test_the_name_beside_the_address_is_what_counts(self):
        from gcrm.company_web import name_near_address
        text = "Acme GmbH, Hauptstraße 5, 86150 Augsburg. " + "x " * 400 + "Other GmbH 80331 München"
        assert name_near_address(normalize_company("Acme GmbH"), text, Address("", "86150", "Augsburg", "DE"))
        assert not name_near_address(normalize_company("Acme GmbH"), text, Address("", "80331", "München", "DE"))

    def test_a_homepage_footer_without_a_street_is_not_an_address(self):
        home = ("<html><body>" + "Willkommen bei Acme. " * 20 + "<footer>86150 Augsburg</footer></body></html>")
        result = lookup_company("Acme GmbH", lambda q: [hit("https://acme.de/")],
                                fake_web({"https://acme.de/": home}), sleep=no_sleep)
        assert result.outcome != "resolved"


class TestFromTheRandomSample:
    def test_directories_are_recognised_by_what_they_call_themselves(self):
        """Regression: Dussmann resolved from firmendata.com, a listing site."""
        for url in ("https://firmendata.com/x", "https://www.branchenbuch24.de/y",
                    "https://zaubacorp.com/company/z", "https://www.unternehmensverzeichnis.org/"):
            assert is_directory(url)
        assert not is_directory("https://www.dussmann.com/")
        assert not is_directory("https://masea.de/")

    def test_a_country_glued_onto_the_town_is_removed(self):
        """Regression: '10117 BerlinGermany'."""
        [a] = find_addresses("Schützenstraße 25, 10117 BerlinGermany", "x.de")
        assert a.city == "Berlin"
