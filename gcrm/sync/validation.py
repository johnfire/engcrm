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

PERSON_FLAGS = {"is_linkedin_contact", "retention_hold"}
DEAL_FIELDS = {"pipeline_stage", "status", "next_step", "next_step_date"}


def validate_sync_patch(kind: str, patch: dict) -> dict:
    if kind == "organization":
        return _validate_contact_fields(patch, OrganizationFields, TEXT_LIMITS, set(EDITABLE_FLAGS), {"fit_score"})
    if kind == "person":
        values = _validate_contact_fields(patch, PersonFields, PERSON_LIMITS, PERSON_FLAGS, set())
        if values.get("linkedin_url"):
            normalized = normalize_linkedin_url(values["linkedin_url"])
            if not normalized:
                raise ValueError("linkedin_url must be a valid LinkedIn profile")
            values["linkedin_url"] = normalized
        return values
    if kind == "deal":
        return _validate_deal_fields(patch)
    raise ValueError("Unknown entity kind")


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
    if not patch or set(patch) - DEAL_FIELDS:
        raise ValueError("Unknown or empty deal fields")
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
