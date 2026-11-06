"""Deployment configuration checks without reading any real deployment secrets."""
import os
import subprocess
import sys

import pytest

from gcrm.config_security import validate_deployment_security

JWT = "5ce8093d42eb7760f62d615ab539bbd36bba78acd649f7e752e9b158a6b31294"
SESSION = "d83cf02ae450adb7e93852ad23b7c2df6dd6884938a16ecb71345d08c921f50a"


@pytest.mark.parametrize("url,cookie", [("http://crm.example.test", True), ("https://crm.example.test", False),
                                      ("http://127.0.0.1:8086", False)])
def test_production_requires_both_https_and_secure_cookies(url, cookie):
    with pytest.raises(RuntimeError):
        validate_deployment_security("production", JWT, SESSION, url, cookie)


@pytest.mark.parametrize("url", ["/relative", "ftp://crm.example.test", "https://user:password@crm.example.test",
                                 "https://crm.example.test?query=secret", "https://crm.example.test#fragment",
                                 "https://crm.example.test:99999", "https://[invalid",
                                 "https://crm.example.test\n", "https://bad host.example.test"])
def test_invalid_public_urls_fail_closed(url):
    with pytest.raises(RuntimeError):
        validate_deployment_security("production", JWT, SESSION, url, True)


def test_signing_keys_must_be_independent():
    with pytest.raises(RuntimeError, match="independent"):
        validate_deployment_security("production", JWT, JWT, "https://crm.example.test", True)


def test_valid_production_and_isolated_loopback_staging_are_supported():
    validate_deployment_security("production", JWT, SESSION, "https://crm.example.test/reviewer", True)
    validate_deployment_security("staging", JWT, SESSION, "http://127.0.0.1:8086", False)
    with pytest.raises(RuntimeError):
        validate_deployment_security("staging", JWT, SESSION, "http://staging.example.test", False)
    validate_deployment_security("development", JWT, JWT, "http://localhost", False)


@pytest.mark.parametrize("overrides", [{"JWT_SECRET": "x"}, {"SESSION_SECRET": JWT},
                                       {"SESSION_COOKIE_SECURE": "false"}, {"APP_PUBLIC_URL": "http://crm.example.test"}])
def test_actual_config_import_refuses_unsafe_production_settings(overrides):
    environment = {**os.environ, "PYTHON_DOTENV_DISABLED": "1", "APP_ENV": "production",
                   "DATABASE_URL": "postgresql://fictional:fictional@localhost/fictional",
                   "JWT_SECRET": JWT, "SESSION_SECRET": SESSION, "ACCOUNT_ENCRYPTION_KEY": SESSION,
                   "SESSION_COOKIE_SECURE": "true", "APP_PUBLIC_URL": "https://crm.example.test",
                   **overrides}
    process = subprocess.run([sys.executable, "-c", "import gcrm.config"], env=environment,
                             capture_output=True, text=True, timeout=20)
    assert process.returncode != 0
    assert "RuntimeError" in process.stderr
    assert JWT not in process.stderr and SESSION not in process.stderr
