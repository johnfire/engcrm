"""Find a company's website and its address from the company name alone.

The LinkedIn export carries a company name and nothing else. This module turns
the name into a website and a postal address the way a person would: search the
web, pick the company's own site (not a directory), read its Impressum / contact
page, and take the address printed there.

Everything that touches the network is injected (`search`, `fetch_html`, and an
optional `llm`), so the logic is testable offline and a failure of any one piece
degrades to "needs a human" instead of a wrong answer. Two rules matter most:

* A wrong address is worse than a blank one. An address is only returned when it
  is *literally present in the fetched page text* (checked, not trusted), and the
  site is only accepted when its domain or its own text carries the company name.
* Anything uncertain — several plausible sites, several distinct addresses, an
  unrecognised country — comes back as candidates for a human, never a guess.

Only company data is read: the address of the registered office. Names of people
on those pages are ignored.
"""
import html as html_lib
import json
import logging
import re
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from gcrm.linkedin import GENERIC_TOKENS, normalize_company

logger = logging.getLogger(__name__)

# Sites that list companies but are not the company. Matched against the host,
# with subdomains (de.wikipedia.org -> wikipedia.org).
DIRECTORY_DOMAINS = frozenset({
    "linkedin.com", "xing.com", "facebook.com", "instagram.com", "twitter.com", "x.com",
    "youtube.com", "tiktok.com", "pinterest.com", "wikipedia.org", "wikidata.org",
    "northdata.de", "northdata.com", "firmenwissen.de", "kununu.com", "glassdoor.com",
    "glassdoor.de", "indeed.com", "stepstone.de", "monster.de", "crunchbase.com", "dnb.com",
    "zoominfo.com", "opencorporates.com", "handelsregister.de", "unternehmensregister.de",
    "bundesanzeiger.de", "cylex.de", "cylex.com", "gelbeseiten.de", "11880.com", "dasoertliche.de",
    "yelp.com", "tripadvisor.com", "bing.com", "google.com", "deutschebiz.de", "wlw.de",
    "europages.com", "europages.de", "kompass.com", "bloomberg.com", "reuters.com",
    "pitchbook.com", "moneyhouse.ch", "local.ch", "meinestadt.de", "yellowpages.com",
    "creditreform.de", "wer-zu-wem.de", "firmenauskunft.de", "unternehmen24.info",
    "companieshouse.gov.uk", "company-information.service.gov.uk", "firmenregister.de",
    "firmenverzeichnis.de", "branchenbuch.de", "marktplatz-mittelstand.de", "implisense.com",
    "ariva.de", "finanzen.net", "boerse.de", "wikimedia.org", "github.com", "medium.com",
    "researchgate.net", "academia.edu", "scholar.google.com", "amazon.com", "ebay.com",
    "trustpilot.com", "mapquest.com", "maps.google.com", "apple.com", "play.google.com",
    "grokipedia.com", "britannica.com", "wikiwand.com", "dbpedia.org", "fandom.com", "quora.com",
    "reddit.com", "alamy.com", "shutterstock.com", "issuu.com", "slideshare.net", "scribd.com",
})

CONTACT_WORDS = ("impressum", "imprint", "legal-notice", "legal notice", "kontakt", "contact",
                 "rechtliches", "anbieterkennzeichnung", "about-us", "ueber-uns", "über uns")
GUESSED_PATHS = ("/impressum", "/impressum/", "/imprint", "/kontakt", "/contact", "/de/impressum",
                 "/en/imprint", "/legal", "/about")

SEARCH_RETRIES = 2
SEARCH_PAUSE = 1.5
MAX_CANDIDATE_SITES = 2
MAX_PAGES_PER_SITE = 3
PATH_MATCH_MAX_LABEL = 5  # letters; ihk, abb, tum — not historicgermany
MIN_PAGE_TEXT = 200  # a "page" shorter than this is an error stub or a JS shell


