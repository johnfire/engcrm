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
    top_level_nav = re.sub(r'<div class="nav-dropdown-links">.*?</div>', "", nav, flags=re.S)
    return [
        label.strip()
        for label in re.findall(r">\s*([^<>]+?)\s*</(?:a|summary)>", top_level_nav)
    ]


def active_labels(nav):
    return [label.strip() for label in re.findall(r'class="active"[^>]*>\s*([^<>]+?)\s*<', nav)]


def menu_markup(nav, menu):
    return re.search(rf'<details class="nav-dropdown nav-{menu}">(.*?)</details>', nav, re.S).group(1)


def link_labels(nav):
    return [label.strip() for label in re.findall(r">\s*([^<>]+?)\s*</a>", nav)]


@pytest.mark.parametrize("path,expected", [
    ("/approvals/", "Approvals"),
    ("/drafts/", "Drafts"),
    ("/inbox/3", "Inbox"),
    # /approvals/dropped/ matches the Approvals prefix too; the more specific
    # tab has to win, or both light up.
    ("/approvals/dropped/", "Dropped"),
    ("/organizations/", "Organizations"),
    ("/organizations/1", "Organizations"),
    ("/people/3", "People"),
    ("/users/", "Users"),
    ("/settings", "Settings"),
    ("/activity/", "Activity"),
    ("/help/", "Help"),
    ("/impressum", "Impressum"),
    ("/privacy", "Privacy"),
])
def test_exactly_one_tab_is_active_and_it_is_the_most_specific(path, expected):
    assert active_labels(render_nav(path)) == [expected]


def test_no_tab_is_active_off_the_navigable_pages():
    assert active_labels(render_nav("/")) == []


def test_top_level_tabs_are_alphabetical_and_grouped():
    labels = tab_labels(render_nav("/organizations/"))
    assert labels == [
        "Admin", "Areas", "Contacts", "Mail", "Organizations", "People", "Research", "Statistics"
    ]
    assert labels == sorted(labels)


def test_tabs_are_alphabetical_in_german_too():
    """Sorting the English labels would leave German in English order."""
    labels = tab_labels(render_nav("/organizations/", language="de"))
    assert labels == sorted(labels)


def test_users_link_stays_admin_only_and_admin_menu_remains_available():
    for role in ("admin", "spectator"):
        nav = render_nav("/organizations/", role=role)
        assert ("Users" in link_labels(menu_markup(nav, "admin"))) is (role == "admin")
        assert "Users" not in tab_labels(nav)
        assert "Admin" in tab_labels(nav)


@pytest.mark.parametrize("language", ["en", "de"])
def test_mail_groups_the_three_links_in_the_requested_order(language):
    nav = render_nav("/organizations/", language=language)
    mail_links = menu_markup(nav, "mail")
    assert re.findall(r'href="([^"]+)"', mail_links) == ["/approvals/", "/drafts/", "/inbox/"]
    assert link_labels(mail_links) == [
        translate(f"nav.{key}", language) for key in ("approvals", "drafts", "inbox")
    ]
    assert "Mail" in tab_labels(nav)
    mail_labels = {translate(f"nav.{key}", language) for key in ("approvals", "drafts", "inbox")}
    assert not mail_labels & set(tab_labels(nav))
    assert '<details class="nav-dropdown nav-mail">' in nav


@pytest.mark.parametrize("language", ["en", "de"])
@pytest.mark.parametrize("role", ["admin", "spectator"])
def test_admin_groups_the_requested_links_in_order(language, role):
    nav = render_nav("/organizations/", language=language, role=role)
    admin_menu = menu_markup(nav, "admin")
    keys = ["activity", "dropped", "help", "offers", "settings"]
    hrefs = ["/activity/", "/approvals/dropped/", "/help/", "/offers/", "/settings"]
    if role == "admin":
        keys.append("users")
        hrefs.append("/users/")
    keys.extend(["impressum", "privacy"])
    hrefs.extend(["/impressum", "/privacy"])
    expected_labels = [translate(f"nav.{key}", language) for key in keys]
    assert link_labels(admin_menu) == expected_labels
    assert re.findall(r'href="([^"]+)"', admin_menu) == hrefs
    assert not set(expected_labels) & set(tab_labels(nav))


@pytest.mark.parametrize("path,is_mail_active", [
    ("/approvals/", True),
    ("/drafts/1", True),
    ("/inbox/", True),
    ("/approvals/dropped/", False),
    ("/people/", False),
])
def test_mail_highlights_only_for_its_own_pages(path, is_mail_active):
    nav = render_nav(path)
    mail_menu = menu_markup(nav, "mail")
    assert ('class="nav-dropdown-active"' in mail_menu) is is_mail_active
    assert ('aria-current="page"' in mail_menu) is is_mail_active


@pytest.mark.parametrize("path", [
    "/activity/", "/approvals/dropped/", "/help/", "/settings", "/users/", "/impressum", "/privacy"
])
def test_admin_highlights_for_all_its_pages_without_highlighting_mail(path):
    nav = render_nav(path)
    assert 'class="nav-dropdown-active"' in menu_markup(nav, "admin")
    assert 'aria-current="page"' in menu_markup(nav, "admin")
    assert 'class="nav-dropdown-active"' not in menu_markup(nav, "mail")


@pytest.mark.parametrize("path", ["/approvals/", "/drafts/", "/inbox/", "/people/", "/"])
def test_admin_is_not_highlighted_on_other_pages(path):
    assert 'class="nav-dropdown-active"' not in menu_markup(render_nav(path), "admin")
