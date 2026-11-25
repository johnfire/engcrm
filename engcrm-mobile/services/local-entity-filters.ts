import { ranked, STAGE_RANKS, STATUS_RANKS } from "./local-contact-filters";
import type { LocalEntity } from "./local-entity-projection";
import type { OrganizationSortKey, PersonSortKey } from "./listSortOptions";

export interface EntityFilters {
  kind: "organization" | "person";
  offer: string;
  search: string;
  stage: string;
  status: string;
  rating: string;
  linkedin: string;
  suppressed: string;
  sort: OrganizationSortKey | PersonSortKey;
  direction: "asc" | "desc";
}

function ratingMatches(value: unknown, filter: string): boolean {
  if (!filter) return true;
  if (filter === "unrated") return value == null;
  if (typeof value !== "number") return false;
  return filter.endsWith("+") ? value <= Number(filter.slice(0, -1)) : value === Number(filter);
}

function matches(entity: LocalEntity, filters: EntityFilters): boolean {
  const value = entity.fields[filters.kind === "person" ? "value_rating" : "personal_priority"];
  if (!ratingMatches(value, filters.rating)) return false;
  if (filters.kind === "organization" && filters.linkedin === "1" && !entity.linkedinCount) return false;
  if (filters.kind === "person" && filters.linkedin && entity.fields.is_linkedin_contact !== true) return false;
  if (filters.kind === "person" && filters.linkedin === "unlinked" && entity.fields.organization_sync_id != null) return false;
  if (filters.suppressed && entity.fields[filters.suppressed] !== true) return false;
  if (filters.stage === "none") {
    if (entity.deals.length) return false;
  } else if ((filters.offer !== "all" || filters.stage || filters.status) && !entity.deals.some((deal) =>
    (!filters.stage || deal.fields.pipeline_stage === filters.stage) && (!filters.status || deal.fields.status === filters.status))) return false;
  if (!filters.search) return true;
  const keys = filters.kind === "person" ? ["name", "email", "city"] : ["name", "city", "type"];
  const query = filters.search.toLocaleLowerCase();
  return keys.some((key) => typeof entity.fields[key] === "string" && (entity.fields[key] as string).toLocaleLowerCase().includes(query));
}

function sortValue(entity: LocalEntity, sort: EntityFilters["sort"]): string | number | null {
  if (sort === "pipeline_stage") return ranked(entity.allDeals, "pipeline_stage", STAGE_RANKS);
  if (sort === "status") return ranked(entity.deals, "status", STATUS_RANKS);
  if (sort === "next_step_date") {
    const values = entity.deals.map((deal) => deal.fields.next_step_date).filter((value): value is string => typeof value === "string" && !!value).sort();
    return values[0] ?? null;
  }
  if (sort === "last_contact") return entity.lastContact;
  const value = entity.fields[sort];
  if (typeof value === "number") return value;
  if (typeof value !== "string") return null;
  if (sort === "created_at") {
    const stamp = Date.parse(value);
    return Number.isFinite(stamp) ? stamp : null;
  }
  return value.toLocaleLowerCase();
}

function compare(a: LocalEntity, b: LocalEntity, filters: EntityFilters): number {
  const left = sortValue(a, filters.sort), right = sortValue(b, filters.sort);
  if (left === null && right !== null) return 1;
  if (right === null && left !== null) return -1;
  if (left !== null && right !== null) {
    const order = typeof left === "number" && typeof right === "number" ? left - right : String(left).localeCompare(String(right));
    if (order) return filters.direction === "asc" ? order : -order;
  }
  if (a.serverId !== null && b.serverId !== null && a.serverId !== b.serverId) return a.serverId - b.serverId;
  return a.syncId.localeCompare(b.syncId);
}

export function filterLocalEntities(entities: LocalEntity[], filters: EntityFilters): LocalEntity[] {
  return entities.filter((entity) => matches(entity, filters)).sort((a, b) => compare(a, b, filters));
}
