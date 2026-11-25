export const SYNC_ENTITY_KINDS = ["organization", "person", "deal", "organization_activity", "person_note"] as const;
export type SyncEntityKind = (typeof SYNC_ENTITY_KINDS)[number];

export interface FieldClock {
  changed_at: string;
  device_id: string;
  mutation_id: string;
}

export interface SyncEntity {
  entity_kind: SyncEntityKind;
  sync_id: string;
  server_id: number;
  fields: Record<string, unknown>;
  field_versions: Record<string, FieldClock>;
}

export interface BootstrapPage {
  entities: SyncEntity[];
  high_water: number;
  next_token: string | null;
}

export type SyncChange =
  | (SyncEntity & { sequence: number; operation: "upsert" })
  | { sequence: number; entity_kind: SyncEntityKind; sync_id: string;
      operation: "soft_delete" | "hard_erase" | "merge_redirect";
      changed_at: string; merge_target_sync_id?: string };

export interface PullPage {
  changes: SyncChange[];
  next_cursor: number;
  has_more: boolean;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isUuid(value: unknown): value is string {
  return typeof value === "string" && /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value);
}

function isFieldClock(value: unknown): value is FieldClock {
  return isRecord(value) && isTimestamp(value.changed_at) &&
    isUuid(value.device_id) && isUuid(value.mutation_id);
}

function isTimestamp(value: unknown): value is string {
  return typeof value === "string" && /(?:Z|[+-]\d\d:\d\d)$/.test(value) && Number.isFinite(Date.parse(value));
}

export function parseSyncEntity(value: unknown): SyncEntity {
  if (!isRecord(value) || !SYNC_ENTITY_KINDS.includes(value.entity_kind as SyncEntityKind) ||
      !isUuid(value.sync_id) || !Number.isSafeInteger(value.server_id) || (value.server_id as number) < 1 ||
      !isRecord(value.fields) || !isRecord(value.field_versions) ||
      !Object.values(value.field_versions).every(isFieldClock)) {
    throw new Error("Invalid sync entity received from the server");
  }
  return value as unknown as SyncEntity;
}

export function parseBootstrapPage(value: unknown): BootstrapPage {
  if (!isRecord(value) || !Array.isArray(value.entities) || value.entities.length > 500 ||
      !Number.isSafeInteger(value.high_water) || (value.high_water as number) < 0 ||
      !(value.next_token === null || (typeof value.next_token === "string" && value.next_token.length > 0))) {
    throw new Error("Invalid bootstrap page received from the server");
  }
  return { entities: value.entities.map(parseSyncEntity), high_water: value.high_water as number,
           next_token: value.next_token as string | null };
}

function parseChange(value: unknown): SyncChange {
  if (!isRecord(value) || !Number.isSafeInteger(value.sequence) || (value.sequence as number) < 1) {
    throw new Error("Invalid sync change sequence");
  }
  if (value.operation === "upsert") return { ...parseSyncEntity(value), sequence: value.sequence as number, operation: "upsert" };
  const allowed = ["sequence", "entity_kind", "sync_id", "operation", "changed_at", "merge_target_sync_id"];
  if (!SYNC_ENTITY_KINDS.includes(value.entity_kind as SyncEntityKind) || !isUuid(value.sync_id) ||
      !["soft_delete", "hard_erase", "merge_redirect"].includes(value.operation as string) ||
      !isTimestamp(value.changed_at) || Object.keys(value).some((key) => !allowed.includes(key)) ||
      (value.operation === "merge_redirect" && !isUuid(value.merge_target_sync_id))) {
    throw new Error("Invalid sync deletion marker");
  }
  return value as unknown as SyncChange;
}

export function parsePullPage(value: unknown): PullPage {
  if (!isRecord(value) || !Array.isArray(value.changes) || value.changes.length > 500 ||
      !Number.isSafeInteger(value.next_cursor) || (value.next_cursor as number) < 0 ||
      typeof value.has_more !== "boolean" || (value.has_more && value.changes.length === 0)) {
    throw new Error("Invalid sync change page");
  }
  const changes = value.changes.map(parseChange);
  if (changes.some((change, index) => change.sequence > (value.next_cursor as number) ||
      (index > 0 && change.sequence <= changes[index - 1].sequence))) {
    throw new Error("Sync change sequence is out of order");
  }
  return { changes, next_cursor: value.next_cursor as number, has_more: value.has_more };
}
