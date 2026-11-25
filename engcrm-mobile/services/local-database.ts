import * as Crypto from "expo-crypto";
import { File } from "expo-file-system";
import * as SecureStore from "expo-secure-store";
import * as SQLite from "expo-sqlite";

import type { Server } from "./reviewer-routing";
import { applyLocalMigrations } from "./local-schema";

export interface LocalDatabaseIdentity {
  environment: Server;
  workspaceId: number;
  userId: number;
}

const openDatabases = new Map<string, Promise<SQLite.SQLiteDatabase>>();
const secureOptions = { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY };

function databaseNames(identity: LocalDatabaseIdentity): { file: string; secret: string } {
  if (!Number.isSafeInteger(identity.workspaceId) || identity.workspaceId < 1 ||
      !Number.isSafeInteger(identity.userId) || identity.userId < 1 ||
      !["production", "reviewer"].includes(identity.environment)) {
    throw new Error("A verified account and workspace are required for offline storage");
  }
  const suffix = `${identity.environment}-${identity.workspaceId}-${identity.userId}`;
  return { file: `engcrm-${suffix}.db`, secret: `engcrm_db_${suffix.replaceAll("-", "_")}` };
}

async function getDatabaseKey(fileName: string, secretName: string): Promise<string> {
  let key = await SecureStore.getItemAsync(secretName, secureOptions);
  if (key === null) {
    const databaseExists = ["", "-wal", "-shm"].some(
      (suffix) => new File(SQLite.defaultDatabaseDirectory, fileName + suffix).exists,
    );
    if (databaseExists) throw new Error("The offline database key is missing; local data has been preserved");
    const bytes = await Crypto.getRandomBytesAsync(32);
    key = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
    await SecureStore.setItemAsync(secretName, key, secureOptions);
  }
  if (!/^[0-9a-f]{64}$/.test(key)) throw new Error("The offline database key is invalid");
  return key;
}

async function openEncryptedDatabase(fileName: string, secretName: string): Promise<SQLite.SQLiteDatabase> {
  const key = await getDatabaseKey(fileName, secretName);
  const database = await SQLite.openDatabaseAsync(fileName);
  try {
    await database.execAsync(`PRAGMA key = "x'${key}'"`);
    const cipher = await database.getFirstAsync<{ cipher_version: string }>("PRAGMA cipher_version");
    if (!cipher?.cipher_version) throw new Error("This app build does not support SQLCipher");
    await database.getFirstAsync("SELECT count(*) AS count FROM sqlite_master");
    await database.execAsync("PRAGMA foreign_keys = ON");
    await applyLocalMigrations(database);
    return database;
  } catch (error) {
    await database.closeAsync();
    throw error;
  }
}

export function openLocalDatabase(identity: LocalDatabaseIdentity): Promise<SQLite.SQLiteDatabase> {
  const names = databaseNames(identity);
  const existing = openDatabases.get(names.file);
  if (existing) return existing;
  const opening = openEncryptedDatabase(names.file, names.secret).catch((error) => {
    openDatabases.delete(names.file);
    throw error;
  });
  openDatabases.set(names.file, opening);
  return opening;
}
