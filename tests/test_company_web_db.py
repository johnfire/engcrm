"""Storage and runner for website/address lookups: what is cached, what is applied
to an organization, and how the run behaves when the search stops answering.
DB mocked — runs without Postgres or network."""
from unittest.mock import MagicMock, patch

from gcrm.company_web import Address, WebResult
from gcrm.tools import db_company_web as w


class Cursor:
    def __init__(self, todo=(), got_lock=True, fail_store_for=None):
        self.todo, self.got_lock, self.fail_store_for = list(todo), got_lock, fail_store_for
        self.executed, self.rowcount, self._one = [], 1, None

    def execute(self, sql, params=None):
        sql = " ".join(sql.split())
        self.executed.append((sql, params))
        if sql.startswith("SELECT pg_try_advisory_lock"):
            self._one = {"got": self.got_lock}
        if sql.startswith("INSERT INTO company_web_lookups") and params[0] == self.fail_store_for:
            raise RuntimeError("boom")

    def fetchall(self):
        last = self.executed[-1][0]
        return [dict(r) for r in self.todo] if "DISTINCT ON" in last else []

    def fetchone(self):
        return self._one

    def sql(self, prefix):
        return [(s, p) for s, p in self.executed if s.startswith(prefix)]


def run(cursor, lookup, **kwargs):
    conn = MagicMock()
    conn.cursor.return_value = cursor
    with patch("gcrm.tools.db_company_web.db") as mock_db, \
         patch("gcrm.tools.db_company_web.log_audit"):
        mock_db.return_value.__enter__.return_value = conn
        return w.resolve_company_websites(lookup=lookup, **kwargs)


def todo(*names, people=1):
    return [{"company_key": n.lower(), "name": n, "people": people} for n in names]


RESOLVED = WebResult("resolved", "https://acme.de/", Address("Hauptstraße 5", "86150", "Augsburg", "DE"),
                     "https://acme.de/impressum")


class TestResolve:
    def test_a_sure_reading_is_cached_and_applied_to_the_organization(self):
        cursor = Cursor(todo("Acme"))
        counts = run(cursor, lambda name: RESOLVED)
        assert counts["resolved"] == 1 and counts["looked_up"] == 1
        [(_, stored)] = cursor.sql("INSERT INTO company_web_lookups")
        assert stored[:3] == ("acme", "resolved", "https://acme.de/")
        [(sql, params)] = [(s, p) for s, p in cursor.sql("UPDATE contacts c SET website") if p]
        assert params == ("https://acme.de/", "Hauptstraße 5, 86150 Augsburg", "Augsburg", "DE",
                          "resolved", "https://acme.de/impressum", "acme")
        # never overwrites what is already there
        assert "COALESCE(NULLIF(c.website, ''), NULLIF(%s, ''))" in sql
        assert "COALESCE(c.city, '') = ''" in sql and "location_source = 'website'" in sql

    def test_an_unsure_reading_is_stored_for_a_human_and_not_applied(self):
        review = WebResult("needs_review", "https://acme.de/", Address("", "86150", "Augsburg", ""),
                           "https://acme.de/impressum", "the country could not be established")
        cursor = Cursor(todo("Acme"))
        counts = run(cursor, lambda name: review)
        assert counts["needs_review"] == 1
        assert cursor.sql("INSERT INTO company_web_lookups")
        assert not [1 for s, p in cursor.sql("UPDATE contacts c SET website") if p]

    def test_a_search_that_never_answered_is_not_recorded_as_not_found(self):
        silent = WebResult("not_found", reason="the search returned nothing", searched=False)
        cursor = Cursor(todo("A", "B"))
        counts = run(cursor, lambda name: silent)
        assert cursor.sql("INSERT INTO company_web_lookups") == []
        assert counts["looked_up"] == 0 and counts["not_found"] == 0

    def test_three_unanswered_searches_in_a_row_end_the_run(self):
        silent = WebResult("not_found", searched=False)
        asked = []
        counts = run(Cursor(todo(*"ABCDEFG")), lambda name: asked.append(name) or silent)
        assert len(asked) == w.UNANSWERED_STOP and "not answering" in counts["stopped"]

    def test_an_answer_resets_the_unanswered_streak(self):
        results = iter([WebResult("not_found", searched=False)] * 2 + [RESOLVED] +
                       [WebResult("not_found", searched=False)] * 2 + [RESOLVED])
        counts = run(Cursor(todo(*"ABCDEF")), lambda name: next(results))
        assert counts["stopped"] == "" and counts["resolved"] == 2

    def test_a_crashing_lookup_is_counted_and_the_rest_continue(self):
        def lookup(name):
            if name == "Bad":
                raise RuntimeError("boom")
            return RESOLVED
        counts = run(Cursor(todo("Bad", "Good")), lookup)
        assert counts["errors"] == 1 and counts["resolved"] == 1

    def test_a_result_that_cannot_be_saved_is_counted_and_skipped(self):
        counts = run(Cursor(todo("Acme", "Globex"), fail_store_for="acme"), lambda name: RESOLVED)
        assert counts["errors"] == 1 and counts["resolved"] == 1

    def test_most_connections_first_and_the_limit_caps_the_run(self):
        rows = [{"company_key": "s", "name": "Small", "people": 1},
                {"company_key": "b", "name": "Big", "people": 9},
                {"company_key": "m", "name": "Mid", "people": 4}]
        asked = []
        run(Cursor(rows), lambda name: asked.append(name) or RESOLVED, limit=2)
        assert asked == ["Big", "Mid"]

    def test_the_time_budget_stops_starting_new_companies(self):
        ticks = iter([0, 1, 200, 201, 202])
        asked = []
        counts = run(Cursor(todo(*"ABC")), lambda name: asked.append(name) or RESOLVED,
                     max_seconds=100, clock=lambda: next(ticks))
        assert asked == ["A"] and "time budget" in counts["stopped"]

    def test_the_selection_skips_cached_companies_and_retries_only_old_not_founds(self):
        cursor = Cursor(todo())
        run(cursor, lambda name: RESOLVED)
        select = [s for s, _ in cursor.executed if "DISTINCT ON" in s][0]
        assert "l.company_key IS NULL" in select
        assert "l.outcome = 'not_found' AND l.attempts < 3" in select and "INTERVAL '1 day'" in select

    def test_a_repeat_search_counts_the_attempt(self):
        cursor = Cursor(todo("Acme"))
        run(cursor, lambda name: RESOLVED)
        sql = cursor.sql("INSERT INTO company_web_lookups")[0][0]
        assert "attempts = company_web_lookups.attempts + 1" in sql