@dataclass(frozen=True)
class Address:
    street: str
    postal_code: str
    city: str
    country: str  # ISO-3166 alpha-2, or "" when it could not be established

    def line(self) -> str:
        """'Hauptstraße 5, 86150 Augsburg' — as stored in the address column (the
        country has its own column)."""
        return ", ".join(part for part in (self.street, f"{self.postal_code} {self.city}".strip()) if part)

    def one_line(self) -> str:
        return ", ".join(part for part in (self.line(), self.country) if part)


@dataclass
class WebResult:
    """outcome: resolved | needs_review | not_found. `candidates` always carries
    what was seen, so a human can finish what the code would not guess."""
    outcome: str
    website: str = ""
    address: Address | None = None
    source_url: str = ""
    reason: str = ""
    candidates: list[dict] = field(default_factory=list)
    # False when the search never answered (empty on every retry): that says
    # nothing about the company, so the caller must not record it as "not found".
    searched: bool = True


# --- sites -------------------------------------------------------------------

def registrable_host(url: str) -> str:
    """'https://de.wikipedia.org/x' -> 'wikipedia.org'; 'https://www.acme.de' -> 'acme.de'.
    Approximate (no public-suffix list), which is enough for matching and grouping."""
    host = (urlsplit(url).hostname or "").lower()
    labels = host.split(".")
    if len(labels) >= 3 and labels[-2] in {"co", "com", "org", "gov", "ac"} and len(labels[-1]) == 2:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:]) if len(labels) >= 2 else host


def is_directory(url: str) -> bool:
    host = registrable_host(url)
    return host in DIRECTORY_DOMAINS or any(host.endswith("." + d) for d in DIRECTORY_DOMAINS)


# Words that say what kind of organization it is, not which one. They need not
# appear in its domain ("Stadt Augsburg" lives at augsburg.de), but the page must
# still carry the whole name before the site is trusted.
ORG_WORDS = frozenset({
    "stadt", "gemeinde", "landkreis", "universitaet", "university", "hochschule", "technische",
    "institut", "institute", "verband", "kliniken", "klinikum", "gruppe", "group", "holding",
    "stiftung", "verein", "bundesamt", "ministerium", "fraunhofer", "department", "college",
})


def distinctive_tokens(company_key: str) -> list[str]:
    """The words of a company name that actually identify it."""
    return [t for t in company_key.split() if len(t) > 2 and t not in GENERIC_TOKENS]


def _fold(text: str) -> str:
    """Letters and digits only, umlauts folded: 'Uni-Augsburg' -> 'uniaugsburg'."""
    return re.sub(r"[^a-z0-9]", "", _umlauts(text.lower()))


def _umlauts(text: str) -> str:
    for source, target in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(source, target)
    return text


def _parts(url: str) -> tuple[list[str], list[str]]:
    """The words a site's address is made of: the domain label split at hyphens
    (ihk-akademie-schwaben -> ihk, akademie, schwaben), and the same plus the first
    path segment (ihk.de/schwaben). Folded, with the folded whole for substring use."""
    parts = urlsplit(url)
    label = registrable_host(url).split(".")[0]
    segment = (parts.path.strip("/").split("/") or [""])[0]
    words = [_fold(w) for w in label.split("-") if _fold(w)]
    with_path = words + ([_fold(segment)] if _fold(segment) else [])
    return words, with_path


def _carries(token: str, words: list[str]) -> bool:
    """A short word must be a whole part of the address ('abb' is abb.com, not
    abbott.com); a long one may sit inside a part ('keytree' in keytreecy.com)."""
    folded = _fold(token)
    return any(w == folded for w in words) or (len(folded) >= 6 and any(folded in w for w in words))


