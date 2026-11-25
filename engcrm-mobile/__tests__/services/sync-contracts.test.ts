import { parseBootstrapPage, parsePullPage } from "../../services/sync-contracts";

const example = {
  entities: [{ entity_kind: "organization", sync_id: "fb4fa281-8a94-4726-9ce7-02c18c90aa90", server_id: 9,
    fields: { name: "Company" }, field_versions: {} }],
  high_water: 12,
  next_token: null,
};

it("accepts a typed bootstrap page", () => {
  expect(parseBootstrapPage(example).entities[0].fields.name).toBe("Company");
});

it("checks incremental cursor ordering and forbids data in erasure markers", () => {
  const erase = { sequence: 13, entity_kind: "person", sync_id: example.entities[0].sync_id,
    operation: "hard_erase", changed_at: "2026-11-25T12:00:00Z" };
  expect(parsePullPage({ changes: [erase], next_cursor: 13, has_more: false }).changes).toHaveLength(1);
  expect(() => parsePullPage({ changes: [erase], next_cursor: 12, has_more: false })).toThrow();
  expect(() => parsePullPage({ changes: [{ ...erase, fields: { name: "private" } }], next_cursor: 13, has_more: false })).toThrow();
  expect(() => parsePullPage({ changes: [erase, erase], next_cursor: 13, has_more: false })).toThrow();
});

it.each([
  { ...example, high_water: -1 },
  { ...example, next_token: 123 },
  { ...example, entities: [{ ...example.entities[0], entity_kind: "sale" }] },
  { ...example, entities: [{ ...example.entities[0], sync_id: "not-a-uuid" }] },
  { ...example, entities: [{ ...example.entities[0], server_id: 0 }] },
  { ...example, entities: [{ ...example.entities[0], fields: [] }] },
  { ...example, entities: [{ ...example.entities[0], field_versions: { name: { changed_at: "not-a-time" } } }] },
])("rejects malformed or out-of-scope records", (invalid) => {
  expect(() => parseBootstrapPage(invalid)).toThrow();
});
