"""Unit tests for the fail-closed signing-secret resolver (gcrm.config.resolve_secret)."""
import pytest

from gcrm.config import resolve_secret


def test_real_value_used_as_is():
    assert resolve_secret("JWT_SECRET", "a-real-strong-secret", "production") == "a-real-strong-secret"


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
