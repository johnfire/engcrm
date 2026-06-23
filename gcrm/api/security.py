"""Password hashing for user accounts — bcrypt with a per-hash salt."""
import bcrypt


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
