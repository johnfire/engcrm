from typing import Any, Protocol


class LanguageModel(Protocol):
    def invoke(self, messages: list) -> Any: ...


class WebSearcher(Protocol):
    def __call__(self, query: str) -> list[dict]: ...


class PageFetcher(Protocol):
    """Fetch a URL and return its plain text content. Returns empty string on failure."""
    def __call__(self, url: str) -> str: ...


class ContactFetcher(Protocol):
    """Fetch contacts that need enrichment (missing website or email)."""
    def __call__(self, limit: int) -> list[dict]: ...


class ContactUpdater(Protocol):
    """Update a contact's website, email, and/or phone."""
    def __call__(self, contact_id: int, **kwargs) -> None: ...


class RunStarter(Protocol):
    def __call__(self, agent_name: str, input_data: dict) -> int: ...


class RunFinisher(Protocol):
    def __call__(self, run_id: int, status: str, summary: str, output_data: dict) -> None: ...
