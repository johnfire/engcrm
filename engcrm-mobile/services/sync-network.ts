import * as Crypto from "expo-crypto";
import * as SecureStore from "expo-secure-store";
import axios from "axios";

import { baseForServer } from "./api-origin";
import { getSession } from "./auth";
import { createBoundSyncNetwork } from "./bound-sync-network";
import type { LocalDatabaseIdentity } from "./local-database";
import type { Server } from "./reviewer-routing";

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
  const identityClient = axios.create({ baseURL: baseForServer(environment), headers: { Authorization: `Bearer ${session.token}` } });
  const response = await identityClient.get("/api/sync/identity");
  const current = await getSession();
  if (current.token !== session.token || current.server !== session.server) throw new Error("Sync session changed during identity verification");
  const identity = response.data;
  if (!identity || !Number.isSafeInteger(identity.user_id) || identity.user_id < 1 ||
      !Number.isSafeInteger(identity.workspace_id) || identity.workspace_id < 1) {
    throw new Error("Server returned an invalid sync identity");
  }
  return { environment, userId: identity.user_id, workspaceId: identity.workspace_id };
}

async function currentNetwork(deviceId: string, environment: Server, appVersion = "unknown") {
  const session = await getSession();
  if (!session.token || session.server !== environment) throw new Error("Sync session does not match the selected environment");
  return createBoundSyncNetwork(session.token, environment, deviceId, appVersion);
}

export async function registerSyncDevice(deviceId: string, environment: Server, appVersion: string): Promise<void> {
  return (await currentNetwork(deviceId, environment, appVersion)).register();
}

export async function requestBootstrapPage(deviceId: string, environment: Server, token: string | null): Promise<unknown> {
  return (await currentNetwork(deviceId, environment)).bootstrap(token);
}

export async function requestChangePage(deviceId: string, environment: Server, cursor: number): Promise<unknown> {
  return (await currentNetwork(deviceId, environment)).pull(cursor);
}

export async function requestReviewOutcomes(deviceId: string, environment: Server, mutationIds: string[]): Promise<unknown> {
  return (await currentNetwork(deviceId, environment)).reviewOutcomes!(mutationIds);
}

export async function requestPushBatch(environment: Server, mutations: Record<string, unknown>[]): Promise<unknown> {
  return (await currentNetwork("", environment)).push!(mutations);
}
