/** Initial schema for encrypted canonical records and unsent local edits. */
export const LOCAL_SCHEMA_V1 = `
CREATE TABLE bootstrap_generations (
  id INTEGER PRIMARY KEY,
  status TEXT NOT NULL CHECK (status IN ('loading', 'active', 'retired', 'abandoned')),
  continuation_token TEXT,
  high_water INTEGER,
  started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX one_active_generation ON bootstrap_generations(status) WHERE status = 'active';

CREATE TABLE local_offers (
  slug TEXT PRIMARY KEY, server_id INTEGER NOT NULL, name TEXT NOT NULL, website TEXT,
  revenue_kind TEXT NOT NULL, display_order INTEGER NOT NULL, is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE local_organizations (
  row_id INTEGER PRIMARY KEY,
  generation INTEGER NOT NULL REFERENCES bootstrap_generations(id),
  sync_id TEXT NOT NULL,
  server_id INTEGER,
  name TEXT NOT NULL DEFAULT '',
  city TEXT, email TEXT, phone TEXT, notes TEXT,
  canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
  field_versions_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(field_versions_json)),
  is_local_only INTEGER NOT NULL DEFAULT 0 CHECK (is_local_only IN (0, 1)),
  is_deleted INTEGER NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
  UNIQUE (generation, sync_id)
);
CREATE VIRTUAL TABLE organization_search USING fts5(name, city, email, phone, notes, content='local_organizations', content_rowid='row_id');
CREATE TRIGGER organization_search_insert AFTER INSERT ON local_organizations BEGIN
  INSERT INTO organization_search(rowid,name,city,email,phone,notes) VALUES (new.row_id,new.name,new.city,new.email,new.phone,new.notes);
END;
CREATE TRIGGER organization_search_delete AFTER DELETE ON local_organizations BEGIN
  INSERT INTO organization_search(organization_search,rowid,name,city,email,phone,notes) VALUES ('delete',old.row_id,old.name,old.city,old.email,old.phone,old.notes);
END;
CREATE TRIGGER organization_search_update AFTER UPDATE ON local_organizations BEGIN
  INSERT INTO organization_search(organization_search,rowid,name,city,email,phone,notes) VALUES ('delete',old.row_id,old.name,old.city,old.email,old.phone,old.notes);
  INSERT INTO organization_search(rowid,name,city,email,phone,notes) VALUES (new.row_id,new.name,new.city,new.email,new.phone,new.notes);
END;

CREATE TABLE local_people (
  row_id INTEGER PRIMARY KEY,
  generation INTEGER NOT NULL REFERENCES bootstrap_generations(id),
  sync_id TEXT NOT NULL,
  server_id INTEGER,
  organization_sync_id TEXT,
  name TEXT NOT NULL DEFAULT '',
  city TEXT, company TEXT, email TEXT, phone TEXT, notes TEXT,
  canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
  field_versions_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(field_versions_json)),
  is_local_only INTEGER NOT NULL DEFAULT 0 CHECK (is_local_only IN (0, 1)),
  is_deleted INTEGER NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
  UNIQUE (generation, sync_id)
);
CREATE VIRTUAL TABLE person_search USING fts5(name, city, company, email, phone, notes, content='local_people', content_rowid='row_id');
CREATE TRIGGER person_search_insert AFTER INSERT ON local_people BEGIN
  INSERT INTO person_search(rowid,name,city,company,email,phone,notes) VALUES (new.row_id,new.name,new.city,new.company,new.email,new.phone,new.notes);
END;
CREATE TRIGGER person_search_delete AFTER DELETE ON local_people BEGIN
  INSERT INTO person_search(person_search,rowid,name,city,company,email,phone,notes) VALUES ('delete',old.row_id,old.name,old.city,old.company,old.email,old.phone,old.notes);
END;
CREATE TRIGGER person_search_update AFTER UPDATE ON local_people BEGIN
  INSERT INTO person_search(person_search,rowid,name,city,company,email,phone,notes) VALUES ('delete',old.row_id,old.name,old.city,old.company,old.email,old.phone,old.notes);
  INSERT INTO person_search(rowid,name,city,company,email,phone,notes) VALUES (new.row_id,new.name,new.city,new.company,new.email,new.phone,new.notes);
END;

CREATE TABLE local_deals (
  generation INTEGER NOT NULL REFERENCES bootstrap_generations(id), sync_id TEXT NOT NULL, server_id INTEGER,
  organization_sync_id TEXT, person_sync_id TEXT, offer_slug TEXT, pipeline_stage TEXT, status TEXT,
  canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)), field_versions_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(field_versions_json)),
  is_local_only INTEGER NOT NULL DEFAULT 0 CHECK (is_local_only IN (0, 1)),
  is_deleted INTEGER NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)), PRIMARY KEY (generation, sync_id)
);
CREATE INDEX local_deals_organization ON local_deals(generation, organization_sync_id);
CREATE INDEX local_deals_person ON local_deals(generation, person_sync_id);
CREATE TABLE local_organization_activities (
  generation INTEGER NOT NULL REFERENCES bootstrap_generations(id), sync_id TEXT NOT NULL, server_id INTEGER,
  organization_sync_id TEXT NOT NULL, occurred_at TEXT, canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
  field_versions_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(field_versions_json)),
  is_local_only INTEGER NOT NULL DEFAULT 0 CHECK (is_local_only IN (0, 1)),
  is_deleted INTEGER NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)), PRIMARY KEY (generation, sync_id)
);
CREATE INDEX local_activities_organization ON local_organization_activities(generation, organization_sync_id);
CREATE TABLE local_person_notes (
  generation INTEGER NOT NULL REFERENCES bootstrap_generations(id), sync_id TEXT NOT NULL, server_id INTEGER,
  person_sync_id TEXT NOT NULL, occurred_at TEXT, canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
  field_versions_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(field_versions_json)),
  is_local_only INTEGER NOT NULL DEFAULT 0 CHECK (is_local_only IN (0, 1)),
  is_deleted INTEGER NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)), PRIMARY KEY (generation, sync_id)
);
CREATE INDEX local_notes_person ON local_person_notes(generation, person_sync_id);

CREATE TABLE sync_outbox (
  local_sequence INTEGER PRIMARY KEY AUTOINCREMENT, mutation_id TEXT NOT NULL UNIQUE,
  device_id TEXT NOT NULL, entity_kind TEXT NOT NULL, entity_sync_id TEXT NOT NULL,
  operation TEXT NOT NULL, changed_at TEXT NOT NULL, patch_json TEXT NOT NULL CHECK (json_valid(patch_json)),
  state TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending', 'failed')),
  error_code TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX sync_outbox_pending ON sync_outbox(state, local_sequence);
CREATE TABLE local_provisional_changes (
  mutation_id TEXT PRIMARY KEY, entity_kind TEXT NOT NULL, entity_sync_id TEXT NOT NULL,
  changed_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'review'
);
CREATE TABLE local_tombstones (
  entity_kind TEXT NOT NULL, sync_id TEXT NOT NULL, operation TEXT NOT NULL,
  changed_at TEXT NOT NULL, merge_target_sync_id TEXT, PRIMARY KEY(entity_kind,sync_id)
);
CREATE TABLE sync_state (
  singleton INTEGER PRIMARY KEY CHECK (singleton = 1), active_generation INTEGER REFERENCES bootstrap_generations(id),
  cursor INTEGER NOT NULL DEFAULT 0 CHECK (cursor >= 0), device_id TEXT NOT NULL,
  last_bootstrap_at TEXT, last_success_at TEXT, last_correlation_id TEXT
);
PRAGMA user_version = 1;
`;

interface MigrationDatabase {
  execAsync(sql: string): Promise<void>;
  getFirstAsync<T>(sql: string): Promise<T | null>;
}

export async function applyLocalMigrations(database: MigrationDatabase): Promise<void> {
  const version = await database.getFirstAsync<{ user_version: number }>("PRAGMA user_version");
  if (!version || !Number.isInteger(version.user_version)) throw new Error("Cannot read offline database version");
  if (version.user_version > 1) throw new Error("This offline database was created by a newer app");
  if (version.user_version === 1) return;
  await database.execAsync("BEGIN IMMEDIATE");
  try {
    await database.execAsync(LOCAL_SCHEMA_V1);
    await database.execAsync("COMMIT");
  } catch (error) {
    await database.execAsync("ROLLBACK");
    throw error;
  }
}