def domain_extra(url: str, company_key: str, strict: bool = False) -> int | None:
    """None if the site's address does not carry the company's words; otherwise how
    many surplus letters it has, so the tightest match wins (ihk.de/schwaben has
    none, ihk-akademie-schwaben.de has eight). Relaxed matching ignores words
    like 'Stadt'; strict requires every distinctive word."""
    tokens = distinctive_tokens(company_key)
    if not tokens:
        return None
    label_words, path_words = _parts(url)
    if not strict and 3 <= len(tokens[0]) <= 5 and label_words == [_fold(tokens[0])]:
        return 0  # the first word is an acronym and the domain is exactly that: kfh.de
    required = tokens if strict else ([t for t in tokens if t not in ORG_WORDS] or tokens)
    wanted = len(_fold("".join(required)))  # only the words the domain must carry
    # A path segment can finish a short domain (ihk.de/schwaben) but never rescues
    # a long unrelated one (historicgermany.com/augsburg).
    candidates = [label_words] + ([path_words] if len("".join(label_words)) <= PATH_MATCH_MAX_LABEL else [])
    extras = [len("".join(words)) - wanted for words in candidates
              if all(_carries(t, words) for t in required)]
    return max(0, min(extras)) if extras else None


def domain_matches(url: str, company_key: str) -> bool:
    return domain_extra(url, company_key, strict=True) is not None


def rank_sites(results: list[dict], company_key: str) -> list[dict]:
    """Company-site candidates from search results, best first: directories are
    dropped, results are grouped by site, and sites whose address carries the
    company name come first, the tightest match leading. Each: {host, url,
    domain_match (relaxed), strict, extra, rank}."""
    sites: dict[str, dict] = {}
    for rank, result in enumerate(results):
        url = result.get("url") or ""
        if not url.startswith("http") or is_directory(url):
            continue
        host = registrable_host(url)
        site = sites.setdefault(host, {"host": host, "url": url, "rank": rank, "domain_match": False,
                                       "strict": False, "extra": 10**6})
        extra = domain_extra(url, company_key)
        if extra is not None and extra < site["extra"]:
            site.update(domain_match=True, extra=extra, url=url)
        if domain_matches(url, company_key):
            site["strict"] = True
    return sorted(sites.values(), key=lambda s: (not s["domain_match"], s["extra"], s["rank"]))


# --- pages -------------------------------------------------------------------

