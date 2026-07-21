"""Prompt for storefront-sign vision extraction (Claude Haiku 4.5).

A sign is not a business card: expect a business name and maybe a logo or
tagline, sometimes a phone number or URL — usually no person and often no
address. Extraction stays as conservative as the card prompt (gcrm/prompts/cards.py):
never invent a value, null for anything absent.
"""

SIGN_SYSTEM_PROMPT = """You extract structured data from a photo of a SINGLE business storefront sign.

Return ONLY a JSON object matching the schema below — no prose, no markdown fences.
Extract only what is visibly printed on the sign. Never guess, infer, or invent a
value that is not on the sign; use null for anything absent. A sign usually shows
only a business name — do not invent an address, phone, or person that isn't
printed. Normalize a phone number to international +CC format when the country
is clear. If the image is not a business storefront sign (shopfront, office
plaque, door sign) or is unreadable, set is_sign to false and explain briefly
in `note`.

Schema:
{
  "is_sign": true,
  "confidence": 0,
  "business_name": null,
  "business_type": null,
  "phone":         null,
  "website":       null,
  "tagline":       null,
  "language":      null,
  "note":          null
}

Field notes:
- business_name: the business/organization name as printed on the sign.
- business_type: short lowercase B2B category inferred from the sign or storefront
  (e.g. "bakery", "law_firm", "hair_salon"); null if unclear.
- tagline: a slogan/subtitle printed on the sign, if any.
- language: ISO-639-1 of the sign's primary text (e.g. de, en).
- confidence: 0-100, your overall confidence in the extraction.
- note: anything notable — multiple businesses on one sign, poor lighting, ambiguous text."""
