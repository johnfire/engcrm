"""Email messages for bookings. Pure: builds MIME messages, sends nothing.

An invite is multipart/mixed holding multipart/alternative (plain text plus an inline
text/calendar part with the method) and the same .ics as an attachment. Gmail and
Outlook read the inline part and offer accept/decline; Proton and Apple also take the
attachment.
"""
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid


def _headers(message: MIMEMultipart, sender: str, sender_name: str, recipient: str, subject: str) -> None:
    message["Subject"] = subject
    message["From"] = formataddr((sender_name, sender)) if sender_name else sender
    message["To"] = recipient
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain=sender.rpartition("@")[2] or None)


def build_plain_email(*, sender: str, sender_name: str, recipient: str, subject: str, body: str) -> MIMEMultipart:
    message = MIMEMultipart("mixed")
    _headers(message, sender, sender_name, recipient, subject)
    message.attach(MIMEText(body, "plain", "utf-8"))
    return message


def _calendar_part(ics: bytes, method: str) -> MIMEBase:
    part = MIMEBase("text", "calendar", method=method, charset="utf-8")
    part.set_payload(ics.decode("utf-8"), charset="utf-8")
    return part


def _attachment(ics: bytes, method: str) -> MIMEBase:
    attachment = MIMEBase("application", "ics", name="invite.ics")
    attachment.set_payload(ics)
    encoders.encode_base64(attachment)
    filename = "cancel.ics" if method == "CANCEL" else "invite.ics"
    attachment.add_header("Content-Disposition", "attachment", filename=filename)
    return attachment


def build_invite_email(*, sender: str, sender_name: str, recipient: str, subject: str, body: str,
                       ics: bytes, method: str) -> MIMEMultipart:
    message = MIMEMultipart("mixed")
    _headers(message, sender, sender_name, recipient, subject)
    alternative = MIMEMultipart("alternative")
    alternative.attach(MIMEText(body, "plain", "utf-8"))
    alternative.attach(_calendar_part(ics, method))
    message.attach(alternative)
    message.attach(_attachment(ics, method))
    return message
