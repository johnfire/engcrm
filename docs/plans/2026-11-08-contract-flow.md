# Contract flow: how new business and money in grow over time (decided 2026-11-08)

Three charts below the Forecast table, with a range switch (3 months by week, 1 year by month, the
whole business by month, or by year past four years). They follow the offer filter and stay inside
the workspace. Everything at "expected" or above counts: expected, booked, contracted, collected.
Cancelled is left out.

1. **New business per week/month/year**: the value entered in each period (by the date the sale was
   won, `won_on`). A monthly contract is one deal, entered once. The tooltip carries the number of
   deals and the split by status. One series, one hue, like the Statistics charts.
2. **Total won so far**: the running total of everything entered, including before the range.
3. **Money in vs target**: collected sales (on the day the money came in) plus confirmed other income,
   against the plan's monthly need, as a running total. The target and the other income are spread
   evenly over the days of each month so a weekly chart has a smooth pace line. Without a plan only
   the money-in line is drawn.

The colours of a sale show where it stands *now*, so none of these charts split by status over time.
That needs history: since migration 089 every status change is written to `sale_status_changes`
(by triggers; existing sales get one starting row dated when they were entered). A chart of the
pipeline as it stood on past days, built on that log, is a later step once there is history.
The log is not part of the backup export yet.

## Outlook (added 2026-11-08)

A fourth range, "Outlook": monthly, from the first month of the business (at most two years back) to
twelve months ahead. The first two charts stop at today; the third spans the page with three lines:
money in so far (solid, stops today), the projection (dotted, smooth, from today on) and the target
(dashed, whole months, through every month ahead).

The projection is **not** a forecast of deals not yet won. It adds up what is already scheduled:
what has been collected, plus every unreceived sale on its due day (`expected_on`; a late one counts in
the current month), plus the confirmed other income for the months it covers. Expected counts, as the
owner treats it as a firm verbal commitment; there are no probabilities. The unconfirmed ("possible")
other income is left out. A sale with no due day cannot be placed and is listed under the chart.
The smoothness is drawing only (monotone cubic interpolation through the true monthly totals, so it
never overshoots). A fitted "if the pace continues" line for future new business is a later, clearly
labelled option once there is enough history to mean something.

### Expected new sales (blue line)
The owner can enter one number in the Plan section: the euros of new sales expected to be **booked each
month**, starting with the current month (`income_plan.expected_new_monthly`, migration 090; blank or 0
draws nothing). The Outlook chart then adds a fourth, blue dotted line: the projection plus that amount
times the months from this one through each month, so "what is already entered" and "what I hope to
add" stay visibly apart. It is an assumption, stated in the chart note: each sale is taken as paid in
the month it is booked, on top of everything already entered.

A second field says how many months each booking keeps paying (migration 091, `expected_new_months`):
1 (the default) is the one-off above; a number such as 6 makes every booking pay its amount for that many
months from the month it is booked, so the streams stack; `i` (or ∞) means it pays every month from then on
(NULL in the database). At 1,000 a month and "for ever" the extra money after k months is 1,000 × k(k+1)/2. The projection itself never changes.
