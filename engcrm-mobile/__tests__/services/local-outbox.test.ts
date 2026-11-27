import { DatabaseSync } from "node:sqlite";

import { queueLocalActivity, queueLocalCreate, queueLocalCreateWithInitialDeal, queueLocalUpdate, readPendingOverlay } from "../../services/local-outbox";
import { LOCAL_SCHEMA_V1 } from "../../services/local-schema";
import { withLocalWrite } from "../../services/local-transaction";

const personId = "fb4fa281-8a94-4726-9ce7-02c18c90aa90";
const deviceId = "fb4fa281-8a94-4726-9ce7-02c18c90aa91";
const mutationId = "fb4fa281-8a94-4726-9ce7-02c18c90aa92";

function setup() {
  const sqlite = new DatabaseSync(":memory:");
  sqlite.exec(LOCAL_SCHEMA_V1);
  sqlite.exec("INSERT INTO bootstrap_generations(id,status) VALUES (1,'active');");
  sqlite.prepare("INSERT INTO sync_state(singleton,active_generation,cursor,device_id) VALUES (1,1,4,?)").run(deviceId);
  sqlite.prepare("INSERT INTO local_people(generation,sync_id,name,canonical_json) VALUES (1,?,?,?)")
    .run(personId, "Old", '{"name":"Old"}');
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

it("preserves the canonical value while making a queued edit visible", async () => {
  const { sqlite, database } = setup();
  try {
    await queueLocalUpdate(database, { mutationId, deviceId, entityKind: "person", entitySyncId: personId,
      changedAt: "2026-11-25T10:00:00Z", patch: { name: "Pending", phone: "123" } });
    expect(sqlite.prepare("SELECT name FROM local_people WHERE sync_id=?").get(personId)).toEqual({ name: "Old" });
    expect(await readPendingOverlay(database, "person", personId, { name: "New server", city: "Augsburg" }))
      .toEqual({ name: "Pending", phone: "123", city: "Augsburg" });
    expect(sqlite.prepare("SELECT count(*) AS n FROM sync_outbox").get()).toEqual({ n: 1 });
  } finally { sqlite.close(); }
});

it("rejects an unknown field without creating an outbox entry", async () => {
  const { sqlite, database } = setup();
  try {
    await expect(queueLocalUpdate(database, { mutationId, deviceId, entityKind: "person", entitySyncId: personId,
      changedAt: "2026-11-25T10:00:00Z", patch: { deleted_at: "now" } })).rejects.toThrow();
    expect(sqlite.prepare("SELECT count(*) AS n FROM sync_outbox").get()).toEqual({ n: 0 });
  } finally { sqlite.close(); }
});

it("orders edits by actual time even when timestamps use different offsets", async () => {
  const { sqlite, database } = setup();
  try {
    await queueLocalUpdate(database, { mutationId, deviceId, entityKind: "person", entitySyncId: personId,
      changedAt: "2026-11-25T10:00:00+01:00", patch: { name: "Earlier" } });
    await queueLocalUpdate(database, { mutationId: "fb4fa281-8a94-4726-9ce7-02c18c90aa93", deviceId,
      entityKind: "person", entitySyncId: personId, changedAt: "2026-11-25T09:30:00Z", patch: { name: "Later" } });
    expect(await readPendingOverlay(database, "person", personId, { name: "Server" })).toEqual({ name: "Later" });
  } finally { sqlite.close(); }
});

it("does not expose an overlay from a transaction that later rolls back", async () => {
  const { sqlite, database } = setup();
  let release!: () => void;
  let started!: () => void;
  const waiting = new Promise<void>((resolve) => { release = resolve; });
  const entered = new Promise<void>((resolve) => { started = resolve; });
  try {
    const write = withLocalWrite(database, async () => {
      await database.runAsync("INSERT INTO sync_outbox(mutation_id,device_id,entity_kind,entity_sync_id,operation,changed_at,patch_json) VALUES (?,?,?,?,'update',?,?)",
        mutationId, deviceId, "person", personId, "2026-11-25T10:00:00Z", '{"name":"Uncommitted"}');
      started();
      await waiting;
      throw new Error("interrupted");
    });
    const handledWrite = write.catch(() => undefined);
    await entered;
    const read = readPendingOverlay(database, "person", personId, { name: "Server" });
    release();
    await handledWrite;
    expect(await read).toEqual({ name: "Server" });
  } finally { sqlite.close(); }
});

it("creates a local person and its pending operation atomically", async () => {
  const { sqlite, database } = setup();
  const newPerson = "fb4fa281-8a94-4726-9ce7-02c18c90aa94";
  try {
    await queueLocalCreate(database, { mutationId, deviceId, entityKind: "person", entitySyncId: newPerson,
      changedAt: "2026-11-25T10:00:00Z", patch: { name: "Offline person", phone: "123" } });
    expect(sqlite.prepare("SELECT name,server_id,is_local_only FROM local_people WHERE sync_id=?").get(newPerson))
      .toEqual({ name: "Offline person", server_id: null, is_local_only: 1 });
    const canonical = sqlite.prepare("SELECT canonical_json FROM local_people WHERE sync_id=?").get(newPerson) as { canonical_json: string };
    expect(JSON.parse(canonical.canonical_json).created_at).toBe("2026-11-25T10:00:00.000Z");
    expect(sqlite.prepare("SELECT operation,entity_sync_id FROM sync_outbox WHERE mutation_id=?").get(mutationId))
      .toEqual({ operation: "create", entity_sync_id: newPerson });
    await expect(queueLocalCreate(database, { mutationId, deviceId, entityKind: "organization",
      entitySyncId: "fb4fa281-8a94-4726-9ce7-02c18c90aa95", changedAt: "2026-11-25T10:00:00Z",
      patch: { name: "Must roll back" } })).rejects.toThrow();
    expect(sqlite.prepare("SELECT count(*) AS n FROM local_organizations").get()).toEqual({ n: 0 });
  } finally { sqlite.close(); }
});

it("stores a person note locally with its original timestamp and pending mutation", async () => {
  const { sqlite, database } = setup();
  const noteId = "fb4fa281-8a94-4726-9ce7-02c18c90aa94";
  try {
    await queueLocalActivity(database, { mutationId, deviceId, entityKind: "person_note", entitySyncId: noteId,
      changedAt: "2026-11-25T10:00:00Z", patch: { person_sync_id: personId, note: "Met offline", method: "visit" } });
    expect(sqlite.prepare("SELECT person_sync_id,occurred_at,is_local_only FROM local_person_notes WHERE sync_id=?").get(noteId))
      .toEqual({ person_sync_id: personId, occurred_at: "2026-11-25T10:00:00.000Z", is_local_only: 1 });
    expect(sqlite.prepare("SELECT operation,entity_kind FROM sync_outbox WHERE mutation_id=?").get(mutationId))
      .toEqual({ operation: "create", entity_kind: "person_note" });
  } finally { sqlite.close(); }
});

it("creates a person and their initial deal in the same transaction", async () => {
  const { sqlite, database } = setup();
  const newPerson = "fb4fa281-8a94-4726-9ce7-02c18c90aa94";
  const dealId = "fb4fa281-8a94-4726-9ce7-02c18c90aa95";
  try {
    await queueLocalCreateWithInitialDeal(database, { mutationId, deviceId, entityKind: "person", entitySyncId: newPerson,
      changedAt: "2026-11-25T10:00:00Z", patch: { name: "New person" } }, {
      mutationId: "fb4fa281-8a94-4726-9ce7-02c18c90aa96", entitySyncId: dealId,
      offerSlug: "consulting", stage: "prospect", status: "meeting",
    });
    expect(sqlite.prepare("SELECT person_sync_id,offer_slug,pipeline_stage FROM local_deals WHERE sync_id=?").get(dealId))
      .toEqual({ person_sync_id: newPerson, offer_slug: "consulting", pipeline_stage: "prospect" });
    expect(sqlite.prepare("SELECT count(*) AS n FROM sync_outbox").get()).toEqual({ n: 2 });
  } finally { sqlite.close(); }
});

it("queues a deal's next step together with its follow-up type", async () => {
  const { sqlite, database } = setup();
  const dealId = "fb4fa281-8a94-4726-9ce7-02c18c90aa94";
  try {
    sqlite.prepare("INSERT INTO local_deals(generation,sync_id,canonical_json) VALUES (1,?,'{}')").run(dealId);
    await queueLocalUpdate(database, { mutationId, deviceId, entityKind: "deal", entitySyncId: dealId,
      changedAt: "2026-11-27T10:00:00Z", patch: { next_step: "Call", next_step_date: null, task_type: "check_in" } });
    const queued = sqlite.prepare("SELECT patch_json FROM sync_outbox").get() as { patch_json: string };
    expect(JSON.parse(queued.patch_json)).toEqual({ next_step: "Call", next_step_date: null, task_type: "check_in" });
  } finally { sqlite.close(); }
});
