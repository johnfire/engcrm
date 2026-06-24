"""Tolerant parsing of JSON from an LLM response.

Strips markdown code fences, then parses the JSON — which may be an object OR an
array. If the response has surrounding prose, falls back to extracting the
outermost {...} or [...] span. One shared implementation used by the tools and
every agent. Raises json.JSONDecodeError if no valid JSON is found.
"""
import json


def parse_llm_json(text: str) -> dict | list:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
        if cleaned[:4].lower() == "json":
            cleaned = cleaned[4:]
        cleaned = cleaned.rsplit("```", 1)[0]
    cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Tolerate surrounding prose: extract the outermost {...} or [...] span.
        starts = [pos for pos in (cleaned.find("{"), cleaned.find("[")) if pos >= 0]
        if starts:
            start = min(starts)
            end = max(cleaned.rfind("}"), cleaned.rfind("]"))
            if end > start:
                return json.loads(cleaned[start : end + 1])
        raise
