# artcrm-outreach-agent

LangGraph agent that researches venues, drafts personalized first-contact emails, and queues them for human approval. Nothing is sent until a human approves via the UI.

## What it does

Fetches contacts with `status=cold`, then for each:

1. GDPR compliance check — hard block if opt-out or erasure flag is set
2. Fetches the venue's website and reads the content
3. Fetches the contact's full interaction history
4. Drafts a personalized first-contact email — using the research notes, scout reasoning, website content, and past interactions to write something specific to this venue
5. Inserts the draft into the approval queue

The human sees the draft in the browser UI, can approve/edit/reject it, and the email is sent on approval.

## What makes a good draft

The LLM is instructed to:

- Reference something specific about the venue from the notes or website — no generic openers
- Introduce Christopher briefly and naturally
- Express genuine interest in this specific space
- Propose one concrete next step (visit, call, or portfolio)
- Keep it short — 4 to 6 sentences

## Usage

```python
from artcrm_outreach_agent import create_outreach_agent

agent = create_outreach_agent(
    llm=your_llm,
    fetch_ready_contacts=your_fetch_fn,
    fetch_interactions=your_interactions_fn,
    fetch_page=your_fetch_page_fn,
    check_compliance=your_compliance_fn,
    queue_for_approval=your_queue_fn,
    start_run=your_start_run_fn,
    finish_run=your_finish_run_fn,
    mission=your_mission,
)

result = agent.invoke({"limit": 1})
print(result["summary"])
# "outreach_agent: processed 1 contacts — 1 queued for approval, 0 blocked"
```

## Protocols

| Parameter              | Protocol              | Description                                      |
| ---------------------- | --------------------- | ------------------------------------------------ |
| `llm`                  | `LanguageModel`       | Any LangChain `BaseChatModel`                    |
| `fetch_ready_contacts` | `ReadyContactFetcher` | `(limit: int) -> list[dict]`                     |
| `fetch_interactions`   | `InteractionFetcher`  | `(contact_id: int) -> list[dict]`                |
| `fetch_page`           | `PageFetcher`         | `(url: str) -> str`                              |
| `check_compliance`     | `ComplianceChecker`   | `(contact_id: int) -> bool`                      |
| `queue_for_approval`   | `ApprovalQueuer`      | `(contact_id, run_id, subject, body) -> int`     |
| `start_run`            | `RunStarter`          | `(agent_name, input_data) -> int`                |
| `finish_run`           | `RunFinisher`         | `(run_id, status, summary, output_data) -> None` |
| `mission`              | `AgentMission`        | Any object with the six mission fields           |

## Opt-out compliance

Opt-out lines are included in every email in 7 languages (de, en, fr, cs, nl, es, it), selected automatically from the contact's `preferred_language`. See [prompts.py](artcrm_outreach_agent/prompts.py).

## Testing

```bash
uv run pytest -v
```

## Support

If you find this useful, a small donation helps keep projects like this going:
[Donate via PayPal](https://paypal.me/christopherrehm001)
