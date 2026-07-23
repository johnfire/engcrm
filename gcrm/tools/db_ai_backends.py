"""Persisted administrator selection for CRM AI backends."""
from gcrm.config import DEFAULT_CHEAP_LLM, DEFAULT_SMART_LLM
from gcrm.db.connection import db
from gcrm.tools.db_account_lifecycle import get_default_workspace_id

CHEAP_MODELS = ("deepseek-v4-flash", "claude-haiku")
SMART_MODELS = ("deepseek-v4-flash", "claude")


def get_ai_backends() -> dict[str, str]:
    """Return the selected models, or the documented defaults before setup."""
    workspace_id = get_default_workspace_id()
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT cheap_llm, smart_llm FROM workspace_ai_backends WHERE workspace_id = %s",
            (workspace_id,),
        )
        selected = cursor.fetchone()
    return dict(selected) if selected else {"cheap_llm": DEFAULT_CHEAP_LLM, "smart_llm": DEFAULT_SMART_LLM}


def set_ai_backends(cheap_llm: str, smart_llm: str) -> None:
    """Validate and persist the workspace-wide administrator selection."""
    if cheap_llm not in CHEAP_MODELS or smart_llm not in SMART_MODELS:
        raise ValueError("Unsupported AI backend selection")
    workspace_id = get_default_workspace_id()
    with db() as connection:
        connection.cursor().execute(
            """INSERT INTO workspace_ai_backends (workspace_id, cheap_llm, smart_llm)
            VALUES (%s, %s, %s)
            ON CONFLICT (workspace_id) DO UPDATE SET cheap_llm = EXCLUDED.cheap_llm,
                smart_llm = EXCLUDED.smart_llm, updated_at = NOW()""",
            (workspace_id, cheap_llm, smart_llm),
        )
