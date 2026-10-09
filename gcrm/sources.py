"""How an organization or person came to exist (`contacts.source`, `people.source`).

Every creation path names its source; `require_source` refuses a blank one, so a new
path cannot leave the origin unrecorded. Labels for each value are the i18n keys
`source.<value>` on the web and `source.<value>` in the mobile app.
"""

# Created by the user, from the phone or the website.
MANUAL_MOBILE = "manual_mobile"
MANUAL_WEB = "manual_web"
VOICE = "voice"
# Created from a photo.
CARD_CAPTURE = "card_capture"
DOCUMENT_CAPTURE = "document_capture"
SIGN_SCAN = "sign_scan"
# Created by an automated search or import.
RESEARCH_AGENT = "research_agent"
MAPS_IMPORT = "maps_import"
SIGN_RESEARCH = "sign_research"
STUDIES_IMPORT = "studies_import"
LINKEDIN = "linkedin"
LINKEDIN_IMPORT = "linkedin_import"
# Older rows from before the web/mobile split; the form used is not known.
MANUAL = "manual"

# Values with a display label. Directory imports carry a dated name
# (bavaria_directory_2026-08-19) and are labelled by their prefix.
KNOWN_SOURCES = (
    MANUAL_MOBILE, MANUAL_WEB, VOICE, CARD_CAPTURE, DOCUMENT_CAPTURE, SIGN_SCAN,
    RESEARCH_AGENT, MAPS_IMPORT, SIGN_RESEARCH, STUDIES_IMPORT, LINKEDIN, LINKEDIN_IMPORT, MANUAL,
)
DIRECTORY_IMPORT_PREFIX = "bavaria_directory"


def require_source(source: str) -> str:
    if not isinstance(source, str) or not source.strip():
        raise ValueError("source is required: say how this record was created")
    return source.strip()


def label_key(source: str | None) -> str:
    """The i18n key suffix for a stored source; anything unrecognized reads as unknown."""
    if source in KNOWN_SOURCES:
        return source
    if source and source.startswith(DIRECTORY_IMPORT_PREFIX):
        return "directory_import"
    return "unknown"
