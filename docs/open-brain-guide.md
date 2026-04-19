# Open Brain — Integration Guide

Open Brain is a personal memory server backed by Supabase. It stores thoughts as embeddings and supports semantic search. This doc covers how to connect to it and use it from a Python agent or coding session.

---

## Connection

**Endpoint:**

```
https://qaonmvqhlvrrvfkqcjbf.supabase.co/functions/v1/open-brain-mcp
```

**Required headers:**

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFhb25tdnFobHZycnZma3FjamJmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM0Mjk2NDksImV4cCI6MjA4OTAwNTY0OX0.AZwWYEdMQ93W2Bxkj-dGgy3_LMnSLPH885auXkYi5Ow
x-brain-key: bf402ca9240a2d5481bf7314033b3d02cbb3a691a6efc871ccb72d8cf022227c
```

Both headers are required. The JWT (`Authorization`) authenticates with Supabase. The `x-brain-key` is the application-level key.

---

## As an MCP Server (Claude Code / AI client config)

Add to your MCP server config (e.g. `~/.claude.json` under `mcpServers`):

```json
"open-brain": {
  "type": "http",
  "url": "https://qaonmvqhlvrrvfkqcjbf.supabase.co/functions/v1/open-brain-mcp",
  "headers": {
    "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFhb25tdnFobHZycnZma3FjamJmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM0Mjk2NDksImV4cCI6MjA4OTAwNTY0OX0.AZwWYEdMQ93W2Bxkj-dGgy3_LMnSLPH885auXkYi5Ow",
    "x-brain-key": "bf402ca9240a2d5481bf7314033b3d02cbb3a691a6efc871ccb72d8cf022227c"
  }
}
```

Once configured, the MCP tools are available directly in the session (see tools section below).

---

## From Python (mcp SDK)

Use `mcp` SDK 1.26+ with `streamablehttp_client`. The pattern below works from both sync and async contexts.

### Installation

```bash
uv add mcp
```

### Sync wrapper (safe from FastAPI or plain Python)

```python
import asyncio
import logging
import concurrent.futures

OPEN_BRAIN_URL = "https://qaonmvqhlvrrvfkqcjbf.supabase.co/functions/v1/open-brain-mcp"
OPEN_BRAIN_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFhb25tdnFobHZycnZma3FjamJmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM0Mjk2NDksImV4cCI6MjA4OTAwNTY0OX0.AZwWYEdMQ93W2Bxkj-dGgy3_LMnSLPH885auXkYi5Ow"

logger = logging.getLogger(__name__)


def _call_tool(tool_name: str, arguments: dict) -> str:
    """Call an Open Brain MCP tool. Returns text response or empty string on failure."""
    async def _inner() -> str:
        from mcp.client.streamable_http import streamablehttp_client
        from mcp import ClientSession
        headers = {"Authorization": f"Bearer {OPEN_BRAIN_TOKEN}"}
        async with streamablehttp_client(OPEN_BRAIN_URL, headers=headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                texts = [c.text for c in result.content if hasattr(c, "text")]
                return "\n".join(texts)

    try:
        # Safe to call from both async (FastAPI) and sync contexts
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(lambda: asyncio.run(_inner())).result(timeout=10)
        else:
            return asyncio.run(_inner())
    except Exception as e:
        logger.warning("open_brain: %s failed: %s", tool_name, e)
        return ""
```

> **Note:** Only the `Authorization` header is needed for the Python SDK client — the `x-brain-key` is for direct HTTP and MCP config file usage.

---

## Available Tools

### `capture_thought`

Save a thought, observation, or learning. Open Brain auto-extracts type, topics, and people from the content and generates an embedding for semantic search.

**Arguments:**

- `content` (required) — the thought text
- `project` (optional) — tag it to a project, e.g. `"artcrm"`, `"personal"`

**Python:**

```python
_call_tool("capture_thought", {
    "content": "Munich hotel galleries respond better to emails under 150 words",
    "project": "artcrm"
})
```

**Via MCP in session:** `mcp__open-brain__capture_thought`

---

### `search_thoughts`

Semantic search over stored thoughts. Returns the top N matches above a similarity threshold.

**Arguments:**

- `query` (required) — what to search for (natural language)
- `limit` (default: 10) — max results to return
- `threshold` (default: 0.5) — similarity cutoff, 0.0–1.0. Use `0.45` for broader recall.

**Python:**

```python
raw = _call_tool("search_thoughts", {
    "query": "artcrm outreach email tone gallery",
    "limit": 5,
    "threshold": 0.45,
})
```

The response is a formatted text block. Each result looks like:

```
Found 2 thought(s):

--- Result 1 (78.0% match) ---
Captured: 4/12/2026
Type: observation
Project: artcrm
Status: active
Topics: outreach

Munich galleries respond better to brief emails — under 150 words.
--- Result 2 (61.0% match) ---
...
```

To extract just the content (strip metadata), split on `--- Result N ... ---` and drop lines matching `Captured:`, `Type:`, `Project:`, `Status:`, `Topics:`, `People:`, `Actions:`, `---`, and `Found N thought(s):`.

**Via MCP in session:** `mcp__open-brain__search_thoughts`

---

### `list_thoughts`

List recently captured thoughts with optional filters.

**Arguments (all optional):**

- `project` — filter by project tag
- `type` — filter by type: `observation`, `task`, `idea`, `reference`, `person_note`
- `topic` — filter by extracted topic tag
- `person` — filter by person mentioned
- `status` — filter by status: `active`, `completed`, `superseded`, `archived`
- `days` — only thoughts from the last N days
- `limit` (default: 10)

**Python:**

```python
raw = _call_tool("list_thoughts", {
    "project": "artcrm",
    "days": 30,
    "limit": 20,
})
```

**Via MCP in session:** `mcp__open-brain__list_thoughts`

---

### `add_topic_hint`

Register a topic hint so Open Brain recognizes it during future ingestion. This is a one-time setup step per project.

**Arguments:**

- `topic` (required) — topic name, e.g. `"artcrm-outreach"`
- `description` (required) — what this topic covers
- `category` (default: `"general"`) — grouping: `ai`, `engineering`, `projects`, `art`, `personal`, etc.

**Python:**

```python
_call_tool("add_topic_hint", {
    "topic": "artcrm-outreach",
    "description": "Email tone, length, subject lines, response rates for art venue outreach",
    "category": "projects",
})
```

**Via MCP in session:** `mcp__open-brain__add_topic_hint`

---

### `list_topic_hints`

List registered topic hints.

**Arguments:**

- `category` (optional) — filter by category

**Via MCP in session:** `mcp__open-brain__list_topic_hints`

---

## artcrm Project Usage

In this project, Open Brain is used with `project="artcrm"`. Four topic hints are registered:

| Topic             | Covers                                              |
| ----------------- | --------------------------------------------------- |
| `artcrm-outreach` | Email tone, length, subject lines, response rates   |
| `artcrm-city`     | City-level venue notes, seasonal patterns           |
| `artcrm-venue`    | Venue type patterns (galleries, hotels, cafes)      |
| `artcrm-seasonal` | Time-of-year observations, events, plein air season |

The project wrapper is in `src/tools/memory.py`:

- `capture_thought(content, project="artcrm")` — saves to Open Brain
- `search_artcrm_thoughts(query, limit=5)` — searches and returns a clean `list[str]`

Config comes from `.env`:

```
OPEN_BRAIN_URL=https://qaonmvqhlvrrvfkqcjbf.supabase.co/functions/v1/open-brain-mcp
OPEN_BRAIN_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```
