"""Same-origin guarantee for every 303 the web UI issues.

The case that motivated gcrm/api/redirects.py: /contacts/{id}/delete used to
redirect to the raw Referer header, so a phishing page could POST at us and
bounce the logged-in admin onto a look-alike login screen.
"""
import pytest

from gcrm.api.redirects import local_path, local_redirect


@pytest.mark.parametrize("candidate", [
    "https://evil.test/login",       # absolute URL
    "http://evil.test",
    "//evil.test/login",             # protocol-relative
    "/\\evil.test/login",            # browsers normalize the backslash to //
    "//",
    "contacts/",                     # relative — resolves against the current page
    "javascript:alert(1)",
    "",
])
def test_off_origin_targets_fall_back(candidate):
    assert local_path(candidate, "/contacts/") == "/contacts/"


@pytest.mark.parametrize("candidate,expected", [
    ("/contacts/", "/contacts/"),
    ("/contacts/42", "/contacts/42"),
    ("/contacts/?page=2&sort=name", "/contacts/?page=2&sort=name"),
    ("/research/?city=M%C3%BCnchen", "/research/?city=M%C3%BCnchen"),
])
def test_in_app_paths_pass_through(candidate, expected):
    assert local_path(candidate, "/") == expected


def test_params_are_encoded_onto_the_query_string():
    response = local_redirect("/research/", queried="scout", city="Bad Tölz")
    assert response.headers["location"] == "/research/?queried=scout&city=Bad+T%C3%B6lz"
    assert response.status_code == 303


def test_param_cannot_escape_the_query_string():
    """A city of "x&admin=1" must stay one value, not smuggle a second param."""
    response = local_redirect("/research/", city="x&admin=1#frag")
    assert response.headers["location"] == "/research/?city=x%26admin%3D1%23frag"


def test_param_cannot_redirect_off_origin():
    response = local_redirect("/research/", city="//evil.test")
    assert response.headers["location"].startswith("/research/?")
    assert "//evil.test" not in response.headers["location"]


def test_off_origin_path_with_params_still_falls_back():
    response = local_redirect("https://evil.test/x", fallback="/contacts/", saved="1")
    assert response.headers["location"] == "/contacts/?saved=1"
