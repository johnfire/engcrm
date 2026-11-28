"""Words for the booking pages and emails, German and English.

Kept apart from gcrm/i18n while that file is being edited elsewhere; each entry is a
str.format() template. Dates are written 08.12.2026 in both languages (gcrm/dates.py).
"""
from datetime import datetime
from zoneinfo import ZoneInfo

LANGUAGES = ("de", "en")

WEEKDAYS = {
    "de": ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"),
    "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
}

TEXTS = {
    "de": {
        "kind.call": "Telefonat (15 Min.)",
        "kind.video": "Videogespräch (45 Min.)",
        "kind.visit": "Besuch vor Ort (60 Min.)",
        "kind.custom": "Eigener Termin (auf Anfrage)",
        "summary": "{kind}: {guest} / {host}",
        "when": "{weekday}, {day}, {start}–{end} Uhr (Berlin)",
        "subject.confirm": "Bitte bestätigen Sie Ihren Termin am {day}",
        "body.confirm": ("Guten Tag {guest},\n\nbitte bestätigen Sie Ihren Termin innerhalb von 30 Minuten:\n{link}\n\n"
                         "Termin: {kind}\n{when}\n\nWenn Sie nichts gebucht haben, ignorieren Sie diese E-Mail einfach; "
                         "dann wird nichts gespeichert.\n\n{host}"),
        "subject.requested": "Ihre Terminanfrage für den {day}",
        "body.requested": ("Guten Tag {guest},\n\nvielen Dank für Ihre Anfrage. Ich melde mich mit einer Zusage, "
                           "sobald ich sie geprüft habe.\n\nAnfrage: {kind}\n{when}\nThema: {topic}\n\n"
                           "Anfrage ändern oder zurückziehen: {manage}\n\n{host}"),
        "subject.invite": "Termin bestätigt: {kind}, {day}",
        "body.invite": ("Guten Tag {guest},\n\nIhr Termin steht. Die Kalendereinladung ist angehängt.\n\n"
                        "{kind}\n{when}\n{place}\n\nTermin verschieben oder absagen: {manage}\n\n{host}"),
        "subject.moved": "Termin verschoben: {kind}, {day}",
        "body.moved": ("Guten Tag {guest},\n\nIhr Termin wurde verschoben. Die neue Kalendereinladung ist angehängt.\n\n"
                       "{kind}\n{when}\n{place}\n\nTermin verschieben oder absagen: {manage}\n\n{host}"),
        "subject.cancelled": "Termin abgesagt: {kind}, {day}",
        "body.cancelled": ("Guten Tag {guest},\n\nder Termin am {when} ist abgesagt. Ihr Kalender entfernt ihn "
                           "mit der angehängten Absage.\n\n{host}"),
        "subject.declined": "Ihre Terminanfrage für den {day}",
        "body.declined": ("Guten Tag {guest},\n\nleider kann ich den angefragten Termin ({when}) nicht wahrnehmen. "
                          "Gern können Sie einen anderen Zeitpunkt wählen.\n\n{host}"),
        "place.video": "Link zum Gespräch: {room}",
        "place.visit": "Ort: {address}",
        "place.call": "Ich rufe Sie unter der angegebenen Nummer an oder Sie erreichen mich wie vereinbart.",
    },
    "en": {
        "kind.call": "Phone call (15 min)",
        "kind.video": "Video meeting (45 min)",
        "kind.visit": "On-site visit (60 min)",
        "kind.custom": "Custom appointment (on request)",
        "summary": "{kind}: {guest} / {host}",
        "when": "{weekday}, {day}, {start}–{end} (Berlin time)",
        "subject.confirm": "Please confirm your appointment on {day}",
        "body.confirm": ("Hello {guest},\n\nplease confirm your appointment within 30 minutes:\n{link}\n\n"
                         "Appointment: {kind}\n{when}\n\nIf you did not book anything, just ignore this email; "
                         "nothing will be kept.\n\n{host}"),
        "subject.requested": "Your appointment request for {day}",
        "body.requested": ("Hello {guest},\n\nthank you for your request. I will confirm as soon as I have "
                           "looked at it.\n\nRequest: {kind}\n{when}\nTopic: {topic}\n\n"
                           "Change or withdraw the request: {manage}\n\n{host}"),
        "subject.invite": "Appointment confirmed: {kind}, {day}",
        "body.invite": ("Hello {guest},\n\nyour appointment is booked. The calendar invite is attached.\n\n"
                        "{kind}\n{when}\n{place}\n\nMove or cancel: {manage}\n\n{host}"),
        "subject.moved": "Appointment moved: {kind}, {day}",
        "body.moved": ("Hello {guest},\n\nyour appointment has moved. The new calendar invite is attached.\n\n"
                       "{kind}\n{when}\n{place}\n\nMove or cancel: {manage}\n\n{host}"),
        "subject.cancelled": "Appointment cancelled: {kind}, {day}",
        "body.cancelled": ("Hello {guest},\n\nthe appointment on {when} is cancelled. The attached cancellation "
                           "removes it from your calendar.\n\n{host}"),
        "subject.declined": "Your appointment request for {day}",
        "body.declined": ("Hello {guest},\n\nunfortunately I cannot make the requested time ({when}). "
                          "You are welcome to pick another time.\n\n{host}"),
        "place.video": "Meeting link: {room}",
        "place.visit": "Place: {address}",
        "place.call": "I will call you, or reach me as agreed.",
    },
}


def text(language: str, key: str, **values) -> str:
    words = TEXTS[language if language in LANGUAGES else "de"][key]
    return words.format(**values)


def describe_time(language: str, starts_at: datetime, ends_at: datetime, zone: ZoneInfo) -> str:
    start, end = starts_at.astimezone(zone), ends_at.astimezone(zone)
    lang = language if language in LANGUAGES else "de"
    return text(lang, "when", weekday=WEEKDAYS[lang][start.weekday()], day=start.strftime("%d.%m.%Y"),
                start=start.strftime("%H:%M"), end=end.strftime("%H:%M"))
