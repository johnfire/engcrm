"""Turning a Google Maps search into organizations."""
from unittest.mock import patch

from gcrm.tools import places_import
from gcrm.tools.places_import import to_organization


def _result(name="BIB Augsburg GmbH", town="Augsburg", status="OPERATIONAL"):
    components = [{"types": ["country"], "longText": "Germany", "shortText": "DE"}]
    if town:
        components.append({"types": ["locality"], "longText": town, "shortText": town})
    return {"name": name, "city": "Augsburg", "country": "DE", "address": f"Hauptstr. 1, {town}",
            "website": "https://bib.example", "phone": "0821 1", "business_status": status,
            "google_data": {"displayName": {"text": name}, "addressComponents": components}}


def test_a_place_is_filed_under_the_town_it_is_in_not_the_one_searched():
    org = to_organization(_result(town="Königsbrunn"))
    assert (org["name"], org["city"], org["country"]) == ("BIB Augsburg GmbH", "Königsbrunn", "DE")


def test_without_a_town_in_the_address_the_searched_town_is_used():
    assert to_organization(_result(town=None))["city"] == "Augsburg"


def test_permanently_closed_places_are_skipped():
    assert to_organization(_result(status="CLOSED_PERMANENTLY")) is None


def test_duplicates_are_reported_not_saved_twice():
    orgs = [to_organization(_result("A")), to_organization(_result("B"))]
    with patch.object(places_import, "save_organization", side_effect=[41, 0]) as save:
        result = places_import.add_organizations(orgs, type="Weiterbildung", note="Found by search.")
    assert result == {"created": [41], "duplicates": ["B"]}
    kwargs = save.call_args_list[0].kwargs
    assert kwargs["type"] == "Weiterbildung" and kwargs["notes"].startswith("Found by search.")
    assert kwargs["google"]["business_status"] == "OPERATIONAL"
