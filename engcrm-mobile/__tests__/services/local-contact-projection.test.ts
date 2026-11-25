import { filterLocalContacts, projectLocalContacts } from "../../services/local-contact-projection";
import type { LocalRecord } from "../../services/local-records";

function record(syncId: string, fields: Record<string, unknown>, serverId: number | null = null): LocalRecord {
  return { syncId, serverId, fields, isLocalOnly: serverId === null, pendingCount: 0, failedCount: 0 };
}

it("groups contacted people under their organization and includes offline notes", () => {
  const contacts = projectLocalContacts({
    organization: [record("org", { name: "Company" }, 1)],
    person: [record("person", { name: "Person", organization_sync_id: "org" }),
      record("uncontacted", { name: "No contact" })],
    deal: [record("deal", { person_sync_id: "person", offer_slug: "consulting", pipeline_stage: "prospect", status: "ready" })],
    person_note: [record("note", { person_sync_id: "person", occurred_at: "2026-11-25T10:00:00Z", method: "visit" })],
    organization_activity: [],
  }, "all");
  expect(contacts).toHaveLength(1);
  expect(contacts[0]).toMatchObject({ kind: "organization", syncId: "org", name: "Company", lastContact: "2026-11-25",
    people: [{ syncId: "person", name: "Person", lastContact: "2026-11-25" }] });
});

it("counts contacted status from all offers but shows only the selected offer's deals", () => {
  const contacts = projectLocalContacts({
    organization: [], person: [record("p", { name: "Contacted" })],
    deal: [record("a", { person_sync_id: "p", offer_slug: "other", status: "meeting", pipeline_stage: "prospect", total_value: 100 }),
      record("b", { person_sync_id: "p", offer_slug: "consulting", status: "ready", pipeline_stage: "candidate", total_value: 50 })],
    person_note: [record("plan", { person_sync_id: "p", occurred_at: "2026-11-25T10:00:00Z", method: "next_step" })],
    organization_activity: [],
  }, "consulting");
  expect(contacts).toHaveLength(1);
  expect(contacts[0].lastContact).toBeNull();
  expect(contacts[0].deals.map((deal) => deal.syncId)).toEqual(["b"]);
  expect(contacts[0].totalValue).toBe(50);
});

it("uses the Berlin contact day for a note and keeps a person standalone if their company is unavailable", () => {
  const contacts = projectLocalContacts({
    organization: [], person: [record("p", { name: "Person", organization_sync_id: "missing" })], deal: [],
    person_note: [record("note", { person_sync_id: "p", occurred_at: "2026-11-25T23:30:00Z", method: "call" })],
    organization_activity: [],
  }, "all");
  expect(contacts).toHaveLength(1);
  expect(contacts[0]).toMatchObject({ kind: "person", lastContact: "2026-11-26" });
});

it("filters grouped contacts by child details and sorts the selected offer by total value", () => {
  const contacts = projectLocalContacts({
    organization: [record("org-a", { name: "A" }, 1), record("org-b", { name: "B" }, 2)],
    person: [record("p", { name: "Pat", title: "Engineer", organization_sync_id: "org-a" }, 3)],
    deal: [record("a", { organization_sync_id: "org-a", offer_slug: "consulting", pipeline_stage: "prospect", status: "contacted", total_value: 20 }),
      record("b", { organization_sync_id: "org-b", offer_slug: "consulting", pipeline_stage: "prospect", status: "contacted", total_value: 40 }),
      record("p-deal", { person_sync_id: "p", offer_slug: "consulting", pipeline_stage: "prospect", status: "contacted" })],
    person_note: [], organization_activity: [],
  }, "consulting");
  expect(filterLocalContacts(contacts, { search: "engineer", kind: "", stage: "prospect", sort: "name", direction: "asc" })
    .map((item) => item.syncId)).toEqual(["org-a"]);
  expect(filterLocalContacts(contacts, { search: "", kind: "", stage: "prospect", sort: "total_value", direction: "desc" })
    .map((item) => item.syncId)).toEqual(["org-b", "org-a"]);
});

it("orders grouped people by most recent contact, with undated contacts last", () => {
  const contacts = projectLocalContacts({
    organization: [record("org", { name: "Company" })],
    person: [record("old", { name: "Old", organization_sync_id: "org" }),
      record("undated", { name: "Undated", organization_sync_id: "org" }),
      record("new", { name: "New", organization_sync_id: "org" })],
    deal: [record("d", { person_sync_id: "undated", status: "contacted", offer_slug: "consulting" })],
    person_note: [record("a", { person_sync_id: "old", occurred_at: "2026-11-01T10:00:00Z" }),
      record("b", { person_sync_id: "new", occurred_at: "2026-11-20T10:00:00Z" })], organization_activity: [],
  }, "all");
  expect(contacts[0].people.map((person) => person.syncId)).toEqual(["new", "old", "undated"]);
});
