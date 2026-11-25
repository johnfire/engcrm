import type { BootstrapPage, SyncEntity } from "./sync-contracts";
import { type LocalBindValue, type LocalDatabase, withLocalWrite } from "./local-transaction";

interface Generation {
  id: number;
  continuation_token: string | null;
  high_water: number | null;
}

export function beginBootstrap(database: LocalDatabase, deviceId: string): Promise<{ id: number; token: string | null }> {
  return withLocalWrite(database, async () => {
    await database.runAsync("INSERT INTO sync_state(singleton,device_id) VALUES (1,?) ON CONFLICT(singleton) DO NOTHING", deviceId);
    const state = await database.getFirstAsync<{ device_id: string }>("SELECT device_id FROM sync_state WHERE singleton=1");
    if (state?.device_id !== deviceId) throw new Error("Offline database belongs to a different device");
    const existing = await database.getFirstAsync<Generation>(
      "SELECT id,continuation_token,high_water FROM bootstrap_generations WHERE status='loading' ORDER BY id DESC LIMIT 1",
    );
    if (existing) return { id: existing.id, token: existing.continuation_token };
    const inserted = await database.runAsync("INSERT INTO bootstrap_generations(status) VALUES ('loading')");
    return { id: inserted.lastInsertRowId, token: null };
  });
}

type StoredEntity = Omit<SyncEntity, "server_id"> & { server_id: number | null };

function textField(entity: StoredEntity, field: string, required = false): string | null {
  const value = entity.fields[field];
  if (value == null && !required) return null;
  if (typeof value !== "string" || (required && !value.trim())) {
    throw new Error(`Invalid ${entity.entity_kind} ${field} in bootstrap`);
  }
  return value;
}

function entityColumns(entity: StoredEntity): { table: string; columns: string[]; values: LocalBindValue[] } {
  switch (entity.entity_kind) {
    case "organization":
      return { table: "local_organizations", columns: ["name", "city", "email", "phone", "notes"],
        values: [textField(entity, "name", true), textField(entity, "city"), textField(entity, "email"), textField(entity, "phone"), textField(entity, "notes")] };
    case "person":
      return { table: "local_people", columns: ["name", "organization_sync_id", "city", "company", "email", "phone", "notes"],
        values: [textField(entity, "name", true), textField(entity, "organization_sync_id"), textField(entity, "city"), textField(entity, "company"), textField(entity, "email"), textField(entity, "phone"), textField(entity, "notes")] };
    case "deal":
      return { table: "local_deals", columns: ["organization_sync_id", "person_sync_id", "offer_slug", "pipeline_stage", "status"],
        values: [textField(entity, "organization_sync_id"), textField(entity, "person_sync_id"), textField(entity, "offer_slug"), textField(entity, "pipeline_stage"), textField(entity, "status")] };
    case "organization_activity":
      return { table: "local_organization_activities", columns: ["organization_sync_id", "occurred_at"],
        values: [textField(entity, "organization_sync_id", true), textField(entity, "interaction_date")] };
    case "person_note":
      return { table: "local_person_notes", columns: ["person_sync_id", "occurred_at"],
        values: [textField(entity, "person_sync_id", true), textField(entity, "occurred_at")] };
  }
}

export async function storeCanonicalEntity(database: LocalDatabase, generationId: number, entity: SyncEntity): Promise<void> {
  const selected = entityColumns(entity);
  const columns = ["generation", "sync_id", "server_id", "canonical_json", "field_versions_json", ...selected.columns];
  const values: LocalBindValue[] = [generationId, entity.sync_id, entity.server_id, JSON.stringify(entity.fields),
    JSON.stringify(entity.field_versions), ...selected.values];
  const updates = columns.slice(2).map((column) => `${column}=excluded.${column}`).join(",") + ",is_deleted=0,is_local_only=0";
  await database.runAsync(`INSERT INTO ${selected.table}(${columns.join(",")}) VALUES (${columns.map(() => "?").join(",")}) ` +
    `ON CONFLICT(generation,sync_id) DO UPDATE SET ${updates}`, ...values);
}

export async function storeLocalEntity(database: LocalDatabase, generationId: number, entity: StoredEntity): Promise<void> {
  const selected = entityColumns(entity);
  const columns = ["generation", "sync_id", "server_id", "canonical_json", "field_versions_json", "is_local_only", ...selected.columns];
  const values: LocalBindValue[] = [generationId, entity.sync_id, null, JSON.stringify(entity.fields), "{}", 1, ...selected.values];
  const inserted = await database.runAsync(`INSERT INTO ${selected.table}(${columns.join(",")}) VALUES (${columns.map(() => "?").join(",")}) ` +
    "ON CONFLICT(generation,sync_id) DO NOTHING", ...values);
  if (inserted.changes !== 1) throw new Error("Offline record identity already exists");
}

export function saveBootstrapPage(database: LocalDatabase, generationId: number, expectedToken: string | null,
                                  page: BootstrapPage): Promise<void> {
  return withLocalWrite(database, async () => {
    const generation = await database.getFirstAsync<Generation>(
      "SELECT id,continuation_token,high_water FROM bootstrap_generations WHERE id=? AND status='loading'", generationId,
    );
    if (!generation || generation.continuation_token !== expectedToken ||
        (generation.high_water !== null && generation.high_water !== page.high_water)) {
      throw new Error("Bootstrap page does not match the saved continuation");
    }
    if (page.next_token === null) {
      const pending = await database.getFirstAsync<{ count: number }>("SELECT count(*) AS count FROM sync_outbox");
      if (pending && pending.count > 0) throw new Error("Cannot switch bootstrap generation while edits are pending");
    }
    for (const entity of page.entities) await storeCanonicalEntity(database, generationId, entity);
    await database.runAsync("UPDATE bootstrap_generations SET continuation_token=?,high_water=? WHERE id=?",
      page.next_token, page.high_water, generationId);
    if (page.next_token === null) {
      await database.runAsync("UPDATE bootstrap_generations SET status='retired' WHERE status='active'");
      await database.runAsync("UPDATE bootstrap_generations SET status='active' WHERE id=?", generationId);
      await database.runAsync("UPDATE sync_state SET active_generation=?,cursor=?,last_bootstrap_at=CURRENT_TIMESTAMP WHERE singleton=1",
        generationId, page.high_water);
    }
  });
}

export function abandonBootstrap(database: LocalDatabase, generationId: number): Promise<void> {
  return withLocalWrite(database, async () => {
    await database.runAsync("UPDATE bootstrap_generations SET status='abandoned' WHERE id=? AND status='loading'", generationId);
  });
}
