import { type LocalDatabase, withLocalWrite } from "./local-transaction";

type ActivityKind = "person_note" | "organization_activity";
export interface ActivityDraft { id: string; values: Record<string, unknown> }

export function openActivityDraft(database: LocalDatabase, kind: ActivityKind, parentSyncId: string, newId: string): Promise<ActivityDraft> {
  return withLocalWrite(database, async () => {
    const existing = await database.getFirstAsync<{ draft_id: string; draft_json: string }>(
      "SELECT draft_id,draft_json FROM local_activity_drafts WHERE entity_kind=? AND parent_sync_id=? AND state='active'", kind, parentSyncId,
    );
    if (existing) return { id: existing.draft_id, values: JSON.parse(existing.draft_json) };
    await database.runAsync("INSERT INTO local_activity_drafts(draft_id,entity_kind,parent_sync_id,draft_json) VALUES (?,?,?,'{}')",
      newId, kind, parentSyncId);
    return { id: newId, values: {} };
  });
}

export function saveActivityDraft(database: LocalDatabase, draftId: string, values: Record<string, unknown>): Promise<void> {
  const encoded = JSON.stringify(values);
  if (encoded.length > 100_000) return Promise.reject(new Error("Offline draft is too large"));
  return withLocalWrite(database, async () => {
    const updated = await database.runAsync("UPDATE local_activity_drafts SET draft_json=?,updated_at=CURRENT_TIMESTAMP " +
      "WHERE draft_id=? AND state='active'", encoded, draftId);
    if (updated.changes === 0) {
      const existing = await database.getFirstAsync<{ state: string }>("SELECT state FROM local_activity_drafts WHERE draft_id=?", draftId);
      if (!existing) throw new Error("Offline activity draft is no longer available");
    }
  });
}
