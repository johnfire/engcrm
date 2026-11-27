"""The Help Centre's "Contracts" article (migration 112): seeded like the first articles, readable in both
languages on the web, and never overwriting an article someone has edited."""
import html
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import gcrm.api.main as main
from gcrm.api.security import hash_password
from gcrm.db.connection import db
from gcrm.tools.db_help import list_published_help

pytestmark = pytest.mark.integration
MIGRATION = Path(__file__).parents[2] / "gcrm" / "db" / "migrations" / "112_contracts_help.sql"
PASSWORD = "a-long-test-password-1"


def _apply():
    with db() as connection:
        connection.cursor().execute(MIGRATION.read_text())


@pytest.fixture
def seeded(clean_database):
    """The cleaning empties the help articles, so the migration's own SQL puts its one back."""
    _apply()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM workspaces WHERE slug = 'default'")
        return cursor.fetchone()["id"]


def _article(workspace, language, surface="web"):
    return next((a for a in list_published_help(workspace, language, surface) if a["slug"] == "contracts"), None)


def test_the_article_is_published_on_the_web_in_both_languages(seeded):
    english, german = _article(seeded, "en"), _article(seeded, "de")
    assert english["title"] == "Contracts" and german["title"] == "Verträge"
    assert english["summary"] and german["summary"] and english["body"] != german["body"]


def test_the_english_text_covers_what_the_page_does(seeded):
    body = _article(seeded, "en")["body"]
    for words in ("payments", "Forecast", "New contract", "Running now", "Upcoming", "Finished", "link", "delete"):
        assert words in body, words


def test_the_german_text_uses_the_words_on_the_german_pages(seeded):
    body = _article(seeded, "de")["body"]
    for words in ("Zahlungen", "Prognose", "Neuer Vertrag", "Laufend", "Anstehend", "Beendet", "Links", "löschen"):
        assert words in body, words
    assert "Sie" in body                                   # the Help Centre addresses the reader formally


def test_paragraphs_are_real_line_breaks_not_a_typed_backslash_n(seeded):
    for language in ("en", "de"):
        body = _article(seeded, language)["body"]
        assert "\n\n" in body and "\\n" not in body


def test_it_is_not_offered_on_the_phone_which_has_no_contracts_yet(seeded):
    assert _article(seeded, "en", "mobile") is None


def test_running_the_migration_again_never_overwrites_an_edited_article(seeded):
    with db() as connection:
        connection.cursor().execute("UPDATE help_articles SET title_en = 'Our own contract guide' WHERE slug = 'contracts'")
    _apply()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT title_en, count(*) OVER () AS n FROM help_articles WHERE slug = 'contracts'")
        row = cursor.fetchone()
    assert (row["title_en"], row["n"]) == ("Our own contract guide", 1)


def test_the_help_page_shows_the_article_in_the_readers_language(seeded):
    with db() as connection:
        connection.cursor().execute(
            "INSERT INTO users (email, name, password_hash, role, workspace_id, is_active) VALUES (%s, 'owner', %s, 'admin', %s, TRUE)",
            ("owner@first.example", hash_password(PASSWORD), seeded))
    browser = TestClient(main.app)
    assert browser.post("/login", data={"email": "owner@first.example", "password": PASSWORD}, follow_redirects=False).status_code == 303
    english = html.unescape(browser.get("/help/").text)
    assert 'id="help-contracts"' in english and "New contract" in english
    browser.post("/settings/language", data={"ui_language": "de"})
    german = html.unescape(browser.get("/help/").text)
    assert 'id="help-contracts"' in german and "Neuer Vertrag" in german
