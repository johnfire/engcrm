"""Validate the ordinary fields an offline device may change."""

from datetime import date

from fastapi import HTTPException
from pydantic import ValidationError

from gcrm.api.routers.api_people import PERSON_LIMITS, PersonFields
from gcrm.api.routers.api_record_edit import (
    EDITABLE_FLAGS,
    TEXT_LIMITS,
    OrganizationFields,
    clean_fields,
)
from gcrm.linkedin import normalize_linkedin_url
from gcrm.organization_state import PIPELINE_STAGES, STATUSES
from gcrm.tools.deal_records import NEXT_STEP_MAX
from gcrm.tools.follow_ups import TASK_TYPES

PERSON_FLAGS = {"is_linkedin_contact", "retention_hold"}
# The follow-up type travels with next_step: deals have no such column, and it has no field clock.
# Older apps send none, so it is always optional.
STEP_TYPE = "task_type"
DEAL_FIELDS = {"pipeline_stage", "status", "next_step", "next_step_date", STEP_TYPE}
PRIVATE_FIELDS = {"organization": {"personal_priority", "short_term_value", "long_term_value"},
                  "person": {"value_rating", "short_term_value", "long_term_value"}, "deal": set()}


def validate_sync_patch(kind: str, patch: dict) -> dict:
    private = _validate_private_fields(kind, patch)
    ordinary = {field: value for field, value in patch.items() if field not in private}
    if kind == "organization":
        return {**(_validate_contact_fields(ordinary, OrganizationFields, TEXT_LIMITS, set(EDITABLE_FLAGS), {"fit_score"}) if ordinary else {}), **private}
    if kind == "person":
        values = _validate_contact_fields(ordinary, PersonFields, PERSON_LIMITS, PERSON_FLAGS, set()) if ordinary else {}
        if values.get("linkedin_url"):
            normalized = normalize_linkedin_url(values["linkedin_url"])
            if not normalized:
                raise ValueError("linkedin_url must be a valid LinkedIn profile")
            values["linkedin_url"] = normalized
        return {**values, **private}
    if kind == "deal":
        return _validate_deal_fields(ordinary)
    raise ValueError("Unknown entity kind")


def _validate_private_fields(kind: str, patch: dict) -> dict:
    if not patch:
        raise ValueError("Unknown or empty edit fields")
    private = {field: patch[field] for field in PRIVATE_FIELDS.get(kind, set()) & patch.keys()}
    for field, value in private.items():
        maximum = 6 if field == "personal_priority" else 5 if field == "value_rating" else 3
        minimum = 1 if field in ("personal_priority", "value_rating") else 0
        if value is not None and (type(value) is not int or not minimum <= value <= maximum):
            raise ValueError("Invalid private rating")
    return private


def _validate_contact_fields(patch: dict, model, limits: dict, flags: set, numbers: set) -> dict:
    if not patch or set(patch) - (set(limits) | flags | numbers):
        raise ValueError("Unknown or empty edit fields")
    for field in flags & patch.keys():
        if type(patch[field]) is not bool:
            raise ValueError(f"{field} must be true or false")
    for field in numbers & patch.keys():
        if patch[field] is not None and (type(patch[field]) is not int or not 0 <= patch[field] <= 100):
            raise ValueError(f"{field} must be between 0 and 100")
    try:
        body = model.model_validate(patch)
        values = clean_fields(body, limits, require_name=False)
    except (ValidationError, HTTPException) as error:
        raise ValueError("Invalid edit fields") from error
    values.update({field: patch[field] for field in (flags | numbers) & patch.keys()})
    return values


def _validate_deal_fields(patch: dict) -> dict:
    if not set(patch) - {STEP_TYPE} or set(patch) - DEAL_FIELDS:
        raise ValueError("Unknown or empty deal fields")
    if patch.get(STEP_TYPE) not in (None, *TASK_TYPES):
        raise ValueError("Unknown follow-up type")
    if "pipeline_stage" in patch and patch["pipeline_stage"] not in PIPELINE_STAGES:
        raise ValueError("Unknown pipeline stage")
    if "status" in patch and patch["status"] not in STATUSES:
        raise ValueError("Unknown deal status")
    values = dict(patch)
    if "next_step" in values and values["next_step"] is not None:
        if not isinstance(values["next_step"], str) or len(values["next_step"].strip()) > NEXT_STEP_MAX:
            raise ValueError("Invalid next step")
        values["next_step"] = values["next_step"].strip() or None
    if "next_step_date" in patch and patch["next_step_date"] is not None:
        try:
            date.fromisoformat(patch["next_step_date"])
        except (TypeError, ValueError) as error:
            raise ValueError("Invalid next-step date") from error
    return values
