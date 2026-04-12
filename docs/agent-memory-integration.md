# Agent Memory Integration Guide

Port of the artcrm-supervisor agent memory system to eng-crm. Adds two memory types:

1. **Outreach quality loop** — the followup agent records warm replies; a weekly job synthesises patterns; the outreach agent injects learnings before drafting
2. **Observations layer** — any agent or the human can write/read shared notes via Open Brain

Reference implementation: `~/programming/art-crm/artcrm-supervisor/`

---

## Before You Start

- Open Brain connection details are in `~/programming/art-crm/artcrm-supervisor/docs/open-brain-guide.md`
- The `mcp` SDK (version 1.26+) must be installed: `uv add mcp`
- All file paths below are relative to `~/programming/eng-crm/`

---

## Step 1: Config

Add to `gcrm/config.py`, after the `EMAIL_ENABLED` line:

```python
# --- Open Brain memory ---
OPEN_BRAIN_URL: str = os.getenv("OPEN_BRAIN_URL", "")
OPEN_BRAIN_TOKEN: str = os.getenv("OPEN_BRAIN_TOKEN", "")
```

Add to `.env`:

```
OPEN_BRAIN_URL=https://qaonmvqhlvrrvfkqcjbf.supabase.co/functions/v1/open-brain-mcp
OPEN_BRAIN_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFhb25tdnFobHZycnZma3FjamJmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM0Mjk2NDksImV4cCI6MjA4OTAwNTY0OX0.AZwWYEdMQ93W2Bxkj-dGgy3_LMnSLPH885auXkYi5Ow
```

---

## Step 2: DB Migration

Create `gcrm/db/migrations/007_outreach_outcomes.sql`:

```sql
CREATE TABLE IF NOT EXISTS outreach_outcomes (
    id                   SERIAL PRIMARY KEY,
    contact_id           INTEGER NOT NULL REFERENCES contacts(id),
    sent_interaction_id  INTEGER REFERENCES interactions(id),
    reply_interaction_id INTEGER REFERENCES interactions(id),
    warm                 BOOLEAN NOT NULL DEFAULT true,
    word_count           INTEGER,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS outreach_outcomes_contact_id_idx ON outreach_outcomes(contact_id);
CREATE INDEX IF NOT EXISTS outreach_outcomes_created_at_idx ON outreach_outcomes(created_at);
```

Create `gcrm/db/migrations/008_outreach_outcomes_unique.sql`:

```sql
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'outreach_outcomes_sent_interaction_unique'
    ) THEN
        ALTER TABLE outreach_outcomes
            ADD CONSTRAINT outreach_outcomes_sent_interaction_unique
            UNIQUE (sent_interaction_id);
    END IF;
END $$;
```

Apply:

```bash
uv run python scripts/migrate.py
```

---

## Step 3: memory.py

Copy `src/tools/memory.py` from artcrm-supervisor to `gcrm/tools/memory.py`. The only change needed is the config import path:

```python
def _get_config() -> tuple[str, str]:
    from gcrm.config import OPEN_BRAIN_URL, OPEN_BRAIN_TOKEN   # ← gcrm not src
    return OPEN_BRAIN_URL, OPEN_BRAIN_TOKEN
```

The rest of the file is identical — `capture_thought`, `search_artcrm_thoughts`, the async-safe `_run_tool` wrapper, the metadata regex.

Copy the tests too: `tests/test_memory.py` from artcrm-supervisor → `tests/test_memory.py`. Change all `src.tools.memory` references to `gcrm.tools.memory`.

---

## Step 4: DB Helper Functions

In `gcrm/tools/__init__.py`, add `record_warm_outcome` and `get_outreach_outcomes`. Copy from artcrm-supervisor `src/tools/db.py` — the functions are identical except:

- Change `from src.db.connection import db` → `from gcrm.db.connection import db` (check the actual import path in `gcrm/tools/__init__.py`)
- Change any `src.` references to `gcrm.`

**record_warm_outcome(contact_id: int) → None**

Queries most recent outbound + inbound interactions and last approved draft, inserts into `outreach_outcomes`. Uses `ON CONFLICT (sent_interaction_id) DO NOTHING` for idempotency. Silently skips if no outbound interaction found.

**get_outreach_outcomes(days: int = 90) → list[dict]**

Joins `outreach_outcomes` with `contacts` and `approval_queue` (LATERAL join for the most recent approved draft), filters to last `days` days.

Full implementations are in `~/programming/art-crm/artcrm-supervisor/src/tools/db.py` — search for `def record_warm_outcome` and `def get_outreach_outcomes`.

---

