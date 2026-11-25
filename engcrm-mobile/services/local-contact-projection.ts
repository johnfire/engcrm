import type { LocalRecord } from "./local-records";
import type { SyncEntityKind } from "./sync-contracts";
export { filterLocalContacts } from "./local-contact-filters";

type Snapshot = Record<SyncEntityKind, LocalRecord[]>;
type ContactKind = "person" | "organization";
export interface LocalContact {
  kind: ContactKind;
  syncId: string;
  serverId: number | null;
  name: string;
  pendingCount: number;
  failedCount: number;
  fields: Record<string, unknown>;
  lastContact: string | null;
  deals: LocalRecord[];
  allDeals: LocalRecord[];
  totalValue: number;
  people: LocalContact[];
}

const CONTACTED = new Set(["contacted", "meeting", "proposal", "customer", "dormant", "not_interested"]);
const NON_CONTACT_METHODS = new Set(["next_step", "next_step_done"]);

function text(value: unknown): string | null {
  return typeof value === "string" && value.length ? value : null;
}

function day(value: unknown, kind: ContactKind): string | null {
  const raw = text(value);
  if (!raw) return null;
  if (kind === "organization") return raw.slice(0, 10);
  const date = new Date(raw);
  if (!Number.isFinite(date.getTime())) return null;
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Berlin", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(date);
  const part = (name: string) => parts.find((item) => item.type === name)?.value;
  return `${part("year")}-${part("month")}-${part("day")}`;
}

function recordsByOwner(records: LocalRecord[], ownerField: string): Map<string, LocalRecord[]> {
  const result = new Map<string, LocalRecord[]>();
  for (const record of records) {
    const owner = text(record.fields[ownerField]);
    if (!owner) continue;
    const group = result.get(owner) ?? [];
    group.push(record);
    result.set(owner, group);
  }
  return result;
}

function latestContact(history: LocalRecord[], kind: ContactKind): string | null {
  const dates = history.filter((entry) => !NON_CONTACT_METHODS.has(text(entry.fields.method) ?? ""))
    .map((entry) => day(entry.fields[kind === "person" ? "occurred_at" : "interaction_date"], kind))
    .filter((value): value is string => value !== null).sort();
  return dates.at(-1) ?? null;
}

function projectRecord(record: LocalRecord, kind: ContactKind, allDeals: LocalRecord[], history: LocalRecord[], offer: string): LocalContact {
  const deals = offer === "all" ? allDeals : allDeals.filter((deal) => deal.fields.offer_slug === offer);
  const totalValue = deals.reduce((sum, deal) => {
    const value = Number(deal.fields.total_value ?? 0);
    if (!Number.isFinite(value)) throw new Error("Invalid offline deal total");
    return sum + value;
  }, 0);
  return { kind, syncId: record.syncId, serverId: record.serverId, name: text(record.fields.name) ?? "",
    pendingCount: record.pendingCount, failedCount: record.failedCount,
    fields: record.fields, lastContact: latestContact(history, kind), deals, allDeals, totalValue, people: [] };
}

function wasContacted(contact: LocalContact, allDeals: LocalRecord[]): boolean {
  return contact.lastContact !== null || allDeals.some((deal) => CONTACTED.has(text(deal.fields.status) ?? ""));
}

export function projectLocalContacts(snapshot: Snapshot, offer: string): LocalContact[] {
  const personDeals = recordsByOwner(snapshot.deal, "person_sync_id");
  const organizationDeals = recordsByOwner(snapshot.deal, "organization_sync_id");
  const notes = recordsByOwner(snapshot.person_note, "person_sync_id");
  const activities = recordsByOwner(snapshot.organization_activity, "organization_sync_id");
  const organizations = new Map(snapshot.organization.map((record) => [record.syncId,
    projectRecord(record, "organization", organizationDeals.get(record.syncId) ?? [], activities.get(record.syncId) ?? [], offer)]));
  const unlinked: LocalContact[] = [];
  for (const record of snapshot.person) {
    const deals = personDeals.get(record.syncId) ?? [];
    const person = projectRecord(record, "person", deals, notes.get(record.syncId) ?? [], offer);
    if (!wasContacted(person, deals)) continue;
    const parent = organizations.get(text(record.fields.organization_sync_id) ?? "");
    if (parent) parent.people.push(person);
    else unlinked.push(person);
  }
  const included = [...organizations.values()].filter((organization) => {
    organization.people.sort((left, right) => {
      if (left.lastContact !== right.lastContact) {
        if (!left.lastContact) return 1;
        if (!right.lastContact) return -1;
        return right.lastContact.localeCompare(left.lastContact);
      }
      if (left.serverId !== null && right.serverId !== null) return right.serverId - left.serverId;
      return left.syncId.localeCompare(right.syncId);
    });
    const dates = organization.people.map((person) => person.lastContact).filter((value): value is string => value !== null).sort();
    if (dates.length && (!organization.lastContact || dates[dates.length - 1] > organization.lastContact)) organization.lastContact = dates[dates.length - 1];
    return organization.people.length > 0 || wasContacted(organization, organizationDeals.get(organization.syncId) ?? []);
  });
  return [...included, ...unlinked];
}
