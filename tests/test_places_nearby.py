"""places_nearby: Google Places Nearby Search for field mode. httpx is mocked, so no
request leaves the machine; the response below has the shape Places (New) returns."""
from unittest.mock import MagicMock, patch

import httpx
import pytest

from gcrm.tools.search import PlacesUnavailable, places_nearby

HERE = (48.0478, 10.8768)  # a street in Landsberg

RESPONSE = {"places": [
    {"id": "ChIJbakery", "displayName": {"text": "Bäckerei Maier"},
     "formattedAddress": "Hauptplatz 12, 86899 Landsberg am Lech",
     "addressComponents": [{"longText": "Landsberg am Lech", "types": ["locality", "political"]},
                           {"longText": "Deutschland", "shortText": "DE", "types": ["country"]}],
     "location": {"latitude": 48.04785, "longitude": 10.87690},
     "primaryType": "bakery", "primaryTypeDisplayName": {"text": "Bäckerei"}, "businessStatus": "OPERATIONAL"},
    {"id": "ChIJoptician", "displayName": {"text": "Optik Huber"},
     "formattedAddress": "Hauptplatz 14, 86899 Landsberg am Lech",
     "location": {"latitude": 48.04800, "longitude": 10.87720}, "primaryType": "store"},
    {"id": "ChIJgone", "displayName": {"text": "Closed Café"}, "businessStatus": "CLOSED_PERMANENTLY",
     "location": {"latitude": 48.0478, "longitude": 10.8768}},
]}


def call(response=None, raises=None, key="test-key", **kwargs):
    reply = MagicMock()
    reply.json.return_value = response if response is not None else RESPONSE
    reply.raise_for_status.return_value = None
    with patch("gcrm.config.GOOGLE_MAPS_API_KEY", key), \
         patch("gcrm.tools.search.httpx.post", return_value=reply, side_effect=raises) as post:
        return places_nearby(*HERE, **kwargs), post


def test_lists_what_is_here_nearest_first_with_distance_and_type():
    results, post = call()
    assert [r["name"] for r in results] == ["Bäckerei Maier", "Optik Huber"]  # the closed one is left out
    bakery = results[0]
    assert bakery == {"name": "Bäckerei Maier", "place_id": "ChIJbakery",
                      "address": "Hauptplatz 12, 86899 Landsberg am Lech", "city": "Landsberg am Lech",
                      "country": "DE", "type": "Bäckerei", "latitude": 48.04785, "longitude": 10.8769,
                      "distance_m": 9}
    # 0.0002° north (22.2 m) and 0.0004° east (29.7 m at this latitude): about 37 m.
    assert results[1]["type"] == "store" and results[1]["distance_m"] == 37


def test_asks_by_distance_within_the_radius_and_only_pro_tier_fields():
    _, post = call(radius_m=80, max_results=5)
    body, headers = post.call_args.kwargs["json"], post.call_args.kwargs["headers"]
    assert body["rankPreference"] == "DISTANCE" and body["maxResultCount"] == 5
    assert body["locationRestriction"]["circle"] == {"center": {"latitude": HERE[0], "longitude": HERE[1]},
                                                     "radius": 80.0}
    # Phone and website would make every call an Enterprise one.
    assert "websiteUri" not in headers["X-Goog-FieldMask"] and "PhoneNumber" not in headers["X-Goog-FieldMask"]
    assert post.call_args.args[0].endswith("places:searchNearby")


def test_nothing_here_is_an_empty_list_but_a_failure_is_an_error():
    assert call(response={})[0] == []
    with pytest.raises(PlacesUnavailable):
        call(raises=httpx.ConnectError("no network"))
    with pytest.raises(PlacesUnavailable):
        call(key="")
