"""Session persistence must not expose raw credentials to database storage or queries."""
import hashlib
from unittest.mock import MagicMock, patch

from gcrm.tools.db_web_sessions import create_web_session, get_web_session


def test_session_stores_only_token_hash_and_keyed_emergency_fingerprint():
    connection = MagicMock()
    with patch("gcrm.tools.db_web_sessions.db") as database:
        database.return_value.__enter__.return_value = connection
        token = create_web_session({"user_id": None}, "fictional-emergency-password")
    parameters = connection.cursor.return_value.execute.call_args.args[1]
    assert token not in parameters
    assert parameters[0] == hashlib.sha256(token.encode()).hexdigest()
    assert "fictional-emergency-password" not in parameters
    assert parameters[3] != hashlib.sha256(b"fictional-emergency-password").hexdigest()


def test_lookup_does_not_transmit_the_emergency_password_to_postgres():
    connection = MagicMock()
    connection.cursor.return_value.fetchone.return_value = None
    with patch("gcrm.tools.db_web_sessions.db") as database:
        database.return_value.__enter__.return_value = connection
        assert get_web_session("opaque-session-token", "fictional-emergency-password") is None
    parameters = connection.cursor.return_value.execute.call_args.args[1]
    assert "opaque-session-token" not in parameters
    assert "fictional-emergency-password" not in parameters
