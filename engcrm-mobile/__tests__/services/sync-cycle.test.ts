import { DatabaseSync } from "node:sqlite";

import { LOCAL_SCHEMA_V1 } from "../../services/local-schema";
import { synchronizeCycle } from "../../services/sync-cycle";

function setup() {
  const sqlite = new DatabaseSync(":memory:");
  sqlite.exec(LOCAL_SCHEMA_V1);
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

it("registers, bootstraps, then pulls once even when multiple triggers fire", async () => {
  const { sqlite, database } = setup();
  const network = {
    register: jest.fn(async () => {}),
    bootstrap: jest.fn(async () => ({ high_water: 4, next_token: null, entities: [] })),
    pull: jest.fn(async () => ({ changes: [], next_cursor: 5, has_more: false })),
  };
  try {
    await Promise.all([synchronizeCycle(database, "phone", network), synchronizeCycle(database, "phone", network)]);
    expect(network.register).toHaveBeenCalledTimes(1);
    expect(network.bootstrap).toHaveBeenCalledTimes(1);
    expect(network.pull).toHaveBeenCalledWith(4);
    expect(sqlite.prepare("SELECT cursor,last_success_at FROM sync_state").get()).toMatchObject({ cursor: 5, last_success_at: expect.any(String) });
  } finally { sqlite.close(); }
});

it("pushes and acknowledges pending edits before pulling newer changes", async () => {
  const { sqlite, database } = setup();
  const personId = "fb4fa281-8a94-4726-9ce7-02c18c90aa90";
  const mutationId = "fb4fa281-8a94-4726-9ce7-02c18c90aa91";
  sqlite.exec("INSERT INTO bootstrap_generations(id,status) VALUES (1,'active'); INSERT INTO sync_state(singleton,active_generation,cursor,device_id) VALUES (1,1,4,'phone');");
  sqlite.prepare("INSERT INTO local_people(generation,sync_id,server_id,name,canonical_json) VALUES (1,?,10,?,?)").run(personId, "Old", '{}');
  sqlite.prepare("INSERT INTO sync_outbox(mutation_id,device_id,entity_kind,entity_sync_id,operation,changed_at,patch_json) VALUES (?,?,?,?,?,?,?)")
    .run(mutationId, "phone", "person", personId, "update", "2026-11-25T10:00:00Z", '{"name":"New"}');
  const events: string[] = [];
  const network = {
    register: jest.fn(async () => {}), bootstrap: jest.fn(),
    push: jest.fn(async () => { events.push("push"); return { outcomes: [{ mutation_id: mutationId, status: "applied",
      entity: { entity_kind: "person", sync_id: personId, server_id: 5, fields: { name: "New" }, field_versions: {} } }] }; }),
    pull: jest.fn(async () => { events.push("pull"); return { changes: [], next_cursor: 5, has_more: false }; }),
  };
  try {
    await synchronizeCycle(database, "phone", network);
    expect(events).toEqual(["push", "pull"]);
    expect(sqlite.prepare("SELECT count(*) AS n FROM sync_outbox").get()).toEqual({ n: 0 });
    expect(sqlite.prepare("SELECT name FROM local_people WHERE sync_id=?").get(personId)).toEqual({ name: "New" });
  } finally { sqlite.close(); }
});

it("does not report success or discard pending changes when writes are not yet supported", async () => {
  const { sqlite, database } = setup();
  sqlite.exec("INSERT INTO bootstrap_generations(id,status) VALUES (1,'active'); INSERT INTO sync_state(singleton,active_generation,cursor,device_id) VALUES (1,1,4,'phone');");
  sqlite.exec("INSERT INTO sync_outbox(mutation_id,device_id,entity_kind,entity_sync_id,operation,changed_at,patch_json) VALUES ('m','phone','person','p','update','2026-11-25T10:00:00Z','{}');");
  const network = { register: jest.fn(async () => {}), bootstrap: jest.fn(), pull: jest.fn() };
  try {
    await expect(synchronizeCycle(database, "phone", network)).rejects.toThrow("pending");
    expect(sqlite.prepare("SELECT count(*) AS n FROM sync_outbox").get()).toEqual({ n: 1 });
    expect(sqlite.prepare("SELECT last_success_at FROM sync_state").get()).toEqual({ last_success_at: null });
    expect(network.pull).not.toHaveBeenCalled();
  } finally { sqlite.close(); }
});
