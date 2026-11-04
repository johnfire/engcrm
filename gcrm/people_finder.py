"""Find decision-makers at a company, and their public LinkedIn/XING profiles, by web search.

Nothing here visits LinkedIn or XING: profiles are recognised in a search engine's result
list, and pages are only fetched from the company's own site. Network and LLM calls are
injected (`search`, `fetch_page`, `extract`) so the rules are testable offline, and any
failure degrades to "no people found" instead of an error.

Three rules keep the list honest:
* A name the LLM returns is only kept when it literally appears in the search results or
  the fetched pages — an LLM must not be able to invent a person.
* Only decision-makers are kept, at most three per company, the most senior first.
* A profile is only linked when its result names both the person and the company; a
  person with no such result is kept with no profile, never a guessed one.
"""
import logging
import re
from collections.abc import Callable
from urllib.parse import urlsplit

from gcrm.company_pages import distinctive_words, names_company
from gcrm.json_parsing import parse_llm_json
from gcrm.linkedin import normalize_company
from gcrm.prompts.enrichment import find_people_prompt

logger = logging.getLogger(__name__)

MAX_PEOPLE = 3
MAX_COMPANY_PAGES = 2
_TITLE_PARTS = re.compile(r"\s+[-–|·]\s+")
_SITE_PREFIX = re.compile(r"^(?:XING|LinkedIn)(?=[A-ZÄÖÜ])")  # 'XINGJan Oehler - …' from a search engine
_SOCIAL_HOSTS = re.compile(r"(linkedin\.|xing\.|facebook\.|instagram\.|google\.|youtube\.)", re.IGNORECASE)
_HONORIFICS = {"dr", "prof", "ing", "dipl", "mag", "herr", "frau"}

# Role words by seniority: owners and managing directors first, then the people who own
# IT and digital work, then those who run production and operations, then other heads.
_ROLE_RANKS = (
    re.compile(r"geschäftsführ|geschaeftsfuehr|inhaber|owner|gründer|gruender|founder|vorstand"
               r"|managing director|\bceo\b|president", re.IGNORECASE),
    re.compile(r"\b(cto|cio|cdo)\b|it-leit|leiter it|leitung it|head of it|it[- ]director|it manager"
               r"|digitalis", re.IGNORECASE),
    re.compile(r"\bcoo\b|werkleit|produktionsleit|betriebsleit|plant manager|operations", re.IGNORECASE),
    re.compile(r"leiter|leitung|head of|director|prokurist|\bcfo\b|chief", re.IGNORECASE),
)


def role_rank(role: str | None) -> int | None:
    """0 for the most senior decision-maker roles, higher for others, None if not one."""
    if not role:
        return None
    return next((rank for rank, pattern in enumerate(_ROLE_RANKS) if pattern.search(role)), None)


def is_decision_maker(role: str | None) -> bool:
    return role_rank(role) is not None


def profile_url(url: str) -> tuple[str, str] | None:
    """('linkedin' | 'xing', tidy profile URL) for a person's profile page, else None."""
    parts = urlsplit((url or "").strip())
    host = (parts.hostname or "").lower()
    if host == "linkedin.com" or host.endswith(".linkedin.com"):
        match = re.match(r"^/in/([^/?#]+)", parts.path)
        return ("linkedin", f"https://www.linkedin.com/in/{match.group(1)}") if match else None
    if host == "xing.com" or host.endswith(".xing.com"):
        match = re.match(r"^/profile/([^/?#]+)", parts.path)
        return ("xing", f"https://www.xing.com/profile/{match.group(1)}") if match else None
    return None


def name_words(person_name: str) -> set[str]:
    return {word for word in normalize_company(person_name).split()
            if len(word) >= 2 and word not in _HONORIFICS}


def mentions_person(text: str, person_name: str) -> bool:
    words = name_words(person_name)
    return len(words) >= 2 and words <= set(normalize_company(text).split())


def link_names_person(profile: str, person_name: str) -> bool:
    """True when the profile's own address carries the person's name — a search engine
    sometimes pairs one result's title with another result's link."""
    slug = normalize_company(profile.rstrip("/").rsplit("/", 1)[-1])
    return name_words(person_name) <= set(re.findall(r"[a-z]+", slug))


def _result_text(search_result: dict) -> str:
    url_words = re.sub(r"[^a-z0-9]+", " ", (search_result.get("url") or "").lower())
    return " ".join([url_words, search_result.get("title") or "", search_result.get("snippet") or ""])


def pick_profile(person_name: str, company_name: str, search_results: list[dict]) -> tuple[str, str] | None:
    """The first profile whose result names both this person and this company."""
    company_words = distinctive_words(company_name)
    for search_result in search_results:
        profile = profile_url(search_result.get("url") or "")
        if profile and link_names_person(profile[1], person_name) \
                and mentions_person(_result_text(search_result), person_name) \
                and names_company(search_result, company_words):
            return profile
    return None


