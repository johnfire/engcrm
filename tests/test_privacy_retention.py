"""Unit tests for GDPR erasure and retention enforcement."""
from pathlib import Path
from unittest.mock import MagicMock, patch


def _mock_connection(rows: list[dict] | None = None):
    cursor = MagicMock()
    cursor.fetchone.return_value = {"id": 7}
    cursor.fetchall.return_value = rows or []
    cursor.rowcount = 3
    connection = MagicMock()
    connection.cursor.return_value = cursor
    connection.__enter__.return_value = connection
    connection.__exit__.return_value = False
    return connection, cursor


def test_erase_organization_removes_related_rows_and_card_image(tmp_path: Path):
    from gcrm.tools import privacy_retention

    image_path = tmp_path / "card.jpg"
    image_path.write_bytes(b"image")
    connection, cursor = _mock_connection([{"image_path": "card.jpg"}])

    with patch.object(privacy_retention, "CARD_IMAGE_DIR", str(tmp_path)), patch.object(
        privacy_retention, "db"
    ) as mock_db, patch.object(privacy_retention, "log_audit"):
        mock_db.return_value.__enter__.return_value = connection
        assert privacy_retention.erase_organization(7) is True

    assert not image_path.exists()
    statements = " ".join(str(call) for call in cursor.execute.call_args_list)
    assert "card_captures" in statements
    assert "outreach_outcomes" in statements
    assert "linked_contact_id = %s OR contact_id = %s" in statements
    assert "inbox_messages" in statements
    assert "DELETE FROM contacts" in statements


def test_erase_organization_returns_false_when_organization_is_missing():
    from gcrm.tools import privacy_retention

    connection, cursor = _mock_connection()
    cursor.fetchone.return_value = None
    with patch.object(privacy_retention, "db") as mock_db:
        mock_db.return_value.__enter__.return_value = connection
        assert privacy_retention.erase_organization(404) is False


def test_purge_expired_data_records_aggregate_counts():
    from gcrm.tools import privacy_retention

    connection, cursor = _mock_connection([])
    with patch.object(privacy_retention, "db") as mock_db, patch.object(
        privacy_retention, "erase_organization", return_value=True
    ) as erase_organization, patch.object(privacy_retention, "log_audit"):
        mock_db.return_value.__enter__.return_value = connection
        counts = privacy_retention.purge_expired_data()

    assert counts["contacts"] == 0
    assert counts["erasure_requests"] == 0
    assert counts["audit_log"] == 3
    erase_organization.assert_not_called()


def test_purge_expired_data_erases_organizations_from_creation_date():
    from gcrm.tools import privacy_retention

    connection, cursor = _mock_connection()
    cursor.fetchall.side_effect = [[], [{"id": 12}]]
    with patch.object(privacy_retention, "db") as mock_db, patch.object(
        privacy_retention, "erase_organization", return_value=True
    ) as erase_organization, patch.object(privacy_retention, "log_audit"):
        mock_db.return_value.__enter__.return_value = connection
        counts = privacy_retention.purge_expired_data()

    erase_organization.assert_called_once_with(12)
    assert counts["contacts"] == 1
    statements = " ".join(str(call) for call in cursor.execute.call_args_list)
    assert "SELECT id FROM contacts WHERE created_at" in statements
    assert "matched_contact_id IS NULL" in statements


def test_erase_person_deletes_the_row_and_remembers_only_a_hash_of_the_linkedin_url():
    from gcrm.linkedin import linkedin_url_hash
    from gcrm.tools import privacy_retention

    connection, cursor = _mock_connection()
    cursor.fetchone.return_value = {"linkedin_url": "https://www.linkedin.com/in/anna"}
    with patch.object(privacy_retention, "db") as mock_db, patch.object(
        privacy_retention, "log_audit"
    ) as audit:
        mock_db.return_value.__enter__.return_value = connection
        assert privacy_retention.erase_person(5) is True

    statements = [(" ".join(c.args[0].split()), c.args[1]) for c in cursor.execute.call_args_list]
    suppression = next(s for s in statements if s[0].startswith("INSERT INTO person_import_suppressions"))
    assert suppression[1] == (linkedin_url_hash("https://www.linkedin.com/in/anna"),)
    assert ("DELETE FROM people WHERE id = %s", (5,)) in statements
    # Nothing but the hash is written: no URL, no name.
    assert "anna" not in str(suppression)
    assert audit.call_args.args[2:] == ("person.erased", "person:5", "suppressed")


def test_erase_person_without_a_url_leaves_no_suppression_row():
    from gcrm.tools import privacy_retention

    connection, cursor = _mock_connection()
    cursor.fetchone.return_value = {"linkedin_url": None}
    with patch.object(privacy_retention, "db") as mock_db, patch.object(privacy_retention, "log_audit"):
        mock_db.return_value.__enter__.return_value = connection
        assert privacy_retention.erase_person(5) is True
    assert "person_import_suppressions" not in str(cursor.execute.call_args_list)


def test_erase_person_can_skip_the_suppression():
    from gcrm.tools import privacy_retention

    connection, cursor = _mock_connection()
    cursor.fetchone.return_value = {"linkedin_url": "https://www.linkedin.com/in/anna"}
    with patch.object(privacy_retention, "db") as mock_db, patch.object(privacy_retention, "log_audit"):
        mock_db.return_value.__enter__.return_value = connection
        privacy_retention.erase_person(5, suppress_reimport=False)
    assert "person_import_suppressions" not in str(cursor.execute.call_args_list)


def test_erase_person_returns_false_when_missing():
    from gcrm.tools import privacy_retention

    connection, cursor = _mock_connection()
    cursor.fetchone.return_value = None
    with patch.object(privacy_retention, "db") as mock_db, patch.object(privacy_retention, "log_audit") as audit:
        mock_db.return_value.__enter__.return_value = connection
        assert privacy_retention.erase_person(404) is False
    audit.assert_not_called()
    assert "DELETE" not in str(cursor.execute.call_args_list)


def test_purge_expired_data_purges_idle_unlinked_people_and_reports_the_count():
    from gcrm.tools import privacy_retention

    connection, cursor = _mock_connection([])
    with patch.object(privacy_retention, "db") as mock_db, patch.object(
        privacy_retention, "erase_organization"
    ), patch.object(privacy_retention, "log_audit"), patch.object(
        privacy_retention, "PEOPLE_RETENTION_DAYS", 400
    ):
        mock_db.return_value.__enter__.return_value = connection
        counts = privacy_retention.purge_expired_data()

    assert counts["people"] == 3  # the mock's rowcount
    sql, params = next(
        (" ".join(c.args[0].split()), c.args[1]) for c in cursor.execute.call_args_list
        if c.args[0].lstrip().startswith("DELETE FROM people p")
    )
    assert params == (400,)
    # Only people with no organization, and never one marked "keep".
    assert "p.contact_id IS NULL AND p.linked_contact_id IS NULL AND NOT p.retention_hold" in sql
    # Any sign of life counts as activity, not just the row's own timestamps.
    for activity in ("p.updated_at", "people_interactions", "person_user_priorities", "approval_queue"):
        assert activity in sql
    # Soft-deleted people are always removed, held or not.
    assert sql.startswith("DELETE FROM people p WHERE p.deleted_at IS NOT NULL OR")
