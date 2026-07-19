"""Password hashing and encrypted TOTP-secret storage for user accounts."""
import base64
import hashlib

import bcrypt
from cryptography.fernet import Fernet


def hash_password(password: str) -> str:
    """Return a bcrypt hash (salt included) suitable for storage."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


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


def _fernet(encryption_key: str) -> Fernet:
    key_bytes = hashlib.sha256(encryption_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(key_bytes))
