"""Request and job-local audit identity used by logs and durable audit events."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True)
class AuditContext:
    """The non-sensitive identity attached to one unit of CRM work."""

    actor: str
    actor_type: str
    correlation_id: str | None = None


_audit_context: ContextVar[AuditContext | None] = ContextVar("audit_context", default=None)


@contextmanager
def audit_scope(actor: str, actor_type: str, correlation_id: str | None = None) -> Iterator[None]:
    """Apply audit identity only for the current request or background job."""
    token = _audit_context.set(AuditContext(actor, actor_type, correlation_id))
    try:
        yield
    finally:
        _audit_context.reset(token)


def current_audit_context() -> AuditContext | None:
    """Return the identity currently responsible for the active work."""
    return _audit_context.get()


def set_audit_context(actor: str, actor_type: str, correlation_id: str | None = None) -> None:
    """Set identity for a dependency or long-running agent execution."""
    _audit_context.set(AuditContext(actor, actor_type, correlation_id))


class CorrelationIdFilter:
    """Add the active correlation ID to ordinary Python log records."""

    def filter(self, record) -> bool:
        context = current_audit_context()
        record.correlation_id = context.correlation_id if context else "-"
        return True
