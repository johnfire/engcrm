from typing import Any, Protocol


class AgentMission(Protocol):
    """
    What the agent system is working toward.
    Any object with these string attributes satisfies this protocol.
    """
    goal: str
    identity: str
    targets: str
    fit_criteria: str
    outreach_style: str
    language_default: str


class LanguageModel(Protocol):
    """Any LangChain-compatible chat model (BaseChatModel) satisfies this."""
    def invoke(self, messages: list) -> Any:
        """Returns an object with a .content (str) attribute."""
        ...


class ReadyContactFetcher(Protocol):
    """Fetch contacts with status='cold' that are ready for first outreach."""
    def __call__(self, limit: int = 20) -> list[dict]: ...


class InteractionFetcher(Protocol):
    """Fetch all logged interactions for a contact, newest first."""
    def __call__(self, contact_id: int) -> list[dict]: ...


class PageFetcher(Protocol):
    """Fetch plain text content of a URL. Returns empty string on failure."""
    def __call__(self, url: str) -> str: ...


class ComplianceChecker(Protocol):
    """
    Check whether a contact can be emailed.
    Returns True if outreach is permitted (no opt-out, not erased).
    """
    def __call__(self, contact_id: int) -> bool: ...


class ApprovalQueuer(Protocol):
    """Insert a drafted email into the approval queue. Returns queue item id."""
    def __call__(
        self,
        contact_id: int,
        run_id: int,
        subject: str,
        body: str,
    ) -> int: ...


class RunStarter(Protocol):
    """Log the start of an agent run. Returns run_id."""
    def __call__(self, agent_name: str, input_data: dict) -> int: ...


class RunFinisher(Protocol):
    """Log the completion of an agent run."""
    def __call__(self, run_id: int, status: str, summary: str, output_data: dict) -> None: ...
