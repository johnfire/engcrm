# general-crm

> I will be happy to help anyone set this up for their personal use case — feel free to open an issue or reach out.

An autonomous AI agent system for B2B outreach. It finds businesses in your target market, researches them, scores them for fit, drafts personalised emails, and manages follow-ups — all without a traditional CRM interface. You talk to Claude, Claude talks to the system.

Swap one config file to retarget the entire system to any vertical: art galleries, cafes, distributors, law firms, whatever you're selling to.

---

## What It Does

The system runs a full outreach pipeline:

```
Research → Enrich → Scout → Outreach → Follow-up
```

1. **Research** — Uses Google Maps (Places API) to find every relevant business in a city. Supplements with web search and page fetching to extract contact details. Cities are organised by scan level so you can start shallow and go deeper when needed.

2. **Enrich** — For every contact missing a website or email, searches the web and uses an LLM to fill in the gaps. Runs automatically on each pipeline invocation.

3. **Scout** — Scores each new contact for mission fit. Contacts above a configurable threshold are promoted to outreach. Below it, they're dropped with a reason saved so you can review. Your `vertical.py` defines what signals make a good or bad fit.

4. **Outreach** — Drafts a personalised first-contact email for each contact ready to be reached. Each draft goes into an approval queue — you review and send, or reject. Nothing is sent without a human in the loop.

5. **Follow-up** — Reads the inbox, classifies replies (interested / rejected / opt-out), and drafts follow-up emails for contacts that haven't responded in 90+ days.

All of this runs on demand. You approve emails and trigger scans through conversation with Claude — no dashboard required beyond a minimal web UI for approvals.

---

## Architecture

```
general-crm/
  gcrm/
    vertical.py          ← THE FILE YOU EDIT TO CHANGE THE TARGET VERTICAL
    vertical_context.md  ← Rich narrative context injected into outreach emails
    mission.py           Mission dataclass
    config.py            Loads mission from vertical.py + vertical_context.md
    prompts/             LLM prompt templates (read from vertical.py)
    supervisor/          LangGraph orchestrator
    tools/               DB, search, email, LLM
    api/                 FastAPI + HTMX approval UI
    mcp/                 MCP server (optional Claude Code integration)
    db/                  Migrations
  agents/
    gcrm-research-agent/ LangGraph agent: finds contacts via Maps + web search
    gcrm-scout-agent/    LangGraph agent: scores candidates for fit
    gcrm-enrichment-agent/ LangGraph agent: fills in missing emails/websites
    gcrm-outreach-agent/ LangGraph agent: drafts and queues first-contact emails
    gcrm-followup-agent/ LangGraph agent: handles inbox replies and follow-ups
  setup.py               Basic CLI wizard (fallback — see Setup below)
```

---

## Prerequisites

