"""Password hashing and encrypted TOTP-secret storage for user accounts."""
import base64
import hashlib

import bcrypt
from cryptography.fernet import Fernet

MIN_PASSWORD_CHARS = 12
MAX_PASSWORD_BYTES = 72  # bcrypt refuses anything longer


def password_problem(password: str) -> str | None:
    """None if the password is acceptable, else "short" or "long"."""
    if len(password) < MIN_PASSWORD_CHARS:
        return "short"
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        return "long"
    return None


def hash_password(password: str) -> str:
    """Return a bcrypt hash (salt included) suitable for storage."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


# A real bcrypt hash at the normal cost. Login checks a submitted password against it when the
# account is missing or disabled, so every attempt costs the same time and the response time
# does not reveal which emails have accounts.
DUMMY_PASSWORD_HASH = bcrypt.hashpw(b"dummy-password-for-timing", bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """
    Check a plaintext password against a stored bcrypt hash.
    Never raises — a malformed/empty hash simply fails the check.
    """
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def encrypt_totp_secret(secret: str, encryption_key: str) -> str:
    """Encrypt a TOTP seed using a key deterministically derived from config."""
    return _fernet(encryption_key).encrypt(secret.encode("utf-8")).decode("utf-8")


def decrypt_totp_secret(ciphertext: str, encryption_key: str) -> str:
    """Decrypt a stored TOTP seed; callers must handle invalid stored values."""
    return _fernet(encryption_key).decrypt(ciphertext.encode("utf-8")).decode("utf-8")


def encrypt_private(text: str, encryption_key: str) -> str:
    """Encrypt other private values at rest (the income calculator's saved figures)."""
    return _fernet(encryption_key).encrypt(text.encode("utf-8")).decode("utf-8")


def decrypt_private(ciphertext: str, encryption_key: str) -> str:
    return _fernet(encryption_key).decrypt(ciphertext.encode("utf-8")).decode("utf-8")


def _fernet(encryption_key: str) -> Fernet:
    key_bytes = hashlib.sha256(encryption_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(key_bytes))