## Step 5: Followup Agent — Warm Outcome Recording

The eng-crm followup agent signature differs from artcrm's — it uses `send_email` + `mark_message_processed` instead of `save_inbox_classification` + `handle_bounce`. The wiring is the same either way.

### 5a. Add WarmOutcomeRecorder to protocols.py

In `agents/gcrm-followup-agent/gcrm_followup_agent/protocols.py`, add before `RunStarter`:

```python
class WarmOutcomeRecorder(Protocol):
    """Record that a contact sent a warm or interested reply. Used for outreach quality analysis."""
    def __call__(self, contact_id: int) -> None: ...
```

### 5b. Add to create_followup_agent signature

In `agents/gcrm-followup-agent/gcrm_followup_agent/graph.py`:

1. Import `WarmOutcomeRecorder` from `.protocols`
2. Add `record_warm_outcome: WarmOutcomeRecorder,` to the function parameters (after `set_opt_out`)

### 5c. Call record_warm_outcome after classification

Find the `log_interaction(...)` call block in `graph.py`. Replace the bare `except: pass` with a tracked pattern, then add the warm outcome call after:

```python
            interaction_logged = False
            try:
                log_interaction(
                    contact_id=contact["id"],
                    method="email",
                    direction="inbound",
                    summary=f"{classification}: {msg.get('subject', '')}",
                    outcome=outcome_map.get(classification, "no_reply"),
                )
                interaction_logged = True
            except Exception as e:
                logger.warning("log_interaction failed: contact_id=%s error=%s", contact.get("id"), e)

            # Record warm signal for outreach quality loop — only if interaction committed
            if interaction_logged and classification in ("interested", "warm"):
                try:
                    record_warm_outcome(contact["id"])
                except Exception as e:
                    logger.warning("record_warm_outcome failed: contact_id=%s error=%s", contact.get("id"), e)
```

Check what classifications the eng-crm followup agent uses for warm/positive replies — may differ from artcrm. Look for the `outcome_map` or the LLM classification prompt.

### 5d. Inject in supervisor/run.py (or wherever create_followup_agent is called)

Add `record_warm_outcome` to the tools import and pass it to `create_followup_agent`:

```python
from gcrm.tools import (
    ...
    record_warm_outcome,
)

agent = create_followup_agent(
    ...
    record_warm_outcome=record_warm_outcome,
)
```

Same if the supervisor graph builds the agent — update that call too.

---

## Step 6: Outreach Agent — Learnings Injection

### 6a. Add learnings to state

In `agents/gcrm-outreach-agent/gcrm_outreach_agent/state.py`, add to the TypedDict:

```python
class OutreachState(TypedDict):
    limit: int
    learnings: list[str]    # style notes from Open Brain, empty list if none
    ...
```

### 6b. Update draft prompt

In `agents/gcrm-outreach-agent/gcrm_outreach_agent/prompts.py`, find the email drafting prompt function and add:

```python
def draft_email_prompt(
    ...,
    learnings: list[str] | None = None,
) -> tuple[str, str]:
    learnings_section = ""
    if learnings:
        items = "\n".join(f"- {l}" for l in learnings)
        learnings_section = f"\nRecent learnings from past outreach (apply these patterns):\n{items}\n"

    system = (
        f"You are {mission.identity}.\n"
        f"Outreach style: {mission.outreach_style}"
        f"{learnings_section}"
    )
    # rest unchanged
```

### 6c. Pass learnings in graph.py

In `agents/gcrm-outreach-agent/gcrm_outreach_agent/graph.py`:

In `init`, pass `"learnings": state.get("learnings", [])`.

In the draft function, pass `learnings=state.get("learnings", [])` to `draft_email_prompt`.

### 6d. Fetch learnings before invoke

Wherever `outreach_agent.invoke(...)` is called (in supervisor `run.py` or `graph.py`):

```python
from gcrm.tools.memory import search_artcrm_thoughts

learnings = search_artcrm_thoughts("outreach email tone style", limit=5)
if learnings:
    logger.info("outreach: injecting %d learnings from Open Brain", len(learnings))

result = agent.invoke({"limit": args.limit, "learnings": learnings})
```

---

## Step 7: Research Agent — City Observation

In `gcrm/supervisor/run_research.py`, after `record_scan_result(...)`:

```python
    summary = result.get("summary", "")
    contacts_found = len(result.get("saved_ids", []))
    record_scan_result(args.city, args.country, args.level, contacts_found)

    if contacts_found > 0:
        from gcrm.tools.memory import capture_thought
        capture_thought(
            f"gcrm city scan: {args.city} (level {args.level}). "
            f"Found {contacts_found} new contacts. {summary}"
        )
        logger.info("memory: captured city observation for %s", args.city)

    logger.info("Done: %s", summary)
```

