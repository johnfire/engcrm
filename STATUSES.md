# Contact Statuses

## Pipeline Statuses (automated flow)

| Status      | Description                                                                            |
| ----------- | -------------------------------------------------------------------------------------- |
| `candidate` | Freshly discovered by the research agent. Not yet evaluated — no scoring, no outreach. |
| `cold`      | Scored by the scout agent as a good fit. Ready for first-contact outreach.             |
| `contacted` | First outreach has been sent. Waiting for a response.                                  |

## Positive Progression

| Status             | Description                                                                          |
| ------------------ | ------------------------------------------------------------------------------------ |
| `meeting`          | A meeting or discovery call has been arranged or confirmed.                          |
| `proposal`         | A proposal or quote has been sent. Awaiting decision.                                |
| `accepted`         | Contact has agreed to proceed with a project. Active client relationship.            |
| `networking_visit` | Responded positively but no immediate project. Flagged to stay in touch and revisit. |

## Inactive / Stalled

| Status    | Description                                                                                                     |
| --------- | --------------------------------------------------------------------------------------------------------------- |
| `dormant` | Was active at some point but has gone quiet. No interaction within the dormancy threshold (default: 12 months). |
| `on_hold` | Manually parked — timing not right, budget not available. Revisit later.                                        |

## Dead Ends

| Status           | Description                                                                                                                                                                                          |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `dropped`        | Decided not to pursue after at least one contact attempt — wrong fit, no response after multiple tries, or business closed. Never set before first contact; use `cold` if no outreach has been made. |
| `rejected`       | Prospect explicitly declined.                                                                                                                                                                        |
| `do_not_contact` | Opted out or explicitly asked not to be contacted. Blocked from all outreach.                                                                                                                        |

## Data Quality

| Status      | Description                                                                                         |
| ----------- | --------------------------------------------------------------------------------------------------- |
| `bad_email` | Outreach email bounced or was undeliverable. Email address needs to be verified before re-outreach. |

---

## Flow

```
candidate → (scout scores) → cold → (outreach sent) → contacted
↓
meeting → proposal → accepted / networking_visit
↓
dormant / on_hold / dropped / do_not_contact
```
