"""Group contacted people before filtering, sorting and paginating businesses."""
from gcrm.tools.db_contact_dates import CONTACT_HISTORY_FILTER, contact_day_sql
from gcrm.tools.db_deals import organization_deal_join, person_deal_join

CONTACT_FEED_SQL = f"""
WITH active_people AS (
    SELECT person.*, person_deal.pipeline_stage, organization.id AS business_id,
           (SELECT MAX({contact_day_sql("person", "occurred_at")}) FROM people_interactions
             WHERE person_id=person.id AND {CONTACT_HISTORY_FILTER}) AS last_contact
      FROM people person
      {person_deal_join("person", "person_deal")}
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
    SELECT organization.*, organization_deal.pipeline_stage, linked.people, linked.searchable_people,
           direct.last_contact AS direct_contact,
           (linked.people->0->>'last_contact')::date AS person_contact
      FROM contacts organization
      {organization_deal_join("organization", "organization_deal")}
      LEFT JOIN business_people linked ON linked.business_id=organization.id
      LEFT JOIN LATERAL (
          SELECT MAX(interaction_date) AS last_contact FROM interactions
           WHERE contact_id=organization.id AND {CONTACT_HISTORY_FILTER}
      ) direct ON TRUE
     WHERE organization.deleted_at IS NULL
), contact_feed AS (
    SELECT id, 'organization' AS kind, name, type AS description, NULL::text AS company,
           city, email, phone, pipeline_stage, created_at, workspace_id,
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
           person.city, person.email, person.phone, person.pipeline_stage,
           person.created_at, person.workspace_id, person.last_contact,
           '[]'::jsonb, NULL::text, 'person', person.id, person.name
      FROM active_people person WHERE person.business_id IS NULL
)
SELECT id, kind, name, description, company, city, email, phone, pipeline_stage,
       created_at, last_contact, people, last_contact_kind, last_contact_id, last_contact_name
FROM contact_feed
"""
