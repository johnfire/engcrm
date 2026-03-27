def enrich_contact_prompt(contact: dict) -> tuple[str, str]:
    """
    Generic enrichment prompt — finds missing website and email for a contact.
    No domain-specific content needed here.
    """
    system = (
        "You are a research assistant helping find missing contact information. "
        "Given partial contact details, find the official website and/or email address."
    )
    user = (
        f"Find the official website and email for this business:\n\n"
        f"Name: {contact.get('name')}\n"
        f"City: {contact.get('city')}\n"
        f"Country: {contact.get('country', '')}\n"
        f"Type: {contact.get('type', '')}\n"
        f"Current website: {contact.get('website', 'unknown')}\n"
        f"Current email: {contact.get('email', 'unknown')}\n"
        f"Notes: {contact.get('notes', '')}\n\n"
        f"Return a JSON object with:\n"
        f"- website: URL (null if not found)\n"
        f"- email: email address (null if not found)\n\n"
        f"Return ONLY the JSON object, no other text."
    )
    return system, user
