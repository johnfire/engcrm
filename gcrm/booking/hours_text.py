"""Open hours as Chris types them for one day: "09:30-12:00, 13:30-16:30". Empty = closed."""
import re
from datetime import time

_WINDOW = re.compile(r"^\s*(\d{1,2})[:.](\d{2})\s*[-–]\s*(\d{1,2})[:.](\d{2})\s*$")


def _clock(hours: str, minutes: str) -> time:
    return time(int(hours), int(minutes))


def parse_day_hours(typed: str) -> list[tuple[time, time]]:
    """Windows in time order. Raises ValueError for a malformed, empty or overlapping window."""
    windows = []
    for part in filter(None, (piece.strip() for piece in typed.split(","))):
        match = _WINDOW.match(part)
        if not match:
            raise ValueError(f"not a time window: {part!r}")
        opens, closes = _clock(*match.group(1, 2)), _clock(*match.group(3, 4))
        if closes <= opens:
            raise ValueError(f"ends before it starts: {part!r}")
        windows.append((opens, closes))
    windows.sort()
    if any(earlier[1] > later[0] for earlier, later in zip(windows, windows[1:])):
        raise ValueError("windows overlap")
    return windows


def format_day_hours(windows: list[tuple[time, time]]) -> str:
    return ", ".join(f"{opens:%H:%M}-{closes:%H:%M}" for opens, closes in windows)
