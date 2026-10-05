"""What kind of work an activity was, and how long it counts for.

Organization activities (`interactions.method`) and person activities
(`people_interactions.method`) grew separate vocabularies ("in_person" vs "visit",
"phone" vs "call"). Statistics need one: this maps both onto the activity types,
in one place. See docs/plans/2026-10-05-statistics-design.md.
"""

ACTIVITY_TYPES = ("drop_in", "meeting", "phone", "video", "email", "note")

# Minutes an activity counts for when no duration was typed. Each workspace can
# change these in Settings (activity_minute_defaults); these are the fallback.
DEFAULT_MINUTES = {"drop_in": 15, "meeting": 45, "phone": 15, "video": 30, "email": 10, "note": 0}

# Stored method value -> activity type. Anything else (other, none) is a plain note.
_METHOD_TYPES = {
    "in_person": "drop_in", "visit": "drop_in",
    "meeting": "meeting",
    "phone": "phone", "call": "phone",
    "video": "video",
    "email": "email",
}

# Log entries that record a plan, not work done.
NOT_ACTIVITIES = ("next_step", "next_step_done")

# Methods each form may store. Organizations and people keep their own words for
# the older types; the new ones are shared.
ORGANIZATION_METHODS = ("in_person", "meeting", "phone", "video", "email", "other")
PERSON_METHODS = ("visit", "meeting", "call", "video", "email", "other")


def activity_type(method: str | None) -> str:
    return _METHOD_TYPES.get((method or "").strip(), "note")


def type_case_sql(column: str) -> str:
    """The same mapping as activity_type(), as a SQL CASE over `column`. Built from
    the constants above only, never from input."""
    whens = " ".join(f"WHEN '{method}' THEN '{kind}'" for method, kind in _METHOD_TYPES.items())
    return f"(CASE {column} {whens} ELSE 'note' END)"


def parse_minutes(value) -> int | None:
    """A typed duration: a whole number of minutes from 0 to 24 h, or None when blank.
    Raises ValueError for anything else."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    minutes = int(value)
    if not 0 <= minutes <= 24 * 60:
        raise ValueError("duration must be between 0 and 1440 minutes")
    return minutes
