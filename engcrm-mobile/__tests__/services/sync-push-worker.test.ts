import { DatabaseSync } from "node:sqlite";

import { LOCAL_SCHEMA_V1 } from "../../services/local-schema";
import { synchronizeOutbox } from "../../services/sync-push-worker";

const personId = "fb4fa281-8a94-4726-9ce7-02c18c90aa90";
const firstId = "fb4fa281-8a94-4726-9ce7-02c18c90aa91";
const secondId = "fb4fa281-8a94-4726-9ce7-02c18c90aa92";

function setup() {
  const sqlite = new DatabaseSync(":memory:");
  sqlite.exec(LOCAL_SCHEMA_V1);
  sqlite.exec("INSERT INTO bootstrap_generations(id,status) VALUES (1,'active'); INSERT INTO sync_state(singleton,active_generation,cursor,device_id) VALUES (1,1,4,'phone');");
  sqlite.prepare("INSERT INTO local_people(generation,sync_id,server_id,name,canonical_json) VALUES (1,?,10,?,?)")
    .run(personId, "Old", '{"name":"Old"}');
  for (const id of [firstId, secondId]) {
    sqlite.prepare("INSERT INTO sync_outbox(mutation_id,device_id,entity_kind,entity_sync_id,operation,changed_at,patch_json) VALUES (?,?,?,?,?,?,?)")
      .run(id, "phone", "person", personId, "update", "2026-11-25T10:00:00Z", '{"name":"Pending"}');
  }
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

it("keeps a rejected mutation but acknowledges later independent mutations", async () => {
  const { sqlite, database } = setup();
  const push = jest.fn(async () => ({ outcomes: [
    { mutation_id: firstId, status: "rejected_clock", entity: null },
    { mutation_id: secondId, status: "applied", entity: { entity_kind: "person", sync_id: personId,
      server_id: 2, fields: { name: "Server" }, field_versions: {} } },
  ] }));
  try {
    await synchronizeOutbox(database, push);
    expect(push).toHaveBeenCalledTimes(1);
    expect(sqlite.prepare("SELECT mutation_id,state,error_code FROM sync_outbox").get())
      .toEqual({ mutation_id: firstId, state: "failed", error_code: "rejected_clock" });
    expect(sqlite.prepare("SELECT name FROM local_people WHERE sync_id=?").get(personId)).toEqual({ name: "Server" });
  } finally { sqlite.close(); }
});

it("does not acknowledge anything when the server returns a mismatched ID", async () => {
  const { sqlite, database } = setup();
  try {
    await expect(synchronizeOutbox(database, async () => ({ outcomes: [
      { mutation_id: firstId, status: "rejected_clock", entity: null },
      { mutation_id: firstId, status: "rejected_clock", entity: null },
    ] }))).rejects.toThrow();
    expect(sqlite.prepare("SELECT count(*) AS n FROM sync_outbox").get()).toEqual({ n: 2 });
    expect(sqlite.prepare("SELECT count(*) AS n FROM sync_outbox WHERE state='failed'").get()).toEqual({ n: 0 });
  } finally { sqlite.close(); }
});

it("accepts a deleted marker for an acknowledged edit while retaining a rejected edit", async () => {
  const { sqlite, database } = setup();
  try {
    await synchronizeOutbox(database, async () => ({ outcomes: [
      { mutation_id: firstId, status: "applied", entity: null,
        target_state: { operation: "soft_delete", changed_at: "2026-11-25T10:05:00Z", merge_target_sync_id: null } },
      { mutation_id: secondId, status: "rejected_clock", entity: null },
    ] }));
    expect(sqlite.prepare("SELECT is_deleted FROM local_people WHERE sync_id=?").get(personId)).toEqual({ is_deleted: 1 });
    expect(sqlite.prepare("SELECT mutation_id,state FROM sync_outbox").get()).toEqual({ mutation_id: secondId, state: "failed" });
  } finally { sqlite.close(); }
});

it("sends dependent operations in the order they were saved even if the device clock moved backwards", async () => {
  const { sqlite, database } = setup();
  try {
    sqlite.prepare("UPDATE sync_outbox SET changed_at=? WHERE mutation_id=?").run("2026-11-25T10:00:00Z", firstId);
    sqlite.prepare("UPDATE sync_outbox SET changed_at=? WHERE mutation_id=?").run("2026-11-25T09:59:00Z", secondId);
    const push = jest.fn(async (mutations: Record<string, unknown>[]) => ({ outcomes: mutations.map((entry) =>
      ({ mutation_id: entry.mutation_id, status: "rejected_clock", entity: null })) }));
    await synchronizeOutbox(database, push);
    expect(push.mock.calls[0][0].map((entry) => entry.mutation_id)).toEqual([firstId, secondId]);
  } finally { sqlite.close(); }
});

it("does not send a dependent person when its parent creation fails, but continues independent work", async () => {
  const { sqlite, database } = setup();
  const organizationId = "fb4fa281-8a94-4726-9ce7-02c18c90aa93";
  const childId = "fb4fa281-8a94-4726-9ce7-02c18c90aa94";
  const independentId = "fb4fa281-8a94-4726-9ce7-02c18c90aa95";
  try {
    sqlite.prepare("INSERT INTO local_organizations(generation,sync_id,name,canonical_json,is_local_only) VALUES (1,?,?,?,1)")
      .run(organizationId, "Parent", '{}');
    sqlite.prepare("INSERT INTO local_people(generation,sync_id,name,organization_sync_id,canonical_json,is_local_only) VALUES (1,?,?,?,?,1)")
      .run(childId, "Child", organizationId, '{}');
    sqlite.prepare("UPDATE sync_outbox SET entity_kind='organization',entity_sync_id=?,operation='create',patch_json=? WHERE mutation_id=?")
      .run(organizationId, '{"name":"Parent"}', firstId);
    sqlite.prepare("UPDATE sync_outbox SET entity_kind='person',entity_sync_id=?,operation='create',patch_json=? WHERE mutation_id=?")
      .run(childId, JSON.stringify({ name: "Child", organization_sync_id: organizationId }), secondId);
    sqlite.prepare("INSERT INTO sync_outbox(mutation_id,device_id,entity_kind,entity_sync_id,operation,changed_at,patch_json) VALUES (?,?,?,?,?,?,?)")
      .run(independentId, "phone", "person", personId, "update", "2026-11-25T10:00:01Z", '{"name":"Independent"}');
    const batches: string[][] = [];
    const push = async (entries: Record<string, unknown>[]) => {
      batches.push(entries.map((entry) => String(entry.mutation_id)));
      return { outcomes: entries.map((entry) => entry.mutation_id === firstId
        ? { mutation_id: firstId, status: "rejected_validation", entity: null }
        : { mutation_id: independentId, status: "applied", entity: { entity_kind: "person", sync_id: personId,
            server_id: 3, fields: { name: "Independent" }, field_versions: {} } }) };
    };
    await synchronizeOutbox(database, push);
    expect(batches.flat()).toEqual([firstId, independentId]);
    expect(sqlite.prepare("SELECT state FROM sync_outbox WHERE mutation_id=?").get(secondId)).toEqual({ state: "pending" });
    expect(sqlite.prepare("SELECT state FROM sync_outbox WHERE mutation_id=?").get(firstId)).toEqual({ state: "failed" });
  } finally { sqlite.close(); }
});

it("sends the dependent person after the parent receives its server ID", async () => {
  const { sqlite, database } = setup();
  const organizationId = "fb4fa281-8a94-4726-9ce7-02c18c90aa93";
  const childId = "fb4fa281-8a94-4726-9ce7-02c18c90aa94";
  try {
    sqlite.prepare("INSERT INTO local_organizations(generation,sync_id,name,canonical_json,is_local_only) VALUES (1,?,?,?,1)")
      .run(organizationId, "Parent", '{}');
    sqlite.prepare("INSERT INTO local_people(generation,sync_id,name,organization_sync_id,canonical_json,is_local_only) VALUES (1,?,?,?,?,1)")
      .run(childId, "Child", organizationId, '{}');
    sqlite.prepare("UPDATE sync_outbox SET entity_kind='organization',entity_sync_id=?,operation='create',patch_json=? WHERE mutation_id=?")
      .run(organizationId, '{"name":"Parent"}', firstId);
    sqlite.prepare("UPDATE sync_outbox SET entity_kind='person',entity_sync_id=?,operation='create',patch_json=? WHERE mutation_id=?")
      .run(childId, JSON.stringify({ name: "Child", organization_sync_id: organizationId }), secondId);
    const batches: string[][] = [];
    const push = async (entries: Record<string, unknown>[]) => {
      batches.push(entries.map((entry) => String(entry.mutation_id)));
      return { outcomes: entries.map((entry) => ({ mutation_id: entry.mutation_id, status: "applied",
        entity: entry.mutation_id === firstId
          ? { entity_kind: "organization", sync_id: organizationId, server_id: 20, fields: { name: "Parent" }, field_versions: {} }
          : { entity_kind: "person", sync_id: childId, server_id: 21, fields: { name: "Child", organization_sync_id: organizationId }, field_versions: {} } })) };
    };
    await synchronizeOutbox(database, push);
    expect(batches).toEqual([[firstId], [secondId]]);
    expect(sqlite.prepare("SELECT count(*) AS n FROM sync_outbox").get()).toEqual({ n: 0 });
  } finally { sqlite.close(); }
});
