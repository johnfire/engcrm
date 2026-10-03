"""The phone's form limits (engcrm-mobile/services/recordFields.ts) must equal the
server's, or the phone would accept values the server then refuses (or refuse values
the server accepts). Also checks the server's limits against the database columns."""
import re
from pathlib import Path

from gcrm.api.routers.api_people import PERSON_LIMITS
from gcrm.api.routers.api_record_edit import TEXT_LIMITS

FIELDS_TS = Path(__file__).resolve().parent.parent / "engcrm-mobile" / "services" / "recordFields.ts"


def phone_limits(constant: str) -> dict[str, int]:
    source = FIELDS_TS.read_text()
    block = re.search(rf"export const {constant}: FieldDef\[\] = \[(.*?)\n\];", source, re.S).group(1)
    return {
        match.group(1): int(match.group(2))
        for match in re.finditer(r'key: "(\w+)".*?maxLength: (\d+)', block)
    }


def test_organization_form_matches_the_server():
    phone = phone_limits("ORGANIZATION_FIELDS")
    assert phone == TEXT_LIMITS


def test_person_form_matches_the_server():
    phone = phone_limits("PERSON_FIELDS")
    assert phone == PERSON_LIMITS


def test_the_database_columns_are_at_least_as_wide_as_the_limits():
    """Needs a database; skipped when none is configured (CI runs it)."""
    import os

    import pytest

    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    import psycopg2

    with psycopg2.connect(url) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT table_name, column_name, character_maximum_length FROM information_schema.columns "
            "WHERE table_name IN ('contacts', 'people') AND character_maximum_length IS NOT NULL"
        )
        widths = {(t, c): n for t, c, n in cur.fetchall()}
    for table, limits in (("contacts", TEXT_LIMITS), ("people", PERSON_LIMITS)):
        for column, limit in limits.items():
            width = widths.get((table, column))
            assert width is None or limit <= width, f"{table}.{column}: limit {limit} > column {width}"
