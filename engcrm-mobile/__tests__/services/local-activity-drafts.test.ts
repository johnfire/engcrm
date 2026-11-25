import { DatabaseSync } from "node:sqlite";

import { openActivityDraft, saveActivityDraft } from "../../services/local-activity-drafts";
import { queueLocalActivity } from "../../services/local-outbox";
import { LOCAL_SCHEMA_V1 } from "../../services/local-schema";

const personId = "fb4fa281-8a94-4726-9ce7-02c18c90aa90";
const deviceId = "fb4fa281-8a94-4726-9ce7-02c18c90aa91";
const draftId = "fb4fa281-8a94-4726-9ce7-02c18c90aa92";
const mutationId = "fb4fa281-8a94-4726-9ce7-02c18c90aa93";
const noteId = "fb4fa281-8a94-4726-9ce7-02c18c90aa94";

function setup() {
  const sqlite = new DatabaseSync(":memory:");
  sqlite.exec(LOCAL_SCHEMA_V1);
  sqlite.exec("INSERT INTO bootstrap_generations(id,status) VALUES (1,'active')");
  sqlite.prepare("INSERT INTO sync_state(singleton,active_generation,cursor,device_id) VALUES (1,1,0,?)").run(deviceId);
  sqlite.prepare("INSERT INTO local_people(generation,sync_id,name,canonical_json) VALUES (1,?,'Pat','{}')").run(personId);
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

it("restores an interrupted draft and keeps it after the activity is queued", async () => {
  const { sqlite, database } = setup();
  try {
    expect(await openActivityDraft(database, "person_note", personId, draftId)).toEqual({ id: draftId, values: {} });
    await saveActivityDraft(database, draftId, { note: "Met offline" });
    expect(await openActivityDraft(database, "person_note", personId, "another-id"))
      .toEqual({ id: draftId, values: { note: "Met offline" } });
    await queueLocalActivity(database, { mutationId, deviceId, entityKind: "person_note", entitySyncId: noteId,
      changedAt: "2026-11-25T10:00:00Z", patch: { person_sync_id: personId, note: "Met offline" }, draftId });
    expect(sqlite.prepare("SELECT state,draft_json FROM local_activity_drafts WHERE draft_id=?").get(draftId))
      .toEqual({ state: "saved", draft_json: '{"note":"Met offline"}' });
    expect(sqlite.prepare("SELECT count(*) AS n FROM sync_outbox").get()).toEqual({ n: 1 });
    await saveActivityDraft(database, draftId, { note: "late write" });
    expect(sqlite.prepare("SELECT state,draft_json FROM local_activity_drafts WHERE draft_id=?").get(draftId))
      .toEqual({ state: "saved", draft_json: '{"note":"Met offline"}' });
  } finally { sqlite.close(); }
});

it("rolls back the activity and outbox if the draft is no longer active", async () => {
  const { sqlite, database } = setup();
  try {
    await expect(queueLocalActivity(database, { mutationId, deviceId, entityKind: "person_note", entitySyncId: noteId,
      changedAt: "2026-11-25T10:00:00Z", patch: { person_sync_id: personId, note: "Met offline" }, draftId })).rejects.toThrow();
    expect(sqlite.prepare("SELECT count(*) AS n FROM local_person_notes").get()).toEqual({ n: 0 });
    expect(sqlite.prepare("SELECT count(*) AS n FROM sync_outbox").get()).toEqual({ n: 0 });
  } finally { sqlite.close(); }
});
