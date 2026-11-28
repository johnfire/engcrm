# Booking (Calendly-style appointments)

Date: 2026-11-28 · Status: approved by Chris on 2026-11-28 ("let's build … then adjust as I get
experience using it"). Defaults marked *(default)* were proposed, not discussed one by one; all of
them are settings, so changing one needs no code change.

## Purpose

People pick a free time from Chris's open hours and book an appointment. Both sides get an email
with a calendar invite that works in Proton Calendar, Google Calendar, Outlook/Microsoft 365 and
Apple Calendar. Chris keeps Proton Calendar as his real calendar and pays nothing extra
(Calendly costs about €10/month).

The bigger need behind it: fewer hand-offs between apps. engcrm becomes the one place where a
booking is made, changed and tied to the organization, person or deal it belongs to.

## Decisions

| Topic | Decision |
| --- | --- |
| Who books | Both: a public page for anyone, and personal links that already know the organization, person or deal. |
| Busy times | engcrm reads Chris's Proton calendar through a "Share with anyone → Limited view" link (busy only, no details; paid Proton plan, which Chris has). |
| Confirmation | Personal links book instantly. The public page holds the slot for 30 minutes and sends a "confirm your booking" link; invites go out only after the click. |
| Types | 15-min call, 45-min video meeting, 60-min on-site visit, and Custom. |
| Custom | The booker picks 30/60/90/120 min and must say what it is about. It is a request: the slot is held, and invites go out only after Chris approves. |
| Video link | One fixed room link from settings, put in every video invite. |
| On-site visit | Any address. A travel buffer before and after (60 min each way *(default)*), on weekdays Chris chooses. Chris cancels a visit that is too far. |
| Cancel / move | Every email carries a private "change or cancel" link, no login, usable until 12 hours before *(default)*; after that it says to contact Chris. |
| Linking to CRM | Personal links link automatically. Public bookers are matched on email to an existing person; otherwise they wait in a "new bookings" list until Chris links them or creates a record. Nothing is created automatically. |
| CRM history | When linked: a `commitment` follow-up dated on the meeting. After the meeting Chris marks it done and it is logged as an activity (phone / video / meeting) with the booked length as minutes. |
| Sender | A new alias on Chris's own mail server (e.g. `termine@christopherrehm.de`), sent through engcrm's existing SMTP login. It is the ORGANIZER of every invite; Chris's Proton address is an ATTENDEE and is never shown publicly. |
| Retention | Unconfirmed holds are deleted after 24 hours. Bookings never linked to a record are erased 6 months after the meeting. Linked bookings follow the person's record. |
| Approach | Built inside engcrm as its own module (approach A). A separate service (B) and a self-hosted scheduler such as Cal.com (C) were considered and rejected as too much extra running cost for one user. |

## Facts checked (2026-11-28, proton.me support pages)

- "Share with anyone" offers Limited view (busy only) and Full view; it needs a paid plan and the
  web app. The link URL contains the decryption key, so engcrm stores it as a secret.
- Changes can take **up to 8 hours** to reach link viewers. Bookings made through engcrm are never
  affected (engcrm knows them itself); events Chris types into Proton may show late. Hence the
  minimum notice and the "block this time" button below.
- Proton auto-adds invitations to the calendar by default, so a booking invite lands in Proton
  without a click.

## Section 1 — Parts and availability

**Module** `gcrm/booking/`: pure functions compute slots and build `.ics` text (no database, no
network); thin adapters fetch the Proton feed, read and write the database, and send mail. The
public router calls booking functions only; it never reads or writes organizations or people.

**Tables** (all carry `workspace_id`):

- `booking_settings` — enabled switch (**off by default**), public slug (`/book/<slug>`), Proton
  feed URL (secret), organizer alias, Chris's attendee address, minimum notice 24 h *(default)*,
  horizon 6 weeks *(default)*, gap between meetings 15 min *(default)*, video room link, cancel
  cut-off 12 h *(default)*.
- `booking_types` — name, minutes, kind (`phone`, `video`, `visit`, `custom`), travel buffer,
  allowed weekdays, needs approval.
- `availability_rules` — weekly open hours. Start: Mon–Fri 09:30–12:00 and 13:30–16:30
  *(Chris's rough hours, to be tuned)*.
- `booking_blocks` — "block this time" entries Chris adds for the Proton lag.
- `bookings` — type, start/end (UTC), name, email, company, topic or address, language, status,
  `ics_uid`, `sequence`, hashed manage and confirm tokens, linked organization/person/deal.
- `booking_links` — personal links: hashed token, the types they offer, the organization/person/deal
  they belong to.

**Free slots = open hours − (Proton busy ∪ engcrm bookings ∪ blocks)**, each busy span widened by
the gap (and by the travel buffer for visits), then limited by minimum notice and horizon.
Slots start every 15 minutes. The feed is cached for 5 minutes. Repeating events in the feed
(`RRULE`) are expanded with the `icalendar` and `recurring-ical-events` libraries.

**Fails closed:** if the feed cannot be read and the last good copy is older than 1 hour, the page
offers no times and says "please email". The rest of engcrm is unaffected.

**No double-booking:** active bookings (held, requested, confirmed) carry a Postgres exclusion
constraint on their time range (including buffers). Two people clicking the same slot: one gets
"just taken, pick another time".

## Section 2 — Flows, mail and invites

**Statuses:** `held` (public, waiting for the confirm click) → `confirmed`; `requested` (custom,
waiting for Chris) → `confirmed` or `declined`; any active booking → `cancelled`.

1. **Book.** The booker picks a type, a day and a time, then types name, email, company (optional),
   and the topic (custom) or address (visit). Personal link → `confirmed` at once. Public page →
   `held`, plus a confirm email. Custom → `requested`, plus a "we got your request" email.
2. **Confirm.** The click within 30 minutes makes it `confirmed`; after that the hold is gone and
   the link says so.
3. **Invite.** On `confirmed`, one email to the booker and one to Chris, each with a
   `METHOD:REQUEST` `.ics` attached: ORGANIZER = alias, ATTENDEES = booker and Chris, times in UTC
   (`…Z`), a stable `UID`, `SEQUENCE` 0, location = room link or the visit address. The email text
   also has the time in words (Berlin time) and the manage link.
4. **Move.** From the manage link (or by Chris in engcrm): pick a new free slot. Same `UID`,
   `SEQUENCE + 1`, sent to both. Calendars move the event in place.
5. **Cancel.** `METHOD:CANCEL`, same `UID`, `SEQUENCE + 1`, sent to both. The slot frees up.

No "Add to Google / Outlook" web links in the email: the attached invite already offers
accept/decline in all four apps and updates itself; a web-link copy would not follow a move.
The confirmation page offers a `.ics` download with the same `UID` instead.

**Time zones:** stored in UTC; the page shows Berlin time and, when the booker's browser is in
another zone, their local time next to it. The `.ics` uses UTC, so each app shows local time.

**Language:** German or English, from the browser, with a switch; emails go in the booker's
language. Chris's copy is in his workspace language.

**Mail path:** `gcrm/tools/email.py` gains a sender for a text body plus a `text/calendar`
attachment. It honours `EMAIL_ENABLED` and the booking switch, and files a copy in Sent like
`send_email`.

## Section 3 — CRM, privacy, safety, testing

**Linking.** Personal link → linked at once. Public → exact email match against people in the
workspace (one match only; several matches go to review). Unmatched → "new bookings" list, where
Chris links to an existing organization/person/deal or creates a person (and organization) in one
step. Linking creates the `commitment` follow-up (`source_kind = 'booking'`). Marking it done logs
the activity. Cancelling a linked booking dismisses its follow-up.

**Privacy (GDPR).** Legal basis: steps at the person's request before a contract, Art. 6(1)(b).
The privacy page gains a booking section (what is stored, why, how long, who receives the invite).
Only the fields needed are asked for. No third-party scripts, fonts or cookies on the public pages.
Retention clean-up runs whenever the bookings list or a public page loads (idempotent, no
scheduler needed) and is audit-logged.

**Abuse.** The confirm step means nobody can make the server email a stranger more than once per
hold. Per-IP and per-email rate limits on booking (reusing `FixedWindowRateLimiter`), at most 2
open holds per email address, a hidden honeypot field, and tokens are random 32-byte values stored
only as hashes.

**Audit.** Every state change (booked, confirmed, approved, declined, moved, cancelled, linked,
purged) goes to the existing audit log with the actor: `public_booker`, `chris` or `system`.

**Errors.** Each step stands alone: if sending the invite fails, the booking stays `confirmed`,
the failure is logged and shown in Chris's list with a "send again" button. If the feed fails, only
the public slots close.

**Testing.**
- Unit: slot maths (hours, buffers, notice, horizon, overlap, daylight-saving days), `.ics`
  building (fields, line folding, escaping, CANCEL/SEQUENCE), feed parsing including repeating
  events.
- Integration on real Postgres: the migration, the exclusion constraint under concurrent booking,
  hold expiry, retention purge, linking and follow-up creation.
- Web: the public flow (book → confirm → move → cancel) through FastAPI's test client with mail
  captured, plus the owner pages.
- Manual once, before turning it on: one real invite to each of Proton, Google, Outlook and Apple,
  checking add, move and cancel.

## Build order

1. Core: slot maths, feed parsing, `.ics` building (pure, unit-tested).
2. Migration and the booking database layer.
3. Invite mail with the `.ics` attached.
4. Public pages: book, confirm, manage.
5. Owner side: settings, open hours, types, blocks, bookings list, linking, approval of requests.
6. Privacy page text; then Chris turns the switch on after the manual four-calendar check.

## Not included (for now)

Reminder emails (calendar apps remind on their own), payments, multiple hosts, round-robin,
group bookings, SMS.
