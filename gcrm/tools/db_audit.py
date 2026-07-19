"""Append-only audit logging for user and automation state changes."""
import logging

from gcrm.audit_context import current_audit_context
from gcrm.db.connection import db

logger = logging.getLogger(__name__)


def log_audit(
    actor: str | None,
    actor_type: str | None,
    action: str,
    target: str | None = None,
    outcome: str | None = None,
    correlation_id: str | None = None,
) -> None:
    """Record an action without allowing audit-storage failures to block work."""
    context = current_audit_context()
    resolved_actor = actor or (context.actor if context else "system-job")
    resolved_actor_type = actor_type or (context.actor_type if context else "system-job")
    resolved_correlation_id = correlation_id or (context.correlation_id if context else None)
    try:
        with db() as conn:
            conn.cursor().execute(
                """
                INSERT INTO audit_log (actor, actor_type, action, target, outcome, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    resolved_actor,
                    resolved_actor_type,
                    action,
                    target,
                    outcome,
                    resolved_correlation_id,
                ),
            )
    except Exception as error:
        logger.warning("audit logging failed: action=%s target=%s error=%s", action, target, error)
