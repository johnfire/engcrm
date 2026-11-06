"""Unit tests for the fail-closed signing-secret resolver (gcrm.config.resolve_secret)."""
import hashlib

import pytest

from gcrm.config import resolve_secret


def test_real_value_used_as_is():
    secret = hashlib.sha256(b"public-config-test-vector").hexdigest()
    assert resolve_secret("JWT_SECRET", secret, "production") == secret


def test_production_rejects_missing_secret():
    with pytest.raises(RuntimeError):
        resolve_secret("JWT_SECRET", None, "production")


def test_production_rejects_placeholder_secret():
    with pytest.raises(RuntimeError):
        resolve_secret("JWT_SECRET", "change-me-in-production", "production")


def test_development_generates_ephemeral_secret():
    generated = resolve_secret("JWT_SECRET", None, "development")
    assert generated and generated != "change-me-in-production"
    assert len(generated) >= 32


def test_development_real_value_still_used():
    assert resolve_secret("SESSION_SECRET", "dev-set-secret", "development") == "dev-set-secret"


@pytest.mark.parametrize("secret", ["x", "password" * 8, "a" * 64, "0123456789abcdef" * 4,
                                   "change-me-in-production-with-extra-padding"])
def test_production_refuses_trivial_or_predictable_configured_secrets(secret):
    with pytest.raises(RuntimeError):
        resolve_secret("JWT_SECRET", secret, "production")


def test_production_secret_minimum_is_exactly_32_bytes():
    secret = hashlib.sha256(b"public-config-boundary-test-vector").hexdigest()[:32]
    assert len(secret) == 32
    with pytest.raises(RuntimeError):
        resolve_secret("JWT_SECRET", secret[:31], "production")
    assert resolve_secret("JWT_SECRET", secret, "production") == secret
