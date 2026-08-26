import logging
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

from gcrm import vertical
from gcrm.mission import Mission

load_dotenv()

logger = logging.getLogger(__name__)

# --- Database ---
DATABASE_URL: str = os.environ["DATABASE_URL"]

# --- AI backends ---
DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

# --- Google Maps ---
GOOGLE_MAPS_API_KEY: str = os.getenv("GOOGLE_MAPS_API_KEY", "")

# --- Whisper (self-hosted transcription, internal container on the compose network) ---
WHISPER_URL: str = os.getenv("WHISPER_URL", "http://whisper:9000")

# --- Bright Data ---
BRIGHTDATA_API_TOKEN: str = os.getenv("BRIGHTDATA_API_TOKEN", "")

# --- Mail (SMTP + IMAP) ---
MAIL_SMTP_HOST: str = os.getenv("MAIL_SMTP_HOST", "")
MAIL_SMTP_PORT: int = int(os.getenv("MAIL_SMTP_PORT", "587"))
MAIL_IMAP_HOST: str = os.getenv("MAIL_IMAP_HOST", "")
MAIL_IMAP_PORT: int = int(os.getenv("MAIL_IMAP_PORT", "143"))
MAIL_USERNAME: str = os.getenv("MAIL_USERNAME", "")
MAIL_PASSWORD: str = os.getenv("MAIL_PASSWORD", "")
# From address for outgoing emails — can be an alias. Defaults to MAIL_USERNAME.
MAIL_FROM_EMAIL: str = os.getenv("MAIL_FROM_EMAIL", "") or os.getenv("MAIL_USERNAME", "")

# --- App ---
HOST: str = os.getenv("HOST", "127.0.0.1")
PORT: int = int(os.getenv("PORT", "8000"))

# Deployment environment. Set APP_ENV=production in the deployed .env so the app
# fails closed on missing or default signing secrets instead of booting insecure.
APP_ENV: str = os.getenv("APP_ENV", "development")

_PLACEHOLDER_SECRET = "change-me-in-production"


def resolve_secret(name: str, value: str | None, app_env: str) -> str:
    """
    Resolve a signing secret, failing closed in production.

    A real, non-placeholder value is used as-is. In production, a missing or
    placeholder value is a fatal misconfiguration (raises at startup). Outside
    production we generate a random per-process secret so local/dev/test runs
    work without shipping a guessable default — such tokens/sessions simply do
    not survive a restart.
    """
    if value and value != _PLACEHOLDER_SECRET:
        return value
    if app_env == "production":
        raise RuntimeError(
            f"{name} must be set to a strong random value in production "
            f"(generate one with: openssl rand -hex 32)"
        )
    logger.warning(
        "%s is not set — using a random ephemeral secret for this process; "
        "tokens/sessions will not survive a restart. Set %s and APP_ENV=production "
        "for a real deployment.",
        name, name,
    )
    return secrets.token_hex(32)


# Mobile JSON API: secret for signing bearer JWTs.
JWT_SECRET: str = resolve_secret("JWT_SECRET", os.getenv("JWT_SECRET"), APP_ENV)

# Mobile bearer-JWT lifetime — 30 days by default. Re-logging in within the
# window mints a fresh token; tokens stay revocable via per-user token_version.
TOKEN_EXPIRY_HOURS: int = int(os.getenv("TOKEN_EXPIRY_HOURS", "720"))

# Web UI: secret for signing the Starlette session cookie.
SESSION_SECRET: str = resolve_secret("SESSION_SECRET", os.getenv("SESSION_SECRET"), APP_ENV)

# Secure-flag the session cookie when served over HTTPS (production). Leave false
# for local HTTP dev, or the browser won't send the cookie back.
SESSION_COOKIE_SECURE: bool = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"

# Encrypt TOTP seeds at rest. Defaults to the already-required session secret
# so adding account features cannot lock an existing production out at startup.
ACCOUNT_ENCRYPTION_KEY: str = os.getenv("ACCOUNT_ENCRYPTION_KEY", SESSION_SECRET)
APP_PUBLIC_URL: str = os.getenv("APP_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/")

# Only these direct peers may supply X-Forwarded-For. Apache runs locally in
# production; requests that reach Uvicorn directly must use their socket IP.
TRUSTED_PROXY_IPS: frozenset[str] = frozenset(
    ip.strip() for ip in os.getenv("TRUSTED_PROXY_IPS", "127.0.0.1,::1").split(",") if ip.strip()
)

