import { type LocalBindValue, type LocalDatabase, withLocalRead, withLocalWrite } from "./local-transaction";
import { storeLocalEntity } from "./local-bootstrap";
import { PIPELINE_STAGES, STATUSES, type OrganizationStatus, type PipelineStage } from "./organizationState";

type EditableKind = "organization" | "person" | "deal";
type PatchValue = string | number | boolean | null;

export interface LocalUpdate {
  mutationId: string;
  deviceId: string;
  entityKind: EditableKind;
  entitySyncId: string;
  changedAt: string;
  patch: Record<string, PatchValue>;
}

export interface LocalCreate extends Omit<LocalUpdate, "entityKind"> {
  entityKind: "organization" | "person";
}

export interface LocalActivity {
  mutationId: string;
  deviceId: string;
  entityKind: "organization_activity" | "person_note";
  entitySyncId: string;
  changedAt: string;
  patch: Record<string, unknown>;
  draftId?: string;
}

export interface InitialDeal {
  mutationId: string;
  entitySyncId: string;
  offerSlug: string;
  stage: PipelineStage;
  status: OrganizationStatus;
}

interface OverlayDatabase extends LocalDatabase {
  getAllAsync<T>(sql: string, ...values: LocalBindValue[]): Promise<T[]>;
}

const EDITABLE_FIELDS: Record<EditableKind, readonly string[]> = {
  organization: ["name", "type", "city", "country", "website", "email", "phone", "decision_maker",
    "preferred_contact_method", "notes", "best_visit_time", "access_notes", "space_notes", "price_sensitivity",
    "fit_score", "do_not_contact", "email_bounced", "research_exhausted", "personal_priority", "short_term_value", "long_term_value"],
  person: ["name", "title", "email", "phone", "website", "city", "country", "relationship", "met_at", "notes",
    "linkedin_url", "is_linkedin_contact", "retention_hold", "value_rating", "short_term_value", "long_term_value"],
  deal: ["pipeline_stage", "status", "next_step", "next_step_date"],
};
const ENTITY_TABLES: Record<EditableKind, string> = {
  organization: "local_organizations", person: "local_people", deal: "local_deals",
};
const UUID_PATTERN = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;

function validateMutationIdentity(mutation: Pick<LocalUpdate, "mutationId" | "deviceId" | "entitySyncId" | "changedAt">): void {
  if (!UUID_PATTERN.test(mutation.mutationId) || !UUID_PATTERN.test(mutation.deviceId) ||
      !UUID_PATTERN.test(mutation.entitySyncId) || !/(?:Z|[+-]\d\d:\d\d)$/.test(mutation.changedAt) ||
      !Number.isFinite(Date.parse(mutation.changedAt))) throw new Error("Invalid offline edit identity");
}

function validateUpdate(update: LocalUpdate): void {
  validateMutationIdentity(update);
  const fields = EDITABLE_FIELDS[update.entityKind];
  if (!fields || !update.patch || typeof update.patch !== "object" ||
      Array.isArray(update.patch) || Object.keys(update.patch).length === 0) throw new Error("Invalid offline edit");
  for (const [field, value] of Object.entries(update.patch)) {
    if (!fields.includes(field) || !(value === null || ["string", "number", "boolean"].includes(typeof value)) ||
        (typeof value === "number" && !Number.isFinite(value))) throw new Error("Invalid offline edit field");
  }
}

