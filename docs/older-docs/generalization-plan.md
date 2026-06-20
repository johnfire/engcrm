# Generalization Plan — general-crm

## Goal

Create a new standalone project at `~/programming/general-crm/` — a vertical-agnostic copy of `artcrm-supervisor` and all its agent packages. Completely separate from the art-crm directory. The original `artcrm-supervisor` and all `artcrm-*-agent` packages are **not touched**. The `general-crm` version replaces all art-specific content with a user-configurable prompts/config layer — swap that layer and the entire system retargets to any B2B outreach vertical.

---

## What Changes (and What Doesn't)

**Does not change:**

- Pipeline architecture (research → enrich → scout → outreach → approval)
- LangGraph graph structure in all agents
- Database schema and migrations
- API / approval UI
- Tool implementations (search, email, db, llm)
- MCP server tool logic

**Changes:**

- All domain-specific text (prompts, search terms, level labels) moves into a single config layer
- Agent packages are copied and renamed to `gcrm_*` — originals left intact
- The `Mission` object becomes fully user-defined via a setup file
- A `setup.py` wizard guides first-time configuration

---

## New Directory Structure

```
~/programming/
├── art-crm/                          ← untouched, stays exactly as-is
│   ├── artcrm-supervisor/
│   ├── artcrm-research-agent/
│   ├── artcrm-enrichment-agent/
│   ├── artcrm-scout-agent/
│   ├── artcrm-outreach-agent/
│   └── artcrm-followup-agent/
│
└── general-crm/                      ← new standalone project
    ├── setup.py                      ← NEW: interactive setup wizard
    ├── gcrm/                         ← renamed from src/
    │   ├── config.py                 ← loads mission from vertical.py
    │   ├── vertical.py               ← NEW: THE FILE YOU SWAP TO CHANGE VERTICALS
    │   ├── prompts/                  ← NEW: all LLM prompt templates in one place
    │   │   ├── __init__.py
    │   │   ├── research.py           ← extract_contacts prompt + level descriptions
    │   │   ├── scout.py              ← scoring prompt + fit signals
    │   │   ├── outreach.py           ← draft_email prompt + opt-out lines
    │   │   └── enrichment.py         ← enrich_contact prompt (already generic)
    │   ├── supervisor/
    │   │   ├── graph.py
    │   │   ├── run.py
    │   │   ├── run_research.py
    │   │   └── targets.py            ← scan levels loaded from vertical.py
    │   ├── tools/                    ← unchanged
    │   ├── mcp/                      ← unchanged
    │   ├── api/                      ← unchanged
    │   ├── db/                       ← unchanged
    │   └── ui/                       ← unchanged
    └── agents/                       ← copies of artcrm agents, renamed
        ├── gcrm-research-agent/
        ├── gcrm-enrichment-agent/
        ├── gcrm-scout-agent/
        ├── gcrm-outreach-agent/
        └── gcrm-followup-agent/
```

---

## The Vertical File (`gcrm/vertical.py`)

This is the single file a user edits (or an AI rewrites) to change the system's focus. It contains everything domain-specific:

```python
# gcrm/vertical.py
# ─────────────────────────────────────────────────────────────
# SWAP THIS FILE TO CHANGE THE VERTICAL.
# Everything else in the system reads from here.
# ─────────────────────────────────────────────────────────────

# Who you are and what you're selling
IDENTITY = "Christopher Rehm, watercolor and oil painter based in Klosterlechfeld, Bavaria"
GOAL = "Find venues across Germany and Bavaria that display and sell original artwork, build relationships, and secure exhibition or sales opportunities."
WEBSITE = "https://artbychristopherrehm.com"

# What kinds of businesses you're targeting
TARGETS = "galleries, hotel lobbies, restaurants, corporate offices, cafes, cultural centres, museums, coworking spaces"

# What makes a contact a strong vs weak fit (used by scout agent for scoring)
FIT_CRITERIA = """
Strong fit: galleries showing regional, emerging, or mid-career artists; venues that sell work on
consignment or display art for atmosphere (hotels, restaurants, offices, cafes); interior designers
who source original art for clients; coworking spaces and concept stores with a design-conscious aesthetic.

Weak fit: galleries that exclusively represent internationally established or blue-chip artists;
venues with no visible interest in art or decor; purely commercial or chain businesses with no cultural angle.
"""

# Tone and style for outreach emails
OUTREACH_STYLE = "personal, artist-direct, warm but professional. Not commercial or templated — each message should feel handwritten."

# Default language for outreach ("de", "en", "fr", etc.)
LANGUAGE_DEFAULT = "de"

# Scout: what contact types get LLM scoring (others are auto-promoted to cold)
SCORED_TYPES = {"gallery"}

# Scout: positive signals to look for in website content
FIT_SIGNALS = [
    "shows emerging or regional artists",
    "rotating exhibitions",
    "open submissions or artist residencies",
    "consignment sales",
    "zeitgenössisch, regional, Nachwuchs, junge Kunst",
]

# Scout: negative signals (these contacts get dropped)
ANTI_SIGNALS = [
    "exclusively internationally established or blue-chip artists",
    "auction house style",
    "established masters only",
]

# Scan levels — what to search for at each depth
# Each level is a dict with a label and a list of Maps/search terms
SCAN_LEVELS = {
    1: {
        "label": "Galleries, Cafes, Interior Designers, Coworking",
        "maps_terms": ["Kunstgalerie", "Galerie", "Café", "Kaffeehaus", "Innenarchitekt", "Raumausstatter", "Coworking Space"],
        "web_queries": ["{city} Galerie zeitgenössische Kunst", "Kunstgalerie Innenarchitekt Coworking {city}"],
    },
    2: {
        "label": "Gift Shops, Esoteric, Concept Stores",
        "maps_terms": ["Geschenkeladen", "Esoterikladen", "Kristallladen", "Yoga Studio", "Concept Store", "Designladen", "Boutique"],
        "web_queries": ["Concept Store Esoterikladen Boutique {city}", "Geschenke Wellness Shop {city}"],
    },
    3: {
        "label": "Independent Restaurants",
        "maps_terms": ["Restaurant", "Gasthaus", "Bistro", "Weinrestaurant", "Gasthof"],
        "web_queries": ["bestes Restaurant {city}", "Restaurant Gasthaus {city} Empfehlung"],
    },
    4: {
        "label": "Corporate Offices & Headquarters",
        "maps_terms": ["Firmensitz", "Hauptverwaltung", "Bürogebäude", "Unternehmensberatung", "Technologieunternehmen"],
        "web_queries": ["größte Unternehmen {city} Kunst Büro", "Firmensitz Unternehmen Hauptverwaltung {city}"],
    },
    5: {
        "label": "Hotels",
        "maps_terms": ["Hotel", "Boutique Hotel", "Design Hotel", "Landhotel", "Stadthotel"],
        "web_queries": ["Design Hotel {city} Boutique", "Hotel Boutique Hotel {city}"],
    },
}
```

---

## The Prompts Directory (`gcrm/prompts/`)

Each file mirrors one agent's prompts but pulls all domain-specific text from `vertical.py` instead of hardcoding it.

### `prompts/research.py`

- Reads `SCAN_LEVELS` from vertical for level descriptions and search terms
- `extract_contacts_prompt(mission, city, level)` — unchanged logic, just imports from vertical

### `prompts/scout.py`

- Reads `FIT_SIGNALS`, `ANTI_SIGNALS`, `SCORED_TYPES` from vertical
- `score_contact_prompt(mission, contact, city_context)` — positive/negative signals injected from vertical
- `SCORED_TYPES` drives which contact types get LLM scoring vs. auto-promotion

### `prompts/outreach.py`

- Reads `OUTREACH_STYLE`, `LANGUAGE_DEFAULT`, `WEBSITE` from vertical
- `draft_email_prompt(mission, contact, interactions, website_content)` — unchanged logic

### `prompts/enrichment.py`

- Already generic — no changes needed, just moved here for consistency

---

## Setup Wizard (`setup.py`)

