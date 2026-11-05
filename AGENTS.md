# gcrm Agents — How They Work

> **Note:** Paths, module names (`gcrm.supervisor.run`), and config locations (`gcrm/…`) have been refreshed to the generalized `gcrm` layout. The prose below still carries the original `theo-hits-the-road` two-system framing (separate "original CRM" + supervisor); a deeper narrative rewrite to reflect the self-contained `general-crm` is recommended. See README.md for the current overview.

This document explains all six agents in the gcrm system, how they interact, and how the whole thing relates to `theo-hits-the-road`.

---

## The foundation: theo-hits-the-road

`theo-hits-the-road` is the original CRM. It owns the database schema — specifically the `contacts`, `interactions`, and `shows` tables — and provides a CLI and MCP server for managing them by hand. It is never modified by the agent system and always works as a standalone fallback.

`gcrm supervisor` adds four new tables to the same PostgreSQL database (`agent_runs`, `consent_log`, `approval_queue`, `inbox_messages`) and then automates the top of the contact funnel: finding leads, qualifying them, and initiating outreach. The two systems share data but do not depend on each other's code.

---

## The six agents

### 1. Supervisor (gcrm supervisor)

**What it is:** The orchestrator. Not really an "agent" itself — it's a LangGraph `StateGraph` that runs the five worker agents in sequence.

**Run order:**

```
research → enrich → scout → outreach → followup
```

**How it works:**

- Starts a run record in `agent_runs`
- Calls each worker agent in order, passing the active `Mission` and concrete tool implementations
- Each worker gets injected tools (DB functions, email, search) — the agents themselves have no direct imports from this repo
- Collects a summary from each worker and writes a final report to `agent_runs`
- Uses PostgreSQL as a LangGraph checkpointer: if a run crashes mid-way, it resumes from the last checkpoint when restarted within the same hour

**The human checkpoint** is the approval queue. The supervisor never sends a first-contact email on its own — it stops at drafting and waits for you to approve at `/approvals/`.

**Configuration knobs:**

- `ACTIVE_MISSION` in `gcrm/config.py` — what the agents are working toward, including `website` for email sign-offs
- `SCAN_LEVELS` in `gcrm/supervisor/targets.py` — Google Maps search terms per scan level
- `EMAIL_ENABLED` in `.env` — set to `false` to disable all outgoing email globally
- `MAIL_FROM_EMAIL` in `.env` — the From address on outgoing emails (can differ from the SMTP login address, e.g. an alias)

---

### 2. Research Agent (gcrm-research-agent)

**What it does:** Finds new potential contacts for a given city + level combination and saves them to the database at the `candidate` stage.

**Inputs:** `city`, `country`, `level` (1–10)

**Scan levels** (defined in `gcrm/vertical.py`; every level aims at companies of 50–5,000 employees, sweet spot 500–2,500 — the scout enforces the size):

| Level | What it finds |
| ----- | ------------- |
| 1     | Larger trade contractors — Gebäudetechnik, TGA, Elektrotechnik, Anlagenbau, Industriemontage |
| 2     | Manufacturers & suppliers with their own production — Maschinenbau, metal/plastics processing, electronics, Werkzeugbau, Automobilzulieferer |
| 3     | Contract logistics & Spedition — firms that transport for other firms |
| 4     | Food & drink producers — breweries, dairies, cheese makers, wineries, meat/bakery/confectionery manufacturers (no shops) |
| 5     | Construction companies — Bauunternehmen, Generalunternehmer, Hoch-/Tief-/Straßenbau |
| 6     | Agricultural business — Landtechnik, Agrarhandel, Raiffeisen, feed and seed producers |
| 7     | Clinics, hospitals, MVZ, medical labs |
| 8     | Professional services & company headquarters — tax, law, engineering, architecture, chain HQs |
| 9     | Academia — universities, Fachhochschulen, research institutes |
| 10    | Defence, security & strategic consulting |

