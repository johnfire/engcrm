import { DatabaseSync } from "node:sqlite";

import { savePullPage } from "../../services/local-pull";
import { LOCAL_SCHEMA_V1 } from "../../services/local-schema";
import { parsePullPage } from "../../services/sync-contracts";

const personId = "fb4fa281-8a94-4726-9ce7-02c18c90aa90";
const mutationId = "fb4fa281-8a94-4726-9ce7-02c18c90aa91";

function setup() {
  const sqlite = new DatabaseSync(":memory:");
  sqlite.exec(LOCAL_SCHEMA_V1);
  sqlite.exec("INSERT INTO bootstrap_generations(id,status) VALUES (1,'active'); INSERT INTO sync_state(singleton,active_generation,cursor,device_id) VALUES (1,1,5,'phone');");
  sqlite.prepare("INSERT INTO local_people(generation,sync_id,name,canonical_json) VALUES (1,?,?,?)")
    .run(personId, "Old", '{"name":"Old"}');
  sqlite.prepare("INSERT INTO sync_outbox(mutation_id,device_id,entity_kind,entity_sync_id,operation,changed_at,patch_json) VALUES (?,?,?,?,?,?,?)")
    .run(mutationId, "phone", "person", personId, "update", "2026-11-25T10:00:00Z", '{"name":"Pending"}');
  const adapter = {
    execAsync: async (sql: string) => { sqlite.exec(sql); },
    getFirstAsync: async <T,>(sql: string, ...values: (string | number | null)[]) => (sqlite.prepare(sql).get(...values) ?? null) as T | null,
    runAsync: async (sql: string, ...values: (string | number | null)[]) => {
      const outcome = sqlite.prepare(sql).run(...values);
      return { lastInsertRowId: Number(outcome.lastInsertRowid), changes: Number(outcome.changes) };
    },
  };
  return { sqlite, adapter };
}

it("updates canonical data and cursor without removing an unsent overlay", async () => {
  const { sqlite, adapter } = setup();
  try {
    const page = parsePullPage({ next_cursor: 6, has_more: false, changes: [{ sequence: 6, operation: "upsert",
      entity_kind: "person", sync_id: personId, server_id: 4, fields: { name: "Server" }, field_versions: {} }] });
    await savePullPage(adapter, 5, page);
    expect(sqlite.prepare("SELECT name FROM local_people WHERE sync_id=?").get(personId)).toEqual({ name: "Server" });
    expect(sqlite.prepare("SELECT patch_json FROM sync_outbox WHERE mutation_id=?").get(mutationId)).toEqual({ patch_json: '{"name":"Pending"}' });
    expect(sqlite.prepare("SELECT cursor FROM sync_state").get()).toEqual({ cursor: 6 });
  } finally { sqlite.close(); }
});

it("retains soft-deleted data and pending edits for review", async () => {
  const { sqlite, adapter } = setup();
  try {
    const page = parsePullPage({ next_cursor: 6, has_more: false, changes: [{ sequence: 6, operation: "soft_delete",
      entity_kind: "person", sync_id: personId, changed_at: "2026-11-25T12:00:00Z" }] });
    await savePullPage(adapter, 5, page);
    expect(sqlite.prepare("SELECT name,is_deleted FROM local_people WHERE sync_id=?").get(personId)).toEqual({ name: "Old", is_deleted: 1 });
    expect(sqlite.prepare("SELECT count(*) AS n FROM sync_outbox").get()).toEqual({ n: 1 });
  } finally { sqlite.close(); }
});

it("purges erased data and its pending mutation across generations", async () => {
  const { sqlite, adapter } = setup();
  try {
    sqlite.exec("INSERT INTO bootstrap_generations(id,status) VALUES (2,'retired')");
    sqlite.prepare("INSERT INTO local_people(generation,sync_id,name,canonical_json) VALUES (2,?,?,?)").run(personId, "Old copy", '{}');
    sqlite.prepare("INSERT INTO local_activity_drafts(draft_id,entity_kind,parent_sync_id,draft_json) VALUES ('draft','person_note',?,?)")
      .run(personId, '{"note":"Private draft"}');
    const page = parsePullPage({ next_cursor: 6, has_more: false, changes: [{ sequence: 6, operation: "hard_erase",
      entity_kind: "person", sync_id: personId, changed_at: "2026-11-25T12:00:00Z" }] });
    await savePullPage(adapter, 5, page);
    expect(sqlite.prepare("SELECT count(*) AS n FROM local_people WHERE sync_id=?").get(personId)).toEqual({ n: 0 });
    expect(sqlite.prepare("SELECT count(*) AS n FROM sync_outbox").get()).toEqual({ n: 0 });
    expect(sqlite.prepare("SELECT count(*) AS n FROM local_activity_drafts").get()).toEqual({ n: 0 });
    expect(sqlite.prepare("SELECT cursor FROM sync_state").get()).toEqual({ cursor: 6 });
  } finally { sqlite.close(); }
});

it("does not discard another kind's pending edit when UUIDs happen to match", async () => {
  const { sqlite, adapter } = setup();
  try {
    sqlite.prepare("INSERT INTO local_person_notes(generation,sync_id,person_sync_id,canonical_json) VALUES (1,?,?,?)")
      .run("same-id", personId, '{}');
    sqlite.prepare("INSERT INTO sync_outbox(mutation_id,device_id,entity_kind,entity_sync_id,operation,changed_at,patch_json) VALUES (?,?,?,?,?,?,?)")
      .run("other-mutation", "phone", "organization", "same-id", "update", "2026-11-25T10:00:00Z", '{}');
    const page = parsePullPage({ next_cursor: 6, has_more: false, changes: [{ sequence: 6, operation: "hard_erase",
      entity_kind: "person", sync_id: personId, changed_at: "2026-11-25T12:00:00Z" }] });
    await savePullPage(adapter, 5, page);
    expect(sqlite.prepare("SELECT entity_kind FROM sync_outbox WHERE mutation_id='other-mutation'").get())
      .toEqual({ entity_kind: "organization" });
  } finally { sqlite.close(); }
});
