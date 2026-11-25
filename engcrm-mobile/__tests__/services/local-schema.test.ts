import { DatabaseSync } from "node:sqlite";

import { applyLocalMigrations, LOCAL_SCHEMA_V1 } from "../../services/local-schema";

it("creates searchable organization and person records in real SQLite", () => {
  const database = new DatabaseSync(":memory:");
  try {
    database.exec(LOCAL_SCHEMA_V1);
    database.prepare("INSERT INTO bootstrap_generations(id, status) VALUES (?, ?)").run(1, "active");
    database.prepare("INSERT INTO local_organizations(generation, sync_id, name, city, canonical_json) VALUES (?, ?, ?, ?, ?)")
      .run(1, "organization-uuid", "Huber GmbH", "Augsburg", "{}");
    database.prepare("INSERT INTO local_people(generation, sync_id, name, email, canonical_json) VALUES (?, ?, ?, ?, ?)")
      .run(1, "person-uuid", "Anna Huber", "anna@example.test", "{}");
    expect(database.prepare("SELECT count(*) AS total FROM organization_search WHERE organization_search MATCH ?")
      .get("Huber")).toEqual({ total: 1 });
    expect(database.prepare("SELECT count(*) AS total FROM person_search WHERE person_search MATCH ?")
      .get("Anna")).toEqual({ total: 1 });
  } finally {
    database.close();
  }
});

it("migrates an empty database once without replacing existing records", async () => {
  const database = new DatabaseSync(":memory:");
  const adapter = {
    execAsync: async (sql: string) => { database.exec(sql); },
    getFirstAsync: async <T,>(sql: string) => database.prepare(sql).get() as T,
  };
  try {
    await applyLocalMigrations(adapter);
    database.prepare("INSERT INTO bootstrap_generations(id, status) VALUES (?, ?)").run(1, "active");
    await applyLocalMigrations(adapter);
    expect(database.prepare("SELECT status FROM bootstrap_generations WHERE id=1").get()).toEqual({ status: "active" });
  } finally {
    database.close();
  }
});

it("refuses an unknown future schema without changing its contents", async () => {
  const database = new DatabaseSync(":memory:");
  database.exec("PRAGMA user_version=99; CREATE TABLE valuable_note(value TEXT); INSERT INTO valuable_note VALUES ('keep');");
  const adapter = {
    execAsync: async (sql: string) => { database.exec(sql); },
    getFirstAsync: async <T,>(sql: string) => database.prepare(sql).get() as T,
  };
  try {
    await expect(applyLocalMigrations(adapter)).rejects.toThrow("newer");
    expect(database.prepare("SELECT value FROM valuable_note").get()).toEqual({ value: "keep" });
  } finally {
    database.close();
  }
});