# --- Business-card capture ---
# Where photographed business-card images are stored (a Docker volume in prod).
CARD_IMAGE_DIR: str = os.getenv("CARD_IMAGE_DIR", "/data/card-images")
# Card images are personal data — delete on confirm by default (we keep the
# extracted text). Set >0 to retain the image file for that many days instead.
CARD_IMAGE_RETENTION_DAYS: int = int(os.getenv("CARD_IMAGE_RETENTION_DAYS", "0"))

# Max accepted upload size (card images, voice memos) — guards against memory
# exhaustion from an oversized multipart body.
MAX_UPLOAD_BYTES: int = int(os.getenv("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))

# --- Scout threshold ---
# Contacts scoring below this are dropped. Start high, lower when you need more volume.
SCOUT_THRESHOLD: int = int(os.getenv("SCOUT_THRESHOLD", "75"))

# --- Email ---
# Set EMAIL_ENABLED=false to disable all outgoing email (approvals will be marked approved_unsent)
EMAIL_ENABLED: bool = os.getenv("EMAIL_ENABLED", "true").lower() == "true"

# --- Open Brain memory ---
OPEN_BRAIN_URL: str = os.getenv("OPEN_BRAIN_URL", "")
OPEN_BRAIN_TOKEN: str = os.getenv("OPEN_BRAIN_TOKEN", "")

# --- LLM backends ---
# The active backends are administrator-selectable in Settings. These variables
# retain safe boot-time defaults when the database is not yet available.
DEFAULT_CHEAP_LLM: str = os.getenv("DEFAULT_CHEAP_LLM", "deepseek-v4-flash")
DEFAULT_SMART_LLM: str = os.getenv("DEFAULT_SMART_LLM", "claude")
CHEAP_LLM = "selected-cheap"
SMART_LLM = "selected-smart"

# --- Privacy retention ---
# These are conservative operational defaults, not a substitute for the
# controller's documented retention schedule. The daily retention job reads
# these values so a reviewed policy can tighten them without a code change.
CONTACT_RETENTION_DAYS: int = int(os.getenv("CONTACT_RETENTION_DAYS", "1095"))
INBOX_RETENTION_DAYS: int = int(os.getenv("INBOX_RETENTION_DAYS", "365"))
# Agent-run records can contain information about multiple contacts, so they
# follow the longest contact lifecycle rather than a shorter draft lifetime.
AGENT_RUN_RETENTION_DAYS: int = int(os.getenv("AGENT_RUN_RETENTION_DAYS", str(CONTACT_RETENTION_DAYS)))
AUDIT_LOG_RETENTION_DAYS: int = int(os.getenv("AUDIT_LOG_RETENTION_DAYS", "730"))
PUSH_TOKEN_RETENTION_DAYS: int = int(os.getenv("PUSH_TOKEN_RETENTION_DAYS", "90"))

# How many NEW businesses one research scan processes (an alphabetical batch).
# Each scan picks up where the last left off, so repeated scans march through the
# full list instead of redoing the same ones. Raise to scan more per press.
SCAN_CUTOFF: int = int(os.getenv("SCAN_CUTOFF", "25"))

# --- Company research dossier ---
# Feature flag: enable evidence-backed company crawling via Crawl4AI.
# Disabled by default. When enabled, the opportunity agent fetches a research
# dossier (crawling 5-8 pages of the official website) instead of a single
# homepage fetch. Crawl4AI is the primary fetcher, falling back to Bright Data
# and plain HTTP.
RESEARCH_DOSSIER_ENABLED: bool = os.getenv("RESEARCH_DOSSIER_ENABLED", "false").lower() == "true"

# --- Mission ---
# Edit gcrm/vertical.py to change the target domain. Nothing else needs to change.
# Edit gcrm/vertical_context.md to provide richer narrative context for outreach emails.

_context_path = Path(__file__).parent / "vertical_context.md"
_vertical_context: str = _context_path.read_text(encoding="utf-8") if _context_path.exists() else ""

ACTIVE_MISSION: Mission = Mission(
    goal=vertical.GOAL,
    identity=vertical.IDENTITY,
    targets=vertical.TARGETS,
    fit_criteria=vertical.FIT_CRITERIA,
    outreach_style=vertical.OUTREACH_STYLE,
    language_default=vertical.LANGUAGE_DEFAULT,
    website=vertical.WEBSITE,
    context=_vertical_context,
    privacy_notice_url=f"{APP_PUBLIC_URL}/privacy",
)
