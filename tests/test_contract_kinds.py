import pytest

from gcrm.contract_kinds import CONTRACT_KINDS, checked_kind


def test_the_kinds_are_the_four_agreed_ones():
    assert CONTRACT_KINDS == ("teaching_course", "workshop", "consulting", "other")


@pytest.mark.parametrize("kind", CONTRACT_KINDS)
def test_a_known_kind_comes_back_unchanged(kind):
    assert checked_kind(kind) == kind


@pytest.mark.parametrize("value", ["speech", "", "Workshop", None, " other"])
def test_an_unknown_kind_is_refused(value):
    with pytest.raises(ValueError):
        checked_kind(value)
