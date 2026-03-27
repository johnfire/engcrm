# artcrm-scout-agent

LangGraph agent that evaluates candidate contacts and decides whether to pursue them. Galleries get deep research; everything else is auto-promoted.

## What it does

Fetches all contacts with `status=candidate` and splits them by type:

- **Non-galleries** (cafes, hotels, restaurants, coworking, interior designers, etc.) → promoted directly to `status=cold` with no LLM call
- **Galleries** → fetches the gallery website and evaluates whether they show emerging/regional artists

Gallery outcomes:

- `cold` — shows emerging, regional, or mid-career artists — worth contacting
- `maybe` — website unclear, too thin, or mixed signals — flagged for manual review
- `dropped` — exclusively blue-chip / internationally established — not a fit

## City market context

The scout reads the city's `market_character` (tourist / mixed / upscale / unknown) and adjusts evaluation accordingly. A gallery in a tourist town (Landsberg, Konstanz) gets more benefit of the doubt than one in an upscale city (Munich, Zurich). Set via `set_city_notes` MCP tool or migration seed data.

## Usage

```python
from artcrm_scout_agent import create_scout_agent

agent = create_scout_agent(
    llm=your_llm,
    fetch_candidates=your_fetch_fn,
    update_contact=your_update_fn,
    fetch_page=your_fetch_page_fn,
    fetch_city_context=your_city_context_fn,
    start_run=your_start_run_fn,
    finish_run=your_finish_run_fn,
    mission=your_mission,
)

result = agent.invoke({"limit": 50})
print(result["summary"])
# "scout_agent: 12 non-galleries auto-promoted, 5 galleries evaluated — 3 cold, 1 maybe, 1 dropped"
```

## Protocols

All dependencies are injected. Each callable must match the Protocol defined in [protocols.py](artcrm_scout_agent/protocols.py):

| Parameter            | Protocol             | Description                                                 |
| -------------------- | -------------------- | ----------------------------------------------------------- |
| `llm`                | `LanguageModel`      | Any LangChain `BaseChatModel`                               |
| `fetch_candidates`   | `CandidateFetcher`   | `(limit: int) -> list[dict]`                                |
| `update_contact`     | `ContactUpdater`     | `(contact_id, status, fit_score, notes) -> None`            |
| `fetch_page`         | `PageFetcher`        | `(url: str) -> str` — returns plain-text page content       |
| `fetch_city_context` | `CityContextFetcher` | `(city, country) -> dict` — market_character + market_notes |
| `start_run`          | `RunStarter`         | `(agent_name, input_data) -> int`                           |
| `finish_run`         | `RunFinisher`        | `(run_id, status, summary, output_data) -> None`            |
| `mission`            | `AgentMission`       | Any object with the mission fields                          |

## Testing

```bash
uv run pytest -v
```

## Support

If you find this useful, a small donation helps keep projects like this going:
[Donate via PayPal](https://paypal.me/christopherrehm001)
