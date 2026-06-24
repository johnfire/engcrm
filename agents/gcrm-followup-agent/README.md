# gcrm-followup-agent

LangGraph agent that monitors the inbox for replies and queues follow-up emails for overdue contacts.

> **Queue-only.** The supervisor runs this agent each cycle. Every drafted email — interested/warm replies and overdue nudges alike — goes to the human approval queue; nothing is sent autonomously. Drafts go out only once approved in the UI.

## What it does

**Stream 1 — Inbox replies:**

- Reads unprocessed inbox messages
- Matches each message to a contact by sender email — messages with no matching contact are skipped (marked processed, no LLM call)
- Classifies the reply: `interested` / `rejected` / `opt_out` / `other`
- Logs the interaction to the database
- If `opt_out`: flags the contact immediately, no further outreach ever
- If `interested`: drafts a reply and queues it for human approval (never sent autonomously)
- Marks each message as processed

**Stream 2 — Proactive follow-ups:**

- Fetches contacts overdue for follow-up (no reply after N days, default 90)
- Drafts a brief, non-pushy follow-up in the contact's preferred language
- Puts it in the **approval queue** (not sent directly — human reviews first)

## Usage

```python
from gcrm_followup_agent import create_followup_agent

agent = create_followup_agent(
    llm=your_llm,
    fetch_inbox=your_inbox_fn,
    match_contact=your_match_fn,
    log_interaction=your_log_fn,
    set_opt_out=your_opt_out_fn,
    mark_message_processed=your_mark_fn,
    fetch_overdue=your_overdue_fn,
    send_email=your_send_fn,
    queue_for_approval=your_queue_fn,
    start_run=your_start_run_fn,
    finish_run=your_finish_run_fn,
    mission=your_mission,
    overdue_days=90,    # optional, default 90
)

result = agent.invoke({})
print(result["summary"])
# "followup_agent: 3 replies processed, 2 overdue contacts, 2 drafts queued for approval, 1 warm replies flagged for visit, 1 opt-outs recorded, 0 bounces marked as bad_email"
```

## Protocols

| Parameter                | Protocol             | Description                                                 |
| ------------------------ | -------------------- | ----------------------------------------------------------- |
| `llm`                    | `LanguageModel`      | Any LangChain `BaseChatModel`                               |
| `fetch_inbox`            | `InboxFetcher`       | `() -> list[dict]`                                          |
| `match_contact`          | `ContactMatcher`     | `(from_email: str) -> dict \| None`                         |
| `log_interaction`        | `InteractionLogger`  | `(contact_id, method, direction, summary, outcome) -> None` |
| `set_opt_out`            | `OptOutSetter`       | `(contact_id: int) -> None`                                 |
| `mark_message_processed` | `InboxMessageMarker` | `(inbox_message_id, contact_id) -> None`                    |
| `fetch_overdue`          | `OverdueFetcher`     | `(days: int) -> list[dict]`                                 |
| `send_email`             | `EmailSender`        | `(to_email, subject, body) -> bool`                         |
| `queue_for_approval`     | `ApprovalQueuer`     | `(contact_id, subject, body, to_email) -> None`             |
| `start_run`              | `RunStarter`         | `(agent_name, input_data) -> int`                           |
| `finish_run`             | `RunFinisher`        | `(run_id, status, summary, output_data) -> None`            |
| `mission`                | `AgentMission`       | Any object with the mission fields                          |

## Testing

```bash
uv run pytest -v
```

## Support

If you find this useful, a small donation helps keep projects like this going:
[Donate via PayPal](https://paypal.me/christopherrehm001)
