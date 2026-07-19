"""Send push notifications to all registered devices via the Expo Push service."""
import logging

import httpx

from gcrm.db.connection import db

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/exponent-push-notification-service/push/send"


def _get_all_tokens() -> list[str]:
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT token FROM push_tokens")
        return [row["token"] for row in cur.fetchall()]


def send_push_to_all(title: str, body: str, data: dict | None = None) -> None:
    """Best-effort broadcast to every registered device. Never raises."""
    try:
        tokens = _get_all_tokens()
        if not tokens:
            return
        messages = [
            {"to": token, "title": title, "body": body, **({"data": data} if data else {})}
            for token in tokens
        ]
        with httpx.Client(timeout=5) as client:
            client.post(EXPO_PUSH_URL, json=messages)
    except Exception as error:
        logger.warning("push notification failed: %s", error)
