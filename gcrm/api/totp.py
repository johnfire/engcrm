"""Minimal standards-compliant TOTP generation and verification."""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

TOTP_PERIOD_SECONDS = 30
TOTP_DIGITS = 6


def generate_totp_secret() -> str:
    """Return a cryptographically random Base32 TOTP seed."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def verify_totp_code(secret: str, code: str, now: int | None = None) -> bool:
    """Accept a current TOTP code, allowing one time-step of clock skew."""
    if not code.isdigit() or len(code) != TOTP_DIGITS:
        return False
    timestamp = now if now is not None else int(time.time())
    return any(hmac.compare_digest(_totp_code(secret, timestamp + offset), code) for offset in (-30, 0, 30))


def build_totp_uri(secret: str, email: str) -> str:
    """Return an otpauth URI suitable for authenticator-app setup."""
    label = quote(f"EngCRM:{email}")
    return f"otpauth://totp/{label}?secret={secret}&issuer=EngCRM&digits={TOTP_DIGITS}&period={TOTP_PERIOD_SECONDS}"


def _totp_code(secret: str, timestamp: int) -> str:
    padding = "=" * (-len(secret) % 8)
    key = base64.b32decode(secret + padding, casefold=True)
    counter = struct.pack(">Q", timestamp // TOTP_PERIOD_SECONDS)
    digest = hmac.new(key, counter, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(number % (10 ** TOTP_DIGITS)).zfill(TOTP_DIGITS)
