import { DatabaseSync } from "node:sqlite";

import { LOCAL_SCHEMA_V1 } from "../../services/local-schema";
import { synchronizePull } from "../../services/sync-pull-worker";

it("pulls successive pages from the last committed cursor with one worker", async () => {
  const sqlite = new DatabaseSync(":memory:");
  sqlite.exec(LOCAL_SCHEMA_V1);
  sqlite.exec("INSERT INTO bootstrap_generations(id,status) VALUES (1,'active'); INSERT INTO sync_state(singleton,active_generation,cursor,device_id) VALUES (1,1,4,'phone');");
  const adapter = {
    execAsync: async (sql: string) => { sqlite.exec(sql); },
    getFirstAsync: async <T,>(sql: string, ...values: (string | number | null)[]) => (sqlite.prepare(sql).get(...values) ?? null) as T | null,
    runAsync: async (sql: string, ...values: (string | number | null)[]) => {
      const outcome = sqlite.prepare(sql).run(...values);
      return { lastInsertRowId: Number(outcome.lastInsertRowid), changes: Number(outcome.changes) };
    },
  };
  const fetchPage = jest.fn(async (cursor: number) => cursor === 4
    ? { changes: [{ sequence: 5, operation: "upsert", entity_kind: "organization",
        sync_id: "fb4fa281-8a94-4726-9ce7-02c18c90aa90", server_id: 1, fields: { name: "Company" }, field_versions: {} }],
        next_cursor: 5, has_more: true }
    : { changes: [], next_cursor: 8, has_more: false });
  try {
    await Promise.all([synchronizePull(adapter, fetchPage), synchronizePull(adapter, fetchPage)]);
    expect(fetchPage.mock.calls.map(([cursor]) => cursor)).toEqual([4, 5]);
    expect(sqlite.prepare("SELECT cursor FROM sync_state").get()).toEqual({ cursor: 8 });
    expect(sqlite.prepare("SELECT name FROM local_organizations").get()).toEqual({ name: "Company" });
  } finally { sqlite.close(); }
});
