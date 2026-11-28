"""What a guest sees on the booking pages, shared by the public pages and Chris's preview of them.

The public pages live under /book/<slug>; the preview lives under /bookings/preview (signed in),
so every link in the guest templates starts from `base_path` instead of a fixed /book/ URL.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import Request
from fastapi.responses import HTMLResponse

from gcrm.api.templates import templates
from gcrm.booking import booking_service as service
from gcrm.booking.availability import available_starts
from gcrm.booking.booking_texts import LANGUAGES, text, weekday_name

DAYS_PER_PAGE = 7
PREVIEW_PATH = "/bookings/preview"


def guest_language(request: Request) -> str:
    chosen = request.query_params.get("lang") or request.session.get("ui_language")
    if chosen in LANGUAGES:
        return chosen
    accepted = request.headers.get("accept-language", "").lower()
    return "en" if accepted.startswith("en") else "de"


def render_guest_page(request: Request, template: str, page: service.BookingPage, language: str, *,
                      base_path: str, preview: bool = False, **values) -> HTMLResponse:
    def words(key: str, **extra) -> str:
        return text(language, key, **extra)

    context = {"request": request, "page": page, "lang": language, "bt": words, "base_path": base_path,
               "preview": preview, **values}
    return templates.TemplateResponse(template, context, status_code=values.get("status_code", 200))


def _days_with_starts(starts: list[datetime], zone: ZoneInfo, first: date, language: str) -> list[dict]:
    days = {first + timedelta(days=offset): [] for offset in range(DAYS_PER_PAGE)}
    for start in starts:
        local = start.astimezone(zone)
        if local.date() in days:
            days[local.date()].append({"value": start.isoformat(), "label": local.strftime("%H:%M")})
    return [{"label": f"{weekday_name(language, day.weekday())}, {day.strftime('%d.%m.%Y')}", "starts": starts_of_day}
            for day, starts_of_day in days.items() if starts_of_day]


def slot_view(page: service.BookingPage, booking_type: dict, week: int, minutes: int | None, language: str,
              except_booking_id: int | None = None) -> dict:
    now = service.utc_now()
    starts = available_starts(booking_type, page.settings, now, minutes=minutes, except_booking_id=except_booking_id)
    first = now.astimezone(page.zone).date() + timedelta(days=DAYS_PER_PAGE * week)
    weeks = max(1, -(-page.settings["horizon_days"] // DAYS_PER_PAGE))
    return {"calendar_unavailable": starts is None, "week": week, "weeks": weeks,
            "days": _days_with_starts(starts or [], page.zone, first, language)}