def person_from_profile_result(search_result: dict, company_name: str) -> dict | None:
    """'Anwar Amir - Produktionsleiter - Faist Systeme GmbH | XING' -> a person, when the
    result is a profile at this company held by a decision-maker."""
    profile = profile_url(search_result.get("url") or "")
    if not profile or not names_company(search_result, distinctive_words(company_name)):
        return None
    parts = _TITLE_PARTS.split(_SITE_PREFIX.sub("", (search_result.get("title") or "").strip()))
    name, role = parts[0].strip(), (parts[1].strip() if len(parts) > 1 else "")
    if not re.fullmatch(r"[^\W\d_]+(?:[ .'-]+[^\W\d_]+){1,3}", name) or not is_decision_maker(role):
        return None
    if not link_names_person(profile[1], name):
        return None
    return {"name": name, "role": role, f"{profile[0]}_url": profile[1],
            "source_url": search_result.get("url")}


def find_people(
    organization: dict,
    *,
    search: Callable[[str], list[dict]],
    fetch_page: Callable[[str], str],
    extract: Callable[[str, str], str],
) -> list[dict]:
    """Up to three decision-makers: {name, role, linkedin_url, xing_url, source_url}."""
    company = (organization.get("name") or "").strip()
    if not company:
        return []
    people = _people_named_by_the_company(organization, search, fetch_page, extract)
    people += _people_with_profiles(organization, search)
    chosen = _best_people(people)
    for person in chosen:
        _add_profile(person, company, search)
    return chosen


def _safe_search(search, query: str) -> list[dict]:
    """Search, retrying without quotes when the quoted search finds nothing (the search
    engine often returns no results for an exact-phrase query)."""
    for attempt in dict.fromkeys([query, query.replace('"', "")]):
        try:
            results = search(attempt) or []
        except Exception as error:
            logger.warning("people_finder: search failed for %r — %s", attempt, error)
            results = []
        if results:
            return results
    return []


def _company_pages(organization: dict, search_results: list[dict]) -> list[str]:
    website = (organization.get("website") or "").strip().rstrip("/")
    urls = [f"{website}/impressum", website] if website else []
    urls += [result.get("url") for result in search_results
             if result.get("url") and not _SOCIAL_HOSTS.search(result["url"])]
    return list(dict.fromkeys(urls))[:MAX_COMPANY_PAGES + 1]


def _people_named_by_the_company(organization, search, fetch_page, extract) -> list[dict]:
    """Decision-makers the LLM reads off the company's own pages and search snippets."""
    company, city = organization["name"], organization.get("city") or ""
    german = (organization.get("country") or "DE") in ("DE", "AT", "CH")
    query = f'"{company}" {city} Geschäftsführer Impressum' if german else f'"{company}" {city} management team'
    search_results = _safe_search(search, query)
    pages = []
    for url in _company_pages(organization, search_results):
        try:
            text = fetch_page(url)
        except Exception:
            text = ""
        if text:
            pages.append(f"[Page: {url}]\n{text[:2000]}")
    system, user = find_people_prompt(organization, search_results, pages)
    try:
        named = parse_llm_json(extract(system, user))
    except Exception as error:
        logger.warning("people_finder: extraction failed for %s — %s", company, error)
        return []
    sources = " ".join(pages + [_result_text(result) for result in search_results])
    return [
        {"name": person["name"].strip(), "role": (person.get("role") or "").strip(), "source_url": None}
        for person in (named if isinstance(named, list) else [])
        if isinstance(person, dict) and isinstance(person.get("name"), str)
        and mentions_person(sources, person["name"]) and is_decision_maker(person.get("role"))
    ]


def _people_with_profiles(organization: dict, search) -> list[dict]:
    """Decision-makers whose own profiles turn up in a search for the company."""
    query = f'"{organization["name"]}" LinkedIn XING'
    found = (person_from_profile_result(result, organization["name"]) for result in _safe_search(search, query))
    return [person for person in found if person]


def _best_people(people: list[dict]) -> list[dict]:
    unique: dict[str, dict] = {}
    for person in people:
        key = " ".join(sorted(name_words(person["name"])))
        unique[key] = {**person, **unique.get(key, {})}
    ranked = sorted(unique.values(), key=lambda person: role_rank(person["role"]))
    return [{"linkedin_url": None, "xing_url": None, **person} for person in ranked[:MAX_PEOPLE]]


def _add_profile(person: dict, company: str, search) -> None:
    if person.get("linkedin_url") or person.get("xing_url"):
        return
    profile = pick_profile(person["name"], company, _safe_search(search, f'"{person["name"]}" "{company}" LinkedIn'))
    if profile:
        person[f"{profile[0]}_url"] = profile[1]


def llm_extractor(llm) -> Callable[[str, str], str]:
    """Adapt a LangChain chat model to the `extract(system, user) -> text` this module needs."""
    from langchain_core.messages import HumanMessage, SystemMessage

    def extract(system: str, user: str) -> str:
        content = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)]).content
        if isinstance(content, str):
            return content
        return "".join(block.get("text", "") for block in content if isinstance(block, dict))

    return extract
