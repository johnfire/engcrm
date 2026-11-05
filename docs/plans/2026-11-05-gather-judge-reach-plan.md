# Gather, Judge, Reach — three separate runs for door-to-door and LinkedIn

Date: 2026-11-05. Status: approved by Chris 2026-11-05 (decisions below), building.

## Why

engcrm was built to find places to hang paintings, then drafted emails to them. First
contact for AI consulting is now **door-to-door** and **LinkedIn voice messages**, with
little or no cold email. The steps that find information, the steps that make judgment
calls, and the step that writes emails should be separate runs, started when Chris
wants them, not one long chain.

## How Chris works (the human side)

**On foot.** Chris walks an industrial area street by street and stops at every
business on the list — no stone unturned, because you never know until you get there.
At the door: "Hi, my name is Christopher Rehm, I'm an AI consulting engineer. I'd like
to leave a flyer and a brochure, and if possible I'd like to know who is responsible
for AI and digitalisation here." Whether the company looks like a close fit does not
matter on the street — only they can decide whether they need the services. Knowing a
little about the company helps; a long brief is not needed.

**On LinkedIn.** Chris works down a list (newest first, or starting part-way down) and
sends voice messages through LinkedIn's direct messages. He records them himself; the
system does not draft them. What matters afterwards is one thing: did a message lead to
a meeting.

What this means for the system:

- **Every gathered company is a walking stop**, fit or not. The Maps list and the
  walking order come straight after Gather; Judge is not needed for a walking day.
- **Judge is for LinkedIn and for deciding where to spend extra effort**, not a gate in
  front of the door.
- **At the door, three facts are worth having**: the name, one line on what they make,
  and the name of the person to ask for if the people finder found one.
- **After the door, the facts to log** are: dropped in, flyer and brochure left, and
  the name and role of whoever handles AI/digitalisation (a new person on the company).
  The field connector already takes all of this by voice.

## How it will work

### Run 1 — Gather ("scan an area")

Started by the area scan or "Run all" button (or by Claude on request). For the area and
levels chosen:

1. **Research** finds the companies and saves them as candidates (as today: shops never
   saved).
2. **Enrichment** fills in website, email, phone and the company's LinkedIn/XING pages,
   for **the companies this run just found** (today it works through every contact
   missing an email, anywhere).
3. **People finder** finds up to three decision-makers per company and their public
   LinkedIn/XING profiles (or "no public profile found"), again for **this run's
   companies**. It moves here from after the scout, so it no longer waits for "ready".
4. **Pin to Google Maps:** every new company goes onto the "Cold call candidates" list.
   This step runs **from Chris's computer**, not the server: Google has no API for
   personal lists, so pins are saved through the browser in his own Google account (the
   method from 2026-11-03/04). After a Gather finishes, Chris says "pin the new ones"
   and Claude does it in the built-in browser and records each pin in the CRM. The
   server keeps a "waiting to be pinned" list so nothing is missed.
5. **Walking list:** the area's companies in walking order (each stop next to the
   last), with the three door facts per stop, readable on the phone. Built from the
   coordinates Gather and pinning already provide.

Result: an area full of companies on the phone map and in walking order, with named
people and profile links. No judgment has been made yet.

### Run 2 — Judge (when Chris wants it)

1. **Scout** rates each candidate: ready, unsure (stays candidate), or dropped (as
   built on 2026-11-04: size rule in code, shops dropped, hand-entered contacts left
   alone). Dropping does **not** delete anything and does not take a company off the
   map or the walking list.
2. **Opportunity** analyses **only the ready companies** (today it analyses any contact
   without an analysis, including dropped ones): services that fit, a first project,
   discovery questions.
3. A short **"dropped but still on your map"** list is shown after the run, for
   information. Pins stay unless Chris asks for some to be removed.

### Run 3 — Outreach (rarely)

Unchanged: drafts emails into the approval queue for ready companies. Nothing sends
without approval. Expected to be used rarely.

### Follow-up

Stays switched off.

### LinkedIn: message → meeting

No message drafting. Two facts are tracked:

- **"I sent a LinkedIn message"** to a person: a new activity type **LinkedIn message**,
  on the person (and so on their company), from the web, the phone and the field
  connector ("I sent Max Beispiel at Faist a voice message").
- **"I got a meeting out of it"**: logged as a **meeting** activity with its date, and
  the company's deal moves to **prospect** (a real conversation exists).

Statistics gain one line: LinkedIn messages sent → meetings that followed.

The People page gets a **"to message on LinkedIn"** view: people with a public LinkedIn
profile and no LinkedIn message yet, newest first — the list Chris works down.

### What Chris sees on an organization

The company's LinkedIn/XING page and its decision-makers with their profile links, or
"no public profile found".

## How we build it

One commit per step, each test-first, with the full CI steps before every push. Each step
is useful on its own.

1. **Gather run.** A new `run_gather` (city or area + levels): research → enrichment →
   people finder, where enrichment and the people finder take the ids research just
   saved. The area scan and "Run all" buttons start it. A failing step does not stop
   the steps after it from working on what was found. Tests: the order, the id
   scoping, one step failing.
2. **People finder moves.** It works on the companies it is given (Gather's new ids),
   not "ready" ones; it is removed from after the scout. Tests updated to the new rule.
3. **Judge run.** A new `run_judge`: scout → opportunity, opportunity limited to ready
   companies, then the "dropped but still on your map" list. A button next to Gather.
   Tests: opportunity skips dropped and candidate companies.
4. **Retire the old chains.** The supervisor graph (all six steps) and `run_pipeline`
   (research → scout → enrichment) are replaced by the three runs. Outreach keeps its
   own button. Nothing runs on a schedule (decision 3): a read-only check of the
   server's crontab first, and any job running the old supervisor is removed (with
   Chris's OK, logged in the agent diary).
5. **Pin queue + pin method in the repo.** A "waiting to be pinned" list (gathered,
   has coordinates, not pinned, not excluded) and the browser pin method moved from an
   old session's scratch folder into the repo, so it survives. Pinning stays a step
   Claude runs in the browser on request. Verified with one real area.
6. **Walking list.** Per area: companies in walking order with name, one line on what
   they make, and the person to ask for. Phone-readable. Checked on a real area.
7. **LinkedIn message activity.** New activity type on web, phone and field connector;
   "got a meeting" path (meeting activity + deal to prospect); statistics line; "to
   message on LinkedIn" view. Real Postgres integration tests.
8. **Organization page.** Company pages and decision-makers with profile links or "no
   public profile found". Checked rendered, without login, as before.
9. **Docs.** AGENTS.md rewritten around the three runs; GDPR record row 17 updated
   (people are now found before judging).

The phone app shows the run buttons it is sent, so new buttons need a phone app build
to appear there; the web gets them immediately.

## Decisions (Chris, 2026-11-05)

1. **People at dropped companies: keep for now.** Nothing is deleted. Chris will use the
   flow first; the idea is parked in issue johnfire/engcrm#111.
2. **Pins:** pin right after Gather; after Judge, show "dropped but still on your map".
   Pins stay.
3. **Scheduled runs: none.** Chris starts every run himself.
4. **Push first:** yesterday's three commits pushed before building (4df7d86).

## Idea, not planned: different flags on the map

Google Maps does not offer custom pin colours on a personal list, but each saved list has
its own icon, so a status can be shown by list — e.g. "Cold call candidates" (not yet
visited) and a second list for "visited". Moving a company between lists would be the same
browser step as pinning. To check in the Maps app before building anything.
