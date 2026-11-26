"""Escape user text for a SQL LIKE pattern, to be used with ESCAPE '!'."""


def escape_like(text: str) -> str:
    """Take ! % _ literally. Use as: `col LIKE %s ESCAPE '!'` with a value built from this."""
    return text.replace("!", "!!").replace("%", "!%").replace("_", "!_")
