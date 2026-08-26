"""
Email tools: SMTP sending and IMAP inbox reading over standard SMTP/IMAP
(the christopherrehm.de mail server).
"""
import email as email_lib
import imaplib
import logging
import smtplib
import ssl
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from gcrm.config import (
    EMAIL_ENABLED,
    MAIL_FROM_EMAIL,
    MAIL_IMAP_HOST,
    MAIL_IMAP_PORT,
    MAIL_PASSWORD,
    MAIL_SMTP_HOST,
    MAIL_SMTP_PORT,
    MAIL_USERNAME,
)
from gcrm.tools.db import save_inbox_message

logger = logging.getLogger(__name__)

_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


def _starttls_context(host: str) -> ssl.SSLContext:
    """Verify the server certificate for remote hosts. A loopback mail server
    (e.g. a local dev bridge) may present a self-signed cert, so verification
    is skipped there; the real christopherrehm.de host gets full verification."""
    ctx = ssl.create_default_context()
    if host in _LOOPBACK_HOSTS:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def send_email(to_email: str, subject: str, body: str, from_email: str | None = None) -> bool:
    """
    Send a plain-text email via SMTP, authenticated as MAIL_USERNAME.
    `from_email` overrides the From header (still sent through the same
    login) — the caller is responsible for validating it against
    MAIL_SENDER_OPTIONS; this function trusts whatever it's given.
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
    msg["From"] = from_email or MAIL_FROM_EMAIL
    msg["To"] = to_email
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP(MAIL_SMTP_HOST, MAIL_SMTP_PORT) as smtp:
            smtp.ehlo()
            smtp.starttls(context=_starttls_context(MAIL_SMTP_HOST))
            smtp.login(MAIL_USERNAME, MAIL_PASSWORD)
            smtp.sendmail(MAIL_USERNAME, [to_email], msg.as_string())
        logger.info("send_email: sent to %s — %s", to_email, subject)
        return True
    except Exception as error:
        logger.error("send_email failed to %s: %s", to_email, error)
        return False


def _parse_message(parsed) -> dict:
    """Extract inbox fields and a conservative sender-authentication signal.

    Authentication-Results parsing intentionally stays simple: it accepts an
    SPF or DKIM pass only when the From domain also appears in the header. This
    is a safety gate for autonomous actions, not a complete DMARC evaluator.
    """
    msg_id = parsed.get("Message-ID", "").strip()
    from_email = email_lib.utils.parseaddr(parsed.get("From", ""))[1]
    from_domain = from_email.rpartition("@")[2].lower()
    authentication_results = parsed.get("Authentication-Results", "").lower()
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

    return {
        "message_id": msg_id,
        "from_email": from_email,
        "subject": subject,
        "body": body,
        "received_at": received_at,
        "content_type": parsed.get_content_type().lower(),
        "authenticated": bool(
            from_domain
            and from_domain in authentication_results
            and re.search(r"(?:spf|dkim)=pass\b", authentication_results)
        ),
    }


def read_inbox(limit: int = 50, since_days: int = 14) -> list[dict]:
    """
    Read emails from the INBOX via IMAP (last since_days days).
    Saves each message to the inbox_messages table (deduplication handled there).
    Returns list of message dicts: {id, message_id, from_email, subject, body, received_at}.
    """
    from datetime import timedelta
    messages = []
    try:
        with imaplib.IMAP4(MAIL_IMAP_HOST, MAIL_IMAP_PORT) as imap:
            imap.starttls(ssl_context=_starttls_context(MAIL_IMAP_HOST))
            imap.login(MAIL_USERNAME, MAIL_PASSWORD)
            imap.select("INBOX")

            since_date = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%d-%b-%Y")
            _, data = imap.search(None, f"SINCE {since_date}")
            message_ids = data[0].split()

            for uid in message_ids[-limit:]:
                _, msg_data = imap.fetch(uid, "(RFC822)")
                raw = msg_data[0][1]
                parsed = email_lib.message_from_bytes(raw)
                fields = _parse_message(parsed)

                db_id = save_inbox_message(
                    fields["message_id"], fields["from_email"], fields["subject"],
                    fields["body"], fields["received_at"],
                )
                if db_id:
                    messages.append({"id": db_id, **fields})

    except Exception as error:
        logger.error("read_inbox failed: %s", error)

    logger.info("read_inbox: fetched %d new messages", len(messages))
    return messages
