"""_parse_message: inbox fields and the sender-authentication signal."""
import email as email_lib
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from gcrm.tools.email import _parse_message

PASS_HEADER = "mx.example; spf=pass smtp.mailfrom=b.de"


def parse(body="hello", html=None, auth=PASS_HEADER, sender="a@b.de"):
    message = EmailMessage()
    message["From"] = sender
    message["To"] = "me@example.test"
    message["Subject"] = "Re: hello"
    message["Message-ID"] = "<1@b.de>"
    if auth:
        message["Authentication-Results"] = auth
    if html is None:
        message.set_content(body)
    else:
        message.set_content(html, subtype="html")
    return _parse_message(email_lib.message_from_bytes(message.as_bytes()))


def test_plain_text_mail_from_an_authenticated_domain_is_authenticated():
    parsed = parse()
    assert parsed["authenticated"] is True
    assert parsed["body"].strip() == "hello"


def test_a_pass_for_another_domain_does_not_authenticate_the_sender():
    assert parse(auth="mx.example; spf=pass smtp.mailfrom=other.de")["authenticated"] is False


def test_a_failed_check_does_not_authenticate_the_sender():
    assert parse(auth="mx.example; spf=fail smtp.mailfrom=b.de")["authenticated"] is False


def test_no_authentication_header_means_not_authenticated():
    assert parse(auth=None)["authenticated"] is False


def test_multipart_mail_with_only_an_html_part_is_reduced_to_text():
    message = MIMEMultipart("mixed")
    message["From"] = "a@b.de"
    message["Message-ID"] = "<2@b.de>"
    message.attach(MIMEText("<p>Hello <b>there</b></p>", "html"))
    parsed = _parse_message(email_lib.message_from_bytes(message.as_bytes()))
    assert "<" not in parsed["body"]
    assert "Hello" in parsed["body"] and "there" in parsed["body"]
    assert parsed["authenticated"] is False
