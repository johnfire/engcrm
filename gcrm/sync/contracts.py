"""Validated boundary models for mobile synchronization."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DeviceRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: UUID
    server_environment: Literal["production", "reviewer"]
    app_version: str = Field(min_length=1, max_length=100)
    schema_version: int = Field(ge=0, le=2147483647)


class DeviceRegistrationResponse(BaseModel):
    protocol_version: int = 1
    bootstrap_required: bool = True


class SyncUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mutation_id: UUID
    device_id: UUID
    entity_kind: Literal["organization", "person", "deal"]
    entity_sync_id: UUID
    operation: Literal["update"]
    changed_at: datetime
    patch: dict[str, Any] = Field(min_length=1, max_length=30)

    @field_validator("changed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("changed_at must include a timezone")
        return value


class SyncPushBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    server_environment: Literal["production", "reviewer"] = "production"
    mutations: list[Any] = Field(min_length=1, max_length=100)


class ReviewOutcomeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: UUID
    server_environment: Literal["production", "reviewer"] = "production"
    mutation_ids: list[UUID] = Field(min_length=1, max_length=100)


class SyncCreate(SyncUpdate):
    entity_kind: Literal["organization", "person", "deal", "person_note", "organization_activity"]
    operation: Literal["create"]