The research step labels every hit with one type from `BUYER_TYPES` or `NOT_A_BUYER_TYPES`. Shops and small services (butcher, bakery, cafe, car dealer, …) are never saved.

**Steps inside the agent:**

1. **run_maps_search** — runs fixed German-language search terms for the level against the Google Maps Places API. Returns name, address, website, phone directly from Maps data. Deduplicates by name.
2. **run_web_search** — two targeted DuckDuckGo queries per level to supplement Maps data and catch companies Maps might miss.
3. **fetch_pages** — visits the top 3 URLs found, strips HTML to plain text, feeds the content to the extraction LLM. This is how emails, contact names and size signals get extracted from the companies' own websites.
4. **extract_contacts** — LLM parses all raw results into structured contact records with a type from the fixed list, and writes 2–3 sentence notes including size signals. Hits typed as not a buyer are left out here.
5. **save_contacts** — writes each contact to `contacts` at the `candidate` stage, raising `research_exhausted` for businesses with no web presence. Deduplication key is `(name, city)` so re-runs are safe.

**LLM:** `CHEAP_LLM` env var (deepseek-chat or claude-haiku) — this is volume work.

**Output:** contacts in the database at the `candidate` stage

**City registry:** Every city scanned is tracked in the `cities` and `city_scans` tables — what level was run, when, and how many contacts were found. Visible at `/research/`.

---

### 3. Enrichment Agent (gcrm-enrichment-agent)

**What it does:** Fills in missing contact details — website, email, phone — for contacts that came back from research without them. Runs automatically between research and scout on every pipeline invocation.

**Inputs:** `limit` (how many contacts to process per run, default 50)

**Why it exists:** The Google Maps Places API returns business names, addresses, and often a website and phone number — but email addresses are rarely in Maps data. The enrichment agent searches the web for each contact and extracts whatever it finds from search snippets.

**Steps inside the agent:**

1. **fetch** — pulls contacts where `website` is missing OR `email` is missing, ordered by `created_at`. Skips contacts that already have both.
2. **enrich_all** — for each contact:
   - Builds a search query: `"{name} {city} website email contact"`
   - Runs it through DuckDuckGo web search
   - Asks the LLM to extract website URL, email address, and phone number from the search snippets
3. **apply_results** — writes whatever was found back to the contact record. Partial updates are fine — if only an email was found, only the email gets written.

**LLM:** `CHEAP_LLM` env var (deepseek-chat or claude-haiku)

**Output:** contacts updated with website/email/phone where found. No status change — enrichment doesn't promote or drop anyone.

**Note:** Enrichment doesn't fetch pages — it only reads search snippets. The research agent already fetched pages during discovery. The scout agent fetches each company's website again during evaluation (for a fuller read).

---

### 4. Scout Agent (gcrm-scout-agent)

**What it does:** Evaluates every `candidate` contact and decides whether to pursue them.

**Inputs:** `limit` (how many candidates to process per run)

**The key idea:** the scout decides whether a machine-found company is an AI-consulting buyer of the right size. The LLM judges the business; code applies the size rule, because the LLM misreads thresholds (it once called 4,000 employees "over 5,000").

**Steps inside the agent:**

1. **fetch** — pulls all contacts at the `candidate` stage (LinkedIn imports only when asked for)
2. **split_and_promote** — routes each candidate:
   - **Entered by hand** (business cards, field visits, manual entries, your Maps list) → `suspect` / `ready` with no LLM call. Those are your call, not the scout's.
   - **Not a buyer** (type in `NOT_A_BUYER_TYPES`: butcher, cafe, car dealer, …) → `not_in_pipeline` / `dropped` with no LLM call.
   - **Everything else** (scan hits, research-agent finds, LinkedIn employers) → scored below.
