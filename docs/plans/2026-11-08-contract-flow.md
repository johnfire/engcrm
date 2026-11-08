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
