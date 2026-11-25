import { DatabaseSync } from "node:sqlite";

import { acknowledgeMutation } from "../../services/local-acknowledgement";
import { LOCAL_SCHEMA_V1 } from "../../services/local-schema";

const personId = "fb4fa281-8a94-4726-9ce7-02c18c90aa90";
const firstId = "fb4fa281-8a94-4726-9ce7-02c18c90aa91";
const secondId = "fb4fa281-8a94-4726-9ce7-02c18c90aa92";

function setup() {
  const sqlite = new DatabaseSync(":memory:");
  sqlite.exec(LOCAL_SCHEMA_V1);
  sqlite.exec("INSERT INTO bootstrap_generations(id,status) VALUES (1,'active'); INSERT INTO sync_state(singleton,active_generation,cursor,device_id) VALUES (1,1,4,'phone');");
  sqlite.prepare("INSERT INTO local_people(generation,sync_id,name,canonical_json) VALUES (1,?,?,?)")
    .run(personId, "Old", '{"name":"Old"}');
  for (const id of [firstId, secondId]) {
    sqlite.prepare("INSERT INTO sync_outbox(mutation_id,device_id,entity_kind,entity_sync_id,operation,changed_at,patch_json) VALUES (?,?,?,?,?,?,?)")
      .run(id, "phone", "person", personId, "update", "2026-11-25T10:00:00Z", '{"name":"Pending"}');
  }
  const database = {
    execAsync: async (sql: string) => { sqlite.exec(sql); },
    getFirstAsync: async <T,>(sql: string, ...values: (string | number | null)[]) => (sqlite.prepare(sql).get(...values) ?? null) as T | null,
    runAsync: async (sql: string, ...values: (string | number | null)[]) => {
      const outcome = sqlite.prepare(sql).run(...values);
      return { lastInsertRowId: Number(outcome.lastInsertRowid), changes: Number(outcome.changes) };
    },
  };
  return { sqlite, database };
}

it("commits canonical data and removes only the acknowledged mutation", async () => {
  const { sqlite, database } = setup();
  try {
    await acknowledgeMutation(database, { mutation_id: firstId, status: "applied", entity: {
      entity_kind: "person", sync_id: personId, server_id: 4, fields: { name: "Server" }, field_versions: {},
    } });
    expect(sqlite.prepare("SELECT name FROM local_people WHERE sync_id=?").get(personId)).toEqual({ name: "Server" });
    expect(sqlite.prepare("SELECT mutation_id FROM sync_outbox").get()).toEqual({ mutation_id: secondId });
  } finally { sqlite.close(); }
});

it("marks rejected edits as failed without discarding them", async () => {
  const { sqlite, database } = setup();
  try {
    await acknowledgeMutation(database, { mutation_id: firstId, status: "rejected_clock", entity: null });
    expect(sqlite.prepare("SELECT state,error_code FROM sync_outbox WHERE mutation_id=?").get(firstId))
      .toEqual({ state: "failed", error_code: "rejected_clock" });
    expect(sqlite.prepare("SELECT count(*) AS n FROM sync_outbox").get()).toEqual({ n: 2 });
  } finally { sqlite.close(); }
});

it("records a provisional outcome before removing that exact pending mutation", async () => {
  const { sqlite, database } = setup();
  try {
    await acknowledgeMutation(database, { mutation_id: firstId, status: "provisional", entity: null });
    expect(sqlite.prepare("SELECT entity_kind,entity_sync_id FROM local_provisional_changes WHERE mutation_id=?").get(firstId))
      .toEqual({ entity_kind: "person", entity_sync_id: personId });
    expect(sqlite.prepare("SELECT mutation_id FROM sync_outbox").get()).toEqual({ mutation_id: secondId });
  } finally { sqlite.close(); }
});

it("acknowledges an applied edit even when the record was subsequently deleted", async () => {
  const { sqlite, database } = setup();
  try {
    await acknowledgeMutation(database, { mutation_id: firstId, status: "applied", entity: null,
      target_state: { operation: "soft_delete", changed_at: "2026-11-25T10:05:00Z" } });
    expect(sqlite.prepare("SELECT is_deleted FROM local_people WHERE sync_id=?").get(personId)).toEqual({ is_deleted: 1 });
    expect(sqlite.prepare("SELECT operation FROM local_tombstones WHERE sync_id=?").get(personId)).toEqual({ operation: "soft_delete" });
    expect(sqlite.prepare("SELECT mutation_id FROM sync_outbox").get()).toEqual({ mutation_id: secondId });
  } finally { sqlite.close(); }
});

it("attaches the server ID to a locally created record without changing its UUID", async () => {
  const { sqlite, database } = setup();
  try {
    sqlite.prepare("UPDATE local_people SET is_local_only=1 WHERE sync_id=?").run(personId);
    sqlite.prepare("UPDATE sync_outbox SET operation='create' WHERE mutation_id=?").run(firstId);
    await acknowledgeMutation(database, { mutation_id: firstId, status: "applied", entity: {
      entity_kind: "person", sync_id: personId, server_id: 17, fields: { name: "New" }, field_versions: {},
    } });
    expect(sqlite.prepare("SELECT sync_id,server_id,is_local_only FROM local_people WHERE sync_id=?").get(personId))
      .toEqual({ sync_id: personId, server_id: 17, is_local_only: 0 });
  } finally { sqlite.close(); }
});
