"""
LinkedIn connections: parse the Connections.csv data export and match each
connection's company string to one of our organizations.

Pure functions only — no database, no network — so every rule here is unit
testable and a bad row can never take the import down with it. The database
side lives in gcrm/tools/db_linkedin.py.

The export is the official "Get a copy of your data -> Connections" download.
Nothing here fetches or scrapes LinkedIn.
"""
import csv
import difflib
import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import urlsplit

# --- CSV parsing -------------------------------------------------------------

# Header text -> our field. The English column names are LinkedIn's own; the
# German ones are what a German-language account is expected to export and
# should be confirmed against a real German file.
_HEADER_ALIASES = {
    "first_name": {"first name", "vorname"},
    "last_name": {"last name", "nachname"},
    "linkedin_url": {"url", "profile url", "profil-url", "profil url"},
    "email": {"email address", "e-mail address", "email", "e-mail", "e-mail-adresse", "e-mail adresse"},
    "company": {"company", "unternehmen", "firma"},
    "title": {"position", "title", "job title", "berufsbezeichnung"},
    "connected_on": {"connected on", "verbunden am", "vernetzt am"},
}

# LinkedIn puts a multi-line "Notes:" paragraph above the header row in recent
# exports, so the header is searched for rather than assumed to be line one.
_HEADER_SEARCH_LINES = 50
_DELIMITERS = (",", ";", "\t")

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "mär": 3, "mrz": 3, "apr": 4, "may": 5, "mai": 5,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "okt": 10, "nov": 11,
    "dec": 12, "dez": 12,
}
_TEXT_DATE = re.compile(r"^\s*(\d{1,2})[\s.\-]+([A-Za-zÄÖÜäöü]+)\.?[\s,\-]+(\d{4})\s*$")
_ISO_DATE = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})")
_NUMERIC_DATE = re.compile(r"^\s*(\d{1,2})\.(\d{1,2})\.(\d{4})\s*$")


@dataclass
class ConnectionsParse:
    """Result of reading one export. `header_found` False means the file was
    not a Connections export at all (wrong file, or a format we don't know)."""
    header_found: bool = False
    rows: list[dict] = field(default_factory=list)
    skipped: int = 0


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("﻿", "")).strip()


def _map_columns(cells: list[str]) -> dict[str, int]:
    columns: dict[str, int] = {}
    for index, cell in enumerate(cells):
        label = _clean(cell).lower()
        for field_name, aliases in _HEADER_ALIASES.items():
            if label in aliases and field_name not in columns:
                columns[field_name] = index
    return columns


def _find_header(lines: list[str]) -> tuple[int, str, dict[str, int]] | None:
    for delimiter in _DELIMITERS:
        for index, line in enumerate(lines[:_HEADER_SEARCH_LINES]):
            if delimiter not in line:
                continue
            cells = next(csv.reader([line], delimiter=delimiter), [])
            columns = _map_columns(cells)
            if "first_name" in columns and "last_name" in columns:
                return index, delimiter, columns
    return None


def parse_connected_on(value: str | None) -> date | None:
    """'05 Mar 2024', '5 Mär 2024', '2024-03-05' or '05.03.2024' -> date.
    Anything unreadable is None: a missing date must never drop the row."""
    text = _clean(value)
    if not text:
        return None
    try:
        match = _ISO_DATE.match(text)
        if match:
            return date(int(match[1]), int(match[2]), int(match[3]))
        match = _NUMERIC_DATE.match(text)
        if match:
            return date(int(match[3]), int(match[2]), int(match[1]))
        match = _TEXT_DATE.match(text)
        if match:
            month = _MONTHS.get(match[2].lower()[:3])
            if month:
                return date(int(match[3]), month, int(match[1]))
    except ValueError:
        return None
    return None


