"""Items for the browser pin loop (scripts/maps/pin_loop.js), built from CRM rows.

Pure functions. A company with coordinates is matched in Maps by distance (within 500 m
by default); one without is matched by address, so its item carries the address, the
postcode, the website's host and the city for the loop to check the Maps card against.
"""
import re
from urllib.parse import urlsplit

_POSTCODE = re.compile(r"\b(\d{5})\b")
_REMARK = re.compile(r"\s+(?:[—–]|\(|/)\s*")  # "Name — remark", "Name (remark)", "Name / remark"


def postcode(address: str | None) -> str | None:
    match = _POSTCODE.search(address or "")
    return match.group(1) if match else None


def site_host(website: str | None) -> str | None:
    text = (website or "").strip()
    if not text:
        return None
    host = urlsplit(text if "://" in text else f"http://{text}").hostname or ""
    return host.removeprefix("www.") or None


def core_name(name: str) -> str | None:
    """'FRISTO SE' from 'FRISTO SE — Zentrale / Zentrallager'; None when there is no remark."""
    core = _REMARK.split(name, maxsplit=1)[0].strip()
    return core if core and core != name.strip() else None


def loop_item(row: dict) -> dict:
    item = {"id": row["id"], "name": row["name"]}
    if core_name(row["name"]):
        item["alias"] = core_name(row["name"])
    if row.get("city"):
        item["city"] = row["city"]
    if row.get("latitude") is not None and row.get("longitude") is not None:
        return {**item, "lat": row["latitude"], "lon": row["longitude"]}
    item["addr"] = row.get("address") or ""
    extras = {"plz": postcode(row.get("address")), "site": site_host(row.get("website"))}
    return {**item, **{key: value for key, value in extras.items() if value}}
