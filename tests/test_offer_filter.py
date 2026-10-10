"""Which offer a list shows: remembered on the web, Consulting by default on the phone."""
import pytest
from starlette.requests import Request

from gcrm.api.offer_filter import api_offer_filter, web_offer_filter


def request(session=None):
    return Request({"type": "http", "session": session if session is not None else {}})


def test_the_web_starts_on_every_offer_and_remembers_a_choice():
    browser = request()
    assert web_offer_filter(browser, None)[0] is None
    assert web_offer_filter(browser, "learnwohl")[0] == "learnwohl"
    assert web_offer_filter(browser, None)[0] == "learnwohl"  # still there on the next page
    assert web_offer_filter(browser, "all")[0] is None
    assert web_offer_filter(browser, None)[0] is None


def test_an_unknown_offer_falls_back_to_every_offer():
    assert web_offer_filter(request(), "'; DROP TABLE deals; --")[0] is None
    assert web_offer_filter(request({"offer_filter": "gone"}), None)[0] is None


def test_the_picker_lists_active_offers():
    _, offers = web_offer_filter(request(), None)
    assert [o["slug"] for o in offers] == ["consulting", "learnwohl", "leguild", "notes-world"]


def test_the_phone_gets_consulting_unless_it_asks():
    assert api_offer_filter(None, None) == "consulting"
    assert api_offer_filter("", None) == "consulting"
    assert api_offer_filter("all", None) is None
    assert api_offer_filter("leguild", None) == "leguild"
    with pytest.raises(ValueError):
        api_offer_filter("bogus", None)
