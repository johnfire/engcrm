import { projectLocalEntities } from "../../services/local-entity-projection";
import { filterLocalEntities } from "../../services/local-entity-filters";
import type { LocalRecord } from "../../services/local-records";

function record(syncId: string, fields: Record<string, unknown>): LocalRecord {
  return { syncId, fields, serverId: null, isLocalOnly: true, pendingCount: 0, failedCount: 0 };
}

it("includes uncontacted people and resolves their local organization's name", () => {
  const snapshot = { organization: [record("org", { name: "Company" })],
    person: [record("p", { name: "Pat", organization_sync_id: "org", is_linkedin_contact: true })],
    deal: [], person_note: [], organization_activity: [] };
  const people = projectLocalEntities(snapshot, "person", "all");
  expect(people).toHaveLength(1);
  expect(people[0].fields.company).toBe("Company");
  const organizations = projectLocalEntities(snapshot, "organization", "all");
  expect(organizations[0].linkedinCount).toBe(1);
});

it("keeps all deals for stage sorting but displays only the selected offer", () => {
  const snapshot = { organization: [], person: [record("p", { name: "Pat" })],
    deal: [record("a", { person_sync_id: "p", offer_slug: "consulting", pipeline_stage: "candidate" }),
      record("b", { person_sync_id: "p", offer_slug: "other", pipeline_stage: "customer" })],
    person_note: [], organization_activity: [] };
  const person = projectLocalEntities(snapshot, "person", "consulting")[0];
  expect(person.deals.map((deal) => deal.syncId)).toEqual(["a"]);
  expect(person.allDeals).toHaveLength(2);
});

it("filters people by LinkedIn and rating and keeps unrated records last", () => {
  const snapshot = { organization: [], person: [record("a", { name: "Amy", value_rating: 2, is_linkedin_contact: true }),
    record("b", { name: "Bob", value_rating: null, is_linkedin_contact: true }),
    record("c", { name: "Chris", value_rating: 1, is_linkedin_contact: false })],
    deal: [], person_note: [], organization_activity: [] };
  const people = projectLocalEntities(snapshot, "person", "all");
  const filters = { kind: "person" as const, offer: "all", search: "", stage: "", status: "", rating: "", linkedin: "1",
    suppressed: "", sort: "value_rating" as const, direction: "desc" as const };
  expect(filterLocalEntities(people, filters).map((person) => person.syncId)).toEqual(["a", "b"]);
  expect(filterLocalEntities(people, { ...filters, rating: "2+" }).map((person) => person.syncId)).toEqual(["a"]);
});

it("requires stage and status to match the same shown deal", () => {
  const snapshot = { organization: [record("org", { name: "Company" })], person: [],
    deal: [record("a", { organization_sync_id: "org", offer_slug: "one", pipeline_stage: "prospect", status: "ready" }),
      record("b", { organization_sync_id: "org", offer_slug: "two", pipeline_stage: "candidate", status: "meeting" })],
    person_note: [], organization_activity: [] };
  const organizations = projectLocalEntities(snapshot, "organization", "all");
  const filters = { kind: "organization" as const, offer: "all", search: "", stage: "prospect", status: "meeting", rating: "",
    linkedin: "", suppressed: "", sort: "name" as const, direction: "asc" as const };
  expect(filterLocalEntities(organizations, filters)).toEqual([]);
});
