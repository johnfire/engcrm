# gcrm Agent System — Runbook

Complete setup, operation, and testing guide.

---

## Repos

| Repo | Purpose | Status |
|---|---|---|
| `theo-hits-the-road` | Original CRM, CLI, PostgreSQL schema | Untouched — always works as fallback |
| `gcrm supervisor` | Orchestrator, FastAPI UI, tool implementations, supervisor graph | Done |
| `gcrm-research-agent` | Researches cities/industries for new contacts | Done |
| `gcrm-scout-agent` | Scores candidates for mission fit | Done |
| `gcrm-outreach-agent` | Drafts first-contact emails, queues for approval | Done |
| `gcrm-followup-agent` | Monitors inbox, classifies replies, sends follow-ups | Done |

The repo lives at `~/ppp2/engcrm`. The five agent packages are vendored in-repo under `agents/gcrm-*-agent/` (installed as editable sources), not separate sibling repos.

> **Note:** This Runbook still describes the original multi-repo `theo-hits-the-road` lineage (separate agent repos, shared `artcrm` DB, "original CRM fallback" framing). Paths, module names, and the DB name have been refreshed to the generalized `gcrm` layout, but a deeper prose rewrite of the architecture narrative is recommended. See README.md for the current self-contained `general-crm` description.

---

## Prerequisites

- PostgreSQL running with the `gcrm` database (same one used by `theo-hits-the-road`)
- `uv` installed (`~/.local/bin/uv`)
- Proton Bridge running locally (required for any email send/receive)
- DeepSeek API key (routine tasks) and/or Anthropic API key (high-stakes drafts)
- `~/logs/` directory exists: `mkdir -p ~/logs`

---

## First-Time Setup

### 1. Configure

```bash
cd ~/ppp2/engcrm
cp .env.example .env
```

Edit `.env`:
```
DATABASE_URL=postgresql://user:password@localhost/gcrm
DEEPSEEK_API_KEY=your_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
ANTHROPIC_API_KEY=your_key          # optional

PROTON_IMAP_HOST=127.0.0.1
PROTON_IMAP_PORT=1143
PROTON_SMTP_HOST=127.0.0.1
PROTON_SMTP_PORT=1025
PROTON_EMAIL=your@proton.me
PROTON_PASSWORD=bridge_app_password  # from Proton Bridge settings

HOST=127.0.0.1
PORT=8000
```

### 2. Run DB migrations

```bash
uv run python scripts/migrate.py
```

Adds 4 new tables (`agent_runs`, `consent_log`, `approval_queue`, `inbox_messages`) and the `candidate` status to `lookup_values`. Does not touch existing tables.

### 3. Verify agent packages are installed

```bash
uv sync --extra agents --extra dev
```

The four agent packages are listed as editable sources in `pyproject.toml` pointing to sibling directories. If they need reinstalling:

```bash
uv add --editable agents/gcrm-research-agent
uv add --editable agents/gcrm-scout-agent
uv add --editable agents/gcrm-outreach-agent
uv add --editable agents/gcrm-followup-agent
```

### 4. Start the UI

```bash
uv run python -m gcrm.api.main
# http://127.0.0.1:8000
```

---

## Running the System

### Full supervisor run

```bash
uv run python -m gcrm.supervisor.run
```

Run order:
1. **Research** — once per target in `gcrm/supervisor/targets.py`
2. **Scout** — scores all `status=candidate` contacts
3. **Outreach** — drafts emails for `status=cold` contacts, queues for approval
4. **Follow-up** — reads inbox, classifies replies, sends follow-ups to overdue contacts

Logs to `~/logs/supervisor.log` and the `/activity/` UI page.

### Schedule with cron

```cron
0 7 * * * cd ~/ppp2/engcrm && ~/.local/bin/uv run python -m gcrm.supervisor.run >> ~/logs/supervisor.log 2>&1
```

---

## The UI

| Page | URL | What it shows |
|---|---|---|
| Approval Queue | `/approvals/` | Email drafts pending review. Approve sends immediately. |
| Contacts | `/contacts/` | All contacts with status filter and name/city search. |
| Activity Feed | `/activity/` | Agent run log with status, duration, and summary. |