def normalize_linkedin_url(value: str | None) -> str | None:
    """Canonical https://www.linkedin.com/<path> form, lowercased and without
    query, fragment or trailing slash — the import's dedup key. None when the
    value is not a linkedin.com link, so a mistyped or hostile string is never
    stored as a profile URL."""
    text = _clean(value)
    if not text:
        return None
    if "://" not in text:
        text = f"https://{text}"
    try:
        parts = urlsplit(text)
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or not (host == "linkedin.com" or host.endswith(".linkedin.com")):
        return None
    path = parts.path.rstrip("/").lower()
    if not path:
        return None
    return f"https://www.linkedin.com{path}"


def linkedin_url_hash(value: str | None) -> str | None:
    """SHA-256 of the canonical profile URL: what is remembered about a person
    who was deleted, so a later import can skip them without keeping their URL."""
    canonical = normalize_linkedin_url(value) or _clean(value).lower()
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest() if canonical else None


def parse_connections_csv(text: str) -> ConnectionsParse:
    """Read a LinkedIn Connections.csv. Rows are parsed independently: an
    unreadable row is counted in `skipped` and the rest carry on."""
    result = ConnectionsParse()
    lines = text.splitlines(keepends=True)
    header = _find_header(lines)
    if header is None:
        return result
    header_index, delimiter, columns = header
    result.header_found = True

    def cell(row: list[str], field_name: str) -> str:
        index = columns.get(field_name)
        return _clean(row[index]) if index is not None and index < len(row) else ""

    for row in csv.reader(lines[header_index + 1:], delimiter=delimiter):
        try:
            if not any(_clean(value) for value in row):
                continue  # blank line, not a skipped connection
            name = f"{cell(row, 'first_name')} {cell(row, 'last_name')}".strip()
            if not name:
                result.skipped += 1
                continue
            email = cell(row, "email").lower()
            result.rows.append({
                "name": name,
                "linkedin_url": normalize_linkedin_url(cell(row, "linkedin_url")),
                "email": email if "@" in email else "",
                "company": cell(row, "company"),
                "title": cell(row, "title"),
                "connected_on": parse_connected_on(cell(row, "connected_on")),
            })
        except Exception:
            result.skipped += 1
    return result


def decode_export(data: bytes) -> str:
    """Bytes of an export -> text. UTF-8 (with or without BOM) first, then
    Windows-1252, which never fails, so a legacy-encoded file still loads."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


# --- Company matching --------------------------------------------------------

_LEGAL_FORMS = frozenset({
    "gmbh", "mbh", "ag", "ug", "kg", "kgaa", "gbr", "ohg", "se", "co", "inc", "llc",
    "ltd", "limited", "corp", "corporation", "company", "sa", "srl", "bv", "nv", "plc",
    "haftungsbeschraenkt",
})
_CONNECTORS = frozenset({"und", "and"})

# Words that say what a business is rather than which business it is. They are
# not allowed to be the *only* thing two names share ("Hotel" vs "Hotel Adler").
GENERIC_TOKENS = frozenset({
    "hotel", "cafe", "restaurant", "galerie", "gallery", "studio", "shop", "bar", "haus",
    "atelier", "museum", "kunst", "art", "design", "group", "gruppe", "international",
    "deutschland", "germany", "consulting", "solutions", "services", "technologies",
    "technology", "systems", "software", "the", "der", "die", "das",
})

# LinkedIn's Company field holds these when there is no company to speak of.
_NO_COMPANY = frozenset({
    "self employed", "selfemployed", "freelance", "freelancer", "selbststaendig",
    "selbstaendig", "independent", "confidential", "stealth", "stealth startup",
    "retired", "ruhestand", "none", "n a", "na", "student", "self", "myself",
    "selbstaendiger", "freiberuflich", "freiberufler", "unemployed", "arbeitssuchend",
})

FUZZY_THRESHOLD = 0.88


def normalize_company(name: str | None) -> str:
    """Comparison form of a company name: lowercase, umlauts folded, punctuation
    and legal forms ('GmbH', 'e.K.', 'Ltd') removed. '' means "no usable
    company", which never matches anything."""
    text = (name or "").lower()
    for source, target in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(source, target)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\be\.\s?[kv]\.?", " ", text)  # e.K. / e.V.
    text = re.sub(r"[^\w\s]|_", " ", text)
    tokens = [t for t in text.split() if t not in _CONNECTORS]
    stripped = [t for t in tokens if t not in _LEGAL_FORMS]
    normalized = " ".join(stripped or tokens)
    return "" if normalized in _NO_COMPANY else normalized


