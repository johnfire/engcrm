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