**Approval actions:**
- **Approve** — sends via Proton Bridge SMTP, logs interaction, contact → `status=contacted`
- **Edit + Approve** — edit subject/body first, then sends
- **Reject** — discards draft, contact stays `status=cold` for next run

If Proton Bridge is not running, status shows `approved_unsent`. Re-trigger by running the outreach agent again.

---

## Contact Flow

```
targets.py — define cities and industries to research
  ↓
research_agent  →  status=candidate
  ↓
scout_agent     →  status=cold (score≥60) or status=dropped
  ↓
outreach_agent  →  approval_queue (status=pending)
  ↓
YOU approve at /approvals/
  ↓
Proton Bridge SMTP  →  email sent, status=contacted, interaction logged
  ↓
followup_agent (next run):
  ├── reply interested  →  drafts + sends reply, logs
  ├── reply rejected    →  logs, no further action
  ├── reply opt_out     →  consent_log updated, status=dormant, never contacted again
  └── no reply (90+ days)  →  drafts + sends brief follow-up
```

---

## Importing Existing Marketing Studies

If you already have venue research as markdown files, import them directly instead of running the research agent:

```bash
uv run python scripts/import_studies.py
```

This reads the 6 city markdown files in `~/ai-workzone/art-marketing-by-city/`, uses the LLM to extract every venue, and saves them as `status=candidate`. Safe to re-run — duplicates (same name + city) are silently skipped.

After import, run the supervisor normally. The scout agent will score and promote them; the research step will find nothing new to add for the same cities (also harmless).

To skip the research step entirely, clear the target list in [gcrm/supervisor/targets.py](gcrm/supervisor/targets.py):

```python
RESEARCH_TARGETS = []
```

To add new cities later, add entries back.

---

## Scout Threshold — Controlling Outreach Volume

The scout agent scores each candidate 0–100 for mission fit. The threshold controls which ones are promoted to `status=cold` for outreach.

Set it in `.env`:

```
SCOUT_THRESHOLD=75   # start here — best venues only
SCOUT_THRESHOLD=60   # lower when you want more volume
SCOUT_THRESHOLD=50   # cast a wide net
```

Default is `75`. Contacts that score below the threshold are set to `status=dropped` and won't be contacted. They remain in the database — if you lower the threshold later and re-run the scout agent against a fresh import, they can be re-evaluated.

---

## Configuring Research Targets

Edit [gcrm/supervisor/targets.py](gcrm/supervisor/targets.py):

```python
RESEARCH_TARGETS = [
    {"city": "Augsburg", "industry": "gallery",    "country": "DE"},
    {"city": "Munich",   "industry": "restaurant", "country": "DE"},
]
```

Supported industries: `gallery`, `restaurant`, `hotel`, `cafe`, `museum`, `office`, `coworking`, `bar`

---

## Changing the Mission

Edit `gcrm/config.py` — replace `ART_MISSION` and point `ACTIVE_MISSION` to it:

```python
SOFTWARE_MISSION = Mission(
    goal="Find SMEs that need web development",
    identity="Acme Web Dev, Munich",
    targets="retail, clinics, tradespeople",
    fit_criteria="10-100 employees, outdated website",
    outreach_style="professional, ROI-focused",
    language_default="de",
)

ACTIVE_MISSION: Mission = SOFTWARE_MISSION
```

All four agents use `ACTIVE_MISSION` — nothing else changes.

---

## The Original CRM

`theo-hits-the-road` is untouched. Both systems share the same PostgreSQL database and can run simultaneously.

```bash
cd ~/programming/theo-hits-the-road
source venv/bin/activate
python main.py      # menu
scripts/crm --help  # CLI
pytest              # its own tests
```

---

## Testing

### Run everything

```bash
# Agent repos (each has its own venv)
for repo in gcrm-research-agent gcrm-scout-agent gcrm-outreach-agent gcrm-followup-agent; do
    echo "=== $repo ===" && cd ~/programming/$repo && uv run pytest -v
done

# Supervisor
cd ~/ppp2/engcrm && uv run pytest -v
```

### Test count and coverage