@dataclass(frozen=True)
class OrgMatch:
    contact_id: int
    name: str
    city: str
    confidence: str  # exact | ambiguous | partial | fuzzy
    score: float


@dataclass(frozen=True)
class _Org:
    contact_id: int
    name: str
    city: str
    normalized: str
    tokens: frozenset[str]


class OrgIndex:
    """Blocking index over our organizations, so matching 1,500 connections
    against tens of thousands of organizations compares each connection with a
    few dozen candidates instead of all of them.

    Two ways to become a candidate: share a *distinguishing* word (for the
    "Siemens" inside "Siemens Healthineers" case), or start with the same three
    letters (for typos: "Hofmann" / "Hoffmann"). A word found in more than
    TOKEN_CAP organizations ("Müller", "Bäckerei") identifies no one, so it is
    treated like a generic word: never the basis of a match, and left out of the
    word index rather than dragging in thousands of candidates.
    """

    TOKEN_CAP = 100
    PREFIX_LENGTH = 3
    MIN_FUZZY_LENGTH = 5  # "acme" vs "acne" is a typo of nothing

    def __init__(self, organizations: list[dict]):
        self._exact: dict[str, list[_Org]] = {}
        by_token: dict[str, list[_Org]] = {}
        self._by_prefix: dict[str, list[_Org]] = {}
        for record in organizations:
            normalized = normalize_company(record.get("name"))
            if not normalized:
                continue
            org = _Org(
                contact_id=record["id"],
                name=record.get("name") or "",
                city=record.get("city") or "",
                normalized=normalized,
                tokens=frozenset(normalized.split()),
            )
            self._exact.setdefault(normalized, []).append(org)
            self._by_prefix.setdefault(normalized[: self.PREFIX_LENGTH], []).append(org)
            for token in org.tokens - GENERIC_TOKENS:
                by_token.setdefault(token, []).append(org)
        self._stop_tokens = frozenset(t for t, orgs in by_token.items() if len(orgs) > self.TOKEN_CAP)
        self._by_token = {t: orgs for t, orgs in by_token.items() if t not in self._stop_tokens}

    def match(self, company: str | None, limit: int = 5) -> list[OrgMatch]:
        normalized = normalize_company(company)
        if not normalized:
            return []
        exact = self._exact.get(normalized)
        if exact:
            # Two organizations sharing a name (a chain, or the same café name
            # in two towns) cannot be told apart from the company string alone.
            confidence = "exact" if len(exact) == 1 else "ambiguous"
            return [OrgMatch(o.contact_id, o.name, o.city, confidence, 1.0) for o in exact[:limit]]

        tokens = frozenset(normalized.split())
        candidates: dict[int, _Org] = {}
        for token in tokens - GENERIC_TOKENS:
            for org in self._by_token.get(token, ()):
                candidates[org.contact_id] = org
        for org in self._by_prefix.get(normalized[: self.PREFIX_LENGTH], ()):
            candidates.setdefault(org.contact_id, org)

        # One matcher per connection, only the organization side swapped: difflib
        # caches its index of the second sequence, so this is the cheap way round.
        matcher = difflib.SequenceMatcher(None)
        matcher.set_seq2(normalized)
        matches = [m for org in candidates.values() if (m := self._score(normalized, tokens, org, matcher))]
        matches.sort(key=lambda m: (-m.score, m.name.lower()))
        return matches[:limit]

    def _score(self, normalized, tokens, org: _Org, matcher) -> OrgMatch | None:
        ignored = GENERIC_TOKENS | self._stop_tokens
        ours = tokens - ignored
        theirs = org.tokens - ignored
        # One name's distinguishing words all appear in the other: "Siemens"
        # inside "Siemens Healthineers". Too little text is too easy to hit.
        for smaller, larger in ((ours, org.tokens), (theirs, tokens)):
            if smaller and smaller <= larger and len("".join(smaller)) >= 4:
                return OrgMatch(org.contact_id, org.name, org.city, "partial", 0.9)
        ours_length, theirs_length = len(normalized), len(org.normalized)
        # Names this different in length cannot reach the threshold; skip the
        # expensive comparison.
        if ours_length < self.MIN_FUZZY_LENGTH or (
            2 * min(ours_length, theirs_length) < FUZZY_THRESHOLD * (ours_length + theirs_length)
        ):
            return None
        matcher.set_seq1(org.normalized)
        if matcher.quick_ratio() >= FUZZY_THRESHOLD:
            ratio = matcher.ratio()
            if ratio >= FUZZY_THRESHOLD:
                return OrgMatch(org.contact_id, org.name, org.city, "fuzzy", round(ratio, 3))
        return None


