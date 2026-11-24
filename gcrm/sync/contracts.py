"""Validated boundary models for mobile synchronization."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DeviceRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: UUID
    server_environment: Literal["production", "reviewer"]
    app_version: str = Field(min_length=1, max_length=100)
    schema_version: int = Field(ge=0, le=2147483647)


class DeviceRegistrationResponse(BaseModel):
    protocol_version: int = 1
    bootstrap_required: bool = True
