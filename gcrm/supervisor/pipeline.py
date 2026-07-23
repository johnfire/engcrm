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

# Stages exposed as buttons. 'all' runs the city pipeline in sequence.
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
    return run + ["gcrm.supervisor.run_pipeline", "--city", city,
                  "--level", str(level), "--country", country]


def spawn_stage(stage: str, city: str = "", level=None, country: str = "DE") -> None:
    """Validate the request, then launch the stage as a detached background process."""
    validate(stage, city, level)
    subprocess.Popen(
        _command(stage, (city or "").strip(), level, country),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
