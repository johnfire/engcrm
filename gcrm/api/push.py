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


def _get_user_tokens(user_id: int) -> list[str]:
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT token FROM push_tokens WHERE user_id = %s", (user_id,))
        return [row["token"] for row in cur.fetchall()]


def _send(tokens: list[str], title: str, body: str, data: dict | None, silent: bool) -> None:
    if not tokens:
        return
    message = {**({"data": data} if data else {})}
    if silent:
        # Data-only push — no visible banner. Android delivers these reliably;
        # this app is Android-only today so iOS quirks don't apply.
        message["_contentAvailable"] = True
        message["priority"] = "high"
    else:
        message["title"] = title
        message["body"] = body
    messages = [{"to": token, **message} for token in tokens]
    with httpx.Client(timeout=5) as client:
        client.post(EXPO_PUSH_URL, json=messages)


def send_push_to_all(title: str, body: str, data: dict | None = None) -> None:
    """Best-effort broadcast to every registered device. Never raises."""
    try:
        _send(_get_all_tokens(), title, body, data, silent=False)
    except Exception as error:
        logger.warning("push notification failed: %s", error)


def send_push_to_user(user_id: int, title: str, body: str, data: dict | None = None) -> None:
    """Best-effort visible push to one account's own devices only. Never raises."""
    try:
        _send(_get_user_tokens(user_id), title, body, data, silent=False)
    except Exception as error:
        logger.warning("push notification failed: %s", error)


def send_silent_push_to_user(user_id: int, data: dict) -> None:
    """
    Best-effort data-only push to one account's own devices — no visible
    banner, used to tell an already-open app to re-fetch something (e.g. a
    changed ui_language) without disturbing the user. Never raises.
    """
    try:
        _send(_get_user_tokens(user_id), "", "", data, silent=True)
    except Exception as error:
        logger.warning("silent push notification failed: %s", error)
