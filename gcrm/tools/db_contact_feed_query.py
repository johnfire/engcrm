"""Group contacted people before filtering, sorting and paginating businesses."""
from gcrm.tools.db_contact_dates import CONTACT_HISTORY_FILTER, contact_day_sql
from gcrm.tools.db_deals import (
    CONSULTING,
    deal_sort_sql,
    deals_json_sql,
    offer_id_sql,
    organization_deal_join,
    person_deal_join,
)


def _stages_sql(alias: str, column: str, offer: str | None) -> str:
    """The stages of the owner's live deals — that offer's, or every offer's —
    as an array, for the stage filter."""
    only = f"AND x.offer_id = {offer_id_sql(f'{alias}.workspace_id', offer)}" if offer else ""
    return (f"ARRAY(SELECT x.pipeline_stage FROM deals x JOIN offers o ON o.id = x.offer_id WHERE x.{column} = {alias}.id "
            f"AND x.deleted_at IS NULL {only} ORDER BY o.sort_order, o.id)")


def contact_feed_sql(offer: str | None = CONSULTING) -> str:
    """The feed for one offer's pipeline (`pipeline_stage` is that deal's), or
    for every offer (offer None: no single stage, `deals` lists them all).
    Every row carries `deals` and, for filtering, `deal_stages`, plus the
    signed-in user's private ratings (priority, short_term_value,
    long_term_value). The query starts with two %s placeholders, both that
    user's id; None matches nobody, so the ratings come back empty."""
    if offer:
        person_stage, person_join = "person_deal.pipeline_stage", person_deal_join("person", "person_deal", offer)
        organization_stage = "organization_deal.pipeline_stage"
        organization_join = organization_deal_join("organization", "organization_deal", offer)
    else:
        person_stage = organization_stage = "NULL::text"
        person_join = organization_join = ""
    return f"""
WITH my_ratings AS (
    SELECT 'organization' AS rated_kind, contact_id AS rated_id, priority, short_term_value, long_term_value
      FROM contact_user_priorities WHERE user_id = %s
    UNION ALL
    SELECT 'person', person_id, priority, short_term_value, long_term_value
      FROM person_user_priorities WHERE user_id = %s
), active_people AS (
    SELECT person.*, {person_stage} AS pipeline_stage, organization.id AS business_id,
           {deals_json_sql("person", "person_id", offer)} AS deals,
           {_stages_sql("person", "person_id", offer)} AS deal_stages,
           {deal_sort_sql("person", "person_id", offer, "pipeline_stage")} AS stage_sort_key,
           (SELECT MAX({contact_day_sql("person", "occurred_at")}) FROM people_interactions
             WHERE person_id=person.id AND {CONTACT_HISTORY_FILTER}) AS last_contact
      FROM people person
      {person_join}
      LEFT JOIN contacts organization ON organization.id=person.contact_id
           AND organization.deleted_at IS NULL AND organization.workspace_id=person.workspace_id
     WHERE person.deleted_at IS NULL
), business_people AS (
    SELECT business_id,
           jsonb_agg(jsonb_build_object(
               'id', id, 'name', name, 'description', title, 'email', email,
               'phone', phone, 'city', city, 'pipeline_stage', pipeline_stage,
               'last_contact', last_contact
           ) ORDER BY last_contact DESC, id DESC) AS people,
           string_agg(concat_ws(' ', name, title, email, phone, city), ' ') AS searchable_people
      FROM active_people WHERE business_id IS NOT NULL AND last_contact IS NOT NULL
     GROUP BY business_id
), business_contacts AS (
    SELECT organization.*, {organization_stage} AS pipeline_stage,
           {deals_json_sql("organization", "contact_id", offer)} AS deals,
           {_stages_sql("organization", "contact_id", offer)} AS deal_stages,
           {deal_sort_sql("organization", "contact_id", offer, "pipeline_stage")} AS stage_sort_key,
           linked.people, linked.searchable_people,
           direct.last_contact AS direct_contact,
           (linked.people->0->>'last_contact')::date AS person_contact
      FROM contacts organization
      {organization_join}
      LEFT JOIN business_people linked ON linked.business_id=organization.id
      LEFT JOIN LATERAL (
          SELECT MAX(interaction_date) AS last_contact FROM interactions
           WHERE contact_id=organization.id AND {CONTACT_HISTORY_FILTER}
      ) direct ON TRUE
     WHERE organization.deleted_at IS NULL
), contact_feed AS (
    SELECT id, 'organization' AS kind, name, type AS description, NULL::text AS company,
           city, email, phone, pipeline_stage, deals, deal_stages, stage_sort_key, created_at, workspace_id,
           GREATEST(direct_contact, person_contact) AS last_contact,
           COALESCE(people, '[]'::jsonb) AS people, searchable_people,
           CASE WHEN direct_contact IS NOT NULL AND (person_contact IS NULL OR direct_contact >= person_contact)
                THEN 'organization' ELSE 'person' END AS last_contact_kind,
           CASE WHEN direct_contact IS NOT NULL AND (person_contact IS NULL OR direct_contact >= person_contact)
                THEN id ELSE (people->0->>'id')::integer END AS last_contact_id,
           CASE WHEN direct_contact IS NOT NULL AND (person_contact IS NULL OR direct_contact >= person_contact)
                THEN name ELSE people->0->>'name' END AS last_contact_name
      FROM business_contacts
    UNION ALL
    SELECT person.id, 'person', person.name, person.title, person.company_raw,
           person.city, person.email, person.phone, person.pipeline_stage, person.deals, person.deal_stages, person.stage_sort_key,
           person.created_at, person.workspace_id, person.last_contact,
           '[]'::jsonb, NULL::text, 'person', person.id, person.name
      FROM active_people person WHERE person.business_id IS NULL
)
SELECT id, kind, name, description, company, city, email, phone, pipeline_stage, deals,
       created_at, last_contact, people, last_contact_kind, last_contact_id, last_contact_name,
       rating.priority, rating.short_term_value, rating.long_term_value
FROM contact_feed
LEFT JOIN my_ratings rating ON rating.rated_kind = contact_feed.kind AND rating.rated_id = contact_feed.id
"""

