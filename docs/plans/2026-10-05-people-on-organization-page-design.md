# People you know at an organization, and the stage picker on the list

Date: 2026-10-05 · Status: built

## Why

The goal is to make it quick to contact someone you know at a company, so you can
meet for coffee and see whether a business relationship comes of it. Open the
organization, see who you know there, click through to what you know about them,
then message them on LinkedIn or email them.

## What it was

The organization page had a "who do I know here" box that listed LinkedIn
connections only. Anyone met in person (business card) or typed in by hand was linked
to the organization but never shown. On the phone, tapping a name opened LinkedIn, so
there was no way to reach the person's record from there.

## What it is now

**People you know here** (web and app) lists everyone linked to the organization,
whatever their source:

- Order: met in person (`card_capture`) first, then added by hand (`manual`), then
  the rest (LinkedIn, research), then by name.
- Each row shows the name (linking to the person record), title, pipeline stage, a
  source tag, a LinkedIn mark, and where you met them. Below that are **LinkedIn ↗**,
  which opens the profile with LinkedIn's Message button (LinkedIn has no link that
  opens a message directly), and **✉ email** when we have an address.
- Unconfirmed LinkedIn lookalikes (people whose company name only *looks* like this
  organization's) stay under their own labelled heading.
- One query (`get_known_people_for_org`) serves both the web page and the app API. The
  API key keeps its old name, `linkedin_connections`, so installed app builds keep
  working. If the lookup fails, the page loads without the box.

**Stage picker on the Organizations list**: the stage badge is now a dropdown.
Choosing a stage saves it straight away (`POST /organizations/{id}/stage`) and returns
you to the same filtered page. Only the stage changes: the status stays, as it would in
the edit form. An unknown stage is refused, and every change is audit-logged.

## Left out on purpose

- A "main contact" per organization, and using it in outreach drafts. Neither is
  needed to see who you know and get in touch.
- Widening the list's "in N" badge to count every known person. It still counts only
  LinkedIn connections.
