"""Ordering rules for edits submitted by synchronized devices."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID


@dataclass(frozen=True, order=True)
class FieldVersion:
    changed_at: datetime
    device_id: UUID
    mutation_id: UUID

    def __post_init__(self) -> None:
        _require_aware(self.changed_at)


def _require_aware(timestamp: datetime) -> None:
    if timestamp.utcoffset() is None:
        raise ValueError("Sync timestamps must include a timezone")


def is_incoming_version_newer(incoming: FieldVersion, stored: FieldVersion) -> bool:
    return incoming > stored


def is_valid_edit_time(changed_at: datetime, server_time: datetime) -> bool:
    _require_aware(changed_at)
    _require_aware(server_time)
    return changed_at <= server_time + timedelta(minutes=5)
