"""Business-card capture: vision extraction, image storage, dedup, and promotion.

Extraction uses Claude Haiku 4.5 (vision) via the existing get_llm() factory.
langchain is imported lazily inside the functions that need it, so the pure
helpers (JSON parsing, dedup, promotion) stay importable and testable without
the agents extra installed.
"""
import base64
import logging
import os

from gcrm.config import CARD_IMAGE_DIR
from gcrm.prompts.cards import CARD_SYSTEM_PROMPT
from gcrm.tools.email_domains import FREEMAIL_DOMAINS
from gcrm.tools.json_parsing import parse_llm_json

logger = logging.getLogger(__name__)

_EXTRACT_MODEL = "claude-haiku"                  # get_llm() key
_EXTRACT_MODEL_NAME = "claude-haiku-4-5-20251001"  # PRICING / response model name


# ---------------------------------------------------------------------------
# Vision extraction
# ---------------------------------------------------------------------------
def _content_to_text(content) -> str:
    """ChatAnthropic .content is usually a str, but can be a list of blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in content
        )
    return str(content)


def _usage_cost(model_name: str, input_tokens: int, output_tokens: int) -> float:
    from gcrm.tools.costs import PRICING
    p = PRICING.get(model_name, {"input": 0.0, "output": 0.0})
    return round((input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000, 6)


def extract_card_fields(image_bytes: bytes, media_type: str = "image/jpeg") -> dict:
    """
    Run Claude Haiku 4.5 vision on a business-card image.

    Returns {"fields": {...}, "model": str, "cost_usd": float}. `fields` always
    has an `is_card` key; on any failure it's {"is_card": False, "error": ...}.
    """
    from langchain_core.messages import HumanMessage, SystemMessage
    from gcrm.tools.llm import get_llm

    b64 = base64.b64encode(image_bytes).decode("ascii")
    user = HumanMessage(content=[
        {"type": "text", "text": "Extract this business card."},
        {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}"}},
    ])
    try:
        resp = get_llm(_EXTRACT_MODEL).invoke([SystemMessage(content=CARD_SYSTEM_PROMPT), user])
        fields = parse_llm_json(_content_to_text(resp.content))
        usage = getattr(resp, "usage_metadata", None) or {}
        cost = _usage_cost(_EXTRACT_MODEL_NAME, usage.get("input_tokens", 0), usage.get("output_tokens", 0))
    except Exception as e:
        logger.exception("card extraction failed")
        return {"fields": {"is_card": False, "error": str(e)}, "model": _EXTRACT_MODEL_NAME, "cost_usd": 0.0}

    fields.setdefault("is_card", True)
    return {"fields": fields, "model": _EXTRACT_MODEL_NAME, "cost_usd": cost}


# ---------------------------------------------------------------------------
# Image storage (VPS volume — see CARD_IMAGE_DIR)
# ---------------------------------------------------------------------------
def save_card_image(capture_id: int, image_bytes: bytes) -> str:
    """Write the image under CARD_IMAGE_DIR; return the stored filename."""
    os.makedirs(CARD_IMAGE_DIR, exist_ok=True)
    name = f"{capture_id}.jpg"
    with open(os.path.join(CARD_IMAGE_DIR, name), "wb") as f:
        f.write(image_bytes)
    return name


def read_card_image(image_path: str) -> bytes | None:
    if not image_path:
        return None
    full = os.path.join(CARD_IMAGE_DIR, os.path.basename(image_path))
    try:
        with open(full, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None


def delete_card_image(image_path: str) -> None:
    if not image_path:
        return
    try:
        os.remove(os.path.join(CARD_IMAGE_DIR, os.path.basename(image_path)))
    except FileNotFoundError:
        pass


# ---------------------------------------------------------------------------
# Dedup
# ---------------------------------------------------------------------------
def _digits(s: str) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit())


def find_possible_duplicate(fields: dict) -> dict | None:
    """
    Return {id,name,city,email,phone} of an existing contact that likely matches
    this card, or None. Priority: exact email → same corporate domain → phone
    suffix → name+city. It's a *suggestion* — the user confirms link-or-new.
    """
    from gcrm.db.connection import db

    email = (fields.get("email") or "").strip()
    company = (fields.get("company") or fields.get("name") or "").strip()
    city = (fields.get("city") or "").strip()
    phone_digits = _digits(fields.get("phone") or fields.get("mobile") or "")
    cols = "id, name, city, email, phone"
    with db() as conn:
        cur = conn.cursor()
        if email:
            cur.execute(
                f"SELECT {cols} FROM contacts WHERE lower(email)=lower(%s) AND deleted_at IS NULL LIMIT 1",
                (email,),
            )
            row = cur.fetchone()
            if row:
                return dict(row)
            domain = email.split("@")[-1].lower() if "@" in email else ""
            if domain and domain not in FREEMAIL_DOMAINS:
                cur.execute(
                    f"SELECT {cols} FROM contacts WHERE lower(email) LIKE %s AND deleted_at IS NULL LIMIT 1",
                    (f"%@{domain}",),
                )
                row = cur.fetchone()
                if row:
                    return dict(row)
        if len(phone_digits) >= 7:
            cur.execute(
                f"SELECT {cols} FROM contacts "
                "WHERE regexp_replace(coalesce(phone,''), '[^0-9]', '', 'g') LIKE %s "
                "AND deleted_at IS NULL LIMIT 1",
                (f"%{phone_digits[-9:]}",),
            )
            row = cur.fetchone()
            if row:
                return dict(row)
        if company and city:
            cur.execute(
                f"SELECT {cols} FROM contacts WHERE lower(name)=lower(%s) AND lower(city)=lower(%s) "
                "AND deleted_at IS NULL LIMIT 1",
                (company, city),
            )
            row = cur.fetchone()
            if row:
                return dict(row)
    return None


# ---------------------------------------------------------------------------
# Promotion to a contact
# ---------------------------------------------------------------------------
def _country_code(raw) -> str:
    c = (raw or "").strip().upper()
    return c if len(c) == 2 and c.isalpha() else "DE"


def promote_to_contact(fields: dict) -> int:
    """
    Create a contact (status 'candidate', source 'card_capture') from card fields.
    company → name, person+title → decision_maker. Returns the new contact id, or
    0 if save_contact deduped it (email or name+city already exists).
    """
    from gcrm.tools.db import save_contact
    from gcrm.db.connection import db

    company = (fields.get("company") or "").strip()
    person = (fields.get("name") or "").strip()
    title = (fields.get("title") or "").strip()
    name = company or person or "Unknown"

    cid = save_contact(
        name=name,
        city=(fields.get("city") or "").strip(),
        country=_country_code(fields.get("country")),
        type=(fields.get("industry") or "").strip(),
        website=(fields.get("website") or "").strip(),
        email=(fields.get("email") or "").strip(),
        phone=(fields.get("phone") or fields.get("mobile") or "").strip(),
        notes=(fields.get("note") or "").strip(),
        status="candidate",
    )
    if cid == 0:
        return 0

    decision_maker = (", ".join(p for p in (person, title) if p)[:200]) or None
    address = (fields.get("address") or "").strip() or None
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE contacts SET decision_maker=%s, address=%s, source='card_capture', "
            "updated_at=NOW() WHERE id=%s",
            (decision_maker, address, cid),
        )
    return cid


# ---------------------------------------------------------------------------
# Enrich a single contact (background task on confirm)
# ---------------------------------------------------------------------------
def enrich_one(contact_id: int) -> None:
    """Run the enrichment agent for one contact, then push when done. Best-effort."""
    try:
        from gcrm.config import CHEAP_LLM
        from gcrm.tools import (
            web_search, fetch_page, update_contact_details,
            start_run, finish_run, get_llm,
        )
        from gcrm.tools.db import get_contact
        from gcrm_enrichment_agent import create_enrichment_agent

        def fetch_one(limit: int = 1, city: str | None = None) -> list[dict]:
            c = get_contact(contact_id)
            return [c] if c else []

        agent = create_enrichment_agent(
            llm=get_llm(CHEAP_LLM),
            web_search=web_search,
            fetch_page=fetch_page,
            fetch_contacts=fetch_one,
            update_contact=update_contact_details,
            start_run=start_run,
            finish_run=finish_run,
        )
        agent.invoke({"limit": 1})
    except Exception:
        logger.exception("enrich_one: enrichment failed for contact %s", contact_id)
        return

    try:
        from gcrm.api.push import send_push_to_all
        from gcrm.tools.db import get_contact
        c = get_contact(contact_id) or {}
        send_push_to_all(
            title="Lead ready",
            body=f"{c.get('name', 'New lead')} enriched & ready",
            data={"screen": "contacts"},
        )
    except Exception:
        logger.debug("enrich_one: push failed", exc_info=True)
