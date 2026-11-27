"""What may be typed into a contract: title, assignment, links. No database."""
import pytest

from gcrm.contract_input import (
    ASSIGNMENT_MAX,
    LABEL_MAX,
    TITLE_MAX,
    URL_MAX,
    ContractInputError,
    checked_assignment,
    checked_link,
    checked_title,
)


def test_a_title_is_trimmed_and_may_be_up_to_200_characters():
    assert checked_title("  Year course  ") == "Year course"
    assert checked_title("x" * TITLE_MAX) == "x" * TITLE_MAX


@pytest.mark.parametrize("value", ["", "   ", None, "x" * (TITLE_MAX + 1)])
def test_a_blank_or_overlong_title_is_refused_with_a_message_key(value):
    with pytest.raises(ContractInputError) as refused:
        checked_title(value)
    assert refused.value.key == "contractPage.error.title" and isinstance(refused.value, ValueError)


def test_an_assignment_is_plain_text_with_unix_line_ends_and_may_be_blank():
    assert checked_assignment("one\r\ntwo\rthree\n") == "one\ntwo\nthree"
    assert checked_assignment(None) == "" and checked_assignment("   ") == ""
    assert checked_assignment("x" * ASSIGNMENT_MAX) == "x" * ASSIGNMENT_MAX


def test_an_assignment_over_20000_characters_is_refused():
    with pytest.raises(ContractInputError) as refused:
        checked_assignment("x" * (ASSIGNMENT_MAX + 1))
    assert refused.value.key == "contractPage.error.assignment"


def test_markup_in_an_assignment_is_kept_as_text_for_the_page_to_escape():
    assert checked_assignment("<script>alert(1)</script>") == "<script>alert(1)</script>"


@pytest.mark.parametrize("url", ["https://example.org/a", "http://example.org", "HTTP://Example.ORG/x?y=1#z",
                                 "https://sub.example.org:8443/a/b", "  https://example.org/a  "])
def test_an_http_or_https_address_is_accepted_and_trimmed(url):
    label, accepted = checked_link("  Syllabus ", url)
    assert label == "Syllabus" and accepted == url.strip()


@pytest.mark.parametrize("url", [
    "javascript:alert(1)", "JAVASCRIPT:alert(1)", " javascript:alert(1)", "java\nscript:alert(1)",
    "data:text/html,<script>alert(1)</script>", "ftp://example.org/a", "file:///etc/passwd", "mailto:a@example.org",
    "//example.org/x", "example.org", "www.example.org", "https://", "https:///x", "http://", "https:example.org",
    "http://exa mple.org", "https://example.org/a\nb", "https://example.org/\tb", "http://[::1", "",
])
def test_anything_that_is_not_an_http_address_with_a_host_is_refused(url):
    with pytest.raises(ContractInputError) as refused:
        checked_link("Label", url)
    assert refused.value.key == "contractPage.error.linkUrl"


def test_an_address_of_2001_characters_is_refused_and_2000_is_accepted():
    base = "https://example.org/"
    assert checked_link("x", base + "a" * (URL_MAX - len(base)))[1].endswith("a")
    with pytest.raises(ContractInputError) as refused:
        checked_link("x", base + "a" * (URL_MAX - len(base) + 1))
    assert refused.value.key == "contractPage.error.linkUrlLength"


@pytest.mark.parametrize("label", ["", "   ", None, "x" * (LABEL_MAX + 1)])
def test_a_blank_or_overlong_label_is_refused(label):
    with pytest.raises(ContractInputError) as refused:
        checked_link(label, "https://example.org")
    assert refused.value.key == "contractPage.error.linkLabel"