A simple CLI that walks a new user through filling out `vertical.py`. Outputs a ready-to-use file.

```
$ python setup.py

Welcome to general-crm setup.

Who are you / what is your business? > Acme Coffee Equipment GmbH, B2B coffee machine distributor
What is your goal? > Find independent cafes and restaurants in Germany to pitch our espresso machines
What types of businesses are you targeting? > cafes, restaurants, hotels, coworking spaces, corporate offices
What makes a strong fit? > ...
...

Writing vertical.py... done.
Run: uv run python -m gcrm.supervisor.run
```

The wizard can also be replaced by an AI rewriting `vertical.py` directly — the file is intentionally readable and self-documenting.

---

## Step-by-Step Implementation

### Phase 1 — Copy and Rename

1. Copy `~/programming/art-crm/artcrm-supervisor/` → `~/programming/general-crm/`
2. Copy all `~/programming/art-crm/artcrm-*-agent/` packages into `~/programming/general-crm/agents/gcrm-*-agent/` — originals stay untouched
3. Rename Python packages inside the copies: `artcrm_*_agent` → `gcrm_*_agent`
4. Rename `src/` → `gcrm/`
5. Update all internal imports in the copies only

### Phase 2 — Create `vertical.py`

6. Create `gcrm/vertical.py` with all art-specific content extracted from:
   - `config.py` (Mission fields)
   - `supervisor/targets.py` (SCAN_LEVELS + maps_terms)
   - `agents/gcrm-research-agent/prompts.py` (LEVEL_DESCRIPTIONS, web queries)
   - `agents/gcrm-scout-agent/prompts.py` (fit/anti signals, GALLERY_TYPES)
7. Update `config.py` to build Mission from `vertical.py` fields

### Phase 3 — Create `prompts/` Directory

8. Create `gcrm/prompts/` with one file per agent
9. Move prompt functions out of agent packages into `gcrm/prompts/`
10. Agent packages import prompts from `gcrm.prompts` instead of their own `prompts.py`
11. All domain-specific strings in prompts are replaced with variables from `vertical.py`

### Phase 4 — Wire Targets to Vertical

12. Update `supervisor/targets.py` to load `SCAN_LEVELS` from `vertical.py`
13. Update research agent `graph.py` to load `LEVEL_TERMS` and web queries from vertical
14. Update MCP server `LEVEL_LABELS` to read from vertical

### Phase 5 — Setup Wizard

15. Write `setup.py` — interactive CLI that generates `vertical.py`
16. Add a `vertical.example.py` with a non-art example (e.g. coffee equipment distributor)

### Phase 6 — Validation

17. Run the full pipeline with the art vertical (should produce identical results to artcrm-supervisor)
18. Swap in a test vertical, run again, verify the system retargets correctly

---

## Files Changed Per Agent Package

| Package                 | Changes                                                                                              |
| ----------------------- | ---------------------------------------------------------------------------------------------------- |
| `gcrm-research-agent`   | Import prompts from `gcrm.prompts.research`; remove own `prompts.py`; load LEVEL_TERMS from vertical |
| `gcrm-scout-agent`      | Import prompts from `gcrm.prompts.scout`; load SCORED_TYPES from vertical                            |
| `gcrm-outreach-agent`   | Import prompts from `gcrm.prompts.outreach`; no logic changes                                        |
| `gcrm-enrichment-agent` | Import prompts from `gcrm.prompts.enrichment`; no logic changes                                      |
| `gcrm-followup-agent`   | Import prompts from `gcrm.prompts.outreach` (follow-up section); no logic changes                    |

---

## Effort Estimate

| Phase                     | Effort                                               |
| ------------------------- | ---------------------------------------------------- |
| Copy + rename             | Small — mostly mechanical find/replace               |
| Create vertical.py        | Small — extracting existing strings                  |
| Create prompts/ directory | Medium — refactoring imports across 5 agent packages |
| Wire targets to vertical  | Small                                                |
| Setup wizard              | Medium — new code, but straightforward               |
| Validation                | Small — run it and compare output                    |

Total: a focused day of work, maybe two if prompt wiring needs tuning.
