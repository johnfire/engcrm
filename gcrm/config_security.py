"""Pure startup checks for deployment origins and cryptographic configuration."""
import hmac
from urllib.parse import urlsplit

STRICT_ENVIRONMENTS = frozenset({"production", "staging"})
PLACEHOLDER_FRAGMENTS = ("change-me", "replace-me", "placeholder", "your-secret", "example-secret")


def is_weak_secret(secret: str) -> bool:
    """Reject obvious weak inputs; this cannot prove that an operator used randomness."""
    if len(secret.encode("utf-8")) < 32 or len(set(secret)) < 8:
        return True
    if any(fragment in secret.lower() for fragment in PLACEHOLDER_FRAGMENTS):
        return True
    return any(len(secret) % width == 0 and secret == secret[:width] * (len(secret) // width)
               for width in range(1, 17))


def validate_deployment_security(app_env: str, jwt_secret: str, session_secret: str,
                                 public_url: str, secure_cookie: bool) -> None:
    """Require independent signing keys and HTTPS, with a loopback-only staging exception."""
    if app_env not in STRICT_ENVIRONMENTS:
        return
    if hmac.compare_digest(jwt_secret.encode(), session_secret.encode()):
        raise RuntimeError("JWT_SECRET and SESSION_SECRET must be independent random values")
    try:
        parsed = urlsplit(public_url)
        valid_origin = (parsed.scheme in {"http", "https"} and parsed.hostname and parsed.port != 0
                        and not any(character.isspace() or ord(character) < 32 for character in public_url)
                        and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment)
    except ValueError:
        valid_origin = False
    if not valid_origin:
        raise RuntimeError("APP_PUBLIC_URL must be a valid HTTP(S) URL without credentials, query or fragment")
    is_local_staging = app_env == "staging" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if not is_local_staging and (parsed.scheme != "https" or not secure_cookie):
        raise RuntimeError("Public deployments require HTTPS APP_PUBLIC_URL and SESSION_COOKIE_SECURE=true")
