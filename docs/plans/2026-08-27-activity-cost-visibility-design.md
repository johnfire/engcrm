# Activity Cost Visibility Design

**Date:** 2026-08-27

## Goal

Cost tracking already exists end-to-end but is invisible: every agent run
records LLM/search/crawler expense into `run_costs`
([020_run_costs.sql](../../gcrm/db/migrations/020_run_costs.sql)) via
`gcrm/tools/costs.py` and `gcrm/tools/db_agent_runs.py`, but the only place it
surfaces is a text line buried in `agent_runs.summary` (e.g.
`cost=$0.0123 | search:5q | claude:1200tok`). Nothing aggregates it and
nothing shows a number you can scan.

This design surfaces the existing data on the web Activity page
(`/activity/`) — no new tracking, no new tables, no mobile changes. Scope is
deliberately narrow: make spend visible and comparable across agents, not
build a full analytics surface or tie cost to business outcomes (opportunities
found, deals closed) — that's a separate, later step if this proves useful.

## Data Layer

All changes are in [gcrm/api/routers/activity.py](../../gcrm/api/routers/activity.py).

**1. Per-run cost column** — change the runs query to:

```sql
SELECT ar.id, ar.agent_name, ar.started_at, ar.finished_at, ar.status,
       ar.summary, rc.total_usd AS cost_usd
FROM agent_runs ar
LEFT JOIN run_costs rc ON rc.run_id = ar.id
ORDER BY ar.started_at DESC
LIMIT 500
```

`LEFT JOIN` because not every run has a cost row (agents that don't call
`start_run`/`finish_run` with cost tracking, or runs that crashed before
`finish_run`). `cost_usd` is `NULL` in that case → render as `—`.

**2. Spend summary (today / week / month / all-time)**:

```sql
SELECT
    COALESCE(SUM(total_usd) FILTER (WHERE recorded_at >= CURRENT_DATE), 0) AS today,
    COALESCE(SUM(total_usd) FILTER (WHERE recorded_at >= NOW() - INTERVAL '7 days'), 0) AS this_week,
    COALESCE(SUM(total_usd) FILTER (WHERE recorded_at >= NOW() - INTERVAL '30 days'), 0) AS this_month,
    COALESCE(SUM(total_usd), 0) AS all_time
FROM run_costs
```

**3. Per-agent breakdown (all-time only)**:

```sql
SELECT ar.agent_name,
       COUNT(*) AS run_count,
       SUM(rc.total_usd) AS total_usd,
       AVG(rc.total_usd) AS avg_usd
FROM run_costs rc
JOIN agent_runs ar ON ar.id = rc.run_id
GROUP BY ar.agent_name
ORDER BY total_usd DESC
```

All three queries run against `run_costs`, which already has an index on
`recorded_at`. No migration needed.

## UI Layer

[gcrm/ui/templates/activity.html](../../gcrm/ui/templates/activity.html):

- A second `.stats-row` (reusing the existing `.stat`/`.stat-value`/
  `.stat-label` markup from the pending/approved/edited/rejected row) showing
  Today / This Week / This Month / All-Time spend as `$X.XX`.
- A small per-agent cost table above the runs table: **Agent | Runs | Total $
  | Avg $/Run**, plain `<table>` styling matching the runs table — no new CSS.
- The runs table gets one new `Cost` column between `Status` and `Summary`,
  right-aligned, `${{ "%.4f"|format(run.cost_usd) }}` or `—` when null. The
  existing text summary line is untouched — this adds a scannable number next
  to it, doesn't replace it.
- New i18n keys in both `gcrm/i18n/en.json` and `gcrm/i18n/de.json`:
  `activity.spendToday`, `activity.spendWeek`, `activity.spendMonth`,
  `activity.spendAllTime`, `activity.costByAgent`, `activity.runs`,
  `activity.totalCost`, `activity.avgCost`, `activity.cost`.

No JavaScript, no charting library — server-rendered like the rest of the
page.

## Testing

- Extend whatever test currently covers `activity_feed()` (or add one) to
  assert: a run with a `run_costs` row shows its `$` value; a run without one
  shows `—`; the spend-summary numbers match a hand-computed sum over seeded
  `run_costs` rows; the per-agent table sums correctly across two agents.
- No new integration/e2e surface — this is additive to an existing
  authenticated page, covered by whatever auth/e2e check already exercises
  `/activity/`.

## Out of Scope (for now)

- Mobile (`/api/activity`, `engcrm-mobile/app/(drawer)/activity.tsx`) —
  structured cost fields could be added the same way later if wanted.
- Cost-per-outcome efficiency metrics (cost per opportunity found, per
  successful outreach) — needs a join to opportunity/outcome tables that
  doesn't exist yet; a natural follow-up once raw spend is visible.
- Budgets/alerts on spend.
