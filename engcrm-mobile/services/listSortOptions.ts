// The sort options each list offers. The first one is the list's default. Directions are
// the useful first tap: ranks (stage, status, priority, rating) best first, values
// highest first, dates soonest or latest first, names A to Z.
import type { SortOption } from "./listSort";

export type OrganizationSortKey =
  | "created_at"
  | "name"
  | "type"
  | "personal_priority"
  | "pipeline_stage"
  | "status"
  | "next_step_date"
  | "last_contact"
  | "short_term_value"
  | "long_term_value";

export type PersonSortKey =
  | "created_at"
  | "name"
  | "connected_on"
  | "company"
  | "city"
  | "value_rating"
  | "pipeline_stage"
  | "status"
  | "next_step_date"
  | "last_contact"
  | "short_term_value"
  | "long_term_value";

// "newest" is the key older app builds sent; the screen no longer offers it.
export type ContactSortKey =
  | "last_contact"
  | "newest"
  | "name"
  | "city"
  | "priority"
  | "pipeline_stage"
  | "status"
  | "next_contact"
  | "total_value"
  | "short_term_value"
  | "long_term_value";

export const ORGANIZATION_SORTS: readonly SortOption<OrganizationSortKey>[] = [
  { key: "created_at", direction: "desc", labelKey: "common.sortNewest" },
  { key: "name", direction: "asc", labelKey: "common.sortAZ" },
  { key: "personal_priority", direction: "asc", labelKey: "organizations.sortPersonalPriority" },
  { key: "pipeline_stage", direction: "asc", labelKey: "sort.stage" },
  { key: "status", direction: "asc", labelKey: "sort.status" },
  { key: "next_step_date", direction: "asc", labelKey: "sort.nextStep" },
  { key: "last_contact", direction: "desc", labelKey: "sort.lastContact" },
  { key: "short_term_value", direction: "desc", labelKey: "sort.shortTermValue" },
  { key: "long_term_value", direction: "desc", labelKey: "sort.longTermValue" },
  { key: "type", direction: "asc", labelKey: "common.sortIndustry" },
];

export const PERSON_SORTS: readonly SortOption<PersonSortKey>[] = [
  { key: "created_at", direction: "desc", labelKey: "common.sortNewest" },
  { key: "name", direction: "asc", labelKey: "common.sortAZ" },
  { key: "value_rating", direction: "asc", labelKey: "people.sortRating" },
  { key: "pipeline_stage", direction: "asc", labelKey: "sort.stage" },
  { key: "status", direction: "asc", labelKey: "sort.status" },
  { key: "next_step_date", direction: "asc", labelKey: "sort.nextStep" },
  { key: "last_contact", direction: "desc", labelKey: "sort.lastContact" },
  { key: "short_term_value", direction: "desc", labelKey: "sort.shortTermValue" },
  { key: "long_term_value", direction: "desc", labelKey: "sort.longTermValue" },
  { key: "connected_on", direction: "desc", labelKey: "people.sortConnected" },
  { key: "company", direction: "asc", labelKey: "people.sortCompany" },
  { key: "city", direction: "asc", labelKey: "people.sortCity" },
];

export const CONTACT_SORTS: readonly SortOption<ContactSortKey>[] = [
  { key: "last_contact", direction: "desc", labelKey: "contactFeed.last_contact" },
  { key: "name", direction: "asc", labelKey: "contactFeed.name" },
  { key: "priority", direction: "asc", labelKey: "sort.priority" },
  { key: "pipeline_stage", direction: "asc", labelKey: "sort.stage" },
  { key: "status", direction: "asc", labelKey: "sort.status" },
  { key: "next_contact", direction: "asc", labelKey: "sort.nextStep" },
  { key: "total_value", direction: "desc", labelKey: "sort.dealValue" },
  { key: "short_term_value", direction: "desc", labelKey: "sort.shortTermValue" },
  { key: "long_term_value", direction: "desc", labelKey: "sort.longTermValue" },
  { key: "city", direction: "asc", labelKey: "people.sortCity" },
];
