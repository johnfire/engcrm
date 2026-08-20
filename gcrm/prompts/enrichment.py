"""
Enrichment prompts and query building.

Vertical-agnostic: talks about a "business", never a specific venue type.
Lives in the shared gcrm package so the enrichment agent (a thin re-export
shim) and any other caller share exactly one source of truth.
"""


def build_search_query(organization: dict) -> str:
    """
    Build a language-aware web-search query for a contact.

    For German-speaking countries (DE/AT/CH) we target Impressum / Kontakt
    pages, because that is where a business's real contact email lives. Every
    other country falls back to a generic English query.
    """
    name = organization["name"]
    city = organization["city"]
    country = organization.get("country", "DE")

    if country in ("DE", "AT", "CH"):
        return f"{name} {city} Impressum Kontakt"
    return f"{name} {city} contact website email"


def enrich_organization_prompt(
    organization: dict,
    search_results: list[dict],
    page_texts: list[str] | None = None,
) -> tuple[str, str]:
    """
    Prompt the LLM to extract a business's website, email, and phone from web
    search results and (when available) fetched page content.

    Page content is far more reliable than search snippets — emails live on
    Impressum/Kontakt pages, not in snippets — so the model is told to prefer it.
    """
    system = (
        "You are extracting contact details for a business from web search results and page content. "
        "Return a JSON object with exactly these fields: "
        "website (string or null), email (string or null), phone (string or null). "
        "Prefer data from page content over search snippets — page content is more reliable. "
        "For email: only return a direct contact email (e.g. info@business.de). "
        "Ignore generic form URLs, social media links, and placeholder addresses. "
        "Do not invent or guess. Return null for any field not clearly found. "
        "Return ONLY the JSON object, no explanation."
    )

    snippets = "\n\n".join(
        f"Title: {result.get('title', '')}\nURL: {result.get('url', '')}\nSnippet: {result.get('snippet', '')}"
        for result in search_results[:5]
    ) or "No results found."

    user = (
        f"Business: {organization['name']}\n"
        f"City: {organization['city']}\n"
        f"Country: {organization.get('country', 'DE')}\n"
        f"Type: {organization.get('type', '')}\n\n"
        f"Search snippets:\n{snippets}"
    )

    if page_texts:
        user += "\n\nPage content:\n" + "\n\n".join(page_texts)

    return system, user


def find_people_prompt(
    organization: dict,
    search_results: list[dict],
    page_texts: list[str] | None = None,
) -> tuple[str, str]:
    """
    Prompt the LLM to extract key people (owners, managers, decision-makers) for
    a business from web search results and fetched page content. Companion to
    enrich_organization_prompt — same inputs, different extraction target.
    """
    system = (
        "You are extracting key people (owners, managers, decision-makers) for a "
        "business from web search results and page content. Return a JSON array "
        "of objects, each with exactly these fields: "
        "name (string, required), role (string or null), email (string or null), "
        "phone (string or null). Only include real named individuals explicitly "
        "associated with this business — never invent a name. Prefer data from "
        "page content (Team/Über uns/Impressum pages) over search snippets. "
        "Return an empty array if no named individuals are found. "
        "Return ONLY the JSON array, no explanation."
    )

    snippets = "\n\n".join(
        f"Title: {result.get('title', '')}\nURL: {result.get('url', '')}\nSnippet: {result.get('snippet', '')}"
        for result in search_results[:5]
    ) or "No results found."

    user = (
        f"Business: {organization.get('name', '')}\n"
        f"City: {organization.get('city', '')}\n"
        f"Country: {organization.get('country', 'DE')}\n\n"
        f"Search snippets:\n{snippets}"
    )

    if page_texts:
        user += "\n\nPage content:\n" + "\n\n".join(page_texts)

    return system, user
