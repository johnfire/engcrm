"""The phone colours the private ratings like the web does
(engcrm-mobile/services/ratingTones.ts): the same tone per rating as the server's
template globals, and the same colour per tone as the stylesheet."""
import re
from pathlib import Path

from gcrm.api.templates import templates

ROOT = Path(__file__).resolve().parent.parent
TONES_TS = ROOT / "engcrm-mobile" / "services" / "ratingTones.ts"
STYLE_CSS = ROOT / "gcrm" / "ui" / "static" / "style.css"


def phone_block(constant: str) -> str:
    return re.search(rf"export const {constant}\b.*?= \{{(.*?)\n\}};", TONES_TS.read_text(), re.S).group(1)


def phone_tones(constant: str) -> dict[int, str]:
    return {int(m.group(1)): m.group(2) for m in re.finditer(r'(\d+): "(\w+)"', phone_block(constant))}


def test_priority_tones_match_the_web():
    assert phone_tones("PRIORITY_TONE") == templates.env.globals["priority_tone"]


def test_value_tones_match_the_web():
    assert phone_tones("VALUE_TONE") == templates.env.globals["value_tone"]


def test_tone_colours_match_the_stylesheet():
    phone = {
        m.group(1): (m.group(2), m.group(3), m.group(4))
        for m in re.finditer(
            r'(\w+): \{ fill: "(#\w+)", line: "(#\w+)", text: "(#\w+)" \}', phone_block("TONE_COLOURS"),
        )
    }
    web = {
        m.group(1): (m.group(2), m.group(3), m.group(4))
        for m in re.finditer(
            r"\.tone-(\w+)\s*\{ --tone: (#\w+); --tone-line: (#\w+); --on-tone: (#\w+); \}", STYLE_CSS.read_text(),
        )
    }
    assert phone == web
    assert len(phone) == 6
