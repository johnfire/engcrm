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
        "place.call": "Ich rufe Sie an unter: {phone}",
        "subject.host": "Buchung ({event}): {kind}, {day} – {guest}",
        "body.host": ("{event}: {kind}\n{when}\n{place}\n\n{guest} <{email}>\nFirma: {company}\nThema: {topic}\n\n"
                      "In engcrm: {admin}"),
        "event.held": "wartet auf Bestätigung",
        "event.requested": "Anfrage",
        "event.invite": "neu",
        "event.moved": "verschoben",
        "event.cancelled": "abgesagt",
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
        "place.call": "I will call you on: {phone}",
        "subject.host": "Booking ({event}): {kind}, {day} – {guest}",
        "body.host": ("{event}: {kind}\n{when}\n{place}\n\n{guest} <{email}>\nCompany: {company}\nTopic: {topic}\n\n"
                      "In engcrm: {admin}"),
        "event.held": "waiting for confirmation",
        "event.requested": "request",
        "event.invite": "new",
        "event.moved": "moved",
        "event.cancelled": "cancelled",
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

# Words on the public booking pages.
TEXTS["de"].update({
    "page.title": "Termin buchen", "page.with": "mit {host}",
    "page.pick_type": "Welche Art von Termin passt?", "page.pick_time": "Zeit wählen",
    "page.length": "Dauer", "page.minutes": "{minutes} Min.", "page.show_times": "Zeiten anzeigen",
    "page.earlier": "← Frühere Woche", "page.later": "Spätere Woche →",
    "page.no_times": "In dieser Woche ist nichts frei. Schauen Sie in die nächste Woche.",
    "page.calendar_unavailable": "Gerade kann ich keine freien Zeiten anzeigen. Schreiben Sie mir gern eine E-Mail: {email}",
    "page.times_note": "Zeiten in Berliner Zeit.", "page.local_time": "bei Ihnen",
    "page.back": "Zurück", "page.language": "English",
    "form.name": "Ihr Name", "form.email": "E-Mail", "form.company": "Firma (optional)",
    "form.topic": "Worum geht es?", "form.address": "Adresse für den Besuch", "form.phone": "Telefonnummer",
    "form.submit": "Termin buchen", "form.submit_request": "Anfrage senden",
    "form.privacy": "Ich verwende Ihre Angaben nur für diesen Termin. Details: Datenschutzerklärung.",
    "done.held": "Fast geschafft: Bitte bestätigen Sie den Termin über den Link in der E-Mail an {email}. Der Link gilt 30 Minuten.",
    "done.requested": "Danke! Ihre Anfrage ist eingegangen. Sie bekommen eine E-Mail, sobald ich sie geprüft habe.",
    "done.confirmed": "Ihr Termin steht. Die Kalendereinladung ist unterwegs an {email}.",
    "done.cancelled": "Der Termin ist abgesagt. Ihr Kalender bekommt die Absage per E-Mail.",
    "done.moved": "Der Termin ist verschoben. Die neue Einladung ist unterwegs an {email}.",
    "done.expired": "Dieser Link ist abgelaufen. Bitte buchen Sie den Termin noch einmal.",
    "confirm.title": "Termin bestätigen", "confirm.text": "Klicken Sie auf den Knopf, um Ihren Termin zu bestätigen.",
    "confirm.button": "Ja, Termin bestätigen",
    "manage.title": "Ihr Termin", "manage.cancel": "Termin absagen", "manage.move": "Auf diese Zeit verschieben",
    "manage.move_title": "Neue Zeit wählen", "manage.download": "Einladung (.ics) herunterladen",
    "manage.too_late": "Änderungen sind jetzt nur noch direkt bei mir möglich: {email}",
    "status.held": "wartet auf Bestätigung", "status.requested": "angefragt", "status.confirmed": "bestätigt",
    "status.declined": "abgelehnt", "status.cancelled": "abgesagt",
    "error.title": "Das hat nicht geklappt",
    "error.type_unavailable": "Diese Terminart gibt es hier nicht.",
    "error.length_needed": "Bitte wählen Sie eine Dauer.", "error.name_needed": "Bitte geben Sie Ihren Namen an.",
    "error.email_needed": "Bitte geben Sie eine gültige E-Mail-Adresse an.",
    "error.topic_needed": "Bitte schreiben Sie kurz, worum es geht.",
    "error.address_needed": "Bitte geben Sie die Adresse für den Besuch an.",
    "error.phone_needed": "Bitte geben Sie Ihre Telefonnummer an.",
    "error.too_many_holds": "Für diese E-Mail warten schon zwei Termine auf Bestätigung. Bitte bestätigen Sie diese zuerst.",
    "error.calendar_unavailable": "Gerade kann ich keine freien Zeiten prüfen. Bitte versuchen Sie es später noch einmal.",
    "error.slot_taken": "Diese Zeit ist leider gerade vergeben worden. Bitte wählen Sie eine andere.",
    "error.too_late": "Für Änderungen ist es jetzt zu knapp. Bitte schreiben Sie mir direkt.",
    "error.not_changeable": "Dieser Termin lässt sich nicht mehr ändern.",
    "error.try_again": "Andere Zeit wählen",
})
TEXTS["en"].update({
    "page.title": "Book an appointment", "page.with": "with {host}",
    "page.pick_type": "What kind of appointment suits you?", "page.pick_time": "Pick a time",
    "page.length": "Length", "page.minutes": "{minutes} min", "page.show_times": "Show times",
    "page.earlier": "← Earlier week", "page.later": "Later week →",
    "page.no_times": "Nothing is free this week. Try the next week.",
    "page.calendar_unavailable": "I can't show free times right now. Feel free to email me: {email}",
    "page.times_note": "Times in Berlin time.", "page.local_time": "your time",
    "page.back": "Back", "page.language": "Deutsch",
    "form.name": "Your name", "form.email": "Email", "form.company": "Company (optional)",
    "form.topic": "What is it about?", "form.address": "Address for the visit", "form.phone": "Phone number",
    "form.submit": "Book", "form.submit_request": "Send request",
    "form.privacy": "I use your details only for this appointment. Details: privacy policy.",
    "done.held": "Almost done: please confirm through the link in the email to {email}. The link works for 30 minutes.",
    "done.requested": "Thank you! Your request is in. You will get an email once I have looked at it.",
    "done.confirmed": "Your appointment is booked. The calendar invite is on its way to {email}.",
    "done.cancelled": "The appointment is cancelled. Your calendar gets the cancellation by email.",
    "done.moved": "The appointment has moved. The new invite is on its way to {email}.",
    "done.expired": "This link has expired. Please book the appointment again.",
    "confirm.title": "Confirm your appointment", "confirm.text": "Press the button to confirm your appointment.",
    "confirm.button": "Yes, confirm it",
    "manage.title": "Your appointment", "manage.cancel": "Cancel the appointment", "manage.move": "Move to this time",
    "manage.move_title": "Pick a new time", "manage.download": "Download the invite (.ics)",
    "manage.too_late": "Changes are now only possible by contacting me: {email}",
    "status.held": "waiting for confirmation", "status.requested": "requested", "status.confirmed": "confirmed",
    "status.declined": "declined", "status.cancelled": "cancelled",
    "error.title": "That did not work",
    "error.type_unavailable": "This kind of appointment is not offered here.",
    "error.length_needed": "Please choose a length.", "error.name_needed": "Please give your name.",
    "error.email_needed": "Please give a valid email address.",
    "error.topic_needed": "Please say briefly what it is about.",
    "error.address_needed": "Please give the address for the visit.",
    "error.phone_needed": "Please give your phone number.",
    "error.too_many_holds": "Two appointments for this email are already waiting for confirmation. Please confirm those first.",
    "error.calendar_unavailable": "I can't check free times right now. Please try again later.",
    "error.slot_taken": "Sorry, that time was just taken. Please pick another.",
    "error.too_late": "It is too close to the appointment to change it here. Please contact me directly.",
    "error.not_changeable": "This appointment can no longer be changed.",
    "error.try_again": "Pick another time",
})
