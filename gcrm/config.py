import os
from dotenv import load_dotenv
from gcrm.mission import Mission
from gcrm import vertical

load_dotenv()

# --- Database ---
DATABASE_URL: str = os.environ["DATABASE_URL"]

# --- AI backends ---
DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

# --- Google Maps ---
GOOGLE_MAPS_API_KEY: str = os.getenv("GOOGLE_MAPS_API_KEY", "")

# --- Proton Bridge (IMAP + SMTP) ---
PROTON_IMAP_HOST: str = os.getenv("PROTON_IMAP_HOST", "127.0.0.1")
PROTON_IMAP_PORT: int = int(os.getenv("PROTON_IMAP_PORT", "1143"))
PROTON_SMTP_HOST: str = os.getenv("PROTON_SMTP_HOST", "127.0.0.1")
PROTON_SMTP_PORT: int = int(os.getenv("PROTON_SMTP_PORT", "1025"))
PROTON_EMAIL: str = os.getenv("PROTON_EMAIL", "")
PROTON_PASSWORD: str = os.getenv("PROTON_PASSWORD", "")
# From address for outgoing emails — can be an alias. Defaults to PROTON_EMAIL.
PROTON_FROM_EMAIL: str = os.getenv("PROTON_FROM_EMAIL", "") or os.getenv("PROTON_EMAIL", "")

# --- App ---
HOST: str = os.getenv("HOST", "127.0.0.1")
PORT: int = int(os.getenv("PORT", "8000"))

# --- Scout threshold ---
# Contacts scoring below this are dropped. Start high, lower when you need more volume.
SCOUT_THRESHOLD: int = int(os.getenv("SCOUT_THRESHOLD", "75"))

# --- Email ---
# Set EMAIL_ENABLED=false to disable all outgoing email (approvals will be marked approved_unsent)
EMAIL_ENABLED: bool = os.getenv("EMAIL_ENABLED", "true").lower() == "true"

# --- LLM backend for cheap/high-volume tasks (research, enrichment, scouting) ---
# Options: deepseek-chat, claude-haiku
CHEAP_LLM: str = os.getenv("CHEAP_LLM", "deepseek-chat")

# --- Mission ---
# Edit gcrm/vertical.py to change the target domain. Nothing else needs to change.

ACTIVE_MISSION: Mission = Mission(
    goal=vertical.GOAL,
    identity=vertical.IDENTITY,
    targets=vertical.TARGETS,
    fit_criteria=vertical.FIT_CRITERIA,
    outreach_style=vertical.OUTREACH_STYLE,
    language_default=vertical.LANGUAGE_DEFAULT,
    website=vertical.WEBSITE,
)
