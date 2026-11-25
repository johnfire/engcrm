import { DatabaseSync } from "node:sqlite";

import { LOCAL_SCHEMA_V1 } from "../../services/local-schema";
import { readSyncStatus } from "../../services/sync-status";

it("reports pending, failed and review counts without claiming unsent work is synced", async () => {
  const sqlite = new DatabaseSync(":memory:");
  sqlite.exec(LOCAL_SCHEMA_V1);
  sqlite.exec("INSERT INTO bootstrap_generations(id,status) VALUES (1,'active'); " +
    "INSERT INTO sync_state(singleton,active_generation,cursor,device_id,last_success_at) VALUES (1,1,4,'phone','2026-11-25T10:00:00Z'); " +
    "INSERT INTO sync_outbox(mutation_id,device_id,entity_kind,entity_sync_id,operation,changed_at,patch_json,state) VALUES " +
    "('one','phone','person','p','update','2026-11-25T10:01:00Z','{}','pending')," +
    "('two','phone','person','p','update','2026-11-25T10:02:00Z','{}','failed'); " +
    "INSERT INTO local_provisional_changes(mutation_id,entity_kind,entity_sync_id,changed_at) VALUES ('three','person','p','2026-11-25T10:03:00Z');");
  const database = {
    execAsync: async (sql: string) => { sqlite.exec(sql); },
    getFirstAsync: async <T,>(sql: string, ...values: (string | number | null)[]) => (sqlite.prepare(sql).get(...values) ?? null) as T | null,
    runAsync: async (sql: string, ...values: (string | number | null)[]) => {
      const result = sqlite.prepare(sql).run(...values);
      return { lastInsertRowId: Number(result.lastInsertRowid), changes: Number(result.changes) };
    },
  };
  try {
    expect(await readSyncStatus(database)).toEqual({ ready: true, pending: 1, failed: 1, review: 1,
      lastSuccessAt: "2026-11-25T10:00:00Z", upToDate: false });
  } finally { sqlite.close(); }
});
