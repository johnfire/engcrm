"""
Read-only data-quality audit of the contacts table. Changes nothing.

    uv run python scripts/audit_contact_data.py

Five checks, each for a failure this CRM has actually suffered:

  1. unfetchable website  — a value with no http(s) scheme is rejected by the
     SSRF guard, so every fetch for that contact silently returns "". 18 rows
     were in this state, including the one an opportunity analysis was failing on.
  2. name/domain mismatch — the recorded website may not be the business's own
     (a trade directory listed as 13 different electricians' site).
  3. shared domain        — one domain across several contacts marks a chain,
     portal or group site rather than the individual business.
  4. email/website mismatch — usually benign (same firm, second domain), but it
     is how a city-hall address on a Gruenderzentrum was spotted.
  5. odd stage/status pair — a combination outside the expected ones, e.g. a
     candidate carrying a proposal. Legal and sometimes correct; worth a look.

Checks 2 and 4 are heuristics and report false positives by design: German firms
trade under initials (kl-mw.de for KL Mechanische Werkstaette) and municipally
run hubs legitimately publish their operator's address. Read the output, do not
bulk-act on it.
"""
import re
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from gcrm.db.connection import db  # noqa: E402
from gcrm.organization_state import is_typical  # noqa: E402

UMLAUT = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
LEGAL = {"gmbh", "ag", "kg", "ohg", "gbr", "mbh", "ug", "eg", "ek", "co", "und",
         "the", "gesellschaft", "inhaber", "filiale", "niederlassung"}
# Consumer mailboxes: a personal provider address is normal for a small firm,
# not evidence that the email belongs to someone else.
FREEMAIL = {"gmail.com", "t-online.de", "web.de", "gmx.de", "gmx.net", "gmx.at",
            "googlemail.com", "outlook.de", "hotmail.com", "aol.com", "yahoo.de",
            "icloud.com", "freenet.de", "a1.net", "aon.at", "utanet.at", "sbg.at"}


def norm(text: str) -> str:
    return (text or "").lower().translate(UMLAUT)


def domain_of(url: str) -> str:
    return norm(url).split("//")[-1].split("/")[0].removeprefix("www.")


def domain_blob(domain: str) -> str:
    parts = domain.split(".")
    core = ".".join(parts[:-1]) if len(parts) > 1 else domain
    return re.sub(r"[^a-z0-9]", "", core)


def name_tokens(name: str) -> set[str]:
    return {w for w in re.split(r"[^a-z0-9]+", norm(name)) if len(w) >= 3 and w not in LEGAL}


def acronyms(name: str) -> set[str]:
    """German firms often trade under initials; without this the audit reports
    kl-mw.de for 'KL Mechanische Werkstaette' as a mismatch."""
    words = [w for w in re.split(r"[^a-z0-9]+", norm(name)) if w and w not in LEGAL]
    initials = "".join(w[0] for w in words)
    found = {initials[i:j] for i in range(len(initials))
             for j in range(i + 2, min(i + 6, len(initials)) + 1)}
    found |= {w for w in words if len(w) <= 3}
    return {a for a in found if len(a) >= 2}


def name_matches_domain(name: str, url: str) -> bool:
    blob = domain_blob(domain_of(url))
    if not blob:
        return False
    if any(t in blob or blob in t for t in name_tokens(name)):
        return True
    return any(a in blob for a in acronyms(name))


def same_org(a: str, b: str) -> bool:
    ca, cb = domain_blob(a), domain_blob(b)
    if ca and cb and (ca in cb or cb in ca):
        return True
    ta = {t for t in re.split(r"[^a-z0-9]+", norm(a)) if len(t) >= 4}
    tb = {t for t in re.split(r"[^a-z0-9]+", norm(b)) if len(t) >= 4}
    return bool(ta & tb)


def section(title: str, rows: list[str], note: str = "") -> None:
    print(f"\n=== {title}: {len(rows)} ===")
    if note:
        print(f"    {note}")
    for line in rows[:20]:
        print(f"  {line}")
    if len(rows) > 20:
        print(f"  ... and {len(rows) - 20} more")


def main() -> int:
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name, website, email, pipeline_stage, status "
                    "FROM contacts WHERE deleted_at IS NULL ORDER BY id")
        organizations = [dict(r) for r in cur.fetchall()]

    with_site = [c for c in organizations if (c["website"] or "").strip()]
    print(f"contacts: {len(organizations)}   with a website: {len(with_site)}")

    unfetchable = [
        f"[{c['id']:>4}] {(c['name'] or '')[:30]:<30} {c['website']!r}"
        for c in with_site
        if urlparse(c["website"].strip()).scheme not in ("http", "https")
    ]
    section("UNFETCHABLE WEBSITE (no http/https scheme)", unfetchable,
            "every fetch for these silently returns empty")

    mismatched = [
        f"[{c['id']:>4}] {(c['name'] or '')[:30]:<30} {domain_of(c['website'])[:40]}"
        for c in with_site if not name_matches_domain(c["name"], c["website"])
    ]
    section("NAME / DOMAIN MISMATCH", mismatched,
            "heuristic — abbreviations are allowed for, but check before acting")

    by_domain = defaultdict(list)
    for c in with_site:
        by_domain[domain_of(c["website"])].append(c)
    shared = sorted(((d, cs) for d, cs in by_domain.items() if len(cs) > 1),
                    key=lambda kv: -len(kv[1]))
    section("DOMAIN SHARED BY SEVERAL CONTACTS", [
        f"{len(cs):>3}x  {d[:40]:<40} e.g. {cs[0]['name'][:28]}" for d, cs in shared
    ], "a chain, portal or directory rather than each business's own site")

    odd_state = [
        f"[{c['id']:>4}] {(c['name'] or '')[:30]:<30} {c['pipeline_stage']} / {c['status']}"
        for c in organizations if not is_typical(c["pipeline_stage"], c["status"])
    ]
    section("UNUSUAL STAGE / STATUS COMBINATION", odd_state,
            "allowed, but rarely what you meant — check the ones you did not set by hand")

    email_diff = []
    for c in with_site:
        mail = (c["email"] or "").split("@")[-1].lower().translate(UMLAUT)
        if not mail or mail in FREEMAIL:
            continue
        site = domain_of(c["website"])
        if ".".join(site.split(".")[-2:]) == ".".join(mail.split(".")[-2:]):
            continue
        tag = "same org?" if same_org(site, mail) else "UNRELATED"
        email_diff.append(f"[{c['id']:>4}] {(c['name'] or '')[:26]:<26} {site[:26]:<26} "
                          f"-> @{mail[:22]:<22} {tag}")
    section("EMAIL DOMAIN != WEBSITE DOMAIN", email_diff,
            "municipally run hubs legitimately publish their operator's address")
    return 0


if __name__ == "__main__":
    sys.exit(main())
