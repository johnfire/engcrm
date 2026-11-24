from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from gcrm.sync.conflict_resolution import (
    FieldVersion,
    is_incoming_version_newer,
    is_valid_edit_time,
)

SAVED_AT = datetime(2026, 11, 23, 10, tzinfo=UTC)
DEVICE_A = UUID(int=1)
DEVICE_B = UUID(int=2)
MUTATION_A = UUID(int=3)
MUTATION_B = UUID(int=4)


@pytest.mark.parametrize(
    ("incoming", "stored", "expected"),
    [
        (FieldVersion(SAVED_AT - timedelta(seconds=1), DEVICE_B, MUTATION_B), FieldVersion(SAVED_AT, DEVICE_A, MUTATION_A), False),
        (FieldVersion(SAVED_AT + timedelta(seconds=1), DEVICE_A, MUTATION_A), FieldVersion(SAVED_AT, DEVICE_B, MUTATION_B), True),
        (FieldVersion(SAVED_AT, DEVICE_B, MUTATION_A), FieldVersion(SAVED_AT, DEVICE_A, MUTATION_B), True),
        (FieldVersion(SAVED_AT, DEVICE_A, MUTATION_B), FieldVersion(SAVED_AT, DEVICE_B, MUTATION_A), False),
        (FieldVersion(SAVED_AT, DEVICE_A, MUTATION_B), FieldVersion(SAVED_AT, DEVICE_A, MUTATION_A), True),
        (FieldVersion(SAVED_AT, DEVICE_A, MUTATION_A), FieldVersion(SAVED_AT, DEVICE_A, MUTATION_B), False),
        (FieldVersion(SAVED_AT, DEVICE_A, MUTATION_A), FieldVersion(SAVED_AT, DEVICE_A, MUTATION_A), False),
    ],
)
def test_field_versions_are_ordered_by_edit_time_then_device_then_mutation(incoming, stored, expected):
    assert is_incoming_version_newer(incoming, stored) is expected


@pytest.mark.parametrize(
    ("edit_time", "expected"),
    [
        (SAVED_AT - timedelta(days=365), True),
        (SAVED_AT + timedelta(minutes=5), True),
        (SAVED_AT + timedelta(minutes=5, microseconds=1), False),
    ],
)
def test_edit_clock_allows_old_edits_and_at_most_five_minutes_ahead(edit_time, expected):
    assert is_valid_edit_time(edit_time, SAVED_AT) is expected


def test_naive_datetimes_are_rejected():
    with pytest.raises(ValueError):
        is_valid_edit_time(SAVED_AT.replace(tzinfo=None), SAVED_AT)
