import * as Crypto from "expo-crypto";
import { File } from "expo-file-system";
import * as SecureStore from "expo-secure-store";
import * as SQLite from "expo-sqlite";

import { openLocalDatabase } from "../../services/local-database";

jest.mock("expo-crypto", () => ({ getRandomBytesAsync: jest.fn() }));
jest.mock("expo-file-system", () => ({ File: jest.fn() }));
jest.mock("expo-sqlite", () => ({ defaultDatabaseDirectory: "/private/SQLite", openDatabaseAsync: jest.fn() }));

const execute = jest.fn();
const first = jest.fn();
const database = { execAsync: execute, getFirstAsync: first, closeAsync: jest.fn() };

beforeEach(() => {
  jest.clearAllMocks();
  jest.mocked(File).mockImplementation(() => ({ exists: false }) as File);
  jest.mocked(Crypto.getRandomBytesAsync).mockResolvedValue(new Uint8Array(32).fill(171));
  jest.mocked(SecureStore.getItemAsync).mockResolvedValue(null);
  jest.mocked(SQLite.openDatabaseAsync).mockResolvedValue(database as never);
  first.mockImplementation(async (sql: string) => sql === "PRAGMA cipher_version"
    ? { cipher_version: "4.6.0" } : sql === "PRAGMA user_version" ? { user_version: 1 } : { count: 0 });
});

it("creates a per-account key and opens an encrypted database before reading it", async () => {
  await openLocalDatabase({ environment: "production", workspaceId: 301, userId: 401 });
  expect(Crypto.getRandomBytesAsync).toHaveBeenCalledWith(32);
  expect(SecureStore.setItemAsync).toHaveBeenCalledWith(
    "engcrm_db_production_301_401", "ab".repeat(32), expect.any(Object),
  );
  expect(SQLite.openDatabaseAsync).toHaveBeenCalledWith("engcrm-production-301-401.db");
  expect(execute.mock.calls[0][0]).toBe(`PRAGMA key = "x'${"ab".repeat(32)}'"`);
  expect(first).toHaveBeenCalledWith("PRAGMA cipher_version");
});

it("refuses to replace a missing key for an existing database", async () => {
  jest.mocked(File).mockImplementation(() => ({ exists: true }) as File);
  await expect(openLocalDatabase({ environment: "reviewer", workspaceId: 302, userId: 402 }))
    .rejects.toThrow("key is missing");
  expect(SecureStore.setItemAsync).not.toHaveBeenCalled();
  expect(SQLite.openDatabaseAsync).not.toHaveBeenCalled();
});

it("refuses to use a build without SQLCipher", async () => {
  first.mockResolvedValue(null);
  await expect(openLocalDatabase({ environment: "production", workspaceId: 303, userId: 403 }))
    .rejects.toThrow("SQLCipher");
  expect(database.closeAsync).toHaveBeenCalled();
});
