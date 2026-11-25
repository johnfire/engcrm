import { type LocalContact, type LocalSnapshot, projectRecord, recordsByOwner } from "./local-contact-projection";
import type { LocalRecord } from "./local-records";

export interface LocalEntity extends LocalContact { linkedinCount: number }

function latestRecorded(history: LocalRecord[], kind: "person" | "organization"): string | null {
  const key = kind === "person" ? "occurred_at" : "interaction_date";
  const dates = history.map((entry) => entry.fields[key]).filter((value): value is string => typeof value === "string" && !!value).sort();
  return dates.at(-1) ?? null;
}

export function projectLocalEntities(snapshot: LocalSnapshot, kind: "person" | "organization", offer: string): LocalEntity[] {
  const parentField = kind === "person" ? "person_sync_id" : "organization_sync_id";
  const deals = recordsByOwner(snapshot.deal, parentField);
  const history = recordsByOwner(kind === "person" ? snapshot.person_note : snapshot.organization_activity, parentField);
  const linkedPeople = recordsByOwner(snapshot.person, "organization_sync_id");
  const organizations = new Map(snapshot.organization.map((organization) => [organization.syncId, organization]));
  return snapshot[kind].map((record) => {
    const entries = history.get(record.syncId) ?? [];
    const projected = projectRecord(record, kind, deals.get(record.syncId) ?? [], [], offer);
    const company = typeof record.fields.organization_sync_id === "string" ? organizations.get(record.fields.organization_sync_id) : null;
    return { ...projected, fields: kind === "person" ? { ...projected.fields, company: company?.fields.name ?? null } : projected.fields,
      lastContact: latestRecorded(entries, kind),
      linkedinCount: (linkedPeople.get(record.syncId) ?? []).filter((person) => person.fields.is_linkedin_contact === true).length };
  });
}
