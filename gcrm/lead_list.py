"""Read a lead list into businesses and people — plain parsing, no LLM.

A lead list is the Markdown master table described in
~/ai-workzone/marketing-leads/HOWTO-city-lead-lists.md, produced by research done in a chat
app (Claude Desktop, ChatGPT) on a subscription:

    | Pg | # | Business | Location | Address | Website | Contact | Role | LinkedIn | LinkedIn status | Notes |

One row per person; a business with no person is one row with "—" as the contact. Rows of
the same business (same name and address) become one company with several people. Anything
that does not fit the format is reported, never guessed.
"""
import re

COLUMNS = ("Pg", "#", "Business", "Location", "Address", "Website", "Contact", "Role",
           "LinkedIn", "LinkedIn status", "Notes")
EMPTY = {"", "—", "-", "–"}
EMPTY_MARKS = ("—", "–")
_HEADER = re.compile(r"^\|\s*Pg\s*\|\s*#\s*\|\s*Business\s*\|")
_LINK = re.compile(r"\[(profile|candidate)\]\((https?://[^)\s]+)\)")
_POSTCODE_TOWN = re.compile(r"\b(\d{5})\s+([^\W\d][\w .'-]*?)\s*(?=[(;,]|$)")
_TOWN_ONLY = re.compile(r"^[^\W\d][\w .'-]*$")


class LeadListError(ValueError):
    """The file is not a lead list in the master format, or a row does not fit it."""


def is_unknown_address(address: str | None) -> bool:
    """'—', '— (possibly …)', 'address unknown': the research could not place it."""
    text = (address or "").strip()
    return not text or text[0] in EMPTY_MARKS or text.lower().startswith("address unknown")


def split_address(address: str | None) -> tuple[str | None, str | None]:
    """('86807', 'Buchloe') from 'Rudolf-Diesel-Str. 10, 86807 Buchloe (Geb. 9)'. Without a
    postcode, a last part that is only a word is the town ('Hartmähderweg 11, Kaufbeuren')."""
    if is_unknown_address(address):
        return None, None
    text = address.strip()
    match = _POSTCODE_TOWN.search(text)
    if match:
        return match.group(1), match.group(2).strip()
    last_part = text.rsplit(",", 1)[-1].strip()
    return (None, last_part) if _TOWN_ONLY.match(last_part) else (None, None)


def _value(cell: str) -> str:
    return "" if cell.strip() in EMPTY else cell.strip()


def _website(cell: str) -> str:
    site = _value(cell)
    return site if not site or "://" in site else f"https://{site}"


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _table_rows(markdown: str) -> list[list[str]]:
    lines = markdown.splitlines()
    start = next((index for index, line in enumerate(lines) if _HEADER.match(line)), None)
    if start is None:
        raise LeadListError("no master table found: expected a header starting '| Pg | # | Business |'")
    rows = []
    for line in lines[start + 2:]:
        if not line.strip().startswith("|"):
            break
        cells = _cells(line)
        if len(cells) < len(COLUMNS):
            raise LeadListError(f"row {len(rows) + 1} has {len(cells)} cells, expected {len(COLUMNS)}: {line[:80]}")
        # Notes is the last column and may itself contain '|' (a copied headline): keep it whole.
        rows.append(cells[:len(COLUMNS) - 1] + [" | ".join(cells[len(COLUMNS) - 1:])])
    return rows


def _person(row: dict) -> dict | None:
    name = _value(row["Contact"])
    if not name:
        return None
    links = dict(_LINK.findall(row["LinkedIn"]))
    status = _value(row["LinkedIn status"])
    return {"name": name, "role": _value(row["Role"]), "linkedin_url": links.get("profile"),
            "linkedin_candidate": links.get("candidate"), "linkedin_status": status,
            "connected": status == "connected", "notes": _value(row["Notes"])}


def parse_lead_list(markdown: str) -> list[dict]:
    """The businesses of a lead list, in table order, each with its people."""
    businesses: dict[tuple[str, str], dict] = {}
    for cells in _table_rows(markdown):
        row = dict(zip(COLUMNS, cells))
        name, address = _value(row["Business"]), _value(row["Address"])
        if not name:
            continue
        if is_unknown_address(address):
            address, unknown = "", address
        else:
            unknown = ""
        business = businesses.setdefault((name.lower(), address.lower()), {
            "name": name, "address": address, "postcode": split_address(address)[0],
            "city": split_address(address)[1], "area": _value(row["Location"]),
            "website": _website(row["Website"]), "notes": [], "people": [],
        })
        for note in (f"Address: {unknown}" if unknown else "", _value(row["Notes"])):
            if note and note not in business["notes"]:
                business["notes"].append(note)
        person = _person(row)
        if person:
            business["people"].append(person)
    return [{**business, "notes": "\n".join(business["notes"])} for business in businesses.values()]
