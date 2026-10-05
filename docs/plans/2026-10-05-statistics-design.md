# Statistics: effort in, euros out

Date: 2026-10-05 · Status: building

## Why

The goal is to track progress, and in the end to answer one question: **how much work, over
what period, did it take to make X euros?** To answer it, the CRM has to know three things:
what was done (activities and the time they took), what moved (stage changes), and what was
won (sales in €).

## What gets recorded

**Sales.** A `sales` table holds an organization, an amount in €, the date won and a short
"what". An organization can have several sales. They're entered on the web organization page
(Record a sale) and soft-deleted.

**Activity types and time.** Every activity (organization `interactions`, person
`people_interactions`) gets an optional `duration_minutes`. When it's blank, the type's
default counts instead. The page labels those hours "estimated".

| Type | Stored as (organization / person) | Default |
|---|---|---|
| Drop-in, first contact at their office | `in_person` / `visit` | 15 min |
| Sit-down meeting | `meeting` / `meeting` | 45 min |
| Phone call | `phone` / `call` | 15 min |
| Video call | `video` / `video` | 30 min |
| Email (sent) | `email` / `email` | 10 min |
| Plain note | anything else / none | 0 min |

The stored values keep their existing vocabulary, and `gcrm/activity_types.py` maps them to
types in one place. Existing "in person" entries count as drop-ins. Inbound messages
(replies) are not counted as work, and next-step log entries are not activities. The defaults
are per workspace in `activity_minute_defaults` and can be edited in Settings. The code
carries the same values as a fallback.

**Stage history.** Triggers on `contacts.pipeline_stage` and `people.pipeline_stage` write
every change (from → to, when) to `stage_changes`, whichever screen or agent makes it.
Promotions are counted from the day the triggers go live, because there's no reliable record
before that.

## The Statistics page (web, `/statistics`)

You pick a period (week, month, quarter, year, or from–to), and each figure is shown next to
the previous period of the same length.

1. **Effort:** the count per type, hours (estimated where defaults were used), and bars per
   week.
2. **New contacts:** organizations and people added, by source.
3. **Pipeline:** organizations and people per stage now, stage changes in the period
   (from → to, forward vs. dropped), and stuck records (a working stage with nothing logged
   for 4 weeks).
4. **Money:** € won, the number of sales, € per hour. Each sale is shown with its
   organization, €, date, weeks from first contact to the sale, and the activities and hours
   spent on the organization and its linked people since the previous sale to that
   organization (or since first contact).

## Left out on purpose

Statistics on the phone, goals and targets, importing from accounting, and charts beyond
simple bars.