| Repo | Tests | What's covered |
|---|---|---|
| `gcrm-research-agent` | 4 | Saves contacts, empty results, LLM JSON error, markdown-wrapped JSON |
| `gcrm-scout-agent` | 4 | Promotes high score, drops low score, empty candidates, batch continues on error |
| `gcrm-outreach-agent` | 4 | Queues compliant contact, blocks opted-out, handles draft error, empty contacts |
| `gcrm-followup-agent` | 7 | Interested reply, opt-out flagging, rejected reply, overdue follow-up, empty inbox, unmatched sender, SMTP failure |
| `gcrm supervisor` — tools | 9 | `save_contact`, `check_compliance` (4 cases), `set_opt_out`, `start_run`, `finish_run` |
| `gcrm supervisor` — supervisor | 3 | All agents run, continues on failure, report includes all summaries |
| **Total** | **31** | |

### Testing philosophy

All unit tests run with **zero external dependencies**:
- `FakeLLM` returns scripted responses — no real API calls
- DB connections are mocked with `unittest.mock.patch`
- No network access

The `conftest.py` in the supervisor tests sets dummy env vars so `config.py` loads without a `.env` file.

### Writing new tests

```python
def test_something():
    llm = FakeLLM(['{"subject": "Hello", "body": "..."}'])
    queued = []

    agent = create_outreach_agent(
        llm=llm,
        fetch_ready_contacts=lambda limit: [{"id": 1, "name": "Gallery X", "city": "Munich"}],
        check_compliance=lambda id: True,
        queue_for_approval=lambda **kw: queued.append(kw) or 1,
        start_run=lambda *a: 1,
        finish_run=lambda *a: None,
        mission=DummyMission(),
    )

    result = agent.invoke({"limit": 1})
    assert result["queued_count"] == 1
    assert len(queued) == 1
```

### Integration tests (future)

When adding integration tests that need a real database, put them in `tests/integration/` and mark them:

```python
import pytest

@pytest.mark.integration
def test_save_contact_round_trip():
    ...
```

Run with: `uv run pytest tests/integration/ -v`
Exclude from default run by adding to `pyproject.toml`:
```toml
[tool.pytest.ini_options]
markers = ["integration: requires live database"]
addopts = "-m 'not integration'"
```

---

## LangGraph Checkpointer

The supervisor uses PostgreSQL as a state checkpointer (`langgraph-checkpoint-postgres`). On first run it creates the checkpoint tables automatically.

Each run uses `thread_id = "supervisor-YYYY-MM-DDTHH"`. A crash mid-run resumes from the last checkpoint when restarted within the same hour. A new hour starts fresh.

---

## File Layout (supervisor repo)

```
general-crm/
  gcrm/
    mission.py              Mission dataclass (frozen)
    vertical.py             Target-vertical config (edit to retarget)
    vertical_context.md     Narrative context injected into outreach drafts
    config.py               Active mission + all env config
    db/
      connection.py         db() context manager
      migrations/
        001_agent_tables.sql
    tools/
      db.py                 All database operations (contacts, compliance, interactions, runs)
      search.py             Overpass geo search + DuckDuckGo web search
      email.py              Proton Bridge SMTP send + IMAP read
      llm.py                LLM factory: deepseek-chat, deepseek-reasoner, claude
    supervisor/
      targets.py            Research target list
      graph.py              LangGraph supervisor with PostgreSQL checkpointer
      run.py                Entry point
    api/
      routers/
        approval.py         Approval queue + send-on-approve
        activity.py         Agent run feed
        contacts.py         Contact board
    ui/
      templates/            Jinja2 + HTMX
      static/style.css
    mcp/                    MCP server (optional Claude Code integration)
  agents/
    gcrm-research-agent/    LangGraph agent: finds contacts via Maps + web
    gcrm-enrichment-agent/  LangGraph agent: fills in missing emails/websites
    gcrm-scout-agent/       LangGraph agent: scores candidates for fit
    gcrm-outreach-agent/    LangGraph agent: drafts and queues emails
    gcrm-followup-agent/    LangGraph agent: inbox replies and follow-ups
  tests/
    conftest.py             Dummy env vars for test environment
    test_tools.py           DB tool unit tests (mocked)
    test_supervisor.py      Supervisor graph flow tests
  scripts/migrate.py
  RUNBOOK.md
  .env.example
```
