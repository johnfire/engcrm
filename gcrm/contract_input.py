"""What may be typed into a contract's fields, checked before the database sees it. Pure functions.

A refused entry raises ContractInputError (a ValueError) carrying `key`, the i18n key of a message the page can
show in the reader's language. The database repeats the limits as CHECK constraints; these checks come first so a
mistake is a readable message and not a constraint error."""
import re
from urllib.parse import urlsplit

TITLE_MAX = 200
ASSIGNMENT_MAX = 20_000
LABEL_MAX = 200
URL_MAX = 2_000

_UNSAFE_IN_URL = re.compile(r"[\s\x00-\x1f\x7f]")


class ContractInputError(ValueError):
    """An entry that is refused. `key` names the message to show."""

    def __init__(self, message: str, key: str):
        super().__init__(message)
        self.key = key


def checked_title(value) -> str:
    """The title, trimmed: 1 to TITLE_MAX characters."""
    title = (value or "").strip()
    if not title or len(title) > TITLE_MAX:
        raise ContractInputError(f"a contract needs a title of 1 to {TITLE_MAX} characters", "contractPage.error.title")
    return title


def checked_assignment(value) -> str:
    """The assignment as plain text: line ends made "\\n", trimmed, at most ASSIGNMENT_MAX characters. Blank is allowed."""
    text = (value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(text) > ASSIGNMENT_MAX:
        raise ContractInputError(f"the assignment is at most {ASSIGNMENT_MAX:,} characters", "contractPage.error.assignment")
    return text


def checked_link(label, url) -> tuple[str, str]:
    """(label, url) of a link: a label of 1 to LABEL_MAX characters and an http or https address with a host,
    at most URL_MAX characters and no spaces or control characters. javascript:, data:, ftp: and the like are refused."""
    label = (label or "").strip()
    if not label or len(label) > LABEL_MAX:
        raise ContractInputError(f"a link needs a label of 1 to {LABEL_MAX} characters", "contractPage.error.linkLabel")
    url = (url or "").strip()
    if len(url) > URL_MAX:
        raise ContractInputError(f"a link address is at most {URL_MAX} characters", "contractPage.error.linkUrlLength")
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        host = None
        parts = None
    if (parts is None or _UNSAFE_IN_URL.search(url) or parts.scheme.lower() not in ("http", "https")
            or not parts.netloc or not host):
        raise ContractInputError("a link address must start with http:// or https:// and name a host", "contractPage.error.linkUrl")
    return label, url
