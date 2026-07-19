-- Append-only record of state-changing work by people, agents, and MCP clients.
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actor TEXT NOT NULL,
    actor_type TEXT NOT NULL CHECK (actor_type IN ('user', 'ai', 'system-job', 'mcp')),
    action TEXT NOT NULL,
    target TEXT,
    outcome TEXT,
    correlation_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_log_correlation_id ON audit_log (correlation_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_target ON audit_log (target);
