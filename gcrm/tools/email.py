"""
Email tools: SMTP sending and IMAP inbox reading via Proton Bridge.
Proton Bridge runs locally and exposes standard IMAP/SMTP ports.
"""
import email as email_lib
import imaplib
import logging
import smtplib
import ssl
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from gcrm.config import (
    PROTON_SMTP_HOST, PROTON_SMTP_PORT,
    PROTON_IMAP_HOST, PROTON_IMAP_PORT,
    PROTON_EMAIL, PROTON_PASSWORD, PROTON_FROM_EMAIL,
    EMAIL_ENABLED,
)
from gcrm.tools.db import save_inbox_message

logger = logging.getLogger(__name__)

_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


def _starttls_context(host: str) -> ssl.SSLContext:
    """Verify the server certificate for remote hosts. The local Proton Bridge
    (loopback) presents a self-signed cert, so verification is skipped there,
    preserving the current local-bridge behavior."""
    ctx = ssl.create_default_context()
    if host in _LOOPBACK_HOSTS:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def send_email(to_email: str, subject: str, body: str) -> bool:
    """
    Send a plain-text email via Proton Bridge SMTP.
    Returns True on success, False on failure.
    """
    if not EMAIL_ENABLED:
        logger.warning("send_email: EMAIL_ENABLED=false — not sending to %s (%s)", to_email, subject)
        return False

    if not to_email or not body:
        logger.warning("send_email: missing to_email or body — skipped")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = PROTON_FROM_EMAIL
    msg["To"] = to_email
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP(PROTON_SMTP_HOST, PROTON_SMTP_PORT) as smtp:
            smtp.ehlo()
            smtp.starttls(context=_starttls_context(PROTON_SMTP_HOST))
            smtp.login(PROTON_EMAIL, PROTON_PASSWORD)
            smtp.sendmail(PROTON_EMAIL, [to_email], msg.as_string())
        logger.info("send_email: sent to %s — %s", to_email, subject)
        return True
    except Exception as e:
        logger.error("send_email failed to %s: %s", to_email, e)
        return False


def read_inbox(limit: int = 50, since_days: int = 14) -> list[dict]:
    """
    Read emails from the INBOX via Proton Bridge IMAP (last since_days days).
    Saves each message to the inbox_messages table (deduplication handled there).
    Returns list of message dicts: {id, message_id, from_email, subject, body, received_at}.
    """
    from datetime import timedelta
    messages = []
    try:
        with imaplib.IMAP4(PROTON_IMAP_HOST, PROTON_IMAP_PORT) as imap:
            imap.starttls(ssl_context=_starttls_context(PROTON_IMAP_HOST))
            imap.login(PROTON_EMAIL, PROTON_PASSWORD)
            imap.select("INBOX")

            since_date = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%d-%b-%Y")
            _, data = imap.search(None, f"SINCE {since_date}")
            message_ids = data[0].split()

            for uid in message_ids[-limit:]:
                _, msg_data = imap.fetch(uid, "(RFC822)")
                raw = msg_data[0][1]
                parsed = email_lib.message_from_bytes(raw)

                msg_id = parsed.get("Message-ID", "").strip()
                from_email = email_lib.utils.parseaddr(parsed.get("From", ""))[1]
                subject = parsed.get("Subject", "")
                received_str = parsed.get("Date", "")

                body = ""
                html_body = ""
                if parsed.is_multipart():
                    for part in parsed.walk():
                        content_type = part.get_content_type()
                        if content_type == "text/plain" and not body:
                            payload = part.get_payload(decode=True)
                            if payload is not None:
                                body = payload.decode("utf-8", errors="replace")
                        elif content_type == "text/html" and not html_body:
                            payload = part.get_payload(decode=True)
                            if payload is not None:
                                html_body = payload.decode("utf-8", errors="replace")
                else:
                    payload = parsed.get_payload(decode=True)
                    body = payload.decode("utf-8", errors="replace") if payload is not None else ""

                if not body.strip() and html_body:
                    import html as html_mod
                    import re
                    text = re.sub(r"<[^>]+>", " ", html_body)
                    body = re.sub(r" {2,}", " ", html_mod.unescape(text)).strip()

                try:
                    received_at = email_lib.utils.parsedate_to_datetime(received_str).astimezone(timezone.utc)
                except Exception:
                    received_at = datetime.now(timezone.utc)

                db_id = save_inbox_message(msg_id, from_email, subject, body, received_at)
                if db_id:
                    messages.append({
                        "id": db_id,
                        "message_id": msg_id,
                        "from_email": from_email,
                        "subject": subject,
                        "body": body,
                        "received_at": received_at,
                    })

    except Exception as e:
        logger.error("read_inbox failed: %s", e)

    logger.info("read_inbox: fetched %d new messages", len(messages))
    return messages
