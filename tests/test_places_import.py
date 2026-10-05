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


COPIED = """Share
WBS TRAINING Augsburg
WBS TRAINING Augsburg
4.8(59)
Adult education school ·  · Bahnhofstraße 17
Open · Closes 4:15 pm · 0821 2480980

Website


Directions
beINsure - unabhängige Finanzberatung
Sponsored

beINsure - unabhängige Finanzberatung
5.0(146)
Financial Advisor · 14 Ulrichsplatz
Open · Closes 6 pm · 0821 24257888

Website
Visit Site
Berufsfachschule für Kosmetik Gebauer Augsburg
Berufsfachschule für Kosmetik Gebauer Augsburg
5.0(30)
Beauty school · Volkhartstraße 2
0821 39868

Website
Cloud Command GmbH
Cloud Command GmbH
5.0(7)
Education center · Prinzregentenstraße 1

Website
beINsure - unabhängige Finanzberatung
Sponsored

beINsure - unabhängige Finanzberatung
"""


def test_a_copied_maps_list_is_read_card_by_card():
    entries = places_import.parse_maps_copy(COPIED)

    assert [(e["name"], e["category"], e["street"], e["phone"], e["sponsored"]) for e in entries] == [
        ("WBS TRAINING Augsburg", "Adult education school", "Bahnhofstraße 17", "0821 2480980", False),
        ("beINsure - unabhängige Finanzberatung", "Financial Advisor", "14 Ulrichsplatz", "0821 24257888", True),
        ("Berufsfachschule für Kosmetik Gebauer Augsburg", "Beauty school", "Volkhartstraße 2", "0821 39868", False),
        ("Cloud Command GmbH", "Education center", "Prinzregentenstraße 1", "", False),
    ]


def test_phone_numbers_compare_in_national_form():
    assert places_import.phone_digits("+49 821 2480980") == places_import.phone_digits("0821 2480980")


def test_a_copied_entry_takes_the_places_record_with_the_same_phone():
    entry = {"name": "WBS TRAINING Augsburg", "street": "Bahnhofstraße 17", "phone": "0821 2480980"}
    other = {**_result("WBS Somewhere"), "phone": "0821 999"}
    same = {**_result("WBS Training AG", town="Augsburg"), "phone": "+49 821 2480980"}

    org = places_import.match_copied_entry(entry, "Augsburg", lookup=lambda *a, **k: [other, same])

    assert org["matched"] and org["name"] == "WBS TRAINING Augsburg"
    assert org["website"] == "https://bib.example" and org["google"]["phone"] == "+49 821 2480980"


def test_without_a_phone_match_the_copy_alone_is_saved():
    entry = {"name": "Cloud Command GmbH", "street": "Prinzregentenstraße 1", "phone": ""}

    org = places_import.match_copied_entry(entry, "Augsburg", lookup=lambda *a, **k: [_result("Cloud Command")])

    assert not org["matched"] and org["google"] is None
    assert (org["city"], org["address"], org["website"]) == ("Augsburg", "Prinzregentenstraße 1", "")
