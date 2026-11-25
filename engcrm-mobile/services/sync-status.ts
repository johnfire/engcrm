import { type LocalDatabase, withLocalRead } from "./local-transaction";

export interface SyncStatus {
  ready: boolean;
  pending: number;
  failed: number;
  review: number;
  lastSuccessAt: string | null;
  upToDate: boolean;
}

export function readSyncStatus(database: LocalDatabase): Promise<SyncStatus> {
  return withLocalRead(database, async () => {
    const state = await database.getFirstAsync<{ active_generation: number | null; last_success_at: string | null }>(
      "SELECT active_generation,last_success_at FROM sync_state WHERE singleton=1",
    );
    const counts = await database.getFirstAsync<{ pending: number; failed: number; review: number }>(
      "SELECT (SELECT count(*) FROM sync_outbox WHERE state='pending') AS pending, " +
      "(SELECT count(*) FROM sync_outbox WHERE state='failed') AS failed, " +
      "(SELECT count(*) FROM local_provisional_changes WHERE status='review') AS review",
    );
    if (!counts) throw new Error("Cannot read synchronization status");
    const ready = state?.active_generation != null;
    const lastSuccessAt = state?.last_success_at ?? null;
    return { ready, ...counts, lastSuccessAt,
      upToDate: ready && lastSuccessAt !== null && counts.pending === 0 && counts.failed === 0 && counts.review === 0 };
  });
}
