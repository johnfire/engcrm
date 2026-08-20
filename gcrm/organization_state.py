"""The contact state model: where an organization sits in the pipeline, what is
currently going on with it, and which suppression facts are true of it.

These were one `status` column until now, which forced unrelated things to
overwrite each other — a bounced address erased the fact that a meeting was
booked, and an opt-out erased the pipeline position it had taken months to
reach. They are three independent axes and are now stored as three:

  pipeline_stage  where the relationship stands — moves forward, one at a time
  status          what is happening right now — changes often, can go sideways
  flags           facts that stay true regardless of either of the above

Every list the UI, the agents and the docs render comes from here. Six separate
hardcoded status lists had drifted apart before this module existed, and agents
were writing values no list contained.
"""
import logging

logger = logging.getLogger(__name__)

PIPELINE_STAGES = (
    "candidate",        # found by research, not yet evaluated
    "suspect",          # looks like a fit; we have reached out or are about to
    "prospect",         # they engaged — a real conversation exists
    "opportunity",      # concrete deal in motion
    "customer",         # closed; working together
    "not_in_pipeline",  # no fit, declined, or never going anywhere
)

STATUSES = (
    "none",       # nothing is going on right now
    "ready",      # scored a fit, first outreach not yet sent
    "contacted",  # outreach sent, waiting for a reply
    "meeting",    # meeting or discovery call arranged
    "proposal",   # proposal or quote sent, awaiting decision
    "dormant",    # was active, gone quiet past the dormancy threshold
    "on_hold",    # parked on purpose — timing or budget
    "dropped",    # not being pursued
)

SUPPRESSION_FLAGS = (
    "do_not_contact",      # opted out — blocked from all outreach
    "email_bounced",       # address undeliverable, needs verifying
    "research_exhausted",  # research could not find an email or enough detail
)

DEFAULT_STAGE = "candidate"
DEFAULT_STATUS = "none"

# What normally goes with what. Advisory only: it orders and groups the pickers
# and lets the data-quality audit spot oddities. It never rejects a write —
# migration 026 is what happens when the pipeline's own writes get refused.
TYPICAL_STATUSES_BY_STAGE = {
    "candidate":       ("none", "ready"),
    "suspect":         ("ready", "contacted", "dormant", "on_hold"),
    "prospect":        ("contacted", "dormant", "on_hold"),
    "opportunity":     ("meeting", "proposal", "dormant", "on_hold"),
    "customer":        ("none", "dormant", "on_hold"),
    "not_in_pipeline": ("dropped", "none"),
}


def coerce_stage(value: str | None) -> str:
    """Return `value` if it is a known stage, else the default — and say so.

    Callers pass whatever an agent, an import script or an old row supplied.
    An unknown value is a bug worth seeing in the logs, but never a reason to
    lose the row.
    """
    if value in PIPELINE_STAGES:
        return value
    logger.warning("unknown pipeline stage %r — falling back to %r", value, DEFAULT_STAGE)
    return DEFAULT_STAGE


def coerce_status(value: str | None) -> str:
    """Return `value` if it is a known status, else the default — and say so."""
    if value in STATUSES:
        return value
    logger.warning("unknown status %r — falling back to %r", value, DEFAULT_STATUS)
    return DEFAULT_STATUS


def is_typical(stage: str, status: str) -> bool:
    """Whether this stage/status pair is one of the expected combinations.

    False is not an error — a real relationship can sit somewhere unusual. It
    marks a pair worth a human glance in the data-quality audit.
    """
    return status in TYPICAL_STATUSES_BY_STAGE.get(stage, ())
