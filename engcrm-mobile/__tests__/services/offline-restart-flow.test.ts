import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";

import { queueLocalActivity, queueLocalCreate, queueLocalCreateWithInitialDeal } from "../../services/local-outbox";
import { LOCAL_SCHEMA_V1 } from "../../services/local-schema";
import { synchronizeOutbox } from "../../services/sync-push-worker";

const id = (last: string) => `fb4fa281-8a94-4726-9ce7-02c18c90aa${last}`;
const deviceId = id("90"), organizationId = id("91"), personId = id("92"), dealId = id("93"), activityId = id("94");
const savedAt = "2026-11-25T10:00:00Z";

function adapter(sqlite: DatabaseSync) {
  return {
    execAsync: async (sql: string) => { sqlite.exec(sql); },
    getFirstAsync: async <T,>(sql: string, ...values: (string | number | null)[]) => (sqlite.prepare(sql).get(...values) ?? null) as T | null,
    getAllAsync: async <T,>(sql: string, ...values: (string | number | null)[]) => sqlite.prepare(sql).all(...values) as T[],
    runAsync: async (sql: string, ...values: (string | number | null)[]) => {
      const result = sqlite.prepare(sql).run(...values);
      return { lastInsertRowId: Number(result.lastInsertRowid), changes: Number(result.changes) };
    },
  };
}

it("survives restart and a lost acknowledgement without losing or duplicating offline work", async () => {
  const file = join(mkdtempSync(join(tmpdir(), "engcrm-offline-test-")), "test.sqlite");
  let sqlite = new DatabaseSync(file);
  sqlite.exec(LOCAL_SCHEMA_V1);
  sqlite.exec("INSERT INTO bootstrap_generations(id,status) VALUES (1,'active')");
  sqlite.prepare("INSERT INTO sync_state(singleton,active_generation,cursor,device_id) VALUES (1,1,0,?)").run(deviceId);
  let database = adapter(sqlite);
  const ledger = new Map<string, Record<string, unknown>>();
  let lostReply = true;
  const push = async (mutations: Record<string, unknown>[]) => {
    const outcomes = mutations.map((mutation) => {
      const mutationId = String(mutation.mutation_id);
      if (!ledger.has(mutationId)) ledger.set(mutationId, { mutation_id: mutationId, status: "applied", entity: {
        entity_kind: mutation.entity_kind, sync_id: mutation.entity_sync_id, server_id: ledger.size + 1,
        fields: mutation.patch, field_versions: {},
      } });
      return ledger.get(mutationId);
    });
    if (lostReply) { lostReply = false; throw new Error("Reply lost after server accepted the batch"); }
    return { outcomes };
  };
  try {
    await queueLocalCreateWithInitialDeal(database, { mutationId: id("95"), deviceId, entityKind: "organization",
      entitySyncId: organizationId, changedAt: savedAt, patch: { name: "Company" } },
    { mutationId: id("96"), entitySyncId: dealId, offerSlug: "consulting", stage: "candidate", status: "none" });
    await queueLocalCreate(database, { mutationId: id("97"), deviceId, entityKind: "person", entitySyncId: personId,
      changedAt: savedAt, patch: { name: "Pat", organization_sync_id: organizationId } });
    await queueLocalActivity(database, { mutationId: id("98"), deviceId, entityKind: "organization_activity", entitySyncId: activityId,
      changedAt: savedAt, patch: { organization_sync_id: organizationId, summary: "Visited" } });
    await expect(synchronizeOutbox(database, push)).rejects.toThrow("Reply lost");
    expect(sqlite.prepare("SELECT count(*) AS n FROM sync_outbox").get()).toEqual({ n: 4 });
    sqlite.close();
    sqlite = new DatabaseSync(file);
    database = adapter(sqlite);
    expect(sqlite.prepare("SELECT name FROM local_people WHERE sync_id=?").get(personId)).toEqual({ name: "Pat" });
    await synchronizeOutbox(database, push);
    expect(sqlite.prepare("SELECT count(*) AS n FROM sync_outbox").get()).toEqual({ n: 0 });
    expect(sqlite.prepare("SELECT count(*) AS n FROM local_organizations WHERE sync_id=?").get(organizationId)).toEqual({ n: 1 });
    expect(sqlite.prepare("SELECT count(*) AS n FROM local_person_notes").get()).toEqual({ n: 0 });
    expect(sqlite.prepare("SELECT count(*) AS n FROM local_organization_activities WHERE sync_id=?").get(activityId)).toEqual({ n: 1 });
    expect(ledger.size).toBe(4);
  } finally { sqlite.close(); }
});
