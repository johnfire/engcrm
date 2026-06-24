"""Tests for the shared LLM-JSON parser (objects, arrays, fences, prose)."""
import pytest

from gcrm.json_parsing import parse_llm_json


def test_clean_object():
    assert parse_llm_json('{"a": 1}') == {"a": 1}


def test_clean_array():
    assert parse_llm_json('[{"a": 1}, {"b": 2}]') == [{"a": 1}, {"b": 2}]


def test_fenced_object():
    assert parse_llm_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_fenced_array_is_not_corrupted():
    # Regression: brace-only extraction used to mangle arrays into invalid JSON.
    assert parse_llm_json('```json\n[{"a": 1}]\n```') == [{"a": 1}]


def test_prose_wrapped_object():
    assert parse_llm_json('Sure, here it is: {"a": 1} — done') == {"a": 1}


def test_invalid_raises():
    with pytest.raises(Exception):
        parse_llm_json("not json at all")