- **Python 3.11+** and [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **PostgreSQL** running locally (any recent version)
- **Google Maps API key** with Places API enabled ([get one here](https://developers.google.com/maps/documentation/places/web-service/get-api-key))
- **DeepSeek API key** for routine tasks (research, enrichment, scouting) — cheap and fast
- **Anthropic API key** for high-stakes writing (outreach drafts, follow-ups)
- **Proton Bridge** running locally if you want email send/receive via ProtonMail — otherwise email is disabled and you copy drafts manually
- `~/logs/` directory: `mkdir -p ~/logs`

---

## Setup

### 1. Clone and install

```bash
git clone <repo-url> general-crm
cd general-crm
uv sync --extra agents --extra dev
```

### 2. Configure your vertical

The recommended way is the AI-powered setup interview in Claude Code. Open the project in a Claude Code session and run:

```
/setup-gcrm
```

Claude will interview you in conversation — asking about your business, your offer, the types of businesses you want to reach, what makes a good or bad fit, and how you want to come across in emails. You don't need to know anything about Google Maps search terms or config formats; Claude figures those out from what you tell it.

At the end of the interview, Claude writes two files:

- **`gcrm/vertical.py`** — the machine-readable config: search terms, scoring signals, language, scan levels. Everything the agents need to run.
- **`gcrm/vertical_context.md`** — a rich narrative document describing your business, your offer, why each target type should care, and what angles work per venue. The outreach agent reads this when drafting emails, making them significantly more specific and personal than a config file alone could achieve.

You can edit either file directly at any time. Re-run `/setup-gcrm` to redo the interview from scratch.

**No Claude Code?** Use the basic CLI wizard instead:

```bash
uv run python setup.py
```

This generates `gcrm/vertical.py` only (no context document). You can write `gcrm/vertical_context.md` manually afterwards — see the [Vertical Context](#vertical-context) section for the expected format.

### 3. Set up environment variables

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Database
DATABASE_URL=postgresql://user:password@localhost/mydb

# AI — at minimum one of these is required
DEEPSEEK_API_KEY=your_deepseek_key
ANTHROPIC_API_KEY=your_anthropic_key

# Google Maps (required for research agent)
GOOGLE_MAPS_API_KEY=your_maps_key

# Email via Proton Bridge (optional — set EMAIL_ENABLED=false to disable)
PROTON_IMAP_HOST=127.0.0.1
PROTON_IMAP_PORT=1143
PROTON_SMTP_HOST=127.0.0.1
PROTON_SMTP_PORT=1025
PROTON_EMAIL=your@proton.me
PROTON_PASSWORD=bridge_app_password
PROTON_FROM_EMAIL=alias@proton.me   # optional alias

# Server
HOST=127.0.0.1
PORT=8000

# Scout threshold: contacts below this score are dropped (default 75)
SCOUT_THRESHOLD=75

# Set false to skip email sending (drafts are still created and saved)
EMAIL_ENABLED=true

# LLM for cheap/high-volume tasks: deepseek-chat or claude-haiku
CHEAP_LLM=deepseek-chat
```

**Minimum to get started:** `DATABASE_URL`, `DEEPSEEK_API_KEY` or `ANTHROPIC_API_KEY`, `GOOGLE_MAPS_API_KEY`.

### 4. Create the database

Create a PostgreSQL database, then run all migrations:

```bash
createdb mydb   # or use your GUI
uv run python scripts/migrate.py
```

This creates the tables: `contacts`, `interactions`, `agent_runs`, `consent_log`, `approval_queue`, `inbox_messages`, `cities`, `city_scans`, and `city_market_context`.

### 5. Add cities to research

The system needs to know which cities to scan. Add them to the `cities` table:

```sql
INSERT INTO cities (city, country, region) VALUES
  ('Munich', 'DE', 'Bavaria'),
  ('Augsburg', 'DE', 'Bavaria'),
  ('Vienna', 'AT', 'Austria');
```

Or use the MCP tool `run_research` if you have the MCP server configured.

### 6. Start the UI

```bash
uv run python -m gcrm.api.main
# → http://127.0.0.1:8000
```

---

## Running the Pipeline

### Full run

```bash
uv run python -m gcrm.supervisor.run
```

This runs all agents in sequence: research → enrich → scout → outreach → followup. Logs to `~/logs/supervisor.log` and the `/activity/` UI page.

Research jobs come from the `cities` table (any city with unscanned levels). To skip research and only run scout/outreach/followup, clear the city scan queue or set all levels to already-scanned.

### Research a specific city

```bash
uv run python -m gcrm.supervisor.run_research --city Munich --level 1
uv run python -m gcrm.supervisor.run_research --city Vienna --level 2 --country AT
```

Levels are defined in `gcrm/vertical.py` under `SCAN_LEVELS`. Run level 1 before any others (it's enforced).

### Schedule with cron

```cron
0 7 * * * cd /path/to/general-crm && /home/you/.local/bin/uv run python -m gcrm.supervisor.run >> /home/you/logs/supervisor.log 2>&1
```

---

## The Approval Queue

Nothing gets sent without your sign-off. After each run, go to `http://127.0.0.1:8000/approvals/` to review drafted emails:

- **Approve** — sends immediately via SMTP, logs the interaction, marks contact as `contacted`
- **Edit + Approve** — edit subject/body inline, then send
- **Reject** — discards the draft; contact stays `cold` and will be re-drafted next run

If Proton Bridge isn't running, approved emails are marked `approved_unsent` rather than failing.

---

## The UI Pages

| Page           | URL           | What it shows                                      |
| -------------- | ------------- | -------------------------------------------------- |
| Approval Queue | `/approvals/` | Email drafts waiting for review                    |
| Contacts       | `/contacts/`  | All contacts with status filter and search         |
| Research       | `/research/`  | Cities and scan levels with email counts per level |
| Activity       | `/activity/`  | Agent run log with status, duration, summary       |

---

## Contact Pipeline

```
cities table → research_agent → status=candidate
                                     ↓
                             scout_agent → status=cold  (fit score ≥ threshold)
                                       → status=dropped (fit score < threshold)
                                             ↓
                             outreach_agent → approval_queue (pending)
                                                   ↓
                                          YOU approve at /approvals/
                                                   ↓
                                          email sent → status=contacted
                                                   ↓
                             followup_agent (next run):
                               ├── reply: interested → drafts reply, logs
                               ├── reply: rejected   → logs, no further action
                               ├── reply: opt_out    → consent_log updated, never contacted again
                               └── no reply (90+ days) → drafts brief follow-up
```

---

## Vertical Context

`gcrm/vertical_context.md` is a free-form markdown document that gets injected verbatim into the outreach agent's system prompt. It makes a noticeable difference to email quality — the LLM has real context to draw on instead of just a config file.

The document has no strict format, but the `/setup-gcrm` interview generates it with these sections:

- **Who You Are** — name, background, what you do and why
- **What You Offer** — the substance of what you're bringing to each contact
- **Why They Should Care** — the value proposition per target type
- **Per Business Type** — specific angles, hooks, and things to mention for each category
- **What to Avoid** — tone mistakes, red flags, things that don't land
- **Credentials & Details** — real specifics: past work, clients, publications, portfolio links

The file is optional — the system degrades gracefully if it doesn't exist. But better context = better emails.

---

## Changing the Vertical

Edit `gcrm/vertical.py`. The entire system re-targets automatically — no other changes needed.

Key fields to change:

```python
IDENTITY = "Acme Coffee GmbH, B2B espresso machine distributor in Munich"
GOAL = "Find independent cafes and restaurants across Germany to pitch our machines"
TARGETS = "cafes, restaurants, hotels, coworking spaces"

FIT_SIGNALS = ["specialty coffee", "espresso bar", "owner-operated"]
ANTI_SIGNALS = ["chain", "franchise", "vending machine"]

SCORED_TYPES = {"cafe"}   # types that get LLM scoring; others auto-promoted

SCAN_LEVELS = {
    1: {
        "label": "Specialty Cafes & Coffee Shops",
        "maps_terms": ["Café", "Kaffeehaus", "Specialty Coffee", "Coffee Shop"],
        "web_queries": ["specialty coffee {city}", "Kaffeehaus espresso {city}"],
    },
    2: {
        "label": "Restaurants & Hotels",
        "maps_terms": ["Restaurant", "Hotel", "Bistro"],
        "web_queries": ["Restaurant {city} Empfehlung", "Boutique Hotel {city}"],
    },
}
```

`web_queries` support `{city}` as a placeholder — the research agent substitutes the current city at runtime. If omitted, the agent builds a fallback query from `maps_terms` automatically.

Or re-run the interview: `/setup-gcrm` in Claude Code

---

## Scout Threshold

Controls outreach volume. Lower = more contacts promoted, higher = stricter filtering.

```env
SCOUT_THRESHOLD=75   # strict — best fits only
SCOUT_THRESHOLD=60   # moderate
SCOUT_THRESHOLD=50   # wide net
```

Only contact types listed in `SCORED_TYPES` get LLM evaluation. All other types are auto-promoted at a neutral score — useful for venue types where you want to contact everyone regardless.

---

## LLM Backends

| Backend             | Used for                                      | Cost           |
| ------------------- | --------------------------------------------- | -------------- |
| `deepseek-chat`     | Research, enrichment, scouting                | Very cheap     |
| `claude-sonnet-4-6` | Outreach drafts, follow-ups                   | Higher quality |
| `claude-haiku`      | Cheap Anthropic alternative for routine tasks | Cheap          |

Set `CHEAP_LLM=deepseek-chat` or `CHEAP_LLM=claude-haiku` in `.env`. High-stakes writing always uses Claude Sonnet.

You only need keys for backends you use. DeepSeek alone is sufficient for a full run — outreach quality will be lower but functional.

---

## MCP Server (optional)

If you use Claude Code, you can control the system from a conversation without touching the UI.

```bash
uv run python -m gcrm.mcp.server
```

Available tools: `pipeline_status`, `contacts_list`, `approval_list`, `approval_approve`, `approval_reject`, `agent_runs`, `manual_drop`, `manual_promote`, `run_research`, `trigger_run`, `set_city_notes`, `research_status`.

To configure as a persistent MCP server in Claude Code, add it to your `~/.claude/settings.json`.

---

## GDPR / Compliance

The system has a built-in compliance layer. Before drafting any email, the outreach agent calls `check_compliance()` which blocks:

- Contacts who have opted out (replied "unsubscribe" or equivalent)
- Contacts whose data has been erased
- Contacts with `status=do_not_contact`

Opt-out detection is automatic — the followup agent classifies incoming replies and sets the flag without human intervention. All consent events are logged to `consent_log`.

---

## Tests

```bash
uv run pytest
```

All tests run without external dependencies — LLM calls are mocked, DB is mocked. 12 tests covering tool logic and supervisor routing.

To also run agent package tests:

```bash
for agent in research scout enrichment outreach followup; do
    echo "=== gcrm-${agent}-agent ===" && uv run pytest agents/gcrm-${agent}-agent/tests/ -v
done
```

---

## Support

If you find this useful, a small donation helps keep projects like this going:

[Donate via PayPal](https://paypal.me/christopherrehm001)
