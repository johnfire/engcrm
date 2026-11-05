"""Turning CRM rows into items for the browser pin loop (scripts/maps/pin_loop.js). A
company with coordinates is matched by distance; one without is matched by address, so
the item carries the postcode, the website's host and the city instead."""
from gcrm.map_pin_items import loop_item, postcode, site_host


def test_the_postcode_is_read_from_a_german_address():
    assert postcode("Siemensstraße 21, 86836 Untermeitingen") == "86836"
    assert postcode("Siemensstraße 21, Untermeitingen") is None
    assert postcode(None) is None


def test_the_site_host_drops_the_scheme_and_www():
    assert site_host("https://www.faistgroup.com/de/kontakt") == "faistgroup.com"
    assert site_host("meile-gruppe.de") == "meile-gruppe.de"
    assert site_host("") is None


def test_a_company_with_coordinates_is_matched_by_distance():
    row = {"id": 5, "name": "Meile GmbH", "city": "Untermeitingen", "latitude": 48.16, "longitude": 10.8,
           "address": "Siemensstraße 21, 86836 Untermeitingen", "website": "http://www.meile-gruppe.de"}
    assert loop_item(row) == {"id": 5, "name": "Meile GmbH", "city": "Untermeitingen", "lat": 48.16, "lon": 10.8}


def test_a_company_without_coordinates_is_matched_by_address():
    row = {"id": 6, "name": "Faist Systeme GmbH", "city": "Untermeitingen", "latitude": None, "longitude": None,
           "address": "Daimlerstraße 3, 86836 Untermeitingen", "website": "http://www.faistgroup.com"}
    assert loop_item(row) == {"id": 6, "name": "Faist Systeme GmbH", "city": "Untermeitingen",
                              "addr": "Daimlerstraße 3, 86836 Untermeitingen", "plz": "86836",
                              "site": "faistgroup.com"}


def test_empty_address_parts_are_left_out_not_sent_as_blanks():
    row = {"id": 7, "name": "Ghost GmbH", "city": "", "latitude": None, "longitude": None,
           "address": "", "website": ""}
    assert loop_item(row) == {"id": 7, "name": "Ghost GmbH", "addr": ""}
