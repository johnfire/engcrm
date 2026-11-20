"""Every sort the mobile app offers is one the backend actually honours.

The org and people endpoints fall back to "newest" for a sort key they do not know,
so a typo or a drifted key would not fail: the list would just quietly not sort.
This reads the app's option lists and checks each key against the backend's own."""
import re
from pathlib import Path

import pytest

from gcrm.api.routers.api_organizations import DEAL_SORTS
from gcrm.api.routers.api_organizations import SORT_COLUMNS as ORGANIZATION_COLUMNS
from gcrm.tools.db_contact_feed import SORT_COLUMNS as FEED_COLUMNS
from gcrm.tools.db_people import SORT_COLUMNS as PEOPLE_COLUMNS

OPTIONS_FILE = Path(__file__).parent.parent / "engcrm-mobile" / "services" / "listSortOptions.ts"


def offered(list_name: str) -> list[str]:
    source = OPTIONS_FILE.read_text()
    block = re.search(rf"export const {list_name}\b.*?= \[(.*?)\n\];", source, re.S).group(1)
    return re.findall(r'key: "(\w+)"', block)


@pytest.mark.parametrize("list_name,accepted", [
    ("ORGANIZATION_SORTS", {*ORGANIZATION_COLUMNS, *DEAL_SORTS}),
    ("PERSON_SORTS", {*PEOPLE_COLUMNS, "pipeline_stage", "status"}),
    ("CONTACT_SORTS", set(FEED_COLUMNS)),
])
def test_every_offered_sort_is_known_to_the_backend(list_name, accepted):
    keys = offered(list_name)
    assert keys, f"found no sort options for {list_name}"
    assert [key for key in keys if key not in accepted] == []


@pytest.mark.parametrize("list_name", ["ORGANIZATION_SORTS", "PERSON_SORTS", "CONTACT_SORTS"])
def test_each_list_can_sort_by_status_and_stage(list_name):
    assert {"status", "pipeline_stage"} <= set(offered(list_name))