class TestWebLookupFromTheBrowser:
    def go(self, limit, got=True):
        cursor = Cursor(got_lock=got)
        conn = MagicMock()
        conn.cursor.return_value = cursor
        with patch("gcrm.tools.db_company_web.db") as mock_db, \
             patch("gcrm.tools.db_company_web.resolve_company_websites",
                   return_value={"looked_up": 1, "stopped": ""}) as resolve:
            mock_db.return_value.__enter__.return_value = conn
            return w.run_web_lookup(limit), resolve, cursor

    def test_the_limit_is_clamped(self):
        for asked, used in ((10, 10), (0, 1), (10_000, w.WEB_LOOKUP_MAX)):
            _, resolve, _ = self.go(asked)
            resolve.assert_called_once_with(limit=used)

    def test_only_one_run_at_a_time(self):
        result, resolve, cursor = self.go(5, got=False)
        resolve.assert_not_called()
        assert "already running" in result["stopped"]
        assert not cursor.sql("SELECT pg_advisory_unlock")

    def test_the_lock_is_released(self):
        _, _, cursor = self.go(5)
        assert cursor.sql("SELECT pg_advisory_unlock")


class TestBackgroundJob:
    def probe(self, got):
        cursor = Cursor(got_lock=got)
        conn = MagicMock()
        conn.cursor.return_value = cursor
        return cursor, conn

    def test_it_is_running_while_someone_holds_the_lock_and_the_probe_lets_go_again(self):
        for held, expected in ((True, False), (False, True)):
            cursor, conn = self.probe(got=held)
            with patch("gcrm.tools.db_company_web.db") as mock_db:
                mock_db.return_value.__enter__.return_value = conn
                assert w.is_job_running() is expected
            assert bool(cursor.sql("SELECT pg_advisory_unlock")) is held  # only unlocks what it took

    def test_a_click_spawns_one_clamped_job(self):
        spawned = []
        with patch("gcrm.tools.db_company_web.is_job_running", return_value=False):
            assert w.start_web_job(10_000, spawn=lambda target, args: spawned.append(args)) is True
        assert spawned == [(w.JOB_MAX,)]

    def test_a_second_click_while_one_runs_starts_nothing(self):
        spawned = []
        with patch("gcrm.tools.db_company_web.is_job_running", return_value=True):
            assert w.start_web_job(5, spawn=lambda target, args: spawned.append(args)) is False
        assert spawned == []

    def test_the_job_holds_the_lock_for_the_run_and_releases_it(self):
        cursor, conn = self.probe(got=True)
        with patch("gcrm.tools.db_company_web.db") as mock_db, \
             patch("gcrm.tools.db_company_web.resolve_company_websites") as resolve:
            mock_db.return_value.__enter__.return_value = conn
            w._job(7)
        resolve.assert_called_once_with(limit=7, max_seconds=w.JOB_SECONDS)
        assert cursor.sql("SELECT pg_advisory_unlock")

    def test_the_job_exits_quietly_if_it_lost_the_race_for_the_lock(self):
        cursor, conn = self.probe(got=False)
        with patch("gcrm.tools.db_company_web.db") as mock_db, \
             patch("gcrm.tools.db_company_web.resolve_company_websites") as resolve:
            mock_db.return_value.__enter__.return_value = conn
            w._job(7)
        resolve.assert_not_called()

    def test_a_crash_in_the_job_is_logged_not_raised(self):
        with patch("gcrm.tools.db_company_web.db", side_effect=RuntimeError("db down")):
            w._job(7)  # must not raise
