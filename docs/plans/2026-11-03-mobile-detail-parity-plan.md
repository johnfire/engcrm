# Phone app: bring the person and organization screens up to the web

Date: 03.11.2026. Status: plan, not started.

Compared files: `gcrm/ui/templates/person_detail.html`, `organization_detail.html` and their
partials, against `engcrm-mobile/app/(drawer)/person-detail.tsx`, `organization-detail.tsx`,
`log-meeting.tsx`, `edit-*.tsx` and their components.

## What is different

### Both screens
| # | Web | Phone | Server API for the phone |
|---|-----|-------|--------------------------|
| B1 | **Short-term / long-term value** rating rows (High/Medium/Low/Zero), on both screens | missing entirely | exists: `PUT /api/{organizations,people}/{id}/value/{short-term,long-term}`; the GET payloads already carry `short_term_value` / `long_term_value` |
| B2 | Priority and value buttons are **coloured** (green/yellow/blue/orange/gray/dark) | all the same purple | n/a (copy `priority_tone` / `value_tone` from `gcrm/api/templates.py`) |
| B3 | Order at the top: known people → priority → value → deals → details | deals first, then priority (org); ratings and deals mixed with links (person) | n/a |

### Organization screen
| # | Web | Phone | API |
|---|-----|-------|-----|
| O1 | Priority has **6 levels**, incl. "6 Forget it" | only 1–5. An org set to 6 on the web shows *nothing selected* on the phone — **a real bug** | server already accepts 1–6 |
| O2 | Venue notes: best time to visit, access/logistics, space notes, price sensitivity | not shown, not editable | PATCH `/api/organizations/{id}` doesn't accept them → **add** |
| O3 | Fit score and all suppression flags editable | flags only shown as badges; fit score read-only | PATCH accepts `do_not_contact` only → **add the rest** |
| O4 | Log activity: **date (backdate)**, materials left, follow-up promised, + "last visited / first & last impression / last read" summary | none of these | `occurred_on`, `materials_left` already accepted; `followup_promised` and the summary need adding |
| O5 | History shows translated type, **minutes, offer, attitude, my read, materials left** | raw method string (`in_person`), none of the rest | GET returns only the old columns → **add** them to the query |
| O6 | **Sales** card: list one-off sales, record a sale against a deal, delete | can't record or delete a one-off sale | `POST /api/deals/{id}/sales` exists; list + delete need adding |
| O7 | Distance (km) in the header; pre-visit brief link | missing | distance is in the payload; brief is web-only (link out) |

### Person screen
| # | Web | Phone | API |
|---|-----|-------|-----|
| P1 | Note history shows **minutes, offer, attitude, my read** | method and text only | the API already returns them; the phone's `PersonInteraction` type ignores them |
| P2 | The inline note form has offer, minutes and the two judgments | the phone's inline note box (`PersonNotesLog`) has method only — so there are two different ways to log on the phone, one complete (Log activity), one not | — |
| P3 | Company name links to the organization; link / unlink organization | plain text, no link/unlink | link/unlink → **add** JSON endpoints |
| P4 | LinkedIn badge, *connected on*, *company on LinkedIn*, job-change notice, added date, distance | missing | in the payload (verify job-change field) |
| P5 | Editable *LinkedIn connection* and *retention hold* checkboxes | missing | PATCH `/api/people/{id}` → **add** both |
| P6 | Curiosity-email draft button | missing | no JSON endpoint |

## Plan — one commit per step, each pushed and checked live

1. **Shared rating pieces (B1, B2, O1).** Add the 6th priority level, tone colours, and a
   `ValueRatings` component (ST + LT rows) used on both screens. Phone-only; the API is there.
   Fixes the real bug first.
2. **Screen order (B3, O7, P4).** Reorder both screens to match the web top-to-bottom; add
   distance, LinkedIn details, added date, tappable company link. *Done 03.11.2026.* The
   brief link was left out: the web brief needs a browser login, and once steps 4–5 are done
   the phone screen itself shows everything the brief does.
3. **History rows (O5, P1).** *Done 03.11.2026.* Server: add the missing columns to the organization GET.
   Phone: one `ActivityEntry` row component showing type · minutes · offer, note, judgments,
   materials left — used by both screens.
4. **One way to log (P2, O4).** *Done 03.11.2026* — the organization screen's inline note box went too (same decision). No `followup_promised` server field was needed: the web stores the promise as the follow-up text, which the phone API already took. Server: accept `followup_promised`, return the visit summary.
   Phone: add date, materials left, follow-up promised to Log activity; show the summary.
   *Decision for you below.*
5. **Edit forms (O2, O3, P5).** Server: widen both PATCH bodies. Phone: add the fields to
   `recordFields.ts` (venue notes, fit score, flags; LinkedIn + retention checkboxes).
   `tests/test_mobile_record_fields.py` keeps the limits honest.
6. **Sales (O6).** Server: list + delete endpoints. Phone: Sales block on the organization screen.
7. **Link / unlink a person's organization (P3).** Server endpoints + a picker on the phone.
8. *(Optional)* Curiosity email (P6) — only if you use it from the phone.

Each step: jest + pytest green, CI green, new EAS build installed, checked on the phone.

## Decisions
- **P2 (decided 03.11.2026):** one form. The person screen's inline note box goes; Log activity
  is the only way to log on the phone, and the person screen keeps the history list.
- **Step 8:** curiosity email on the phone — still open.
