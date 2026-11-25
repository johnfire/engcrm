import { DatabaseSync } from "node:sqlite";

import { LOCAL_SCHEMA_V1 } from "../../services/local-schema";
import { synchronizeReviewOutcomes } from "../../services/sync-review-worker";

const mutationId = "fb4fa281-8a94-4726-9ce7-02c18c90aa91";
const personId = "fb4fa281-8a94-4726-9ce7-02c18c90aa90";

function setup() {
  const sqlite = new DatabaseSync(":memory:");
  sqlite.exec(LOCAL_SCHEMA_V1);
  sqlite.prepare("INSERT INTO local_provisional_changes(mutation_id,entity_kind,entity_sync_id,changed_at) VALUES (?,'person',?,'2026-11-25T10:00:00Z')")
    .run(mutationId, personId);
  const database = {
    execAsync: async (sql: string) => { sqlite.exec(sql); },
    getFirstAsync: async <T,>(sql: string, ...values: (string | number | null)[]) => (sqlite.prepare(sql).get(...values) ?? null) as T | null,
    getAllAsync: async <T,>(sql: string, ...values: (string | number | null)[]) => sqlite.prepare(sql).all(...values) as T[],
    runAsync: async (sql: string, ...values: (string | number | null)[]) => {
      const result = sqlite.prepare(sql).run(...values);
      return { lastInsertRowId: Number(result.lastInsertRowid), changes: Number(result.changes) };
    },
  };
  return { sqlite, database };
}

it("records a reviewed outcome without losing its identity", async () => {
  const { sqlite, database } = setup();
  try {
    await synchronizeReviewOutcomes(database, async (ids) => {
      expect(ids).toEqual([mutationId]);
      return { outcomes: [{ mutation_id: mutationId, status: "applied" }] };
    });
    expect(sqlite.prepare("SELECT mutation_id,status FROM local_provisional_changes").get())
      .toEqual({ mutation_id: mutationId, status: "applied" });
  } finally { sqlite.close(); }
});

it("retains a pending item if the server omits it or the response is invalid", async () => {
  const { sqlite, database } = setup();
  try {
    await synchronizeReviewOutcomes(database, async () => ({ outcomes: [] }));
    await expect(synchronizeReviewOutcomes(database, async () => ({ outcomes: [{ mutation_id: "other", status: "applied" }] }))).rejects.toThrow();
    expect(sqlite.prepare("SELECT status FROM local_provisional_changes").get()).toEqual({ status: "review" });
  } finally { sqlite.close(); }
});

it("purges an erased target when that review outcome arrives", async () => {
  const { sqlite, database } = setup();
  try {
    sqlite.exec("INSERT INTO bootstrap_generations(id,status) VALUES (1,'active')");
    sqlite.prepare("INSERT INTO local_people(generation,sync_id,name,canonical_json) VALUES (1,?,'Private','{}')").run(personId);
    await synchronizeReviewOutcomes(database, async () => ({ outcomes: [{ mutation_id: mutationId, status: "erased" }] }));
    expect(sqlite.prepare("SELECT count(*) AS n FROM local_people").get()).toEqual({ n: 0 });
    expect(sqlite.prepare("SELECT operation FROM local_tombstones WHERE sync_id=?").get(personId)).toEqual({ operation: "hard_erase" });
  } finally { sqlite.close(); }
});
