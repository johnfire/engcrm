import { DatabaseSync } from "node:sqlite";

import { listLocalRecords, readLocalRecord } from "../../services/local-records";
import { LOCAL_SCHEMA_V1 } from "../../services/local-schema";

const syncId = "fb4fa281-8a94-4726-9ce7-02c18c90aa90";

function setup() {
  const sqlite = new DatabaseSync(":memory:");
  sqlite.exec(LOCAL_SCHEMA_V1);
  sqlite.exec("INSERT INTO bootstrap_generations(id,status) VALUES (1,'active'),(2,'retired'); " +
    "INSERT INTO sync_state(singleton,active_generation,cursor,device_id) VALUES (1,1,4,'phone');");
  sqlite.prepare("INSERT INTO local_people(generation,sync_id,server_id,name,canonical_json) VALUES (1,?,7,'Server',?)")
    .run(syncId, '{"name":"Server","city":"Munich"}');
  const database = {
    execAsync: async (sql: string) => { sqlite.exec(sql); },
    getFirstAsync: async <T,>(sql: string, ...values: (string | number | null)[]) => (sqlite.prepare(sql).get(...values) ?? null) as T | null,
    getAllAsync: async <T,>(sql: string, ...values: (string | number | null)[]) => sqlite.prepare(sql).all(...values) as T[],
    runAsync: async (sql: string, ...values: (string | number | null)[]) => {
      const outcome = sqlite.prepare(sql).run(...values);
      return { lastInsertRowId: Number(outcome.lastInsertRowid), changes: Number(outcome.changes) };
    },
  };
  return { sqlite, database };
}

it("reads the active generation with pending and failed edits overlaid", async () => {
  const { sqlite, database } = setup();
  try {
    sqlite.prepare("INSERT INTO sync_outbox(mutation_id,device_id,entity_kind,entity_sync_id,operation,changed_at,patch_json,state) " +
      "VALUES ('one','phone','person',?,'update','2026-11-25T10:00:00Z',?,'failed')").run(syncId, '{"name":"Local"}');
    expect(await readLocalRecord(database, "person", syncId)).toEqual({ syncId, serverId: 7, isLocalOnly: false,
      fields: { name: "Local", city: "Munich" }, pendingCount: 1, failedCount: 1 });
  } finally { sqlite.close(); }
});

it("does not expose deleted records or an old generation", async () => {
  const { sqlite, database } = setup();
  try {
    sqlite.prepare("UPDATE local_people SET is_deleted=1 WHERE sync_id=?").run(syncId);
    sqlite.prepare("INSERT INTO local_people(generation,sync_id,name,canonical_json) VALUES (2,?,'Old','{}')").run(syncId);
    expect(await readLocalRecord(database, "person", syncId)).toBeNull();
  } finally { sqlite.close(); }
});

it("lists only active records with their own pending overlays", async () => {
  const { sqlite, database } = setup();
  try {
    sqlite.prepare("INSERT INTO local_people(generation,sync_id,name,canonical_json,is_local_only) VALUES (1,'new','New',?,1)")
      .run('{"name":"New"}');
    sqlite.prepare("INSERT INTO sync_outbox(mutation_id,device_id,entity_kind,entity_sync_id,operation,changed_at,patch_json) " +
      "VALUES ('one','phone','person',?,'update','2026-11-25T10:00:00Z',?)").run(syncId, '{"name":"Edited"}');
    sqlite.prepare("INSERT INTO local_people(generation,sync_id,name,canonical_json,is_deleted) VALUES (1,'deleted','Deleted','{}',1)").run();
    const records = await listLocalRecords(database, "person");
    expect(records.map((record) => [record.syncId, record.fields.name, record.pendingCount, record.isLocalOnly]))
      .toEqual([[syncId, "Edited", 1, false], ["new", "New", 0, true]]);
  } finally { sqlite.close(); }
});
