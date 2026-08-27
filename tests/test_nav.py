"""The nav bar's ordering and active-tab rules.

Rendered straight from the template with a stub request, so these need no
database and no login — the questions here are about the template's own logic.
"""
import re
import types

import pytest

from gcrm.api.templates import templates
from gcrm.i18n import translate

TEMPLATE = templates.env.get_template("base.html")


class StubRequest:
    def __init__(self, path, role="admin", language="en"):
        self.url = types.SimpleNamespace(path=path)
        self.session = {"role": role, "ui_language": language}


def render_nav(path, role="admin", language="en"):
    html = TEMPLATE.render(
        request=StubRequest(path, role, language),
        t=lambda key, **kwargs: translate(key, language, **kwargs),
        static_version="test",
    )
    return re.search(r"<nav>(.*?)</nav>", html, re.S).group(1)


def tab_labels(nav):
    return [label.strip() for label in re.findall(r">\s*([^<>]+?)\s*</a>", nav)]


def active_labels(nav):
    return [label.strip() for label in re.findall(r'class="active">\s*([^<>]+?)\s*<', nav)]


@pytest.mark.parametrize("path,expected", [
    ("/approvals/", "Approvals"),
    # /approvals/dropped/ matches the Approvals prefix too; the more specific
    # tab has to win, or both light up.
    ("/approvals/dropped/", "Dropped"),
    ("/organizations/", "Organizations"),
    ("/organizations/1", "Organizations"),
    ("/people/3", "People"),
    ("/users/", "Users"),
    ("/settings", "Settings"),
])
def test_exactly_one_tab_is_active_and_it_is_the_most_specific(path, expected):
    assert active_labels(render_nav(path)) == [expected]


def test_no_tab_is_active_off_the_navigable_pages():
    assert active_labels(render_nav("/")) == []


def test_tabs_are_alphabetical_with_the_legal_links_pinned_last():
    labels = tab_labels(render_nav("/organizations/"))
    assert labels[-2:] == ["Impressum", "Privacy"]
    assert labels[:-2] == sorted(labels[:-2])


def test_tabs_are_alphabetical_in_german_too():
    """Sorting the English labels would leave German in English order."""
    labels = tab_labels(render_nav("/organizations/", language="de"))
    assert labels[:-2] == sorted(labels[:-2])


def test_admin_only_tab_appears_for_admins_and_sorts_into_place():
    assert "Users" in tab_labels(render_nav("/organizations/", role="admin"))
    assert "Users" not in tab_labels(render_nav("/organizations/", role="spectator"))
