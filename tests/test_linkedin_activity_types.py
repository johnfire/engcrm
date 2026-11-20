"""The LinkedIn message is a type of work; the reply is recorded and shown but is not work."""
import pytest

from gcrm.activity_types import (
    ACTIVITY_TYPES,
    DEFAULT_MINUTES,
    ORGANIZATION_METHODS,
    PERSON_METHODS,
    REPLY_TYPE,
    activity_type,
    type_case_sql,
)


def test_a_message_is_a_work_type_with_default_minutes():
    assert activity_type("linkedin") == "linkedin" and "linkedin" in ACTIVITY_TYPES
    assert set(DEFAULT_MINUTES) == set(ACTIVITY_TYPES)          # every work type has a default


def test_a_reply_has_its_own_name_but_is_not_work():
    assert activity_type("linkedin_reply") == REPLY_TYPE == "linkedin_reply"
    assert REPLY_TYPE not in ACTIVITY_TYPES and REPLY_TYPE not in DEFAULT_MINUTES


@pytest.mark.parametrize("method", ["linkedin", "linkedin_reply"])
def test_organizations_and_people_can_both_store_them(method):
    assert method in ORGANIZATION_METHODS and method in PERSON_METHODS
    assert f"WHEN '{method}' THEN '{method}'" in type_case_sql("x")        # and statistics' SQL knows them too
