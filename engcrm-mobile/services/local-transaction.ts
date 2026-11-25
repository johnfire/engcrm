export type LocalBindValue = string | number | null;

export interface LocalDatabase {
  execAsync(sql: string): Promise<void>;
  runAsync(sql: string, ...values: LocalBindValue[]): Promise<{ lastInsertRowId: number; changes: number }>;
  getFirstAsync<T>(sql: string, ...values: LocalBindValue[]): Promise<T | null>;
}

const accessTails = new WeakMap<LocalDatabase, Promise<void>>();

function serializeAccess<T>(database: LocalDatabase, operation: () => Promise<T>): Promise<T> {
  const previous = accessTails.get(database) ?? Promise.resolve();
  const current = previous.then(operation);
  accessTails.set(database, current.then(() => undefined, () => undefined));
  return current;
}

export function withLocalRead<T>(database: LocalDatabase, operation: () => Promise<T>): Promise<T> {
  return serializeAccess(database, operation);
}

export function withLocalWrite<T>(database: LocalDatabase, operation: () => Promise<T>): Promise<T> {
  return serializeAccess(database, async () => {
    await database.execAsync("BEGIN IMMEDIATE");
    try {
      const outcome = await operation();
      await database.execAsync("COMMIT");
      return outcome;
    } catch (error) {
      await database.execAsync("ROLLBACK");
      throw error;
    }
  });
}
