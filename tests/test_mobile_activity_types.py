"""The phone names logged activities like the web does: its method -> activity type
map (engcrm-mobile/services/activityTypes.ts) must equal the server's."""
import re
from pathlib import Path

from gcrm.activity_types import _METHOD_TYPES

TYPES_TS = Path(__file__).resolve().parent.parent / "engcrm-mobile" / "services" / "activityTypes.ts"


def test_method_types_match_the_server():
    block = re.search(r"export const METHOD_TYPES\b.*?= \{(.*?)\n\};", TYPES_TS.read_text(), re.S).group(1)
    phone = {m.group(1): m.group(2) for m in re.finditer(r'(\w+): "(\w+)"', block)}
    assert phone == _METHOD_TYPES
