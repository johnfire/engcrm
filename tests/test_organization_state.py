"""The contact state vocabulary: coercion, typical combinations, and the guard
that keeps the mobile app's copy of the vocabulary identical to this one."""
import re
from pathlib import Path

import pytest

from gcrm.organization_state import (
    DEFAULT_STAGE,
    DEFAULT_STATUS,
    PIPELINE_STAGES,
    STATUSES,
    SUPPRESSION_FLAGS,
    TYPICAL_STATUSES_BY_STAGE,
    coerce_stage,
    coerce_status,
    is_typical,
)

MOBILE_VOCABULARY = Path(__file__).parents[1] / "engcrm-mobile" / "services" / "organizationState.ts"


def read_mobile_list(name: str) -> tuple[str, ...]:
    """Pull one exported string array out of the TypeScript vocabulary file."""
    source = MOBILE_VOCABULARY.read_text()
    match = re.search(rf"export const {name} = \[(.*?)\]", source, re.S)
    assert match, f"{name} not found in {MOBILE_VOCABULARY.name}"
    return tuple(re.findall(r'"([a-z_]+)"', match.group(1)))


class TestCoercion:
    @pytest.mark.parametrize("stage", PIPELINE_STAGES)
    def test_keeps_every_known_stage(self, stage):
        assert coerce_stage(stage) == stage

    @pytest.mark.parametrize("status", STATUSES)
    def test_keeps_every_known_status(self, status):
        assert coerce_status(status) == status

    @pytest.mark.parametrize("unknown", ["cold", "accepted", "maybe", "", None, "DROP TABLE"])
    def test_falls_back_rather_than_losing_the_row(self, unknown):
        assert coerce_stage(unknown) == DEFAULT_STAGE
        assert coerce_status(unknown) == DEFAULT_STATUS

    def test_retired_vocabulary_is_gone(self):
        """The values migration 041 mapped away must not be selectable again."""
        retired = {"cold", "accepted", "rejected", "networking_visit", "maybe",
                   "lead_unverified", "opt_out", "bad_email", "cannot_find_more_data"}
        assert retired.isdisjoint(set(STATUSES) | set(PIPELINE_STAGES))

    def test_unknown_value_is_logged_not_swallowed(self, caplog):
        with caplog.at_level("WARNING"):
            coerce_status("accepted")
        assert "accepted" in caplog.text


class TestTypicalCombinations:
    def test_every_stage_has_expected_statuses(self):
        assert set(TYPICAL_STATUSES_BY_STAGE) == set(PIPELINE_STAGES)

    def test_expected_statuses_are_all_real_statuses(self):
        for stage, statuses in TYPICAL_STATUSES_BY_STAGE.items():
            assert set(statuses) <= set(STATUSES), stage

    def test_recognises_a_normal_pairing(self):
        assert is_typical("opportunity", "proposal")
        assert is_typical("suspect", "ready")

    def test_flags_an_odd_pairing_without_forbidding_it(self):
        assert is_typical("candidate", "proposal") is False


class TestMobileVocabularyMatches:
    """The app ships its own copy so it works offline; it must not drift."""

    def test_stages_match(self):
        assert read_mobile_list("PIPELINE_STAGES") == PIPELINE_STAGES

    def test_statuses_match(self):
        assert read_mobile_list("STATUSES") == STATUSES

    def test_flags_match(self):
        assert read_mobile_list("SUPPRESSION_FLAGS") == SUPPRESSION_FLAGS
