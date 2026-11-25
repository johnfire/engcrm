import { storeCanonicalEntity } from "./local-bootstrap";
import { type LocalDatabase, withLocalWrite } from "./local-transaction";
import type { PullPage, SyncChange, SyncEntityKind } from "./sync-contracts";

const ENTITY_TABLES: Record<SyncEntityKind, string> = {
  organization: "local_organizations", person: "local_people", deal: "local_deals",
  organization_activity: "local_organization_activities", person_note: "local_person_notes",
};

export async function purgeErasedEntity(database: LocalDatabase, kind: SyncEntityKind, syncId: string): Promise<void> {
  if (kind === "person" || kind === "organization") {
    const history = kind === "person" ? "local_person_notes" : "local_organization_activities";
    const parent = kind === "person" ? "person_sync_id" : "organization_sync_id";
    const historyKind = kind === "person" ? "person_note" : "organization_activity";
    await database.runAsync(`DELETE FROM sync_outbox WHERE entity_kind=? AND entity_sync_id IN (SELECT sync_id FROM ${history} WHERE ${parent}=?)`, historyKind, syncId);
    await database.runAsync(`DELETE FROM sync_outbox WHERE entity_kind='deal' AND entity_sync_id IN (SELECT sync_id FROM local_deals WHERE ${parent}=?)`, syncId);
    await database.runAsync(`DELETE FROM ${history} WHERE ${parent}=?`, syncId);
    await database.runAsync(`DELETE FROM local_deals WHERE ${parent}=?`, syncId);
  }
  await database.runAsync("DELETE FROM sync_outbox WHERE entity_kind=? AND entity_sync_id=?", kind, syncId);
  await database.runAsync("DELETE FROM local_provisional_changes WHERE entity_kind=? AND entity_sync_id=?", kind, syncId);
  await database.runAsync(`DELETE FROM ${ENTITY_TABLES[kind]} WHERE sync_id=?`, syncId);
}

async function applyChange(database: LocalDatabase, generation: number, change: SyncChange): Promise<void> {
  if (change.operation === "upsert") {
    const marker = await database.getFirstAsync<{ operation: string }>(
      "SELECT operation FROM local_tombstones WHERE entity_kind=? AND sync_id=?", change.entity_kind, change.sync_id,
    );
    if (marker?.operation === "hard_erase") throw new Error("Server attempted to restore an erased record");
    await storeCanonicalEntity(database, generation, change);
    return;
  }
  await applyDeletionMarker(database, change);
}

export async function applyDeletionMarker(database: LocalDatabase, change: Exclude<SyncChange, { operation: "upsert" }>): Promise<void> {
  if (change.operation === "hard_erase") await purgeErasedEntity(database, change.entity_kind, change.sync_id);
  else await database.runAsync(`UPDATE ${ENTITY_TABLES[change.entity_kind]} SET is_deleted=1 WHERE sync_id=?`, change.sync_id);
  await database.runAsync(
    "INSERT INTO local_tombstones(entity_kind,sync_id,operation,changed_at,merge_target_sync_id) VALUES (?,?,?,?,?) " +
    "ON CONFLICT(entity_kind,sync_id) DO UPDATE SET operation=excluded.operation,changed_at=excluded.changed_at,merge_target_sync_id=excluded.merge_target_sync_id",
    change.entity_kind, change.sync_id, change.operation, change.changed_at, change.merge_target_sync_id ?? null,
  );
}

export function savePullPage(database: LocalDatabase, expectedCursor: number, page: PullPage): Promise<void> {
  return withLocalWrite(database, async () => {
    const state = await database.getFirstAsync<{ active_generation: number | null; cursor: number }>(
      "SELECT active_generation,cursor FROM sync_state WHERE singleton=1",
    );
    if (!state || state.active_generation === null || state.cursor !== expectedCursor ||
        page.next_cursor < expectedCursor || page.changes.some((change) => change.sequence <= expectedCursor)) {
      throw new Error("Sync page does not match the saved cursor");
    }
    for (const change of page.changes) await applyChange(database, state.active_generation, change);
    await database.runAsync("UPDATE sync_state SET cursor=? WHERE singleton=1", page.next_cursor);
  });
}
