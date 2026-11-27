"""The figures an account saved on the income calculator.

Encrypted before they are stored (they include health and disability amounts), read and
written only by user id inside the workspace's scope, and never exported or logged.
"""
import json

from gcrm.api.security import decrypt_private, encrypt_private
from gcrm.config import ACCOUNT_ENCRYPTION_KEY
from gcrm.db.connection import db


def load_inputs(user_id: int) -> dict | None:
    """The saved form values, or None. Raises if the stored value cannot be decrypted."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT data_encrypted FROM income_calculator_inputs WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
    if not row:
        return None
    return json.loads(decrypt_private(row["data_encrypted"], ACCOUNT_ENCRYPTION_KEY))


def save_inputs(user_id: int, values: dict) -> None:
    encrypted = encrypt_private(json.dumps(values), ACCOUNT_ENCRYPTION_KEY)
    with db() as conn:
        conn.cursor().execute(
            "INSERT INTO income_calculator_inputs (user_id, data_encrypted) VALUES (%s, %s) "
            "ON CONFLICT (user_id) DO UPDATE SET data_encrypted = EXCLUDED.data_encrypted, updated_at = NOW()",
            (user_id, encrypted),
        )


def delete_inputs(user_id: int) -> None:
    with db() as conn:
        conn.cursor().execute("DELETE FROM income_calculator_inputs WHERE user_id = %s", (user_id,))