function localDate(timestamp: string): string {
  const date = new Date(timestamp);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export async function queueLocalActivity(database: LocalDatabase, activity: LocalActivity): Promise<void> {
  validateMutationIdentity(activity);
  const isPerson = activity.entityKind === "person_note";
  const parentField = isPerson ? "person_sync_id" : "organization_sync_id";
  const bodyField = isPerson ? "note" : "summary";
  const allowed = isPerson
    ? [parentField, bodyField, "method", "duration_minutes", "offer_slug", "attitude", "my_read"]
    : [parentField, bodyField, "method", "duration_minutes", "offer_slug", "attitude", "my_read", "interaction_date",
       "materials_left", "next_action", "next_action_date", "follow_up_type"];
  if (!activity.patch || Array.isArray(activity.patch) || typeof activity.patch !== "object" ||
      Object.keys(activity.patch).some((field) => !allowed.includes(field)) ||
      typeof activity.patch[parentField] !== "string" || !UUID_PATTERN.test(activity.patch[parentField] as string) ||
      typeof activity.patch[bodyField] !== "string" || !(activity.patch[bodyField] as string).trim()) {
    throw new Error("Invalid offline activity");
  }
  const patch = { ...activity.patch };
  if (!isPerson && patch.interaction_date == null) patch.interaction_date = localDate(activity.changedAt);
  const fields = isPerson ? { ...patch, occurred_at: new Date(activity.changedAt).toISOString() } : patch;
  await withLocalWrite(database, async () => {
    const state = await database.getFirstAsync<{ active_generation: number | null; device_id: string }>(
      "SELECT active_generation,device_id FROM sync_state WHERE singleton=1",
    );
    if (!state?.active_generation || state.device_id !== activity.deviceId) throw new Error("Offline account or device is not ready");
    const table = isPerson ? "local_people" : "local_organizations";
    const parent = await database.getFirstAsync<{ sync_id: string }>(
      `SELECT sync_id FROM ${table} WHERE generation=? AND sync_id=? AND is_deleted=0`, state.active_generation, patch[parentField] as string,
    );
    if (!parent) throw new Error("Offline activity parent is not available");
    await storeLocalEntity(database, state.active_generation, { entity_kind: activity.entityKind, sync_id: activity.entitySyncId,
      server_id: null, fields, field_versions: {} });
    await database.runAsync("INSERT INTO sync_outbox(mutation_id,device_id,entity_kind,entity_sync_id,operation,changed_at,patch_json) " +
      "VALUES (?,?,?,?,'create',?,?)", activity.mutationId, activity.deviceId, activity.entityKind,
      activity.entitySyncId, new Date(activity.changedAt).toISOString(), JSON.stringify(patch));
    if (activity.draftId) {
      const saved = await database.runAsync("UPDATE local_activity_drafts SET state='saved',updated_at=CURRENT_TIMESTAMP " +
        "WHERE draft_id=? AND entity_kind=? AND parent_sync_id=? AND state='active'", activity.draftId, activity.entityKind, patch[parentField] as string);
      if (saved.changes !== 1) throw new Error("Offline activity draft is no longer active");
    }
  });
}

export async function queueLocalUpdate(database: LocalDatabase, update: LocalUpdate): Promise<void> {
  validateUpdate(update);
  return withLocalWrite(database, async () => {
    const state = await database.getFirstAsync<{ active_generation: number | null; device_id: string }>(
      "SELECT active_generation,device_id FROM sync_state WHERE singleton=1",
    );
    if (!state?.active_generation || state.device_id !== update.deviceId) throw new Error("Offline account or device is not ready");
    const entity = await database.getFirstAsync<{ sync_id: string }>(
      `SELECT sync_id FROM ${ENTITY_TABLES[update.entityKind]} WHERE generation=? AND sync_id=? AND is_deleted=0`,
      state.active_generation, update.entitySyncId,
    );
    if (!entity) throw new Error("Offline record is not available for editing");
    await database.runAsync(
      "INSERT INTO sync_outbox(mutation_id,device_id,entity_kind,entity_sync_id,operation,changed_at,patch_json) " +
      "VALUES (?,?,?,?,'update',?,?)", update.mutationId, update.deviceId, update.entityKind,
      update.entitySyncId, new Date(update.changedAt).toISOString(), JSON.stringify(update.patch),
    );
  });
}

function validateCreation(creation: LocalCreate): string | null {
  const { organization_sync_id: organizationId, ...ordinaryFields } = creation.patch;
  if (creation.entityKind !== "person" && organizationId !== undefined) throw new Error("Invalid organization link");
  if (organizationId != null && (typeof organizationId !== "string" || !UUID_PATTERN.test(organizationId))) {
    throw new Error("Invalid organization link");
  }
  validateUpdate({ ...creation, patch: ordinaryFields });
  if (typeof ordinaryFields.name !== "string" || !ordinaryFields.name.trim()) throw new Error("Name is required");
  return typeof organizationId === "string" ? organizationId : null;
}

async function insertLocalCreation(database: LocalDatabase, creation: LocalCreate, organizationId: string | null): Promise<number> {
  const state = await database.getFirstAsync<{ active_generation: number | null; device_id: string }>(
    "SELECT active_generation,device_id FROM sync_state WHERE singleton=1",
  );
  if (!state?.active_generation || state.device_id !== creation.deviceId) throw new Error("Offline account or device is not ready");
  if (organizationId) {
    const organization = await database.getFirstAsync<{ sync_id: string }>(
      "SELECT sync_id FROM local_organizations WHERE generation=? AND sync_id=? AND is_deleted=0", state.active_generation, organizationId,
    );
    if (!organization) throw new Error("Linked organization is not available offline");
  }
  await storeLocalEntity(database, state.active_generation, { entity_kind: creation.entityKind, sync_id: creation.entitySyncId,
    server_id: null, fields: { ...creation.patch, created_at: new Date(creation.changedAt).toISOString() }, field_versions: {} });
  await database.runAsync("INSERT INTO sync_outbox(mutation_id,device_id,entity_kind,entity_sync_id,operation,changed_at,patch_json) " +
    "VALUES (?,?,?,?,'create',?,?)", creation.mutationId, creation.deviceId, creation.entityKind,
    creation.entitySyncId, new Date(creation.changedAt).toISOString(), JSON.stringify(creation.patch));
  return state.active_generation;
}

export async function queueLocalCreate(database: LocalDatabase, creation: LocalCreate): Promise<void> {
  const organizationId = validateCreation(creation);
  await withLocalWrite(database, async () => { await insertLocalCreation(database, creation, organizationId); });
}

export async function queueLocalCreateWithInitialDeal(database: LocalDatabase, creation: LocalCreate,
                                                       deal: InitialDeal): Promise<void> {
  const organizationId = validateCreation(creation);
  validateMutationIdentity({ ...creation, mutationId: deal.mutationId, entitySyncId: deal.entitySyncId });
  if (!deal.offerSlug || !PIPELINE_STAGES.includes(deal.stage) || !STATUSES.includes(deal.status)) {
    throw new Error("Invalid initial deal");
  }
  const ownerField = creation.entityKind === "person" ? "person_sync_id" : "organization_sync_id";
  const patch = { [ownerField]: creation.entitySyncId, offer_slug: deal.offerSlug, pipeline_stage: deal.stage, status: deal.status };
  await withLocalWrite(database, async () => {
    const generation = await insertLocalCreation(database, creation, organizationId);
    await storeLocalEntity(database, generation, { entity_kind: "deal", sync_id: deal.entitySyncId,
      server_id: null, fields: patch, field_versions: {} });
    await database.runAsync("INSERT INTO sync_outbox(mutation_id,device_id,entity_kind,entity_sync_id,operation,changed_at,patch_json) " +
      "VALUES (?,?,'deal',?,'create',?,?)", deal.mutationId, creation.deviceId, deal.entitySyncId,
      new Date(creation.changedAt).toISOString(), JSON.stringify(patch));
  });
}

export async function readPendingOverlay(database: OverlayDatabase, kind: EditableKind, syncId: string,
                                         canonical: Record<string, unknown>): Promise<Record<string, unknown>> {
  return withLocalRead(database, async () => {
    const entries = await database.getAllAsync<{ patch_json: string }>(
      "SELECT patch_json FROM sync_outbox WHERE entity_kind=? AND entity_sync_id=? ORDER BY changed_at,device_id,mutation_id",
      kind, syncId,
    );
    return entries.reduce((fields, entry) => ({ ...fields, ...JSON.parse(entry.patch_json) }), { ...canonical });
  });
}
