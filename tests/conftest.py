"""
Set dummy environment variables before any src.* imports so that
config.py doesn't raise KeyError when DATABASE_URL etc. are absent.
All DB calls in tests are mocked — these values are never used.
"""
import os

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("PROTON_EMAIL", "test@test.com")
os.environ.setdefault("PROTON_PASSWORD", "test")
os.environ.setdefault("DEEPSEEK_API_KEY", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-not-for-production")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-not-for-production")

import pytest


@pytest.fixture(autouse=True)
def _reset_auth_rate_limiter():
    """Start each test with a clean auth rate limiter so the process-global
    counter doesn't couple otherwise-independent tests."""
    from gcrm.api.rate_limit import _auth_limiter
    _auth_limiter.reset()
    yield
