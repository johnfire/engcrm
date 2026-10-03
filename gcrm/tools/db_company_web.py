"""Storage and runner for website + address lookups of LinkedIn-created
organizations (see gcrm.company_web for how one company is looked up).

Every outcome is cached per company, so nothing is searched twice. A search that
never answered is *not* recorded, so a throttled run cannot turn real companies
into "not found". One company failing never stops the others.
"""
import logging
import time
from collections.abc import Callable

from psycopg2.extras import Json

from gcrm.company_web import Address, WebResult, lookup_company
from gcrm.db.connection import db
from gcrm.tools.db_audit import log_audit
from gcrm.tools.search import fetch_html, web_search

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3            # a not_found is retried this many times in total
RETRY_AFTER = "1 day"       # ...no sooner than this after the last try
UNANSWERED_STOP = 3         # searches that never answered, in a row, end the run
WEB_LOOKUP_MAX = 20         # most companies one browser click may start
DEFAULT_SECONDS = 100       # a click stops starting new companies after this long
LOCK_KEY = 7_340_012

_NEEDS_CITY = (
    "c.source = 'linkedin' AND c.city_status = 'needs_review' AND c.deleted_at IS NULL "
    "AND c.company_key IS NOT NULL"
)


def _retryable() -> str:
    return (f"(l.outcome = 'not_found' AND l.attempts < {MAX_ATTEMPTS} "
            f"AND l.looked_up_at < NOW() - INTERVAL '{RETRY_AFTER}')")


def count_web_work() -> dict:
    """What a run would do: `to_lookup` companies never searched, `retry` earlier
    not-founds due another try, `review` readings waiting for a human to accept,
    `cached_ready` accepted readings not yet applied to an organization."""
    with db() as conn:
        cur = conn.cursor()

        def count(extra_join: str, where: str) -> int:
            cur.execute(f"SELECT COUNT(DISTINCT c.company_key) AS n FROM contacts c {extra_join} "
                        f"WHERE {_NEEDS_CITY} {where}")
            return cur.fetchone()["n"]
        join = "LEFT JOIN company_web_lookups l ON l.company_key = c.company_key"
        return {
            "to_lookup": count(join, "AND l.company_key IS NULL"),
            "retry": count(join, f"AND {_retryable()}"),
            "review": count(join, "AND l.outcome = 'needs_review'"),
            "cached_ready": count(join, "AND l.outcome = 'resolved'"),
        }


def apply_reading(cur, key: str, website: str, address: str, city: str, country: str,
           source_url: str, status: str) -> int:
    cur.execute(
        f"""
        UPDATE contacts c SET
            website = COALESCE(NULLIF(c.website, ''), NULLIF(%s, '')),
            address = COALESCE(NULLIF(c.address, ''), NULLIF(%s, '')),
            city = %s, country = NULLIF(%s, ''), city_status = %s,
            location_source = 'website', address_source_url = %s, updated_at = NOW()
        WHERE c.company_key = %s AND {_NEEDS_CITY} AND COALESCE(c.city, '') = ''
        """,
        (website[:300], address, city[:100], country, status, source_url, key),
    )
    return cur.rowcount


