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


class CandidateFetcher(Protocol):
    """Fetch contacts with status='candidate'. Returns list of contact dicts."""
    def __call__(self, limit: int = 50) -> list[dict]: ...


class ContactUpdater(Protocol):
    """Update a contact's status and fit_score in the database."""
    def __call__(self, contact_id: int, status: str, fit_score: int, notes: str = "") -> None: ...


class PageFetcher(Protocol):
    """Fetch plain text content of a URL. Returns empty string on failure."""
    def __call__(self, url: str) -> str: ...


class CityContextFetcher(Protocol):
    """Return market_character and market_notes for a city."""
    def __call__(self, city: str, country: str = "DE") -> dict: ...


class RunStarter(Protocol):
    """Log the start of an agent run. Returns run_id."""
    def __call__(self, agent_name: str, input_data: dict) -> int: ...


class RunFinisher(Protocol):
    """Log the completion of an agent run."""
    def __call__(self, run_id: int, status: str, summary: str, output_data: dict) -> None: ...