Note: use `"gcrm city scan:"` prefix (not `"artcrm"`) so searches can distinguish the two systems if Open Brain is shared.

---

## Step 8: Weekly Analysis Job

Create `gcrm/supervisor/run_outreach_analysis.py`. Copy from `~/programming/art-crm/artcrm-supervisor/src/supervisor/run_outreach_analysis.py` and change:

- All `src.` imports → `gcrm.`
- The `project=` tag in `capture_thought` if you want to namespace: leave as default (`"artcrm"`) if sharing Open Brain with artcrm, or use `"gcrm"` to keep them separate
- The system prompt references "watercolor painter … galleries … Germany" — update to match the eng-crm vertical context

Add to crontab (Monday 7:30am):

```
30 7 * * 1  cd ~/programming/eng-crm && .venv/bin/python -m gcrm.supervisor.run_outreach_analysis >> ~/logs/gcrm-outreach-analysis.log 2>&1
```

---

## Step 9: Marketing / Dashboard UI (Optional)

The artcrm UI has a full Observations section on the marketing page. For eng-crm, add an equivalent section to whatever dashboard page makes sense.

Key pieces:

- `GET /observations` partial — calls `search_artcrm_thoughts("gcrm", limit=20)`, returns `observations_list.html`
- `POST /observations` — calls `capture_thought(content)`, returns refreshed partial
- HTMX form + lazy-load div (see `src/ui/templates/marketing.html` in artcrm for the pattern)

---

## Step 10: Setup Script

Create `scripts/setup_memory.py`. Copy from `~/programming/art-crm/artcrm-supervisor/scripts/setup_memory.py` and update the topic hints descriptions to match the eng-crm vertical (engineering / consulting instead of art / galleries):

```python
TOPIC_HINTS = [
    {
        "topic": "gcrm-outreach",
        "description": "Email tone, word count, subject lines, response rates for engineering CRM outreach",
        "category": "projects",
    },
    {
        "topic": "gcrm-city",
        "description": "City-level notes for gcrm: company density, responsiveness, regional patterns",
        "category": "projects",
    },
    {
        "topic": "gcrm-venue",
        "description": "Company type patterns for gcrm: startups, SMEs, enterprises, consulting firms",
        "category": "projects",
    },
    {
        "topic": "gcrm-seasonal",
        "description": "Seasonal observations for gcrm: hiring cycles, budget cycles, conference seasons",
        "category": "projects",
    },
]
```

Change `from src.tools.memory import _run_tool` → `from gcrm.tools.memory import _run_tool`.

Run once after setup:

```bash
uv run python scripts/setup_memory.py
```

---

## Shared vs Separate Open Brain

Both systems use the same Open Brain instance. Thoughts are namespaced by the `project=` argument in `capture_thought` and by the prefix in search queries.

- artcrm uses `project="artcrm"` and searches for `"artcrm ..."`
- eng-crm should use `project="gcrm"` and search for `"gcrm ..."`

The `search_artcrm_thoughts` function in `memory.py` prefixes with `"artcrm"` — for eng-crm, rename it `search_gcrm_thoughts` and prefix with `"gcrm"` instead. Everything else in `memory.py` is identical.

---

## File Checklist

```
gcrm/config.py                              ← add OPEN_BRAIN_URL, OPEN_BRAIN_TOKEN
gcrm/db/migrations/007_outreach_outcomes.sql  ← new
gcrm/db/migrations/008_outreach_outcomes_unique.sql  ← new
gcrm/tools/memory.py                        ← new (copy + change import path)
gcrm/tools/__init__.py                      ← add record_warm_outcome, get_outreach_outcomes
gcrm/supervisor/run_research.py             ← add capture_thought after scan
gcrm/supervisor/run_outreach_analysis.py    ← new (copy + change imports)
agents/gcrm-followup-agent/gcrm_followup_agent/protocols.py  ← add WarmOutcomeRecorder
agents/gcrm-followup-agent/gcrm_followup_agent/graph.py      ← wire record_warm_outcome
agents/gcrm-outreach-agent/gcrm_outreach_agent/state.py      ← add learnings field
agents/gcrm-outreach-agent/gcrm_outreach_agent/prompts.py    ← add learnings to prompt
agents/gcrm-outreach-agent/gcrm_outreach_agent/graph.py      ← pass learnings through
scripts/setup_memory.py                     ← new (copy + update topic hints)
.env                                        ← add OPEN_BRAIN_URL, OPEN_BRAIN_TOKEN
```