class _TextAndLinks(HTMLParser):
    """Visible text plus (href, anchor text) pairs. Scripts and styles dropped."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._skip = 0
        self._href: str | None = None
        self._anchor: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip += 1
        elif tag in {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "footer", "address"}:
            self.text.append("\n")
        elif tag == "a":
            self._href = dict(attrs).get("href")
            self._anchor = []

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip = max(0, self._skip - 1)
        elif tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join(self._anchor).strip()))
            self._href = None

    def handle_data(self, data):
        if self._skip:
            return
        self.text.append(data)
        if self._href is not None:
            self._anchor.append(data.strip())


def parse_page(html: str, base_url: str) -> tuple[str, list[tuple[str, str]]]:
    """-> (visible text, [(absolute url, anchor text)])."""
    parser = _TextAndLinks()
    try:
        parser.feed(html or "")
    except Exception:  # malformed HTML must not abort the lookup
        logger.debug("parse_page: malformed html from %s", base_url)
    text = html_lib.unescape("".join(parser.text))
    text = re.sub(r"[ \t\r\f\v ]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    links = []
    for href, anchor in parser.links:
        if href and not href.startswith(("mailto:", "tel:", "javascript:", "#")):
            links.append((urljoin(base_url, href), anchor))
    return text, links


def contact_urls(site_url: str, links: list[tuple[str, str]], found_urls: list[str]) -> list[str]:
    """Pages likely to carry the address, best first: URLs the search returned for
    this site that look like Impressum/contact pages, links on the page that say
    so, then conventional paths. Same site only."""
    host = registrable_host(site_url)
    seen, ordered = set(), []

    def add(url: str):
        url = url.split("#")[0]
        if url not in seen and registrable_host(url) == host and not is_directory(url):
            seen.add(url)
            ordered.append(url)

    for url in found_urls:
        if any(word in url.lower() for word in CONTACT_WORDS):
            add(url)
    ranked = []
    for url, anchor in links:
        label = f"{url} {anchor}".lower()
        for position, word in enumerate(CONTACT_WORDS):
            if word in label:
                ranked.append((position, url))
                break
    for _, url in sorted(ranked):
        add(url)
    base = f"{urlsplit(site_url).scheme}://{urlsplit(site_url).netloc}"
    for path in GUESSED_PATHS:
        add(base + path)
    return ordered


# --- addresses ---------------------------------------------------------------

_STREET_WORDS = (r"str(?:\.|a(?:ß|ss)e)|weg|platz|allee|gasse|ring|damm|ufer|hof|park|chaussee|"
                 r"steig|pfad|markt|brücke|bruecke|zeile|berg|promenade|kai")
# 5-digit (DE) or 4-digit (AT/CH) postal code followed by a town.
_PLZ_CITY = re.compile(
    r"(?<![\d/.,-])(?P<pre>D-|A-|CH-)?(?P<plz>\d{5}|\d{4})\s+(?P<city>[A-ZÄÖÜ][A-Za-zÄÖÜäöüß.\-]+"
    r"(?:[ \-/][A-ZÄÖÜa-zäöüß.\-]+){0,3})")
_JUNK_CITY = re.compile(r"alle rechte|rights|reserved|copyright|vorbehalten|datenschutz|cookie", re.IGNORECASE)
_CITY_STOP = re.compile(
    r"\b(?:Tel|Telefon|Fon|Fax|Mobil|E-?Mail|Email|Web|www|http|USt|Ust-?Id|Handelsregister|"
    r"Amtsgericht|HRB|HRA|Gesch[äa]ftsf[üu]hr|Vertreten|Vorstand|Inhaber|Registergericht|"
    r"Deutschland|Germany|Österreich|Austria|Schweiz|Switzerland|Steuer|Umsatzsteuer|Sitz|"
    r"Verantwortlich|Telefax|Postfach|Mail)\b.*$", re.IGNORECASE)
_STREET_BEFORE = re.compile(
    r"([A-ZÄÖÜ][\wäöüßÄÖÜ.\-]*(?:[ \-][\wäöüßÄÖÜ.\-]+){0,3}?\s?(?:" + _STREET_WORDS +
    r")\s?\d+\s?[a-zA-Z]?(?:\s?[-/–]\s?\d+\s?[a-zA-Z]?)?)\s*[,;|]?\s*(?:D-|A-|CH-)?$", re.IGNORECASE)
_COUNTRY_WORDS = {"DE": ("deutschland", "germany"), "AT": ("österreich", "austria", "oesterreich"),
                  "CH": ("schweiz", "switzerland", "suisse", "svizzera")}


_LINE_COUNTRY = re.compile(r"\b(?:A|CH)-\d{4}\b|österreich|oesterreich|austria|schweiz|switzerland|suisse",
                          re.IGNORECASE)


def _four_digit_ok(host: str, line: str) -> bool:
    """4-digit postal codes exist (Austria, Switzerland), but so do years, house
    numbers and report titles ("2025 Gartner Magic Quadrant"). One only counts when
    the site is .at/.ch or the *same line* names the country or carries an A-/CH-
    prefix — a country mentioned anywhere else on the page proves nothing."""
    return host.rsplit(".", 1)[-1] in {"at", "ch"} or bool(_LINE_COUNTRY.search(line))


# A German-law Impressum with a five-digit postal code is Germany: France, Italy
# and Spain print "mentions légales" / "note legali" / "aviso legal", and none of
# them has a Registergericht or a Geschäftsführer.
_DE_EVIDENCE = re.compile(
    r"\bDE\s?\d{9}\b|amtsgericht|handelsregister|registergericht|gesch[äa]ftsf[üu]hr|"
    r"vertretungsberechtigt|\bimpressum\b|angaben gem[äa](?:ß|ss) § ?5", re.IGNORECASE)


def _country_for(plz: str, host: str, text: str) -> str:
    """5 digits is Germany *or* France/Italy/Spain, 4 digits Austria *or* Switzerland
    (and others): the postal code alone proves nothing, so a country is only
    named when the site's domain or its own text says so."""
    lowered = text.lower()
    for code, words in _COUNTRY_WORDS.items():
        if any(word in lowered for word in words) and len(plz) == (5 if code == "DE" else 4):
            return code
    suffix = host.rsplit(".", 1)[-1]
    if len(plz) == 5 and (suffix == "de" or _DE_EVIDENCE.search(text)):
        return "DE"
    if suffix in {"at", "ch"} and len(plz) == 4:
        return suffix.upper()
    return ""