def apply_cached_web() -> int:
    """Fill organizations still waiting from readings that were accepted as
    resolved earlier. Never overwrites a city that is set. Returns rows updated."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM company_web_lookups WHERE outcome = 'resolved'")
        rows = [dict(r) for r in cur.fetchall()]
        return sum(
            apply_reading(cur, r["company_key"], r["website"] or "",
                   Address(r["street"] or "", r["postal_code"] or "", r["city"] or "", "").line(),
                   r["city"] or "", r["country"] or "", r["source_url"] or "", "resolved")
            for r in rows)


def _store(cur, key: str, result: WebResult) -> None:
    address = result.address
    cur.execute(
        """
        INSERT INTO company_web_lookups
            (company_key, outcome, website, street, postal_code, city, country, source_url,
             reason, candidates)
        VALUES (%s, %s, NULLIF(%s, ''), NULLIF(%s, ''), NULLIF(%s, ''), NULLIF(%s, ''),
                NULLIF(%s, ''), NULLIF(%s, ''), NULLIF(%s, ''), %s)
        ON CONFLICT (company_key) DO UPDATE SET
            outcome = EXCLUDED.outcome, website = EXCLUDED.website, street = EXCLUDED.street,
            postal_code = EXCLUDED.postal_code, city = EXCLUDED.city, country = EXCLUDED.country,
            source_url = EXCLUDED.source_url, reason = EXCLUDED.reason,
            candidates = EXCLUDED.candidates,
            attempts = company_web_lookups.attempts + 1, looked_up_at = NOW()
        """,
        (key, result.outcome, result.website,
         address.street if address else "", address.postal_code if address else "",
         address.city if address else "", address.country if address else "",
         result.source_url, result.reason, Json(result.candidates)),
    )


def default_lookup() -> Callable[[str], WebResult]:
    """The real lookup: DuckDuckGo search, direct page fetches, and — when an LLM
    is configured — a fallback reader for non-German pages."""
    llm_address = _llm_address()
    return lambda name: lookup_company(name, lambda q: web_search(q, max_results=8), fetch_html,
                                       llm_address=llm_address)


def _llm_address():
    """An address reader backed by the cheap model, or None when none is
    configured. Its answers are kept only if they appear on the page."""
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from gcrm.company_web import llm_prompt, parse_llm_address
        from gcrm.config import CHEAP_LLM
        from gcrm.tools import get_llm
        model = get_llm(CHEAP_LLM)
    except Exception:
        logger.info("company web lookup: no LLM configured, German-style pages only")
        return None

    def read(name: str, text: str) -> Address | None:
        try:
            system, user = llm_prompt(name, text)
            return parse_llm_address(model.invoke([SystemMessage(content=system),
                                                   HumanMessage(content=user)]).content, text)
        except Exception:
            logger.warning("company web lookup: LLM reader failed", exc_info=True)
            return None
    return read


def resolve_company_websites(limit: int = 10, lookup: Callable[[str], WebResult] | None = None,
                             max_seconds: float = DEFAULT_SECONDS, clock=time.monotonic) -> dict:
    """Find the website and address of LinkedIn-created organizations that have no
    city, most connections first, at most `limit` companies and `max_seconds`.

    A reading the code is sure of is applied to the organization; anything unsure is
    stored for a human with what was seen. Counts — applied_cached, looked_up,
    resolved, needs_review, not_found, errors, stopped (reason or "")."""
    counts = {"applied_cached": apply_cached_web(), "looked_up": 0, "resolved": 0,
              "needs_review": 0, "not_found": 0, "errors": 0, "stopped": ""}
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT DISTINCT ON (c.company_key) c.company_key, c.name,
                   (SELECT COUNT(*) FROM people p
                     WHERE p.contact_id = c.id AND p.deleted_at IS NULL) AS people
              FROM contacts c LEFT JOIN company_web_lookups l ON l.company_key = c.company_key
             WHERE {_NEEDS_CITY} AND (l.company_key IS NULL OR {_retryable()})
             ORDER BY c.company_key, people DESC
            """
        )
        todo = sorted((dict(r) for r in cur.fetchall()), key=lambda r: (-r["people"], r["name"]))
    lookup = lookup or default_lookup()
    started, unanswered = clock(), 0
    for item in todo[:limit]:
        if clock() - started > max_seconds:
            counts["stopped"] = "time budget reached — run it again to continue"
            break
        try:
            result = lookup(item["name"])
        except Exception:
            counts["errors"] += 1
            logger.warning("company web lookup crashed for %r", item["name"], exc_info=True)
            continue
        if not result.searched:  # the search never answered: say nothing about the company
            unanswered += 1
            if unanswered >= UNANSWERED_STOP:
                counts["stopped"] = "the search engine is not answering (throttled?) — try again later"
                break
            continue
        unanswered = 0
        try:
            with db() as conn:
                cur = conn.cursor()
                _store(cur, item["company_key"], result)
                if result.outcome == "resolved" and result.address:
                    a = result.address
                    apply_reading(cur, item["company_key"], result.website, a.line(), a.city, a.country,
                           result.source_url, "resolved")
        except Exception:
            counts["errors"] += 1
            logger.warning("company web result not saved for %r", item["name"], exc_info=True)
            continue
        counts["looked_up"] += 1
        counts[result.outcome] += 1
    logger.info("company web lookups: %s", counts)
    if counts["looked_up"] or counts["applied_cached"]:
        log_audit(None, None, "linkedin.websites_resolved", None,
                  f"looked_up={counts['looked_up']} resolved={counts['resolved']}")
    return counts


def run_web_lookup(limit: int) -> dict:
    """resolve_company_websites for the browser: the limit is clamped to
    1..WEB_LOOKUP_MAX and one run at a time (advisory lock)."""
    limit = max(1, min(int(limit), WEB_LOOKUP_MAX))
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT pg_try_advisory_lock(%s) AS got", (LOCK_KEY,))
        if not cur.fetchone()["got"]:
            return {"applied_cached": 0, "looked_up": 0, "resolved": 0, "needs_review": 0,
                    "not_found": 0, "errors": 0, "stopped": "another lookup is already running"}
        try:
            return resolve_company_websites(limit=limit)
        finally:
            cur.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))


# --- background job for the browser --------------------------------------------
# One lookup takes ~10 s, so a few dozen companies run for minutes — longer than a
# web request may live. A click starts a background thread instead; every company
# is cached the moment it finishes, so a restart just resumes where it stopped.

JOB_MAX = 200               # most companies one job may process
JOB_SECONDS = 3600          # ...or this long, whichever comes first


def is_job_running() -> bool:
    """True while any process holds the lookup lock. Probed with a try-lock that is
    released at once, so it works across workers and restarts."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT pg_try_advisory_lock(%s) AS got", (LOCK_KEY,))
        got = cur.fetchone()["got"]
        if got:
            cur.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
        return not got


def _job(limit: int) -> None:
    """The thread body: hold the lock for the whole run, never raise."""
    try:
        with db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT pg_try_advisory_lock(%s) AS got", (LOCK_KEY,))
            if not cur.fetchone()["got"]:
                return
            try:
                resolve_company_websites(limit=limit, max_seconds=JOB_SECONDS)
            finally:
                cur.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    except Exception:
        logger.exception("company web lookup job crashed")


def start_web_job(limit: int, spawn=None) -> bool:
    """Start a background lookup of up to `limit` (1..JOB_MAX) companies. Returns
    False, starting nothing, if one is already running."""
    limit = max(1, min(int(limit), JOB_MAX))
    if is_job_running():
        return False
    if spawn is None:
        import threading
        spawn = lambda target, args: threading.Thread(  # noqa: E731
            target=target, args=args, daemon=True, name="company-web-lookup").start()
    spawn(_job, (limit,))
    return True
