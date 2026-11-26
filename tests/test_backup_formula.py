"""Spreadsheet formula neutralising for the exported CSV files."""
import pytest

from gcrm.backup_export import neutralize_formula


@pytest.mark.parametrize("text", ["=1+1", "@SUM(A1)", "\tcmd", "-cmd|x", "+cmd|x", "+1+cmd|' /C calc'!A0",
                                  "-2+3+cmd|'/C calc'!A0", "-1;SUM(A1)", "+1+SUM(A1)", "-2+3+cmd|x"])
def test_text_a_spreadsheet_would_run_gets_a_leading_apostrophe(text):
    assert neutralize_formula(text) == "'" + text


@pytest.mark.parametrize("text", ["+49 171 1234567", "+49 (0)171-123 45 67", "-12.50", "-3", "+1 555 0100", "-2+3", "+1+2", "+49 171 1234567 + 1", "Hello", "a=b", "12"])
def test_numbers_and_phone_numbers_are_left_alone(text):
    assert neutralize_formula(text) == text
