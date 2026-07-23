from typing import Any, Protocol


class LanguageModel(Protocol):
    def invoke(self, messages: list) -> Any: ...


class ContactFetcher(Protocol):
    def __call__(self, limit: int) -> list[dict]: ...


class InteractionFetcher(Protocol):
    def __call__(self, contact_id: int) -> list[dict]: ...


class PageFetcher(Protocol):
    def __call__(self, url: str) -> str: ...


class AnalysisSaver(Protocol):
    def __call__(self, contact_id: int, analysis: dict, model_used: str) -> None: ...


class RunStarter(Protocol):
    def __call__(self, agent_name: str, input_data: dict) -> int: ...


class RunFinisher(Protocol):
    def __call__(self, run_id: int, status: str, summary: str, output_data: dict) -> None: ...
