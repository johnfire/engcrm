import { type LocalBindValue, type LocalDatabase, withLocalRead } from "./local-transaction";
import type { SyncEntityKind } from "./sync-contracts";

interface RecordsDatabase extends LocalDatabase {
  getAllAsync<T>(sql: string, ...values: LocalBindValue[]): Promise<T[]>;
}

export interface LocalRecord {
  syncId: string;
  serverId: number | null;
  isLocalOnly: boolean;
  fields: Record<string, unknown>;
  pendingCount: number;
  failedCount: number;
}

const TABLES: Record<SyncEntityKind, string> = {
  organization: "local_organizations", person: "local_people", deal: "local_deals",
  organization_activity: "local_organization_activities", person_note: "local_person_notes",
};

export function readLocalRecord(database: RecordsDatabase, kind: SyncEntityKind, syncId: string): Promise<LocalRecord | null> {
  return withLocalRead(database, async () => {
    const row = await database.getFirstAsync<{ server_id: number | null; is_local_only: number; canonical_json: string }>(
      `SELECT server_id,is_local_only,canonical_json FROM ${TABLES[kind]} WHERE sync_id=? AND is_deleted=0 ` +
      "AND generation=(SELECT active_generation FROM sync_state WHERE singleton=1)", syncId,
    );
    if (!row) return null;
    const queued = await database.getAllAsync<{ patch_json: string; state: string }>(
      "SELECT patch_json,state FROM sync_outbox WHERE entity_kind=? AND entity_sync_id=? ORDER BY changed_at,device_id,mutation_id",
      kind, syncId,
    );
    const fields = queued.reduce((current, entry) => ({ ...current, ...JSON.parse(entry.patch_json) }), JSON.parse(row.canonical_json));
    return { syncId, serverId: row.server_id, isLocalOnly: row.is_local_only === 1, fields,
      pendingCount: queued.length, failedCount: queued.filter((entry) => entry.state === "failed").length };
  });
}