3. **fetch_scored_websites** — fetches each company's website (up to 4,000 characters). No website still proceeds on the notes.
4. **score_candidates** — the LLM returns `outcome` (fit / unsure / no_fit, judged on everything except size), `employees` (a head count the site states, or null) and `size_band` (its estimate when no number is stated).
5. **apply_scores** — code combines them: a stated head count wins over the band; under 50 or over 5,000 is `no_fit` whatever the LLM said. Fit scores: 85 in the 500–2,500 sweet spot, 75 elsewhere in range, 65 when size is unknown; unsure 50; no fit 20.

**LLM:** `CHEAP_LLM` env var

**What the LLM looks for:** own production, warehouse, fleet or construction crews; manual steps, spreadsheets, paper or an underused ERP; several sites, shift work, ISO 9001; research groups needing tooling; defence/security analysis work. Negative: shops and branch outlets, one-person businesses, software/IT companies, agencies, startups.

**City market context:** the city's `market_character` from the `cities` table is passed to the LLM as background.

**Output:** contacts moved to `suspect`/`ready`, left at `candidate` for review, or moved to `not_in_pipeline`/`dropped`. The size and the scout's reasoning are written into the contact's notes field.

---

### 5. Outreach Agent (gcrm-outreach-agent)

**What it does:** Researches each company, drafts a personalized first-contact email, and puts it in the approval queue. Does not send anything.

**Inputs:** `limit` (how many cold contacts to draft for per run — default is 1 for controlled rollout)

**Steps inside the agent:**

1. **fetch** — pulls contacts where `status=ready`, excluding any carrying a suppression flag
2. **draft_all** — for each contact:
   - Checks GDPR compliance first (hard block if `opt_out` or `erasure_requested` is set in `consent_log`)
   - Fetches the company's website and reads up to 3000 characters of content
   - Fetches the full interaction history for this contact
   - Asks the LLM to write a first-contact email using all of this: research notes, scout reasoning, website content, and past interactions
3. **queue_drafts** — inserts drafts into `approval_queue` with `status=pending`

**LLM:** Claude Sonnet — quality matters here, this is the email a human reads.

**What the LLM is told to do:**

- Reference something specific about the company from the notes or website — no generic openers
- Introduce Christopher briefly and naturally
- Express genuine interest in this specific space
- Propose one concrete next step (visit, call, or portfolio)
- Keep it short — 4 to 6 sentences

**Output:** rows in `approval_queue` waiting for human review at `/approvals/`

**What happens after you approve:**

- Email is sent via SMTP (if `EMAIL_ENABLED=true`)
- An interaction is logged in `interactions`
- Contact moves to `status=contacted`

---

### 6. Follow-up Agent (gcrm-followup-agent)

> **Currently disabled.** The supervisor short-circuits this agent and returns immediately. All follow-up is handled manually while patterns are established.

**What it does (when enabled):** Handles everything that happens after the first email has been sent. Two work streams per run.

**Work stream 1 — Inbox replies:**

1. **fetch_inbox_messages** — reads unprocessed messages from IMAP
2. **classify_replies** — for each message, finds the matching contact by email address
   - Messages with no matching contact are skipped and marked processed (no LLM call)
   - Classifies as: `interested`, `rejected`, `opt_out`, `other`
   - `opt_out`: immediately sets the flag in `consent_log` and moves contact to `status=dormant` — never contacted again
   - `interested`: drafts a warm reply and **sends it directly** (time-sensitive, bypasses approval queue)
   - `rejected` / `other`: logs the interaction, no further action
3. Marks each inbox message as processed

**Work stream 2 — Overdue contacts:**

1. **fetch_overdue_contacts** — finds contacts with `status=contacted` who haven't had an interaction in 90+ days
2. **draft_followup_emails** — drafts a brief follow-up for each, referencing the original outreach subject line
3. Puts drafts in the **approval queue** (not sent directly — human reviews first)

**LLM:** Claude Sonnet (writing quality matters for both replies and follow-ups)

---

## Contact status flow

```
[research_agent]
      ↓
  candidate
      ↓
[enrichment_agent]  ← fills in website/email/phone, no status change
      ↓
[scout_agent]
    ↙   ↓   ↘
  cold maybe dropped
    ↓
[outreach_agent → you approve]
      ↓
  contacted
      ↓
[followup_agent]
    ↙         ↘
(stays       dormant  ← opt-out received
contacted)
```