def find_addresses(text: str, host: str = "") -> list[Address]:
    """Every 'postal code + town' in the text, with the street printed just before
    it, most frequent first. Deterministic and conservative; the country comes
    from evidence on the page or the domain, not from the digit count."""
    found: Counter = Counter()
    first_seen: dict[tuple, int] = {}
    lines = text.split("\n")
    for index, line in enumerate(lines):
        for match in _PLZ_CITY.finditer(line):
            plz = match.group("plz")
            if len(plz) == 4 and not _four_digit_ok(host, line):
                continue
            before = line[: match.start()].rstrip()
            if len(plz) == 4 and re.search(r"(?:©|\(c\)|copyright|&copy;)\s*$", before, re.IGNORECASE):
                continue
            city = _CITY_STOP.sub("", match.group("city")).strip(" .,-/")
            city = " ".join(city.split()[:3]).strip(" .,-/")
            if len(city) < 2 or _JUNK_CITY.search(city):
                continue
            street_match = _STREET_BEFORE.search(before)
            if not street_match and not before.strip() and index > 0:
                # Impressum layouts often put the street on the line above the town.
                street_match = _STREET_BEFORE.search(lines[index - 1].rstrip())
            street = street_match.group(1).strip() if street_match else ""
            key = (street, plz, city, match.group("pre") or "")
            found[key] += 1
            first_seen.setdefault(key, len(first_seen))
    ordered = sorted(found, key=lambda k: (-bool(k[0]), -found[k], first_seen[k]))
    prefix_country = {"D-": "DE", "A-": "AT", "CH-": "CH"}
    return [Address(street, plz, city, prefix_country.get(pre) or _country_for(plz, host, text))
            for street, plz, city, pre in ordered]


def address_in_text(address: Address, text: str) -> bool:
    """Verification, not trust: the postal code and the town really appear."""
    squashed = re.sub(r"\s+", " ", text)
    return address.postal_code in squashed and address.city.split()[0] in squashed


# --- LLM fallback (other countries) ------------------------------------------

def llm_prompt(company: str, text: str) -> tuple[str, str]:
    system = (
        "You read the Impressum / contact page of a company website and report the company's "
        "postal address (registered office or main office). Reply with ONLY a JSON object: "
        '{"street": str|null, "postal_code": str|null, "city": str|null, '
        '"country": ISO 3166-1 alpha-2 code|null}. Use only text that appears on the page. '
        "Ignore the names and addresses of individual people. If there is no clear company "
        "address, return nulls. Never guess."
    )
    return system, f"Company: {company}\n\nPage text:\n{text[:6000]}"


def parse_llm_address(raw: str, text: str) -> Address | None:
    """The model's answer, kept only if it is well-formed *and* its postal code and
    town are literally on the page."""
    try:
        data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    except (ValueError, TypeError):
        return None
    city, plz = (data.get("city") or "").strip(), (data.get("postal_code") or "").strip()
    if not city or not plz:
        return None
    country = (data.get("country") or "").strip().upper()
    address = Address((data.get("street") or "").strip(), plz, city,
                      country if re.fullmatch(r"[A-Z]{2}", country) else "")
    return address if address_in_text(address, text) else None


# --- the lookup --------------------------------------------------------------

Search = Callable[[str], list[dict]]
FetchHtml = Callable[[str], tuple[str, str]]  # url -> (final url, html); ("", "") on failure
LlmAddress = Callable[[str, str], "Address | None"]  # company, page text -> address


