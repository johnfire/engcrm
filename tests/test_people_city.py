"""Comparing a person's city with their company's: only real differences count."""
import pytest

from gcrm.tools.people_city import city_key


@pytest.mark.parametrize("a, b", [
    ("Augsburg", "augsburg "),
    ("86150 Augsburg", "Augsburg"),
    ("Munich", "München"),
    ("Muenchen", "München"),
    ("Cologne", "Köln"),
])
def test_same_city_written_differently_matches(a, b):
    assert city_key(a) == city_key(b)


def test_different_cities_do_not_match():
    assert city_key("Augsburg") != city_key("Friedberg")


@pytest.mark.parametrize("blank", [None, "", "   ", "86150"])
def test_blank_or_postal_code_only_counts_as_no_city(blank):
    assert city_key(blank) == ""