Organizations the scout was unsure about stay at the `candidate` stage until you review them. Use `manual_promote` or `manual_drop` MCP tools, or review them at `/organizations/?stage=candidate`.

---

## How the agents are wired together

The five worker agents are **tool-agnostic**. Each one defines its dependencies as Python Protocols (type-checked interfaces) and accepts them as constructor arguments. This means:

- The agents contain no database imports, no email imports, no config imports
- The supervisor injects concrete implementations at startup
- Tests inject fakes — no real DB, no real LLM, no real SMTP needed

The run scripts in `gcrm/supervisor/` (`run_gather.py`, `run_judge.py`, and the per-agent `run_*.py` they call) are the only place that knows about the actual infrastructure.

---

## At a glance

| Agent      | Reads from DB                            | Writes to DB                     | LLM           | Sends email                     |
| ---------- | ---------------------------------------- | -------------------------------- | ------------- | ------------------------------- |
| Supervisor | —                                        | `agent_runs`                     | —             | —                               |
| Research   | —                                        | `contacts` (candidate)           | CHEAP_LLM     | —                               |
| Enrichment | `contacts` (missing website/email)       | `contacts` (website/email/phone) | CHEAP_LLM     | —                               |
| Scout      | `contacts` (candidate)                   | `contacts` (cold/maybe/dropped)  | CHEAP_LLM     | —                               |
| Outreach   | `contacts` (cold)                        | `approval_queue`                 | Claude Sonnet | —                               |
| Follow-up  | `inbox_messages`, `contacts` (contacted) | `interactions`, `consent_log`    | Claude Sonnet | Replies only (disabled for now) |

---

## Running manually vs. on schedule

**Gather, Judge, Outreach** (separate runs, started by hand):

```bash
uv run python -m gcrm.supervisor.run_gather --city Untermeitingen --level 2
uv run python -m gcrm.supervisor.run_judge
```

**Research only (single city + level):**

```bash
uv run python -m gcrm.supervisor.run_research --city Konstanz --level 1
uv run python -m gcrm.supervisor.run_research --city Innsbruck --level 1 --country AT
```

**Individual agent (for debugging):**
Each agent package exposes a `create_*_agent()` factory. You can instantiate and invoke them directly — see the test files for examples.

**Scheduled:** nothing. Every run is started by hand (decision 2026-11-05).

---

## MCP tools (manual operations)

The FastMCP server exposes tools for operating the CRM from Claude Code directly, without running the full pipeline.

**Contact management:**

| Tool                               | What it does                             |
| ---------------------------------- | ---------------------------------------- |
| `contact_search`                   | Search by name, city, status             |
| `contact_get`                      | Full contact record                      |
| `contact_update`                   | Edit any field                           |
| `manual_drop(contact_id, reason)`  | Move to not_in_pipeline / dropped and log the reason |
| `manual_promote(contact_id, note)` | Move to suspect / ready (into the outreach queue) |

**City context:**

| Tool                                              | What it does                                                                        |
| ------------------------------------------------- | ----------------------------------------------------------------------------------- |
| `set_city_notes(city, notes, character, country)` | Set market_character (tourist/mixed/upscale/unknown) and free-text notes for a city |

**Outreach:**

| Tool                               | What it does                                                    |
| ---------------------------------- | --------------------------------------------------------------- |
| `draft_first_contact(contact_id)`  | Draft an email for one contact and put it in the approval queue |
| `scout_city(city, country, level)` | Run research + scout for a city directly                        |

**City characters pre-seeded:** Landsberg, Konstanz, Friedrichshafen, Lindau, Garmisch-Partenkirchen, Rosenheim → `tourist`. Munich, Zurich, Basel → `upscale`. Augsburg, Heidelberg, Tübingen → `mixed`.