def search_with_retry(search: Search, query: str, sleep=time.sleep) -> list[dict]:
    """Searching is flaky: the same query can be empty now and fine a moment later,
    and the search tool reports both as 'no results'. Try again before believing it."""
    for attempt in range(SEARCH_RETRIES + 1):
        results = search(query)
        if results:
            return results
        if attempt < SEARCH_RETRIES:
            sleep(SEARCH_PAUSE * (attempt + 1))
    return []


def name_near_address(company_key: str, text: str, address: "Address", before: int = 600,
                      after: int = 40) -> bool:
    """Is the company's name printed next to this address? An umbrella body's
    Impressum names many institutes; the address belongs to the one beside it.
    An Impressum prints the name first and the address after it, so the window
    reaches well before the postal code and barely past it (what follows is often a
    list of other bodies). Looks around each place the postal code and town appear."""
    anchor = f"{address.postal_code} {address.city.split()[0]}"
    start = 0
    while (pos := text.find(anchor, start)) != -1:
        if name_on_page(company_key, text[max(0, pos - before): pos + len(anchor) + after]):
            return True
        start = pos + 1
    return False


def is_contact_page(url: str, text: str) -> bool:
    """An Impressum / contact page, by its address or its heading. Addresses printed
    elsewhere (articles, listings, footers of unrelated pages) are not the company's."""
    head = text[:300].lower()
    return any(word in url.lower() or word in head for word in CONTACT_WORDS)


def name_on_page(company_key: str, text: str) -> bool:
    """Does the page itself say the company's whole name? A second, independent
    sign that the site belongs to the company (the first being its domain). The
    name must appear as a run of words, with 'und', 'e.V.', 'GmbH' and the like
    ignored on both sides; the words scattered over a page prove nothing."""
    return bool(company_key) and f" {company_key} " in f" {normalize_company(text)} "


def lookup_company(
    name: str,
    search: Search,
    fetch_html: FetchHtml,
    llm_address: LlmAddress | None = None,
    sleep=time.sleep,
) -> WebResult:
    """Website and address for one company name. Never raises: a failing search or
    fetch makes the result weaker (`needs_review` / `not_found`), not wrong."""
    key = normalize_company(name)
    if not key:
        return WebResult("not_found", reason="no usable company name")

    results: list[dict] = []
    seen_urls: set[str] = set()
    for query in (name, f"{name} Impressum"):
        for result in search_with_retry(search, query, sleep):
            if result.get("url") not in seen_urls:
                seen_urls.add(result.get("url"))
                results.append(result)
        # One query usually finds the company's own site; ask again only if it did not.
        if any(site["domain_match"] for site in rank_sites(results, key)):
            break
        sleep(0.5)
    if not results:
        return WebResult("not_found", reason="the search returned nothing", searched=False)
    sites = rank_sites(results, key)
    if not sites:
        return WebResult("not_found", reason="the search found no company website")

    candidates = [{"website": s["url"], "domain_match": s["domain_match"]} for s in sites[:4]]
    read = [(site, _read_site(name, key, site, results, fetch_html, llm_address))
            for site in sites[:MAX_CANDIDATE_SITES]]
    if not any(o.outcome == "resolved" for _, o in read) and len(sites) > MAX_CANDIDATE_SITES:
        site = sites[MAX_CANDIDATE_SITES]  # the right one is sometimes ranked third
        read.append((site, _read_site(name, key, site, results, fetch_html, llm_address)))
    resolved = [(site, outcome) for site, outcome in read if outcome.outcome == "resolved"]
    if resolved:
        site, outcome = resolved[0]
        outcome.candidates = candidates
        distinct = {(o.address.postal_code, o.address.city) for _, o in resolved}
        if len(distinct) > 1:
            # Sites that disagree: the one whose domain *is* the company name
            # (no surplus letters) is more trustworthy than one that merely
            # contains it. If exactly one such site resolved, it wins; otherwise a
            # human decides.
            exact = [(s_, o) for s_, o in resolved if s_["extra"] == 0]
            if len(exact) == 1:
                site, outcome = exact[0]
                outcome.candidates = candidates
                return outcome
            return WebResult("needs_review", outcome.website, outcome.address, outcome.source_url,
                             "the company's websites give different addresses", candidates)
        return outcome
    # Nothing certain. Prefer the attempt that found an address, then the first.
    best = next((o for _, o in read if o.address), read[0][1])
    best.candidates = candidates
    if best.outcome == "not_found":
        best.outcome, best.website = "needs_review", best.website or sites[0]["url"]
    return best


