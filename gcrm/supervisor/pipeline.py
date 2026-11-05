"""
Spawn a pipeline stage (or the whole city pipeline) as a detached background
process. Shared by the mobile (JWT) and web (session) triggers so the command
mapping lives in exactly one place.

Each stage maps to a gcrm.supervisor.run_* module; the children log to
agent_runs, so progress shows on the Activity screen.
"""
import subprocess
import sys

from gcrm.vertical import SCAN_LEVELS

# Stages exposed as buttons. 'all' is Gather for a city: research, enrichment, people finder
# (plan docs/plans/2026-11-05-gather-judge-reach-plan.md).
STAGES = ("research", "scout", "enrichment", "opportunity", "outreach", "followup", "all")

_CITY_STAGES = ("research", "scout", "enrichment", "outreach", "all")
_LEVEL_STAGES = ("research", "outreach", "all")


def validate(stage: str, city: str, level) -> None:
    """Raise ValueError if the request is invalid for the stage."""
    if stage not in STAGES:
        raise ValueError(f"stage must be one of {', '.join(STAGES)}")
    if stage in _CITY_STAGES and not (city or "").strip():
        raise ValueError(f"{stage} requires a city")
    if stage in _LEVEL_STAGES and level not in SCAN_LEVELS:
        raise ValueError(f"{stage} requires a level in {sorted(SCAN_LEVELS)}")


def _command(stage: str, city: str, level, country: str) -> list[str]:
    run = [sys.executable, "-m"]
    if stage == "research":
        return run + ["gcrm.supervisor.run_research", "--city", city,
                      "--level", str(level), "--country", country]
    if stage == "scout":
        return run + ["gcrm.supervisor.run_scout", "--city", city]
    if stage == "enrichment":
        return run + ["gcrm.supervisor.run_enrichment", "--city", city]
    if stage == "opportunity":
        return run + ["gcrm.supervisor.run_opportunity_analysis"]
    if stage == "outreach":
        return run + ["gcrm.supervisor.run_outreach", "--city", city, "--level", str(level)]
    if stage == "followup":
        return run + ["gcrm.supervisor.run_followup"]
    # stage == "all"
    return run + ["gcrm.supervisor.run_gather", "--city", city,
                  "--level", str(level), "--country", country]


def spawn_stage(stage: str, city: str = "", level=None, country: str = "DE") -> None:
    """Validate the request, then launch the stage as a detached background process."""
    validate(stage, city, level)
    subprocess.Popen(
        _command(stage, (city or "").strip(), level, country),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


# An area scan is Gather: research for the area, then enrichment and the people finder on
# exactly the companies it found (run_gather). 'research' alone stays available. The scout
# is not geography-scoped: it judges every candidate, however it was found.
_AREA_STAGES = ("research", "gather")
_MAX_AREA_LEVELS = 6  # bounds Places API calls per run — see design doc's rollout risks


def validate_area(stage: str, area_id, levels: list[int]) -> None:
    """Raise ValueError if the request is invalid for the area stage."""
    if stage not in _AREA_STAGES:
        raise ValueError(f"area stage must be one of {', '.join(_AREA_STAGES)}")
    if not isinstance(area_id, int) or area_id <= 0:
        raise ValueError("area stage requires a valid area_id")
    if not levels or any(level not in SCAN_LEVELS for level in levels):
        raise ValueError(f"area stage requires levels in {sorted(SCAN_LEVELS)}")
    if len(levels) > _MAX_AREA_LEVELS:
        raise ValueError(f"area scans are capped at {_MAX_AREA_LEVELS} levels per run")


def _area_command(stage: str, area_id: int, levels: list[int]) -> list[str]:
    level_arg = ",".join(str(level) for level in levels)
    module = "gcrm.supervisor.run_gather" if stage == "gather" else "gcrm.supervisor.run_research"
    return [sys.executable, "-m", module, "--area-id", str(area_id), "--levels", level_arg]


def spawn_area_stage(stage: str, area_id: int, levels: list[int]) -> None:
    """Validate the request, then launch an area/GPS-radius scan ('gather', or research
    alone) as a detached background process."""
    validate_area(stage, area_id, levels)
    subprocess.Popen(
        _area_command(stage, area_id, levels),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
