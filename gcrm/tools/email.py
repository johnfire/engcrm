"""
Email tools: SMTP sending and IMAP inbox reading via Proton Bridge.
Proton Bridge runs locally and exposes standard IMAP/SMTP ports.
"""
import email as email_lib
import imaplib
import logging
import smtplib
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
            smtp.starttls()
            smtp.login(PROTON_EMAIL, PROTON_PASSWORD)
            smtp.sendmail(PROTON_EMAIL, [to_email], msg.as_string())
        logger.info("send_email: sent to %s — %s", to_email, subject)
        return True
    except Exception as e:
        logger.error("send_email failed to %s: %s", to_email, e)
        return False


def read_inbox(limit: int = 50) -> list[dict]:
    """
    Read unseen emails from the INBOX via Proton Bridge IMAP.
    Saves each message to the inbox_messages table (deduplication handled there).
    Returns list of message dicts: {id, message_id, from_email, subject, body, received_at}.
    """
    messages = []
    try:
        with imaplib.IMAP4(PROTON_IMAP_HOST, PROTON_IMAP_PORT) as imap:
            imap.starttls()
            imap.login(PROTON_EMAIL, PROTON_PASSWORD)
            imap.select("INBOX")

            _, data = imap.search(None, "UNSEEN")
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
                if parsed.is_multipart():
                    for part in parsed.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                            break
                else:
                    body = parsed.get_payload(decode=True).decode("utf-8", errors="replace")

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
