import { acknowledgeMutation, type MutationOutcome } from "./local-acknowledgement";
import { type LocalBindValue, type LocalDatabase, withLocalRead } from "./local-transaction";
import { parsePullPage, parseSyncEntity } from "./sync-contracts";

export interface OutboxDatabase extends LocalDatabase {
  getAllAsync<T>(sql: string, ...values: LocalBindValue[]): Promise<T[]>;
}

interface OutboxEntry {
  local_sequence: number;
  mutation_id: string; device_id: string; entity_kind: string; entity_sync_id: string;
  operation: string; changed_at: string; patch_json: string;
}

type PushBatch = (mutations: Record<string, unknown>[]) => Promise<unknown>;
const statuses = ["applied", "partially_applied", "ignored_older", "provisional", "erased",
  "rejected_validation", "rejected_clock", "rejected_device", "conflict", "retryable_error"] as const;

function parseOutcomes(response: unknown, entries: OutboxEntry[]): MutationOutcome[] {
  if (!response || typeof response !== "object" || !("outcomes" in response) ||
      !Array.isArray(response.outcomes) || response.outcomes.length !== entries.length) {
    throw new Error("Invalid sync acknowledgement batch");
  }
  const expected = new Set(entries.map((entry) => entry.mutation_id));
  return response.outcomes.map((outcome: unknown) => {
    if (!outcome || typeof outcome !== "object" || !("mutation_id" in outcome) || !("status" in outcome) ||
        typeof outcome.mutation_id !== "string" || !expected.delete(outcome.mutation_id) ||
        !statuses.includes(outcome.status as MutationOutcome["status"])) throw new Error("Sync acknowledgement does not match the outbox");
    const status = outcome.status as MutationOutcome["status"];
    const entity = "entity" in outcome && outcome.entity != null ? parseSyncEntity(outcome.entity) : null;
    const entry = entries.find((item) => item.mutation_id === outcome.mutation_id)!;
    let targetState: MutationOutcome["target_state"];
    if ("target_state" in outcome && outcome.target_state && typeof outcome.target_state === "object") {
      const marker = outcome.target_state as Record<string, unknown>;
      const parsed = parsePullPage({ next_cursor: 1, has_more: false, changes: [{ sequence: 1,
        entity_kind: entry.entity_kind, sync_id: entry.entity_sync_id, operation: marker.operation,
        changed_at: marker.changed_at, ...(marker.merge_target_sync_id ? { merge_target_sync_id: marker.merge_target_sync_id } : {}) }] });
      const change = parsed.changes[0];
      if (change.operation !== "soft_delete" && change.operation !== "merge_redirect") throw new Error("Invalid acknowledgement marker");
      targetState = { operation: change.operation, changed_at: change.changed_at, merge_target_sync_id: change.merge_target_sync_id };
    }
    if (["applied", "partially_applied", "ignored_older"].includes(status) && !entity && !targetState) {
      throw new Error("Sync acknowledgement is missing its canonical record");
    }
    return { mutation_id: outcome.mutation_id, status, entity, target_state: targetState };
  });
}

function toMutation(entry: OutboxEntry): Record<string, unknown> {
  const patch: unknown = JSON.parse(entry.patch_json);
  if (!patch || typeof patch !== "object" || Array.isArray(patch)) throw new Error("Offline edit is corrupt");
  return { mutation_id: entry.mutation_id, device_id: entry.device_id, entity_kind: entry.entity_kind,
    entity_sync_id: entry.entity_sync_id, operation: entry.operation, changed_at: entry.changed_at, patch };
}

async function readBatch(database: OutboxDatabase, after: OutboxEntry | null): Promise<OutboxEntry[]> {
  return withLocalRead(database, () => after
    ? database.getAllAsync<OutboxEntry>("SELECT * FROM sync_outbox WHERE state='pending' " +
        "AND local_sequence>? ORDER BY local_sequence LIMIT 100", after.local_sequence)
    : database.getAllAsync<OutboxEntry>("SELECT * FROM sync_outbox WHERE state='pending' ORDER BY local_sequence LIMIT 100"));
}

async function hasServerRecord(database: OutboxDatabase, table: string, syncId: string): Promise<boolean> {
  const row = await database.getFirstAsync<{ server_id: number | null }>(
    `SELECT server_id FROM ${table} WHERE sync_id=? AND generation=(SELECT active_generation FROM sync_state WHERE singleton=1)`, syncId,
  );
  return !!row?.server_id;
}

async function isReadyToSend(database: OutboxDatabase, entry: OutboxEntry): Promise<boolean> {
  if (entry.operation !== "create") {
    const tables: Record<string, string> = { organization: "local_organizations", person: "local_people", deal: "local_deals" };
    const table = tables[entry.entity_kind];
    if (!table) throw new Error("Unknown offline edit kind");
    return hasServerRecord(database, table, entry.entity_sync_id);
  }
  const mutation = toMutation(entry);
  const patch = mutation.patch as Record<string, unknown>;
  const dependency = entry.entity_kind === "deal" ? (patch.person_sync_id ?? patch.organization_sync_id)
    : entry.entity_kind === "person" || entry.entity_kind === "organization_activity"
      ? patch.organization_sync_id : entry.entity_kind === "person_note" ? patch.person_sync_id : null;
  if (dependency != null) {
    if (typeof dependency !== "string") throw new Error("Invalid offline record dependency");
    const table = entry.entity_kind === "person_note" || (entry.entity_kind === "deal" && patch.person_sync_id != null)
      ? "local_people" : "local_organizations";
    return hasServerRecord(database, table, dependency);
  }
  return true;
}

async function readyEntries(database: OutboxDatabase, entries: OutboxEntry[], attempted: Set<string>): Promise<OutboxEntry[]> {
  return withLocalRead(database, async () => {
    const ready: OutboxEntry[] = [];
    for (const entry of entries) {
      if (!attempted.has(entry.mutation_id) && await isReadyToSend(database, entry)) ready.push(entry);
    }
    return ready;
  });
}

export async function synchronizeOutbox(database: OutboxDatabase, push: PushBatch): Promise<void> {
  let after: OutboxEntry | null = null;
  let madeProgress = false;
  let hadBlockedEntries = false;
  const attempted = new Set<string>();
  while (true) {
    const entries = await readBatch(database, after);
    if (entries.length === 0) {
      if (!hadBlockedEntries || !madeProgress) return;
      after = null;
      madeProgress = false;
      hadBlockedEntries = false;
      continue;
    }
    const ready = await readyEntries(database, entries, attempted);
    if (ready.length < entries.filter((entry) => !attempted.has(entry.mutation_id)).length) hadBlockedEntries = true;
    if (ready.length) {
      const outcomes = parseOutcomes(await push(ready.map(toMutation)), ready);
      for (const outcome of outcomes) {
        await acknowledgeMutation(database, outcome);
        attempted.add(outcome.mutation_id);
        if (["applied", "partially_applied", "ignored_older"].includes(outcome.status)) madeProgress = true;
      }
    }
    after = entries[entries.length - 1];
  }
}
