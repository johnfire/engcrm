"""Lightweight in-memory rate limiting for the authentication endpoints.

Throttles repeated login / token-issue attempts per client to blunt
brute-forcing. Process-local (no external store) — fine for the single-worker
deployment; if the app is ever scaled to multiple workers, move the counter to
a shared store (e.g. Redis). The limiter fails OPEN: any internal error logs a
warning and allows the request, so a limiter bug can never lock users out.
"""
import logging
import time
from threading import Lock

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


class FixedWindowRateLimiter:
    """At most `max_attempts` per `window_seconds` for a given key."""

    def __init__(self, max_attempts: int, window_seconds: float):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._hits: dict[str, tuple[float, int]] = {}
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        """Record an attempt for `key`; return False once the window is exceeded."""
        now = time.monotonic()
        with self._lock:
            window_start, count = self._hits.get(key, (now, 0))
            if now - window_start >= self.window_seconds:
                window_start, count = now, 0
            count += 1
            self._hits[key] = (window_start, count)
            return count <= self.max_attempts

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


# 10 auth attempts per minute per client is generous for humans, hostile to
# brute-force. Login is infrequent, so this won't inconvenience real users.
_auth_limiter = FixedWindowRateLimiter(max_attempts=10, window_seconds=60.0)


def client_key(request: Request) -> str:
    """Return the forwarded client only when a trusted proxy supplied it."""
    from gcrm.config import TRUSTED_PROXY_IPS

    peer = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded and peer in TRUSTED_PROXY_IPS:
        return forwarded.split(",")[0].strip()
    return peer


def rate_limit_auth(request: Request) -> None:
    """FastAPI dependency: throttle repeated auth attempts per client (HTTP 429)."""
    try:
        allowed = _auth_limiter.allow(client_key(request))
    except Exception as error:  # never let the limiter itself block a legitimate login
        logger.warning("auth rate limiter error (failing open): %s", error)
        return
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many attempts — please wait a minute and try again.",
            headers={"Retry-After": "60"},
        )
