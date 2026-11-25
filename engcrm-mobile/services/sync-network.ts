import * as Crypto from "expo-crypto";
import * as SecureStore from "expo-secure-store";

import { client } from "./api";
import { getSession } from "./auth";
import type { LocalDatabaseIdentity } from "./local-database";
import type { Server } from "./reviewer-routing";
import { BootstrapExpiredError } from "./sync-bootstrap-worker";

const DEVICE_KEY = "engcrm_sync_device_id";
let devicePromise: Promise<string> | null = null;

function validUuid(value: string): boolean {
  return /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value);
}

async function loadDeviceId(): Promise<string> {
  const stored = await SecureStore.getItemAsync(DEVICE_KEY);
  if (stored !== null) {
    if (!validUuid(stored)) throw new Error("Saved sync device identifier is invalid");
    return stored;
  }
  const deviceId = Crypto.randomUUID();
  await SecureStore.setItemAsync(DEVICE_KEY, deviceId, { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY });
  return deviceId;
}

export function getSyncDeviceId(): Promise<string> {
  if (!devicePromise) devicePromise = loadDeviceId().catch((error) => { devicePromise = null; throw error; });
  return devicePromise;
}

export async function fetchSyncIdentity(environment: Server): Promise<LocalDatabaseIdentity> {
  const session = await getSession();
  if (!session.token || session.server !== environment) throw new Error("Sync session does not match the selected environment");
  const response = await client.get("/api/sync/identity");
  const current = await getSession();
  if (current.token !== session.token || current.server !== session.server) throw new Error("Sync session changed during identity verification");
  const identity = response.data;
  if (!identity || !Number.isSafeInteger(identity.user_id) || identity.user_id < 1 ||
      !Number.isSafeInteger(identity.workspace_id) || identity.workspace_id < 1) {
    throw new Error("Server returned an invalid sync identity");
  }
  return { environment, userId: identity.user_id, workspaceId: identity.workspace_id };
}

export async function registerSyncDevice(deviceId: string, environment: Server, appVersion: string): Promise<void> {
  const response = await client.post("/api/sync/devices", {
    device_id: deviceId, server_environment: environment, app_version: appVersion, schema_version: 1,
  });
  if (response.data?.protocol_version !== 1 || typeof response.data.bootstrap_required !== "boolean") {
    throw new Error("Server returned an unsupported sync protocol");
  }
}

export async function requestBootstrapPage(deviceId: string, environment: Server, token: string | null): Promise<unknown> {
  try {
    const response = await client.get("/api/sync/bootstrap", {
      params: { device_id: deviceId, server_environment: environment, ...(token ? { token } : {}) },
    });
    return response.data;
  } catch (error) {
    if (isExpiredBootstrap(error)) throw new BootstrapExpiredError("Bootstrap continuation expired");
    throw error;
  }
}

function isExpiredBootstrap(error: unknown): boolean {
  if (!error || typeof error !== "object" || !("response" in error)) return false;
  const response = error.response;
  if (!response || typeof response !== "object" || !("status" in response) || !("data" in response)) return false;
  const body = response.data;
  if (!body || typeof body !== "object" || !("detail" in body)) return false;
  return response.status === 400 && ["Invalid or expired bootstrap token", "Bootstrap token has expired"].includes(String(body.detail));
}

export async function requestChangePage(deviceId: string, environment: Server, cursor: number): Promise<unknown> {
  const response = await client.get("/api/sync/changes", {
    params: { device_id: deviceId, server_environment: environment, after: cursor },
  });
  return response.data;
}

export async function requestPushBatch(environment: Server, mutations: Record<string, unknown>[]): Promise<unknown> {
  try {
    const response = await client.post("/api/sync/push", { server_environment: environment, mutations });
    return response.data;
  } catch (error) {
    if (mutations.length === 1 && error && typeof error === "object" && "response" in error &&
        error.response && typeof error.response === "object" && "status" in error.response &&
        error.response.status === 409 && typeof mutations[0].mutation_id === "string") {
      return { outcomes: [{ mutation_id: mutations[0].mutation_id, status: "conflict", entity: null }] };
    }
    throw error;
  }
}
