# Pipeline stages

Progression: **Candidate → Suspect → Nibble → Prospect → Opportunity → Customer**.
**Not in pipeline** is available separately for contacts that are not being pursued.

**Nibble** means contact has been made and something looked positive, but the
relationship is not yet a prospect. It is selected manually. Positive responses
do not automatically move contacts into this stage.

The stage is available for company and person deals, stage filters, list sorting
and statistics. Best-first ascending sorting places Nibble after Prospect and
before Suspect; descending reverses that order. Ranking uses the strongest stage
across every live offer, even when a list is filtered to one offer. A Training
customer therefore ranks as a Customer even if Consulting is still a Suspect.
Nibble is included among active
working stages when reporting stalled relationships.

Stages and activity/status remain separate. Adding the stage does not create
contact history or move existing records. The database already stores stages as
text with application validation, so no data migration is needed.

Each existing card under **Offers pitched** now has an **Offer** selector. Choosing
another offer changes that same deal; its stage, status, contact person, next
step, notes and associated financial records stay attached to the same deal ID.
Previously recorded activities retain their original offer tags. An offer that
is already pitched to the same owner cannot be chosen again; the API rejects
that conflict rather than merging or discarding either deal.
