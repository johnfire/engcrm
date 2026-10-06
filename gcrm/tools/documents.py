"""Read document contacts and validate vision output before staging drafts."""
import base64
import logging

from gcrm.json_parsing import parse_llm_json
from gcrm.prompts.documents import DOCUMENT_SYSTEM_PROMPT
from gcrm.tools.cards import _content_to_text, _usage_cost

logger = logging.getLogger(__name__)
MODEL_NAME = "claude-haiku-4-5-20251001"
EXTRACTION_FAILED = "Could not read this page. Retake the photo with the text clearly visible."
TEXT_FIELDS = (
    "company", "name", "title", "email", "phone", "mobile", "website", "address",
    "city", "country", "industry", "language", "note",
)


def normalize_document_contacts(payload: dict) -> list[dict]:
    """Reject malformed or truncated responses instead of losing page rows."""
    if not isinstance(payload, dict) or not isinstance(payload.get("contacts"), list):
        raise ValueError("Expected contacts array")
    if len(payload["contacts"]) > 50:
        raise ValueError("Too many contacts; photograph smaller sections")
    contacts = []
    for contact in payload["contacts"]:
        if not isinstance(contact, dict):
            raise ValueError("Expected contact object")
        fields = {}
        for key in TEXT_FIELDS:
            value = contact.get(key)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"Expected text for {key}")
            fields[key] = value.strip() or None if value is not None else None
        if not any(fields[key] for key in ("company", "name", "email", "phone", "mobile", "website")):
            raise ValueError("Empty contact row")
        confidence = contact.get("confidence")
        fields["confidence"] = (
            int(confidence) if isinstance(confidence, (int, float))
            and not isinstance(confidence, bool) and 0 <= confidence <= 100 else None
        )
        contacts.append(fields)
    return contacts


def extract_document_contacts(image_bytes: bytes, media_type: str = "image/jpeg") -> dict:
    from langchain_core.messages import HumanMessage, SystemMessage

    from gcrm.tools.llm import get_llm

    encoded_image = base64.b64encode(image_bytes).decode("ascii")
    message = HumanMessage(content=[
        {"type": "text", "text": "Read the contacts on this page."},
        {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{encoded_image}"}},
    ])
    try:
        response = get_llm("claude-haiku").invoke([
            SystemMessage(content=DOCUMENT_SYSTEM_PROMPT), message,
        ])
        if (getattr(response, "response_metadata", None) or {}).get("stop_reason") == "max_tokens":
            raise ValueError("Truncated document extraction")
        payload = parse_llm_json(_content_to_text(response.content))
        contacts = normalize_document_contacts(payload)
        usage = getattr(response, "usage_metadata", None) or {}
        return {
            "contacts": contacts, "model": MODEL_NAME,
            "note": payload.get("note") if isinstance(payload.get("note"), str) else None,
            "cost_usd": _usage_cost(MODEL_NAME, usage.get("input_tokens", 0), usage.get("output_tokens", 0)),
        }
    except Exception:
        logger.exception("document extraction failed")
        return {"contacts": [], "model": MODEL_NAME, "note": EXTRACTION_FAILED, "cost_usd": 0.0}
