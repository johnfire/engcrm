"""Re-export of the shared LLM-JSON parser (one implementation for all agents)."""

from gcrm.json_parsing import parse_llm_json as parse_json_response

__all__ = ["parse_json_response"]