def _site_root(site_url: str, fetched_url: str, company_key: str) -> str:
    """The address to store as the company's website: the main host, plus the first path
    segment when the company lives under one — only when the domain alone does not
    carry the name but domain + path does (ihk.de/schwaben)."""
    parts = urlsplit(fetched_url or site_url)
    # The main site, not whichever portal subdomain the search happened to return.
    root = f"{parts.scheme or 'https'}://{registrable_host(fetched_url or site_url)}/"
    segment = (urlsplit(site_url).path.strip("/").split("/") or [""])[0]
    tokens = distinctive_tokens(company_key)
    required = [t for t in tokens if t not in ORG_WORDS] or tokens
    label_words, path_words = _parts(site_url)
    if (segment and required and all(_carries(t, path_words) for t in required)
            and not all(_carries(t, label_words) for t in required)):
        return f"{root}{segment}/"
    return root


def _read_site(name, key, site, results, fetch_html, llm_address) -> WebResult:
    """Fetch a candidate site's homepage and contact pages and look for the address."""
    home_url, home_html = fetch_html(site["url"])
    home_url = home_url or site["url"]
    home_text, links = parse_page(home_html, home_url) if home_html else ("", [])
    website = _site_root(site["url"], home_url, key)
    found = [r["url"] for r in results if registrable_host(r.get("url") or "") == site["host"]]

    texts = []
    for url in contact_urls(home_url, links, found)[:MAX_PAGES_PER_SITE]:
        if url == home_url:
            continue
        final_url, page_html = fetch_html(url)
        if not page_html:
            continue
        text, _ = parse_page(page_html, final_url or url)
        if len(text) >= MIN_PAGE_TEXT:
            texts.append((final_url or url, text))
    # The Impressum / contact pages are authoritative about where the company is;
    # a homepage footer is only the last resort (it may show another office).
    if len(home_text) >= MIN_PAGE_TEXT:
        texts.append((home_url, home_text))

    if not texts:
        return WebResult("needs_review", website, reason="the site could not be read")
    host = urlsplit(website).hostname or ""

    weak: WebResult | None = None  # an address we found but may not vouch for
    for url, text in texts:
        # The page that prints the address must itself name the company (or the
        # domain must): a name elsewhere on the site proves nothing about this address.
        contact_page = is_contact_page(url, text)
        addresses = find_addresses(text, host)
        if addresses:
            primary, distinct = addresses[0], {(a.postal_code, a.city) for a in addresses}
            if len(distinct) > 1 and not primary.street:
                continue  # a page that lists several towns and no street: try the next page
            if not contact_page and not primary.street:
                continue  # outside an Impressum / contact page only a full street address counts
            vouched = site["strict"] or (contact_page and name_near_address(key, text, primary))
            if not vouched:
                weak = weak or WebResult("needs_review", website, primary, url,
                                         "the site does not carry the company name")
                continue
            if not primary.country:
                return WebResult("needs_review", website, primary, url,
                                 "the country could not be established")
            return WebResult("resolved", website, primary, url)
        vouched = site["strict"] or (contact_page and name_on_page(key, text))
        if llm_address and vouched:
            address = llm_address(name, text)
            if address:
                return (WebResult("resolved", website, address, url) if address.country else
                        WebResult("needs_review", website, address, url,
                                  "the country could not be established"))
    if weak:
        return weak
    return WebResult("needs_review", website, reason="no address found on the site's pages")
