-- Per-run cost record (LLM token usage + web-search query count), written by
-- finish_run when cost tracking is enabled.
CREATE TABLE IF NOT EXISTS run_costs (
    id             SERIAL PRIMARY KEY,
    run_id         INTEGER NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    search_queries INTEGER NOT NULL DEFAULT 0,
    llm_usage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    total_usd      NUMERIC(12, 6) NOT NULL DEFAULT 0,
    recorded_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_run_costs_recorded_at ON run_costs (recorded_at DESC);