@dataclass
class CompanyPlan:
    """What promoting LinkedIn employers to organizations would do. Nothing in
    it has been written yet: `create` groups would become new organizations,
    `link` groups attach to one we already have, `ambiguous` groups share an
    exact name with several organizations and wait for a human."""
    create: list[dict]
    link: list[dict]
    ambiguous: list[dict]
    skipped_no_company: int


def plan_company_promotion(people: list[dict], organizations: list[dict]) -> CompanyPlan:
    """Group unlinked LinkedIn people by employer and decide, per employer,
    whether it needs a new organization. Pure: callers supply the rows.

    people: {id, company_raw}. organizations: {id, name, city, source, company_key}.

    Re-running after a newer export is stable: an employer we already created
    is found by its company_key, one we had before by an exact name match. Only
    an *exact* name match counts as the same organization; a partial or fuzzy
    one ("Siemens" vs "Siemens Healthineers") is a different company, reported
    as `near` on the create entry so it can be eyeballed in the preview."""
    created_before = {
        org["company_key"]: org for org in organizations
        if org.get("source") == "linkedin" and org.get("company_key")
    }
    groups: dict[str, dict] = {}
    skipped = 0
    for person in people:
        key = normalize_company(person.get("company_raw"))
        if not key:
            skipped += 1
            continue
        group = groups.setdefault(key, {"spellings": {}, "people_ids": []})
        raw = (person.get("company_raw") or "").strip()
        group["spellings"][raw] = group["spellings"].get(raw, 0) + 1
        group["people_ids"].append(person["id"])

    index = OrgIndex(organizations)
    plan = CompanyPlan(create=[], link=[], ambiguous=[], skipped_no_company=skipped)
    for key in sorted(groups):
        group = groups[key]
        # Most common spelling wins; ties go to the alphabetically first.
        name = sorted(group["spellings"].items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        entry = {"key": key, "name": name, "people_ids": group["people_ids"]}
        if key in created_before:
            org = created_before[key]
            plan.link.append({**entry, "contact_id": org["id"], "contact_name": org["name"],
                              "reason": "created_earlier"})
            continue
        matches = index.match(name)
        exact = [m for m in matches if m.confidence in ("exact", "ambiguous")]
        if len(exact) == 1:
            plan.link.append({**entry, "contact_id": exact[0].contact_id,
                              "contact_name": exact[0].name, "reason": "exact_name"})
        elif exact:
            plan.ambiguous.append({**entry, "contact_ids": [m.contact_id for m in exact]})
        else:
            near = [{"contact_id": m.contact_id, "name": m.name, "confidence": m.confidence}
                    for m in matches[:2]]
            plan.create.append({**entry, "near": near})
    return plan

