# Payment schedules, then the forecast (decided 2026-11-07)

**Why.** The owner needs to see what money is coming in and *when*, to plan which customers to
target next. Accounting stays in the billing records; this is a pipeline and forecast tool.
Some contracts (e.g. adult-education courses) are paid monthly, so one amount on one date is
not enough.

## Step 1 — payment schedules (built)
A contract paid over N months (2 to 60) is **N sale rows**, one per payment, tied by a
`series_id` (`series_part` of `series_total`). Each payment has its own due day
(`expected_on`), amount and status, so marking February received leaves March expected, and
every existing feature (statuses, statistics, revenue columns, backup) works on payments.
- The total is split in whole cents; the last payment takes the remainder. Due days keep the
  day of month, clipped in short months (31 Jan → 28 Feb).
- A schedule starts as expected, booked or contracted (never collected): each payment is
  marked received as it arrives. The contract-level control moves every payment not yet
  received (booked → contracted, cancel, or undo); received ones stay received.
- Entry: Sales form (organization page, deal card for people, phone API) with "paid in how
  many monthly payments" and the first due day. The phone app shows "payment 2 of 4"; it
  cannot yet create a schedule.

## Step 2 — forecast (next)
- **Periods:** a Month / Quarter / Year switch, plus "this month", "this quarter" and "this
  year" tiles. Each period shows expected, booked, contracted, collected and the total
  (without cancelled), placed by due day (`expected_on`) — or `collected_on` once received.
  Money with no due day goes to an "undated" bucket.
- **Targets:** entered **per month** and summed for a quarter or year. A month's target is the
  income needed minus any other income that covers part of it over a date range (so the
  target can change from one month to the next). Users think in quarters, so the quarter is
  the headline figure. The owner's own figures are not recorded in this public repository.
- **No probabilities:** expected is expected, booked is booked, collected is collected.
- Follows the offer filter; stays inside the workspace (customers will get it later).

## Step 3 — targeting
Group revenue, pipeline, hours and € per hour by organization type, offer and city, to show
which kinds of customers pay for the time spent. Only as good as the hours logged.
