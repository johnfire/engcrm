import type { LocalContact } from "./local-contact-projection";
import type { ContactSortKey } from "./listSortOptions";
import type { LocalRecord } from "./local-records";

interface ContactFilters {
  search: string;
  kind: "" | "person" | "organization";
  stage: string;
  sort: ContactSortKey;
  direction: "asc" | "desc";
}

const STAGES = ["customer", "opportunity", "prospect", "nibble", "suspect", "candidate", "not_now", "not_in_pipeline"];
const STATUSES = ["customer", "proposal", "meeting", "contacted", "ready", "on_hold", "dormant", "none", "dropped", "not_interested"];

function ranked(deals: LocalRecord[], field: string, ranks: string[]): number | null {
  const values = deals.map((deal) => ranks.indexOf(String(deal.fields[field]))).filter((rank) => rank >= 0);
  return values.length ? Math.min(...values) : null;
}

function sortValue(contact: LocalContact, sort: ContactSortKey): string | number | null {
  switch (sort) {
    case "last_contact": case "newest": return contact.lastContact;
    case "name": return contact.name.toLocaleLowerCase();
    case "city": return typeof contact.fields.city === "string" ? contact.fields.city.toLocaleLowerCase() : null;
    case "priority": return Number.isInteger(contact.fields[contact.kind === "person" ? "value_rating" : "personal_priority"])
      ? contact.fields[contact.kind === "person" ? "value_rating" : "personal_priority"] as number : null;
    case "pipeline_stage": return ranked(contact.allDeals, "pipeline_stage", STAGES);
    case "status": return ranked(contact.deals, "status", STATUSES);
    case "next_contact": {
      const dates = contact.deals.map((deal) => deal.fields.next_step_date).filter((value): value is string => typeof value === "string" && !!value).sort();
      return dates[0] ?? null;
    }
    case "total_value": return contact.totalValue;
    case "short_term_value": case "long_term_value": return Number.isInteger(contact.fields[sort]) ? contact.fields[sort] as number : null;
  }
}

function searchable(contact: LocalContact): string {
  const words = [contact.name, contact.fields.type, contact.fields.title, contact.fields.company_raw,
    contact.fields.city, contact.fields.email, contact.fields.phone];
  for (const person of contact.people) words.push(person.name, person.fields.title, person.fields.city, person.fields.email, person.fields.phone);
  return words.filter((value): value is string => typeof value === "string").join(" ").toLocaleLowerCase();
}

function matches(contact: LocalContact, filters: ContactFilters): boolean {
  if (filters.kind && filters.kind !== contact.kind) return false;
  if (filters.stage === "none" && contact.deals.length !== 0) return false;
  if (filters.stage && filters.stage !== "none" && !contact.deals.some((deal) => deal.fields.pipeline_stage === filters.stage)) return false;
  const content = searchable(contact);
  return filters.search.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean).slice(0, 4).every((word) => content.includes(word));
}

function compareContacts(a: LocalContact, b: LocalContact, filters: ContactFilters): number {
  const left = sortValue(a, filters.sort), right = sortValue(b, filters.sort);
  if (left === null && right !== null) return 1;
  if (right === null && left !== null) return -1;
  if (left !== null && right !== null) {
    const order = typeof left === "number" && typeof right === "number" ? left - right : String(left).localeCompare(String(right));
    if (order !== 0) return filters.direction === "asc" ? order : -order;
  }
  const kind = a.kind.localeCompare(b.kind);
  if (kind) return kind;
  if (a.serverId !== null && b.serverId !== null && a.serverId !== b.serverId) {
    return filters.sort === "last_contact" || filters.sort === "newest" ? b.serverId - a.serverId : a.serverId - b.serverId;
  }
  return a.syncId.localeCompare(b.syncId);
}

export function filterLocalContacts(contacts: LocalContact[], filters: ContactFilters): LocalContact[] {
  return contacts.filter((contact) => matches(contact, filters)).sort((a, b) => compareContacts(a, b, filters));
}
