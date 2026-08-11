"""Translation lookup for the web UI (German + English).

Flat, dot-namespaced keys (e.g. "nav.contacts"), loaded once from
gcrm/i18n/{en,de}.json. Deliberately hand-rolled rather than gettext/Babel —
see docs/plans/2026-07-21-i18n-design.md for the reasoning. This is entirely
separate from contacts.preferred_language / people.preferred_language, which
pick the language the AI drafts outreach in for a given business.
"""
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = ("en", "de")
DEFAULT_LANGUAGE = "en"

_I18N_DIR = Path(__file__).parent
_VAR_PATTERN = re.compile(r"\{\{(\w+)\}\}")

_catalogs: dict[str, dict[str, str]] = {}

# Every catalog file this module can ever open, fixed at import time. The path
# is chosen by lookup rather than built from the language string, so a caller
# passing "../../secrets" doesn't get a traversal — it just isn't a key. main.py
# already validates ?lang= on the way in; this makes the file read safe on its
# own terms, without depending on every future caller remembering to.
_CATALOG_PATHS = {language: _I18N_DIR / f"{language}.json" for language in SUPPORTED_LANGUAGES}


def _load_catalog(language: str) -> dict[str, str]:
    if language not in _CATALOG_PATHS:
        logger.warning("i18n: unsupported language %r, falling back to %s", language, DEFAULT_LANGUAGE)
        language = DEFAULT_LANGUAGE
    if language not in _catalogs:
        path = _CATALOG_PATHS[language]
        try:
            _catalogs[language] = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            logger.warning("i18n catalog missing: %s", path)
            _catalogs[language] = {}
    return _catalogs[language]


def _interpolate(text: str, params: dict) -> str:
    def replace(match: re.Match) -> str:
        return str(params.get(match.group(1), match.group(0)))

    return _VAR_PATTERN.sub(replace, text)


def _resolve_key(key: str, language: str, count: int | None) -> str | None:
    catalog = _load_catalog(language)
    if count is not None:
        pluralized = catalog.get(f"{key}_{'one' if count == 1 else 'other'}")
        if pluralized is not None:
            return pluralized
    return catalog.get(key)


def translate(key: str, language: str = DEFAULT_LANGUAGE, **params) -> str:
    """
    Resolve `key` in `language`, falling back to English, then to a visible
    `[key]` marker so a gap is obvious rather than silently blank.

    Pass `count=N` to pick an `_one`/`_other` pluralized variant (e.g. a key
    `capture.pendingCards_other` = "{{count}} cards waiting").
    """
    count = params.pop("count", None)
    text = _resolve_key(key, language, count)
    if text is None and language != DEFAULT_LANGUAGE:
        text = _resolve_key(key, DEFAULT_LANGUAGE, count)
    if text is None:
        logger.debug("i18n: missing key %r for language %r", key, language)
        return f"[{key}]"
    if count is not None:
        params["count"] = count
    return _interpolate(text, params) if params else text


def reload_catalogs() -> None:
    """Clear the in-memory cache. Tests use this after monkeypatching a catalog file."""
    _catalogs.clear()
