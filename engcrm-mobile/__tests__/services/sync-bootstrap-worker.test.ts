import { DatabaseSync } from "node:sqlite";

import { LOCAL_SCHEMA_V1 } from "../../services/local-schema";
import { BootstrapExpiredError, synchronizeBootstrap } from "../../services/sync-bootstrap-worker";

function createDatabase() {
  const sqlite = new DatabaseSync(":memory:");
  sqlite.exec(LOCAL_SCHEMA_V1);
  return { sqlite, adapter: {
    execAsync: async (sql: string) => { sqlite.exec(sql); },
    getFirstAsync: async <T,>(sql: string, ...values: (string | number | null)[]) =>
      (sqlite.prepare(sql).get(...values) ?? null) as T | null,
    runAsync: async (sql: string, ...values: (string | number | null)[]) => {
      const outcome = sqlite.prepare(sql).run(...values);
      return { lastInsertRowId: Number(outcome.lastInsertRowid), changes: Number(outcome.changes) };
    },
  } };
}

it("downloads each page once and publishes it only after completion", async () => {
  const { sqlite, adapter } = createDatabase();
  const fetchPage = jest.fn(async (token: string | null) => token === null
    ? { high_water: 9, next_token: "second", entities: [{ entity_kind: "organization",
        sync_id: "fb4fa281-8a94-4726-9ce7-02c18c90aa90", server_id: 1, fields: { name: "Company" }, field_versions: {} }] }
    : { high_water: 9, next_token: null, entities: [] });
  try {
    await Promise.all([synchronizeBootstrap(adapter, "phone", fetchPage), synchronizeBootstrap(adapter, "phone", fetchPage)]);
    expect(fetchPage.mock.calls.map(([token]) => token)).toEqual([null, "second"]);
    expect(sqlite.prepare("SELECT cursor FROM sync_state").get()).toEqual({ cursor: 9 });
    expect(sqlite.prepare("SELECT name FROM local_organizations").get()).toEqual({ name: "Company" });
  } finally {
    sqlite.close();
  }
});

it("starts a fresh generation when a saved continuation expires and preserves the old data", async () => {
  const { sqlite, adapter } = createDatabase();
  sqlite.exec("INSERT INTO bootstrap_generations(id,status,continuation_token,high_water) VALUES (1,'loading','expired',9); INSERT INTO sync_state(singleton,cursor,device_id) VALUES (1,0,'phone');");
  const fetchPage = jest.fn(async (token: string | null) => {
    if (token === "expired") throw new BootstrapExpiredError();
    return { high_water: 12, next_token: null, entities: [] };
  });
  try {
    await synchronizeBootstrap(adapter, "phone", fetchPage);
    expect(fetchPage.mock.calls.map(([token]) => token)).toEqual(["expired", null]);
    expect(sqlite.prepare("SELECT status FROM bootstrap_generations WHERE id=1").get()).toEqual({ status: "abandoned" });
    expect(sqlite.prepare("SELECT cursor FROM sync_state").get()).toEqual({ cursor: 12 });
  } finally { sqlite.close(); }
});

it("resumes a partially downloaded bootstrap after a network failure", async () => {
  const { sqlite, adapter } = createDatabase();
  const fetchPage = jest.fn(async (token: string | null) => {
    if (token === null) return { high_water: 10, next_token: "second", entities: [] };
    throw new Error("offline");
  });
  try {
    await expect(synchronizeBootstrap(adapter, "phone", fetchPage)).rejects.toThrow("offline");
    const resume = jest.fn(async () => ({ high_water: 10, next_token: null, entities: [] }));
    await synchronizeBootstrap(adapter, "phone", resume);
    expect(resume).toHaveBeenCalledWith("second");
    expect(sqlite.prepare("SELECT cursor FROM sync_state").get()).toEqual({ cursor: 10 });
  } finally {
    sqlite.close();
  }
});
