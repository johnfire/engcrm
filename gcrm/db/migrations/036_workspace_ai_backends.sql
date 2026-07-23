-- Administrator-selected AI backends for each workspace.
CREATE TABLE IF NOT EXISTS workspace_ai_backends (
    workspace_id INTEGER PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    cheap_llm TEXT NOT NULL CHECK (cheap_llm IN ('deepseek-v4-flash', 'claude-haiku')),
    smart_llm TEXT NOT NULL CHECK (smart_llm IN ('deepseek-v4-flash', 'claude')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
