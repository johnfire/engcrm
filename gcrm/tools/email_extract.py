"""Person-from-email extraction: pull one person's contact fields out of pasted
email text (body/signature) via LLM. Mirrors gcrm/tools/cards.py's vision
extraction, minus the image handling.
"""
import logging

from gcrm.json_parsing import parse_llm_json
from gcrm.prompts.person_email import PERSON_EMAIL_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

_EXTRACT_MODEL = "claude-haiku"                  # get_llm() key
_EXTRACT_MODEL_NAME = "claude-haiku-4-5-20251001"  # PRICING / response model name

# What the web client is told when extraction fails. Deliberately free of
# detail — the diagnosable version is in the server log.
_EXTRACTION_FAILED = "Could not read this. Enter the details manually."


def _content_to_text(content) -> str:
    """ChatAnthropic .content is usually a str, but can be a list of blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "") if isinstance(block, dict) else str(block) for block in content
        )
    return str(content)


def _usage_cost(model_name: str, input_tokens: int, output_tokens: int) -> float:
    from gcrm.tools.costs import PRICING
    p = PRICING.get(model_name, {"input": 0.0, "output": 0.0})
    return round((input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000, 6)


def extract_person_from_email(text: str) -> dict:
    """
    Run Claude Haiku 4.5 on raw email text to pull out one person's contact
    fields.

    Returns {"fields": {...}, "model": str, "cost_usd": float}. On any failure
    `fields` is {"error": ...} with a fixed client-safe string — the real cause
    goes to the log.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    from gcrm.tools.llm import get_llm

    try:
        resp = get_llm(_EXTRACT_MODEL).invoke([
            SystemMessage(content=PERSON_EMAIL_SYSTEM_PROMPT),
            HumanMessage(content=text),
        ])
        fields = parse_llm_json(_content_to_text(resp.content))
        usage = getattr(resp, "usage_metadata", None) or {}
        cost = _usage_cost(_EXTRACT_MODEL_NAME, usage.get("input_tokens", 0), usage.get("output_tokens", 0))
    except Exception:
        # The detail stays in the server log; the web client gets a fixed
        # string. str(error) here reached the app verbatim, and an upstream SDK
        # error can carry request URLs, model wiring, even key fragments.
        logger.exception("person-from-email extraction failed")
        return {"fields": {"error": _EXTRACTION_FAILED}, "model": _EXTRACT_MODEL_NAME, "cost_usd": 0.0}

    return {"fields": fields, "model": _EXTRACT_MODEL_NAME, "cost_usd": cost}
