import { DatabaseSync } from "node:sqlite";

import { beginBootstrap, saveBootstrapPage } from "../../services/local-bootstrap";
import { LOCAL_SCHEMA_V1 } from "../../services/local-schema";
import { parseBootstrapPage } from "../../services/sync-contracts";

const firstId = "fb4fa281-8a94-4726-9ce7-02c18c90aa90";
const secondId = "fb4fa281-8a94-4726-9ce7-02c18c90aa91";

function createDatabase() {
  const sqlite = new DatabaseSync(":memory:");
  sqlite.exec(LOCAL_SCHEMA_V1);
  const adapter = {
    execAsync: async (sql: string) => { sqlite.exec(sql); },
    getFirstAsync: async <T,>(sql: string, ...values: (string | number | null)[]) =>
      (sqlite.prepare(sql).get(...values) ?? null) as T | null,
    runAsync: async (sql: string, ...values: (string | number | null)[]) => {
      const outcome = sqlite.prepare(sql).run(...values);
      return { lastInsertRowId: Number(outcome.lastInsertRowid), changes: Number(outcome.changes) };
    },
  };
  return { sqlite, adapter };
}

it("keeps the old generation readable until the new bootstrap commits completely", async () => {
  const { sqlite, adapter } = createDatabase();
  try {
    sqlite.exec("INSERT INTO bootstrap_generations(id,status) VALUES (1,'active'); INSERT INTO sync_state(singleton,active_generation,cursor,device_id) VALUES (1,1,7,'phone');");
    const generation = await beginBootstrap(adapter, "phone");
    const firstPage = parseBootstrapPage({ high_water: 12, next_token: "next-page", entities: [
      { entity_kind: "organization", sync_id: firstId, server_id: 1, fields: { name: "New" }, field_versions: {} },
    ] });
    await saveBootstrapPage(adapter, generation.id, null, firstPage);
    expect(sqlite.prepare("SELECT active_generation,cursor FROM sync_state").get()).toEqual({ active_generation: 1, cursor: 7 });
    expect(await beginBootstrap(adapter, "phone")).toEqual({ id: generation.id, token: "next-page" });
    const finalPage = parseBootstrapPage({ high_water: 12, next_token: null, entities: [
      { entity_kind: "person", sync_id: secondId, server_id: 2, fields: { name: "Anna" }, field_versions: {} },
    ] });
    await saveBootstrapPage(adapter, generation.id, "next-page", finalPage);
    expect(sqlite.prepare("SELECT active_generation,cursor FROM sync_state").get())
      .toEqual({ active_generation: generation.id, cursor: 12 });
    expect(sqlite.prepare("SELECT status FROM bootstrap_generations WHERE id=1").get()).toEqual({ status: "retired" });
    expect(sqlite.prepare("SELECT count(*) AS n FROM local_people WHERE generation=?").get(generation.id)).toEqual({ n: 1 });
  } finally {
    sqlite.close();
  }
});

it("rolls back an incomplete page and keeps the previous cursor", async () => {
  const { sqlite, adapter } = createDatabase();
  try {
    sqlite.exec("INSERT INTO bootstrap_generations(id,status) VALUES (1,'active'); INSERT INTO sync_state(singleton,active_generation,cursor,device_id) VALUES (1,1,7,'phone');");
    const generation = await beginBootstrap(adapter, "phone");
    const page = parseBootstrapPage({ high_water: 12, next_token: null, entities: [
      { entity_kind: "organization", sync_id: firstId, server_id: 1, fields: { name: "Company" }, field_versions: {} },
      { entity_kind: "person_note", sync_id: secondId, server_id: 2, fields: { note: "Missing parent" }, field_versions: {} },
    ] });
    await expect(saveBootstrapPage(adapter, generation.id, null, page)).rejects.toThrow();
    expect(sqlite.prepare("SELECT count(*) AS n FROM local_organizations WHERE generation=?").get(generation.id)).toEqual({ n: 0 });
    expect(sqlite.prepare("SELECT active_generation,cursor FROM sync_state").get()).toEqual({ active_generation: 1, cursor: 7 });
  } finally {
    sqlite.close();
  }
});

it("serializes concurrent starts into one recoverable generation", async () => {
  const { sqlite, adapter } = createDatabase();
  try {
    const starts = await Promise.all([beginBootstrap(adapter, "phone"), beginBootstrap(adapter, "phone")]);
    expect(starts[0]).toEqual(starts[1]);
    expect(sqlite.prepare("SELECT count(*) AS n FROM bootstrap_generations WHERE status='loading'").get()).toEqual({ n: 1 });
  } finally {
    sqlite.close();
  }
});

it("does not switch generations if an edit was queued during bootstrap", async () => {
  const { sqlite, adapter } = createDatabase();
  try {
    sqlite.exec("INSERT INTO bootstrap_generations(id,status) VALUES (1,'active'); INSERT INTO sync_state(singleton,active_generation,cursor,device_id) VALUES (1,1,7,'phone');");
    const generation = await beginBootstrap(adapter, "phone");
    sqlite.exec("INSERT INTO sync_outbox(mutation_id,device_id,entity_kind,entity_sync_id,operation,changed_at,patch_json) VALUES ('m','phone','person','p','update','2026-11-25T10:00:00Z','{}');");
    const finalPage = parseBootstrapPage({ high_water: 12, next_token: null, entities: [] });
    await expect(saveBootstrapPage(adapter, generation.id, null, finalPage)).rejects.toThrow("pending");
    expect(sqlite.prepare("SELECT active_generation,cursor FROM sync_state").get()).toEqual({ active_generation: 1, cursor: 7 });
    expect(sqlite.prepare("SELECT count(*) AS n FROM sync_outbox").get()).toEqual({ n: 1 });
  } finally { sqlite.close(); }
});
