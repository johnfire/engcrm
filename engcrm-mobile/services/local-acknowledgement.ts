import { storeCanonicalEntity } from "./local-bootstrap";
import { applyDeletionMarker, purgeErasedEntity } from "./local-pull";
import { type LocalDatabase, withLocalWrite } from "./local-transaction";
import type { SyncEntity, SyncEntityKind } from "./sync-contracts";

export interface MutationOutcome {
  mutation_id: string;
  status: "applied" | "partially_applied" | "ignored_older" | "provisional" | "erased" |
    "rejected_validation" | "rejected_clock" | "rejected_device" | "conflict" | "retryable_error";
  entity: SyncEntity | null;
  target_state?: { operation: "soft_delete" | "merge_redirect"; changed_at: string; merge_target_sync_id?: string | null };
}

interface QueuedMutation {
  entity_kind: SyncEntityKind;
  entity_sync_id: string;
  changed_at: string;
}

async function acknowledgeApplied(database: LocalDatabase, outcome: MutationOutcome, queued: QueuedMutation): Promise<void> {
  const state = await database.getFirstAsync<{ active_generation: number | null }>(
    "SELECT active_generation FROM sync_state WHERE singleton=1",
  );
  if (!state?.active_generation) throw new Error("No active offline database");
  if (outcome.entity && outcome.entity.entity_kind === queued.entity_kind && outcome.entity.sync_id === queued.entity_sync_id) {
    await storeCanonicalEntity(database, state.active_generation, outcome.entity);
  } else if (!outcome.entity && outcome.target_state) {
    await applyDeletionMarker(database, { sequence: 0, entity_kind: queued.entity_kind, sync_id: queued.entity_sync_id,
      operation: outcome.target_state.operation, changed_at: outcome.target_state.changed_at,
      ...(outcome.target_state.merge_target_sync_id ? { merge_target_sync_id: outcome.target_state.merge_target_sync_id } : {}) });
  } else throw new Error("Sync acknowledgement does not match the pending record");
  await database.runAsync("DELETE FROM sync_outbox WHERE mutation_id=?", outcome.mutation_id);
}

async function acknowledgeErasure(database: LocalDatabase, queued: QueuedMutation): Promise<void> {
  await purgeErasedEntity(database, queued.entity_kind, queued.entity_sync_id);
  await database.runAsync("INSERT INTO local_tombstones(entity_kind,sync_id,operation,changed_at) " +
    "VALUES (?,?,'hard_erase',strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(entity_kind,sync_id) " +
    "DO UPDATE SET operation='hard_erase',changed_at=excluded.changed_at,merge_target_sync_id=NULL",
    queued.entity_kind, queued.entity_sync_id);
}

export function acknowledgeMutation(database: LocalDatabase, outcome: MutationOutcome): Promise<void> {
  return withLocalWrite(database, async () => {
    const queued = await database.getFirstAsync<QueuedMutation>(
      "SELECT entity_kind,entity_sync_id,changed_at FROM sync_outbox WHERE mutation_id=?", outcome.mutation_id,
    );
    if (!queued) return;
    if (["applied", "partially_applied", "ignored_older"].includes(outcome.status)) {
      await acknowledgeApplied(database, outcome, queued);
    } else if (outcome.status === "provisional") {
      await database.runAsync("INSERT INTO local_provisional_changes(mutation_id,entity_kind,entity_sync_id,changed_at) VALUES (?,?,?,?) " +
        "ON CONFLICT(mutation_id) DO NOTHING", outcome.mutation_id, queued.entity_kind, queued.entity_sync_id, queued.changed_at);
      await database.runAsync("DELETE FROM sync_outbox WHERE mutation_id=?", outcome.mutation_id);
    } else if (outcome.status === "erased") {
      await acknowledgeErasure(database, queued);
    } else if (outcome.status !== "retryable_error") {
      await database.runAsync("UPDATE sync_outbox SET state='failed',error_code=? WHERE mutation_id=?", outcome.status, outcome.mutation_id);
    }
  });
}
