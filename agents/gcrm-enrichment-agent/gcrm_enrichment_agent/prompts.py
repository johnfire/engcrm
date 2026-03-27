def enrich_contact_prompt(contact: dict, search_results: list[dict]) -> tuple[str, str]:
    system = (
        "You are extracting contact details for a business from web search results. "
        "Return a JSON object with these fields: "
        "website (string or null), email (string or null), phone (string or null). "
        "Only return data you are confident about from the search results. "
        "Do not invent or guess. Return null for any field not clearly found. "
        "Return ONLY the JSON object, no explanation."
    )

    results_text = "\n\n".join(
        f"Title: {r.get('title', '')}\nURL: {r.get('url', '')}\nSnippet: {r.get('snippet', '')}"
        for r in search_results[:5]
    ) or "No results found."

    user = (
        f"Business: {contact['name']}\n"
        f"City: {contact['city']}\n"
        f"Country: {contact.get('country', 'DE')}\n"
        f"Type: {contact.get('type', '')}\n\n"
        f"Search results:\n{results_text}"
    )

    return system, user
