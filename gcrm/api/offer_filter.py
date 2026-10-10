"""Which offer a list shows: one offer's pipeline, or every offer at once.

The web remembers the choice per browser session, so the Organizations, People
and Contacts lists open on the pipeline you were last looking at. The phone API
has no memory and keeps its old meaning by default: no `offer` means Consulting,
because the app installed before offers existed expects exactly that."""
from gcrm.tools.db_deals import CONSULTING
from gcrm.tools.db_offers import list_offers

ALL = "all"
SESSION_KEY = "offer_filter"


def _known(workspace_id: int | None) -> list[dict]:
    return list_offers(workspace_id, include_archived=True)


def web_offer_filter(request, offer: str | None) -> tuple[str | None, list[dict]]:
    """(slug or None for every offer, the active offers for the picker). An
    explicit `offer` is remembered; without one the remembered choice applies."""
    workspace_id = request.session.get("workspace_id")
    known = _known(workspace_id)
    slugs = {o["slug"] for o in known}
    if offer is not None:
        choice = offer if offer in slugs else ALL
        request.session[SESSION_KEY] = choice
    else:
        choice = request.session.get(SESSION_KEY, ALL)
        if choice != ALL and choice not in slugs:
            choice = ALL
    return (None if choice == ALL else choice), [o for o in known if not o["archived"]]


def api_offer_filter(offer: str | None, workspace_id: int | None) -> str | None:
    """The phone's `offer` parameter: absent means Consulting, 'all' every offer,
    anything else must be an offer of the workspace (else ValueError)."""
    if offer is None or offer == "":
        return CONSULTING
    if offer == ALL:
        return None
    if offer not in {o["slug"] for o in _known(workspace_id)}:
        raise ValueError(f"unknown offer: {offer!r}")
    return offer
